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
    "Round brush preset": "Brush Preset.png",
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

IMAGES_STEPS_DIR = os.path.join(IMAGES_DIR, "images-steps")

# Step numbers at which the side-panel reference image updates (phase = tutorial 1–6).
PROGRESSIVE_REFERENCE_STEPS = {
    1: (1, 6, 17, 35),
    2: (1, 6, 16, 21, 30),
    3: (1, 6, 14, 22, 28, 33, 38, 57),
    4: (1, 6, 13, 18, 26, 34, 49, 64),
    5: (1, 5, 13, 22, 28, 40),
    6: (1, 8, 14, 18, 24, 27, 45),
}

# Qt rich text ignores CSS max-width on <img>; use explicit pixel dimensions.
GOAL_IMAGE_MAX_WIDTH = 140

LEARNING_TASK_DESCRIPTION = (
    "In this learning phase, follow the step-by-step instructions in order to "
    "create a simple drawing in Krita. Complete each step, then click Next to "
    "continue. As you progress, reference images will appear at certain steps "
    "to show how your canvas should look at that point, so you can check your "
    "work and stay on track.")


def _png_pixel_size(path):
    with open(path, "rb") as handle:
        handle.read(16)
        width = int.from_bytes(handle.read(4), "big")
        height = int.from_bytes(handle.read(4), "big")
    return width, height


def _goal_image_html(src_relative):
    """Build img tag; src_relative is under the plugin dir (forward slashes)."""
    ref_path = os.path.join(
        PLUGIN_DIR, src_relative.replace("/", os.path.sep))
    if not os.path.isfile(ref_path):
        return ""
    try:
        src_w, src_h = _png_pixel_size(ref_path)
        scale = min(1.0, GOAL_IMAGE_MAX_WIDTH / max(src_w, 1))
        disp_w = max(1, int(src_w * scale))
        disp_h = max(1, int(src_h * scale))
    except (OSError, ValueError):
        disp_w, disp_h = GOAL_IMAGE_MAX_WIDTH, 212
    src_attr = html.escape(src_relative.replace("\\", "/"))
    return (
        "<p style='font-size:14px; font-weight:bold; color:#ddd;"
        " margin:0 0 8px 0;'>Reference image</p>"
        '<p style="margin:0 0 18px 0; text-align:center;">'
        '<img src="%s" alt="Goal reference" width="%d" height="%d"'
        ' style="border:1px solid #555; border-radius:4px;" /></p>'
        % (src_attr, disp_w, disp_h))


def _checkpoint_step_for_progress(phase, step_number):
    """Latest checkpoint step number <= current tutorial step."""
    checkpoints = PROGRESSIVE_REFERENCE_STEPS.get(int(phase))
    if not checkpoints:
        return None
    current = max(1, int(step_number))
    active = None
    for cp in checkpoints:
        if cp <= current:
            active = cp
        else:
            break
    return active


def _progressive_reference_src(phase, step_number):
    """Relative URL path under plugin root for the current checkpoint image."""
    cp = _checkpoint_step_for_progress(phase, step_number)
    if cp is None:
        return None
    rel = "images/images-steps/tuto %d/step %d.png" % (int(phase), int(cp))
    full = os.path.join(PLUGIN_DIR, rel.replace("/", os.path.sep))
    if os.path.isfile(full):
        return rel
    return None


def _learning_reference_html(phase, step_number):
    src = _progressive_reference_src(phase, step_number)
    if src:
        return _goal_image_html(src)
    return ""

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
    if "round brush preset" in low:
        return "Round brush preset"
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
    "Step 4: Drag from bottom to top on the canvas to make a gradient",
    "Step 5: On the color wheel, pick light blue",
    "Step 6: Create another gradient in light blue, dragging from top to bottom",
    "Step 7: Click {Add layer} in Layers",
    "Step 8: Click the {Ellipse Tool}",
    "Step 9: On the color wheel, pick golden yellow",
    "Step 10: Draw one big yellow circle (the sun)",
    "Step 11: Click the {Fill Tool}",
    "Step 12: Fill the circle",
    "Step 13: To test, press {Move down} in Layers to try moving the sun layer down in the layer stack and see how it affects the image.",
    "Step 14: Press {Move up} in Layers to bring the sun layer back to the order you had before, so we can continue the tutorial.",
    "Step 15: Click the {Move Tool}",
    "Step 16: Place the sun approximately in the middle of the canvas horizontally, as shown in the reference image.",
    "Step 17: Click the {Straight Line Tool}",
    "Step 18: Adjust the width of the line you are drawing (around 40–45 px)",
    "Step 19: On the color wheel, pick orange",
    "Step 20: Draw the sun rays one by one",
    "Step 21: Click {Add layer} in Layers",
    "Step 22: Click the {Rectangle Tool}",
    "Step 23: On the color wheel, pick dark blue",
    "Step 24: Drag to draw a thin strip along the bottom of the canvas (the ground)",
    "Step 25: Click the {Fill Tool}",
    "Step 26: Click inside the ground strip to fill it",
    "Step 27: Maybe it's better to get rid of it… Use {Delete layer} in Layers to remove the ground layer",
    "Step 28: Click {Add layer} in Layers",
    "Step 29: Click the {Freehand Brush Tool}",
    "Step 30: On the color wheel, pick white",
    "Step 31: Try to draw a smiley face on the sun :D (two eyes and a smile)",
    "Step 32: It doesn't look very good… Use the {Eraser Preset} in the brush panel to remove the eyes and the smile we just drew.",
    "Step 33: In the brush panel, switch back to the {Round brush preset}. This allows Krita to switch the mode from erasing back to Normal (writing/painting).",
    "Step 34: The layer created for the eyes and smile is no longer needed, so please remove it. To do this, use {Delete layer} in Layers",
    "Step 35: Click the {Text Tool}",
    "Step 36: Drag to define a text box, and type \"The Sun\". In Krita, text is created as its own layer by default",
    "Step 37: Select the newly created text and choose brown from the color wheel, then apply it to the text",
    "Step 38: Click the {Move Tool}",
    "Step 39: Center the text on the canvas like the reference image shows",
]

TUTORIAL_2_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick yellow",
    "Step 4: Drag top to bottom on the canvas to make a gradient",
    "Step 5: Click {Add layer} in Layers",
    "Step 6: Click the {Rectangle Tool}",
    "Step 7: On the color wheel, pick dark red",
    "Step 8: Drag to draw the Olympic medal lanyard",
    "Step 9: To practice, press {Move down} in Layers to try moving the Olympic medal lanyard layer in the layer stack.",
    "Step 10: Press {Move up} in Layers to bring the lanyard layer back to the order we had before, so we can continue the tutorial.",
    "Step 11: Click the {Move Tool}",
    "Step 12: Center the Olympic medal lanyard on the canvas",
    "Step 13: Click the {Straight Line Tool}",
    "Step 14: Adjust the width of the line you are drawing",
    "Step 15: Use the {Straight Line Tool} to create the striped pattern on the Olympic medal lanyard",
    "Step 16: Use the {Straight Line Tool} to draw the connector between the lanyard and the medal",
    "Step 17: On the color wheel, pick white",
    "Step 18: Click the {Fill Tool}",
    "Step 19: Fill the middle stripe of the lanyard, as shown in the reference image",
    "Step 20: Click {Add layer} in Layers",
    "Step 21: Click the {Ellipse Tool}",
    "Step 22: On the color wheel, pick black",
    "Step 23: Drag to draw the circular Olympic medal",
    "Step 24: Click the {Move Tool}",
    "Step 25: Center the medal and connect it to the lanyard",
    "Step 26: Click {Add layer} in Layers",
    "Step 27: Click the {Ellipse Tool} to create an inner circle that outlines the medal",
    "Step 28: Click the {Move Tool}",
    "Step 29: Position the inner circle over the circular medal, as shown in the reference image",
    "Step 30: Click {Add layer} in Layers",
    "Step 31: Click the {Freehand Brush Tool}",
    "Step 32: On the color wheel, pick white",
    "Step 33: Try to draw the text \"1st\" to say that this is a medal for a winner",
    "Step 34: Maybe it's better to use text for that, right? Let's first use the {Eraser Preset} in the brush panel to erase what we drew",
    "Step 35: Use {Delete layer} in Layers to remove that layer",
    "Step 36: In the brush panel, switch back to the {Round brush preset}",
    "Step 37: Click the {Text Tool}",
    "Step 38: Drag to define a text box, and type \"1st\".",
    "Step 39: Select the newly created text and choose dark red from the color wheel, then apply it to the text",
    "Step 40: Click the {Move Tool}",
    "Step 41: Center the text on the medal",
]

TUTORIAL_3_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick light blue",
    "Step 4: Drag top to bottom on the canvas to make a gradient (the sky)",
    "Step 5: Click {Add layer} in Layers",
    "Step 6: Click the {Rectangle Tool}",
    "Step 7: On the color wheel, pick dark green",
    "Step 8: Drag to draw the grass beneath the house, as shown in the reference image",
    "Step 9: Click the {Fill Tool}",
    "Step 10: Click inside the grass to fill it",
    "Step 11: Press {Move down} in Layers to try moving the grass layer down in the layer stack.",
    "Step 12: Press {Move up} in Layers to bring the grass layer back to the order you had before, so you can continue the tutorial.",
    "Step 13: Click {Add layer} in Layers",
    "Step 14: Click the {Rectangle Tool}",
    "Step 15: On the color wheel, pick brown",
    "Step 16: Drag to draw the body of the house, as shown in the reference image",
    "Step 17: Click the {Move Tool}",
    "Step 18: Center the house body on the canvas",
    "Step 19: Click the {Fill Tool}",
    "Step 20: Click inside the house body to fill it",
    "Step 21: Click {Add layer} in Layers",
    "Step 22: Click the {Straight Line Tool}",
    "Step 23: On the color wheel, pick red",
    "Step 24: Drag to draw the triangular roof of the house",
    "Step 25: Click the {Fill Tool}",
    "Step 26: Click inside the roof to fill it",
    "Step 27: Click {Add layer} in Layers",
    "Step 28: Click the {Rectangle Tool}",
    "Step 29: On the color wheel, pick yellow",
    "Step 30: Drag to draw one big square window on the house",
    "Step 31: Click the {Fill Tool}",
    "Step 32: Click inside the window to fill it",
    "Step 33: Click the {Straight Line Tool}",
    "Step 34: Set a smaller line width (30–35 px)",
    "Step 35: On the color wheel, pick black",
    "Step 36: Drag to draw the window dividers",
    "Step 37: Click {Add layer} in Layers",
    "Step 38: Click the {Rectangle Tool}",
    "Step 39: On the color wheel, pick light brown",
    "Step 40: Drag to draw the house door",
    "Step 41: Click the {Fill Tool}",
    "Step 42: Click inside the door to fill it",
    "Step 43: Click the {Freehand Brush Tool}",
    "Step 44: On the color wheel, pick black",
    "Step 45: Drag to draw the doorknob",
    "Step 46: Click {Add layer} in Layers",
    "Step 47: Click the {Ellipse Tool}",
    "Step 48: On the color wheel, pick golden yellow",
    "Step 49: Drag to draw a small sun in the sky",
    "Step 50: Click the {Fill Tool}",
    "Step 51: Fill the circle",
    "Step 52: Click the {Move Tool}",
    "Step 53: Place the sun approximately at the top of the canvas, to the right",
    "Step 54: It's not a sunny day, so we'd better erase the sun. Use the {Eraser Preset} in the brush panel to do so",
    "Step 55: Use {Delete layer} in Layers to remove the sun layer",
    "Step 56: In the brush panel, switch back to the {Round brush preset}",
    "Step 57: Click the {Text Tool}",
    "Step 58: Drag to define a text box, and type \"The House\".",
    "Step 59: Click the {Move Tool}",
    "Step 60: Center the text on the canvas like the reference image shows",
]

TUTORIAL_4_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick very light yellow",
    "Step 4: Drag top to bottom on the canvas to make a gradient",
    "Step 5: Click {Add layer} in Layers",
    "Step 6: Click the {Rectangle Tool}",
    "Step 7: On the color wheel, pick dark orange",
    "Step 8: Drag to draw the plant's pot, which forms its base",
    "Step 9: Click the {Fill Tool}",
    "Step 10: Click inside the pot to fill it",
    "Step 11: Click the {Move Tool}",
    "Step 12: Center the pot on the canvas",
    "Step 13: Click the {Rectangle Tool}",
    "Step 14: Drag to create the rim (the top edge of the pot), as shown in the reference image",
    "Step 15: Click the {Fill Tool}",
    "Step 16: Click inside the rim to fill it",
    "Step 17: Click {Add layer} in Layers",
    "Step 18: Click the {Rectangle Tool}",
    "Step 19: On the color wheel, pick dark brown",
    "Step 20: Drag to draw the plant's trunk",
    "Step 21: Click the {Fill Tool}",
    "Step 22: Click inside the trunk to fill it",
    "Step 23: Click the {Move Tool}",
    "Step 24: Center the trunk within the plant pot",
    "Step 25: Click {Add layer} in Layers",
    "Step 26: Click the {Ellipse Tool}",
    "Step 27: On the color wheel, pick green",
    "Step 28: Drag to draw a leaf ball on top of the trunk",
    "Step 29: Click the {Fill Tool}",
    "Step 30: Click inside the leaf ball to fill it",
    "Step 31: Click the {Move Tool}",
    "Step 32: Position the leaf ball in the middle of the trunk",
    "Step 33: Click {Add layer} in Layers",
    "Step 34: Click the {Ellipse Tool} to create a second leaf ball",
    "Step 35: On the color wheel, pick a different shade of green",
    "Step 36: Drag to draw a second leaf ball on top of the trunk",
    "Step 37: Click the {Fill Tool}",
    "Step 38: Click inside the leaf ball to fill it",
    "Step 39: Click the {Move Tool}",
    "Step 40: Position the leaf ball on the right side of the trunk",
    "Step 41: Click {Add layer} in Layers",
    "Step 42: Click the {Ellipse Tool} to create a third leaf ball",
    "Step 43: On the color wheel, pick a different shade of green",
    "Step 44: Drag to draw a third leaf ball on top of the trunk",
    "Step 45: Click the {Fill Tool}",
    "Step 46: Click inside the leaf ball to fill it",
    "Step 47: Click the {Move Tool}",
    "Step 48: Position the leaf ball on the left side of the trunk",
    "Step 49: Press {Move up} and {Move down} in Layers to reorder the leaf balls until it looks better",
    "Step 50: Click {Add layer} in Layers",
    "Step 51: Click the {Straight Line Tool}",
    "Step 52: On the color wheel, pick light brown",
    "Step 53: Adjust the width of the line you are drawing (25–30 px)",
    "Step 54: Draw lines on the trunk to create bark texture",
    "Step 55: This does not look very good… let's use the {Eraser Preset} in the brush panel to erase the lines",
    "Step 56: In the brush panel, switch back to the {Round brush preset}",
    "Step 57: Click the {Freehand Brush Tool}",
    "Step 58: On the color wheel, pick red",
    "Step 59: Draw small round fruits on the leaf balls to represent apples",
    "Step 60: No, I think it's better to delete this. Use the {Eraser Preset} in the brush panel to erase that mark",
    "Step 61: Use {Delete layer} in Layers to remove the current layer",
    "Step 62: In the brush panel, switch back to the {Round brush preset}",
    "Step 63: On the color wheel, pick black",
    "Step 64: Click the {Text Tool}",
    "Step 65: Drag to define a text box, and type \"The Tree\".",
    "Step 66: Click the {Move Tool}",
    "Step 67: Center the text on the canvas like the reference image shows",
]

TUTORIAL_5_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick light green",
    "Step 4: Drag top to bottom on the canvas to make a gradient",
    "Step 5: Click the {Ellipse Tool}",
    "Step 6: On the color wheel, pick light gray",
    "Step 7: Drag to draw a gray plate, as shown in the reference image",
    "Step 8: Click the {Fill Tool}",
    "Step 9: Click inside the plate to fill it",
    "Step 10: Click the {Move Tool}",
    "Step 11: Center the plate on the canvas",
    "Step 12: Click {Add layer} in Layers",
    "Step 13: Click the {Ellipse Tool}",
    "Step 14: On the color wheel, pick red",
    "Step 15: Drag to draw an apple on the plate",
    "Step 16: Click the {Fill Tool}",
    "Step 17: Click inside the apple to fill it",
    "Step 18: Click the {Move Tool}",
    "Step 19: Place the apple in the middle of the plate",
    "Step 20: Press {Move down} in Layers to move the apple behind the plate and see what it looks like.",
    "Step 21: Press {Move up} in Layers to bring the apple layer back to the order you had before, so we can continue the tutorial.",
    "Step 22: Click the {Straight Line Tool}",
    "Step 23: Adjust the width of the line you are drawing (25–30 px)",
    "Step 24: On the color wheel, pick brown",
    "Step 25: Drag to draw the apple stem",
    "Step 26: Click the {Ellipse Tool}",
    "Step 27: On the color wheel, pick green",
    "Step 28: Drag to draw a leaf on the stem",
    "Step 29: Click the {Fill Tool}",
    "Step 30: Click inside the leaf to fill it",
    "Step 31: Click the {Freehand Brush Tool}",
    "Step 32: Use the {Eraser Preset} in the brush panel to reshape the leaf so it looks more natural",
    "Step 33: In the brush panel, switch back to the {Round brush preset}",
    "Step 34: Click {Add layer} in Layers",
    "Step 35: Click the {Rectangle Tool}",
    "Step 36: On the color wheel, pick dark green",
    "Step 37: Drag to draw a rectangle on the canvas that will serve as the table on which the plate sits",
    "Step 38: It does not look good! Use {Delete layer} in Layers to remove the rectangle layer",
    "Step 39: On the color wheel, pick black",
    "Step 40: Click the {Text Tool}",
    "Step 41: Drag to define a text box, and type \"The Apple\".",
    "Step 42: Click the {Move Tool}",
    "Step 43: Center the text on the canvas like the reference image shows",
]

TUTORIAL_6_STEPS = [
    "Step 1: Click {Add layer} in Layers",
    "Step 2: Click the {Gradient Tool}",
    "Step 3: On the color wheel, pick blue",
    "Step 4: Drag top to bottom on the canvas to make a gradient",
    "Step 5: On the color wheel, pick light cyan",
    "Step 6: Create another gradient in light cyan, dragging from bottom to top",
    "Step 7: Click {Add layer} in Layers",
    "Step 8: Click the {Freehand Brush Tool}",
    "Step 9: On the color wheel, pick red",
    "Step 10: Adjust the width of the line you are drawing (35–45 px)",
    "Step 11: Drag to draw the first rainbow ray",
    "Step 12: Press {Move down} in Layers to try moving the rainbow layer under the gradient to see how it looks.",
    "Step 13: Definitely not a good look. Press {Move up} in Layers to bring the rainbow layer back to the order we had before.",
    "Step 14: On the color wheel, pick orange",
    "Step 15: Drag to draw the second rainbow ray",
    "Step 16: On the color wheel, pick yellow",
    "Step 17: Drag to draw the third rainbow ray",
    "Step 18: On the color wheel, pick green",
    "Step 19: Drag to draw the fourth rainbow ray",
    "Step 20: On the color wheel, pick blue",
    "Step 21: Drag to draw the fifth rainbow ray",
    "Step 22: Click {Add layer} in Layers",
    "Step 23: On the color wheel, pick white",
    "Step 24: Drag to draw a cloud beneath the rainbow",
    "Step 25: Click the {Fill Tool}",
    "Step 26: Click inside the cloud to fill it",
    "Step 27: Click the {Freehand Brush Tool}",
    "Step 28: Drag to draw a second cloud beneath the rainbow",
    "Step 29: Click the {Fill Tool}",
    "Step 30: Click inside the cloud to fill it",
    "Step 31: Click {Add layer} in Layers",
    "Step 32: Click the {Straight Line Tool}",
    "Step 33: Adjust the width of the line you are drawing",
    "Step 34: On the color wheel, pick gray",
    "Step 35: Draw small short lines on the cloud to add more details for decoration",
    "Step 36: Click the {Rectangle Tool}",
    "Step 37: Drag to draw small gray rectangles on the cloud to add more details for decoration",
    "Step 38: Click the {Ellipse Tool}",
    "Step 39: Drag to draw small gray circles on the cloud to add more details for decoration",
    "Step 40: Click the {Freehand Brush Tool}",
    "Step 41: Use the {Eraser Preset} in the brush panel to erase all of that",
    "Step 42: Use {Delete layer} in Layers to remove that layer",
    "Step 43: In the brush panel, switch back to the {Round brush preset}",
    "Step 44: On the color wheel, pick black",
    "Step 45: Click the {Text Tool}",
    "Step 46: Drag to define a text box, and type \"Color\".",
    "Step 47: Click the {Move Tool}",
    "Step 48: Center the text on the canvas like the reference image shows",
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
    html_out += _learning_reference_html(phase, step_number)
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
    html_out += _learning_reference_html(phase, 1)
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
