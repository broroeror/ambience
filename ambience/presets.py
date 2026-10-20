"""The Ambience gallery: original presets (our own names and palettes — Philips' gallery
lives inside their phone app and isn't ours to copy). "Add to room" turns one into a real
scene on the bridge, so the phone app sees it too."""
from __future__ import annotations

from dataclasses import dataclass

from .colour import rgb_to_xy


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    mood: str
    colours: tuple[str, ...]
    brightness: float = 70.0
    speed: float = 0.6       # dynamic-mode speed the scene is created with (0..1)


PRESETS = (
    Preset("harbour-dusk", "Harbour Dusk", "Blue hour over warm windows",
           ("#1b3a6b", "#2f6fa8", "#e07a3f", "#f2b05e", "#ffd9a0")),
    Preset("moss-ember", "Moss & Ember", "Forest floor, low fire",
           ("#2e5d34", "#6b8f3a", "#c8a24a", "#d9632b", "#8a2a1f"), brightness=60),
    Preset("paper-lantern", "Paper Lantern", "Soft, warm, unhurried",
           ("#ffcf8a", "#ffb067", "#ff8f4f", "#f2643a", "#c94a3a"), brightness=55, speed=0.4),
    Preset("deep-pool", "Deep Pool", "Cool and still",
           ("#003b5c", "#00689b", "#009fc2", "#2ad1d6", "#7ff0e0"), speed=0.45),
    Preset("citrus-noon", "Citrus Noon", "Bright and awake",
           ("#fff3a0", "#ffd84a", "#ffb72e", "#b8e05a", "#6fcf5c"), brightness=90),
    Preset("northern-static", "Northern Static", "Aurora on a cold night",
           ("#0b1f4d", "#1c5fa8", "#2fd1a0", "#9ef06a", "#c25fe8"), speed=0.7),
    Preset("velvet-hour", "Velvet Hour", "Late, deep, a little dramatic",
           ("#3a0d4f", "#6b1d7a", "#b02e86", "#e2507a", "#ff8a6b"), brightness=50),
    Preset("quiet-study", "Quiet Study", "Two calm whites for reading",
           ("#ffe2b8", "#fff1dc"), brightness=85, speed=0.3),
)
BY_ID = {p.id: p for p in PRESETS}


def _xy(hex_: str) -> dict:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    x, y = rgb_to_xy(r, g, b)
    return {"x": x, "y": y}


def scene_body(preset: Preset, group: dict, lights: list[dict]) -> dict:
    """CLIP v2 POST body for a scene in `group` (room or zone): the palette for dynamic
    mode, and a static look that hands the colours out round-robin across the lights."""
    ordered = sorted(lights, key=lambda l: (l.get("metadata") or {}).get("name", ""))
    actions = []
    for i, light in enumerate(ordered):
        act = {"on": {"on": True}, "dimming": {"brightness": preset.brightness}}
        if "color" in light:
            act["color"] = {"xy": _xy(preset.colours[i % len(preset.colours)])}
        actions.append({"target": {"rid": light["id"], "rtype": "light"}, "action": act})
    return {
        "type": "scene",
        "metadata": {"name": preset.name},
        "group": {"rid": group["id"], "rtype": group["type"]},
        "actions": actions,
        "palette": {
            "color": [{"color": {"xy": _xy(c)}, "dimming": {"brightness": preset.brightness}}
                      for c in preset.colours],
            "dimming": [], "color_temperature": [], "effects": [],
        },
        "speed": preset.speed,
    }
