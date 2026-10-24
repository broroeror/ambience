"""App preferences for the Settings page, kept in ~/.config/ambience/settings.json.

How the app feels (scroll speed, colour fades) lives here; sync choices stay with the
Sync page (sync.json), which remembers them as you use it. "Start with the computer" is
not a setting in the file but the presence of an autostart entry, so removing that entry
by hand (or in System Settings) shows up here too.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .. import __version__
from ..bridge import store

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
SETTINGS = CONFIG / "ambience" / "settings.json"
AUTOSTART = CONFIG / "autostart" / "ambience.desktop"
LOG_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ambience"

DEFAULTS = {"fadeMs": 700, "scrollSpeed": 34,
            "edgeGlow": True, "edgeGlowSyncOnly": False, "edgeGlowStrength": 60, "edgeGlowWidth": 90}


class Settings(QObject):
    changed = Signal()

    def __init__(self, backend):
        super().__init__(backend)
        self._backend = backend
        try:
            saved = json.loads(SETTINGS.read_text())
        except (OSError, ValueError):
            saved = {}
        self._v = {k: saved.get(k, d) for k, d in DEFAULTS.items()}
        backend.changed.connect(self.changed)       # bridge details follow the live state

    def _set(self, key: str, value):
        if self._v[key] != value:
            self._v[key] = value
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps(self._v, indent=2))
            self.changed.emit()

    # --- how the app feels -------------------------------------------------------------
    @Property(int, notify=changed)
    def fadeMs(self):
        return self._v["fadeMs"]

    @Slot(int)
    def setFadeMs(self, ms: int):
        self._set("fadeMs", max(0, min(2000, int(round(ms / 50) * 50))))

    @Property(int, notify=changed)
    def scrollSpeed(self):
        """Pixels per scroll "line"; one wheel notch is usually 3 lines."""
        return self._v["scrollSpeed"]

    @Slot(int)
    def setScrollSpeed(self, px: int):
        self._set("scrollSpeed", max(10, min(90, int(px))))

    # --- edge glow -----------------------------------------------------------------------
    @Property(bool, notify=changed)
    def edgeGlow(self):
        return bool(self._v["edgeGlow"])

    @Slot(bool)
    def setEdgeGlow(self, on: bool):
        self._set("edgeGlow", bool(on))

    @Property(bool, notify=changed)
    def edgeGlowSyncOnly(self):
        return bool(self._v["edgeGlowSyncOnly"])

    @Slot(bool)
    def setEdgeGlowSyncOnly(self, on: bool):
        self._set("edgeGlowSyncOnly", bool(on))

    @Property(int, notify=changed)
    def edgeGlowStrength(self):
        """Percent."""
        return self._v["edgeGlowStrength"]

    @Slot(int)
    def setEdgeGlowStrength(self, pct: int):
        self._set("edgeGlowStrength", max(10, min(100, int(pct))))

    @Property(int, notify=changed)
    def edgeGlowWidth(self):
        """How far the glow reaches in from the edge, px."""
        return self._v["edgeGlowWidth"]

    @Slot(int)
    def setEdgeGlowWidth(self, px: int):
        self._set("edgeGlowWidth", max(30, min(240, int(px))))

    @Slot(str)
    def reset(self, key: str):
        self._set(key, DEFAULTS[key])

    @Property("QVariantMap", constant=True)
    def defaults(self):
        return DEFAULTS

    # --- start with the computer ---------------------------------------------------------
    @Property(bool, notify=changed)
    def autostart(self):
        return AUTOSTART.exists()

    @Slot(bool)
    def setAutostart(self, on: bool):
        if on:
            if shutil.which("ambience"):          # installed from the package
                exec_line, extra = "ambience --hidden", ""
            else:                                 # running from the source tree
                root = Path(__file__).resolve().parents[2]
                exec_line, extra = f"{sys.executable} -m ambience.gui --hidden", f"Path={root}\n"
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text("[Desktop Entry]\nType=Application\nName=Ambience\n"
                                 "Comment=Start Ambience in the tray\n"
                                 f"Exec={exec_line}\n{extra}Icon=ambience\nTerminal=false\n"
                                 "X-GNOME-Autostart-enabled=true\n")
        else:
            AUTOSTART.unlink(missing_ok=True)
        self.changed.emit()

    # --- the bridge ------------------------------------------------------------------------
    @Property("QVariantMap", notify=changed)
    def bridge(self):
        got = store.load()
        if not got:
            return {}
        p = got[0]
        info = {"id": p.bridge_id, "host": p.host, "model": p.model, "name": "Hue Bridge", "software": ""}
        state = self._backend.state
        dev = next((d for d in state.of("device") if any(s.get("rtype") == "bridge" for s in d.get("services", []))),
                   None) if state else None
        if dev:
            info["name"] = (dev.get("metadata") or {}).get("name") or info["name"]
            pd = dev.get("product_data") or {}
            info["model"] = pd.get("model_id") or info["model"]
            info["software"] = pd.get("software_version", "")
        return info

    # --- about -------------------------------------------------------------------------------
    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, constant=True)
    def logDir(self):
        return str(LOG_DIR).replace(str(Path.home()), "~", 1)

    @Slot()
    def openLogDir(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR)))
