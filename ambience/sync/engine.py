"""The sync engine: a producer (screen or music) → HueStream over DTLS, at a steady 50 Hz.

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

LOG = __import__("pathlib").Path(__import__("os").environ.get("XDG_CACHE_HOME", __import__("pathlib").Path.home() / ".cache")) / "ambience" / "sync.log"


def log(msg: str) -> None:
    """Sync lifecycle log (~/.cache/ambience/sync.log): what happened when, for diagnosing
    reports like "the lights didn't go back". Kept short: trimmed to its last ~400 lines."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        lines = LOG.read_text().splitlines()[-400:] if LOG.exists() else []
        lines.append(time.strftime("%Y-%m-%d %H:%M:%S ") + msg)
        LOG.write_text("\n".join(lines) + "\n")
    except OSError:
        pass


@dataclass
class SyncSettings:
    intensity: str = "moderate"
    brightness: float = 0.85          # 0..1 overall
    stop: threading.Event = field(default_factory=threading.Event)


def area_channels(area: dict) -> list[dict]:
    return [{"id": c["channel_id"], "x": c.get("position", {}).get("x", 0.0),
             "z": c.get("position", {}).get("z", 0.0)} for c in area.get("channels", [])]


class ScreenProducer:
    """Screen capture → a colour per light (see colours.py)."""

    def __init__(self, capture, channels: list[dict]):
        self.capture, self.frames, self._last = capture, 0, -1
        frame, _ = capture.latest()
        h, w = (frame.shape[:2] if frame is not None else (144, 256))
        self.mapper = ColourMapper(channels, w, h)

    def step(self, settings: SyncSettings) -> dict[int, tuple]:
        frame, count = self.capture.latest()
        fresh = frame if count != self._last else None
        if fresh is not None:
            self.frames += 1
            self._last = count
        level = INTENSITIES.get(settings.intensity, INTENSITIES["moderate"])
        return self.mapper.step(fresh, level, settings.brightness)

    def preview(self) -> dict:
        frame, _ = self.capture.latest()
        if frame is None or frame.shape[0] % 36 or frame.shape[1] % 64:
            return {"frame": None}
        h, w = frame.shape[:2]       # 64×36 thumbnail of what the lights sample
        small = frame.reshape(36, h // 36, 64, w // 64, 3).mean(axis=(1, 3)).astype("uint8")
        return {"frame": small.tobytes(), "w": 64, "h": 36}


class MusicProducer:
    """What's playing → a colour per light (see music.py)."""

    def __init__(self, audio, channels: list[dict], palette: list[str] | None):
        from .music import MusicMapper
        self.audio, self.frames, self._last = audio, 0, -1
        self.mapper = MusicMapper(channels, palette)

    def step(self, settings: SyncSettings) -> dict[int, tuple]:
        from .music import MUSIC_LEVELS
        samples, count = self.audio.latest()
        if count != self._last:
            self.frames += 1
            self._last = count
        return self.mapper.step(samples, MUSIC_LEVELS.get(settings.intensity, MUSIC_LEVELS["moderate"]),
                                settings.brightness)

    def preview(self) -> dict:
        return {"bands": dict(self.mapper.last_levels), "beats": self.mapper.analyser_beats}


class SyncEngine:
    def __init__(self, bridge: Bridge, host: str, client_key: str, area: dict, producer):
        self.bridge, self.host, self.client_key, self.area, self.producer = bridge, host, client_key, area, producer
        self.stats = {"sent": 0, "started": 0.0}
        self.preview: dict[int, tuple] = {}          # last colours sent, for the UI

    @property
    def frames(self) -> int:
        return self.producer.frames

    def run(self, settings: SyncSettings) -> None:
        # Ending a session only RELEASES the lights (they keep the last streamed colour), so
        # remember how they were and put them back afterwards (see restore.py).
        from .restore import restore, snapshot
        try:
            snap = snapshot(self.bridge, self.area)
            log(f"snapshot: {len(snap.lights)} lights" + (f", scene playing ({snap.scene_action})" if snap.scene_id else ""))
        except Exception as e:  # noqa: BLE001 — sync still works; we just can't restore
            snap = None
            log(f"snapshot FAILED (lights won't be restored): {e}")
        log(f"area {self.area['id'][:8]} start → streaming mode")
        self.bridge.set_entertainment(self.area["id"], True)
        log("area started; opening DTLS")
        try:
            with DtlsPskClient(self.host, 2100, identity=self.bridge.app_key.encode(),
                               psk=bytes.fromhex(self.client_key)) as conn:
                seq = 0
                period = 1.0 / RATE_HZ
                nxt = self.stats["started"] = time.monotonic()
                while not settings.stop.is_set():
                    colours = self.producer.step(settings)
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
            log(f"stream ended after {self.stats['sent']} updates; stopping the area")
            try:
                self.bridge.set_entertainment(self.area["id"], False)
                log("area stopped: bridge accepted action=stop")
            except Exception as e:  # noqa: BLE001 — best effort; the bridge also times out on its own
                log(f"area stop FAILED: {e}")
            if snap is not None:
                try:
                    restore(self.bridge, snap, log)
                except Exception as e:  # noqa: BLE001
                    log(f"restore FAILED: {e}")
