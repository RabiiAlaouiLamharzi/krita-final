"""Step-by-step learning instructions shown during timed tutorial blocks."""

import html
import os
import re

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
COMMANDS_DIR = os.path.join(PLUGIN_DIR, "commands")
IMAGES_DIR = os.path.join(PLUGIN_DIR, "images")

# Maps {marker} in step text to PNG filename under commands/.
COMMAND_ICONS = {
    "Add layer": "Add layer.png",
    "Delete layer": "Delete layer.png",
    "Gradient Tool": "Gradient Tool.png",
    "Ellipse Tool": "Ellipse Tool.png",
    "Fill Tool": "Fill Tool.png",
    "Move Tool": "Move Tool.png",
    "Straight Line Tool": "Straight Line Tool.png",
    "Freehand Brush Tool": "Freehand Brush Tool.png",
    "Text Tool": "Text tool.png",
    "Rectangle Tool": "Rectangle Tool.png",
    "Eraser Preset": "Eraser Preset.png",
    "Move down": "Move down.png",
    "Move up": "Move up.png",
}

REFERENCE_IMAGES = {
    1: "tutorial 1.png",
    2: "tutorial 2.png",
    3: "tutorial 3.png",
    4: "tutorial 4.png",
    5: "tutorial 5.png",
    6: "tutorial 6.png",
}

# Qt rich text ignores CSS max-width on <img>; use explicit pixel dimensions.
GOAL_IMAGE_MAX_WIDTH = 140

LEARNING_TASK_DESCRIPTION = (
    "This task involves recreating this reference image as accurately as "
    "possible in Krita. Below are step-by-step instructions on how to "
    "produce the reference image.")


def _png_pixel_size(path):
    with open(path, "rb") as handle:
        handle.read(16)
        width = int.from_bytes(handle.read(4), "big")
        height = int.from_bytes(handle.read(4), "big")
    return width, height


def _goal_image_html(ref_name):
    ref_path = os.path.join(IMAGES_DIR, ref_name)
    if not os.path.isfile(ref_path):
        return ""
    try:
        src_w, src_h = _png_pixel_size(ref_path)
        scale = min(1.0, GOAL_IMAGE_MAX_WIDTH / max(src_w, 1))
        disp_w = max(1, int(src_w * scale))
        disp_h = max(1, int(src_h * scale))
    except (OSError, ValueError):
        disp_w, disp_h = GOAL_IMAGE_MAX_WIDTH, 212
    return (
        "<p style='font-size:14px; font-weight:bold; color:#ddd;"
        " margin:0 0 8px 0;'>Reference image</p>"
        '<p style="margin:0 0 18px 0; text-align:center;">'
        '<img src="images/%s" alt="Goal reference" width="%d" height="%d"'
        ' style="border:1px solid #555; border-radius:4px;" /></p>'
        % (html.escape(ref_name), disp_w, disp_h))

_ICON_RE = re.compile(r"\{([^}]+)\}")
_STEP_PREFIX_RE = re.compile(r"^(Step \d+):\s*(.*)$", re.IGNORECASE | re.DOTALL)


def parse_step_markers(step_text):
    return [m.strip() for m in _ICON_RE.findall(step_text or "")]


def step_expects_color(step_text):
    low = (step_text or "").lower()
    return "color wheel" in low or "pick " in low


def required_command_for_step(step_text):
    """Command the tutorial step asks for — always non-empty."""
    markers = parse_step_markers(step_text)
    if markers:
        return markers[0]
    low = (step_text or "").lower()
    if step_expects_color(step_text):
        return "color wheel"
    if "eraser preset" in low or "use the eraser" in low:
        return "Eraser Preset"
    if "gradient" in low:
        return "Gradient Tool"
    if "line width" in low or "brush size" in low:
        return "brush size"
    if "straight line" in low:
        return "Straight Line Tool"
    if "fill" in low:
        return "Fill Tool"
    if "text" in low:
        return "Text Tool"
    if "move" in low:
        return "Move Tool"
    if "draw" in low or "drag" in low:
        return "Freehand Brush Tool"
    return "canvas action"


def _phase_index(session_num, learn_num):
    return (max(1, int(session_num)) - 1) * 3 + max(1, int(learn_num))


def _icon_img_tag(name):
    filename = COMMAND_ICONS.get(name)
    display = html.escape(name)
    if not filename:
        return display
    path = os.path.join(COMMANDS_DIR, filename)
    if not os.path.isfile(path):
        return display
    src = "commands/%s" % html.escape(filename)
    return (
        '<span style="white-space:nowrap;">'
        '<img src="%s" height="22" alt="%s"'
        ' style="vertical-align:middle;margin-right:4px;" />'
        '<span style="font-weight:600; vertical-align:middle;">%s</span>'
        '</span>'
        % (src, display, display))


def render_step_text(step):
    """Replace {Command} markers with inline icon images."""
    parts = []
    last = 0
    for match in _ICON_RE.finditer(step):
        if match.start() > last:
            parts.append(html.escape(step[last:match.start()]))
        parts.append(_icon_img_tag(match.group(1).strip()))
        last = match.end()
    if last < len(step):
        parts.append(html.escape(step[last:]))
    return "".join(parts)


def render_step_html(step):
    """Format one step with a bold, underlined label and rendered body text."""
    match = _STEP_PREFIX_RE.match(step.strip())
    if match:
        label, body = match.group(1), match.group(2)
        label_html = (
            '<span style="font-weight:bold; text-decoration:underline;">'
            "%s:</span> " % html.escape(label))
        return label_html + render_step_text(body)
    return render_step_text(step)


TUTORIAL_1_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick light yellow",
    "Step 4: Drag bottom-to-top on the canvas to make a gradient",
    "Step 5: Create another gradient light blue, dragging from top-to-bottom",
    "Step 6: Click {Add layer} in Layers (to create a new layer for drawing the sun)",
    "Step 7: Click the {Ellipse Tool}",
    "Step 8: On the color wheel, pick golden yellow",
    "Step 9: Draw one big yellow circle (the sun)",
    "Step 10: Click the {Fill Tool} and fill the circle",
    "Step 11: Click the {Move Tool} and place the sun in the middle of the canvas",
    "Step 12: Click the {Straight Line Tool}",
    "Step 13: Adjust the width of the line you are drawing",
    "Step 14: On the color wheel, pick orange, then draw the sun rays one by one",
    "Step 15: Click {Add layer} in Layers (we will try to draw a smiley face on the sun :D)",
    "Step 16: Click the {Freehand Brush Tool}",
    "Step 17: On the color wheel, pick white",
    "Step 18: Draw two eyes and a smile on the sun. It doesn't look very good...",
    "Step 19: Use the {Eraser Preset} in the brush panel to remove the eyes and the smile we just drew. The layer created for the eyes and smile is no longer needed, so it can be removed if desired. To do this, we can use {Delete layer} in Layers",
    "Step 20: Click the {Text Tool}, drag to define a text box, and type \"The Sun\". In Krita, text is created as its own layer by default",
    "Step 21: Select the newly created text, then choose the brown color from the color wheel, and apply it to it",
    "Step 22: Click the {Move Tool} and center the text on the canvas",
]

TUTORIAL_2_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick yellow",
    "Step 4: Drag top-to-bottom on the canvas to make a gradient",
    "Step 5: Click {Add layer} in Layers",
    "Step 6: Click the {Rectangle Tool}",
    "Step 7: On the color wheel, pick dark red then drag to draw the Olympic medal lanyard",
    "Step 8: Click the {Move Tool} and center the shape on the canvas",
    "Step 9: Click the {Straight Line Tool}",
    "Step 10: Use the straight line tool to create the striped pattern on the Olympic medal lanyard",
    "Step 11: Use the straight line tool to draw the connector between the lanyard and the medal",
    "Step 12: Click the {Fill Tool}",
    "Step 13: On the color wheel, pick yellow, and fill the top and bottom stripes of the lanyard",
    "Step 14: On the color wheel, pick white, and fill the middle stripe of the lanyard",
    "Step 15: Click {Add layer} in Layers",
    "Step 16: Click the {Ellipse Tool}",
    "Step 17: On the color wheel, pick black then drag to draw the circular Olympic medal",
    "Step 18: Click the {Move Tool} to center the medal and connect it to the lanyard",
    "Step 19: Click the {Ellipse Tool} to create another circle that outlines the medal",
    "Step 20: Click the {Move Tool} to position the outline over the circular medal",
    "Step 21: Click the {Text Tool}, drag to define a text box, and type \"1st\"",
    "Step 22: Select the newly created text, then choose the dark red color from the color wheel, and apply it to it",
    "Step 23: Click the {Move Tool} to center the text on the medal",
]

TUTORIAL_3_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick light blue",
    "Step 4: Drag top-to-bottom on the canvas to make a gradient (the sky)",
    "Step 5: Click {Add layer} in Layers",
    "Step 6: Click the {Rectangle Tool}",
    "Step 7: On the color wheel, pick dark green then drag to draw the grass beneath the house",
    "Step 8: Click the {Fill Tool} then click inside the grass to fill it",
    "Step 9: Click {Add layer} in Layers",
    "Step 10: Click the {Rectangle Tool}",
    "Step 11: On the color wheel, pick brown then drag to draw the body of the house",
    "Step 12: Click the {Move Tool} to center the shape on the canvas",
    "Step 13: Click the {Fill Tool} then click inside the house body to fill it",
    "Step 14: Click {Add layer} in Layers",
    "Step 15: Click the {Straight Line Tool}",
    "Step 16: On the color wheel, pick red then drag to draw the triangular roof of the house",
    "Step 17: Click the {Fill Tool} then click inside the roof to fill it",
    "Step 18: Click {Add layer} in Layers",
    "Step 19: Click the {Rectangle Tool}",
    "Step 20: On the color wheel, pick yellow then drag to draw a square window on the house",
    "Step 21: Click the {Fill Tool} then click inside the window to fill it",
    "Step 22: Click the {Straight Line Tool} and set a smaller line width",
    "Step 23: On the color wheel, pick black then drag to draw the window dividers",
    "Step 24: Click {Add layer} in Layers",
    "Step 25: Click the {Rectangle Tool}",
    "Step 26: On the color wheel, pick light brown then drag to draw the house door",
    "Step 27: Click the {Fill Tool} then click inside the door to fill it",
    "Step 28: Click the {Freehand Brush Tool}",
    "Step 29: On the color wheel, pick black then drag to draw the door knob",
    "Step 30: Click the {Text Tool}, drag to define a text box, and type \"The House\"",
    "Step 31: Click the {Move Tool} to center the text on the canvas",
]

TUTORIAL_4_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick floral white",
    "Step 4: Drag top-to-bottom on the canvas to make a gradient",
    "Step 5: Click {Add layer} in Layers",
    "Step 6: Click the {Rectangle Tool}",
    "Step 7: On the color wheel, pick dark orange then drag to draw the plant's pot, which forms its base",
    "Step 8: Click the {Fill Tool} then click inside the pot to fill it",
    "Step 9: Click the {Move Tool} to center the pot on the canvas",
    "Step 10: Click the {Rectangle Tool} and drag to create the rim (the top edge of the pot)",
    "Step 11: Click the {Fill Tool} then click inside the rim to fill it",
    "Step 12: Click {Add layer} in Layers",
    "Step 13: Click the {Rectangle Tool}",
    "Step 14: On the color wheel, pick dark brown then drag to draw the plant's trunk",
    "Step 15: Click the {Fill Tool} then click inside the trunk to fill it",
    "Step 16: Click the {Move Tool} to center the trunk within the plant pot",
    "Step 17: Click {Add layer} in Layers",
    "Step 18: Click the {Ellipse Tool}",
    "Step 19: On the color wheel, pick green then drag to draw a leaf ball on top of the trunk",
    "Step 20: Click the {Fill Tool} then click inside the leaf ball to fill it",
    "Step 21: Click the {Move Tool} then position the leaf ball on the side of the trunk",
    "Step 22: Click {Add layer} in Layers",
    "Step 23: Click the {Ellipse Tool} to create a second leaf ball",
    "Step 24: On the color wheel, pick a different shade of green then drag to draw a second leaf ball on top of the trunk",
    "Step 25: Click the {Fill Tool} then click inside the leaf ball to fill it",
    "Step 26: Click {Add layer} in Layers",
    "Step 27: Click the {Ellipse Tool} to create a third leaf ball",
    "Step 28: On the color wheel, pick a different shade of green then drag to draw a third leaf ball on top of the trunk",
    "Step 29: Click the {Fill Tool} then click inside the leaf ball to fill it",
    "Step 30: Click the {Move Tool} then position the leaf ball on the side of the trunk",
    "Step 31: {Move down} in Layers to reorder the leaf balls until it looks better",
    "Step 32: On the color wheel, pick black",
    "Step 33: Click the {Text Tool}, drag to define a text box, and type \"The Tree\"",
    "Step 34: Click the {Move Tool} to center the text on the canvas",
]

TUTORIAL_5_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick light green",
    "Step 4: Drag top-to-bottom on the canvas to make a gradient",
    "Step 5: Click the {Ellipse Tool}",
    "Step 6: On the color wheel, pick light gray then drag to draw the plate for the fruit",
    "Step 7: Click the {Fill Tool} then click inside the plate to fill it",
    "Step 8: Click the {Move Tool} to center the plate on the canvas",
    "Step 9: Click {Add layer} in Layers",
    "Step 10: Click the {Ellipse Tool}",
    "Step 11: On the color wheel, pick red then drag to draw an apple on the plate",
    "Step 12: Click the {Fill Tool} then click inside the apple to fill it",
    "Step 13: Click the {Move Tool} to place the apple in the middle of the plate",
    "Step 14: Click the {Straight Line Tool} to draw the apple stem",
    "Step 15: On the color wheel, pick brown then drag to draw the stem",
    "Step 16: Click the {Ellipse Tool}",
    "Step 17: On the color wheel, pick green then drag to draw a leaf on the stem",
    "Step 18: Click the {Fill Tool} then click inside the leaf to fill it",
    "Step 19: Click the {Freehand Brush Tool}",
    "Step 20: Use the {Eraser Preset} in the brush panel to reshape the leaf so it looks more natural",
    "Step 21: On the color wheel, pick black",
    "Step 22: Click the {Text Tool}, drag to define a text box, and type \"The Apple\"",
    "Step 23: Click the {Move Tool} to center the text on the canvas",
]

TUTORIAL_6_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick blue",
    "Step 4: Drag top-to-bottom on the canvas to make a gradient",
    "Step 5: Create another gradient light cyan, dragging from bottom-to-top",
    "Step 6: Click {Add layer} in Layers",
    "Step 7: Click the {Freehand Brush Tool}",
    "Step 8: On the color wheel, pick red, increase the brush size, then drag to draw the first rainbow ray.",
    "Step 9: On the color wheel, pick orange then drag to draw the second rainbow ray.",
    "Step 10: On the color wheel, pick yellow then drag to draw the third rainbow ray.",
    "Step 11: On the color wheel, pick green then drag to draw the fourth rainbow ray.",
    "Step 12: On the color wheel, pick blue then drag to draw the fifth rainbow ray.",
    "Step 13: Click {Add layer} in Layers",
    "Step 14: On the color wheel, pick white, then drag to draw a cloud beneath the rainbow",
    "Step 15: Click the {Fill Tool} then click inside the cloud to fill it",
    "Step 16: Click the {Freehand Brush Tool}",
    "Step 17: On the color wheel, pick white, then drag to draw a second cloud beneath the rainbow",
    "Step 18: Click the {Fill Tool} then click inside the cloud to fill it",
    "Step 19: Click the {Freehand Brush Tool}, then fill in any remaining uncolored spots in the cloud",
    "Step 20: On the color wheel, pick black",
    "Step 21: Click the {Text Tool}, drag to define a text box, and type \"Color\"",
    "Step 22: Click the {Move Tool} to center the text on the canvas",
]

LEARNING_STEPS = {
    1: TUTORIAL_1_STEPS,
    2: TUTORIAL_2_STEPS,
    3: TUTORIAL_3_STEPS,
    4: TUTORIAL_4_STEPS,
    5: TUTORIAL_5_STEPS,
    6: TUTORIAL_6_STEPS,
}


def format_learning_step_html(title, step_text, step_number, total_steps, phase=1):
    """One instruction step plus reference image for the side panel."""
    html_out = (
        "<p style='font-size:22px; font-weight:bold; margin:0 0 12px 0;'>%s</p>"
        "<p style='font-size:14px; line-height:1.5; color:#ddd;"
        " margin:0 0 16px 0;'>%s</p>"
        % (html.escape(title), html.escape(LEARNING_TASK_DESCRIPTION)))
    ref_name = REFERENCE_IMAGES.get(int(phase))
    if ref_name:
        html_out += _goal_image_html(ref_name)
    html_out += (
        "<p style='font-size:13px; color:#aaa; margin:0 0 10px 0;'>"
        "Step %d of %d</p>"
        % (int(step_number), int(total_steps)))
    html_out += (
        "<p style='font-size:16px; line-height:1.55; margin:0;'>"
        "%s</p>" % render_step_html(step_text))
    return html_out


def format_learning_steps_html(title, steps, phase=1):
    html_out = (
        "<p style='font-size:22px; font-weight:bold; margin:0 0 12px 0;'>%s</p>"
        "<p style='font-size:14px; line-height:1.5; color:#ddd;"
        " margin:0 0 16px 0;'>%s</p>"
        % (html.escape(title), html.escape(LEARNING_TASK_DESCRIPTION)))
    ref_name = REFERENCE_IMAGES.get(int(phase))
    if ref_name:
        html_out += _goal_image_html(ref_name)
    html_out += (
        "<ul style='margin:0; padding-left:24px; list-style-type:disc;'>")
    for step in steps:
        html_out += (
            "<li style='font-size:15px; line-height:1.55; margin:0 0 12px 0;'>"
            "%s</li>" % render_step_html(step))
    html_out += "</ul>"
    return html_out


def get_learning_instructions(session_info, learn_num):
    """Return title and step list for the right-hand instruction panel."""
    session_num = 1
    if session_info:
        session_num = int(session_info.get("session", 1) or 1)
    phase = _phase_index(session_num, learn_num)
    steps = list(LEARNING_STEPS.get(phase, TUTORIAL_1_STEPS))
    title = "Learning Phase %d" % phase
    return {
        "title": title,
        "steps": steps,
        "phase": phase,
    }
