"""Put the lights back the way they were before sync.

Ending an entertainment session (action=stop) only RELEASES the lights — they keep the
last streamed colour (confirmed on the user's bridge via the sync log). So before
streaming we snapshot the area's lights, and afterwards restore them:

1. If a scene covering those lights was active (and the lights were on — recalling would
   switch them on), re-recall it — static or dynamic — which restores effects (candle,
   fire, …) and dynamic animation exactly. If several apply (a room and a zone), the most
   recently recalled wins.
2. Every light the scene doesn't cover is restored one by one: on/off, brightness, colour
   or white temperature, effect, with a short fade.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

FADE_MS = 400


@dataclass
class Snapshot:
    scene_id: str = ""
    scene_action: str = ""                      # "active" (static) or "dynamic_palette"
    scene_lights: set[str] = field(default_factory=set)     # lights that scene sets
    lights: dict[str, dict] = field(default_factory=dict)   # light id → PUT body to restore


def _light_body(l: dict) -> dict:
    if not l.get("on", {}).get("on"):
        return {"on": {"on": False}}
    body: dict = {"on": {"on": True}, "dynamics": {"duration": FADE_MS}}
    bri = (l.get("dimming") or {}).get("brightness")
    if bri is not None:
        body["dimming"] = {"brightness": bri}
    ct = l.get("color_temperature") or {}
    if ct.get("mirek_valid") and ct.get("mirek"):
        body["color_temperature"] = {"mirek": ct["mirek"]}
    elif (l.get("color") or {}).get("xy"):
        body["color"] = {"xy": l["color"]["xy"]}
    eff = (l.get("effects") or {}).get("status")
    if eff and eff != "no_effect":
        body["effects"] = {"effect": eff}
    return body


def snapshot(bridge, area: dict) -> Snapshot:
    """Capture the area's lights (and the scene they were showing, if any)."""
    light_ids = [s["rid"] for s in area.get("light_services", []) if s.get("rtype") == "light"]
    snap = Snapshot()
    lights = {l["id"]: l for l in bridge.get("light")}
    for lid in light_ids:
        if lid in lights:
            snap.lights[lid] = _light_body(lights[lid])

    # Which rooms/zones contain these lights, and was one of their scenes playing?
    owner = {l["owner"]["rid"]: l["id"] for l in lights.values()}            # device → light
    groups = set()
    for g in bridge.get("room") + bridge.get("zone"):
        members = {owner.get(c["rid"]) if c["rtype"] == "device" else c["rid"] for c in g.get("children", [])}
        if members & set(light_ids):
            groups.add(g["id"])
    best = None
    for s in bridge.get("scene"):
        st = s.get("status") or {}
        if s.get("group", {}).get("rid") in groups and st.get("active") not in (None, "inactive"):
            if best is None or st.get("last_recall", "") > (best.get("status") or {}).get("last_recall", ""):
                best = s
    any_on = any(b["on"]["on"] for b in snap.lights.values())
    if best is not None and any_on:
        snap.scene_lights = {a["target"]["rid"] for a in best.get("actions", [])}
        snap.scene_id = best["id"]
        snap.scene_action = "dynamic_palette" if best["status"]["active"] == "dynamic_palette" else "active"
    return snap


def restore(bridge, snap: Snapshot, log=lambda m: None) -> None:
    if snap.scene_id:
        bridge.put("scene", snap.scene_id, {"recall": {"action": snap.scene_action}})
        log(f"restored: re-recalled the scene that was playing ({snap.scene_action})")
    rest = {lid: body for lid, body in snap.lights.items() if lid not in snap.scene_lights}
    for lid, body in rest.items():
        time.sleep(0.1)                         # the bridge's ~10 commands/s guidance
        bridge.put("light", lid, body)
    if rest:
        log(f"restored {len(rest)} lights one by one")
