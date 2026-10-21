# Ambience

**Unofficial** Linux desktop app for Philips Hue: rooms and lights, scenes (including
dynamic ones) with a preset gallery, and **entertainment-area sync** — your lights
follow your screen or your music, like Hue Sync does on Windows and macOS.

> Not affiliated with or endorsed by Signify / Philips Hue. "Ambience" is a working name.
> Status: early development — lights, rooms, scenes, screen and music sync work; a Settings page is next.

## Requirements

- A Hue Bridge (v2 square bridge or Bridge Pro) on your network.
- Python 3, `python-keyring` (keys are stored in KWallet / GNOME Keyring),
  `python-cryptography`, OpenSSL 3 (entertainment streaming uses DTLS-PSK via libssl).

## Installing (Arch)

```fish
cd packaging; makepkg -si    # builds from the committed state of this repo
```

Then open **Ambience** from the app menu (or run `ambience`; `ambience --hidden` starts in the
tray). The first run walks you through pairing. `ambience-cli` has the command-line tools below.

## Running from the source tree

```fish
python -m ambience.gui       # the app (pairs on first run)
```

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
- `ambience/bridge/state.py` — a live mirror of the bridge kept current by the CLIP v2
  event stream, and a command queue that coalesces bursts (a dragged slider sends only its
  latest value) and paces writes to the bridge's limits (~10/s lights, ~1/s rooms).
- `ambience/gui/` — the PySide6/QML app. Fonts: Manrope (SIL Open Font License, see
  `gui/fonts/OFL.txt`).

## Licence

MIT — see [LICENSE](LICENSE). The bundled Manrope fonts are under the SIL Open Font Licence
(`ambience/gui/fonts/OFL.txt`).
