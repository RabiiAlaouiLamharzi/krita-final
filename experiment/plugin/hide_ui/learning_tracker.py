"""Learning-phase CSV logging — one row per step; revisits update that row."""

import re
import time

from .learning_instructions import required_command_for_step

_ICON_RE = re.compile(r"\{([^}]+)\}")

TOOLBOX_BUTTON_TO_COMMAND = {
    "KritaShape/KisToolBrush": "Freehand Brush Tool",
    "KritaTransform/KisToolMove": "Move Tool",
    "KritaShape/KisToolLine": "Straight Line Tool",
    "KritaShape/KisToolRectangle": "Rectangle Tool",
    "KritaShape/KisToolEllipse": "Ellipse Tool",
    "KritaFill/KisToolFill": "Fill Tool",
    "KritaFill/KisToolGradient": "Gradient Tool",
    "SvgTextTool": "Text Tool",
}

EVENT_TO_COMMAND = {
    "layer_added": "Add layer",
    "layer_deleted": "Delete layer",
    "layer_moved_up": "Move up",
    "layer_moved_down": "Move down",
}

IDLE_THRESHOLD_MS = 2000


def toolbox_command_name(object_name):
    oid = str(object_name or "").strip()
    if oid.startswith("toolbox:"):
        oid = oid.split(":", 1)[1]
    return TOOLBOX_BUTTON_TO_COMMAND.get(oid, "")


def parse_step_markers(step_text):
    return [m.strip() for m in _ICON_RE.findall(step_text or "")]


def _now_ms():
    return int(time.time() * 1000)


def _command_label(event_type, event_value):
    value = str(event_value or "").strip()
    if event_type == "tool_selected":
        return value
    if event_type == "preset_clicked":
        return "Brush preset: %s" % value if value else "Brush preset clicked"
    if event_type == "color_wheel_clicked":
        return "color wheel"
    if event_type in EVENT_TO_COMMAND:
        return EVENT_TO_COMMAND[event_type]
    return value or event_type


class LearningTracker:
    """Accumulates per-step metrics; writes learning.csv on Next (updates on revisit)."""

    def __init__(self, write_step=None):
        if write_step is None:
            from .experiment_log import log_learning_step
            write_step = log_learning_step
        self._write = write_step
        self._active = False
        self._tutorial_number = 0
        self._steps = []
        self._step_markers = []
        self._current_step_index = 0
        self._step_shown_ms = 0
        self._first_match_ms = None
        self._commands_clicked = []
        self._longest_pause_ms = 0
        self._last_meaningful_ms = 0
        self._step_open = False
        self._step_row_cache = {}

    @property
    def active(self):
        return self._active

    @property
    def current_step_index(self):
        return self._current_step_index

    @property
    def step_open(self):
        return self._step_open

    def start(self, tutorial_number, phase_number, steps):
        self._active = True
        self._tutorial_number = int(tutorial_number or 0)
        self._steps = list(steps or [])
        self._step_markers = [parse_step_markers(s) for s in self._steps]
        self._current_step_index = 0
        self._step_row_cache = {}
        if self._steps:
            self._begin_step(0)

    def stop(self):
        if not self._active:
            return
        if self._step_open and self._step_shown_ms:
            self._flush_step_row(_now_ms())
        self._active = False

    def on_step_next(self):
        if not self._active or not self._steps:
            return
        now = _now_ms()
        if self._step_open:
            self._flush_step_row(now)
        next_index = self._current_step_index + 1
        if next_index < len(self._steps):
            self._current_step_index = next_index
            self._begin_step(next_index)

    def on_step_back(self):
        """Return to the previous step without writing a row for the current step."""
        if not self._active or not self._steps:
            return
        if self._current_step_index <= 0:
            return
        self._current_step_index -= 1
        self._begin_step(self._current_step_index)

    def _begin_step(self, step_index):
        now = _now_ms()
        self._current_step_index = int(step_index)
        self._step_shown_ms = now
        self._step_open = True
        self._first_match_ms = None
        self._commands_clicked = []
        self._longest_pause_ms = 0
        self._last_meaningful_ms = now

    def _merge_step_data(self, existing, new):
        """Combine metrics when the participant revisits a step after Back."""
        merged = dict(existing)
        merged["time_on_step_ms"] = (
            int(existing.get("time_on_step_ms") or 0)
            + int(new.get("time_on_step_ms") or 0))
        old_cmds = [
            c for c in str(existing.get("commands_clicked") or "").split("|") if c]
        for cmd in str(new.get("commands_clicked") or "").split("|"):
            if cmd and cmd not in old_cmds:
                old_cmds.append(cmd)
        merged["commands_clicked"] = "|".join(old_cmds)
        old_delay = existing.get("delay_until_matching_action_ms", "")
        new_delay = new.get("delay_until_matching_action_ms", "")
        if old_delay not in (None, "") and new_delay not in (None, ""):
            merged["delay_until_matching_action_ms"] = min(
                int(old_delay), int(new_delay))
        elif new_delay not in (None, ""):
            merged["delay_until_matching_action_ms"] = new_delay
        else:
            merged["delay_until_matching_action_ms"] = old_delay or ""
        if (existing.get("followed_instruction") == "yes"
                or new.get("followed_instruction") == "yes"):
            merged["followed_instruction"] = "yes"
        else:
            merged["followed_instruction"] = new.get("followed_instruction", "no")
        pauses = []
        for pause in (existing.get("longest_pause_ms"), new.get("longest_pause_ms")):
            if pause not in (None, ""):
                pauses.append(int(pause))
        if pauses:
            best_pause = max(pauses)
            merged["longest_pause_ms"] = (
                best_pause if best_pause >= IDLE_THRESHOLD_MS else "")
        else:
            merged["longest_pause_ms"] = ""
        merged["required_command"] = (
            existing.get("required_command") or new.get("required_command") or "")
        return merged

    def _flush_step_row(self, step_next_time_ms):
        if not self._step_shown_ms:
            return
        next_ms = int(step_next_time_ms) if step_next_time_ms else _now_ms()
        time_on_step = max(0, next_ms - self._step_shown_ms)
        delay_match = (
            (self._first_match_ms - self._step_shown_ms)
            if self._first_match_ms else "")
        followed = "yes" if self._first_match_ms else "no"
        pause = (
            self._longest_pause_ms
            if self._longest_pause_ms >= IDLE_THRESHOLD_MS else "")
        step_text = (
            self._steps[self._current_step_index]
            if self._current_step_index < len(self._steps) else "")
        step_number = self._current_step_index + 1
        new_data = {
            "step_number": step_number,
            "time_on_step_ms": time_on_step,
            "delay_until_matching_action_ms": delay_match,
            "followed_instruction": followed,
            "longest_pause_ms": pause,
            "commands_clicked": "|".join(self._commands_clicked),
            "required_command": required_command_for_step(step_text),
        }
        update_existing = step_number in self._step_row_cache
        if update_existing:
            merged = self._merge_step_data(
                self._step_row_cache[step_number], new_data)
            self._write(
                tutorial_number=self._tutorial_number,
                update_existing=True,
                **merged)
            self._step_row_cache[step_number] = merged
        else:
            self._write(
                tutorial_number=self._tutorial_number,
                **new_data)
            self._step_row_cache[step_number] = dict(new_data)
        self._step_open = False
        self._step_shown_ms = 0

    def _command_for_event(self, event_type, event_value):
        if event_type == "tool_selected":
            return str(event_value or "").strip()
        if event_type == "preset_clicked":
            return str(event_value or "").strip()
        if event_type == "color_wheel_clicked":
            return "color wheel"
        return EVENT_TO_COMMAND.get(event_type, "")

    def _match_for_current_step(self, event_type, event_value):
        idx = self._current_step_index
        if idx >= len(self._steps):
            return ""
        markers = self._step_markers[idx] if idx < len(self._step_markers) else []
        step_text = self._steps[idx] if idx < len(self._steps) else ""
        command = self._command_for_event(event_type, event_value)
        required = required_command_for_step(step_text)

        if command and markers:
            if command in markers:
                return "yes"
            if any(command in m or m in command for m in markers):
                return "partial"
            return "no"
        if event_type == "color_wheel_clicked" and required == "color wheel":
            return "yes"
        if event_type == "preset_clicked":
            preset = str(event_value or "").lower()
            if required == "Eraser Preset" and "eraser" in preset:
                return "yes"
            if command and command == required:
                return "yes"
        if event_type == "tool_selected" and command == required:
            return "yes"
        if event_type == "tool_selected" and required in (
                "Freehand Brush Tool", "Gradient Tool", "Fill Tool",
                "Move Tool", "Straight Line Tool") and command == required:
            return "yes"
        if event_type in EVENT_TO_COMMAND and EVENT_TO_COMMAND[event_type] == required:
            return "yes"
        return ""

    def _note_pause(self, now_ms):
        if not self._last_meaningful_ms:
            return
        gap = now_ms - self._last_meaningful_ms
        if gap >= IDLE_THRESHOLD_MS and gap > self._longest_pause_ms:
            self._longest_pause_ms = gap

    def _note_meaningful_action(self, now_ms):
        self._note_pause(now_ms)
        self._last_meaningful_ms = now_ms

    def _note_command(self, event_type, event_value=""):
        if not self._active or not self._step_open:
            return
        now = _now_ms()
        self._note_meaningful_action(now)
        label = _command_label(event_type, event_value)
        if label:
            self._commands_clicked.append(label)
        match = self._match_for_current_step(event_type, event_value)
        if match in ("yes", "partial") and self._first_match_ms is None:
            self._first_match_ms = now

    def on_tool_selected(self, command_name):
        if command_name:
            self._note_command("tool_selected", command_name)

    def on_layer_event(self, event_type, detail=""):
        self._note_command(event_type, detail)

    def on_preset_clicked(self, preset_name):
        if preset_name:
            self._note_command("preset_clicked", preset_name)

    def on_color_wheel_clicked(self):
        self._note_command("color_wheel_clicked", "color wheel")
