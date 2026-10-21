"""The sync engine: capture → colours → HueStream over DTLS, at a steady 50 Hz.

Lifecycle (the bridge's rules): put the entertainment area in streaming mode (PUT
action=start), open the DTLS connection, send continuously (the bridge drops the stream
after ~10 s of silence), and ALWAYS stop the area at the end so the lights return to
normal control — even on errors.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from ..bridge.client import Bridge
from ..stream.dtls import DtlsPskClient
from ..stream.huestream import encode_rgb
from .colours import INTENSITIES, ColourMapper

RATE_HZ = 50


@dataclass
class SyncSettings:
    intensity: str = "moderate"
    brightness: float = 0.85          # 0..1 overall
    stop: threading.Event = field(default_factory=threading.Event)


def area_channels(area: dict) -> list[dict]:
    return [{"id": c["channel_id"], "x": c.get("position", {}).get("x", 0.0),
             "z": c.get("position", {}).get("z", 0.0)} for c in area.get("channels", [])]


class SyncEngine:
    def __init__(self, bridge: Bridge, host: str, client_key: str, area: dict, source):
        """source: anything with latest() → (HxWx3 uint8 frame | None, frame counter)."""
        self.bridge, self.host, self.client_key, self.area, self.source = bridge, host, client_key, area, source
        self.stats = {"sent": 0, "frames": 0, "started": 0.0}
        self.preview: dict[int, tuple] = {}          # last colours sent, for the UI

    def run(self, settings: SyncSettings) -> None:
        chans = area_channels(self.area)
        frame, _ = self.source.latest()
        h, w = (frame.shape[:2] if frame is not None else (144, 256))
        mapper = ColourMapper(chans, w, h)
        self.bridge.set_entertainment(self.area["id"], True)
        try:
            with DtlsPskClient(self.host, 2100, identity=self.bridge.app_key.encode(),
                               psk=bytes.fromhex(self.client_key)) as conn:
                seq, last_count = 0, -1
                period = 1.0 / RATE_HZ
                nxt = self.stats["started"] = time.monotonic()
                while not settings.stop.is_set():
                    frame, count = self.source.latest()
                    fresh = frame if count != last_count else None
                    if fresh is not None:
                        self.stats["frames"] += 1
                        last_count = count
                    level = INTENSITIES.get(settings.intensity, INTENSITIES["moderate"])
                    colours = mapper.step(fresh, level, settings.brightness)
                    if colours:
                        conn.send(encode_rgb(self.area["id"], seq, colours))
                        self.preview = colours
                        seq += 1
                        self.stats["sent"] += 1
                    nxt += period
                    time.sleep(max(0.0, nxt - time.monotonic()))
                    if time.monotonic() - nxt > 0.5:     # fell far behind (suspend?) — don't burst
                        nxt = time.monotonic()
        finally:
            try:
                self.bridge.set_entertainment(self.area["id"], False)
            except Exception:  # noqa: BLE001 — best effort; the bridge also times out on its own
                pass
