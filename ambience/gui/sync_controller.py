"""The window's side of sync: owns the worker process, forwards the user's choices, and turns
the worker's ~8/s reports into properties the Sync page binds to (status, rates, each
light's live colour, and the thumbnail the lights sample — served to QML as image://sync)."""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import time
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



def _edge_anchor(x: float, y: float) -> list[float]:
    """A top-down position (x left→right, y back→front, -1..1) pushed out onto the window's
    edge, as 0..1 coordinates with the front at the top."""
    dx, dy = x / 2, -y / 2
    m = max(abs(dx), abs(dy))
    if m < 1e-3:
        return [0.5, 0.0]
    t = 0.5 / m
    return [0.5 + dx * t, 0.5 + dy * t]


def _resting(light: dict | None) -> tuple[float, float, float] | None:
    """A light's current colour, 0..1, scaled by brightness; dark when off."""
    if not light:
        return None
    if not light.get("on", {}).get("on"):
        return (0.0, 0.0, 0.0)
    from ..colour import light_hex
    h = light_hex(light)
    level = 0.45 + 0.55 * (light.get("dimming") or {}).get("brightness", 100) / 100
    return tuple(int(h[i:i + 2], 16) / 255 * level for i in (1, 3, 5))

class SyncController(QObject):
    changed = Signal()
    previewChanged = Signal()
    glowChanged = Signal()       # the edge glow's colours: ~30/s while syncing

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
        self._mode = saved.get("mode", "screen")
        self._palette_id = saved.get("palette", "party")
        self._bands = {"bass": 0.0, "mids": 0.0, "highs": 0.0}
        self._beat_count = 0
        self._intensity = saved.get("intensity", "moderate")
        self._brightness = float(saved.get("brightness", 0.85))
        self._poll = QTimer(self, interval=16)
        backend.changed.connect(self.glowChanged)   # resting light colours
        self._poll.timeout.connect(self._drain)

    def _save(self):
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({"area": self._area_id, "intensity": self._intensity,
                                        "brightness": self._brightness, "mode": self._mode,
                                        "palette": self._palette_id}))

    # --- mode + music palette ---------------------------------------------------------
    @Property(str, notify=changed)
    def mode(self):
        return self._mode

    @Slot(str)
    def setMode(self, mode: str):
        if mode in ("screen", "music") and self._state not in ("running", "starting"):
            self._mode = mode
            self._save()
            self.changed.emit()

    def _palettes(self) -> list[dict]:
        from ..colour import palette_hexes
        from ..presets import PRESETS
        from ..sync.music import DEFAULT_PALETTE
        out = [{"id": "party", "name": "Party (built in)", "glow": DEFAULT_PALETTE}]
        out += [{"id": "preset:" + p.id, "name": p.name + " · gallery", "glow": list(p.colours)} for p in PRESETS]
        st = self.backend.state
        if st:
            seen = set()
            for sc in sorted(st.of("scene"), key=_name):
                pal = palette_hexes(sc)
                if len(pal) >= 3 and _name(sc) not in seen:     # one entry per name (rooms share scenes)
                    seen.add(_name(sc))
                    out.append({"id": "scene:" + sc["id"], "name": _name(sc), "glow": pal})
        return out

    @Property("QVariantList", notify=changed)
    def palettes(self):
        return self._palettes()

    @Property("QVariantMap", notify=changed)
    def palette(self):
        ps = self._palettes()
        return next((p for p in ps if p["id"] == self._palette_id), ps[0])

    @Slot(str)
    def choosePalette(self, pid: str):
        self._palette_id = pid
        self._save()
        self.changed.emit()

    @Property("QVariantMap", notify=previewChanged)
    def bands(self):
        return dict(self._bands)

    @Property(int, notify=previewChanged)
    def beatCount(self):
        return self._beat_count

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

    # --- edge glow -------------------------------------------------------------------
    @Property(bool, notify=changed)
    def syncing(self):
        return self._state == "running"

    @Property("QVariantList", notify=glowChanged)
    def edgeLamps(self):
        """Up to 8 lights for the window's edge glow: an anchor on the window's edge (where
        the light sits in the area, front = top, as on the Sync page's map) and a colour
        0..1 at its brightness. While syncing: the streamed colours. Otherwise: the lights'
        current colours from the bridge (off = dark)."""
        st = self.backend.state
        area = self._area()
        out = []
        if area and st:
            by_ent = {}                                   # entertainment service → light
            for d in st.of("device"):
                svcs = d.get("services", [])
                light = next((s["rid"] for s in svcs if s.get("rtype") == "light"), None)
                for s in svcs:
                    if s.get("rtype") == "entertainment" and light:
                        by_ent[s["rid"]] = light
            for c in area.get("channels", [])[:8]:
                p = c.get("position", {})
                if self._state == "running":
                    rgb = self._colours.get(c["channel_id"])
                    if rgb is None:
                        continue
                else:
                    lid = next((by_ent.get(m.get("service", {}).get("rid")) for m in c.get("members", [])), None)
                    rgb = _resting(st.get(lid)) if lid else None
                    if rgb is None:
                        continue
                out.append({"anchor": _edge_anchor(p.get("x", 0.0), p.get("y", 0.0)), "rgb": list(rgb)})
        elif st:                                          # no area: every light, spread around
            lights = sorted(st.of("light"), key=_name)[:8]
            for i, l in enumerate(lights):
                a = 2 * math.pi * i / max(1, len(lights))
                out.append({"anchor": _edge_anchor(math.sin(a), math.cos(a)), "rgb": list(_resting(l))})
        return out

    @Property("QVariantList", notify=glowChanged)
    def accentColours(self):
        """The lights' colours at full strength (a dimmed light still gives a clear colour),
        ordered left → right as they sit in the room, for sliders and level bars. Dark and
        faint lights are skipped — below a quarter of the brightest one, so mid-sync only the
        lights that are actually lit count; near-duplicates collapse. Empty → amber."""
        lamps = sorted(self.edgeLamps, key=lambda l: (l["anchor"][0], l["anchor"][1]))
        floor = max(0.03, 0.25 * max((max(l["rgb"]) for l in lamps), default=0))
        out: list[tuple] = []
        for l in lamps:
            r, g, b = l["rgb"]
            m = max(r, g, b)
            if m < floor:
                continue
            c = (r / m, g / m, b / m)
            if all(max(abs(a - b) for a, b in zip(c, o)) > 0.12 for o in out):
                out.append(c)
        return ["#%02x%02x%02x" % tuple(round(v * 255) for v in c) for c in out]

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
        src = "screen" if self._mode == "screen" else "audio"
        return f"{self._rate:.0f} updates/s · {src} {self._fps:.0f}/s"

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
        from ..sync.music import vivid
        self._send({"cmd": "start", "mode": self._mode, "area": area, "host": pairing.host,
                    "cert": pairing.cert_sha256, "app_key": app_key, "client_key": client_key,
                    "intensity": self._intensity, "brightness": self._brightness,
                    "palette": vivid(self.palette["glow"])})

    @Slot()
    def stop(self):
        self._send({"cmd": "stop"})

    def shutdown(self):
        """App quitting: stop streaming (hands the lights back) and end the worker.

        Keep READING the pipe while we wait. Once the event loop has stopped nobody drains
        it, the worker's ~55 KB/s of previews fill it within a second, the worker blocks in
        send() and never sees "quit" — it then got force-killed before stopping the area, so
        the lights froze on the last colour. As a safety net, if the worker never confirms it
        stopped, end the area's session from here (idempotent)."""
        if self._proc is None or not self._proc.is_alive():
            return
        area = self._area() if self._state in ("running", "starting") else None
        stopped = area is None
        self._send({"cmd": "quit"})
        deadline = time.monotonic() + 8
        while self._proc.is_alive() and time.monotonic() < deadline:
            try:
                while self._conn is not None and self._conn.poll(0.05):
                    msg = self._conn.recv()
                    if msg.get("state") in ("stopped", "error"):
                        stopped = True
            except (EOFError, OSError):
                self._proc.join(1)
                break
        if self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(2)
        from ..sync.engine import log
        log(f"window: shutdown — worker {'confirmed stop' if stopped else 'did NOT confirm stop'}")
        if area and not stopped and self.backend.bridge is not None:
            log("window: safety-net stop of the area")
            try:
                self.backend.bridge.set_entertainment(area["id"], False)
            except Exception:  # noqa: BLE001 — best effort; the bridge also times out on its own
                pass

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
                self.glowChanged.emit()
                self.changed.emit()
            elif "glow" in msg:
                self._colours = {int(k): v for k, v in msg["glow"].items()}
                self.glowChanged.emit()
            elif "preview" in msg:
                p = msg["preview"]
                self._colours = {int(k): v for k, v in p["colours"].items()}
                self._rate, self._fps = p["rate"], p["fps"]
                if "bands" in p:
                    self._bands = p["bands"]
                    self._beat_count = int(p.get("beats", self._beat_count))
                if p.get("frame"):
                    self.provider.image = QImage(p["frame"], p["w"], p["h"], p["w"] * 3, QImage.Format_RGB888).copy()
                    self._frame_version += 1
                got_preview = True
        if got_preview:
            self.previewChanged.emit()
