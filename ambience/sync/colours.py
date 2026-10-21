"""Screen frame → one colour per entertainment channel.

Each light gets a soft "region of interest" on the screen, centred where it sits in the
entertainment area: x (-1 left … +1 right) picks the column, z (-1 floor … +1 ceiling) the
row. Regions are Gaussian, so neighbouring lights blend instead of flickering at edges.
Averaging happens in LINEAR light (how light actually mixes); the result is then shaped by
the intensity level — saturation boost, brightness response, and how fast it follows.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Intensity:
    saturation: float   # boost (1 = as on screen)
    follow: float       # per-update smoothing factor at 50 Hz (higher = snappier)
    floor: float        # minimum brightness so dark scenes dim the room rather than black it out
    gamma: float        # brightness response (<1 lifts mid-tones)


INTENSITIES = {
    "subtle":   Intensity(saturation=1.05, follow=0.06, floor=0.08, gamma=0.9),
    "moderate": Intensity(saturation=1.25, follow=0.14, floor=0.05, gamma=0.8),
    "high":     Intensity(saturation=1.45, follow=0.30, floor=0.03, gamma=0.75),
    "intense":  Intensity(saturation=1.65, follow=0.55, floor=0.0,  gamma=0.7),
}

_SRGB_TO_LIN = ((np.arange(256) / 255.0) ** 2.2).astype(np.float32)   # close enough for averaging


class ColourMapper:
    def __init__(self, channels: list[dict], width: int, height: int,
                 sigma_x: float = 0.16, sigma_y: float = 0.22):
        """channels: [{"id": int, "x": float, "z": float}, …] from the entertainment area."""
        self.ids = [c["id"] for c in channels]
        u = (np.arange(width) + 0.5) / width
        v = (np.arange(height) + 0.5) / height
        weights = []
        for c in channels:
            cu, cv = (c["x"] + 1) / 2, (1 - c["z"]) / 2          # z=+1 (ceiling) → top row
            wu = np.exp(-((u - cu) ** 2) / (2 * sigma_x ** 2))
            wv = np.exp(-((v - cv) ** 2) / (2 * sigma_y ** 2))
            w = np.outer(wv, wu).astype(np.float32)
            weights.append(w / w.sum())
        self._w = np.stack(weights).reshape(len(channels), -1)    # (channels, H*W)
        self._state: np.ndarray | None = None                      # smoothed linear RGB per channel

    def target(self, frame: np.ndarray) -> np.ndarray:
        """Raw per-channel average colour (linear RGB 0..1) for one frame."""
        lin = _SRGB_TO_LIN[frame].reshape(-1, 3)                    # (H*W, 3)
        return self._w @ lin                                        # (channels, 3)

    def step(self, frame: np.ndarray | None, level: Intensity, brightness: float) -> dict[int, tuple]:
        """Advance one update: smooth toward the frame's colours and shape them.
        Returns {channel_id: (r, g, b)} in 0..1, gamma-encoded for the bridge."""
        if frame is not None:
            tgt = self.target(frame)
            self._state = tgt if self._state is None else self._state + level.follow * (tgt - self._state)
        if self._state is None:
            return {}
        out = {}
        for cid, rgb in zip(self.ids, self._state):
            out[cid] = shape(rgb, level, brightness)
        return out


def shape(lin_rgb: np.ndarray, level: Intensity, brightness: float) -> tuple[float, float, float]:
    """Saturation boost + brightness response on one linear colour; returns sRGB 0..1."""
    peak = float(lin_rgb.max())
    if peak <= 1e-6:
        v = level.floor * brightness
        return (v * 0.6, v * 0.5, v * 0.45)                       # a dim warm glow, not black
    chroma = lin_rgb / peak                                        # hue + saturation at full value
    grey = chroma.mean()
    chroma = np.clip(grey + (chroma - grey) * level.saturation, 0, 1)
    value = max(level.floor, peak ** level.gamma) * brightness
    srgb = (chroma * value) ** (1 / 2.2)
    return tuple(float(c) for c in np.clip(srgb, 0, 1))
