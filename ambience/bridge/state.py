"""A live mirror of the bridge: an initial snapshot of every resource we care about, kept
current by the CLIP v2 event stream (Server-Sent Events). Everything else — the UI, sync —
reads from here instead of polling the bridge.

Threads: one reader for the event stream. Listeners are called on that thread with the
list of changed resource ids; a Qt front end re-posts them to its own thread.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from .client import Bridge, BridgeError

TRACKED = ("light", "room", "zone", "grouped_light", "scene", "device", "entertainment_configuration")


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


class HomeState:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.res: dict[str, dict] = {}            # id → resource (all types)
        self._lock = threading.RLock()
        self._listeners: list[Callable[[set[str]], None]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False

    # --- snapshot + queries -----------------------------------------------------
    def load(self) -> None:
        fresh = {}
        for t in TRACKED:
            for r in self.bridge.get(t):
                fresh[r["id"]] = r
        with self._lock:
            self.res = fresh
        self._notify(set(fresh))

    def of(self, rtype: str) -> list[dict]:
        with self._lock:
            return [r for r in self.res.values() if r.get("type") == rtype]

    def get(self, rid: str) -> dict | None:
        with self._lock:
            return self.res.get(rid)

    def lights_in(self, group: dict) -> list[dict]:
        """Lights of a room (children are devices) or zone (children are lights)."""
        with self._lock:
            by_owner = {l["owner"]["rid"]: l for l in self.res.values() if l.get("type") == "light"}
            out = []
            for c in group.get("children", []):
                if c["rtype"] == "light" and c["rid"] in self.res:
                    out.append(self.res[c["rid"]])
                elif c["rtype"] == "device" and c["rid"] in by_owner:
                    out.append(by_owner[c["rid"]])
            return out

    def grouped_light_of(self, group: dict) -> dict | None:
        for s in group.get("services", []):
            if s["rtype"] == "grouped_light":
                return self.get(s["rid"])
        return None

    def scenes_for(self, group_id: str) -> list[dict]:
        return sorted((s for s in self.of("scene") if s.get("group", {}).get("rid") == group_id),
                      key=lambda s: s["metadata"]["name"].lower())

    # --- listeners ---------------------------------------------------------------
    def subscribe(self, fn: Callable[[set[str]], None]) -> None:
        self._listeners.append(fn)

    def _notify(self, ids: set[str]) -> None:
        for fn in list(self._listeners):
            try:
                fn(ids)
            except Exception:  # noqa: BLE001 — a broken listener must not kill the stream
                pass

    # --- event stream ------------------------------------------------------------
    def apply(self, events: list[dict]) -> set[str]:
        """Apply one SSE payload (a list of {type: add|update|delete, data: [...]})."""
        changed: set[str] = set()
        with self._lock:
            for ev in events:
                for item in ev.get("data", []):
                    rid = item.get("id")
                    if not rid or item.get("type") not in TRACKED:
                        continue
                    if ev.get("type") == "delete":
                        self.res.pop(rid, None)
                    elif ev.get("type") == "add" or rid not in self.res:
                        self.res[rid] = item
                    else:
                        _merge(self.res[rid], item)
                    changed.add(rid)
        if changed:
            self._notify(changed)
        return changed

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hue-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._stream()
                backoff = 1.0
            except (OSError, BridgeError, ValueError):
                pass
            self.connected = False
            self._notify(set())
            if self._stop.wait(backoff):
                return
            backoff = min(backoff * 2, 30.0)
            try:
                self.load()  # we may have missed events while disconnected
            except (OSError, BridgeError):
                pass

    def _stream(self) -> None:
        conn = self.bridge._connect(timeout=90)  # the bridge sends a keep-alive well inside this
        try:
            conn.request("GET", "/eventstream/clip/v2",
                         headers={"hue-application-key": self.bridge.app_key, "Accept": "text/event-stream"})
            resp = conn.getresponse()
            if resp.status != 200:
                raise BridgeError(f"event stream HTTP {resp.status}")
            self.connected = True
            self._notify(set())
            data: list[str] = []
            while not self._stop.is_set():
                line = resp.readline()
                if not line:
                    raise OSError("event stream closed")
                line = line.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("data:"):
                    data.append(line[5:].lstrip())
                elif line == "" and data:
                    self.apply(json.loads("".join(data)))
                    data = []
        finally:
            conn.close()


class CommandQueue:
    """Rate-limited, coalescing writer. Rapid updates to the same resource (a dragged
    slider) collapse to the newest; sends are paced to the bridge's guidance of ~10/s
    for lights and ~1/s for grouped lights (rooms/zones)."""

    MIN_GAP = {"grouped_light": 1.0}
    DEFAULT_GAP = 0.1

    def __init__(self, bridge: Bridge, on_error: Callable[[str], None] | None = None):
        self.bridge, self.on_error = bridge, on_error
        self._pending: dict[tuple[str, str], dict] = {}
        self._last_sent: dict[str, float] = {}
        self._cv = threading.Condition()
        threading.Thread(target=self._run, name="hue-commands", daemon=True).start()

    def put(self, rtype: str, rid: str, body: dict, slot: str = "") -> None:
        """Queue a PUT. Bodies for the same (rtype, rid, slot) merge; a different `slot`
        keeps a command separate and in order — e.g. a scene's speed change must go out
        BEFORE its recall, as its own PUT (the bridge rejects the two combined)."""
        with self._cv:
            cur = self._pending.setdefault((rtype, rid, slot), {})
            _merge(cur, body)
            self._cv.notify()

    def _run(self) -> None:
        while True:
            with self._cv:
                while not self._pending:
                    self._cv.wait()
                # Oldest command whose type is off cooldown; a room waiting out its 1 s
                # gap must not hold up individual lights queued behind it.
                now = time.monotonic()
                ready_in = {k: self._last_sent.get(k[0], 0) + self.MIN_GAP.get(k[0], self.DEFAULT_GAP) - now
                            for k in self._pending}
                key = next((k for k, w in ready_in.items() if w <= 0), None)
                if key is None:
                    self._cv.wait(min(ready_in.values()))
                    continue
                body = self._pending.pop(key)
                self._last_sent[key[0]] = time.monotonic()
            try:
                self.bridge.put(key[0], key[1], body)
            except (OSError, BridgeError) as e:
                if self.on_error:
                    self.on_error(str(e))
