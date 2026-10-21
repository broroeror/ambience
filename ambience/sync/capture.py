"""Screen capture through the xdg-desktop-portal ScreenCast API + PipeWire + GStreamer.

The portal shows the desktop's own "share your screen" dialog the first time; we ask it
to remember the choice (persist_mode=2) and keep the restore token it returns, so later
runs start silently. Frames arrive from PipeWire already shrunk to 256×144 RGB — the colour
engine averages regions anyway, and scaling before colour conversion keeps a 4K capture
cheap.

Needs a running GLib main loop (the portal answers with D-Bus signals); `ScreenCapture`
runs its own in a thread, so callers just call start() and read latest().
"""
from __future__ import annotations

import os
import random
import string
import threading
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, Gst  # noqa: E402

import numpy as np  # noqa: E402

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST = "org.freedesktop.portal.ScreenCast"
REQUEST = "org.freedesktop.portal.Request"
TOKEN_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ambience" / "screencast-token"
WIDTH, HEIGHT = 256, 144


class CaptureError(RuntimeError):
    pass


def _token() -> str:
    return "ambience_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


class ScreenCapture:
    def __init__(self, fps: int = 60):
        self.fps = fps
        self._frame: np.ndarray | None = None
        self._frame_count = 0
        self._lock = threading.Lock()
        self._loop: GLib.MainLoop | None = None
        self._ctx: GLib.MainContext | None = None
        self._pipeline = None
        self._session = ""
        self._bus: Gio.DBusConnection | None = None
        self.error = ""

    # --- public -------------------------------------------------------------------
    def start(self, timeout: float = 120.0) -> None:
        """Ask the portal for a screen (dialog only on first use) and start streaming.
        Blocks until frames flow or it fails; raises CaptureError with a readable reason."""
        ready, result = threading.Event(), {}

        def run():
            self._ctx = GLib.MainContext.new()
            self._ctx.push_thread_default()
            self._loop = GLib.MainLoop.new(self._ctx, False)
            GLib.idle_add(lambda: self._begin(ready, result) and False)
            self._loop.run()
            self._ctx.pop_thread_default()

        Gst.init(None)
        threading.Thread(target=run, name="screencast", daemon=True).start()
        if not ready.wait(timeout):
            self.stop()
            raise CaptureError("the screen-sharing dialog wasn't answered in time")
        if "error" in result:
            self.stop()
            raise CaptureError(result["error"])

    def latest(self) -> tuple[np.ndarray | None, int]:
        """(newest frame as uint8 HxWx3 RGB, frame counter) — the counter tells callers
        whether anything new arrived."""
        with self._lock:
            return self._frame, self._frame_count

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        if self._bus and self._session:
            try:
                self._bus.call_sync(PORTAL, self._session, "org.freedesktop.portal.Session", "Close",
                                    None, None, Gio.DBusCallFlags.NONE, 2000, None)
            except GLib.Error:
                pass
            self._session = ""
        if self._loop is not None:
            self._loop.quit()

    # --- portal dance (runs on the capture thread's main loop) ------------------------
    def _request(self, method: str, args: GLib.Variant, on_response) -> None:
        """Call a portal method that answers via a Request object's Response signal. The
        args must carry the handle_token just made by _new_token() — the reply arrives on
        a Request path derived from it, which we subscribe to BEFORE calling."""
        sender = self._bus.get_unique_name()[1:].replace(".", "_")
        token = self._next_token
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

        def handler(_conn, _sender, _path, _iface, _signal, params, *_):
            self._bus.signal_unsubscribe(sub)
            code, results = params.unpack()
            on_response(code, results)

        sub = self._bus.signal_subscribe(PORTAL, REQUEST, "Response", path, None,
                                         Gio.DBusSignalFlags.NO_MATCH_RULE, handler)
        self._bus.call_sync(PORTAL, PORTAL_PATH, SCREENCAST, method, args, None,
                            Gio.DBusCallFlags.NONE, -1, None)

    def _begin(self, ready: threading.Event, result: dict) -> None:
        def fail(msg):
            result["error"] = msg
            ready.set()

        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            return fail(f"no session D-Bus: {e.message}")

        def created(code, res):
            if code != 0:
                return fail("the screen-sharing request was refused")
            self._session = res["session_handle"]
            opts = {"handle_token": GLib.Variant("s", self._new_token()),
                    "types": GLib.Variant("u", 1),           # monitors
                    "multiple": GLib.Variant("b", False),
                    "cursor_mode": GLib.Variant("u", 1),     # hidden: the pointer isn't scenery
                    "persist_mode": GLib.Variant("u", 2)}    # remember until revoked
            saved = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
            if saved:
                opts["restore_token"] = GLib.Variant("s", saved)
            self._request("SelectSources", GLib.Variant("(oa{sv})", (self._session, opts)), selected)

        def selected(code, _res):
            if code != 0:
                return fail("no screen was chosen")
            self._request("Start", GLib.Variant("(osa{sv})", (self._session, "",
                          {"handle_token": GLib.Variant("s", self._new_token())})), started)

        def started(code, res):
            if code == 1:
                return fail("screen sharing was cancelled")
            if code != 0:
                return fail("screen sharing couldn't start")
            if res.get("restore_token"):
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(res["restore_token"])
            streams = res.get("streams") or []
            if not streams:
                return fail("the portal returned no screen stream")
            node = streams[0][0]
            try:
                ret, fds = self._bus.call_with_unix_fd_list_sync(
                    PORTAL, PORTAL_PATH, SCREENCAST, "OpenPipeWireRemote",
                    GLib.Variant("(oa{sv})", (self._session, {})), GLib.VariantType("(h)"),
                    Gio.DBusCallFlags.NONE, -1, None, None)
                fd = fds.get(ret.unpack()[0])
            except GLib.Error as e:
                return fail(f"couldn't open the PipeWire stream: {e.message}")
            err = self._start_pipeline(fd, node)
            if err:
                return fail(err)
            ready.set()

        self._request("CreateSession", GLib.Variant("(a{sv})", ({
            "handle_token": GLib.Variant("s", self._new_token()),
            "session_handle_token": GLib.Variant("s", _token())},)), created)

    def _new_token(self) -> str:
        self._next_token = _token()
        return self._next_token

    # --- GStreamer -----------------------------------------------------------------
    def _start_pipeline(self, fd: int, node: int) -> str:
        desc = (f"pipewiresrc fd={fd} path={node} do-timestamp=true keepalive-time=500 always-copy=true "
                f"! videorate drop-only=true ! video/x-raw,framerate=[1/1,{self.fps}/1] "
                f"! videoscale method=bilinear n-threads=2 ! video/x-raw,width={WIDTH},height={HEIGHT} "
                "! videoconvert n-threads=2 ! video/x-raw,format=RGB "
                "! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false")
        try:
            self._pipeline = Gst.parse_launch(desc)
        except GLib.Error as e:
            return f"capture pipeline failed: {e.message}"
        sink = self._pipeline.get_by_name("sink")
        sink.connect("new-sample", self._on_sample)
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", lambda _b, m: setattr(self, "error", m.parse_error()[0].message))
        if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            return "the capture pipeline wouldn't start"
        return ""

    def _on_sample(self, sink) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        buf, caps = sample.get_buffer(), sample.get_caps().get_structure(0)
        w, h = caps.get_value("width"), caps.get_value("height")
        ok, info = buf.map(Gst.MapFlags.READ)
        if ok:
            try:
                stride = len(info.data) // h
                arr = np.frombuffer(info.data, dtype=np.uint8).reshape(h, stride)[:, :w * 3].reshape(h, w, 3).copy()
            finally:
                buf.unmap(info)
            with self._lock:
                self._frame = arr
                self._frame_count += 1
        return Gst.FlowReturn.OK
