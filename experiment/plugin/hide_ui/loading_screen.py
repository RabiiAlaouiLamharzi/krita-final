"""Full-screen loading overlay while the study UI is prepared."""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from .experiment import _WINDOW_FLAGS, suppress_krita_ui


class LoadingWindow(QWidget):
    """Standalone loading overlay; keeps Krita hidden until dismissed."""

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("Loading")
        self.setWindowFlags(_WINDOW_FLAGS)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #e0e0e0; }
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
        lay.addWidget(self._bar)
        self._guard = None

    def _center(self):
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.setFixedWidth(min(420, geo.width() - 80))
            self.adjustSize()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2)

    def show_loading(self):
        if self._guard is None:
            self._guard = QTimer()
            self._guard.setInterval(100)
            self._guard.timeout.connect(lambda: suppress_krita_ui(self))
        self._guard.start()
        suppress_krita_ui(self)
        self._center()
        self.show()
        self.raise_()
        self.activateWindow()
        # Force an immediate paint before any heavy setup runs on the same tick.
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def set_progress(self, percent, message=None):
        self._bar.setValue(max(0, min(100, int(percent))))
        if message:
            self._status.setText(message)

    def dismiss(self):
        if self._guard is not None:
            self._guard.stop()
        self.hide()
