"""What the computer is playing, via PipeWire's monitor of the default output (through the
PulseAudio compatibility layer: `@DEFAULT_MONITOR@`). No microphone, no permission dialog —
it hears exactly what your speakers/headphones get. Mono float32 at 48 kHz, kept in a short
ring buffer the music analyser reads from.
"""
from __future__ import annotations

import threading

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

import numpy as np  # noqa: E402

RATE = 48000
KEEP = 8192          # ~170 ms of history: enough for a 4096-point FFT with overlap


class AudioCaptureError(RuntimeError):
    pass


class AudioCapture:
    def __init__(self, device: str = "@DEFAULT_MONITOR@"):
        self.device = device
        self._buf = np.zeros(KEEP, np.float32)
        self._count = 0
        self._lock = threading.Lock()
        self._pipeline = None
        self.error = ""

    def start(self) -> None:
        Gst.init(None)
        desc = (f"pulsesrc device={self.device} client-name=Ambience "
                "! audioconvert ! audioresample "
                f"! audio/x-raw,format=F32LE,channels=1,rate={RATE} "
                "! appsink name=sink emit-signals=true sync=false max-buffers=4 drop=true")
        try:
            self._pipeline = Gst.parse_launch(desc)
        except Exception as e:  # noqa: BLE001
            raise AudioCaptureError(f"audio pipeline failed: {e}") from e
        self._pipeline.get_by_name("sink").connect("new-sample", self._on_sample)
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise AudioCaptureError("couldn't listen to the sound output (is PipeWire running?)")

    def latest(self) -> tuple[np.ndarray, int]:
        """(the newest KEEP samples, block counter)."""
        with self._lock:
            return self._buf.copy(), self._count

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None

    def _on_sample(self, sink):
        smp = sink.emit("pull-sample")
        buf = smp.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if ok:
            try:
                a = np.frombuffer(info.data, np.float32)
                with self._lock:
                    n = min(len(a), KEEP)
                    self._buf = np.concatenate([self._buf[n:], a[-n:]])
                    self._count += 1
            finally:
                buf.unmap(info)
        return Gst.FlowReturn.OK
