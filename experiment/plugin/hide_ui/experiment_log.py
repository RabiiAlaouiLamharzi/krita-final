"""Split CSV logs for participant runs — durations in ms plus wall-clock timestamps.

Each session run folder contains:
  phases.csv         — learning, recall, survey, break blocks
  learning.csv       — one row per instruction step (on Next click)
  learning_pointer.csv — throttled mouse moves/clicks during learning
  recall_trials.csv  — one row per recall question
  survey.csv         — one row per survey submission
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
    "phase_type",
    "phase_index",
    "phase_started_at",
    "phase_ended_at",
    "block_duration_ms",
    "planned_time_limit_ms",
    "phase_end_reason",
)

LEARNING_COLUMNS = RUN_META_KEYS + (
    "tutorial_number",
    "step_number",
    "step_started_at",
    "step_ended_at",
    "step_duration_ms",
    "required_command",
    "commands_clicked",
    "followed_instruction",
    "delay_until_matching_action_ms",
    "longest_pause_ms",
)

LEARNING_POINTER_COLUMNS = RUN_META_KEYS + (
    "tutorial_number",
    "step_number",
    "step_started_at",
    "step_ended_at",
    "event_type",
    "recorded_at",
    "event_offset_ms",
    "x",
    "y",
    "clicked_target",
)

RECALL_TRIALS_COLUMNS = RUN_META_KEYS + (
    "tutorial_number",
    "question_order_number",
    "question_id",
    "question_text_prompt",
    "trial_started_at",
    "trial_ended_at",
    "response_duration_ms",
    "participant_did_answer",
    "participant_answer_text",
    "answer_was_correct",
    "slot_offset_x",
    "slot_offset_y",
    "slot_distance",
    "pixel_offset_x",
    "pixel_offset_y",
    "pixel_distance",
)

SURVEY_META_COLUMNS = RUN_META_KEYS + (
    "survey_type",
    "survey_started_at",
    "survey_ended_at",
    "survey_duration_ms",
)

SURVEY_COLUMN_NAMES = {
    "recall_difficulty": "survey_recall_difficulty_rating",
    "hard_without_labels": "survey_no_labels_difficulty_rating",
    "disoriented_layout_switch": "survey_felt_disoriented_switch_rating",
    "most_confusing": "survey_most_confusing_text",
}

SURVEY_ITEM_ORDER = (
    "recall_difficulty",
    "hard_without_labels",
    "disoriented_layout_switch",
    "most_confusing",
)

PHASE_TYPES = frozenset(("learning", "recall", "survey", "break"))

# Allowed values written to phases.csv phase_end_reason.
PHASE_END_REASONS = frozenset(("quit", "complete", "experimenter_skip", "timer"))


def normalize_phase_end_reason(reason, phase_type=None):
    """Map internal reasons to the four exported phase_end_reason values."""
    del phase_type
    raw = str(reason or "").strip().lower()
    if raw in PHASE_END_REASONS:
        return raw
    if raw in ("timer_finished",):
        return "timer"
    if raw in ("quit", "replaced"):
        return "quit"
    if raw in ("experimenter_skip",):
        return "experimenter_skip"
    # completed, ended, survey_completed, block_finished, etc.
    return "complete"


def _now_ms():
    return int(time.time() * 1000)


def _format_timestamp(ms=None):
    """Wall-clock time: YYYY-MM-DD HH:MM:SS.mmm"""
    if ms in (None, ""):
        ms = _now_ms()
    ms = int(ms)
    dt = datetime.fromtimestamp(ms / 1000.0)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + ".%03d" % (ms % 1000)


def _interval_fields(start_ms, end_ms, prefix):
    """Build {prefix}_started_at, {prefix}_ended_at from epoch ms."""
    if start_ms in (None, "") or end_ms in (None, ""):
        return {}
    start_ms = int(start_ms)
    end_ms = int(end_ms)
    return {
        "%s_started_at" % prefix: _format_timestamp(start_ms),
        "%s_ended_at" % prefix: _format_timestamp(end_ms),
    }


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


def _format_participant_answer(clicked):
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
        self._survey_meta = {}
        self._survey_started_ms = 0

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
            "learning_pointer": os.path.join(base, "learning_pointer.csv"),
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
            self._survey_meta = {}
            self._survey_started_ms = 0
            self._init_run_csv_files()
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
        survey_cols = tuple(SURVEY_META_COLUMNS) + tuple(
            SURVEY_COLUMN_NAMES[qid] for qid in SURVEY_ITEM_ORDER
            if qid in SURVEY_COLUMN_NAMES)
        for key, cols in (
                ("phases", PHASES_COLUMNS),
                ("learning", LEARNING_COLUMNS),
                ("learning_pointer", LEARNING_POINTER_COLUMNS),
                ("recall_trials", RECALL_TRIALS_COLUMNS),
                ("survey", survey_cols)):
            path = paths[key]
            if os.path.isfile(path):
                continue
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=cols)
                writer.writeheader()

    def _phase_key(self, phase_type, phase_index=0):
        return "%s:%s" % (phase_type, int(phase_index or 0))

    def _start_phase(self, phase_type, phase_index=0, **fields):
        if phase_type not in PHASE_TYPES:
            return
        idx = int(phase_index or 0)
        key = self._phase_key(phase_type, idx)
        planned_ms = fields.get("planned_duration_ms")
        if planned_ms is None and fields.get("duration_sec") is not None:
            planned_ms = int(fields["duration_sec"]) * 1000
        self._open_phases[key] = {
            **self._run_meta(),
            "phase_type": phase_type,
            "phase_index": idx,
            "planned_time_limit_ms": planned_ms if planned_ms is not None else "",
            "block_duration_ms": "",
            "phase_end_reason": "",
            "_started_at_ms": _now_ms(),
        }

    def _end_phase(self, phase_type, phase_index=0, ended_reason="", **fields):
        if phase_type not in PHASE_TYPES:
            return 0
        idx = int(phase_index or 0)
        key = self._phase_key(phase_type, idx)
        row = self._open_phases.pop(key, None)
        if row is None:
            row = {
                **self._run_meta(),
                "phase_type": phase_type,
                "phase_index": idx,
                "_started_at_ms": _now_ms(),
            }
        ended_ms = _now_ms()
        started = row.get("_started_at_ms") or ended_ms
        duration_ms = max(0, int(ended_ms) - int(started))
        row["block_duration_ms"] = duration_ms
        row["phase_end_reason"] = normalize_phase_end_reason(
            ended_reason or fields.get("reason", ""),
            phase_type)
        row["phase_started_at"] = _format_timestamp(started)
        row["phase_ended_at"] = _format_timestamp(ended_ms)
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
        started_ms = fields.pop("step_started_ms", None)
        ended_ms = fields.pop("step_ended_ms", None)
        fields.pop("command_click_ms", None)
        fields.pop("longest_pause_started_ms", None)
        fields.pop("longest_pause_ended_ms", None)
        row = {
            **self._run_meta(),
            "tutorial_number": int(tutorial_number or 0),
            **_interval_fields(started_ms, ended_ms, "step"),
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

    def log_learning_pointer(self, tutorial_number, **fields):
        if not self._run_dir:
            return
        step_started_ms = fields.pop("step_started_ms", None)
        event_ms = fields.pop("event_ms", None)
        row = {
            **self._run_meta(),
            "tutorial_number": int(tutorial_number or 0),
        }
        if step_started_ms not in (None, ""):
            row["step_started_at"] = _format_timestamp(step_started_ms)
        if event_ms not in (None, ""):
            row["recorded_at"] = _format_timestamp(event_ms)
        for col in LEARNING_POINTER_COLUMNS:
            if col in row:
                continue
            if col in fields and fields[col] is not None:
                row[col] = fields[col]
        _append_csv(
            self._paths()["learning_pointer"], LEARNING_POINTER_COLUMNS, row)

    def backfill_learning_pointer_step_ended(
            self, tutorial_number, step_number, step_started_ms, step_ended_ms):
        """Set step_ended_at on pointer rows for one step session."""
        if not self._run_dir or step_ended_ms in (None, ""):
            return
        path = self._paths()["learning_pointer"]
        if not os.path.isfile(path):
            return
        started_at = _format_timestamp(step_started_ms)
        ended_at = _format_timestamp(step_ended_ms)
        run_id = str(self._run_meta().get("run_folder_id") or "")
        rows = _read_csv(path, LEARNING_POINTER_COLUMNS)
        changed = False
        for row in rows:
            if (int(row.get("tutorial_number") or 0) != int(tutorial_number or 0)
                    or int(row.get("step_number") or 0) != int(step_number or 0)
                    or str(row.get("run_folder_id") or "") != run_id
                    or str(row.get("step_started_at") or "") != started_at):
                continue
            row["step_ended_at"] = ended_at
            changed = True
        if changed:
            _write_csv(path, LEARNING_POINTER_COLUMNS, rows)

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
        phase_index = int(fields.get("phase_index", learn_num) or 0)

        if event == "learning":
            if action == "start":
                self._start_phase(
                    "learning", phase_index=learn_num,
                    duration_sec=fields.get("duration_sec"))
            elif action == "end":
                self._end_phase(
                    "learning", phase_index=learn_num,
                    ended_reason=fields.get("reason", "complete"))

        elif event == "recall":
            if action == "start":
                self._recall_learn_num = learn_num
                self._start_phase("recall", phase_index=learn_num)
            elif action == "end":
                reason = normalize_phase_end_reason(
                    fields.get("reason", "complete"), "recall")
                self._end_phase(
                    "recall", phase_index=learn_num,
                    ended_reason=reason)

        elif event == "break":
            if action == "start":
                self._start_phase(
                    "break", phase_index=learn_num,
                    duration_sec=fields.get("duration_sec"))
            elif action == "end":
                self._end_phase(
                    "break", phase_index=learn_num,
                    ended_reason=fields.get("reason", "complete"))

        elif event == "survey":
            if action == "start":
                self._survey_buffer = {}
                self._survey_started_ms = _now_ms()
                phase_index = int(fields.get("phase_index", learn_num) or 0)
                self._survey_meta = {
                    "survey_type": fields.get("survey_type", ""),
                    "phase_index": phase_index,
                }
                self._start_phase("survey", phase_index=phase_index)
            elif action == "end":
                phase_index = int(
                    (getattr(self, "_survey_meta", {}) or {}).get(
                        "phase_index", learn_num) or 0)
                duration_ms = self._end_phase(
                    "survey", phase_index=phase_index,
                    ended_reason="complete")
                if fields.get("duration_ms") not in (None, ""):
                    duration_ms = max(0, int(fields["duration_ms"]))
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
        if bool(fields.get("phase_skipped")):
            return
        correct = bool(fields.get("correct"))
        timeout = bool(fields.get("timeout"))
        clicked = fields.get("clicked")
        has_click = clicked not in (None, "")
        answered = bool(has_click and not timeout)

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

        if timeout or not has_click:
            correct = False

        ended_ms = answered_ms if answered_ms not in (None, "") else _now_ms()
        row = {
            **self._run_meta(),
            "tutorial_number": self._recall_learn_num,
            "question_order_number": question_num,
            "question_id": question_id,
            "question_text_prompt": prompt,
            **_interval_fields(presented_ms, ended_ms, "trial"),
            "participant_did_answer": answered,
            "participant_answer_text": _format_participant_answer(clicked),
            "response_duration_ms": response_duration_ms,
            "answer_was_correct": correct,
            "slot_offset_x": fields.get("slot_offset_x", ""),
            "slot_offset_y": fields.get("slot_offset_y", ""),
            "slot_distance": fields.get("slot_distance", ""),
            "pixel_offset_x": fields.get("pixel_offset_x", ""),
            "pixel_offset_y": fields.get("pixel_offset_y", ""),
            "pixel_distance": fields.get("pixel_distance", ""),
        }
        _append_csv(self._paths()["recall_trials"], RECALL_TRIALS_COLUMNS, row)
        if question_num:
            self._logged_recall_nums.add(int(question_num))
        self._pending_question = None

    def finalize_recall_block(self, questions, partial_results,
                              phase_skipped=False):
        """Fill missing recall rows and return a complete per-question result list."""
        if phase_skipped:
            self._recall_questions = []
            self._logged_recall_nums = set()
            self._pending_question = None
            return []

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
                if row.get("timeout") or not row.get("clicked"):
                    row["unanswered"] = True
                    row["correct"] = False
                elif row.get("correct"):
                    row["unanswered"] = False
                else:
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
                "timeout": True,
            })
            complete.append({
                "question_id": qid,
                "prompt": question.get("prompt", ""),
                "expected": question.get("answer", ""),
                "clicked": None,
                "correct": False,
                "timeout": True,
                "unanswered": True,
                "time_taken_ms": 0,
            })

        self._recall_questions = []
        self._logged_recall_nums = set()
        self._pending_question = None
        return complete

    def _flush_survey(self, duration_ms=0):
        if not self._survey_buffer:
            return
        meta = getattr(self, "_survey_meta", {}) or {}
        survey_cols = tuple(
            SURVEY_COLUMN_NAMES.get(qid, qid) for qid in SURVEY_ITEM_ORDER)
        columns = tuple(SURVEY_META_COLUMNS) + survey_cols
        row = {
            **self._run_meta(),
            "survey_type": meta.get("survey_type", ""),
            "survey_duration_ms": int(duration_ms or 0),
        }
        ended_ms = _now_ms()
        started_ms = int(getattr(self, "_survey_started_ms", 0) or 0)
        if not started_ms and duration_ms:
            started_ms = ended_ms - int(duration_ms)
        row.update(_interval_fields(started_ms, ended_ms, "survey"))
        for qid in SURVEY_ITEM_ORDER:
            col = SURVEY_COLUMN_NAMES.get(qid, qid)
            row[col] = self._survey_buffer.get(qid, "")
        _append_csv(self._paths()["survey"], columns, row)
        debug_log("survey responses saved to %s (%s)" % (
            self._paths()["survey"],
            meta.get("survey_type", "")))
        self._survey_buffer = {}
        self._survey_meta = {}
        self._survey_started_ms = 0

    def end_session(self, action="complete"):
        if not self._run_dir:
            return
        try:
            action = normalize_phase_end_reason(action)
            for key in list(self._open_phases.keys()):
                phase_type, phase_index = key.split(":", 1)
                if phase_type in PHASE_TYPES:
                    self._end_phase(phase_type, phase_index=int(phase_index),
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
            self._survey_meta = {}
            self._survey_started_ms = 0


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
        questions, partial_results,
        phase_skipped=phase_skipped)


def end_session(action="complete"):
    _LOGGER.end_session(action=action)


def log_learning_step(**fields):
    tutorial_number = fields.pop("tutorial_number", 0)
    _LOGGER.log_learning_step(tutorial_number, **fields)


def log_learning_row(**fields):
    """Alias for log_learning_step."""
    log_learning_step(**fields)


def log_learning_pointer(**fields):
    tutorial_number = fields.pop("tutorial_number", 0)
    _LOGGER.log_learning_pointer(tutorial_number, **fields)


def backfill_learning_pointer_step_ended(
        tutorial_number, step_number, step_started_ms, step_ended_ms):
    _LOGGER.backfill_learning_pointer_step_ended(
        tutorial_number, step_number, step_started_ms, step_ended_ms)


def save_learning_drawing(tutorial_number):
    return _LOGGER.save_learning_drawing(tutorial_number)


def _encode_survey_type(survey_type, learn_num=0, phase_index=0):
    st = str(survey_type or "").strip()
    if st == "post_recall" and learn_num:
        return "post_recall_%d" % int(learn_num)
    if st == "final":
        return "final"
    return st


def log_survey_responses(responses):
    """Write survey likert + open answers to survey.csv and phases.csv."""
    if not responses:
        return
    learn_num = int(responses.get("learn_num", 0) or 0)
    phase_index = int(responses.get("phase_index", learn_num) or 0)
    survey_type = _encode_survey_type(
        responses.get("survey_type") or "",
        learn_num=learn_num,
        phase_index=phase_index)
    for qid, val in (responses.get("likert") or {}).items():
        _LOGGER.log_t("survey", question_id=qid, response=val)
    for qid, text in (responses.get("open") or {}).items():
        _LOGGER.log_t("survey", question_id=qid, response=text)
    duration_ms = responses.get("duration_ms")
    _LOGGER.log_e(
        "survey", action="end",
        survey_type=survey_type,
        learn_num=learn_num,
        phase_index=phase_index,
        duration_ms=duration_ms)


def start_survey(survey_type, learn_num=0, phase_index=0):
    """Begin survey timing when the survey window is shown."""
    encoded = _encode_survey_type(
        survey_type or "", learn_num=learn_num, phase_index=phase_index)
    _LOGGER.log_e(
        "survey", action="start",
        survey_type=encoded,
        learn_num=learn_num,
        phase_index=phase_index)


def get_run_dir():
    return _LOGGER.path or ""


def learning_drawing_path(tutorial_number):
    """Absolute path for the learning-phase PNG; creates the folder."""
    if not _LOGGER.path:
        return ""
    folder = _LOGGER.learning_drawings_dir(tutorial_number)
    return os.path.abspath(os.path.join(folder, "drawing.png"))
