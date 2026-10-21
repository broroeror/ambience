"""The sync worker: a separate process that owns screen capture and the 50 Hz stream, so
nothing the window does (busy, frozen, crashed) can stutter the lights — and the area is
handed back from here no matter what.

Protocol over a multiprocessing Pipe (dicts):
  window → worker   {"cmd": "start", "area": {...}, "host", "app_key", "cert", "client_key",
                     "intensity", "brightness"}
                    {"cmd": "set", "intensity"?, "brightness"?}
                    {"cmd": "stop"} · {"cmd": "quit"}
  worker → window   {"state": "starting"|"running"|"stopped"|"error", "message"?}
                    {"preview": {"colours": {ch: [r,g,b]}, "frame": bytes|None, "w", "h",
                                 "rate": float, "fps": float}}   ~8×/s while running
"""
from __future__ import annotations

import threading
import time

import numpy as np


def run_worker(conn) -> None:
    from ..bridge.client import Bridge
    from .capture import CaptureError, ScreenCapture
    from .engine import SyncEngine, SyncSettings

    cap: ScreenCapture | None = None
    engine: SyncEngine | None = None
    thread: threading.Thread | None = None
    settings: SyncSettings | None = None

    def stop_all(state="stopped", message=""):
        nonlocal cap, engine, thread, settings
        if settings:
            settings.stop.set()
        if thread:
            thread.join(5)
        if cap:
            cap.stop()
        cap = engine = thread = settings = None
        conn.send({"state": state, "message": message})

    def engine_main(eng, st):
        try:
            eng.run(st)
        except Exception as e:  # noqa: BLE001 — report, don't die silently
            st.error = str(e)
        finally:
            st.done = True

    last_preview = 0.0
    while True:
        if conn.poll(0.05):
            try:
                msg = conn.recv()
            except EOFError:
                msg = {"cmd": "quit"}
            cmd = msg.get("cmd")
            if cmd == "quit":
                if thread:
                    stop_all()
                return
            if cmd == "stop" and thread:
                stop_all()
            elif cmd == "set" and settings:
                if "intensity" in msg:
                    settings.intensity = msg["intensity"]
                if "brightness" in msg:
                    settings.brightness = float(msg["brightness"])
            elif cmd == "start" and not thread:
                conn.send({"state": "starting"})
                cap = ScreenCapture()
                try:
                    cap.start()
                    t0 = time.monotonic()
                    while cap.latest()[0] is None and time.monotonic() - t0 < 5:
                        time.sleep(0.05)
                    if cap.latest()[0] is None:
                        raise CaptureError(f"no screen frames arrived ({cap.error or 'no error reported'})")
                except CaptureError as e:
                    stop_all("error", str(e))
                    continue
                bridge = Bridge(msg["host"], msg["cert"], msg["app_key"])
                engine = SyncEngine(bridge, msg["host"], msg["client_key"], msg["area"], cap)
                settings = SyncSettings(intensity=msg.get("intensity", "moderate"),
                                        brightness=float(msg.get("brightness", 0.85)))
                settings.error, settings.done = "", False
                thread = threading.Thread(target=engine_main, args=(engine, settings), daemon=True)
                thread.start()
                conn.send({"state": "running"})

        if thread and settings and settings.done:
            err = settings.error
            settings.stop.set()
            stop_all("error" if err else "stopped", err)
            continue

        now = time.monotonic()
        if thread and engine and now - last_preview > 0.12:
            last_preview = now
            frame, _ = cap.latest() if cap else (None, 0)
            small = None
            if frame is not None:   # 64×36 thumbnail of what the lights sample
                h, w = frame.shape[:2]
                small = frame.reshape(36, h // 36, 64, w // 64, 3).mean(axis=(1, 3)).astype(np.uint8).tobytes() \
                    if h % 36 == 0 and w % 64 == 0 else None
            el = max(1e-6, now - engine.stats["started"]) if engine.stats["started"] else 1.0
            conn.send({"preview": {"colours": {k: list(v) for k, v in engine.preview.items()},
                                   "frame": small, "w": 64, "h": 36,
                                   "rate": engine.stats["sent"] / el, "fps": engine.stats["frames"] / el}})
