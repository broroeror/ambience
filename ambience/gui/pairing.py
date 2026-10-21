"""First-run pairing inside the app: find the bridge, then wait for its link button.

Same trust rules as `python -m ambience pair`: the certificate's CN must match the bridge id
the network reported, and its SHA-256 is pinned for every later connection. Network work
runs on threads; results come back to the GUI thread through queued signals.
"""
from __future__ import annotations

import hashlib
import socket
import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ..bridge import store
from ..bridge.client import (Bridge, BridgeError, LinkButtonNotPressed, certificate_common_name,
                             discover, fetch_certificate)

WAIT_SECONDS = 90


class PairingController(QObject):
    changed = Signal()
    paired = Signal()                 # keys saved: the backend reconnects
    _searchDone = Signal(list, str)
    _pairDone = Signal(str)           # "" = success, else an error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stage = "idle"          # idle · searching · found · waiting · done · error
        self._bridges: list[dict] = []
        self._message = ""
        self._deadline = 0.0
        self._cancel = threading.Event()
        self._tick = QTimer(self, interval=250)
        self._tick.timeout.connect(self.changed)
        self._searchDone.connect(self._on_search)
        self._pairDone.connect(self._on_pair)

    # --- properties -----------------------------------------------------------------
    @Property(str, notify=changed)
    def stage(self):
        return self._stage

    @Property("QVariantList", notify=changed)
    def bridges(self):
        return self._bridges

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(int, notify=changed)
    def secondsLeft(self):
        return max(0, int(self._deadline - time.monotonic() + 0.999)) if self._stage == "waiting" else 0

    @Property(int, constant=True)
    def waitSeconds(self):
        return WAIT_SECONDS

    def _set(self, stage: str, message: str = ""):
        self._stage, self._message = stage, message
        self.changed.emit()

    # --- search -----------------------------------------------------------------------
    @Slot()
    def search(self):
        self._set("searching")

        def work():
            found = [{"id": f.bridge_id, "host": f.host,
                      "model": {"BSB002": "Hue Bridge (2nd gen)", "BSB003": "Hue Bridge Pro",
                                "BSB001": "Hue Bridge (1st gen)"}.get(f.model, f.model or "Hue Bridge")}
                     for f in discover()]
            self._searchDone.emit(found, "")
        threading.Thread(target=work, daemon=True).start()

    def _on_search(self, found: list, _err: str):
        self._bridges = found
        if found:
            self._set("found")
        else:
            self._set("error", "No Hue Bridge answered on your network. Check it's powered and on the "
                               "same network as this computer, or enter its IP address.")

    # --- pair -------------------------------------------------------------------------
    @Slot(str)
    def pairWith(self, host: str):
        host = host.strip()
        if not host:
            return
        match = next((b for b in self._bridges if b["host"] == host), None)
        expected_id = match["id"] if match else ""
        self._cancel.clear()
        self._deadline = time.monotonic() + WAIT_SECONDS
        self._set("waiting")
        self._tick.start()

        def work():
            try:
                der = fetch_certificate(host)
            except OSError as e:
                return self._pairDone.emit(f"Couldn't reach a bridge at {host} ({e.strerror or e}).")
            cn = certificate_common_name(der).lower()
            if expected_id and cn != expected_id:
                return self._pairDone.emit("That bridge's certificate doesn't match its id, so Ambience "
                                           "won't trust it. If this keeps happening, something on the "
                                           "network may be intercepting the connection.")
            pin = hashlib.sha256(der).hexdigest()
            bridge = Bridge(host, pin)
            # Confirm it IS a Hue Bridge before sending it anything: its public, no-login
            # config must report a bridge id matching the certificate. (A typed address that's
            # some other device would otherwise get our pairing request.)
            try:
                cfg = bridge.request("GET", "/api/0/config", auth=False) or {}
            except (OSError, BridgeError, ValueError):
                cfg = {}
            if not isinstance(cfg, dict) or str(cfg.get("bridgeid", "")).lower() != cn \
                    or not str(cfg.get("modelid", "")).startswith("BSB"):
                return self._pairDone.emit(f"The device at {host} doesn't look like a Hue Bridge. "
                                           "Check the address in your router or the Hue app "
                                           "(Settings → Bridges).")
            while not self._cancel.is_set():
                try:
                    app_key, client_key = bridge.pair(f"ambience#{socket.gethostname()}")
                except LinkButtonNotPressed:
                    if time.monotonic() > self._deadline:
                        return self._pairDone.emit("timeout")
                    time.sleep(1.5)
                    continue
                except (OSError, BridgeError) as e:
                    return self._pairDone.emit(f"Pairing failed: {e}")
                model = match["model"] if match else str(cfg.get("modelid", ""))
                store.save(store.Pairing(cn, host, pin, model), app_key, client_key)
                return self._pairDone.emit("")
            self._pairDone.emit("cancelled")
        threading.Thread(target=work, daemon=True).start()

    def _on_pair(self, err: str):
        self._tick.stop()
        if not err:
            self._set("done")
            QTimer.singleShot(900, self.paired.emit)      # let "Connected" show for a moment
        elif err == "cancelled":
            self._set("found" if self._bridges else "idle")
        elif err == "timeout":
            self._set("error", "The button wasn't pressed in time. Press it once, firmly, then try again — "
                               "the countdown restarts.")
        else:
            self._set("error", err)

    @Slot()
    def cancel(self):
        self._cancel.set()
