"""Ambience desktop app: python -m ambience.gui"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .backend import Backend

HERE = Path(__file__).resolve().parent


def main() -> int:
    # Our own look everywhere: never let the desktop's Qt style restyle the controls.
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Ambience")
    app.setDesktopFileName("ambience")
    signal.signal(signal.SIGINT, signal.SIG_DFL)

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
    rc = app.exec()
    backend.sync.shutdown()   # stop streaming → the lights are handed back before we exit
    del engine          # tear the screens down while `backend` still exists
    backend.state and backend.state.stop()
    return rc


if __name__ == "__main__":
    sys.exit(main())
