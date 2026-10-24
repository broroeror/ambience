"""The sync worker: a separate process that owns screen capture and the 50 Hz stream, so
nothing the window does (busy, frozen, crashed) can stutter the lights — and the area is
handed back from here no matter what.

Protocol over a multiprocessing Pipe (dicts):
  window → worker   {"cmd": "start", "mode": "screen"|"music", "area": {...}, "host",
                     "app_key", "cert", "client_key", "intensity", "brightness", "palette"?}
                    {"cmd": "set", "intensity"?, "brightness"?}
                    {"cmd": "stop"} · {"cmd": "quit"}
  worker → window   {"state": "starting"|"running"|"stopped"|"error", "message"?}
                    {"preview": {"colours": {ch: [r,g,b]}, "rate": float, "fps": float,
                                 screen: "frame": bytes|None, "w", "h" · music: "bands", "beat"}}
                    ~8×/s while running
"""
from __future__ import annotations

import threading
import time



def run_worker(conn) -> None:
    from ..bridge.client import Bridge
    from .engine import MusicProducer, ScreenProducer, SyncEngine, SyncSettings, area_channels

    cap = None                     # the active capture (screen or audio)
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

    last_preview = last_glow = 0.0
    while True:
        if conn.poll(0.05):
            try:
                msg = conn.recv()
            except EOFError:
                msg = {"cmd": "quit"}
            cmd = msg.get("cmd")
            if cmd in ("quit", "stop", "start"):
                from .engine import log
                log(f"worker: received {cmd}" + (f" ({msg.get('mode', 'screen')})" if cmd == "start" else ""))
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
                chans = area_channels(msg["area"])
                try:
                    if msg.get("mode") == "music":
                        from .audio import AudioCapture
                        cap = AudioCapture()
                        cap.start()
                        producer = MusicProducer(cap, chans, msg.get("palette"))
                    else:
                        from .capture import ScreenCapture
                        cap = ScreenCapture()
                        cap.start()
                        t0 = time.monotonic()
                        while cap.latest()[0] is None and time.monotonic() - t0 < 5:
                            time.sleep(0.05)
                        if cap.latest()[0] is None:
                            raise RuntimeError(f"no screen frames arrived ({cap.error or 'no error reported'})")
                        producer = ScreenProducer(cap, chans)
                except Exception as e:  # noqa: BLE001 — CaptureError, AudioCaptureError, …
                    stop_all("error", str(e))
                    continue
                bridge = Bridge(msg["host"], msg["cert"], msg["app_key"])
                engine = SyncEngine(bridge, msg["host"], msg["client_key"], msg["area"], producer)
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
        if thread and engine and now - last_glow > 0.03:
            # Colours only, ~30/s, so the window's edge glow can pulse with the lights;
            # the heavier preview (screen thumbnail, bands) stays at ~8/s.
            last_glow = now
            conn.send({"glow": {k: list(v) for k, v in engine.preview.items()}})
        if thread and engine and now - last_preview > 0.12:
            last_preview = now
            el = max(1e-6, now - engine.stats["started"]) if engine.stats["started"] else 1.0
            conn.send({"preview": {"colours": {k: list(v) for k, v in engine.preview.items()},
                                   "rate": engine.stats["sent"] / el, "fps": engine.frames / el,
                                   **engine.producer.preview()}})
