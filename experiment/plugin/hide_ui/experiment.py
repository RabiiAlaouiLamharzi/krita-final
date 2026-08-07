"""Experiment gateway shown before Krita becomes usable.

Login and consent are full standalone windows (not dialog popups). Krita stays
completely hidden until the participant finishes every required step.
"""

import os
import json
import hashlib
import datetime
import traceback
import re

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
PASSWORDS_PLAIN_FILE = os.path.join(PLUGIN_DIR, "passwords_plain.json")
_passwords_config_cache = None
CONSENT_FILE = os.path.join(PLUGIN_DIR, "consent.txt")
LOG = os.path.expanduser("~/krita_hide_ui_log.txt")

CONDITIONS = ["A", "B", "C"]
PARTICIPANT_ID_MIN = 0
PARTICIPANT_ID_MAX = 59
# Valid sessions per condition (password = condition + session, e.g. A1, B4).
CONDITION_SESSIONS = {
    "A": ["1", "2"],
    "B": ["1", "2"],
    "C": ["1", "2"],
}


def normalize_participant_id(text):
    """Return canonical P00–P59 id, or None if invalid."""
    raw = (text or "").strip().upper()
    if not re.match(r"^P\d{1,2}$", raw):
        return None
    num = int(raw[1:], 10)
    if num < PARTICIPANT_ID_MIN or num > PARTICIPANT_ID_MAX:
        return None
    return "P%02d" % num


def condition_for_participant_id(participant_id):
    """Assign A/B/C from participant number (P00–P19 / P20–P39 / P40–P59)."""
    pid = normalize_participant_id(participant_id)
    if pid is None:
        return None
    num = int(pid[1:], 10)
    if num <= 19:
        return "A"
    if num <= 39:
        return "B"
    return "C"

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


def _default_passwords_config():
    """Plain-text passwords — edit passwords_plain.json."""
    import random

    _WORDS_A = (
        "cat", "dog", "moon", "pizza", "turtle", "coffee", "banana", "hot",
        "rocket", "pickle", "penguin", "sun", "fish", "bird", "cake", "tree",
        "star", "boat", "bean", "lion", "frog", "cloud", "mango", "cookie",
    )
    _WORDS_B = (
        "dog", "pie", "time", "shell", "bean", "walk", "house", "fish", "fly",
        "run", "jump", "blue", "red", "gold", "rain", "snow", "wave", "rock",
        "mint", "lime", "berry", "toast", "soup", "noodle",
    )
    used = set()

    def _memorable():
        for _ in range(200):
            w1 = random.choice(_WORDS_A)
            w2 = random.choice(_WORDS_B)
            if w2 == w1:
                continue
            num = random.randint(10, 99)
            if random.random() < 0.15:
                num = random.randint(100, 999)
            pwd = "%s%s%d" % (w1, w2, num)
            if pwd not in used and len(pwd) <= 16:
                used.add(pwd)
                return pwd
        return "catdog69"

    login = {}
    for c, sessions in CONDITION_SESSIONS.items():
        for s in sessions:
            login["%s-%s" % (s, c)] = _memorable()
    return {
        "login": login,
        "skip_learning": {"1": _memorable(), "2": _memorable()},
        "skip_recall": {"1": _memorable(), "2": _memorable()},
    }


def _merge_passwords_config(stored, defaults):
    merged = {
        "login": dict(defaults["login"]),
        "skip_learning": dict(defaults["skip_learning"]),
        "skip_recall": dict(defaults["skip_recall"]),
    }
    for section in merged:
        if isinstance(stored.get(section), dict):
            for key, val in stored[section].items():
                if val is not None and str(val).strip():
                    merged[section][str(key)] = str(val)
    return merged


def _sync_login_password_hashes(login_plain):
    expected = {k: _hash(v) for k, v in login_plain.items()}
    try:
        if os.path.exists(PASSWORDS_FILE):
            with open(PASSWORDS_FILE) as f:
                stored = json.load(f)
            if stored == expected:
                return expected
    except Exception:
        _log(traceback.format_exc())
    try:
        with open(PASSWORDS_FILE, "w") as f:
            json.dump(expected, f, indent=2, sort_keys=True)
        _log("passwords.json synced from passwords_plain.json")
    except Exception:
        _log(traceback.format_exc())
    return expected


def load_passwords_config():
    """Load login + skip passwords from passwords_plain.json (shipped with the pack)."""
    global _passwords_config_cache
    cfg = {"login": {}, "skip_learning": {}, "skip_recall": {}}
    try:
        if os.path.isfile(PASSWORDS_PLAIN_FILE):
            with open(PASSWORDS_PLAIN_FILE) as f:
                stored = json.load(f)
            # Do not invent random fillers — only keep explicit stored values.
            for section in ("login", "skip_learning", "skip_recall"):
                if isinstance(stored.get(section), dict):
                    for key, val in stored[section].items():
                        if val is not None and str(val).strip():
                            cfg[section][str(key)] = str(val)
        else:
            _log("passwords_plain.json missing — using passwords.json only")
    except Exception:
        _log(traceback.format_exc())
    _passwords_config_cache = cfg
    return cfg


def load_password_hashes():
    cfg = load_passwords_config()
    login = cfg.get("login") or {}
    if login:
        return _sync_login_password_hashes(login)
    # No plain passwords available: keep the shipped hashed file as-is.
    try:
        if os.path.exists(PASSWORDS_FILE):
            with open(PASSWORDS_FILE) as f:
                stored = json.load(f)
            if isinstance(stored, dict) and stored:
                return stored
    except Exception:
        _log(traceback.format_exc())
    return {}


def get_skip_learning_password(session):
    cfg = _passwords_config_cache or load_passwords_config()
    return cfg.get("skip_learning", {}).get(str(int(session)), "")


def get_skip_recall_password(session):
    cfg = _passwords_config_cache or load_passwords_config()
    return cfg.get("skip_recall", {}).get(str(int(session)), "")


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
        self.pid.setPlaceholderText("P00–P59 (e.g. P07)")
        self.condition_label = QLabel("—")
        self.condition_label.setStyleSheet("color: #e0e0e0; font-weight: bold;")
        self.session = QComboBox()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Provided by the experimenter")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Participant ID:", self.pid)
        form.addRow("Condition:", self.condition_label)
        form.addRow("Session:", self.session)
        form.addRow("Password:", self.password)

        self._update_sessions()
        self.pid.textChanged.connect(self._on_participant_id_changed)

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

    def _current_condition(self):
        return condition_for_participant_id(self.pid.text())

    def _on_participant_id_changed(self, _text=None):
        cond = self._current_condition()
        if cond:
            self.condition_label.setText(cond)
            self.condition_label.setStyleSheet(
                "color: #e0e0e0; font-weight: bold;")
        else:
            raw = self.pid.text().strip()
            if raw:
                self.condition_label.setText("Invalid ID")
                self.condition_label.setStyleSheet("color: #e06c6c;")
            else:
                self.condition_label.setText("—")
                self.condition_label.setStyleSheet("color: #888;")
        self._update_sessions()

    def _update_sessions(self):
        c = self._current_condition() or "A"
        sessions = CONDITION_SESSIONS.get(c, [])
        self.session.blockSignals(True)
        self.session.clear()
        self.session.addItems(sessions)
        self.session.blockSignals(False)

    def _try_start(self):
        pid = normalize_participant_id(self.pid.text())
        if pid is None:
            self.msg.setText(
                "Participant ID must be P00 through P59 (e.g. P07).")
            return
        c = condition_for_participant_id(pid)
        s = self.session.currentText()
        key = "%s-%s" % (s, c)
        expected = self._hashes.get(key)
        if not expected or _hash(self.password.text()) != expected:
            self.msg.setText(
                "Incorrect password for this session and assigned condition.")
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
