"""Session 2 surveys: short post-recall + final end-of-session."""

import traceback

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea,
    QTextEdit, QButtonGroup, QFrame)

from .experiment import GatewayWindow, suppress_krita_ui, _log
from .ui_controls import WhiteDotToggle

LIKERT_ANCHOR_LOW = "Strongly disagree"
LIKERT_ANCHOR_HIGH = "Strongly agree"

# After each Session 2 learning-block recall (not opening recall).
POST_RECALL_LIKERT = [
    {
        "id": "recall_difficulty",
        "text": "It was difficult to recall where commands were located.",
    },
    {
        "id": "hard_without_labels",
        "text": "Finding commands without labels or icons was difficult.",
    },
]

# End of Session 2 only.
FINAL_LIKERT = [
    {
        "id": "disoriented_layout_switch",
        "text": (
            "I felt disoriented when the interface layout switched during "
            "today's session."),
    },
]

FINAL_OPEN = [
    {
        "id": "most_confusing",
        "text": "What was most confusing after today's session?",
        "placeholder": "Type your answer here.",
    },
]

# Backward-compatible aliases used by older logging helpers.
SESSION_1_LIKERT = POST_RECALL_LIKERT + [
    {
        "id": "disoriented_layout",
        "text": "I felt disoriented by the interface layout during the recall test.",
    },
]
SESSION_1_OPEN = FINAL_OPEN

SURVEY_POST_RECALL = "post_recall"
SURVEY_FINAL = "final"


class _LikertRadioCell(QWidget):
    """Hand-painted radio with its value label on the right."""

    def __init__(self, value, group, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)
        self._radio = WhiteDotToggle()
        group.addButton(self._radio, value)
        label = QLabel(str(value))
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        lay.addWidget(self._radio, alignment=Qt.AlignVCenter)
        lay.addWidget(label, alignment=Qt.AlignVCenter)

    def radio(self):
        return self._radio


class _LikertRow(QWidget):
    def __init__(self, question_id, question_text, parent=None):
        super().__init__(parent)
        self.question_id = question_id
        self._group = QButtonGroup(self)

        prompt = QLabel(question_text)
        prompt.setWordWrap(True)
        prompt.setStyleSheet("color: #ececec; font-size: 14px; font-weight: bold;")

        scale = QHBoxLayout()
        scale.setSpacing(6)
        low = QLabel(LIKERT_ANCHOR_LOW)
        low.setStyleSheet("color: #aaa; font-size: 11px;")
        low.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        high = QLabel(LIKERT_ANCHOR_HIGH)
        high.setStyleSheet("color: #aaa; font-size: 11px;")
        high.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        for value in range(1, 6):
            cell = _LikertRadioCell(value, self._group)
            buttons.addWidget(cell, alignment=Qt.AlignCenter)

        scale.addWidget(low, 2)
        scale.addLayout(buttons, 3)
        scale.addWidget(high, 2)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(prompt)
        lay.addLayout(scale)

    def value(self):
        btn = self._group.checkedButton()
        if btn is None:
            return None
        return self._group.id(btn)


class SessionSurveyWindow(GatewayWindow):
    """Configurable Likert + optional open-ended survey."""

    def __init__(self, likert_items, open_items=None, title_text=None,
                 intro_text=None, survey_type=SURVEY_FINAL, learn_num=0,
                 phase_index=0):
        super().__init__("Survey")
        self._likert_items = list(likert_items or [])
        self._open_items = list(open_items or [])
        self._likert_rows = []
        self._open_fields = {}
        self._survey_type = survey_type
        self._learn_num = int(learn_num or 0)
        self._phase_index = int(phase_index if phase_index else learn_num or 0)

        title = QLabel(title_text or "Feedback survey")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: bold;")

        intro = QLabel(intro_text or (
            "Please answer the questions below.\n"
            "Rate each statement from 1 (strongly disagree) to 5 (strongly agree)."))
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignCenter)
        intro.setStyleSheet("color: #c8c8c8; font-size: 14px; padding: 0 8px;")

        form = QWidget()
        form_lay = QVBoxLayout(form)
        form_lay.setSpacing(18)
        form_lay.setContentsMargins(4, 4, 12, 4)

        if self._likert_items:
            likert_heading = QLabel("Rating questions")
            likert_heading.setStyleSheet(
                "color: #ffffff; font-size: 15px; font-weight: bold;")
            form_lay.addWidget(likert_heading)
            for item in self._likert_items:
                row = _LikertRow(item["id"], item["text"])
                self._likert_rows.append(row)
                form_lay.addWidget(row)

        if self._open_items:
            if self._likert_items:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("color: #555;")
                form_lay.addWidget(sep)
            open_heading = QLabel("Open-ended question")
            open_heading.setStyleSheet(
                "color: #ffffff; font-size: 15px; font-weight: bold;")
            form_lay.addWidget(open_heading)
            for item in self._open_items:
                label = QLabel(item["text"])
                label.setWordWrap(True)
                label.setStyleSheet("color: #ececec; font-size: 14px;")
                field = QTextEdit()
                field.setPlaceholderText(item.get("placeholder", ""))
                field.setMaximumHeight(90)
                field.setStyleSheet(
                    "background-color: #3c3c3c; color: #e0e0e0;"
                    "border: 1px solid #555; padding: 6px; font-size: 13px;")
                form_lay.addWidget(label)
                form_lay.addWidget(field)
                self._open_fields[item["id"]] = field

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(form)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        scroll.setMinimumHeight(280)

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setStyleSheet("color: #e06c6c; font-size: 13px;")

        submit_btn = QPushButton("Submit and continue")
        submit_btn.setDefault(True)
        submit_btn.clicked.connect(self._try_submit)

        inner = QWidget()
        inner.setMinimumWidth(520)
        inner.setMaximumWidth(640)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setSpacing(12)
        inner_lay.addWidget(title)
        inner_lay.addWidget(intro)
        inner_lay.addSpacing(4)
        inner_lay.addWidget(scroll, 1)
        inner_lay.addWidget(self._msg)
        inner_lay.addWidget(submit_btn, alignment=Qt.AlignCenter)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.addWidget(inner)

        self.setMinimumSize(600, 480)
        self.resize(640, 540)

    def _try_submit(self):
        missing_likert = []
        responses = {
            "likert": {},
            "open": {},
            "survey_type": self._survey_type,
            "learn_num": self._learn_num,
            "phase_index": self._phase_index,
        }
        for row in self._likert_rows:
            val = row.value()
            if val is None:
                missing_likert.append(row.question_id)
            else:
                responses["likert"][row.question_id] = val
        missing_open = []
        for item in self._open_items:
            text = self._open_fields[item["id"]].toPlainText().strip()
            if not text:
                missing_open.append(item["id"])
            else:
                responses["open"][item["id"]] = text
        if missing_likert or missing_open:
            if missing_likert and missing_open:
                self._msg.setText(
                    "Please answer every rating and open-ended question "
                    "before continuing.")
            elif missing_likert:
                self._msg.setText(
                    "Please answer every rating question (1-5) before continuing.")
            else:
                self._msg.setText(
                    "Please answer every open-ended question before continuing.")
            return
        from .experiment_log import log_survey_responses
        log_survey_responses(responses)
        _log("survey completed (%s learn=%s): %s" % (
            self._survey_type, self._learn_num, responses))
        self._finish(responses)

    def closeEvent(self, event):
        self._finish(None)
        event.accept()


def run_post_recall_survey(learn_num=0):
    """Short 2-item Likert survey after a Session 2 learning-block recall."""
    try:
        win = SessionSurveyWindow(
            likert_items=POST_RECALL_LIKERT,
            open_items=[],
            title_text="Recall feedback",
            intro_text=(
                "Please rate how this recall block felt.\n"
                "Rate each statement from 1 (strongly disagree) to 5 "
                "(strongly agree)."),
            survey_type=SURVEY_POST_RECALL,
            learn_num=learn_num,
            phase_index=int(learn_num or 0))
        suppress_krita_ui(win)
        return win.run_blocking()
    except Exception:
        _log(traceback.format_exc())
        return None


def run_final_session_survey():
    """End-of-session survey: layout-switch disorientation + open question."""
    try:
        from .session_flow import session2_tutorial_count
        phase_index = session2_tutorial_count("A")
        win = SessionSurveyWindow(
            likert_items=FINAL_LIKERT,
            open_items=FINAL_OPEN,
            title_text="End of session feedback",
            intro_text=(
                "Please answer the questions below about today's session.\n"
                "Rate the statement from 1 (strongly disagree) to 5 "
                "(strongly agree)."),
            survey_type=SURVEY_FINAL,
            learn_num=0,
            phase_index=phase_index)
        suppress_krita_ui(win)
        return win.run_blocking()
    except Exception:
        _log(traceback.format_exc())
        return None


def run_session_survey():
    """Alias for the final Session 2 survey."""
    return run_final_session_survey()
