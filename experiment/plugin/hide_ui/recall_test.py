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
TRIAL_RECALL_QUESTION_TIME_SEC = 10
TRIAL_RECALL_QUESTION_COUNT = 5

# Legacy alias
RECALL_TIME_SEC = RECALL_QUESTION_TIME_SEC

RECALL_SIDE_PANEL = {
    "title": "Command recall test",
    "body": "",  # built by recall_side_panel_message()
}

RECALL_PRACTICE_SIDE_PANEL = {
    "title": "Command recall test",
    "body": "",
}

RECALL_OPENING_SIDE_PANEL = {
    "title": "Recall: Layout A",
    "body": "",
}


def _recall_instruction_body_html(question_time_sec, intro_paragraphs=()):
    sec = max(1, int(question_time_sec))
    parts = []
    for para in intro_paragraphs:
        text = str(para or "").strip()
        if text:
            parts.append("<p style='margin:10px 0;'>%s</p>" % text)
    parts.append(
        "<p style='margin:14px 0;'><b>Commands are hidden behind white boxes "
        "on the Krita interface. Read each question, then click the white box "
        "that hides the correct command for that question.</b></p>")
    parts.append(
        "<p style='margin:14px 0;'><b>Answer as fast as you can. You have at most "
        "%d seconds per question.</b></p>" % sec)
    parts.append(
        "<p style='margin:14px 0;'>When you are ready, click "
        "<b>Start first question</b> on the panel to the right.</p>")
    return "".join(parts)

RECALL_INTRO = {
    "title": RECALL_SIDE_PANEL["title"],
    "body": (
        "Commands are hidden behind white boxes on the Krita interface. "
        "Read each question at the top and click the box that hides the correct "
        "command. Answer as fast as you can; you have at most 10 seconds per question."),
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
        "prompt": "Where do you change layer order to bring a layer up?",
        "answer": "layer:bnRaise",
    },
    {
        "id": "lower_layer",
        "prompt": "Where do you change layer order to bring a layer down?",
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


def _cluster_1d(values, tol):
    """Cluster scalar positions; return sorted cluster centers."""
    if not values:
        return []
    ordered = sorted(values)
    clusters = [[ordered[0]]]
    for value in ordered[1:]:
        if abs(value - clusters[-1][-1]) <= tol:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(c) / float(len(c)) for c in clusters]


def _nearest_cluster_index(value, centers):
    best_i = 0
    best_d = None
    for index, center in enumerate(centers):
        dist = abs(value - center)
        if best_d is None or dist < best_d:
            best_d = dist
            best_i = index
    return best_i


def _assign_overlay_slots(overlays):
    """Assign (col, row) from overlay centers using shared x/y bins.

    Columns share similar x across rows, so one-command-below stays offset_x=0.
    Returns dict cmd_id -> (col, row). col/row increase rightward / downward.
    """
    items = [dict(o) for o in (overlays or []) if o.get("cmd_id")]
    if not items:
        return {}
    widths = [max(1, int(o.get("w") or 1)) for o in items]
    heights = [max(1, int(o.get("h") or 1)) for o in items]
    tol_x = max(12, int(0.55 * (sum(widths) / float(len(widths)))))
    tol_y = max(12, int(0.55 * (sum(heights) / float(len(heights)))))
    col_centers = _cluster_1d([int(o["cx"]) for o in items], tol_x)
    row_centers = _cluster_1d([int(o["cy"]) for o in items], tol_y)
    slots = {}
    for item in items:
        col = _nearest_cluster_index(int(item["cx"]), col_centers)
        row = _nearest_cluster_index(int(item["cy"]), row_centers)
        slots[str(item["cmd_id"])] = (col, row)
    return slots


def _find_overlay(overlays, cmd_id, match_expected=False):
    """Find overlay entry for a command id.

    If match_expected is True, also accept preset aliases for that answer id.
    """
    if not cmd_id:
        return None
    for item in overlays or []:
        cand = item.get("cmd_id")
        if not cand:
            continue
        if _normalize_recall_cmd(cand) == _normalize_recall_cmd(cmd_id):
            return item
        if match_expected and recall_answer_matches(cmd_id, cand):
            return item
    return None


def compute_recall_click_error(overlays, expected_cmd, clicked_cmd,
                               click_x=None, click_y=None):
    """Compute command-slot and pixel error from a recall click.

    Slot convention: 0 = correct; positive x = clicked right of correct;
    positive y = clicked below correct.

    Pixel offsets use the click point when given, else the clicked overlay center,
    relative to the correct overlay center.

    Returns a dict with slot_offset_x/y, slot_distance, pixel_offset_x/y,
    pixel_distance (empty strings when unknown).
    """
    empty = {
        "slot_offset_x": "",
        "slot_offset_y": "",
        "slot_distance": "",
        "pixel_offset_x": "",
        "pixel_offset_y": "",
        "pixel_distance": "",
    }
    if not expected_cmd or not clicked_cmd or not overlays:
        return empty

    correct = _find_overlay(overlays, expected_cmd, match_expected=True)
    clicked = _find_overlay(overlays, clicked_cmd, match_expected=False)
    if correct is None:
        return empty

    cx = int(correct["cx"])
    cy = int(correct["cy"])
    if click_x is not None and click_y is not None:
        px = int(click_x)
        py = int(click_y)
    elif clicked is not None:
        px = int(clicked["cx"])
        py = int(clicked["cy"])
    else:
        return empty

    dx = px - cx
    dy = py - cy
    dist = (dx * dx + dy * dy) ** 0.5
    out = {
        "slot_offset_x": "",
        "slot_offset_y": "",
        "slot_distance": "",
        "pixel_offset_x": int(dx),
        "pixel_offset_y": int(dy),
        "pixel_distance": round(dist, 1),
    }

    if clicked is None:
        return out

    slots = _assign_overlay_slots(overlays)
    correct_slot = None
    clicked_slot = None
    for cmd_id, slot in slots.items():
        if recall_answer_matches(expected_cmd, cmd_id):
            correct_slot = slot
        if _normalize_recall_cmd(cmd_id) == _normalize_recall_cmd(clicked_cmd):
            clicked_slot = slot
    if correct_slot is None or clicked_slot is None:
        return out

    sox = int(clicked_slot[0] - correct_slot[0])
    soy = int(clicked_slot[1] - correct_slot[1])
    out["slot_offset_x"] = sox
    out["slot_offset_y"] = soy
    out["slot_distance"] = abs(sox) + abs(soy)
    return out


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
    """Per-question time limits for this recall block (no whole-phase cap)."""
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
        "phase_time_sec": None,
        "question_count": len(RECALL_QUESTIONS_ALL),
    }


def recall_side_panel_message(opening=False, practice=False, question_time_sec=None):
    if question_time_sec is None:
        question_time_sec = (
            TRIAL_RECALL_QUESTION_TIME_SEC if practice else RECALL_QUESTION_TIME_SEC)
    if opening:
        intro = (
            "Before introducing the new tutorials, you will begin Session 2 "
            "with a recall test to assess whether you still remember the "
            "positions of the commands you learned in Session 1.")
        return {
            "title": RECALL_OPENING_SIDE_PANEL["title"],
            "body": _recall_instruction_body_html(
                question_time_sec, intro_paragraphs=(intro,)),
        }
    if practice:
        intro = "This is a practice recall trial."
        return {
            "title": RECALL_PRACTICE_SIDE_PANEL["title"],
            "body": _recall_instruction_body_html(
                question_time_sec, intro_paragraphs=(intro,)),
        }
    return {
        "title": RECALL_SIDE_PANEL["title"],
        "body": _recall_instruction_body_html(question_time_sec),
    }


def run_recall_intro():
    """Legacy fullscreen intro (not used during recall UI)."""
    return run_tutorial_intro(RECALL_INTRO["title"], RECALL_INTRO["body"])
