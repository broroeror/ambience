"""HueStream v2 message encoding (the payload sent over DTLS to an entertainment area).

Layout (Entertainment API v2):
    "HueStream"            9 bytes  protocol name
    0x02 0x00              2        version 2.0
    sequence               1        (ignored by the bridge; we increment it)
    0x00 0x00              2        reserved
    color space            1        0x00 = RGB, 0x01 = XY + brightness
    0x00                   1        reserved
    entertainment area id  36       the configuration's UUID, ASCII
    then per channel (max 20):
    channel id             1
    R G B (or X Y Bri)     3 × uint16 big-endian
"""
from __future__ import annotations

import struct

MAX_CHANNELS = 20
_HEADER = b"HueStream" + bytes([0x02, 0x00])


def encode_rgb(area_id: str, sequence: int, channels: dict[int, tuple[float, float, float]]) -> bytes:
    """channels: {channel_id: (r, g, b)} with components in 0..1 (clamped)."""
    if len(area_id) != 36:
        raise ValueError("entertainment area id must be a 36-char UUID")
    if len(channels) > MAX_CHANNELS:
        raise ValueError(f"at most {MAX_CHANNELS} channels per message")
    out = bytearray(_HEADER)
    out += bytes([sequence & 0xFF, 0x00, 0x00, 0x00, 0x00])  # seq, reserved×2, RGB, reserved
    out += area_id.encode("ascii")
    for cid, (r, g, b) in channels.items():
        out += struct.pack(">BHHH", cid, _u16(r), _u16(g), _u16(b))
    return bytes(out)


def _u16(v: float) -> int:
    return int(round(min(1.0, max(0.0, v)) * 0xFFFF))
