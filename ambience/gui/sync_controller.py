"""The window's side of sync: owns the worker process, forwards the user's choices, and turns
the worker's ~8/s reports into properties the Sync page binds to (status, rates, each
light's live colour, and the thumbnail the lights sample — served to QML as image://sync)."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from ..sync.worker import run_worker

SETTINGS = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ambience" / "sync.json"
INTENSITY_NAMES = ["subtle", "moderate", "high", "intense"]


class SyncFrameProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.image = QImage(64, 36, QImage.Format_RGB888)
        self.image.fill(0x121318)

    def requestImage(self, _id, size, _requested):
        size.setWidth(self.image.width())
        size.setHeight(self.image.height())
        return self.image


def _name(r: dict) -> str:
    return (r.get("metadata") or {}).get("name", "?")


class SyncController(QObject):
    changed = Signal()
    previewChanged = Signal()

    def __init__(self, backend, provider: SyncFrameProvider):
        super().__init__(backend)
        self.backend, self.provider = backend, provider
        self._proc = self._conn = None
        self._state, self._message = "stopped", ""
        self._rate = self._fps = 0.0
        self._colours: dict[int, list] = {}
        self._frame_version = 0
        saved = {}
        try:
            saved = json.loads(SETTINGS.read_text())
        except (OSError, ValueError):
            pass
        self._area_id = saved.get("area", "")
        self._intensity = saved.get("intensity", "moderate")
        self._brightness = float(saved.get("brightness", 0.85))
        self._poll = QTimer(self, interval=60)
        self._poll.timeout.connect(self._drain)

    def _save(self):
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({"area": self._area_id, "intensity": self._intensity,
                                        "brightness": self._brightness}))

    # --- areas ---------------------------------------------------------------------
    def _areas(self) -> list[dict]:
        st = self.backend.state
        return sorted(st.of("entertainment_configuration"), key=_name) if st else []

    def _area(self) -> dict | None:
        areas = self._areas()
        return next((a for a in areas if a["id"] == self._area_id), areas[0] if areas else None)

    @Property("QVariantList", notify=changed)
    def areas(self):
        return [{"id": a["id"], "name": _name(a), "type": a.get("configuration_type", ""),
                 "lights": len(a.get("channels", []))} for a in self._areas()]

    @Property("QVariantMap", notify=changed)
    def area(self):
        a = self._area()
        if not a:
            return {}
        return {"id": a["id"], "name": _name(a), "type": a.get("configuration_type", ""),
                "lights": len(a.get("channels", []))}

    @Slot(str)
    def chooseArea(self, area_id: str):
        if self._state in ("running", "starting"):
            return
        self._area_id = area_id
        self._save()
        self.changed.emit()

    @Property("QVariantList", notify=previewChanged)
    def lamps(self):
        """Each channel's position (top-down: x left→right, y back→front) + live colour."""
        a = self._area()
        out = []
        for c in (a or {}).get("channels", []):
            p = c.get("position", {})
            rgb = self._colours.get(c["channel_id"])
            col = "#%02x%02x%02x" % tuple(int(v * 255) for v in rgb) if rgb and self._state == "running" else "#3a3f4a"
            out.append({"id": c["channel_id"], "x": p.get("x", 0), "y": p.get("y", 0), "z": p.get("z", 0), "colour": col})
        # Display only: lights set up almost on top of each other would hide one another on
        # the map, so nudge near-duplicates apart (sync itself uses the exact positions).
        for i, a_ in enumerate(out):
            for b_ in out[:i]:
                dx, dy = a_["x"] - b_["x"], a_["y"] - b_["y"]
                if dx * dx + dy * dy < 0.2 ** 2:
                    a_["y"] = max(-1.0, min(1.0, b_["y"] - 0.22 if b_["y"] > -0.7 else b_["y"] + 0.22))
                    a_["x"] = max(-1.0, min(1.0, a_["x"] + (0.12 if a_["x"] < 0.8 else -0.12)))
        return out

    # --- settings ------------------------------------------------------------------
    @Property(str, notify=changed)
    def intensity(self):
        return self._intensity

    @Slot(str)
    def setIntensity(self, name: str):
        if name in INTENSITY_NAMES:
            self._intensity = name
            self._send({"cmd": "set", "intensity": name})
            self._save()
            self.changed.emit()

    @Property(float, notify=changed)
    def brightness(self):
        return self._brightness * 100

    @Slot(float)
    def setBrightness(self, pct: float):
        self._brightness = max(0.05, min(1.0, pct / 100))
        self._send({"cmd": "set", "brightness": self._brightness})
        self._save()
        self.changed.emit()

    # --- status --------------------------------------------------------------------
    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(str, notify=previewChanged)
    def rateText(self):
        if self._state != "running":
            return ""
        return f"{self._rate:.0f} updates/s · screen {self._fps:.0f} fps"

    @Property(int, notify=previewChanged)
    def frameVersion(self):
        return self._frame_version

    # --- start / stop ----------------------------------------------------------------
    def _send(self, msg: dict):
        if self._conn is not None:
            try:
                self._conn.send(msg)
            except (OSError, BrokenPipeError):
                self._conn = None

    def _ensure_worker(self):
        if self._proc is None or not self._proc.is_alive():
            ctx = mp.get_context("spawn")
            self._conn, child = ctx.Pipe()
            self._proc = ctx.Process(target=run_worker, args=(child,), name="ambience-sync", daemon=True)
            self._proc.start()
            self._poll.start()

    @Slot()
    def start(self):
        area = self._area()
        st = self.backend.state
        if not area or not st or self._state in ("running", "starting"):
            return
        from ..bridge import store
        got = store.load()
        if not got:
            return
        pairing, app_key, client_key = got
        self._ensure_worker()
        self._state, self._message = "starting", ""
        self.changed.emit()
        self._send({"cmd": "start", "area": area, "host": pairing.host, "cert": pairing.cert_sha256,
                    "app_key": app_key, "client_key": client_key,
                    "intensity": self._intensity, "brightness": self._brightness})

    @Slot()
    def stop(self):
        self._send({"cmd": "stop"})

    def shutdown(self):
        """Window closing: stop streaming (hands the lights back) and end the worker."""
        if self._proc is not None and self._proc.is_alive():
            self._send({"cmd": "quit"})
            self._proc.join(6)
            if self._proc.is_alive():
                self._proc.terminate()

    def _drain(self):
        got_preview = False
        while self._conn is not None:
            try:
                if not self._conn.poll():
                    break
                msg = self._conn.recv()
            except (EOFError, OSError):
                self._conn = None
                if self._state in ("running", "starting"):
                    self._state, self._message = "error", "The sync process stopped unexpectedly."
                    self.changed.emit()
                break
            if "state" in msg:
                self._state, self._message = msg["state"], msg.get("message", "")
                if self._state != "running":
                    self._colours = {}
                    got_preview = True
                self.changed.emit()
            elif "preview" in msg:
                p = msg["preview"]
                self._colours = {int(k): v for k, v in p["colours"].items()}
                self._rate, self._fps = p["rate"], p["fps"]
                if p.get("frame"):
                    self.provider.image = QImage(p["frame"], p["w"], p["h"], p["w"] * 3, QImage.Format_RGB888).copy()
                    self._frame_version += 1
                got_preview = True
        if got_preview:
            self.previewChanged.emit()
