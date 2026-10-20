"""Colour conversions between the bridge (CIE xy + brightness, or mirek for whites) and
the screen (sRGB). Display conversions favour a faithful *look* (hue and saturation),
not photometric accuracy: a lamp at 30 % still shows as its colour, just dimmer."""
from __future__ import annotations

import math


def _gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def xy_to_rgb(x: float, y: float, brightness: float = 100.0) -> tuple[float, float, float]:
    """CIE xy (+ brightness 0..100) → sRGB 0..1, normalised to full saturation then
    dimmed gently, so dim lamps keep their hue on screen."""
    if y <= 0:
        return 0.0, 0.0, 0.0
    X, Y, Z = x / y, 1.0, (1 - x - y) / y
    r = X * 3.2406 - Y * 1.5372 - Z * 0.4986
    g = -X * 0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 - Y * 0.2040 + Z * 1.0570
    m = max(r, g, b, 1e-9)
    scale = max(0.25, brightness / 100) ** 0.5
    return tuple(min(1.0, _gamma(max(0.0, c / m)) * scale) for c in (r, g, b))


def mirek_to_rgb(mirek: float, brightness: float = 100.0) -> tuple[float, float, float]:
    """Colour temperature in mirek (153 cool … 500 warm) → sRGB 0..1."""
    t = 1e6 / max(mirek, 1) / 100
    r = 1.0 if t <= 66 else 329.7 * (t - 60) ** -0.1332 / 255
    g = (99.47 * math.log(t) - 161.1) / 255 if t <= 66 else 288.1 * (t - 60) ** -0.0755 / 255
    b = 1.0 if t >= 66 else (0.0 if t <= 19 else (138.5 * math.log(t - 10) - 305.0) / 255)
    scale = max(0.25, brightness / 100) ** 0.5
    return tuple(max(0.0, min(1.0, c)) * scale for c in (r, g, b))


def rgb_to_xy(r: float, g: float, b: float) -> tuple[float, float]:
    """sRGB 0..1 → CIE xy (what a colour PUT sends). The bridge clamps to each lamp's gamut."""
    R, G, B = _linear(r), _linear(g), _linear(b)
    X = R * 0.4124 + G * 0.3576 + B * 0.1805
    Y = R * 0.2126 + G * 0.7152 + B * 0.0722
    Z = R * 0.0193 + G * 0.1192 + B * 0.9505
    s = X + Y + Z
    return (0.3127, 0.3290) if s <= 0 else (round(X / s, 4), round(Y / s, 4))


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#%02x%02x%02x" % tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb)


def light_hex(light: dict) -> str:
    """The on-screen colour for a CLIP v2 light resource (off lamps → dark grey)."""
    if not light.get("on", {}).get("on"):
        return "#2a2e37"
    bri = light.get("dimming", {}).get("brightness", 100.0)
    ct = light.get("color_temperature") or {}
    if ct.get("mirek_valid") and ct.get("mirek"):
        return to_hex(mirek_to_rgb(ct["mirek"], bri))
    xy = (light.get("color") or {}).get("xy")
    if xy:
        return to_hex(xy_to_rgb(xy["x"], xy["y"], bri))
    return to_hex((bri / 100,) * 3)


def palette_hexes(scene: dict, limit: int = 5) -> list[str]:
    """Display colours for a scene: its palette, else the colours of its per-light actions."""
    pal = scene.get("palette") or {}
    out = [to_hex(xy_to_rgb(c["color"]["xy"]["x"], c["color"]["xy"]["y"])) for c in pal.get("color", [])]
    out += [to_hex(mirek_to_rgb(c["color_temperature"]["mirek"])) for c in pal.get("color_temperature", [])]
    if not out:
        for a in scene.get("actions", []):
            act = a.get("action", {})
            if act.get("color", {}).get("xy"):
                xy = act["color"]["xy"]
                out.append(to_hex(xy_to_rgb(xy["x"], xy["y"])))
            elif act.get("color_temperature", {}).get("mirek"):
                out.append(to_hex(mirek_to_rgb(act["color_temperature"]["mirek"])))
    seen = []
    for h in out:
        if h not in seen:
            seen.append(h)
    return seen[:limit]
