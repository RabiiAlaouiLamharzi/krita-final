"""Experiment gateway shown before Krita becomes usable.

Login and consent are full standalone windows (not dialog popups). Krita stays
completely hidden until the participant finishes every required step.
"""

import os
import json
import hashlib
import datetime
import traceback

from PyQt5.QtCore import Qt, QEventLoop, QTimer
from PyQt5.QtWidgets import (
    QLabel, QLineEdit, QComboBox, QPushButton, QVBoxLayout,
    QHBoxLayout, QFormLayout, QWidget, QTextEdit,
    QApplication, QScrollArea)

from .ui_controls import WhiteDotToggle

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_base_dir():
    """Participant CSV logs live under experiment/participant_data/."""
    pointer = os.path.join(PLUGIN_DIR, "data_root.txt")
    if os.path.isfile(pointer):
        with open(pointer) as f:
            path = f.read().strip()
            if path:
                return os.path.abspath(os.path.expanduser(path))
    repo_data = os.path.abspath(
        os.path.join(PLUGIN_DIR, "..", "..", "participant_data"))
    if os.path.isdir(os.path.join(os.path.dirname(repo_data), "plugin")):
        return repo_data
    return os.path.abspath(os.path.expanduser(
        "~/Desktop/untitled folder 24/experiment/participant_data"))


BASE_DIR = _resolve_base_dir()
PASSWORDS_FILE = os.path.join(PLUGIN_DIR, "passwords.json")
CONSENT_FILE = os.path.join(PLUGIN_DIR, "consent.txt")
LOG = os.path.expanduser("~/krita_hide_ui_log.txt")

CONDITIONS = ["A", "B", "C"]
# Valid sessions per condition (password = condition + session, e.g. A1, B4).
CONDITION_SESSIONS = {
    "A": ["1", "2"],
    "B": ["1", "2"],
    "C": ["1", "2"],
}

# Standalone window on top of everything (incl. Krita splash).
_WINDOW_FLAGS = (
    Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint
    | Qt.WindowStaysOnTopHint
)

# Krita top-level windows that must stay hidden during the gateway.
_KRITA_TOPLEVEL = ("KisSplashScreen", "KisMainWindow")


def _log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def suppress_krita_ui(keep=None):
    """Hide Krita splash/main windows so the gateway is never covered."""
    try:
        for w in QApplication.topLevelWidgets():
            if w is keep:
                continue
            cls = w.metaObject().className()
            if cls in _KRITA_TOPLEVEL:
                w.hide()
                w.lower()
    except Exception:
        _log(traceback.format_exc())


def restore_krita_ui(qwin=None):
    """Ensure the main Krita window is visible after gateway / intro screens."""
    try:
        for w in QApplication.topLevelWidgets():
            if qwin is not None and w is not qwin:
                continue
            if w.metaObject().className() == "KisMainWindow":
                w.show()
                w.raise_()
                w.activateWindow()
                return True
    except Exception:
        _log(traceback.format_exc())
    return False


def _default_passwords_plain():
    plain = {}
    for c, sessions in CONDITION_SESSIONS.items():
        for s in sessions:
            plain["%s-%s" % (s, c)] = "%s%s" % (c, s)
    return plain


def _expected_password_keys():
    return set(_default_passwords_plain().keys())


def load_password_hashes():
    expected = _expected_password_keys()
    try:
        if os.path.exists(PASSWORDS_FILE):
            with open(PASSWORDS_FILE) as f:
                stored = json.load(f)
            if set(stored.keys()) == expected:
                return stored
    except Exception:
        _log(traceback.format_exc())
    plain = _default_passwords_plain()
    hashed = {k: _hash(v) for k, v in plain.items()}
    try:
        with open(PASSWORDS_FILE, "w") as f:
            json.dump(hashed, f, indent=2, sort_keys=True)
        _log("passwords.json updated: " + ", ".join(sorted(plain.values())))
    except Exception:
        _log(traceback.format_exc())
    return hashed


DEFAULT_CONSENT = (
    "You are invited to take part in a research study on how people learn "
    "tools and buttons in a drawing program. The study is conducted by the "
    "Loop team (Inria Center at the University of Lille).\n\n"
    "The study has two online sessions. Each session lasts about 60 minutes. "
    "The sessions take place roughly 48 hours apart.\n\n"
    "The sessions are conducted remotely. You will share your screen with "
    "the experimenter. The experimenter will guide you through the steps, "
    "answer questions about the procedure, and help if something on screen "
    "looks unexpected.\n\n"
    "In each session, you will use a simplified version of the \"Krita\" "
    "drawing program on your computer. First, you will complete short guided "
    "tasks to learn a set of tools and panels. Then, these commands will be "
    "hidden behind white boxes, and you will be asked to locate and click "
    "them as quickly and accurately as possible. This allows us to measure "
    "your spatial memory and how well you remember the location of Krita "
    "commands.\n\n"
    "In Session 2, we will modify the Krita interface layout. This change "
    "is a key part of the study, as we intend to understand how you adapt "
    "to new interface arrangements.\n\n"
    "During the experiment, we will collect quantitative interaction data, "
    "including task completion times, clicks, and response accuracy. You may "
    "also be asked to complete short surveys, including both open-ended "
    "questions and Likert-scale items. We will record this qualitative "
    "feedback as well. No sensitive, medical, or financial information will "
    "be collected.\n\n"
    "Participation is voluntary and unpaid. You may stop at any time without "
    "giving a reason and without any negative consequence. If you decide to "
    "stop, please tell the experimenter. You can also ask questions about the "
    "study before you agree to take part.\n\n"
    "By agreeing below, you confirm that you have read and understood this "
    "information and that you agree to participate under the conditions "
    "described here.\n"
)


def load_consent():
    try:
        if os.path.exists(CONSENT_FILE):
            with open(CONSENT_FILE) as f:
                return f.read()
    except Exception:
        _log(traceback.format_exc())
    try:
        with open(CONSENT_FILE, "w") as f:
            f.write(DEFAULT_CONSENT)
    except Exception:
        _log(traceback.format_exc())
    return DEFAULT_CONSENT


class GatewayWindow(QWidget):
    """Base for unskippable standalone gateway windows."""

    def __init__(self, title):
        super().__init__(None)
        self.setWindowTitle(title)
        self.setWindowFlags(_WINDOW_FLAGS)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._loop = None
        self._result = None

        self.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #e0e0e0; }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #3c3c3c; color: #e0e0e0;
                border: 1px solid #555; padding: 4px;
            }
            QPushButton {
                background-color: #4a6fa5; color: white;
                border: none; padding: 8px 20px; min-width: 90px;
            }
            QPushButton:hover { background-color: #5a7fb5; }
            QPushButton:disabled {
                background-color: #444; color: #888;
            }
            QPushButton#quitBtn {
                background-color: #555; color: #e0e0e0;
            }
            QPushButton#quitBtn:hover { background-color: #666; }
        """)

    def _finish(self, result):
        self._result = result
        self.hide()
        if self._loop is not None:
            self._loop.quit()

    def closeEvent(self, event):
        # No close button, but handle platform shortcuts (Cmd+W etc.).
        self._finish(None)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def _center_on_screen(self):
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2)

    def run_blocking(self):
        """Show this window and block until _finish() is called."""
        loop = QEventLoop()
        self._loop = loop

        # Keep Krita splash/main hidden while this window is open.
        guard = QTimer()
        guard.setInterval(100)
        guard.timeout.connect(lambda: suppress_krita_ui(self))
        guard.start()

        self._center_on_screen()
        suppress_krita_ui(self)
        self.show()
        self.raise_()
        self.activateWindow()
        loop.exec_()

        guard.stop()
        self._loop = None
        return self._result


class ConsentWindow(GatewayWindow):

    def __init__(self, consent_text):
        super().__init__("Consent Form")
        self._read_to_end = False

        notice = QLabel(
            "Please scroll through the information below before you can agree.")
        notice.setAlignment(Qt.AlignCenter)
        notice.setWordWrap(True)
        notice.setStyleSheet("color:#aaa;")

        body = QLabel(consent_text.strip())
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        body.setStyleSheet(
            "color: #e0e0e0; font-size: 14px; background: transparent;"
            " padding: 12px 14px; line-height: 1.4;")
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._rules_scroll = QScrollArea()
        self._rules_scroll.setWidget(body)
        self._rules_scroll.setWidgetResizable(True)
        self._rules_scroll.setFixedHeight(300)
        self._rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rules_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #555; background: #3c3c3c; }"
            " QScrollArea > QWidget > QWidget { background: #3c3c3c; }")

        self.agree = WhiteDotToggle()
        self.agree.setEnabled(False)
        agree_text = QLabel(
            "I have read and understood the above and I agree to participate.")
        agree_text.setWordWrap(True)
        agree_text.setStyleSheet("color: #888;")
        self._agree_text = agree_text

        agree_row = QHBoxLayout()
        agree_row.setContentsMargins(0, 0, 0, 0)
        agree_row.addWidget(self.agree, alignment=Qt.AlignTop)
        agree_row.addWidget(agree_text, stretch=1)

        agree_widget = QWidget()
        agree_lay = QVBoxLayout(agree_widget)
        agree_lay.setContentsMargins(0, 12, 0, 12)
        agree_lay.addLayout(agree_row)

        self.msg = QLabel(
            "Scroll to the end of the text to unlock the agreement.")
        self.msg.setStyleSheet("color:#aaa;")
        self.msg.setWordWrap(True)
        self.msg.setAlignment(Qt.AlignCenter)

        self.submitBtn = QPushButton("Continue")
        self.submitBtn.setDefault(True)
        self.submitBtn.setEnabled(False)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.submitBtn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(0)
        lay.addWidget(notice)
        lay.addSpacing(12)
        lay.addWidget(self._rules_scroll)
        lay.addWidget(agree_widget)
        lay.addWidget(self.msg)
        lay.addSpacing(8)
        lay.addLayout(btns)

        self.setMinimumSize(700, 520)

        self._rules_scroll.verticalScrollBar().valueChanged.connect(
            self._on_consent_scroll)
        self.agree.toggled.connect(self._on_agree_toggled)
        self.submitBtn.clicked.connect(self._submit)
        QTimer.singleShot(0, self._check_consent_scroll)

    def _on_consent_scroll(self, _value=None):
        self._check_consent_scroll()

    def _check_consent_scroll(self):
        bar = self._rules_scroll.verticalScrollBar()
        if bar.maximum() <= 0:
            # Short text fits without scrolling — treat as fully read.
            at_end = True
        else:
            at_end = bar.value() >= max(0, bar.maximum() - 4)
        if at_end and not self._read_to_end:
            self._read_to_end = True
            self.agree.setEnabled(True)
            self._agree_text.setStyleSheet("color: #e0e0e0;")
            self.msg.setText("")
            self.msg.setStyleSheet("color:#e06c6c;")
            self._on_agree_toggled(self.agree.isChecked())

    def _on_agree_toggled(self, checked):
        self.submitBtn.setEnabled(bool(self._read_to_end and checked))

    def _submit(self):
        if not self._read_to_end:
            self.msg.setText(
                "Please scroll to the end of the text before continuing.")
            return
        if not self.agree.isChecked():
            self.msg.setText("You must check the agreement box to continue.")
            return
        self._finish(True)


class LoginWindow(GatewayWindow):

    def __init__(self, password_hashes):
        super().__init__("Experiment Login")
        self._hashes = password_hashes

        title = QLabel("Software Learning Study")
        f = title.font()
        f.setPointSize(20)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(
            "Please enter your details to begin.\n"
            "You cannot use the software until this step is completed.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#aaa;")

        self.pid = QLineEdit()
        self.pid.setPlaceholderText("e.g. P07")
        self.condition = QComboBox()
        self.condition.addItems(CONDITIONS)
        self.session = QComboBox()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Provided by the experimenter")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Participant ID:", self.pid)
        form.addRow("Condition:", self.condition)
        form.addRow("Session:", self.session)
        form.addRow("Password:", self.password)

        self._update_sessions()
        self.condition.currentIndexChanged.connect(self._update_sessions)

        self.msg = QLabel("")
        self.msg.setStyleSheet("color:#e06c6c;")
        self.msg.setWordWrap(True)
        self.msg.setAlignment(Qt.AlignCenter)

        self.startBtn = QPushButton("Start")
        self.startBtn.setDefault(True)
        self.quitBtn = QPushButton("Quit")
        self.quitBtn.setObjectName("quitBtn")
        btns = QHBoxLayout()
        btns.addWidget(self.quitBtn)
        btns.addStretch()
        btns.addWidget(self.startBtn)

        inner = QWidget()
        inner.setMaximumWidth(480)
        inner_lay = QVBoxLayout(inner)
        inner_lay.addWidget(title)
        inner_lay.addWidget(subtitle)
        inner_lay.addSpacing(16)
        inner_lay.addLayout(form)
        inner_lay.addWidget(self.msg)
        inner_lay.addSpacing(8)
        inner_lay.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.addStretch()
        outer.addWidget(inner, alignment=Qt.AlignCenter)
        outer.addStretch()

        self.setMinimumSize(560, 420)

        self.startBtn.clicked.connect(self._try_start)
        self.quitBtn.clicked.connect(lambda: self._finish(None))
        self.password.returnPressed.connect(self._try_start)

    def _update_sessions(self):
        c = self.condition.currentText()
        sessions = CONDITION_SESSIONS.get(c, [])
        self.session.blockSignals(True)
        self.session.clear()
        self.session.addItems(sessions)
        self.session.blockSignals(False)

    def _try_start(self):
        pid = self.pid.text().strip()
        if not pid:
            self.msg.setText("Please enter your Participant ID.")
            return
        s = self.session.currentText()
        c = self.condition.currentText()
        key = "%s-%s" % (s, c)
        expected = self._hashes.get(key)
        if not expected or _hash(self.password.text()) != expected:
            self.msg.setText(
                "Incorrect password for this session/condition.")
            return
        self._finish({
            "participant_id": pid,
            "session": int(s),
            "condition": c,
        })


def _hide_krita(qwin):
    suppress_krita_ui()
    if qwin is not None:
        qwin.hide()
        qwin.lower()


def _show_krita(qwin):
    if qwin is not None:
        qwin.show()
        qwin.raise_()
        qwin.activateWindow()


def run_gateway(qwin):
    """Run login. Krita stays hidden the whole time.
    Returns session info on success, or None if the participant quit."""
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
        _hide_krita(qwin)

        hashes = load_password_hashes()
        info = LoginWindow(hashes).run_blocking()
        if info is None:
            return None
        _log("login ok: %s" % info)

        info["started_at"] = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        _log("gateway completed: %s" % info)
        return info
    except Exception:
        _log(traceback.format_exc())
        return None
