"""Music → light. Fifty times a second:

1. Analyse the newest audio: energy in bass (40–150 Hz), mids (150–2 kHz) and highs
   (2–10 kHz), each auto-levelled against its own recent peak — so quiet jazz and loud EDM
   both use the full range — plus a beat detector on bass "flux" (a sudden rise above its
   recent average).
2. Each light shows a colour from the chosen palette. Its brightness follows one band,
   picked by its height in the entertainment area (floor lights → bass, mid-height → mids,
   ceiling lights → highs). Beats rotate the colours between lights and kick brightness.
3. The intensity level sets how hard brightness pulses, how quickly it decays, and how
   many beats pass between colour changes. Silence fades to a calm, dim palette glow.
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass

import numpy as np

from .audio import RATE

FFT = 4096
_WINDOW = np.hanning(FFT).astype(np.float32)
_FREQS = np.fft.rfftfreq(FFT, 1 / RATE)
BANDS = {"bass": (40, 150), "mids": (150, 2000), "highs": (2000, 10000)}
_MASKS = {k: (_FREQS >= lo) & (_FREQS < hi) for k, (lo, hi) in BANDS.items()}


@dataclass(frozen=True)
class MusicLevel:
    pulse: float          # how much brightness follows the music (0 = steady)
    decay: float          # per-update fall-off after a peak (higher = snappier)
    beats_per_change: int # colours rotate every N beats
    kick: float           # extra brightness on a beat


MUSIC_LEVELS = {
    "subtle":   MusicLevel(pulse=0.35, decay=0.04, beats_per_change=8, kick=0.0),
    "moderate": MusicLevel(pulse=0.6,  decay=0.08, beats_per_change=4, kick=0.15),
    "high":     MusicLevel(pulse=0.8,  decay=0.14, beats_per_change=2, kick=0.3),
    "intense":  MusicLevel(pulse=0.95, decay=0.22, beats_per_change=1, kick=0.45),
}

DEFAULT_PALETTE = ["#ff2e63", "#7c3aed", "#08d9d6", "#ffb000", "#3b82f6"]


class MusicAnalyser:
    """Band energies (0..1, auto-levelled) + beat flag for one audio window."""

    def __init__(self):
        self.peaks = {k: 1e-4 for k in BANDS}
        self.flux_avg = 1e-4
        self.prev_bass = 0.0
        self.since_beat = 99

    def analyse(self, samples: np.ndarray) -> tuple[dict[str, float], bool, float]:
        x = samples[-FFT:] * _WINDOW
        mag = np.abs(np.fft.rfft(x))
        loudness = float(np.sqrt(np.mean(samples[-FFT:] ** 2)))
        raw = {k: float(mag[m].mean()) for k, m in _MASKS.items()}
        levels = {}
        for k, v in raw.items():
            # auto-level: peak follows up instantly, sinks slowly (~6 s half-life)
            self.peaks[k] = max(v, self.peaks[k] * 0.9977, 1e-4)
            levels[k] = min(1.0, v / self.peaks[k])
        flux = max(0.0, raw["bass"] - self.prev_bass)
        self.prev_bass = raw["bass"]
        self.flux_avg = self.flux_avg * 0.95 + flux * 0.05
        self.since_beat += 1
        beat = flux > self.flux_avg * 2.2 and levels["bass"] > 0.5 and self.since_beat >= 12  # ≥240 ms apart
        if beat:
            self.since_beat = 0
        return levels, beat, loudness


def _rgb(hex_: str) -> tuple[float, float, float]:
    return tuple(int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))


class MusicMapper:
    def __init__(self, channels: list[dict], palette: list[str] | None = None):
        self.channels = channels
        self.palette = [_rgb(h) for h in (palette or DEFAULT_PALETTE)] or [_rgb(DEFAULT_PALETTE[0])]
        self.analyser = MusicAnalyser()
        self.offset = 0
        self.beats = 0
        self.bright = {c["id"]: 0.0 for c in channels}
        self.silent_for = 0
        self.last_levels = {k: 0.0 for k in BANDS}
        self.last_beat = False
        self.analyser_beats = 0          # every beat detected (the preview counts these)

    @staticmethod
    def _band_for(z: float) -> str:
        return "bass" if z < -0.33 else ("highs" if z > 0.33 else "mids")

    def step(self, samples: np.ndarray, level: MusicLevel, brightness: float) -> dict[int, tuple]:
        levels, beat, loudness = self.analyser.analyse(samples)
        self.last_levels, self.last_beat = levels, beat
        self.silent_for = self.silent_for + 1 if loudness < 0.003 else 0
        if beat:
            self.analyser_beats += 1
            self.beats += 1
            if self.beats % level.beats_per_change == 0:
                self.offset = (self.offset + 1) % len(self.palette)
        out = {}
        silent = self.silent_for > 100      # ~2 s of silence → calm glow
        for i, c in enumerate(self.channels):
            band = levels[self._band_for(c["z"])]
            target = 0.15 if silent else (1 - level.pulse) * 0.55 + level.pulse * band + (level.kick if beat else 0)
            cur = self.bright[c["id"]]
            # rise instantly with the music, fall at the level's decay rate
            cur = target if target > cur else cur + (target - cur) * (0.05 if silent else level.decay)
            self.bright[c["id"]] = cur
            r, g, b = self.palette[(i + self.offset) % len(self.palette)]
            v = max(0.05, min(1.0, cur)) * brightness
            out[c["id"]] = (r * v, g * v, b * v)
        return out


def vivid(hexes: list[str]) -> list[str]:
    """Keep a palette's hues but make every colour fully saturated and bright — music sync
    reads best in vivid colour (a scene's pastel or dim tones look washed out pulsing)."""
    out = []
    for h in hexes:
        r, g, b = _rgb(h)
        hh, s, v = colorsys.rgb_to_hsv(r, g, b)
        r, g, b = colorsys.hsv_to_rgb(hh, max(s, 0.75), 1.0)
        out.append("#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)))
    return out
