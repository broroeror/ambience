"""Where pairing lives: non-secret bridge details in ~/.config/ambience/bridge.json, the
two keys (application key + entertainment client key) in the desktop keyring (KWallet
or GNOME Keyring via the Secret Service), never on disk in plain text."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import keyring

SERVICE = "ambience"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ambience"
BRIDGE_FILE = CONFIG_DIR / "bridge.json"


@dataclass
class Pairing:
    bridge_id: str
    host: str
    cert_sha256: str
    model: str = ""


def save(p: Pairing, app_key: str, client_key: str) -> None:
    keyring.set_password(SERVICE, p.bridge_id, json.dumps({"app_key": app_key, "client_key": client_key}))
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BRIDGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(p), indent=2))
    os.replace(tmp, BRIDGE_FILE)


def has_pairing() -> bool:
    """A bridge was paired (its details are on disk), whether or not the keys are readable."""
    try:
        Pairing(**json.loads(BRIDGE_FILE.read_text()))
        return True
    except (OSError, ValueError, TypeError):
        return False


def load() -> tuple[Pairing, str, str] | None:
    """(pairing, app_key, client_key) or None if not paired / keys unreadable. Right after
    login the keyring may not be unlocked yet: then has_pairing() is True and a later
    load() succeeds, so callers should wait rather than ask to pair again."""
    try:
        p = Pairing(**json.loads(BRIDGE_FILE.read_text()))
    except (OSError, ValueError, TypeError):
        return None
    try:
        secret = keyring.get_password(SERVICE, p.bridge_id)
    except Exception:  # noqa: BLE001 — a locked or not-yet-started keyring raises its own errors
        return None
    if not secret:
        return None
    k = json.loads(secret)
    return p, k["app_key"], k["client_key"]
