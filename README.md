# Ambience

**Unofficial** Linux desktop app for Philips Hue: rooms and lights, scenes (including
dynamic ones) with a preset gallery, and **entertainment-area sync** — your lights
follow your screen or your music, like Hue Sync does on Windows and macOS.

> Not affiliated with or endorsed by Signify / Philips Hue. "Ambience" is a working name.
> Status: early development (milestone 1: pairing + streaming proof of concept).

## Requirements

- A Hue Bridge (v2 square bridge or Bridge Pro) on your network.
- Python 3, `python-keyring` (keys are stored in KWallet / GNOME Keyring),
  `python-cryptography`, OpenSSL 3 (entertainment streaming uses DTLS-PSK via libssl).

## Milestone-1 tools

```fish
python -m ambience discover       # find bridges on the network
python -m ambience pair           # then press the round button on the bridge
python -m ambience show           # rooms, lights, scenes, entertainment areas
python -m ambience test-pattern   # 10 s rainbow on your first entertainment area
```

## How it fits together

- `ambience/bridge/` — discovery (mDNS, then Signify's lookup), pairing, the CLIP v2 API.
  The bridge's certificate is **pinned at pairing** (it's signed by Signify's private CA
  and we connect by IP), and the keys live in your keyring, never in a plain file.
- `ambience/stream/` — the Entertainment API: HueStream v2 messages over a DTLS 1.2 PSK
  connection to the bridge (port 2100), driven through the system's OpenSSL 3.
