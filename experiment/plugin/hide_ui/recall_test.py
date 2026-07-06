"""Command-location recall test after each tutorial block."""

import html
import os
import random
import traceback
from pathlib import Path

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
COMMANDS_DIR = os.path.join(PLUGIN_DIR, "commands")

from .session_flow import run_tutorial_intro

RECALL_QUESTION_TIME_SEC = 10
RECALL_PHASE_TIME_SEC = 180          # 3 minutes for the whole recall block
TRIAL_RECALL_QUESTION_TIME_SEC = 30
TRIAL_RECALL_QUESTION_COUNT = 5

# Legacy alias
RECALL_TIME_SEC = RECALL_QUESTION_TIME_SEC

RECALL_SIDE_PANEL = {
    "title": "Command recall test",
    "body": (
        "Some commands are hidden under white boxes on the Krita interface.\n\n"
        "Read each question in the bar at the top of Krita.\n\n"
        "Click the white box where you think that command is.\n\n"
        "Answer as quickly and accurately as you can."),
}

RECALL_PRACTICE_SIDE_PANEL = {
    "title": "Command recall test",
    "body": (
        "This is a practice trial.\n\n"
        "Some commands are hidden under white boxes on the Krita interface.\n\n"
        "Read each question in the bar at the top of Krita.\n\n"
        "Click the white box where you think that command is.\n\n"
        "Answer as quickly and accurately as you can."),
}

RECALL_OPENING_SIDE_PANEL = {
    "title": "Recall: Layout A",
    "body": (
        "Before the new tutorials, recall where commands were in the "
        "interface you learned in Session 1.\n\n"
        "Some commands are hidden under white boxes.\n\n"
        "Read each question at the top of Krita and click the matching white box."),
}

RECALL_INTRO = {
    "title": RECALL_SIDE_PANEL["title"],
    "body": RECALL_SIDE_PANEL["body"],
}

# answer ids must match hide_ui recall overlay command ids (16 study targets).
RECALL_QUESTIONS_ALL = [
    {
        "id": "brush_tool",
        "prompt": "Where is the Brush tool?",
        "answer": "toolbox:KritaShape/KisToolBrush",
    },
    {
        "id": "move_tool",
        "prompt": "Where is the Move tool?",
        "answer": "toolbox:KritaTransform/KisToolMove",
    },
    {
        "id": "line_tool",
        "prompt": "Where is the Line tool?",
        "answer": "toolbox:KritaShape/KisToolLine",
    },
    {
        "id": "rectangle_tool",
        "prompt": "Where is the Rectangle tool?",
        "answer": "toolbox:KritaShape/KisToolRectangle",
    },
    {
        "id": "ellipse_tool",
        "prompt": "Where is the Ellipse tool?",
        "answer": "toolbox:KritaShape/KisToolEllipse",
    },
    {
        "id": "fill_tool",
        "prompt": "Where is the Fill tool?",
        "answer": "toolbox:KritaFill/KisToolFill",
    },
    {
        "id": "gradient_tool",
        "prompt": "Where is the Gradient tool?",
        "answer": "toolbox:KritaFill/KisToolGradient",
    },
    {
        "id": "text_tool",
        "prompt": "Where is the Text tool?",
        "answer": "toolbox:SvgTextTool",
    },
    {
        "id": "brush_preset",
        "prompt": "Where is the round brush preset?",
        "answer": "preset:b)_Basic-5_Size_default",
    },
    {
        "id": "eraser_preset",
        "prompt": "Where is the eraser preset?",
        "answer": "preset:a)_Eraser_Circle",
    },
    {
        "id": "color_selector",
        "prompt": "Where do you choose a color?",
        "answer": "color:wheel",
    },
    {
        "id": "brush_size",
        "prompt": "Where do you change the brush size?",
        "answer": "toolbar:brush_size",
    },
    {
        "id": "add_layer",
        "prompt": "Where do you add a new layer?",
        "answer": "layer:bnAdd",
    },
    {
        "id": "delete_layer",
        "prompt": "Where do you delete a layer?",
        "answer": "layer:bnDelete",
    },
    {
        "id": "raise_layer",
        "prompt": "Where do you move a layer up?",
        "answer": "layer:bnRaise",
    },
    {
        "id": "lower_layer",
        "prompt": "Where do you move a layer down?",
        "answer": "layer:bnLower",
    },
]

# Alternate brush preset stem shown in some installs — still counts as correct.
RECALL_ANSWER_ALIASES = {
    "preset:b)_Basic-5_Size_default": ("preset:b)_Basic-1",),
}

RECALL_QUESTIONS = RECALL_QUESTIONS_ALL

# Maps recall question id to command PNG under commands/ (shown in the prompt).
RECALL_QUESTION_ICONS = {
    "brush_tool": "Freehand Brush Tool.png",
    "move_tool": "Move Tool.png",
    "line_tool": "Straight Line Tool.png",
    "rectangle_tool": "Rectangle Tool.png",
    "ellipse_tool": "Ellipse Tool.png",
    "fill_tool": "Fill Tool.png",
    "gradient_tool": "Gradient Tool.png",
    "text_tool": "Text tool.png",
    "brush_preset": "Brush Preset.png",
    "eraser_preset": "Eraser Preset.png",
    "add_layer": "Add layer.png",
    "delete_layer": "Delete layer.png",
    "raise_layer": "Move up.png",
    "lower_layer": "Move down.png",
}


def format_recall_prompt_html(question):
    """Return (text, rich_text) for the recall question banner."""
    prompt = question.get("prompt") or ""
    icon_file = RECALL_QUESTION_ICONS.get(question.get("id"))
    if not icon_file:
        return prompt, False
    icon_path = os.path.join(COMMANDS_DIR, icon_file)
    if not os.path.isfile(icon_path):
        return prompt, False
    icon_url = html.escape(Path(icon_path).as_uri())
    text = (
        '<span style="font-size:18px; font-weight:bold;">%s</span>'
        ' <img src="%s" height="28" style="vertical-align:middle;" />'
        % (html.escape(prompt), icon_url))
    return text, True


def _normalize_recall_cmd(cmd):
    """Normalize answer ids for comparison (preset stems vary by case)."""
    if not cmd:
        return ""
    s = str(cmd).strip()
    if s.startswith("preset:"):
        return "preset:" + s[7:].lower()
    return s


def recall_answer_matches(expected, clicked):
    """True if clicked command id matches expected (including preset aliases)."""
    if not expected or not clicked:
        return False
    exp = _normalize_recall_cmd(expected)
    clk = _normalize_recall_cmd(clicked)
    if clk == exp:
        return True
    for alias in RECALL_ANSWER_ALIASES.get(expected, ()):
        if clk == _normalize_recall_cmd(alias):
            return True
    return False


def recall_score_percent(results, total_questions=None):
    """Return whole-number score (0–100) from recall responses."""
    total = total_questions
    if total is None:
        total = len(results or [])
    if total <= 0:
        return 0
    correct = sum(1 for r in (results or []) if r.get("correct"))
    return int(round(100.0 * correct / total))


def prepare_recall_questions(trial=False):
    """Build question list: trial = 5 random; otherwise all 16, shuffled."""
    pool = list(RECALL_QUESTIONS_ALL)
    if trial:
        count = min(TRIAL_RECALL_QUESTION_COUNT, len(pool))
        picked = random.sample(pool, count)
        random.shuffle(picked)
        return picked
    out = list(pool)
    random.shuffle(out)
    return out


def recall_timing(trial=False):
    """Per-question and whole-phase time limits for this recall block."""
    if trial:
        return {
            "trial": True,
            "question_time_sec": TRIAL_RECALL_QUESTION_TIME_SEC,
            "phase_time_sec": None,
            "question_count": TRIAL_RECALL_QUESTION_COUNT,
        }
    return {
        "trial": False,
        "question_time_sec": RECALL_QUESTION_TIME_SEC,
        "phase_time_sec": RECALL_PHASE_TIME_SEC,
        "question_count": len(RECALL_QUESTIONS_ALL),
    }


def recall_side_panel_message(opening=False, practice=False):
    if opening:
        return dict(RECALL_OPENING_SIDE_PANEL)
    if practice:
        return dict(RECALL_PRACTICE_SIDE_PANEL)
    return dict(RECALL_SIDE_PANEL)


def run_recall_intro():
    """Legacy fullscreen intro (not used during recall UI)."""
    return run_tutorial_intro(RECALL_INTRO["title"], RECALL_INTRO["body"])
