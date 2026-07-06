"""Split CSV logs for participant runs — durations in milliseconds (no wall-clock timestamps).

Each session run folder contains:
  phases.csv        — consent, learning, recall, survey blocks
  learning.csv      — one row per instruction step (on Next click)
  recall_trials.csv — one row per recall question
  survey.csv        — one row per survey submission
"""

import csv
import os
import re
import time
import traceback
from datetime import datetime

from .experiment import _log as debug_log

RUN_META_KEYS = ("run_folder_id",)

PHASES_COLUMNS = RUN_META_KEYS + (
    "phase_block_type",
    "tutorial_number",
    "learning_phase_number",
    "planned_time_limit_ms",
    "block_duration_ms",
    "block_ended_reason",
    "total_question_count",
    "answered_question_count",
    "correct_answer_count",
    "recall_score_percent",
)

LEARNING_COLUMNS = RUN_META_KEYS + (
    "tutorial_number",
    "step_number",
    "time_on_step_ms",
    "delay_until_matching_action_ms",
    "followed_instruction",
    "longest_pause_ms",
    "commands_clicked",
    "required_command",
)

RECALL_TRIALS_COLUMNS = RUN_META_KEYS + (
    "tutorial_number",
    "question_order_number",
    "question_identifier_code",
    "question_text_prompt",
    "response_duration_ms",
    "participant_did_answer",
    "answer_was_correct",
    "answer_outcome_category",
    "participant_answer_text",
    "recall_block_was_skipped",
)

SURVEY_META_COLUMNS = RUN_META_KEYS + ("survey_duration_ms",)

SURVEY_COLUMN_NAMES = {
    "recall_difficulty": "survey_recall_difficulty_rating",
    "disoriented_layout": "survey_felt_disoriented_rating",
    "hard_without_labels": "survey_no_labels_difficulty_rating",
    "most_confusing": "survey_most_confusing_text",
}

PHASE_TYPES = frozenset(("learning", "recall", "consent", "survey"))


def _now_ms():
    return int(time.time() * 1000)


def _safe_part(text):
    cleaned = re.sub(r"[^\w\-]+", "_", str(text or "").strip())
    return cleaned or "unknown"


def _cell(value):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def run_folder_id(session, stamp):
    pid = _safe_part(session.get("participant_id", "P00"))
    condition = _safe_part(session.get("condition", "X"))
    session_num = int(session.get("session", 0) or 0)
    return "%s_%s_S%d_%s" % (pid, condition, session_num, stamp)


def _stamp_from_session(session):
    started = session.get("started_at")
    if started and len(str(started)) == 15 and "_" in str(started):
        raw = str(started)
        return "%s-%s-%s-%s-%s-%s" % (
            raw[0:4], raw[4:6], raw[6:8],
            raw[9:11], raw[11:13], raw[13:15])
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")


def _append_csv(path, columns, row):
    exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({col: _cell(row.get(col, "")) for col in columns})


def _read_csv(path, columns):
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{col: row.get(col, "") for col in columns} for row in reader]


def _write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: _cell(row.get(col, "")) for col in columns})


def _format_participant_answer(clicked, outcome):
    if outcome == "phase_skipped":
        return "Block skipped (experimenter)"
    if outcome == "unanswered":
        return "Unanswered"
    if not clicked:
        return "Unanswered"
    return str(clicked)


class ExperimentLogger:
    def __init__(self):
        self._run_dir = None
        self._run_id = None
        self._session = None
        self._open_phases = {}
        self._recall_learn_num = 0
        self._recall_questions = []
        self._logged_recall_nums = set()
        self._pending_question = None
        self._survey_buffer = {}

    @property
    def path(self):
        return self._run_dir

    @property
    def run_id(self):
        return self._run_id

    def active(self):
        return bool(self._run_dir)

    def _paths(self):
        base = self._run_dir
        return {
            "phases": os.path.join(base, "phases.csv"),
            "learning": os.path.join(base, "learning.csv"),
            "recall_trials": os.path.join(base, "recall_trials.csv"),
            "survey": os.path.join(base, "survey.csv"),
        }

    def _run_meta(self):
        return {"run_folder_id": self._run_id}

    def start_session(self, session):
        self.end_session(action="replaced")
        if not session:
            return None
        try:
            from .participant_data import ensure_participant_dir
            pid = session.get("participant_id")
            if not pid:
                return None
            stamp = _stamp_from_session(session)
            self._run_id = run_folder_id(session, stamp)
            pdir = ensure_participant_dir(pid)
            self._run_dir = os.path.join(pdir, self._run_id)
            os.makedirs(self._run_dir, exist_ok=True)
            self._session = dict(session)
            self._open_phases = {}
            self._recall_learn_num = 0
            self._recall_questions = []
            self._logged_recall_nums = set()
            self._pending_question = None
            self._survey_buffer = {}
            self._init_run_csv_files()
            if session.get("consent_signed"):
                self._log_consent()
            debug_log("experiment log started: %s" % self._run_dir)
            return self._run_dir
        except Exception:
            debug_log(traceback.format_exc())
            self._run_dir = None
            self._run_id = None
            self._session = None
            return None

    def _init_run_csv_files(self):
        """Create CSV files with headers as soon as the session starts."""
        paths = self._paths()
        for key, cols in (
                ("phases", PHASES_COLUMNS),
                ("learning", LEARNING_COLUMNS),
                ("recall_trials", RECALL_TRIALS_COLUMNS)):
            path = paths[key]
            if os.path.isfile(path):
                continue
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=cols)
                writer.writeheader()
        row = dict(self._run_meta())
        session_num = int((self._session or {}).get("session", 0) or 0)
        row.update({
            "phase_block_type": "session",
            "tutorial_number": 0,
            "learning_phase_number": session_num,
            "planned_time_limit_ms": "",
            "block_duration_ms": 0,
            "block_ended_reason": "session_started",
            "total_question_count": "",
            "answered_question_count": "",
            "correct_answer_count": "",
            "recall_score_percent": "",
        })
        _append_csv(paths["phases"], PHASES_COLUMNS, row)

    def _log_consent(self):
        row = dict(self._run_meta())
        row.update({
            "phase_block_type": "consent",
            "tutorial_number": 0,
            "learning_phase_number": "",
            "planned_time_limit_ms": "",
            "block_duration_ms": 0,
            "block_ended_reason": "consent_accepted",
            "total_question_count": "",
            "answered_question_count": "",
            "correct_answer_count": "",
            "recall_score_percent": "",
        })
        _append_csv(self._paths()["phases"], PHASES_COLUMNS, row)

    def _phase_key(self, phase_type, learn_num=None):
        return "%s:%s" % (phase_type, int(learn_num or 0))

    def _start_phase(self, phase_type, learn_num=0, **fields):
        if phase_type not in PHASE_TYPES:
            return
        key = self._phase_key(phase_type, learn_num)
        planned_ms = fields.get("planned_duration_ms")
        if planned_ms is None and fields.get("duration_sec") is not None:
            planned_ms = int(fields["duration_sec"]) * 1000
        self._open_phases[key] = {
            **self._run_meta(),
            "phase_block_type": phase_type,
            "tutorial_number": int(learn_num or 0),
            "learning_phase_number": fields.get("phase", ""),
            "planned_time_limit_ms": planned_ms if planned_ms is not None else "",
            "block_duration_ms": "",
            "block_ended_reason": "",
            "total_question_count": fields.get("question_count", ""),
            "answered_question_count": "",
            "correct_answer_count": "",
            "recall_score_percent": "",
            "_started_at_ms": _now_ms(),
            "_interface_layout_code": fields.get("layout", ""),
            "_is_practice_trial": fields.get("practice", ""),
        }

    def _end_phase(self, phase_type, learn_num=0, ended_reason="", **fields):
        if phase_type not in PHASE_TYPES:
            return 0
        key = self._phase_key(phase_type, learn_num)
        row = self._open_phases.pop(key, None)
        if row is None:
            row = {
                **self._run_meta(),
                "phase_block_type": phase_type,
                "tutorial_number": int(learn_num or 0),
                "_started_at_ms": _now_ms(),
            }
        ended_ms = _now_ms()
        started = row.get("_started_at_ms") or ended_ms
        duration_ms = max(0, int(ended_ms) - int(started))
        row["block_duration_ms"] = duration_ms
        row["block_ended_reason"] = ended_reason or fields.get("reason", "")
        mapping = {
            "question_count": "total_question_count",
            "answered_count": "answered_question_count",
            "correct_count": "correct_answer_count",
            "score_percent": "recall_score_percent",
            "phase_index": "learning_phase_number",
        }
        for src, dest in mapping.items():
            if src in fields and fields[src] is not None:
                row[dest] = fields[src]
        phase_row = {k: v for k, v in row.items() if not k.startswith("_")}
        _append_csv(self._paths()["phases"], PHASES_COLUMNS, phase_row)
        return duration_ms

    def learning_drawings_dir(self, tutorial_number):
        """Folder for the learning-phase PNG: learning_drawings/tutorial_N/"""
        path = os.path.join(
            self._run_dir,
            "learning_drawings",
            "tutorial_%d" % int(tutorial_number or 0))
        os.makedirs(path, exist_ok=True)
        return path

    def save_learning_drawing(self, tutorial_number):
        """Save the current canvas once when a learning phase ends or is skipped."""
        if not self._run_dir:
            debug_log("learning export: no run folder")
            return False
        try:
            from krita import Krita
            from PyQt5.QtWidgets import QApplication

            k = Krita.instance()
            doc = None
            win = k.activeWindow()
            if win is not None:
                view = win.activeView()
                if view is not None:
                    doc = view.document()
            if doc is None:
                doc = k.activeDocument()
            if doc is None:
                docs = list(k.documents())
                doc = docs[-1] if docs else None
            if doc is None:
                debug_log("learning export: no document")
                return False

            doc.waitForDone()
            doc.refreshProjection()
            doc.waitForDone()
            QApplication.processEvents()

            image = doc.projection()
            if image is None or image.isNull():
                debug_log("learning export: blank projection")
                return False

            folder = self.learning_drawings_dir(tutorial_number)
            path = os.path.abspath(os.path.join(folder, "drawing.png"))
            if not image.save(path, "PNG"):
                debug_log("learning export: QImage.save failed for %s" % path)
                return False

            if os.path.isfile(path) and os.path.getsize(path) > 0:
                debug_log("learning export saved: %s" % path)
                return True
            debug_log("learning export: file missing after save %s" % path)
        except Exception:
            debug_log(traceback.format_exc())
        return False

    def log_learning_step(self, tutorial_number, **fields):
        if not self._run_dir:
            return
        update_existing = bool(fields.pop("update_existing", False))
        step_number = int(fields.get("step_number") or 0)
        row = {
            **self._run_meta(),
            "tutorial_number": int(tutorial_number or 0),
        }
        for col in LEARNING_COLUMNS:
            if col in row:
                continue
            if col in fields and fields[col] is not None:
                row[col] = fields[col]
        path = self._paths()["learning"]
        if update_existing and step_number:
            run_id = str(row.get("run_folder_id") or "")
            rows = _read_csv(path, LEARNING_COLUMNS)
            match_index = None
            for index, existing in enumerate(rows):
                if (int(existing.get("tutorial_number") or 0) == int(tutorial_number)
                        and int(existing.get("step_number") or 0) == step_number
                        and str(existing.get("run_folder_id") or "") == run_id):
                    match_index = index
                    break
            if match_index is not None:
                for col in LEARNING_COLUMNS:
                    if col in row:
                        rows[match_index][col] = _cell(
                            row.get(col, rows[match_index].get(col, "")))
                _write_csv(path, LEARNING_COLUMNS, rows)
                return
        _append_csv(path, LEARNING_COLUMNS, row)

    def register_recall_questions(self, questions, learn_num=0):
        self._recall_questions = list(questions or [])
        self._recall_learn_num = int(learn_num or 0)
        self._logged_recall_nums = set()
        self._pending_question = None

    def log_e(self, event, **fields):
        if not self._run_dir:
            return
        action = fields.get("action")
        learn_num = int(fields.get("learn_num", 0) or 0)

        if event == "learning":
            if action == "start":
                self._start_phase(
                    "learning", learn_num=learn_num,
                    phase=fields.get("phase"),
                    layout=fields.get("layout"),
                    practice=fields.get("practice"),
                    duration_sec=fields.get("duration_sec"))
            elif action == "end":
                self._end_phase(
                    "learning", learn_num=learn_num,
                    ended_reason=fields.get("reason", "timer_finished"))

        elif event == "recall":
            if action == "start":
                self._recall_learn_num = learn_num
                self._start_phase(
                    "recall", learn_num=learn_num,
                    question_count=fields.get("question_count"))
            elif action == "end":
                self._end_phase(
                    "recall", learn_num=learn_num,
                    ended_reason=fields.get("reason", "block_finished"),
                    question_count=fields.get("question_count"),
                    answered_count=fields.get("answered_count"),
                    correct_count=fields.get("correct_count"),
                    score_percent=fields.get("score_percent"))

        elif event == "survey":
            if action == "start":
                self._survey_buffer = {}
                self._start_phase("survey", learn_num=0)
            elif action == "end":
                duration_ms = self._end_phase(
                    "survey", learn_num=0,
                    ended_reason="survey_completed")
                self._flush_survey(duration_ms=duration_ms)

        elif event == "recall_question":
            presented = fields.get("presented_ms")
            if presented in (None, ""):
                presented = _now_ms()
            self._pending_question = {
                "num": int(fields.get("num", 0) or 0),
                "question_id": fields.get("question_id", ""),
                "prompt": fields.get("prompt", ""),
                "presented_ms": int(presented),
            }

    def log_t(self, subtype, **fields):
        if not self._run_dir:
            return
        if subtype == "recall":
            self._append_recall_trial(fields)
        elif subtype == "survey":
            qid = fields.get("question_id")
            if qid:
                self._survey_buffer[str(qid)] = fields.get("response", "")

    def _append_recall_trial(self, fields):
        correct = bool(fields.get("correct"))
        timeout = bool(fields.get("timeout"))
        phase_skipped = bool(fields.get("phase_skipped"))
        clicked = fields.get("clicked")
        has_click = clicked not in (None, "")

        if phase_skipped:
            outcome = "phase_skipped"
            answered = False
            correct = False
        elif timeout or not has_click:
            outcome = "unanswered"
            answered = False
            correct = False
        elif correct:
            outcome = "correct"
            answered = True
        else:
            outcome = "incorrect"
            answered = True

        presented_ms = fields.get("presented_ms", "")
        question_num = fields.get("num", "")
        question_id = fields.get("question_id", "")
        prompt = fields.get("prompt", "")
        if self._pending_question:
            if presented_ms in (None, ""):
                presented_ms = self._pending_question.get("presented_ms", "")
            question_num = question_num or self._pending_question.get("num", "")
            question_id = question_id or self._pending_question.get("question_id", "")
            prompt = prompt or self._pending_question.get("prompt", "")
        answered_ms = fields.get("answered_ms")
        if answered_ms in (None, "") and answered:
            answered_ms = _now_ms()
        response_duration_ms = 0
        if presented_ms not in (None, "") and answered_ms not in (None, ""):
            response_duration_ms = max(
                0, int(answered_ms) - int(presented_ms))
        elif fields.get("time_taken_ms") not in (None, ""):
            response_duration_ms = int(fields["time_taken_ms"])

        row = {
            **self._run_meta(),
            "tutorial_number": self._recall_learn_num,
            "question_order_number": question_num,
            "question_identifier_code": question_id,
            "question_text_prompt": prompt,
            "response_duration_ms": response_duration_ms,
            "participant_did_answer": answered,
            "answer_was_correct": correct,
            "answer_outcome_category": outcome,
            "participant_answer_text": _format_participant_answer(clicked, outcome),
            "recall_block_was_skipped": phase_skipped,
        }
        _append_csv(self._paths()["recall_trials"], RECALL_TRIALS_COLUMNS, row)
        if question_num:
            self._logged_recall_nums.add(int(question_num))
        if not phase_skipped:
            self._pending_question = None

    def finalize_recall_block(self, questions, partial_results, phase_skipped=False):
        """Fill missing recall rows and return a complete per-question result list."""
        by_id = {}
        for row in partial_results or []:
            qid = str(row.get("question_id", ""))
            if qid:
                by_id[qid] = dict(row)

        complete = []
        for index, question in enumerate(questions or []):
            qnum = index + 1
            qid = str(question.get("id", ""))
            if qid in by_id:
                row = dict(by_id[qid])
                if row.get("phase_skipped"):
                    row["outcome"] = "phase_skipped"
                    row["unanswered"] = True
                elif row.get("timeout") or not row.get("clicked"):
                    row["outcome"] = "unanswered"
                    row["unanswered"] = True
                    row["correct"] = False
                elif row.get("correct"):
                    row["outcome"] = "correct"
                    row["unanswered"] = False
                else:
                    row["outcome"] = "incorrect"
                    row["unanswered"] = False
                complete.append(row)
                continue

            presented_ms = ""
            if (self._pending_question
                    and str(self._pending_question.get("question_id")) == qid):
                presented_ms = self._pending_question.get("presented_ms", "")

            self._append_recall_trial({
                "num": qnum,
                "question_id": qid,
                "prompt": question.get("prompt", ""),
                "presented_ms": presented_ms,
                "answered_ms": "",
                "time_taken_ms": 0,
                "correct": False,
                "clicked": "",
                "timeout": not phase_skipped,
                "phase_skipped": phase_skipped,
            })
            complete.append({
                "question_id": qid,
                "prompt": question.get("prompt", ""),
                "expected": question.get("answer", ""),
                "clicked": None,
                "correct": False,
                "timeout": not phase_skipped,
                "phase_skipped": phase_skipped,
                "unanswered": True,
                "outcome": "phase_skipped" if phase_skipped else "unanswered",
                "time_taken_ms": 0,
            })

        self._recall_questions = []
        self._logged_recall_nums = set()
        self._pending_question = None
        return complete

    def _flush_survey(self, duration_ms=0):
        if not self._survey_buffer:
            return
        try:
            from .survey import SESSION_1_LIKERT, SESSION_1_OPEN
            item_ids = [item["id"] for item in SESSION_1_LIKERT]
            item_ids += [item["id"] for item in SESSION_1_OPEN]
        except Exception:
            item_ids = sorted(self._survey_buffer.keys())
        survey_cols = tuple(
            SURVEY_COLUMN_NAMES.get(qid, qid) for qid in item_ids)
        columns = tuple(SURVEY_META_COLUMNS) + survey_cols
        row = {
            **self._run_meta(),
            "survey_duration_ms": int(duration_ms or 0),
        }
        for qid in item_ids:
            col = SURVEY_COLUMN_NAMES.get(qid, qid)
            row[col] = self._survey_buffer.get(qid, "")
        _write_csv(self._paths()["survey"], columns, [row])
        self._survey_buffer = {}

    def end_session(self, action="complete"):
        if not self._run_dir:
            return
        try:
            for key in list(self._open_phases.keys()):
                phase_type, learn_num = key.split(":", 1)
                if phase_type in PHASE_TYPES:
                    self._end_phase(phase_type, learn_num=int(learn_num),
                                    ended_reason=action)
            debug_log("experiment log ended (%s): %s" % (action, self._run_dir))
        finally:
            self._run_dir = None
            self._run_id = None
            self._session = None
            self._open_phases = {}
            self._recall_questions = []
            self._logged_recall_nums = set()
            self._pending_question = None
            self._survey_buffer = {}


_LOGGER = ExperimentLogger()


def get_logger():
    return _LOGGER


def start_session(session):
    return _LOGGER.start_session(session)


def log_e(event, **fields):
    _LOGGER.log_e(event, **fields)


def log_t(subtype, **fields):
    _LOGGER.log_t(subtype, **fields)


def register_recall_questions(questions, learn_num=0):
    _LOGGER.register_recall_questions(questions, learn_num=learn_num)


def finalize_recall_block(questions, partial_results, phase_skipped=False):
    return _LOGGER.finalize_recall_block(
        questions, partial_results, phase_skipped=phase_skipped)


def end_session(action="complete"):
    _LOGGER.end_session(action=action)


def log_learning_step(**fields):
    tutorial_number = fields.pop("tutorial_number", 0)
    _LOGGER.log_learning_step(tutorial_number, **fields)


def log_learning_row(**fields):
    """Alias for log_learning_step."""
    log_learning_step(**fields)


def save_learning_drawing(tutorial_number):
    return _LOGGER.save_learning_drawing(tutorial_number)


def get_run_dir():
    return _LOGGER.path or ""


def learning_drawing_path(tutorial_number):
    """Absolute path for the learning-phase PNG; creates the folder."""
    if not _LOGGER.path:
        return ""
    folder = _LOGGER.learning_drawings_dir(tutorial_number)
    return os.path.abspath(os.path.join(folder, "drawing.png"))
