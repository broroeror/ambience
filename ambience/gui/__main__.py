"""Ambience desktop app: python -m ambience.gui [--hidden]

Lives in the tray: closing the window hides it (sync keeps running); Quit from the tray
menu stops sync — handing the lights back — and exits. Only one copy runs: launching it
again just brings the existing window forward. --hidden starts straight into the tray.
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .backend import Backend

HERE = Path(__file__).resolve().parent
INSTANCE_KEY = "ambience-gui"


def icon(name: str) -> QIcon:
    return QIcon(str(HERE / "icons" / f"{name}.svg"))


def already_running() -> bool:
    """If another copy runs, ask it to show its window and return True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        return True
    return False


def main() -> int:
    # Our own look everywhere: never let the desktop's Qt style restyle the controls.
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)          # widgets: the tray icon + its menu
    app.setApplicationName("Ambience")
    app.setDesktopFileName("ambience")
    app.setWindowIcon(icon("ambience"))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if already_running():
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    # Static weights (Qt won't pick weights out of a variable font loaded this way).
    families = set()
    for ttf in sorted((HERE / "fonts").glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(ttf))
        if fid >= 0:
            families.update(QFontDatabase.applicationFontFamilies(fid))
    if families:
        font = QFont(sorted(families)[0])
        font.setPixelSize(14)
        app.setFont(font)

    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(HERE))
    engine.rootContext().setContextProperty("backend", backend)
    engine.addImageProvider("sync", backend.sync_provider)
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    win = engine.rootObjects()[0]

    def show_window():
        win.show()
        win.raise_()
        win.requestActivate()

    def on_connection():
        sock = server.nextPendingConnection()
        if sock:
            sock.waitForReadyRead(200)
            if bytes(sock.readAll()).startswith(b"show"):
                show_window()
            sock.disconnectFromServer()
    server.newConnection.connect(on_connection)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        win.setProperty("hideOnClose", True)        # closing hides to the tray; sync keeps going

        tray = QSystemTrayIcon(icon("ambience"), app)
        menu = QMenu()
        act_open = QAction("Open Ambience", menu)
        act_open.triggered.connect(show_window)
        act_sync = QAction("Start sync", menu)
        act_sync.triggered.connect(lambda: backend.sync.stop() if backend.sync.state in ("running", "starting")
                                   else backend.sync.start())
        act_off = QAction("All lights off", menu)
        act_off.triggered.connect(lambda: backend.setAllOn(False))
        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(app.quit)
        for a in (act_open, act_sync, act_off):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: (win.hide() if win.isVisible() else show_window())
                               if reason == QSystemTrayIcon.Trigger else None)

        def sync_changed():
            sync = backend.sync
            area = sync.area.get("name", "") if sync.area else ""
            running = sync.state == "running"
            act_sync.setEnabled(bool(backend.paired) and sync.state != "starting")
            act_sync.setText(("Stop sync" if running else "Starting sync…" if sync.state == "starting"
                              else f"Start {sync.mode} sync" + (f" · {area}" if area else "")))
            tray.setIcon(icon("ambience-sync" if running else "ambience"))
            tray.setToolTip(f"Ambience — syncing {area}" if running else "Ambience")
        backend.sync.changed.connect(sync_changed)
        backend.changed.connect(sync_changed)
        sync_changed()
        tray.show()

    if "--hidden" in sys.argv and tray is not None:
        win.hide()
    else:
        show_window()

    rc = app.exec()
    backend.sync.shutdown()   # stop streaming → the lights are handed back before we exit
    if tray is not None:
        tray.hide()
    del engine          # tear the screens down while `backend` still exists
    backend.state and backend.state.stop()
    return rc


if __name__ == "__main__":
    sys.exit(main())
