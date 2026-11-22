"""The notation IDE in a real window.

The family stack is Rust to wasm, three.js for the visual notation, and Qt6 for the window
that holds it. This file is the window: a top level QMainWindow with its own title bar,
status bar and geometry memory, hosting the same page the server serves at 127.0.0.1:5177.

    python window.py                 # open the window
    python window.py --grab shot.png # open, wait for the scene, save a picture, quit

The window owns the Node server: it starts one when the port is closed and stops only the
process it started.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView

HERE = Path(__file__).resolve().parent
PORT = 5177
GEOMETRY = HERE / "data" / "window.json"


def port_open(port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


class NotationWindow(QMainWindow):
    def __init__(self, server: subprocess.Popen | None, grab: str | None, wait_ms: int) -> None:
        super().__init__()
        self.server = server
        self.grab_target = grab
        self.setWindowTitle("Notation IDE — the crudity gap")
        self.resize(1400, 880)
        self.move(30, 30)

        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)

        self.state = QLabel("core: rust to wasm · server 127.0.0.1:%d" % PORT)
        self.statusBar().addWidget(self.state)

        self.view.loadFinished.connect(self.loaded)
        self.view.setUrl(QUrl(f"http://127.0.0.1:{PORT}/"))
        self.wait_ms = wait_ms
        self.restore()

    def restore(self) -> None:
        if not GEOMETRY.exists():
            return
        try:
            box = json.loads(GEOMETRY.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.setGeometry(int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"]))

    def loaded(self, ok: bool) -> None:
        self.state.setText("page loaded" if ok else "page failed to load")
        if self.grab_target:
            QTimer.singleShot(self.wait_ms, self.grab_and_quit)

    def grab_and_quit(self) -> None:
        # Two false captures came from the window not being in front: grabWindow(winId) returned
        # the foreground app, and a desktop region did the same. The window goes on top, and the
        # picture is taken a moment later.
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.setActiveWindow(self)
        QTimer.singleShot(900, self.capture)

    def capture(self) -> None:
        rect = self.frameGeometry()
        shot = self.screen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        if shot.isNull():
            self.state.setText("grab returned nothing")
        else:
            shot.save(self.grab_target)
            self.state.setText(f"saved {self.grab_target}")
        QTimer.singleShot(120, self.close)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt names this
        GEOMETRY.parent.mkdir(parents=True, exist_ok=True)
        box = self.geometry()
        GEOMETRY.write_text(
            json.dumps({"x": box.x(), "y": box.y(), "w": box.width(), "h": box.height()}),
            encoding="utf-8",
        )
        if self.server is not None and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.server.kill()
        super().closeEvent(event)


def ensure_server() -> subprocess.Popen | None:
    if port_open():
        return None
    node = subprocess.Popen(
        ["node", "server.js"],
        cwd=str(HERE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if port_open():
            return node
        time.sleep(0.15)
    node.terminate()
    raise SystemExit("the notation server did not start")


def main() -> int:
    parser = argparse.ArgumentParser(description="Notation IDE window")
    parser.add_argument("--grab", help="save a picture of the window and quit")
    parser.add_argument("--wait", type=int, default=4200, help="milliseconds to wait before the grab")
    args = parser.parse_args()

    server = ensure_server()
    app = QApplication(sys.argv[:1])
    window = NotationWindow(server, args.grab, args.wait)
    window.show()
    if args.grab:
        QTimer.singleShot(15000, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
