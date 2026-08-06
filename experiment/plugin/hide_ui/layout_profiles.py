"""Study interface layout profiles for the Krita UI rearrangement experiment.

Layout A:       Left: Toolbox | Right: Color, Layers, Brushes (top to bottom)
A + C1:         Left: Toolbox | Right: Color, Layers | Brushes in top toolbar
A + C1 + C2:    Left: —       | Right: Color, Layers | Brushes in top toolbar | Bottom: Toolbox
Layout B:       Left: Layers  | Right: Color         | Brushes in top toolbar | Bottom: Toolbox

Order changes happen only when that panel itself moves:
  - Brushes move to toolbar (A_C1+)     -> swap round brush / eraser
  - Toolbox moves to bottom (A_C1_C2+)  -> reshuffle toolbox tools
  - Layers move to left (B)             -> swap layer up / layer down
"""

LAYOUT_A = "A"
LAYOUT_A_C1 = "A_C1"
LAYOUT_A_C1_C2 = "A_C1_C2"
LAYOUT_B = "B"

ALL_PROFILES = (LAYOUT_A, LAYOUT_A_C1, LAYOUT_A_C1_C2, LAYOUT_B)

# IconStripHorizontal in ResourceListViewModes.h
PRESET_LIST_HORIZONTAL = 1

PROFILE_FLAGS = {
    LAYOUT_A: {
        "presets_in_toolbar": False,
        "toolbox_bottom": False,
        "layers_left": False,
    },
    LAYOUT_A_C1: {
        "presets_in_toolbar": True,
        "toolbox_bottom": False,
        "layers_left": False,
    },
    LAYOUT_A_C1_C2: {
        "presets_in_toolbar": True,
        "toolbox_bottom": True,
        "layers_left": False,
    },
    LAYOUT_B: {
        "presets_in_toolbar": True,
        "toolbox_bottom": True,
        "layers_left": True,
    },
}

# Learned baseline (Session 1 / Layout A / toolbox still on the left).
STUDY_TOOLBOX_ORDER_DEFAULT = (
    "SvgTextTool",
    "KritaShape/KisToolBrush",
    "KritaShape/KisToolLine",
    "KritaShape/KisToolRectangle",
    "KritaShape/KisToolEllipse",
    "KritaTransform/KisToolMove",
    "KritaFill/KisToolGradient",
    "KritaFill/KisToolFill",
)

# Applied once when the toolbox moves to the bottom (A_C1_C2 and B).
STUDY_TOOLBOX_ORDER_MOVED = (
    "KritaShape/KisToolRectangle",
    "KritaShape/KisToolEllipse",
    "KritaShape/KisToolLine",
    "KritaShape/KisToolBrush",
    "SvgTextTool",
    "KritaFill/KisToolFill",
    "KritaFill/KisToolGradient",
    "KritaTransform/KisToolMove",
)

# Brush preset whitelist slots. Order = desired display order.
# Default: round brush then eraser. Swapped when brushes move into the toolbar.
BRUSH_PRESET_ORDER_DEFAULT = (
    ("b)_Basic-5_Size_default", "b)_Basic-1"),
    ("a)_Eraser_Circle",),
)
BRUSH_PRESET_ORDER_SWAPPED = (
    ("a)_Eraser_Circle",),
    ("b)_Basic-5_Size_default", "b)_Basic-1"),
)

LAYER_BUTTONS_DEFAULT = ("bnAdd", "bnDelete", "bnRaise", "bnLower")
# Swap up/down when layers move to the left (Layout B).
LAYER_BUTTONS_LAYERS_LEFT = ("bnAdd", "bnDelete", "bnLower", "bnRaise")


def profile_flags(profile):
    return dict(PROFILE_FLAGS.get(profile, PROFILE_FLAGS[LAYOUT_A]))


def toolbox_order_for_profile(profile):
    if profile_flags(profile).get("toolbox_bottom"):
        return STUDY_TOOLBOX_ORDER_MOVED
    return STUDY_TOOLBOX_ORDER_DEFAULT


def brush_preset_order_for_profile(profile):
    if profile_flags(profile).get("presets_in_toolbar"):
        return BRUSH_PRESET_ORDER_SWAPPED
    return BRUSH_PRESET_ORDER_DEFAULT


def layer_button_order_for_profile(profile):
    if profile_flags(profile).get("layers_left"):
        return LAYER_BUTTONS_LAYERS_LEFT
    return LAYER_BUTTONS_DEFAULT


def resolve_layout_profile(condition, session, tutorial_index=0, phase="learning"):
    """Return the interface profile for the current study phase."""
    session = int(session)
    if session == 1:
        return LAYOUT_A
    if session != 2:
        return LAYOUT_A
    if phase == "opening_recall":
        return LAYOUT_A
    cond = (condition or "A").upper()
    idx = max(0, int(tutorial_index))
    if cond == "A":
        return LAYOUT_B
    if cond == "B":
        return (LAYOUT_A_C1, LAYOUT_A_C1_C2, LAYOUT_B)[min(idx, 2)]
    if cond == "C":
        return LAYOUT_B if idx in (0, 2) else LAYOUT_A
    return LAYOUT_A
