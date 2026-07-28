"""Tutorial intro / hold screens for Session 1 and Session 2."""

import random
import traceback

from PyQt5.QtCore import Qt, QTimer, QRectF, QEventLoop
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QApplication,
    QSizePolicy, QMessageBox)

from .experiment import GatewayWindow, suppress_krita_ui, _log

TUTORIAL_LEARN_SEC = 600        # 10 min — Session 1 tutorials 2–3, all Session 2 tutorials
TUTORIAL_PRACTICE_SEC = 900     # 15 min — Session 1 practice trial only
BREAK_SEC = 120                 # 2 min break between blocks
TUTORIAL_1_TIME_SEC = TUTORIAL_PRACTICE_SEC
TUTORIAL_2_TIME_SEC = TUTORIAL_LEARN_SEC
TUTORIAL_3_TIME_SEC = TUTORIAL_LEARN_SEC
TUTORIAL_TIME_SEC = TUTORIAL_1_TIME_SEC

BREAK_MESSAGE = {
    "title": "Break",
    "body": (
        "This is a 2-minute break. You can either take this time to rest or "
        "click Continue immediately to start the next learning tutorial."),
}

BREAK_MESSAGE_SESSION2_FINAL = {
    "title": "Break",
    "body": (
        "This is a 2-minute break. You can either take this time to rest or "
        "click Continue immediately to complete a short survey consisting of "
        "two questions. This will be the final activity you need to complete "
        "for this study!"),
}


def session2_tutorial_count(condition):
    """Session 2 has three learning–recall blocks for all conditions (A, B, C)."""
    del condition
    return 3


def learning_skip_password(condition, session, learn_num):
    """One skip password per session — all learning tutorials in that session."""
    del condition, learn_num
    from .experiment import get_skip_learning_password
    return get_skip_learning_password(session)


def break_skip_password(condition, session, learn_num):
    """Same password as learning skip for this session."""
    return learning_skip_password(condition, session, learn_num)


def recall_skip_password(condition, session, learn_num):
    """One skip password per session — all recall blocks in that session."""
    del condition, learn_num
    from .experiment import get_skip_recall_password
    return get_skip_recall_password(session)


def _tutorial_time_label(seconds):
    if seconds % 60 == 0 and seconds >= 60:
        mins = seconds // 60
        return "%d minute%s" % (mins, "" if mins == 1 else "s")
    return "%d second%s" % (seconds, "" if seconds == 1 else "s")


def _learn_task_paragraph():
    return (
        "The task involves recreating a simple drawing in Krita, but you do "
        "not need to be a perfectionist. Just make sure to follow the "
        "step-by-step process as accurately as possible.")


def _learn_intro_body(seconds, start_paragraph, include_workspace_intro=False):
    parts = [
        start_paragraph + " Follow the step-by-step instructions displayed on "
        "the right. You will have %s to complete the tutorial once the canvas "
        "opens." % _tutorial_time_label(seconds),
        _learn_task_paragraph(),
    ]
    if include_workspace_intro:
        parts.append(
            "Before starting Tutorial 1, you will first see a short "
            "introduction to the Krita workspace.")
    return "\n\n".join(parts)


def _session_learning_start_paragraph(session_num, tutorial_index):
    ordinals = ("first", "second", "third")
    idx = max(1, min(3, int(tutorial_index))) - 1
    return (
        "Session %d includes three learning tutorials in total. You will now "
        "start the %s learning tutorial."
        % (max(1, int(session_num)), ordinals[idx]))


def session1_learning_intro_body(tutorial_index):
    idx = max(1, min(3, int(tutorial_index)))
    start = _session_learning_start_paragraph(1, idx)
    seconds = TUTORIAL_PRACTICE_SEC if idx == 1 else TUTORIAL_LEARN_SEC
    return _learn_intro_body(
        seconds, start, include_workspace_intro=(idx == 1))


def session2_learning_intro_body(tutorial_index):
    idx = max(1, min(3, int(tutorial_index)))
    start = _session_learning_start_paragraph(2, idx)
    return _learn_intro_body(TUTORIAL_LEARN_SEC, start)


def learning_intro_body_for_session(session_num, tutorial_index):
    if int(session_num) == 2:
        return session2_learning_intro_body(tutorial_index)
    return session1_learning_intro_body(tutorial_index)


_RECALL_AFTER_INTRO = (
    "where you will be asked to identify the positions of a set of commands "
    "you used during the tutorial. This will help us assess whether you "
    "remember their locations.")


TUTORIAL_1 = {
    "title": "Tutorial 1: Practice trial",
    "body": session1_learning_intro_body(1),
    "logged": True,
    "learn_sec": TUTORIAL_PRACTICE_SEC,
}

TUTORIAL_2 = {
    "title": "Learning Tutorial 2",
    "body": session1_learning_intro_body(2),
    "logged": True,
    "learn_sec": TUTORIAL_LEARN_SEC,
}

TUTORIAL_3 = {
    "title": "Learning Tutorial 3",
    "body": session1_learning_intro_body(3),
    "logged": True,
    "learn_sec": TUTORIAL_LEARN_SEC,
}

SESSION_1_TUTORIALS = (TUTORIAL_1, TUTORIAL_2, TUTORIAL_3)

STUDY_PRESENTATION = (
    "Krita is a professional painting program used by thousands of artists worldwide. "
    "This study uses a simplified interface to help you learn key commands and panels "
    "without the complexity of the full program.\n\n"
    "Click Next to explore each panel and its associated commands. "
    "Click Finish on the last screen to proceed with the study.")

SESSION_2_OPENING_RECALL = {
    "title": "Recall: Layout A",
    "body": (
        "Before introducing the new tutorials, you will begin Session 2 with a "
        "recall test to assess whether you still remember the positions of the "
        "commands you learned in Session 1."),
}

SESSION_2_TUTORIAL = {
    "title": "Learning Tutorial %d",
    "logged": True,
    "learn_sec": TUTORIAL_LEARN_SEC,
}

HOLD_AFTER_TUTORIAL = {
    1: {
        "title": "Tutorial 1 complete",
        "body": (
            "Nice work. When you press Continue, you will take a practice "
            "recall test %s After the recall test, Learning Tutorial 2 will "
            "begin." % _RECALL_AFTER_INTRO),
    },
    2: {
        "title": "Tutorial 2 complete",
        "body": (
            "Nice work. When you press Continue, you will take a recall test "
            "%s After the recall test, Learning Tutorial 3 will begin."
            % _RECALL_AFTER_INTRO),
    },
    3: {
        "title": "Tutorial 3 complete",
        "body": (
            "Nice work. When you press Continue, you will take a recall test "
            "%s After the recall test, Session 1 will end."
            % _RECALL_AFTER_INTRO),
    },
}

HOLD_SESSION2_AFTER_TUTORIAL = {
    1: {
        "title": "Tutorial 1 complete",
        "body": (
            "Nice work. When you press Continue, you will take a recall test "
            "%s After the recall test, Learning Tutorial 2 will begin."
            % _RECALL_AFTER_INTRO),
    },
    2: {
        "title": "Tutorial 2 complete",
        "body": (
            "Nice work. When you press Continue, you will take a recall test "
            "%s After the recall test, Learning Tutorial 3 will begin."
            % _RECALL_AFTER_INTRO),
    },
    3: {
        "title": "Tutorial 3 complete",
        "body": (
            "Nice work. When you press Continue, you will take a recall test "
            "%s After the recall test, you will complete a short survey, "
            "then a break, then the final survey."
            % _RECALL_AFTER_INTRO),
    },
}


class TutorialIntroWindow(GatewayWindow):
    """Full-screen gateway before each timed tutorial block."""

    def __init__(self, title, body):
        super().__init__(title)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        heading.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: bold; padding: 0 12px;")
        heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        continue_btn = QPushButton("Continue")
        continue_btn.setDefault(True)
        continue_btn.clicked.connect(lambda: self._finish(True))

        inner = QWidget()
        inner.setMinimumWidth(480)
        inner.setMaximumWidth(560)
        lay = QVBoxLayout(inner)
        lay.setSpacing(10)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.addWidget(heading)
        lay.addSpacing(8)

        for para in body.strip().split("\n\n"):
            text = para.strip()
            if not text:
                continue
            desc = QLabel(text)
            desc.setWordWrap(True)
            desc.setAlignment(Qt.AlignCenter)
            desc.setStyleSheet(
                "color: #f2f2f2; font-size: 15px; padding: 4px 12px;")
            desc.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            lay.addWidget(desc)

        lay.addSpacing(20)
        lay.addWidget(continue_btn, alignment=Qt.AlignCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.addStretch(1)
        outer.addWidget(inner, 0, Qt.AlignCenter)
        outer.addStretch(1)

        inner.adjustSize()
        self.adjustSize()
        self.setMinimumSize(560, max(360, inner.sizeHint().height() + 140))


def run_tutorial_intro(title, body):
    """Show intro window; return True when the participant continues."""
    try:
        win = TutorialIntroWindow(title, body)
        suppress_krita_ui(win)
        return win.run_blocking() is True
    except Exception:
        _log(traceback.format_exc())
        return False


def run_hold_screen(title, body):
    """Transition screen between tutorial blocks."""
    return run_tutorial_intro(title, body)


def _format_countdown(seconds_left):
    sec = max(0, int(seconds_left))
    minutes, seconds = divmod(sec, 60)
    return "%d:%02d" % (minutes, seconds)


class TimedBreakWindow(GatewayWindow):
    """Standalone break screen with countdown; Krita stays hidden."""

    def __init__(self, title, body, duration_sec, allow_skip=False):
        super().__init__(title)
        self._remaining = max(1, int(duration_sec))
        self._end_reason = "complete"
        self._allow_skip = bool(allow_skip)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)

        heading = QLabel(title)
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet(
            "color: #ffffff; font-size: 24px; font-weight: bold; padding: 0 12px;")

        self._timer_label = QLabel(_format_countdown(self._remaining))
        self._timer_label.setAlignment(Qt.AlignCenter)
        self._timer_label.setStyleSheet(
            "color: #ffffff; font-size: 64px; font-weight: bold; padding: 12px;")

        inner = QWidget()
        inner.setMinimumWidth(480)
        inner.setMaximumWidth(560)
        lay = QVBoxLayout(inner)
        lay.setSpacing(12)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.addWidget(heading)
        lay.addSpacing(8)
        for para in body.strip().split("\n\n"):
            text = para.strip()
            if not text:
                continue
            desc = QLabel(text)
            desc.setWordWrap(True)
            desc.setAlignment(Qt.AlignCenter)
            desc.setStyleSheet(
                "color: #f2f2f2; font-size: 15px; padding: 4px 12px;")
            lay.addWidget(desc)
        lay.addSpacing(16)
        lay.addWidget(self._timer_label)

        footer = QHBoxLayout()
        footer.addStretch(1)
        if self._allow_skip:
            skip_btn = QPushButton("Skip break")
            skip_btn.setObjectName("quitBtn")
            skip_btn.clicked.connect(self._try_skip)
            footer.addWidget(skip_btn)
        lay.addLayout(footer)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.addStretch(1)
        outer.addWidget(inner, 0, Qt.AlignCenter)
        outer.addStretch(1)

        inner.adjustSize()
        self.adjustSize()
        self.setMinimumSize(560, max(360, inner.sizeHint().height() + 140))

    def _try_skip(self):
        if not self._allow_skip:
            return
        answer = QMessageBox.question(
            self,
            "Skip break",
            "Are you sure you want to skip this break?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        _log("break skipped: confirmed")
        self._end_reason = "experimenter_skip"
        self._finish(True)

    def _on_tick(self):
        self._remaining -= 1
        self._timer_label.setText(_format_countdown(self._remaining))
        if self._remaining <= 0:
            self._tick.stop()
            self._finish(True)

    def run_blocking(self):
        loop = QEventLoop()
        self._loop = loop
        guard = QTimer()
        guard.setInterval(100)
        guard.timeout.connect(lambda: suppress_krita_ui(self))
        guard.start()
        self._center_on_screen()
        suppress_krita_ui(self)
        self.show()
        self.raise_()
        self.activateWindow()
        self._tick.start()
        loop.exec_()
        self._tick.stop()
        guard.stop()
        self._loop = None
        return self._result


def run_timed_break(allow_skip=False, body=None):
    """Show timed break window. Returns (finished_ok, end_reason)."""
    break_body = body if body is not None else BREAK_MESSAGE["body"]
    try:
        win = TimedBreakWindow(
            BREAK_MESSAGE["title"],
            break_body,
            BREAK_SEC,
            allow_skip=allow_skip)
        suppress_krita_ui(win)
        if win.run_blocking() is not True:
            return False, ""
        return True, getattr(win, "_end_reason", "complete")
    except Exception:
        _log(traceback.format_exc())
        return False, ""


class RecallScoreWindow(GatewayWindow):
    """Brief encouragement after recall; no score shown to the participant."""

    def __init__(self, percent=None):
        super().__init__("Recall complete")
        _ = percent  # logged elsewhere; not shown in the UI

        heading = QLabel("Good job!")
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        heading.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: bold; padding: 0 12px;")

        message = QLabel(
            "Thank you for completing this recall task. "
            "Click Continue when you are ready to proceed.")
        message.setAlignment(Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet("color: #f2f2f2; font-size: 16px; padding: 8px 12px;")

        continue_btn = QPushButton("Continue")
        continue_btn.setDefault(True)
        continue_btn.clicked.connect(lambda: self._finish(True))

        inner = QWidget()
        inner.setMinimumWidth(480)
        inner.setMaximumWidth(560)
        lay = QVBoxLayout(inner)
        lay.setSpacing(10)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.addWidget(heading)
        lay.addWidget(message)
        lay.addSpacing(24)
        lay.addWidget(continue_btn, alignment=Qt.AlignCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.addStretch(1)
        outer.addWidget(inner, 0, Qt.AlignCenter)
        outer.addStretch(1)

        inner.adjustSize()
        self.adjustSize()
        self.setMinimumSize(560, max(360, inner.sizeHint().height() + 140))


def run_recall_score_screen(percent):
    """Show post-recall encouragement; return True when the participant continues."""
    try:
        win = RecallScoreWindow(percent)
        suppress_krita_ui(win)
        return win.run_blocking() is True
    except Exception:
        _log(traceback.format_exc())
        return False


CONFETTI_COLORS = (
    "#f44336", "#e91e63", "#9c27b0", "#673ab7", "#2196f3",
    "#03a9f4", "#4caf50", "#8bc34a", "#ffeb3b", "#ff9800", "#00bcd4",
)


class _ConfettiOverlay(QWidget):
    """Animated confetti layer for session-complete screens."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._particles = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start_burst(self, count=140):
        self._particles = []
        w = max(self.width(), 480)
        for _ in range(count):
            self._particles.append({
                "x": random.uniform(0, w),
                "y": random.uniform(-self.height() * 0.4, -8),
                "vx": random.uniform(-2.8, 2.8),
                "vy": random.uniform(2.5, 8.5),
                "w": random.uniform(6, 13),
                "h": random.uniform(4, 11),
                "rot": random.uniform(0, 360),
                "vr": random.uniform(-10, 10),
                "color": random.choice(CONFETTI_COLORS),
            })
        if not self._timer.isActive():
            self._timer.start(33)

    def _tick(self):
        gravity = 0.18
        h = self.height()
        alive = []
        for part in self._particles:
            part["vy"] += gravity
            part["x"] += part["vx"]
            part["y"] += part["vy"]
            part["rot"] += part["vr"]
            if part["y"] < h + 50:
                alive.append(part)
        self._particles = alive
        self.update()
        if not alive:
            self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for part in self._particles:
            painter.save()
            painter.translate(part["x"], part["y"])
            painter.rotate(part["rot"])
            painter.fillRect(
                QRectF(-part["w"] / 2, -part["h"] / 2, part["w"], part["h"]),
                QColor(part["color"]))
            painter.restore()


class SessionCompleteWindow(GatewayWindow):
    """Celebration screen shown when a session finishes."""

    def __init__(self, session_num):
        super().__init__("Session %d complete" % session_num)
        self._confetti = _ConfettiOverlay(self)

        heading = QLabel("Session %d completed!" % session_num)
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        heading.setStyleSheet(
            "color: #ffffff; font-size: 28px; font-weight: bold; padding: 0 12px;")
        heading.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        sub = QLabel("Thank you for taking part.")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #f2f2f2; font-size: 16px; padding: 8px 12px;")

        continue_btn = QPushButton("Continue")
        continue_btn.setDefault(True)
        continue_btn.clicked.connect(lambda: self._finish(True))

        inner = QWidget()
        inner.setMinimumWidth(480)
        inner.setMaximumWidth(560)
        lay = QVBoxLayout(inner)
        lay.setSpacing(12)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.addWidget(heading)
        lay.addWidget(sub)
        lay.addSpacing(24)
        lay.addWidget(continue_btn, alignment=Qt.AlignCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.addStretch(1)
        outer.addWidget(inner, 0, Qt.AlignCenter)
        outer.addStretch(1)

        inner.adjustSize()
        self.adjustSize()
        self.setMinimumSize(560, max(360, inner.sizeHint().height() + 140))
        self._content = inner

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._confetti.setGeometry(self.rect())
        if self._content is not None:
            self._content.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._confetti.setGeometry(self.rect())
        self._confetti.start_burst(160)
        self._confetti.lower()
        if self._content is not None:
            self._content.raise_()


def run_session_complete(session_num):
    """Show session-complete celebration; return True when the participant continues."""
    try:
        win = SessionCompleteWindow(session_num)
        suppress_krita_ui(win)
        return win.run_blocking() is True
    except Exception:
        _log(traceback.format_exc())
        return False
