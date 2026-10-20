"""Hue bridge client: discovery, pairing and the CLIP v2 REST API.

Trust model: the bridge serves a certificate signed by Signify's private CA with the
bridge id as its CN, and we connect by IP — so instead of CA validation we PIN the
certificate's SHA-256 at pairing (trust on first use, after checking the CN matches the
bridge id the bridge itself reports) and refuse any later connection whose certificate
differs.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import socket
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass


class BridgeError(Exception):
    pass


class LinkButtonNotPressed(BridgeError):
    pass


class CertificateMismatch(BridgeError):
    pass


@dataclass
class Found:
    bridge_id: str   # lowercase, e.g. 001788fffe0a1b2c
    host: str
    model: str = ""


def discover(timeout: float = 6.0) -> list[Found]:
    """Bridges on the LAN: mDNS (_hue._tcp via avahi) first, Signify's cloud lookup as a fallback."""
    found: dict[str, Found] = {}
    if shutil.which("avahi-browse"):
        try:
            out = subprocess.run(["avahi-browse", "-rtp", "_hue._tcp"], capture_output=True,
                                 text=True, timeout=timeout).stdout
            for line in out.splitlines():
                f = line.split(";")
                if len(f) >= 10 and f[0] == "=" and f[2] == "IPv4":
                    txt = dict(kv.strip('"').split("=", 1) for kv in f[9].split() if "=" in kv)
                    bid = txt.get("bridgeid", "").lower()
                    if bid:
                        found[bid] = Found(bid, f[7], txt.get("modelid", ""))
        except (subprocess.TimeoutExpired, OSError):
            pass
    if not found:
        try:
            with urllib.request.urlopen("https://discovery.meethue.com/", timeout=timeout) as r:
                for b in json.load(r):
                    bid = b["id"].lower()
                    found[bid] = Found(bid, b["internalipaddress"])
        except (OSError, ValueError, KeyError):
            pass
    return list(found.values())


def _unverified_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # verified by pin (Bridge._connect), not by CA
    return ctx


def fetch_certificate(host: str, port: int = 443, timeout: float = 5.0) -> bytes:
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with _unverified_ctx().wrap_socket(raw) as tls:
            return tls.getpeercert(binary_form=True)


def certificate_common_name(der: bytes) -> str:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    attrs = x509.load_der_x509_certificate(der).subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return attrs[0].value if attrs else ""


class Bridge:
    def __init__(self, host: str, cert_sha256: str, app_key: str | None = None, timeout: float = 8.0):
        self.host, self.cert_sha256, self.app_key, self.timeout = host, cert_sha256.lower(), app_key, timeout

    # --- transport -------------------------------------------------------------
    def _connect(self, timeout: float | None = None) -> http.client.HTTPSConnection:
        conn = http.client.HTTPSConnection(self.host, 443, timeout=timeout or self.timeout,
                                           context=_unverified_ctx())
        conn.connect()
        got = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
        if got != self.cert_sha256:
            conn.close()
            raise CertificateMismatch(
                f"the bridge at {self.host} presented a different certificate than at pairing "
                f"(expected {self.cert_sha256[:16]}…, got {got[:16]}…). Re-pair if the bridge was "
                "reset or replaced; otherwise something is intercepting the connection.")
        return conn

    def request(self, method: str, path: str, body=None, auth: bool = True):
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.app_key:
                raise BridgeError("not paired yet")
            headers["hue-application-key"] = self.app_key
        conn = self._connect()
        try:
            conn.request(method, path, None if body is None else json.dumps(body), headers)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        data = json.loads(raw) if raw else None
        if resp.status >= 400:
            errs = (data or {}).get("errors") if isinstance(data, dict) else None
            detail = "; ".join(e.get("description", "") for e in errs or []) or raw[:200].decode(errors="replace")
            raise BridgeError(f"{method} {path} → HTTP {resp.status}: {detail}")
        return data

    # --- pairing (classic /api endpoint; CLIP v2 has no pairing call) ----------
    def pair(self, device_type: str) -> tuple[str, str]:
        """→ (application key, entertainment client key). Needs the link button pressed
        within the previous ~30 s; raises LinkButtonNotPressed otherwise."""
        res = self.request("POST", "/api", {"devicetype": device_type[:40], "generateclientkey": True}, auth=False)
        item = res[0] if isinstance(res, list) and res else {}
        if "success" in item:
            return item["success"]["username"], item["success"]["clientkey"]
        err = item.get("error", {})
        if err.get("type") == 101:
            raise LinkButtonNotPressed("press the round button on top of the bridge, then try again")
        raise BridgeError(f"pairing failed: {err.get('description', res)}")

    # --- CLIP v2 ---------------------------------------------------------------
    def get(self, resource: str, rid: str | None = None) -> list[dict]:
        path = f"/clip/v2/resource/{resource}" + (f"/{rid}" if rid else "")
        return (self.request("GET", path) or {}).get("data", [])

    def put(self, resource: str, rid: str, body: dict):
        return self.request("PUT", f"/clip/v2/resource/{resource}/{rid}", body)

    def set_entertainment(self, area_id: str, active: bool):
        """Start/stop streaming mode for an entertainment area (must be started before
        the DTLS connection; stopping releases the lights back to normal control)."""
        return self.put("entertainment_configuration", area_id, {"action": "start" if active else "stop"})
