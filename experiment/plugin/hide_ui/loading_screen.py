"""Full-screen loading overlay while learning/recall UI is prepared."""

from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from .experiment import suppress_krita_ui

_FULLSCREEN_FLAGS = (
    Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)


class LoadingWindow(QWidget):
    """Full-screen opaque cover for learning/recall prep (not breaks)."""

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("Loading")
        self.setWindowFlags(_FULLSCREEN_FLAGS)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setObjectName("hideuiLoadingRoot")
        self.setStyleSheet("""
            QWidget#hideuiLoadingRoot {
                background-color: #2b2b2b; color: #e0e0e0;
            }
            QProgressBar {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: #e0e0e0;
                min-height: 14px;
                max-height: 14px;
            }
            QProgressBar::chunk {
                background-color: #4a6fa5;
                border-radius: 3px;
            }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(16)
        lay.addStretch(1)
        self._title = QLabel("Loading workspace")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet("font-size: 18px; font-weight: bold;")
        lay.addWidget(self._title)
        self._status = QLabel("Starting…")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("font-size: 13px; color: #bbbbbb;")
        lay.addWidget(self._status)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setMaximumWidth(420)
        bar_row = QVBoxLayout()
        bar_row.setAlignment(Qt.AlignHCenter)
        bar_row.addWidget(self._bar)
        lay.addLayout(bar_row)
        lay.addStretch(1)
        self._guard = None
        self._raise_only = False

    def _virtual_desktop_geometry(self):
        geo = QRect()
        for screen in QApplication.screens() or []:
            geo = geo.united(screen.geometry())
        if geo.isNull():
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.geometry()
        return geo

    def _apply_fullscreen(self):
        if self.windowFlags() != _FULLSCREEN_FLAGS:
            self.setWindowFlags(_FULLSCREEN_FLAGS)
        geo = self._virtual_desktop_geometry()
        if not geo.isNull():
            self.setGeometry(geo)

    def _on_guard(self):
        if not self.isVisible():
            return
        if self._raise_only:
            # Keep cover on top without hiding Krita underneath.
            self.show()
            self.raise_()
            return
        suppress_krita_ui(self)
        self.raise_()

    def show_loading(self, raise_only=False):
        self._raise_only = bool(raise_only)
        if self._guard is None:
            self._guard = QTimer()
            self._guard.setInterval(50)
            self._guard.timeout.connect(self._on_guard)
        self._guard.start()
        self._apply_fullscreen()
        self._on_guard()
        self.show()
        self.raise_()
        self.activateWindow()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def set_progress(self, percent, message=None, title=None):
        self._bar.setValue(max(0, min(100, int(percent))))
        if message:
            self._status.setText(message)
        if title:
            self._title.setText(title)

    def dismiss(self):
        if self._guard is not None:
            self._guard.stop()
        self._raise_only = False
        self.hide()
