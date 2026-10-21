"""The QML-facing backend: turns HomeState into plain lists the screens bind to, and turns
user actions into rate-limited bridge commands.

Every write is ALSO applied to the local state at once ("optimistic"), so tiles, glows and
sliders respond instantly; the bridge's own event confirms it a moment later.
"""
from __future__ import annotations

import colorsys
import os
import threading
from pathlib import Path

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, QObject, Qt, QTimer, QUrl,
                            Signal, Slot)
from PySide6.QtGui import QImage

from ..bridge import store
from ..bridge.client import Bridge, BridgeError
from ..bridge.state import CommandQueue, HomeState
from ..colour import light_hex, palette_hexes, rgb_to_xy, scene_effect, scene_look
from ..presets import BY_ID as PRESETS_BY_ID, PRESETS, scene_body

# Your own scene photos live on this computer (the bridge can't store images), so the
# phone app won't show them.
PHOTO_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ambience" / "scene-photos"

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
    _noticeFromThread = Signal(str)

    def __init__(self):
        super().__init__()
        self._error = ""
        self._room_id = ""
        self._light_id = ""
        self.state: HomeState | None = None
        self.cmd: CommandQueue | None = None
        self._label = ""
        self._rooms, self._lights, self._scenes = ItemModel(self), ItemModel(self), ItemModel(self)
        self._scene_groups, self._gallery = ItemModel(self), ItemModel(self)
        self._group_scenes: dict[str, ItemModel] = {}   # one model per room/zone: a change in
        self._scene_id = ""                             # one strip never resets the others
        self._notice = ""
        self._noticeFromThread.connect(self._set_notice)
        self._noticeTimer = QTimer(self, singleShot=True, interval=4000)
        self._noticeTimer.timeout.connect(lambda: self._set_notice(""))
        self.bridge: Bridge | None = None
        from .sync_controller import SyncController, SyncFrameProvider
        self.sync_provider = SyncFrameProvider()
        self._sync = SyncController(self, self.sync_provider)
        self._debounce = QTimer(self, singleShot=True, interval=40)  # batch event bursts
        self._debounce.timeout.connect(self._refresh)
        self._stateBumped.connect(self._debounce.start)

        from .settings import Settings
        self._settings = Settings(self)

        from .pairing import PairingController
        self._pairing = PairingController(self)
        self._pairing.paired.connect(self._on_paired)
        # AMBIENCE_PAIR=1 opens the pairing screen even when already paired (re-pair / try it)
        self._pairing_open = bool(os.environ.get("AMBIENCE_PAIR"))
        self._attach()

    def _attach(self):
        """(Re)connect to the paired bridge: live state, event stream, command queue."""
        got = store.load()
        if not got:
            return
        if self.state:
            self.state.stop()
        pairing, app_key, _client_key = got
        bridge = Bridge(pairing.host, pairing.cert_sha256, app_key)
        self.bridge = bridge
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

    def _on_paired(self):
        self._pairing_open = False
        self._attach()
        self.changed.emit()

    @Property(QObject, constant=True)
    def pairing(self):
        return self._pairing

    @Property(bool, notify=changed)
    def pairingOpen(self):
        """Show the pairing screen: never paired, or asked for (re-pair)."""
        return self._pairing_open or self.state is None

    @Slot()
    def openPairing(self):
        self._pairing_open = True
        self.changed.emit()

    @Slot()
    def closePairing(self):
        if self.state is not None:
            self._pairing.cancel()
            self._pairing_open = False
            self.changed.emit()

    def _refresh(self):
        if self.state:
            self._rooms.set(self._room_list())
            self._lights.set(self._light_list())
            self._scenes.set(self._scene_list())
            groups = self._groups()
            self._scene_groups.set([{"id": g["id"], "name": _name(g), "kind": "Zone" if g["type"] == "zone" else "Room",
                                     "count": len(self.state.scenes_for(g["id"]))} for g in groups])
            for g in groups:
                self.sceneModelFor(g["id"]).set([self._scene_entry(x) for x in self.state.scenes_for(g["id"])])
            self._gallery.set([{"id": p.id, "name": p.name, "mood": p.mood, "glow": list(p.colours)} for p in PRESETS])
        self.changed.emit()

    def _groups(self):
        return sorted(self.state.of("room"), key=_name) + sorted(self.state.of("zone"), key=_name)

    @Slot(str, result=QObject)
    def sceneModelFor(self, group_id: str):
        if group_id not in self._group_scenes:
            self._group_scenes[group_id] = ItemModel(self)
        return self._group_scenes[group_id]

    @Property(QObject, constant=True)
    def sceneGroupsModel(self):
        return self._scene_groups

    @Property(QObject, constant=True)
    def galleryModel(self):
        return self._gallery

    @Property("QVariantList", notify=changed)
    def groupChoices(self):
        return [{"id": g["id"], "name": _name(g)} for g in self._groups()] if self.state else []

    @Property(str, notify=changed)
    def notice(self):
        return self._notice

    def _set_notice(self, msg: str):
        self._notice = msg
        if msg:
            self._noticeTimer.start()
        self.changed.emit()

    @Property(QObject, constant=True)
    def settings(self):
        return self._settings

    @Property(QObject, constant=True)
    def sync(self):
        return self._sync

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
    # Diagnostics: AMBIENCE_DEBUG_WHEEL=1 prints every wheel event the pages receive.
    @Property(bool, constant=True)
    def debugWheel(self):
        return bool(os.environ.get("AMBIENCE_DEBUG_WHEEL"))

    @Slot(str)
    def debugLog(self, msg: str):
        import sys
        print(msg, file=sys.stderr, flush=True)

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
        return [self._group_entry(g) for g in self._groups()]

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
        return [self._scene_entry(s) for s in self.state.scenes_for(self._room_id)]

    def _scene_entry(self, s: dict) -> dict:
        effect = scene_effect(s)
        pal = scene_look(s)
        status = (s.get("status") or {}).get("active") or "inactive"
        bris = [a["action"]["dimming"]["brightness"] for a in s.get("actions", [])
                if a.get("action", {}).get("dimming", {}).get("brightness") is not None]
        group = self.state.get(s.get("group", {}).get("rid", "")) or {}
        photo = PHOTO_DIR / f"{s['id']}.jpg"
        return {
            "id": s["id"], "name": _name(s), "glow": pal or ["#ffb547"], "groupName": _name(group),
            # effect scenes animate by themselves; "dynamic" means cycling a colour palette
            "dynamic": not effect and len(palette_hexes(s)) > 1, "effect": effect.replace("_", " "),
            "active": status != "inactive", "playing": status,
            "speed": float(s.get("speed", 0.6)), "brightness": round(sum(bris) / len(bris)) if bris else 100,
            "selected": s["id"] == self._scene_id,
            # the mtime in the URL makes QML reload a replaced photo instead of using its cache
            "photo": QUrl.fromLocalFile(str(photo)).toString() + f"?v={int(photo.stat().st_mtime)}"
                     if photo.exists() else "",
        }

    # --- scenes ------------------------------------------------------------------------
    @Slot(str)
    def selectScene(self, sid: str):
        self._scene_id = sid
        self._refresh()

    @Property("QVariantMap", notify=changed)
    def scene(self):
        s = self.state.get(self._scene_id) if self.state and self._scene_id else None
        return self._scene_entry(s) if s else {}

    @Slot(str, bool, float, float)
    def playScene(self, sid: str, dynamic: bool, speed: float, brightness: float):
        """Recall a scene static or dynamic (cycling through its palette at `speed`)."""
        if not self.state:
            return
        if dynamic:   # the scene's stored speed first, as its own PUT ("Recall cannot be
            speed = round(max(0.0, min(1.0, speed)), 3)   # combined with modifying 'speed'")
            self._send("scene", sid, {"speed": speed})
        self._preview_scene(sid, "dynamic_palette" if dynamic else "static")
        self.cmd.put("scene", sid, {"recall": {"action": "dynamic_palette" if dynamic else "active",
                                               "dimming": {"brightness": max(1.0, min(100.0, brightness))}}},
                     slot="recall")

    @Slot(str, float)
    def setSceneSpeed(self, sid: str, speed: float):
        self._send("scene", sid, {"speed": round(max(0.0, min(1.0, speed)), 3)})

    @Slot(str, str)
    def setScenePhoto(self, sid: str, file_url: str):
        """Copy a picture in as this scene's thumbnail, scaled down to keep it small."""
        img = QImage(QUrl(file_url).toLocalFile())
        if img.isNull():
            self._set_notice("That file isn't a picture Ambience can read.")
            return
        if img.width() > 800:
            img = img.scaledToWidth(800, Qt.SmoothTransformation)
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        img.save(str(PHOTO_DIR / f"{sid}.jpg"), "JPG", 88)
        self._refresh()

    @Slot(str)
    def clearScenePhoto(self, sid: str):
        (PHOTO_DIR / f"{sid}.jpg").unlink(missing_ok=True)
        self._refresh()

    @Slot(str)
    def deleteScene(self, sid: str):
        """Delete a scene from the bridge (the UI asks for confirmation first)."""
        scene = self.state.get(sid) if self.state else None
        if not scene:
            return
        name = _name(scene)

        def work():
            try:
                self.bridge.delete("scene", sid)
            except (OSError, BridgeError) as e:
                self._set_error_from_thread(f"Couldn't delete {name}: {e}")
                return
            (PHOTO_DIR / f"{sid}.jpg").unlink(missing_ok=True)
            self.state.apply([{"type": "delete", "data": [{"id": sid, "type": "scene"}]}])
            self._noticeFromThread.emit(f"Deleted “{name}”")
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str)
    def addPreset(self, preset_id: str, group_id: str):
        """Create a gallery preset as a real scene in a room/zone (network call → thread)."""
        preset, group = PRESETS_BY_ID.get(preset_id), self.state.get(group_id) if self.state else None
        if not (preset and group):
            return
        lights = self.state.lights_in(group)

        def work():
            try:
                self.bridge.post("scene", scene_body(preset, group, lights))
                self._noticeFromThread.emit(f"Added “{preset.name}” to {_name(group)}")
            except (OSError, BridgeError) as e:
                self._set_error_from_thread(f"Couldn't add {preset.name}: {e}")
        threading.Thread(target=work, daemon=True).start()

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
        """Recall a scene as saved (static)."""
        if self.state:
            self._preview_scene(sid, "static")
            self.cmd.put("scene", sid, {"recall": {"action": "active"}}, slot="recall")

    def _preview_scene(self, sid: str, status: str):
        """Show a scene's target state at once. A scene stores exactly what each light
        becomes, so the app needn't wait ~1 s for the bridge's events (which arrive after
        the lamps have already changed)."""
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
                            "status": {"active": status if s["id"] == sid else "inactive"}})
        if updates:
            self.state.apply([{"type": "update", "data": updates}])
