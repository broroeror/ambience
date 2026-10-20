"""Milestone-1 command line: python -m ambience {discover,pair,show,test-pattern}."""
from __future__ import annotations

import argparse
import hashlib
import math
import socket
import sys
import time

from . import __version__
from .bridge import store
from .bridge.client import (Bridge, BridgeError, LinkButtonNotPressed, certificate_common_name,
                            discover, fetch_certificate)


def _paired() -> tuple[Bridge, store.Pairing, str]:
    got = store.load()
    if not got:
        sys.exit("Not paired yet — run: python -m ambience pair")
    p, app_key, client_key = got
    return Bridge(p.host, p.cert_sha256, app_key), p, client_key


def cmd_discover(_a):
    for f in discover() or []:
        print(f"{f.bridge_id}  {f.host}  {f.model}")


def cmd_pair(a):
    bridges = discover()
    if a.host:
        bridges = [b for b in bridges if b.host == a.host] or [type("F", (), {"bridge_id": "", "host": a.host, "model": ""})()]
    if not bridges:
        sys.exit("No bridge found on the network. Pass --host <ip>.")
    b = bridges[0]
    der = fetch_certificate(b.host)
    cn = certificate_common_name(der).lower()
    if b.bridge_id and cn != b.bridge_id:
        sys.exit(f"Refusing to pair: certificate CN {cn!r} doesn't match bridge id {b.bridge_id!r}.")
    pin = hashlib.sha256(der).hexdigest()
    bridge = Bridge(b.host, pin)
    print(f"Bridge {cn} at {b.host}. Press the round link button on top of the bridge now "
          f"(waiting up to {a.wait} s)…", flush=True)
    deadline = time.monotonic() + a.wait
    while True:
        try:
            app_key, client_key = bridge.pair(f"ambience#{socket.gethostname()}")
            break
        except LinkButtonNotPressed:
            if time.monotonic() > deadline:
                sys.exit("Timed out waiting for the link button. Run pair again.")
            time.sleep(1.5)
    store.save(store.Pairing(cn, b.host, pin, getattr(b, "model", "")), app_key, client_key)
    print("Paired. Keys stored in your keyring; bridge details in", store.BRIDGE_FILE)


def _name(r):
    return (r.get("metadata") or {}).get("name", "?")


def cmd_show(_a):
    br, p, _ = _paired()
    lights = {l["id"]: l for l in br.get("light")}
    devices = {d["id"]: d for d in br.get("device")}
    light_of_device = {s["rid"]: l for l in lights.values() for s in [l.get("owner", {})]}
    print(f"Bridge {p.bridge_id} @ {p.host}\n")
    for kind in ("room", "zone"):
        for g in sorted(br.get(kind), key=_name):
            members = []
            for c in g.get("children", []):
                l = light_of_device.get(c["rid"]) if c["rtype"] == "device" else lights.get(c["rid"])
                if l:
                    on = "on " if l.get("on", {}).get("on") else "off"
                    gamut = "colour" if "color" in l else "white"
                    members.append(f"{_name(l)} [{on}, {gamut}]")
            print(f"{kind.title()}: {_name(g)} — {len(members)} light(s)")
            for m in members:
                print(f"    {m}")
    scenes = br.get("scene")
    groups = {g["id"]: _name(g) for k in ("room", "zone") for g in br.get(k)}
    print(f"\nScenes ({len(scenes)}):")
    for s in sorted(scenes, key=lambda s: (groups.get(s["group"]["rid"], ""), _name(s))):
        pal = s.get("palette") or {}
        n_pal = len(pal.get("color", [])) + len(pal.get("color_temperature", []))
        dyn = " dynamic-capable" if n_pal else ""
        print(f"    {groups.get(s['group']['rid'], '?'):18} {_name(s)}{dyn}")
    print("\nEntertainment areas:")
    for e in br.get("entertainment_configuration"):
        chans = e.get("channels", [])
        print(f"    {_name(e)}  id={e['id']}  status={e.get('status')}  type={e.get('configuration_type')}  "
              f"channels={len(chans)}")
        for ch in chans:
            pos = ch.get("position", {})
            print(f"        ch {ch['channel_id']:2}  x={pos.get('x', 0):+.2f} y={pos.get('y', 0):+.2f} z={pos.get('z', 0):+.2f}")


def cmd_test_pattern(a):
    from .stream.dtls import DtlsPskClient
    from .stream.huestream import encode_rgb
    br, p, client_key = _paired()
    areas = br.get("entertainment_configuration")
    area = next((e for e in areas if a.area in (e["id"], _name(e))), None) if a.area else (areas[0] if areas else None)
    if not area:
        sys.exit("No entertainment area found. Create one in the Hue app (Settings → Entertainment areas).")
    chans = [c["channel_id"] for c in area.get("channels", [])]
    print(f"Streaming a {a.seconds:g} s rainbow to '{_name(area)}' ({len(chans)} channels)…", flush=True)
    br.set_entertainment(area["id"], True)
    try:
        with DtlsPskClient(p.host, 2100, identity=br.app_key.encode(), psk=bytes.fromhex(client_key)) as c:
            seq, t0 = 0, time.monotonic()
            while (t := time.monotonic() - t0) < a.seconds:
                frame = {}
                for i, ch in enumerate(chans):  # a hue wheel sweeping across the channels
                    h = (t / 4 + i / max(1, len(chans))) % 1.0
                    frame[ch] = tuple(0.5 + 0.5 * math.cos(2 * math.pi * (h - k / 3)) for k in range(3))
                c.send(encode_rgb(area["id"], seq, frame))
                seq += 1
                time.sleep(1 / 50)
            print(f"Sent {seq} frames ({seq / a.seconds:.0f}/s).")
    finally:
        br.set_entertainment(area["id"], False)  # always hand the lights back
        print("Entertainment area released.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ambience", description=f"Ambience {__version__} — milestone-1 tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover", help="list bridges on the network").set_defaults(fn=cmd_discover)
    sp = sub.add_parser("pair", help="pair with a bridge (press its link button)")
    sp.add_argument("--host")
    sp.add_argument("--wait", type=int, default=60)
    sp.set_defaults(fn=cmd_pair)
    sub.add_parser("show", help="rooms, lights, scenes, entertainment areas").set_defaults(fn=cmd_show)
    st = sub.add_parser("test-pattern", help="stream a rainbow to an entertainment area")
    st.add_argument("--area", help="name or id (default: the first one)")
    st.add_argument("--seconds", type=float, default=10)
    st.set_defaults(fn=cmd_test_pattern)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except BridgeError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
