"""Study interface layout profiles for the Krita UI rearrangement experiment.

Layout A:       Left: Toolbox | Right: Color, Layers, Brushes (top to bottom)
A + C1:         Left: Toolbox | Right: Color, Layers | Brushes in top toolbar
A + C1 + C2:    Left: —       | Right: Color, Layers | Brushes in top toolbar | Bottom: Toolbox
Layout B:       Left: Layers  | Right: Color         | Brushes in top toolbar | Bottom: Toolbox
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


def profile_flags(profile):
    return dict(PROFILE_FLAGS.get(profile, PROFILE_FLAGS[LAYOUT_A]))


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
