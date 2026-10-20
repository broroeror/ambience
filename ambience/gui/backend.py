"""The QML-facing backend: turns HomeState into plain lists the screens bind to, and turns
user actions into rate-limited bridge commands.

Every write is ALSO applied to the local state at once ("optimistic"), so tiles, glows and
sliders respond instantly; the bridge's own event confirms it a moment later.
"""
from __future__ import annotations

import colorsys

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, QObject, Qt, QTimer, Signal,
                            Slot)

from ..bridge import store
from ..bridge.client import Bridge, BridgeError
from ..bridge.state import CommandQueue, HomeState
from ..colour import light_hex, palette_hexes, rgb_to_xy

QUICK_WHITES = [  # (label, mirek): the classic four, as plain colour temperatures
    ("Relax", 447), ("Read", 346), ("Concentrate", 233), ("Energize", 156),
]


# Hue "archetypes" are product-shape ids; "sultan_bulb" is just an ordinary bulb.
ARCHETYPES = {"sultan_bulb": "Bulb", "classic_bulb": "Bulb", "candle_bulb": "Candle bulb",
              "spot_bulb": "Spot", "hue_lightstrip": "Lightstrip", "hue_play": "Play bar",
              "hue_go": "Go", "hue_bloom": "Bloom", "hue_iris": "Iris", "table_shade": "Table lamp",
              "floor_shade": "Floor lamp", "pendant_round": "Pendant", "ceiling_round": "Ceiling light"}


def _archetype(a: str) -> str:
    return ARCHETYPES.get(a, a.replace("_", " ").capitalize() if a else "Light")


def _name(r: dict) -> str:
    return (r.get("metadata") or {}).get("name", "?")


class ItemModel(QAbstractListModel):
    """A list of dicts keyed by "id", exposed to QML as one role, `item`. Updating with
    the same ids changes rows IN PLACE (dataChanged), so delegates — and a slider being
    dragged inside one — survive every live update; only a different set of ids resets."""

    ItemRole = Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if role == self.ItemRole and 0 <= index.row() < len(self._items):
            return self._items[index.row()]
        return None

    def roleNames(self):
        return {self.ItemRole: b"item"}

    def set(self, items: list[dict]) -> None:
        if [i["id"] for i in items] == [i["id"] for i in self._items]:
            for row, new in enumerate(items):
                if self._items[row] != new:
                    self._items[row] = new
                    ix = self.index(row)
                    self.dataChanged.emit(ix, ix, [self.ItemRole])
        else:
            self.beginResetModel()
            self._items = list(items)
            self.endResetModel()


class Backend(QObject):
    changed = Signal()
    _stateBumped = Signal()      # emitted on the event thread; queued onto the GUI thread

    def __init__(self):
        super().__init__()
        self._error = ""
        self._room_id = ""
        self._light_id = ""
        self.state: HomeState | None = None
        self.cmd: CommandQueue | None = None
        self._label = ""
        self._rooms, self._lights, self._scenes = ItemModel(self), ItemModel(self), ItemModel(self)
        self._debounce = QTimer(self, singleShot=True, interval=40)  # batch event bursts
        self._debounce.timeout.connect(self._refresh)
        self._stateBumped.connect(self._debounce.start)

        got = store.load()
        if not got:
            return
        pairing, app_key, _client_key = got
        bridge = Bridge(pairing.host, pairing.cert_sha256, app_key)
        self._label = f"{pairing.host}"
        self.state = HomeState(bridge)
        self.cmd = CommandQueue(bridge, on_error=self._set_error_from_thread)
        try:
            self.state.load()
        except (OSError, BridgeError) as e:
            self._error = str(e)
        self.state.subscribe(lambda _ids: self._stateBumped.emit())
        self.state.start()
        self._refresh()

    def _refresh(self):
        if self.state:
            self._rooms.set(self._room_list())
            self._lights.set(self._light_list())
            self._scenes.set(self._scene_list())
        self.changed.emit()

    @Property(QObject, constant=True)
    def roomsModel(self):
        return self._rooms

    @Property(QObject, constant=True)
    def lightsModel(self):
        return self._lights

    @Property(QObject, constant=True)
    def scenesModel(self):
        return self._scenes

    # --- status -----------------------------------------------------------------
    @Property(bool, notify=changed)
    def paired(self):
        return self.state is not None

    @Property(bool, notify=changed)
    def connected(self):
        return bool(self.state and self.state.connected)

    @Property(str, notify=changed)
    def bridgeLabel(self):
        return self._label

    @Property(str, notify=changed)
    def error(self):
        return self._error

    @Property(str, notify=changed)
    def roomId(self):
        return self._room_id

    def _set_error_from_thread(self, msg: str):
        self._error = msg
        self._stateBumped.emit()

    # --- home ---------------------------------------------------------------------
    def _group_entry(self, g: dict) -> dict:
        lights = self.state.lights_in(g)
        on = [l for l in lights if l.get("on", {}).get("on")]
        gl = self.state.grouped_light_of(g) or {}
        bri = round(sum(l.get("dimming", {}).get("brightness", 0) for l in on) / len(on)) if on else 0
        active = next((s for s in self.state.scenes_for(g["id"])
                       if (s.get("status") or {}).get("active") not in (None, "inactive")), None)
        kind = "Zone" if g["type"] == "zone" else "Room"
        what = _name(active) if active else ("custom colours" if on else "off")
        return {
            "id": g["id"], "name": _name(g), "kind": kind, "groupedId": gl.get("id", ""),
            "on": bool(gl.get("on", {}).get("on")) if gl else bool(on), "bri": bri,
            "count": len(lights), "onCount": len(on),
            "meta": (f"Zone · {len(lights)} lights" if kind == "Zone" else f"{len(lights)} lights") + f" · {what}",
            "glow": self._room_glow(lights),
        }

    @staticmethod
    def _room_glow(lights: list[dict]) -> list[str]:
        """One glow spot per light, in a FIXED order (by name), so a colour change fades
        spot-to-spot instead of spots appearing and vanishing. A room in one uniform
        colour collapses to a single centred glow."""
        hexes = [light_hex(l) for l in sorted(lights, key=_name)][:5] or ["#2a2e37"]
        rgb = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in hexes]
        uniform = all(max(abs(a - b) for a, b in zip(c, rgb[0])) < 24 for c in rgb)
        return hexes[:1] if uniform else hexes

    def _room_list(self):
        if not self.state:
            return []
        rooms = sorted(self.state.of("room"), key=_name) + sorted(self.state.of("zone"), key=_name)
        return [self._group_entry(g) for g in rooms]

    @Property(str, notify=changed)
    def summary(self):
        if not self.state:
            return ""
        lights = self.state.of("light")
        on = sum(1 for l in lights if l.get("on", {}).get("on"))
        return f"{on} of {len(lights)} lights on · {len(self.state.of('room'))} rooms · {len(self.state.of('zone'))} zones"

    # --- the open room --------------------------------------------------------------
    @Slot(str)
    def openRoom(self, rid: str):
        self._room_id = rid
        lights = self.state.lights_in(self.state.get(rid) or {}) if self.state else []
        self._light_id = lights[0]["id"] if lights else ""
        self._refresh()

    @Property("QVariantMap", notify=changed)
    def room(self):
        g = self.state.get(self._room_id) if self.state else None
        return self._group_entry(g) if g else {}

    def _light_entry(self, l: dict) -> dict:
        ct = l.get("color_temperature") or {}
        is_white = bool(ct.get("mirek_valid") and ct.get("mirek"))
        return {
            "id": l["id"], "name": _name(l), "on": bool(l.get("on", {}).get("on")),
            "bri": round(l.get("dimming", {}).get("brightness", 0)), "hex": light_hex(l),
            "hasColor": "color" in l, "mode": "white" if is_white else "colour",
            "mirek": ct.get("mirek") or 366, "selected": l["id"] == self._light_id,
            "kind": _archetype((l.get("metadata") or {}).get("archetype", "")),
        }

    def _light_list(self):
        g = self.state.get(self._room_id) if self.state else None
        if not g:
            return []
        return [self._light_entry(l) for l in sorted(self.state.lights_in(g), key=_name)]

    @Slot(str)
    def selectLight(self, lid: str):
        self._light_id = lid
        self._refresh()

    @Property("QVariantMap", notify=changed)
    def light(self):
        l = self.state.get(self._light_id) if self.state else None
        return self._light_entry(l) if l else {}

    def _scene_list(self):
        if not self.state or not self._room_id:
            return []
        out = []
        for s in self.state.scenes_for(self._room_id):
            pal = palette_hexes(s)
            out.append({"id": s["id"], "name": _name(s), "glow": pal or ["#ffb547"],
                        "dynamic": len(pal) > 1,
                        "active": (s.get("status") or {}).get("active") not in (None, "inactive")})
        return out

    @Property("QVariantList", constant=True)
    def quickWhites(self):
        return [{"label": n, "mirek": m} for n, m in QUICK_WHITES]

    # --- actions (optimistic local update + rate-limited PUT) -------------------------
    def _send(self, rtype: str, rid: str, body: dict, local: dict | None = None):
        """PUT `body` to the bridge; apply `body` + `local` (read-only fields the bridge
        would reject, like mirek_valid) to our own copy straight away."""
        if not (self.state and rid):
            return
        self._error = ""
        mirror = {"id": rid, "type": rtype, **body}
        for k, v in (local or {}).items():
            mirror[k] = {**mirror.get(k, {}), **v} if isinstance(v, dict) else v
        self.state.apply([{"type": "update", "data": [mirror]}])
        self.cmd.put(rtype, rid, body)

    @Slot(str, bool)
    def setGroupOn(self, grouped_id: str, on: bool):
        self._send("grouped_light", grouped_id, {"on": {"on": on}})
        g = self.state.get(grouped_id) or {}
        owner = (g.get("owner") or {}).get("rid")
        group = self.state.get(owner) if owner else None
        if group:  # mirror onto member lights so tiles + glows follow immediately
            for l in self.state.lights_in(group):
                self.state.apply([{"type": "update", "data": [{"id": l["id"], "type": "light", "on": {"on": on}}]}])

    @Slot(str, float)
    def setGroupBrightness(self, grouped_id: str, bri: float):
        self._send("grouped_light", grouped_id, {"dimming": {"brightness": max(1.0, min(100.0, bri))}})

    @Slot(bool)
    def setAllOn(self, on: bool):
        for g in self.state.of("room") if self.state else []:
            gl = self.state.grouped_light_of(g)
            if gl:
                self.setGroupOn(gl["id"], on)

    @Slot(str, bool)
    def setLightOn(self, lid: str, on: bool):
        self._send("light", lid, {"on": {"on": on}})

    @Slot(str, float)
    def setLightBrightness(self, lid: str, bri: float):
        self._send("light", lid, {"on": {"on": True}, "dimming": {"brightness": max(1.0, min(100.0, bri))}})

    @Slot(str, float, float)
    def setLightHueSat(self, lid: str, hue: float, sat: float):
        """From the colour wheel: hue 0..1 (angle), saturation 0..1 (distance from centre)."""
        r, g, b = colorsys.hsv_to_rgb(hue % 1.0, max(0.0, min(1.0, sat)), 1.0)
        x, y = rgb_to_xy(r, g, b)
        self._send("light", lid, {"on": {"on": True}, "color": {"xy": {"x": x, "y": y}}},
                   local={"color_temperature": {"mirek_valid": False}})

    @Slot(str, int)
    def setLightMirek(self, lid: str, mirek: int):
        self._send("light", lid, {"on": {"on": True}, "color_temperature": {"mirek": max(153, min(500, int(mirek)))}},
                   local={"color_temperature": {"mirek_valid": True}})

    @Slot(str)
    def recallScene(self, sid: str):
        """Recall a scene — and show its target state at once. A scene stores exactly what
        each light becomes, so the app needn't wait ~1 s for the bridge's events (which
        arrive after the lamps have already changed)."""
        if not self.state:
            return
        scene = self.state.get(sid) or {}
        group = scene.get("group", {}).get("rid")
        updates = []
        for a in scene.get("actions", []):
            target, act = a.get("target", {}), a.get("action", {})
            if target.get("rtype") != "light":
                continue
            u = {"id": target["rid"], "type": "light", "on": act.get("on", {"on": True})}
            if "dimming" in act:
                u["dimming"] = act["dimming"]
            if act.get("color", {}).get("xy"):
                u["color"] = {"xy": act["color"]["xy"]}
                u["color_temperature"] = {"mirek_valid": False}
            elif act.get("color_temperature", {}).get("mirek"):
                u["color_temperature"] = {"mirek": act["color_temperature"]["mirek"], "mirek_valid": True}
            updates.append(u)
        for s in self.state.scenes_for(group) if group else []:   # this one becomes the active scene
            updates.append({"id": s["id"], "type": "scene",
                            "status": {"active": "static" if s["id"] == sid else "inactive"}})
        if updates:
            self.state.apply([{"type": "update", "data": updates}])
        self.cmd.put("scene", sid, {"recall": {"action": "active"}})
