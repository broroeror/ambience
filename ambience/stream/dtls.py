"""Minimal DTLS 1.2 PSK client on the system's OpenSSL 3, via ctypes.

The Hue Entertainment API streams light colours over DTLS 1.2 with a pre-shared key
(cipher TLS_PSK_WITH_AES_128_GCM_SHA256, port 2100). Python's ssl module has no DTLS,
and pyOpenSSL exposes DTLS but not PSK, so we drive libssl directly. Only the handful
of calls a client needs are bound: method/context, cipher list, PSK callback, a
connected datagram BIO, connect, write, shutdown.

    with DtlsPskClient(host, 2100, identity=b"<app key>", psk=bytes.fromhex(clientkey)) as c:
        c.send(packet)
"""
from __future__ import annotations

import ctypes
import ctypes.util
import select
import socket
import time

_ssl = ctypes.CDLL(ctypes.util.find_library("ssl") or "libssl.so.3")
_crypto = ctypes.CDLL(ctypes.util.find_library("crypto") or "libcrypto.so.3")

_vp, _int, _uint, _long = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_long


def _fn(lib, name, res, *args):
    f = getattr(lib, name)
    f.restype, f.argtypes = res, list(args)
    return f


DTLS_client_method = _fn(_ssl, "DTLS_client_method", _vp)
SSL_CTX_new = _fn(_ssl, "SSL_CTX_new", _vp, _vp)
SSL_CTX_free = _fn(_ssl, "SSL_CTX_free", None, _vp)
SSL_CTX_ctrl = _fn(_ssl, "SSL_CTX_ctrl", _long, _vp, _int, _long, _vp)
SSL_CTX_set_cipher_list = _fn(_ssl, "SSL_CTX_set_cipher_list", _int, _vp, ctypes.c_char_p)
SSL_new = _fn(_ssl, "SSL_new", _vp, _vp)
SSL_free = _fn(_ssl, "SSL_free", None, _vp)
SSL_set_bio = _fn(_ssl, "SSL_set_bio", None, _vp, _vp, _vp)
SSL_connect = _fn(_ssl, "SSL_connect", _int, _vp)
SSL_write = _fn(_ssl, "SSL_write", _int, _vp, ctypes.c_char_p, _int)
SSL_shutdown = _fn(_ssl, "SSL_shutdown", _int, _vp)
SSL_get_error = _fn(_ssl, "SSL_get_error", _int, _vp, _int)
SSL_ctrl = _fn(_ssl, "SSL_ctrl", _long, _vp, _int, _long, _vp)
BIO_new_dgram = _fn(_crypto, "BIO_new_dgram", _vp, _int, _int)
BIO_ctrl = _fn(_crypto, "BIO_ctrl", _long, _vp, _int, _long, _vp)
BIO_ADDR_new = _fn(_crypto, "BIO_ADDR_new", _vp)
BIO_ADDR_free = _fn(_crypto, "BIO_ADDR_free", None, _vp)
BIO_ADDR_rawmake = _fn(_crypto, "BIO_ADDR_rawmake", _int, _vp, _int, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_ushort)
ERR_get_error = _fn(_crypto, "ERR_get_error", ctypes.c_ulong)
ERR_error_string_n = _fn(_crypto, "ERR_error_string_n", None, ctypes.c_ulong, ctypes.c_char_p, ctypes.c_size_t)

# unsigned int cb(SSL *ssl, const char *hint, char *identity, unsigned int max_identity_len,
#                 unsigned char *psk, unsigned int max_psk_len)
_PSK_CB = ctypes.CFUNCTYPE(_uint, _vp, ctypes.c_char_p, _vp, _uint, _vp, _uint)
SSL_CTX_set_psk_client_callback = _fn(_ssl, "SSL_CTX_set_psk_client_callback", None, _vp, _PSK_CB)

SSL_CTRL_SET_MIN_PROTO_VERSION = 123
SSL_CTRL_SET_MAX_PROTO_VERSION = 124
DTLS1_2_VERSION = 0xFEFD
BIO_NOCLOSE = 0
BIO_CTRL_DGRAM_SET_CONNECTED = 32
DTLS_CTRL_GET_TIMEOUT = 73     # DTLSv1_get_timeout()   (a macro in C)
DTLS_CTRL_HANDLE_TIMEOUT = 74  # DTLSv1_handle_timeout()
SSL_ERROR_WANT_READ, SSL_ERROR_WANT_WRITE, SSL_ERROR_SYSCALL = 2, 3, 5
HUE_CIPHER = b"PSK-AES128-GCM-SHA256"


class _Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class DtlsError(OSError):
    pass


def _openssl_errors() -> str:
    out = []
    while (code := ERR_get_error()):
        buf = ctypes.create_string_buffer(256)
        ERR_error_string_n(code, buf, len(buf))
        out.append(buf.value.decode(errors="replace"))
    return "; ".join(out) or "no OpenSSL detail"


class DtlsPskClient:
    """A connected DTLS 1.2 PSK session over UDP. Not thread-safe; one writer."""

    def __init__(self, host: str, port: int, identity: bytes, psk: bytes,
                 cipher: bytes = HUE_CIPHER, timeout: float = 5.0):
        self._identity, self._psk = identity, psk
        self._ctx = self._ssl = self._addr = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Non-blocking: we run the handshake loop ourselves (below), so a lost
            # datagram triggers OpenSSL's DTLS retransmit timer instead of a hang.
            self._sock.setblocking(False)
            self._sock.connect((host, port))
            self._ctx = SSL_CTX_new(DTLS_client_method())
            if not self._ctx:
                raise DtlsError(f"SSL_CTX_new failed: {_openssl_errors()}")
            SSL_CTX_ctrl(self._ctx, SSL_CTRL_SET_MIN_PROTO_VERSION, DTLS1_2_VERSION, None)
            SSL_CTX_ctrl(self._ctx, SSL_CTRL_SET_MAX_PROTO_VERSION, DTLS1_2_VERSION, None)
            if SSL_CTX_set_cipher_list(self._ctx, cipher) != 1:
                raise DtlsError(f"cipher {cipher!r} unavailable: {_openssl_errors()}")
            self._cb = _PSK_CB(self._on_psk)  # keep a reference: OpenSSL holds a raw pointer
            SSL_CTX_set_psk_client_callback(self._ctx, self._cb)

            self._ssl = SSL_new(self._ctx)
            bio = BIO_new_dgram(self._sock.fileno(), BIO_NOCLOSE)
            ip = socket.inet_aton(socket.gethostbyname(host))
            self._addr = BIO_ADDR_new()
            BIO_ADDR_rawmake(self._addr, socket.AF_INET, ip, len(ip), socket.htons(port))
            BIO_ctrl(bio, BIO_CTRL_DGRAM_SET_CONNECTED, 0, self._addr)  # use send(), not sendto()
            SSL_set_bio(self._ssl, bio, bio)  # the SSL now owns the BIO
            self._handshake(timeout)
        except BaseException:
            self.close()
            raise

    def _handshake(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        tv = _Timeval()
        while True:
            rc = SSL_connect(self._ssl)
            if rc == 1:
                return
            err = SSL_get_error(self._ssl, rc)
            if err == SSL_ERROR_SYSCALL:
                raise DtlsError("the bridge refused the stream connection — is the entertainment "
                                "area started (PUT action=start) before connecting?")
            if err not in (SSL_ERROR_WANT_READ, SSL_ERROR_WANT_WRITE):
                raise DtlsError(f"DTLS handshake failed (SSL error {err}): {_openssl_errors()}")
            left = deadline - time.monotonic()
            if left <= 0:
                # A PSK mismatch looks exactly like silence: the server drops our Finished.
                raise DtlsError(f"DTLS handshake timed out after {timeout:g}s — wrong client key, "
                                "or the bridge isn't answering")
            wait = left
            if SSL_ctrl(self._ssl, DTLS_CTRL_GET_TIMEOUT, 0, ctypes.byref(tv)) == 1:
                wait = min(wait, tv.tv_sec + tv.tv_usec / 1e6)  # OpenSSL's retransmit deadline
            if err == SSL_ERROR_WANT_READ:
                ready, _, _ = select.select([self._sock], [], [], wait)
            else:
                _, ready, _ = select.select([], [self._sock], [], wait)
            if not ready:
                SSL_ctrl(self._ssl, DTLS_CTRL_HANDLE_TIMEOUT, 0, None)  # resend the last flight

    def _on_psk(self, _ssl, _hint, identity, max_identity_len, psk, max_psk_len):
        ident = self._identity
        if len(ident) + 1 > max_identity_len or len(self._psk) > max_psk_len:
            return 0  # 0 = abort the handshake
        ctypes.memmove(identity, ident + b"\0", len(ident) + 1)
        ctypes.memmove(psk, self._psk, len(self._psk))
        return len(self._psk)

    def send(self, data: bytes) -> None:
        n = SSL_write(self._ssl, data, len(data))
        if n != len(data):
            raise DtlsError(f"SSL_write failed (SSL error {SSL_get_error(self._ssl, n)}): {_openssl_errors()}")

    def close(self) -> None:
        if self._ssl:
            SSL_shutdown(self._ssl)  # best-effort close_notify
            SSL_free(self._ssl)      # also frees the BIO
            self._ssl = None
        if self._ctx:
            SSL_CTX_free(self._ctx)
            self._ctx = None
        if self._addr:
            BIO_ADDR_free(self._addr)
            self._addr = None
        self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
