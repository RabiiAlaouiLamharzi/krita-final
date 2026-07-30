import os
import re
import subprocess
import sys
import time
import traceback
from krita import Krita, Extension
from PyQt5.QtCore import (
    QTimer, Qt, QEvent, QPoint, QSize, QRect, QRectF, QPointF, QEventLoop,
    QByteArray)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QIcon, QPixmap, QTransform, QKeySequence, QCursor)
from PyQt5.QtWidgets import (
    QDockWidget, QLabel, QFrame, QToolButton, QWidget, QGridLayout, QSplitter,
    QApplication, QTreeWidget, QAbstractButton, QToolBar, QStackedWidget,
    QHBoxLayout, QMainWindow, QPushButton, QAbstractItemView, QSizePolicy,
    QWidgetAction, QDialog, QLineEdit, QVBoxLayout, QFormLayout, QTextEdit, QMenu,
    QToolTip, QMessageBox, QListView)

MAC_CLOSE_SIZE = 16
STUDY_TOP_BAR_H = 36
CHURN_STEP_MS = 60          # in-place document reset path
CHURN_STEP_MS_SLOW = 120    # close/create document path
CHURN_NEUTRALIZE_MS = 150   # pause before createDocument
CANVAS_WAIT_MS = 40         # poll interval while waiting for canvas
STUDY_CHROME_TOOLBAR = "hideuiStudyBar"
NATIVE_TOOLBARS = ("editToolBar", "BrushesAndStuff")
STUDY_TOOLBARS = (STUDY_CHROME_TOOLBAR,) + NATIVE_TOOLBARS
NATIVE_BRUSH_SLIDER_WIDTH = 150   # Krita sliderLabels mode (kis_paintop_box.cc)
NATIVE_BRUSH_SLIDER_WIDTH_COMPACT = 120
NATIVE_BRUSH_SLIDER_HEIGHT = 32   # Krita toolbar ButtonSize default
PRESET_STRIP_HEIGHT = NATIVE_BRUSH_SLIDER_HEIGHT
PRESET_ICON_SIZE = 24
PRESET_ICON_CELL = 28
TIMER_STYLE_NORMAL = (
    "color: #1a1a1a; font-size: 16px; font-weight: bold;"
    "padding: 2px 14px; background: #fff3cd; border-radius: 4px;")
TIMER_STYLE_URGENT = (
    "color: #ffffff; font-size: 16px; font-weight: bold;"
    "padding: 2px 14px; background: #dc3545; border-radius: 4px;")
TIMER_STYLE_URGENT_TEXT_HIDDEN = (
    "color: #dc3545; font-size: 16px; font-weight: bold;"
    "padding: 2px 14px; background: #dc3545; border-radius: 4px;")
SKIP_LEARN_STYLE = (
    "QPushButton {"
    " color: #1a1a1a; font-size: 16px; font-weight: bold;"
    " padding: 2px 14px; background: #d8d8d8; border-radius: 4px; border: none; }"
    " QPushButton:hover { background: #c8c8c8; }"
    " QPushButton:pressed { background: #b8b8b8; }")
NEXT_RECALL_STYLE = (
    "QPushButton {"
    " color: #ffffff; font-size: 16px; font-weight: bold;"
    " padding: 2px 14px; background: #4a6fa5; border-radius: 4px; border: none; }"
    " QPushButton:hover { background: #5a7fb5; }"
    " QPushButton:pressed { background: #3a5f95; }")
TIMER_URGENT_SEC = 5
TIMER_BLINK_MS = 400
# Extra beat after learning/recall prep so the full-screen cover never drops mid-layout.
LOADING_EXTRA_SETTLE_MS = 1000
# Hard cap so recall never sits forever on "Preparing…" (slow machines / missed timers).
RECALL_AUTO_START_FAILSAFE_MS = 8000
RECALL_OVERLAY_WARMUP_DELAYS_MS = (120, 400, 850)
RECALL_FEEDBACK_CORRECT = (
    "border: 3px solid #28a745; border-radius: 4px;"
    " background-color: rgba(40, 167, 69, 0.18);")
RECALL_FEEDBACK_WRONG = (
    "border: 3px solid #dc3545; border-radius: 4px;"
    " background-color: rgba(220, 53, 69, 0.18);")
RECALL_PLACEHOLDER_STYLE = (
    "background-color: #ffffff; border: 2px solid #b0b0b0;"
    " border-radius: 4px;")
RECALL_MASK_BTN_STYLE = (
    "QToolButton { background-color: #ffffff; color: transparent;"
    " border: 2px solid #b0b0b0; border-radius: 4px; }"
    " QToolButton:checked { background-color: #ffffff; }"
    " QToolButton:hover { background-color: #ffffff; }"
    " QToolButton:pressed { background-color: #ffffff; }")
RECALL_MASK_GENERIC_STYLE = (
    "background-color: #ffffff; color: transparent;"
    " border: 2px solid #b0b0b0; border-radius: 4px;")
RECALL_MASK_PRESET_STYLE = (
    "QAbstractItemView { background-color: transparent; color: transparent; }"
    " QAbstractItemView::item { background-color: #ffffff;"
    " border: 2px solid #b0b0b0; border-radius: 4px; }"
    " QAbstractItemView::item:selected { background-color: #ffffff; }")
RECALL_OVERLAY_NAME = "hideuiRecallOverlay"
RECALL_PRESET_BACKDROP_NAME = "hideuiRecallPresetBackdrop"
RECALL_QUESTION_NAME = "hideuiRecallQuestion"


class _SkipLearningDialog(QDialog):
    """Experimenter password to skip a timed learning phase or break."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Skip phase")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(360)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; }
            QLineEdit {
                background-color: #3c3c3c; color: #e0e0e0;
                border: 1px solid #555; padding: 6px;
            }
            QPushButton {
                background-color: #4a6fa5; color: white;
                border: none; padding: 8px 16px; min-width: 80px;
            }
            QPushButton:hover { background-color: #5a7fb5; }
            QPushButton#cancelBtn {
                background-color: #555; color: #e0e0e0;
            }
        """)
        self._title = QLabel("Enter the skip password for this phase.")
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignCenter)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("")
        self._msg = QLabel("")
        self._msg.setStyleSheet("color: #e06c6c;")
        self._msg.setWordWrap(True)
        self._msg.setAlignment(Qt.AlignCenter)
        form = QFormLayout()
        form.addRow("Password:", self._password)
        skip_btn = QPushButton("Skip")
        skip_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(cancel_btn)
        btns.addWidget(skip_btn)
        lay = QVBoxLayout(self)
        lay.addWidget(self._title)
        lay.addLayout(form)
        lay.addWidget(self._msg)
        lay.addLayout(btns)
        skip_btn.clicked.connect(self._try_accept)
        cancel_btn.clicked.connect(self.reject)
        self._password.returnPressed.connect(self._try_accept)
        self._expected = None

    def _try_accept(self):
        got = self._password.text().strip()
        expected = (self._expected or "").strip()
        if not expected:
            self._msg.setText("Skip is not available for this phase.")
            return
        if got and got.upper() == expected.upper():
            self.accept()
        else:
            self._msg.setText("Incorrect password.")
            self._password.selectAll()
            self._password.setFocus()

    def run(self, expected_password, title=None, window_title=None):
        self._expected = expected_password or ""
        if title:
            self._title.setText(title)
        if window_title:
            self.setWindowTitle(window_title)
        self._password.clear()
        self._msg.clear()
        self._password.setFocus()
        QApplication.processEvents()
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.adjustSize()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2)
        return self.exec_() == QDialog.Accepted


class _RecallOverlay(QWidget):
    """Solid white click target on top of a command (sibling layer, not child of button)."""

    def __init__(self, cmd_id, feedback_widget, parent=None):
        super().__init__(parent)
        self.setObjectName(RECALL_OVERLAY_NAME)
        self.setProperty("hideui_recall_cmd", cmd_id)
        self.setProperty("hideui_recall_feedback", feedback_widget)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(255, 255, 255))
        self.setPalette(pal)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(RECALL_PLACEHOLDER_STYLE)
        self.setToolTip("")

    def set_recall_result(self, correct):
        self.setProperty(
            "hideui_recall_result", "correct" if correct else "wrong")
        self.setStyleSheet("")
        self.update()
        self.repaint()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        result = self.property("hideui_recall_result")
        if result is not None and not isinstance(result, str):
            result = str(result)
        if result == "correct":
            pen_color, width = QColor(255, 255, 255), 3
        elif result == "wrong":
            pen_color, width = QColor(255, 255, 255), 3
        else:
            pen_color, width = QColor(176, 176, 176), 2
        inset = max(1, width // 2)
        p.setPen(QPen(pen_color, width))
        p.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))


class _RecallQuestionBanner(QFrame):
    """Recall question prompt overlaid on the canvas (not the top study bar)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName(RECALL_QUESTION_NAME)
        self.setFocusPolicy(Qt.NoFocus)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self._text = QLabel("")
        self._text.setWordWrap(True)
        self._text.setAlignment(Qt.AlignCenter)
        self._text.setStyleSheet(
            "color: #1a1a1a; font-size: 18px; font-weight: bold;")
        lay.addWidget(self._text)
        self.setStyleSheet(
            "QFrame { background-color: rgba(255, 243, 205, 0.96);"
            " border: 2px solid #e6c200; border-radius: 6px; }")

    def set_question(self, text, rich=False):
        self._text.setTextFormat(Qt.RichText if rich else Qt.PlainText)
        self._text.setText(text or "")


class _MacCloseButton(QWidget):
    """Painted macOS traffic-light close — avoids QPushButton platform quirks."""

    def __init__(self, parent=None, on_click=None):
        super().__init__(parent)
        self._on_click = on_click
        self._hover = False
        self.setFixedSize(MAC_CLOSE_SIZE, MAC_CLOSE_SIZE)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            if self._on_click:
                self._on_click()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = float(min(self.width(), self.height()))
        inset = 0.5
        d = side - 2 * inset
        x0 = (self.width() - d) / 2.0
        y0 = (self.height() - d) / 2.0
        circle = QRectF(x0, y0, d, d)
        fill = QColor("#ff3b30" if self._hover else "#ff5f57")
        p.setPen(QPen(QColor("#cf4c43"), 1))
        p.setBrush(fill)
        p.drawEllipse(circle)
        cx, cy = circle.center().x(), circle.center().y()
        arm = d * 0.17
        icon_w = max(1.4, d * 0.10)
        p.setPen(QPen(
            QColor("#2d0001" if self._hover else "#4a0002"),
            icon_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(cx - arm, cy - arm), QPointF(cx + arm, cy + arm))
        p.drawLine(QPointF(cx - arm, cy + arm), QPointF(cx + arm, cy - arm))


class _ExpandingWidgetAction(QWidgetAction):
    """Host a child widget that fills the full toolbar row."""

    def __init__(self, child, parent=None):
        super().__init__(parent)
        self._child = child

    def createWidget(self, parent):
        host = QWidget(parent)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._child.setParent(host)
        lay.addWidget(self._child)
        return host

# The four panels we keep (by objectName). Everything else is hidden.
KEEP_DOCKERS = {
    "ToolBox",
    "PresetDocker",
    "ColorSelectorNg",
    "KisLayerBox",
}
# Auto-styled text for the study (no font-size / properties window).
# Vector shape bounding boxes are in points (1/72 inch).
STUDY_TEXT_HEIGHT_PT = 35
STUDY_TEXT_MIN_HEIGHT_PT = 4.0
STUDY_TEXT_STYLE_DELAY_MS = 700
TEXT_PROPERTIES_DOCKER = "TextProperties"
BLOCKED_TEXT_WINDOW_CLASSES = (
    "SvgTextEditor",
    "GlyphPaletteDialog",
)

# Extra widgets inside the kept panels to hide, identified by Qt class name.
HIDE_BY_CLASS = {
    "KisMinimalShadeSelector",   # shade gradient bars (color selector)
    "KisMyPaintShadeSelector",   # alt shade selector (color selector)
    "KisTagChooserWidget",       # "Tag" dropdown row (brush presets)
    "KisTagFilterWidget",        # search + "Filter in Tag" (brush presets)
    "KisPopupButton",            # "Display settings" (≡) button
    "KisStorageChooserWidget",   # storage box button
}

# Hide buttons by their tooltip text (any widget type, within kept panels).
HIDE_BY_TOOLTIP = {
    "Display settings",
    "Storage Resources",
    "Import resource",
    "Delete resource",
}

# Hide buttons by their objectName.
HIDE_BY_OBJNAME = {
    "bnLayerFilters",                 # layers filter button
    "bnDuplicate",                    # duplicate layer
    "configureLayerDockerToolbar",    # layers config/menu button
}

# Panel commands: toolbox 8 + presets 2 + color wheel 1 + layers 4.
KEEP_TOOLBOX_IDS = {
    "KritaShape/KisToolBrush",
    "KritaTransform/KisToolMove",
    "KritaShape/KisToolLine",
    "KritaShape/KisToolRectangle",
    "KritaShape/KisToolEllipse",
    "KritaFill/KisToolFill",
    "KritaFill/KisToolGradient",
    "SvgTextTool",
}
KEEP_TOOLBOX_TOOLTIP_NEEDLES = (
    "eraser tool",
)
# Fixed command order everywhere:
# text -> brush -> line -> rectangle -> ellipse -> move -> gradient -> fill
STUDY_TOOLBOX_ORDER = (
    "SvgTextTool",
    "KritaShape/KisToolBrush",
    "KritaShape/KisToolLine",
    "KritaShape/KisToolRectangle",
    "KritaShape/KisToolEllipse",
    "KritaTransform/KisToolMove",
    "KritaFill/KisToolGradient",
    "KritaFill/KisToolFill",
)
# KisAbstractResourceModel::Name / Filename column offsets (Qt.UserRole + column).
_PRESET_ROLE_NAME = Qt.UserRole + 2
_PRESET_ROLE_FILENAME = Qt.UserRole + 3
# Round brush + block eraser preset.
BRUSH_PRESET_WHITELIST = (
    ("b)_Basic-5_Size_default", "b)_Basic-1"),
    ("a)_Eraser_Circle",),
)
DEFAULT_BRUSH_STEMS = ("b)_Basic-5_Size_default", "b)_Basic-1")
KEEP_LAYER_WIDGETS = {
    "bnAdd", "bnDelete", "bnRaise", "bnLower", "listLayers",
}
LAYER_RECALL_BUTTONS = ("bnAdd", "bnDelete", "bnRaise", "bnLower")
HIDE_LAYER_WIDGETS = {
    "cmbComposite", "bnProperties", "doubleOpacity", "opacityLabel",
}
HIDE_COLOR_SELECTOR_CLASSES = {
    "KisColorHistory",
    "KisCommonColors",
}
LAYER_ROW_INLINE_ICON_ZONE_PX = 96

# Welcome-screen widgets to hide: the whole "Community" link list and the
# News column. (The New/Open file buttons and recent docs stay.)
WELCOME_HIDE = {
    "helpTitleLabel",
    "userManualIcon", "manualLink",
    "supportKritaIcon", "supportKritaLink",
    "kdeIcon", "poweredByKDELink",
    "sourceCodeIcon", "sourceCodeLink",
    "gettingStartedIcon", "gettingStartedLink",
    "userCommunityIcon", "userCommunityLink",
    "kritaWebsiteIcon", "kritaWebsiteLink",
    "widgetRight",   # entire News / updater column
}

LOG = os.path.expanduser("~/krita_hide_ui_log.txt")

# Fixed UI sizes — Krita and video panel are separate dimensions.
DEFAULT_LAYOUT = {"ui_w": 950, "ui_h": 820, "video_w": 500, "video_h": 820}
SESSION_LAYOUTS = {}
LAYOUT_PANEL_GAP = 16
DEFAULT_DOCK_WIDTHS = {
    "ToolBox": 38,
    "PresetDocker": 220,  # right column in Layout A, same width as Color/Layers
    "ColorSelectorNg": 220,
    "KisLayerBox": 220,
}
DEFAULT_DOCK_HEIGHTS = {
    "ColorSelectorNg": 300,
    "KisLayerBox": 240,
}
BOTTOM_PRESET_DOCK_HEIGHT = 48
TOP_PRESET_DOCK_HEIGHT = PRESET_STRIP_HEIGHT
BOTTOM_TOOLBOX_DOCK_HEIGHT = 52


def _log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass


def _qt_alive(obj):
    if obj is None:
        return False
    try:
        from PyQt5 import sip
        return not sip.isdeleted(obj)
    except Exception:
        try:
            obj.objectName()
            return True
        except RuntimeError:
            return False


def _widget_parent(widget):
    """QWindow has no parentWidget(); only walk QWidget trees."""
    return widget.parentWidget() if isinstance(widget, QWidget) else None


class HideUIExtension(Extension):

    def __init__(self, parent):
        super().__init__(parent)
        self._filtered = set()
        self._autodone = set()
        self._creating_doc = False
        self._start = time.monotonic()
        self._gateway_done = False
        self._gateway_ok = False
        self.session = None
        self._qwin = None
        self._win_locked = False
        self._fixed_pos = None
        self._fixed_size = None
        self._pos_guard = None
        self._study_toolbar = None
        self._study_toolbar_ready = False
        self._close_btn = None
        self._timer_label = None
        self._skip_learn_btn = None
        self._tutorial_timer = None
        self._tutorial_timer_done_cb = None
        self._current_learning_num = 0
        self._current_break_learn_num = 0
        self._current_recall_learn_num = 0
        self._recall_input_blocked = False
        self._timer_blink_timer = None
        self._timer_blink_on = True
        self._timer_urgent_active = False
        self._session1_step_fn = None
        self._video_panel = None
        self._quitting = False
        self._close_krita_started = False
        self._geom_busy = False
        self._tutorial_active = False
        self._recall_active = False
        self._session1_running = False
        self._apply_timer = None
        self._video_shown_for_canvas = False
        self._hidden_logged = set()
        self._session1_doc_ready = False
        self._ui_applied = False
        self._welcome_w = None
        self._canvas_w = None
        self._ui_hooks_done = False
        self._toolbox_hooks_done = False
        self._text_tool_active = False
        self._text_idle_timer = QTimer()
        self._text_idle_timer.setSingleShot(True)
        self._text_idle_timer.setInterval(STUDY_TEXT_STYLE_DELAY_MS)
        self._text_idle_timer.timeout.connect(self._apply_study_text_style)
        self._text_style_busy = False
        self._styled_text_shape_ids = set()
        self._styled_text_positions = set()
        self._text_app_filter_active = False
        self._shortcuts_disabled = False
        self._extras_hidden = False
        self._loading_window = None
        self._loading_armed = False
        self._loading_started_at = None
        self._polish_reveal_active = False
        self._tutorial_phase_sec = 3600
        self._tutorial_remaining_sec = None
        self._recall_questions = []
        self._recall_index = 0
        self._recall_results = []
        self._recall_timer = None
        self._recall_phase_timer = None
        self._recall_remaining_sec = 0
        self._recall_phase_remaining_sec = None
        self._recall_question_time_sec = 15
        self._recall_phase_time_sec = None
        self._recall_meta = {}
        self._recall_question_answered = False
        self._recall_waiting_for_next = False
        self._recall_awaiting_first_question = False
        self._recall_auto_starting = False
        self._recall_auto_start_token = 0
        self._recall_krita_hidden_until_start = False
        self._recall_mask_state = []
        self._recall_question_banner = None
        self._next_recall_btn = None
        self._recall_feedback_widgets = []
        self._recall_command_widgets = []
        self._recall_overlay_generation = 0
        self._recall_app_filter_active = False
        self._session_tutorial_index = 0
        self._active_learn_num = 0
        self._session2_running = False
        self._after_recall_fn = None
        self._recall_skip_save = False
        self._recall_end_reason = "complete"
        self._break_active = False
        self._recall_panel_message = None
        self._study_layout_profile = "A"
        self._study_layout_applied_sig = None
        self._capture_timer = None
        self._capture_attempts = 0
        self._dock_refs = {}
        self._dock_ref_warned = set()
        self._brushes_toolbar_ref = None
        self._presets_in_toolbar = False
        self._preset_toolbar_action = None
        self._preset_popup_widget = None
        self._preset_dock_placeholder = None
        self._recall_layout_profile_override = None
        self._learning_layout_profile = "A"
        self._learning_tracker = None
        self._learning_pointer_timer = None
        self._learning_steps = None
        self._learning_step_index = 0
        self._learning_done_cb = None
        self._learning_panel_title = ""
        self._learning_panel_phase = 1
        self._learning_phase_finished = False
        self._study_brush_size = None
        self._brush_size_sync_hooked = False
        self._brush_preset_keepalive_armed = False
        self._phase_transition_busy = False

    def _halt_deferred_work(self):
        """Stop pending timers before document/layout phase changes."""
        self._recall_overlay_generation += 1
        self._stop_position_guard()
        for name in (
                "_apply_timer", "_tutorial_timer", "_recall_timer",
                "_recall_phase_timer", "_timer_blink_timer", "_suppress_timer",
                "_capture_timer", "_learning_pointer_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
            if name == "_learning_pointer_timer":
                setattr(self, name, None)

    def _pause_video_for_phase_change(self):
        try:
            from .video_panel import suspend_playback_for_phase_change
            suspend_playback_for_phase_change()
        except Exception:
            _log(traceback.format_exc())

    def _recall_layout_profile(self):
        """Layout profile recall must match — same as the preceding learning block."""
        return (
            getattr(self, "_recall_layout_profile_override", None)
            or getattr(self, "_learning_layout_profile", None)
            or getattr(self, "_study_layout_profile", "A"))

    def _apply_layout_for_profile(self, qwin, profile, force=False):
        """Apply the full study layout + presets for a profile (learning or recall)."""
        if not _qt_alive(qwin) or self._quitting:
            return
        profile = profile or "A"
        self._study_layout_profile = profile
        if force:
            self._study_layout_applied_sig = None
        if profile == "A" or self._is_session1():
            self._lock_dock_panels_layout_a(qwin)
        else:
            self._apply_study_layout(qwin)
        self._ensure_presets_for_profile(qwin, profile)
        toolbox = self._dock_by_name(qwin, "ToolBox")
        if toolbox is not None:
            self._apply_study_toolbox_order(toolbox, qwin)
        self._lock_dock_panel_heights(qwin)
        self._lock_dock_splitters(qwin)
        self._apply_all_dock_titles(qwin)
        self._trim_brush_presets(qwin)

    def _stabilize_study_layout_for_recall(self, qwin):
        """Re-apply the same full layout as the preceding learning block."""
        profile = self._recall_layout_profile()
        _log("recall layout apply: profile=%s" % profile)
        self._apply_layout_for_profile(qwin, profile, force=True)

    def _study_active_view(self):
        try:
            win = Krita.instance().activeWindow()
            if win is None:
                return None
            view = win.activeView()
            if view is not None:
                return view
            views = win.views()
            return views[0] if views else None
        except Exception:
            return None

    def _apply_study_brush_size(self, size=None):
        """Keep one shared brush size across round brush and eraser presets."""
        if self._quitting:
            return
        view = self._study_active_view()
        if view is None:
            return
        try:
            if size is not None:
                self._study_brush_size = float(size)
            elif self._study_brush_size is None:
                self._study_brush_size = float(view.brushSize())
                return
            target = float(self._study_brush_size)
            if abs(float(view.brushSize()) - target) > 0.05:
                view.setBrushSize(target)
        except Exception:
            _log(traceback.format_exc())

    def _on_study_brush_size_spinbox_changed(self, value):
        try:
            self._study_brush_size = float(value)
        except Exception:
            pass

    def _schedule_study_brush_size_apply(self):
        for delay in (0, 40, 120):
            QTimer.singleShot(delay, lambda: self._apply_study_brush_size())

    def _hook_study_brush_size_on_spinbox(self, qwin):
        for frame in qwin.findChildren(QFrame):
            if frame.metaObject().className() != "KisWidgetChooser":
                continue
            for child in frame.findChildren(QWidget):
                if "SliderSpinBox" not in child.metaObject().className():
                    continue
                if child.property("hideui_size_sync"):
                    continue
                try:
                    child.valueChanged.connect(
                        self._on_study_brush_size_spinbox_changed)
                except Exception:
                    pass
                child.setProperty("hideui_size_sync", True)
        if self._study_brush_size is None:
            view = self._study_active_view()
            if view is not None:
                try:
                    self._study_brush_size = float(view.brushSize())
                except Exception:
                    pass

    def _hook_study_brush_size_on_presets(self, qwin):
        roots = []
        dock = self._dock_by_name(qwin, "PresetDocker")
        if dock is not None:
            roots.append(dock)
        if self._preset_popup_widget is not None:
            roots.append(self._preset_popup_widget)
        for root in roots:
            for view in root.findChildren(QAbstractItemView):
                if view.property("hideui_preset_size_sync"):
                    continue
                try:
                    view.clicked.connect(
                        lambda *a: self._schedule_study_brush_size_apply())
                    view.activated.connect(
                        lambda *a: self._schedule_study_brush_size_apply())
                except Exception:
                    pass
                view.setProperty("hideui_preset_size_sync", True)

    def _hook_study_brush_size_on_toolbox(self, qwin):
        dock = self._dock_by_name(qwin, "ToolBox")
        if dock is None:
            return
        for btn in dock.findChildren(QToolButton):
            if not self._keep_toolbox_button(btn):
                continue
            if btn.property("hideui_brush_size_sync"):
                continue
            tip = (btn.toolTip() or "").lower()
            oid = btn.objectName() or ""
            if oid == "KritaShape/KisToolBrush" or "eraser" in tip:
                try:
                    btn.clicked.connect(
                        lambda *a: self._schedule_study_brush_size_apply())
                except Exception:
                    pass
                btn.setProperty("hideui_brush_size_sync", True)

    def _hook_study_brush_size_sync(self, qwin):
        if not _qt_alive(qwin):
            return
        try:
            self._hook_study_brush_size_on_spinbox(qwin)
            self._hook_study_brush_size_on_presets(qwin)
            self._hook_study_brush_size_on_toolbox(qwin)
            self._brush_size_sync_hooked = True
        except Exception:
            _log(traceback.format_exc())

    def _is_session1(self):
        return bool(self.session and self.session.get("session") == 1)

    def _learning_uses_phase_timer(self):
        """Session 1 and 2 learning blocks use the phase countdown (all conditions)."""
        if not self.session:
            return False
        return int(self.session.get("session", 0) or 0) in (1, 2)

    def _in_session1_flow(self):
        return bool(
            self._session1_running or self._session2_running
            or self._tutorial_active or self._recall_active or self._break_active
            or (self.session and self.session.get("session") in (1, 2)
                and self._session1_doc_ready))

    def _qwin_alive(self):
        return _qt_alive(self._qwin)

    def _stop_position_guard(self):
        try:
            if self._pos_guard is not None:
                self._pos_guard.stop()
        except Exception:
            pass

    def _invalidate_qwin(self):
        self._stop_position_guard()
        self._qwin = None
        self._win_locked = False

    def _experiment_in_progress(self):
        return bool(
            self._tutorial_active or self._recall_active or self._break_active
            or self._session1_running or getattr(self, "_session2_running", False))

    def _detach_for_quit(self):
        """Stop interfering with Krita's native shutdown (no dock reparenting)."""
        self._stop_position_guard()
        self._recall_overlay_generation += 1
        for timer_attr in (
                "_apply_timer", "_suppress_timer", "_tutorial_timer",
                "_recall_phase_timer", "_pos_guard"):
            try:
                timer = getattr(self, timer_attr, None)
                if timer is not None and hasattr(timer, "stop"):
                    timer.stop()
            except Exception:
                pass
        if not self._qwin_alive():
            return
        qwin = self._qwin
        try:
            if qwin.property("hideui_winfilter"):
                qwin.removeEventFilter(self)
                qwin.setProperty("hideui_winfilter", False)
            qwin.setMinimumSize(0, 0)
            qwin.setMaximumSize(16777215, 16777215)
            flags = Qt.Window
            if qwin.windowFlags() & Qt.FramelessWindowHint:
                qwin.setWindowFlags(flags)
                qwin.show()
        except Exception:
            _log(traceback.format_exc())
        try:
            self._clear_recall_overlays_for_quit(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _clear_recall_overlays_for_quit(self, qwin):
        """Hide recall overlays without deleteLater — safer during app teardown."""
        if not _qt_alive(qwin):
            return
        for name in (RECALL_OVERLAY_NAME, RECALL_PRESET_BACKDROP_NAME):
            for w in qwin.findChildren(QWidget, name):
                try:
                    w.hide()
                    w.setParent(None)
                except Exception:
                    pass

    def _force_quit(self):
        """Last resort only if Krita did not close after normal window quit."""
        if getattr(self, "_force_quit_called", False):
            return
        self._force_quit_called = True
        _log("force_quit: last resort")
        try:
            app = QApplication.instance()
            if app is not None and self._qwin_alive():
                self._detach_for_quit()
                self._qwin.close()
                app.processEvents()
                if not self._qwin_alive():
                    return
            if app is not None:
                act = Krita.instance().action("file_quit")
                if act is not None:
                    act.trigger()
                    app.processEvents()
                    return
        except Exception:
            _log(traceback.format_exc())
        try:
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception:
            _log(traceback.format_exc())
        os._exit(0)

    def _close_krita(self):
        """Exit through Krita's normal quit path (avoids macOS crash dialog)."""
        if self._close_krita_started:
            return
        self._close_krita_started = True
        _log("close_krita: begin")
        try:
            self._detach_for_quit()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            k = Krita.instance()
            for doc in list(k.documents()):
                try:
                    doc.setModified(False)
                except Exception:
                    _log(traceback.format_exc())
            if app is not None:
                app.processEvents()
        except Exception:
            _log(traceback.format_exc())
        # Krita segfaults inside qwin.close() / its C++ teardown after our
        # widget reparenting — the crash fires BEFORE aboutToQuit, so macOS
        # shows "Krita quit unexpectedly" on every exit. All participant
        # data, results and logs are already flushed to disk by this point,
        # so end the process here and never let that teardown run.
        _log("close_krita: clean hard exit")
        os._exit(0)

    def _close_krita_fallback(self):
        if not self._quitting:
            return
        if not self._qwin_alive():
            _log("close_krita: window closed")
            return
        _log("close_krita: fallback file_quit")
        try:
            act = Krita.instance().action("file_quit")
            if act is not None:
                act.trigger()
                QApplication.processEvents()
        except Exception:
            _log(traceback.format_exc())
        QTimer.singleShot(1500, self._close_krita_last_resort)

    def _close_krita_last_resort(self):
        if not self._quitting or not self._qwin_alive():
            return
        _log("close_krita: last resort force quit")
        self._force_quit()

    def _request_quit(self, force=False):
        """Close button — stop experiment UI, then quit Krita cleanly."""
        if self._quitting:
            return
        if (not force and self._experiment_in_progress()
                and self._qwin_alive()):
            parent = self._study_toolbar or self._qwin
            answer = QMessageBox.question(
                parent,
                "End session?",
                "Quit Krita now? Your current learning or recall phase will stop.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self._quitting = True
        try:
            from .experiment_log import end_session
            end_session("quit")
        except Exception:
            pass
        _log("request_quit: clean shutdown (force=%s)" % force)
        try:
            self._stop_recall_click_capture()
        except Exception:
            pass
        try:
            if self._tutorial_timer is not None:
                self._tutorial_timer.stop()
                self._tutorial_timer = None
            self._stop_timer_blink()
        except Exception:
            pass
        try:
            if hasattr(self, "_suppress_timer"):
                self._suppress_timer.stop()
        except Exception:
            _log(traceback.format_exc())
        self._stop_position_guard()
        try:
            if self._apply_timer is not None:
                self._apply_timer.stop()
        except Exception:
            _log(traceback.format_exc())
        try:
            from .video_panel import shutdown_all_video
            shutdown_all_video()
            self._video_panel = None
        except Exception:
            _log(traceback.format_exc())
        QTimer.singleShot(0, self._close_krita)

    def _on_app_about_to_quit(self):
        if getattr(self, "_quit_hook_logged", False):
            return
        self._quit_hook_logged = True
        self._quitting = True
        _log("aboutToQuit")
        self._stop_position_guard()
        try:
            from .video_panel import shutdown_all_video
            shutdown_all_video()
        except Exception:
            _log(traceback.format_exc())
        # Krita segfaults in its C++ teardown after our reparented widgets,
        # which makes macOS show "Krita quit unexpectedly" on every exit.
        # All participant data and settings are already flushed by this point,
        # so end the process cleanly before that teardown can crash.
        _log("aboutToQuit: clean hard exit")
        try:
            os._exit(0)
        except Exception:
            pass

    def setup(self):
        # Hide Krita splash/main immediately (before createActions runs).
        try:
            app = QApplication.instance()
            if app is not None and not app.property("hideui_quit_hook"):
                app.aboutToQuit.connect(self._on_app_about_to_quit)
                app.setProperty("hideui_quit_hook", True)
            from .experiment import suppress_krita_ui
            self._suppress_timer = QTimer()
            self._suppress_timer.setInterval(100)
            self._suppress_timer.timeout.connect(
                lambda: suppress_krita_ui() if not self._gateway_ok else None)
            self._suppress_timer.start()
            suppress_krita_ui()
            try:
                from .loading_screen import LoadingWindow
                self._loading_window = LoadingWindow()
            except Exception:
                _log(traceback.format_exc())
        except Exception:
            _log(traceback.format_exc())

    def createActions(self, window):
        qwin = window.qwindow()
        self._qwin = qwin
        qwin.hide()
        self._arm_loading_screen("Starting…", 0)

        # Gateway runs as soon as possible; Krita stays hidden until done.
        QTimer.singleShot(0, lambda: self._run_gateway(qwin))

    def _schedule_apply(self, qwin):
        if self._quitting or self._in_session1_flow() or not self._ui_applied:
            return
        if self._apply_timer is None:
            self._apply_timer = QTimer()
            self._apply_timer.setSingleShot(True)
            self._apply_timer.timeout.connect(lambda: self._apply(qwin))
        self._apply_timer.start(800)

    def _welcome_widget(self, qwin):
        if self._welcome_w is not None and _qt_alive(self._welcome_w):
            return self._welcome_w
        self._welcome_w = None
        if not _qt_alive(qwin):
            return None
        for w in qwin.findChildren(QWidget):
            if w.metaObject().className() == "KisWelcomePageWidget":
                self._welcome_w = w
                break
        return self._welcome_w

    def _is_welcome_visible(self, qwin):
        w = self._welcome_widget(qwin)
        if w is None:
            return False
        if self._stacked_on_welcome(qwin):
            return True
        return w.isVisible()

    def _stacked_on_welcome(self, qwin):
        """True when the welcome page is the active stack page (works while qwin is hidden)."""
        w = self._welcome_widget(qwin)
        if w is None:
            return False
        p = _widget_parent(w)
        while p is not None:
            if isinstance(p, QStackedWidget):
                return p.currentWidget() is w
            p = _widget_parent(p)
        return w.isVisible()

    def _has_paint_canvas(self, qwin):
        if not _qt_alive(qwin):
            return False
        for w in qwin.findChildren(QWidget):
            if "Canvas" in w.metaObject().className():
                self._canvas_w = w
                return True
        return False

    def _is_canvas_ready(self, qwin):
        if not _qt_alive(qwin):
            return False
        if not list(Krita.instance().documents()):
            return False
        if self._stacked_on_welcome(qwin):
            return False
        return self._has_paint_canvas(qwin)

    def _show_study_toolbars(self, qwin):
        """Row 2: Krita save / undo / redo / brush-size toolbars."""
        try:
            if self._is_welcome_visible(qwin):
                return
            mb = qwin.menuBar()
            if mb is not None:
                mb.hide()
            for t in qwin.findChildren(QToolBar):
                name = t.objectName()
                if name == STUDY_CHROME_TOOLBAR:
                    continue
                keep = name in NATIVE_TOOLBARS
                t.setVisible(keep)
                if keep:
                    t.setMovable(False)
                    t.setFloatable(False)
                    t.show()
            self._order_study_toolbar(qwin)
            self._ensure_study_dockers_visible(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _hide_document_chrome(self, qwin):
        """Hide the MDI '[Not Saved]' tab row — study uses one fixed document."""
        try:
            for w in qwin.findChildren(QWidget):
                cls = w.metaObject().className()
                if cls == "QTabBar":
                    w.hide()
                elif cls == "QMdiSubWindow":
                    flags = w.windowFlags()
                    w.setWindowFlags(flags | Qt.FramelessWindowHint)
                    w.show()
        except Exception:
            _log(traceback.format_exc())

    def _configure_native_brush_slider(self, qwin):
        """Lock brushslider1 to Size (width), not opacity."""
        try:
            self._restore_brush_size_slider(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _slider_labels_enabled(self):
        try:
            raw = Krita.instance().readSetting("", "sliderLabels", "true")
            return str(raw).lower() in ("1", "true", "yes")
        except Exception:
            return True

    def _brush_slider_metrics(self, qwin):
        """Match kis_paintop_box.cc slider width/height (dpi + ButtonSize)."""
        screen = qwin.screen() if qwin is not None and qwin.screen() else None
        if screen is None:
            screen = QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInchX() if screen else 96.0
        base = (NATIVE_BRUSH_SLIDER_WIDTH if self._slider_labels_enabled()
                else NATIVE_BRUSH_SLIDER_WIDTH_COMPACT)
        width = max(base, int(base * dpi / 96.0))
        height = NATIVE_BRUSH_SLIDER_HEIGHT
        try:
            raw = Krita.instance().readSetting("", "ButtonSize", str(height))
            if raw not in (None, ""):
                height = int(float(raw))
        except Exception:
            pass
        return width, height

    def _configure_size_spinbox_labels(self, spinbox, frame):
        """One bar like stock Krita: 'Size: 40,00 px' inside the slider."""
        if not self._slider_labels_enabled():
            return
        try:
            if hasattr(spinbox, "setPrefix"):
                spinbox.setPrefix("Size: ")
            if hasattr(spinbox, "setSuffix"):
                spinbox.setSuffix(" px")
        except Exception:
            pass
        for label in frame.findChildren(QLabel):
            if label.text().strip().lower().startswith("size"):
                label.hide()

    def _clear_widget_recall_styling(self, widget, reset_geometry=False):
        """Remove recall masks/styles without stripping native Krita sizing."""
        if widget is None or not _qt_alive(widget):
            return
        widget.setStyleSheet("")
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        widget.setProperty("hideui_size_masked", None)
        widget.setProperty("hideui_recall_size_rect", None)
        widget.setProperty("hideui_recall_saved_geom", None)
        widget.setProperty("hideui_recall_orig_style", None)
        if reset_geometry and hasattr(widget, "setMinimumSize"):
            widget.setMinimumSize(0, 0)
            widget.setMaximumSize(16777215, 16777215)

    def _hide_chooser_arrow(self, frame):
        """Hide the size/opacity dropdown arrow; return its layout width."""
        arrow_w = 0
        for child in frame.children():
            if not isinstance(child, QToolButton):
                continue
            arrow_w = max(arrow_w, child.sizeHint().width(), child.width())
            child.hide()
            child.setEnabled(False)
        return arrow_w

    def _apply_native_slider_geometry(self, spinbox, min_width, height, extra_width=0):
        """Restore KisDoubleSliderSpinBox sizing from kis_paintop_box.cc."""
        cls = spinbox.metaObject().className()
        if "SliderSpinBox" not in cls:
            return
        target_w = max(min_width + extra_width, spinbox.sizeHint().width())
        spinbox.setMinimumWidth(target_w)
        spinbox.setFixedWidth(target_w)
        spinbox.setFixedHeight(height)
        spinbox.setMinimumHeight(height)
        spinbox.setMaximumHeight(height)
        spinbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        spinbox.show()
        spinbox.setEnabled(True)
        spinbox.updateGeometry()
        spinbox.update()

    def _restore_brush_size_slider(self, qwin):
        """Restore native Krita brush size slider dimensions and padding."""
        if not _qt_alive(qwin):
            return
        try:
            if not self._recall_active:
                for ov in qwin.findChildren(QWidget, RECALL_OVERLAY_NAME):
                    if ov.property("hideui_recall_cmd") == "toolbar:brush_size":
                        ov.hide()
                        ov.setParent(None)
            Krita.instance().writeSetting("", "toolbarslider_1", "size")
            min_width, height = self._brush_slider_metrics(qwin)
            for tb in qwin.findChildren(QToolBar):
                if tb.objectName() == "BrushesAndStuff":
                    tb.show()
            for frame in qwin.findChildren(QFrame):
                if frame.metaObject().className() != "KisWidgetChooser":
                    continue
                self._clear_widget_recall_styling(frame, reset_geometry=True)
                for child in frame.findChildren(QWidget):
                    cls = child.metaObject().className()
                    reset_geom = "SliderSpinBox" not in cls
                    self._clear_widget_recall_styling(child, reset_geometry=reset_geom)
                sp = frame.sizePolicy()
                sp.setHorizontalPolicy(QSizePolicy.Preferred)
                sp.setVerticalPolicy(QSizePolicy.Fixed)
                frame.setSizePolicy(sp)
                frame.show()
                try:
                    frame.chooseWidget("size")
                except Exception:
                    pass
                arrow_w = self._hide_chooser_arrow(frame)
                for child in frame.findChildren(QWidget):
                    cls = child.metaObject().className()
                    if "SliderSpinBox" not in cls:
                        continue
                    self._configure_size_spinbox_labels(child, frame)
                    self._apply_native_slider_geometry(
                        child, min_width, height, extra_width=arrow_w)
                frame.setMinimumWidth(min_width + arrow_w)
                frame.updateGeometry()
                frame.update()
            self._hook_study_brush_size_on_spinbox(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _study_ui_locked(self):
        return self._shortcuts_disabled and not self._quitting

    def _study_text_editing_active(self):
        return self._text_tool_active and not self._recall_active

    def _widget_tree_walk(self, widget):
        w = widget
        while w is not None and isinstance(w, QWidget):
            yield w
            w = _widget_parent(w)

    def _event_on_canvas(self, obj):
        if not isinstance(obj, QWidget):
            return False
        for w in self._widget_tree_walk(obj):
            cls = w.metaObject().className()
            if "Canvas" in cls or w is self._canvas_w:
                return True
        return False

    def _has_study_shortcut_modifier(self, event):
        if not hasattr(event, "modifiers"):
            return False
        return bool(event.modifiers() & (
            Qt.ControlModifier | Qt.MetaModifier | Qt.AltModifier))

    def _focus_on_text_editing(self):
        fw = QApplication.focusWidget()
        if fw is None:
            return self._study_text_editing_active()
        if isinstance(fw, (QLineEdit, QTextEdit)):
            return True
        cls = fw.metaObject().className()
        if "SvgText" in cls or "TextEdit" in cls:
            return True
        for w in self._widget_tree_walk(fw):
            cls = w.metaObject().className()
            if "Canvas" in cls or w is self._canvas_w:
                return True
        return False

    def _study_context_menu_allowed(self, obj):
        if not self._study_ui_locked():
            return True
        return self._study_text_editing_active() and self._event_on_canvas(obj)

    def _active_modal_dialog(self):
        modal = QApplication.activeModalWidget()
        if modal is not None and isinstance(modal, QDialog):
            return modal
        return None

    def _widget_in_dialog(self, widget, dialog):
        if widget is None or dialog is None:
            return False
        w = widget
        while w is not None and isinstance(w, QWidget):
            if w is dialog:
                return True
            w = _widget_parent(w)
        return False

    def _study_modal_keyboard_allowed(self, obj):
        """Allow typing in skip-password and other modal dialogs."""
        modal = self._active_modal_dialog()
        if modal is None:
            return False
        if isinstance(obj, QWidget) and self._widget_in_dialog(obj, modal):
            return True
        fw = QApplication.focusWidget()
        if fw is not None and self._widget_in_dialog(fw, modal):
            return True
        return obj is modal

    def _study_keyboard_allowed(self, obj, event):
        """Allow text typing/delete on canvas; block Krita shortcut chords."""
        if not self._study_ui_locked():
            return True
        if self._study_modal_keyboard_allowed(obj):
            return True
        if isinstance(obj, (QLineEdit, QTextEdit)):
            for w in self._widget_tree_walk(obj):
                if isinstance(w, QDialog):
                    return True
        modal = self._active_modal_dialog()
        if modal is not None and isinstance(obj, QWidget):
            if self._widget_in_dialog(obj, modal):
                return True
        if self._study_text_editing_active():
            if self._has_study_shortcut_modifier(event):
                return False
            if self._focus_on_text_editing() or self._event_on_canvas(obj):
                return True
            if QApplication.focusWidget() is None:
                return True
        return False

    def _ensure_shortcuts_blocked(self, qwin=None):
        self._ensure_text_app_filter()
        if self._shortcuts_disabled:
            if qwin is not None:
                self._disable_krita_shortcuts(qwin)
            return
        if not self._gateway_ok:
            return
        self._shortcuts_disabled = True
        self._disable_krita_shortcuts(qwin)

    def _disable_krita_shortcuts(self, qwin=None):
        """Strip every Krita action shortcut (Ctrl+Z, B, etc.)."""
        try:
            cleared = 0
            for action in Krita.instance().actions():
                if action is None:
                    continue
                try:
                    if not action.shortcut().isEmpty():
                        action.setShortcut(QKeySequence())
                        cleared += 1
                except Exception:
                    pass
            if qwin is not None and _qt_alive(qwin):
                for action in qwin.actions():
                    if action is None:
                        continue
                    try:
                        if not action.shortcut().isEmpty():
                            action.setShortcut(QKeySequence())
                            cleared += 1
                    except Exception:
                        pass
                for tb in qwin.findChildren(QToolBar):
                    for action in tb.actions():
                        if action is None:
                            continue
                        try:
                            if not action.shortcut().isEmpty():
                                action.setShortcut(QKeySequence())
                                cleared += 1
                        except Exception:
                            pass
            if cleared:
                _log("disabled %d keyboard shortcut(s)" % cleared)
        except Exception:
            _log(traceback.format_exc())

    def _configure_video_session(self, session_info=None, video_override=None):
        """Pick tutorial video; never block session flow if video setup fails."""
        try:
            from .video_panel import configure_video_session
            info = session_info if session_info is not None else self.session
            configure_video_session(info, video_override=video_override)
        except Exception:
            _log(traceback.format_exc())

    def _on_new_session_started(self):
        """Reset per-session UI state when a new run folder is opened."""
        self._ui_applied = False
        self._study_layout_applied_sig = None
        self._study_layout_profile = "A"
        self._learning_tracker = None
        self._stop_learning_pointer_poll()
        self._learning_steps = None
        self._recall_layout_profile_override = None
        self._invalidate_dock_cache()

    def _run_gateway(self, qwin):
        if self._gateway_done:
            return
        self._gateway_done = True
        try:
            self._hide_loading_screen()
            from .experiment import run_gateway
            info = run_gateway(qwin)
            if info is None:
                if hasattr(self, "_suppress_timer"):
                    self._suppress_timer.stop()
                _log("gateway cancelled -> quitting Krita")
                self._request_quit(force=True)
                return
            self.session = info
            from .experiment_log import start_session
            start_session(self.session)
            self._on_new_session_started()
            self._gateway_ok = True
            self._ensure_shortcuts_blocked(qwin)
            try:
                from .video_panel import reset_video_state
                reset_video_state()
            except Exception:
                _log(traceback.format_exc())
            if hasattr(self, "_suppress_timer"):
                self._suppress_timer.stop()
            session1 = info.get("session") == 1
            if session1:
                # Session 1: stay on gateway screens until the first tutorial opens.
                qwin.hide()
                _log("session 1: Krita stays hidden until tutorial")
                self._setup_after_gateway(qwin, light=True)
                self._lock_window(qwin, show=False)
                self._run_session1(qwin)
            elif info.get("session") == 2:
                qwin.hide()
                _log("session 2: Krita stays hidden until opening recall")
                self._setup_after_gateway(qwin, light=True)
                self._lock_window(qwin, show=False)
                self._run_session2(qwin)
            else:
                _log("gateway done: polished reveal")
                self._arm_loading_screen("Preparing workspace…", 3)
                self._setup_after_gateway(qwin, light=False, defer_apply=False)
                self._lock_window(qwin, show=False)

                def _prepare():
                    self._ensure_ui_customized(qwin)

                def _after_reveal(ok):
                    if ok:
                        QTimer.singleShot(
                            300, lambda q=qwin: self._update_video_panel(q))

                self._run_polished_reveal(qwin, _prepare, on_ready=_after_reveal)
        except Exception:
            _log(traceback.format_exc())

    def _setup_after_gateway(self, qwin, light=False, defer_apply=True):
        """Wire experiment hooks. light=True for session 1 (defer heavy UI work)."""
        self._install_new_override(qwin)
        try:
            QApplication.instance().focusChanged.connect(self._on_focus_changed)
        except Exception:
            _log(traceback.format_exc())
        if light:
            return
        if defer_apply:
            QTimer.singleShot(200, lambda q=qwin: self._ensure_ui_customized(q))
        try:
            notifier = Krita.instance().notifier()
            notifier.setActive(True)
            notifier.imageCreated.connect(
                lambda *a: self._schedule_apply(qwin))
            notifier.viewCreated.connect(
                lambda *a: self._schedule_apply(qwin))
        except Exception:
            _log(traceback.format_exc())
        try:
            for st in qwin.findChildren(QStackedWidget):
                if not st.property("hideui_stack"):
                    st.currentChanged.connect(
                        lambda idx, q=qwin: self._on_view_changed(q))
                    st.setProperty("hideui_stack", True)
        except Exception:
            _log(traceback.format_exc())

    def _ensure_ui_customized(self, qwin):
        if self._ui_applied or self._quitting or not _qt_alive(qwin):
            return
        self._apply(qwin)
        self._ui_applied = True
        _log("UI customized (one-time)")

    def _focus_canvas(self, qwin):
        """Give keyboard focus to the paint canvas (frameless Krita often needs this)."""
        try:
            if not _qt_alive(qwin):
                return
            qwin.activateWindow()
            qwin.raise_()
            if self._canvas_w is not None and _qt_alive(self._canvas_w):
                if self._canvas_w.isVisible() and self._canvas_w.isEnabled():
                    self._canvas_w.setFocus(Qt.OtherFocusReason)
                    return
            for w in qwin.findChildren(QWidget):
                cls = w.metaObject().className()
                if "Canvas" in cls and w.isVisible() and w.isEnabled():
                    self._canvas_w = w
                    w.setFocus(Qt.OtherFocusReason)
                    return
            qwin.setFocus(Qt.OtherFocusReason)
            self._suppress_canvas_floating_messages(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _force_canvas_if_needed(self, qwin):
        """Session 1 must stay on the canvas — never flash the welcome screen."""
        if self._switch_to_canvas(qwin):
            return
        try:
            if not _qt_alive(qwin) or not self._stacked_on_welcome(qwin):
                return
            self._new_default(force=True)
            _log("session1: creating document to skip welcome")
        except Exception:
            _log(traceback.format_exc())

    def _on_view_changed(self, qwin):
        if not self._ui_applied:
            return
        if self._in_session1_flow() and self._is_welcome_visible(qwin):
            QTimer.singleShot(0, lambda: self._force_canvas_if_needed(qwin))
            return
        if self._is_welcome_visible(qwin):
            self._video_shown_for_canvas = False
        self._ensure_study_chrome(qwin)
        self._show_study_toolbars(qwin)
        self._hide_document_chrome(qwin)
        self._configure_native_brush_slider(qwin)
        if not self._is_session1() and getattr(
                self, "_study_layout_profile", "A") != "A":
            self._schedule_study_layout_refresh(qwin)
        self._update_text_tool_ui(qwin)
        if not self._in_session1_flow():
            self._update_content_zone(qwin)
        self._update_video_panel(qwin)
        if not self._is_welcome_visible(qwin):
            QTimer.singleShot(250, lambda: self._focus_canvas(qwin))

    def _screen_geometry(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            from PyQt5.QtCore import QRect
            return QRect(0, 0, 1920, 1080)
        return screen.availableGeometry()

    def _compute_layout(self, qwin=None):
        """Krita left + video right; welcome screen centers Krita alone."""
        base = DEFAULT_LAYOUT
        if self.session:
            key = "%s-%s" % (self.session["condition"], self.session["session"])
            base = SESSION_LAYOUTS.get(key, DEFAULT_LAYOUT)
        ui_w, ui_h = base["ui_w"], base["ui_h"]
        vw = base["video_w"]
        vh = ui_h
        geo = self._screen_geometry()
        welcome_only = (
            qwin is not None and self._win_locked and self._is_welcome_visible(qwin))
        if welcome_only:
            kx = geo.x() + max(0, (geo.width() - ui_w) // 2)
            ky = geo.y() + max(0, (geo.height() - ui_h) // 2)
            kx = max(geo.x(), min(kx, geo.x() + max(0, geo.width() - ui_w)))
            ky = max(geo.y(), min(ky, geo.y() + max(0, geo.height() - ui_h)))
        else:
            pair_w = ui_w + LAYOUT_PANEL_GAP + vw
            kx = geo.x() + max(0, (geo.width() - pair_w) // 2)
            ky = geo.y() + max(0, (geo.height() - ui_h) // 2)
            kx = max(geo.x(), min(kx, geo.x() + max(0, geo.width() - pair_w)))
            ky = max(geo.y(), min(ky, geo.y() + max(0, geo.height() - ui_h)))
        vx = kx + ui_w + LAYOUT_PANEL_GAP
        vy = ky
        return {
            "krita_pos": QPoint(kx, ky),
            "krita_size": QSize(ui_w, ui_h),
            "video_pos": QPoint(vx, vy),
            "video_size": QSize(vw, vh),
        }

    def _compute_geometry(self, qwin=None):
        layout = self._compute_layout(qwin)
        return layout["krita_pos"], layout["krita_size"]

    def _should_show_video(self, qwin):
        if self._break_active or self._recall_active:
            return True
        if self._in_session1_flow() and self._is_welcome_visible(qwin):
            return False
        if self._is_welcome_visible(qwin):
            return False
        if self._is_session1() or (self.session and self.session.get("session") == 2):
            return self._tutorial_active and not self._recall_active
        return True

    def _update_video_panel(self, qwin):
        """Show video only on the canvas UI — never on the welcome screen."""
        if self._quitting or not _qt_alive(qwin):
            return
        try:
            from .video_panel import get_video_panel, _SHUTTING_DOWN
            if _SHUTTING_DOWN:
                return
            panel = get_video_panel()
            if panel is None or not self._win_locked:
                return
            self._video_panel = panel
            layout = self._compute_layout(qwin)
            if self._recall_active:
                msg = getattr(self, "_recall_panel_message", None) or {}
                from .recall_test import RECALL_SIDE_PANEL
                title = msg.get("title", RECALL_SIDE_PANEL["title"])
                body = msg.get("body", RECALL_SIDE_PANEL["body"])
                on_start = None
                if (self._recall_awaiting_first_question
                        and not getattr(self, "_recall_auto_starting", False)):
                    on_start = self._on_recall_start_from_panel
                panel.show_recall_instructions_panel(
                    layout["video_pos"], layout["video_size"], title, body,
                    on_start=on_start)
                return
            if self._tutorial_active and self._should_show_video(qwin):
                if self._learning_steps:
                    self._refresh_learning_step_panel(qwin)
                else:
                    from .learning_instructions import get_learning_instructions
                    learn_num = int(getattr(self, "_active_learn_num", 1) or 1)
                    inst = get_learning_instructions(self.session, learn_num)
                    panel.show_learning_instructions_panel(
                        layout["video_pos"], layout["video_size"],
                        inst["title"], inst["steps"], inst.get("phase", 1))
                return
            if not self._should_show_video(qwin):
                self._video_shown_for_canvas = False
                panel.hide_panel()
                return
            # Video playback disabled for study packages (no ffmpeg).
            self._video_shown_for_canvas = False
            panel.hide_panel()
        except Exception:
            _log(traceback.format_exc())

    def _present_krita(self, qwin):
        """Show and foreground Krita after intro / gateway screens."""
        try:
            from .experiment import restore_krita_ui
            if _qt_alive(qwin):
                qwin.show()
                qwin.raise_()
                qwin.activateWindow()
            restore_krita_ui(qwin)
            QApplication.processEvents()
        except Exception:
            _log(traceback.format_exc())

    def _arm_loading_screen(self, message="Loading workspace…", percent=0,
                            title=None, hide_krita=True, raise_only=False):
        """Show the full-screen learning/recall loading cover."""
        try:
            if self._loading_window is None:
                from .loading_screen import LoadingWindow
                self._loading_window = LoadingWindow()
            if not self._loading_armed:
                self._loading_armed = True
                self._loading_started_at = time.monotonic()
            self._loading_window.show_loading(raise_only=raise_only)
            self._loading_window.set_progress(
                percent, message, title=title or "Preparing workspace")
            if hide_krita and self._qwin_alive():
                self._qwin.hide()
            if not raise_only:
                from .experiment import suppress_krita_ui
                suppress_krita_ui(self._loading_window)
            else:
                self._loading_window.raise_()
                self._loading_window.activateWindow()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            _log(traceback.format_exc())

    def _show_loading_screen(self):
        self._arm_loading_screen()

    def _hide_loading_screen(self):
        self._loading_armed = False
        self._loading_started_at = None
        if self._loading_window is not None:
            self._loading_window.dismiss()

    def _update_loading_progress(self, percent, message):
        if self._loading_window is not None:
            self._loading_window.set_progress(percent, message)

    def _run_hidden_polish_chrome(self, qwin):
        """Study chrome setup while the window is still hidden."""
        if not _qt_alive(qwin):
            return
        self._ensure_study_chrome(qwin)
        self._show_study_toolbars(qwin)
        self._hide_document_chrome(qwin)
        self._configure_native_brush_slider(qwin)
        self._update_content_zone(qwin)
        self._suppress_canvas_floating_messages(qwin)

    def _sync_polish_pass(self, qwin):
        """One immediate polish pass before reveal; _apply keeps deferred timers."""
        if not _qt_alive(qwin):
            return
        self._run_hidden_polish_chrome(qwin)
        self._trim_brush_presets(qwin)
        self._fix_preset_gap(qwin)
        self._trim_panel_commands(qwin)
        QApplication.processEvents()

    def _run_polished_reveal(self, qwin, prepare_fn, on_ready=None,
                             skip_krita_reveal=False):
        """Show loading during real setup work, reveal as soon as prep finishes."""
        if self._quitting or not _qt_alive(qwin):
            if on_ready:
                on_ready(False)
            return
        if self._polish_reveal_active:
            _log("polished reveal already active")
            if on_ready:
                on_ready(False)
            return
        self._polish_reveal_active = True
        if not self._loading_armed:
            self._arm_loading_screen("Preparing workspace…", 3)
        else:
            current = 3
            if self._loading_window is not None:
                current = self._loading_window._bar.value()
            self._update_loading_progress(
                max(3, current), "Preparing workspace…")
        qwin.hide()
        from .experiment import suppress_krita_ui
        suppress_krita_ui(self._loading_window)

        def finish_reveal():
            self._polish_reveal_active = False
            self._update_loading_progress(100, "Ready")
            QApplication.processEvents()
            if skip_krita_reveal:
                # Keep the full-screen cover; recall auto-start dismisses it.
                if self._qwin_alive():
                    pos, size = self._compute_geometry(qwin)
                    self._fixed_pos = pos
                    self._fixed_size = size
                    qwin.setFixedSize(size)
                    qwin.move(pos)
                    self._lock_window(qwin, show=False)
                _log("polished reveal complete (krita deferred, cover kept)")
            else:
                self._hide_loading_screen()
                self._present_krita(qwin)
                if self._qwin_alive():
                    self._lock_window(qwin, show=True)
                    self._enforce_window_geometry()
                QTimer.singleShot(100, lambda: self._focus_canvas(qwin))
                _log("polished reveal complete")
            if on_ready:
                on_ready(True)

        def start_prepare():
            try:
                prepare_fn()
            except Exception:
                _log(traceback.format_exc())
                self._polish_reveal_active = False
                self._hide_loading_screen()
                if on_ready:
                    on_ready(False)
                return
            self._sync_polish_pass(qwin)
            # Extra settle so the full-screen cover never drops mid-layout.
            QTimer.singleShot(LOADING_EXTRA_SETTLE_MS, finish_reveal)

        def tick_progress():
            if self._quitting or not self._polish_reveal_active:
                return
            started = self._loading_started_at or time.monotonic()
            elapsed_ms = int((time.monotonic() - started) * 1000)
            percent = min(90, 10 + elapsed_ms // 40)
            message = (
                "Preparing canvas…" if elapsed_ms < 600
                else "Preparing workspace…")
            self._update_loading_progress(percent, message)
            QTimer.singleShot(50, tick_progress)

        tick_progress()
        QTimer.singleShot(0, start_prepare)

    def _ensure_study_chrome(self, qwin):
        """Row 1: gray bar with close (left) and timer (right)."""
        try:
            if not _qt_alive(qwin) or not qwin.isVisible():
                return

            if self._study_toolbar is None:
                self._study_toolbar = QToolBar("Study", qwin)
                self._study_toolbar.setObjectName(STUDY_CHROME_TOOLBAR)
                self._study_toolbar.setMovable(False)
                self._study_toolbar.setFloatable(False)
                self._study_toolbar.setIconSize(QSize(1, 1))
                self._study_toolbar.setMinimumHeight(STUDY_TOP_BAR_H)
                self._study_toolbar.setSizePolicy(
                    QSizePolicy.Expanding, QSizePolicy.Fixed)
                self._study_toolbar.setStyleSheet(
                    "QToolBar { background-color: #e8eaeb; border: none;"
                    " border-bottom: 1px solid #b8b8b8; padding: 0px; margin: 0px; }")

                bar = QWidget()
                bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                bar.setStyleSheet("background-color: #e8eaeb;")
                bar_lay = QHBoxLayout(bar)
                bar_lay.setContentsMargins(12, 0, 12, 0)
                bar_lay.setSpacing(8)
                bar_lay.setAlignment(Qt.AlignVCenter)

                self._close_btn = _MacCloseButton(
                    bar, on_click=lambda: self._request_quit(force=False))
                self._close_btn.setToolTip("Close")
                bar_lay.addWidget(self._close_btn, 0, Qt.AlignVCenter)

                bar_lay.addStretch(1)

                self._skip_learn_btn = QPushButton("Skip")
                self._skip_learn_btn.setStyleSheet(SKIP_LEARN_STYLE)
                self._skip_learn_btn.setToolTip(
                    "Experimenter: skip this learning phase (password required)")
                self._skip_learn_btn.hide()
                self._skip_learn_btn.clicked.connect(self._on_skip_learning_click)
                self._skip_learn_btn.installEventFilter(self)
                bar_lay.addWidget(self._skip_learn_btn, 0, Qt.AlignVCenter)

                self._next_recall_btn = QPushButton("Next question")
                self._next_recall_btn.setStyleSheet(NEXT_RECALL_STYLE)
                self._next_recall_btn.setToolTip(
                    "Continue to the next recall question")
                self._next_recall_btn.hide()
                self._next_recall_btn.clicked.connect(self._on_next_recall_click)
                self._next_recall_btn.installEventFilter(self)
                bar_lay.addWidget(self._next_recall_btn, 0, Qt.AlignVCenter)

                self._timer_label = QLabel("")
                self._timer_label.setFocusPolicy(Qt.NoFocus)
                self._timer_label.setAlignment(Qt.AlignCenter)
                self._timer_label.setStyleSheet(TIMER_STYLE_NORMAL)
                bar_lay.addWidget(self._timer_label, 0, Qt.AlignVCenter)

                bar_action = _ExpandingWidgetAction(bar, self._study_toolbar)
                self._study_toolbar.addAction(bar_action)
                tb_lay = self._study_toolbar.layout()
                if tb_lay is not None:
                    tb_lay.setContentsMargins(0, 0, 0, 0)
                    tb_lay.setSpacing(0)

            self._order_study_toolbar(qwin)
            self._study_toolbar.show()
        except Exception:
            _log(traceback.format_exc())

    def _first_native_toolbar(self, qwin):
        for name in NATIVE_TOOLBARS + ("mainToolBar",):
            tb = qwin.findChild(QToolBar, name)
            if tb is not None and _qt_alive(tb) and tb.isVisible():
                return tb
        for tb in qwin.findChildren(QToolBar):
            if (tb.objectName() != STUDY_CHROME_TOOLBAR
                    and _qt_alive(tb) and tb.isVisible()):
                return tb
        return None

    def _study_toolbar_needs_reorder(self, qwin):
        """Study chrome must sit on row 1; undo/redo + brush size on row 2."""
        study = self._study_toolbar
        native = self._first_native_toolbar(qwin)
        if study is None or native is None or not _qt_alive(study):
            return False
        if not study.isVisible() or not native.isVisible():
            return False
        # Same row or study below native → wrong stacking.
        return study.y() >= native.y() - 2

    def _order_study_toolbar(self, qwin):
        """Row 1: close / skip / timer. Row 2: Krita undo-redo and brush size."""
        if not _qt_alive(qwin) or self._study_toolbar is None:
            return
        try:
            study = self._study_toolbar
            anchor = self._first_native_toolbar(qwin)
            if anchor is None:
                if not self._study_toolbar_ready:
                    qwin.addToolBar(Qt.TopToolBarArea, study)
                    qwin.addToolBarBreak(Qt.TopToolBarArea)
                    self._study_toolbar_ready = True
                study.show()
                return

            same_row = abs(study.y() - anchor.y()) < 8
            needs = (not self._study_toolbar_ready
                     or self._study_toolbar_needs_reorder(qwin))
            if needs:
                qwin.removeToolBar(study)
                qwin.insertToolBar(anchor, study)
                if same_row or study.y() >= anchor.y() - 2:
                    qwin.insertToolBarBreak(anchor)
                self._study_toolbar_ready = True
            study.show()
        except Exception:
            _log(traceback.format_exc())

    def _schedule_study_toolbar_order(self, qwin):
        """Re-apply toolbar row order after async layout restores (recall)."""
        self._order_study_toolbar(qwin)
        for delay in (80, 400):
            QTimer.singleShot(
                delay, lambda q=qwin: self._order_study_toolbar(q))

    def _lock_window(self, qwin, show=True):
        """Fixed Krita window on the left; video panel on the right."""
        try:
            self._qwin = qwin
            pos, size = self._compute_geometry(qwin)
            self._fixed_pos = pos
            self._fixed_size = size

            qwin.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            qwin.setFixedSize(size)
            qwin.move(pos)
            if show:
                qwin.show()
            try:
                qwin.setDockOptions(QMainWindow.NoDockOptions)
            except (AttributeError, TypeError):
                try:
                    qwin.setDockOptions(QMainWindow.DockOptions(0))
                except Exception:
                    pass

            if not qwin.property("hideui_winfilter"):
                qwin.installEventFilter(self)
                qwin.setProperty("hideui_winfilter", True)

            self._win_locked = True
            self._ensure_shortcuts_blocked(qwin)
            if show:
                self._lock_dock_panels(qwin)
                qwin.raise_()
                qwin.activateWindow()
                self._start_position_guard()
            _log("krita locked %dx%d at %s show=%s" % (
                size.width(), size.height(), pos, show))
        except Exception:
            _log(traceback.format_exc())

    def _suppress_canvas_floating_messages(self, qwin):
        """Stop the blinking 'Zoom: N %' overlay on canvas resize."""
        if not _qt_alive(qwin):
            return
        for w in qwin.findChildren(QWidget):
            cls = w.metaObject().className()
            if cls == "KisView":
                try:
                    w.setShowFloatingMessage(False)
                except Exception:
                    pass
                if not w.property("hideui_zoom_filter"):
                    w.installEventFilter(self)
                    w.setProperty("hideui_zoom_filter", True)
            elif cls == "KisFloatingMessage":
                text = ""
                for lbl in w.findChildren(QLabel):
                    text += lbl.text() or ""
                if "zoom" in text.lower():
                    w.hide()

    def _lock_dock_panel_heights(self, qwin):
        """Keep color + layers panels at Layout A height, not full column."""
        if not _qt_alive(qwin):
            return
        for dock in qwin.findChildren(QDockWidget):
            name = dock.objectName()
            if name not in DEFAULT_DOCK_HEIGHTS:
                continue
            if not dock.isVisible():
                continue
            h = DEFAULT_DOCK_HEIGHTS[name]
            dock.setMinimumHeight(h)
            dock.setMaximumHeight(h)

    def _study_layout_signature(self, qwin, profile, flags):
        parts = [profile, flags.get("presets_in_toolbar"), self._presets_in_toolbar]
        for name in sorted(KEEP_DOCKERS):
            dock = self._dock_by_name(qwin, name)
            if dock is None:
                parts.append((name, None))
                continue
            try:
                area = int(qwin.dockWidgetArea(dock))
            except Exception:
                area = -1
            parts.append((name, area, dock.isVisible()))
        return tuple(parts)

    def _update_content_zone(self, qwin):
        try:
            if not self._win_locked:
                return
            self._lock_dock_panel_heights(qwin)
            self._lock_dock_splitters(qwin)
            self._enforce_window_geometry()
        except Exception:
            _log(traceback.format_exc())

    def _on_splitter_moved(self, splitter):
        try:
            saved = splitter.property("hideui_saved_sizes")
            if not saved:
                splitter.setProperty("hideui_saved_sizes", splitter.sizes())
                return
            if list(splitter.sizes()) != list(saved):
                splitter.blockSignals(True)
                splitter.setSizes(saved)
                splitter.blockSignals(False)
        except Exception:
            _log(traceback.format_exc())

    def _sync_kritarc_layout_state(self, profile):
        """Point kritarc's [MainWindow] State at the target profile blob.

        Krita re-applies that State on every welcome->canvas switch; keeping it
        equal to the layout we want makes Krita's own restores work for us
        instead of against us.
        """
        try:
            if not self._qwin_alive():
                return
            from .layout_state import load_state_blob, sync_state_to_kritarc
            key, w, h = self._layout_state_key(self._qwin, profile)
            blob = load_state_blob(key, w, h)
            if blob is not None:
                sync_state_to_kritarc(blob)
        except Exception:
            _log(traceback.format_exc())

    def _set_study_layout_profile(self, profile):
        profile = profile or "A"
        if self._study_layout_profile != profile:
            _log("study layout profile: %s -> %s" % (
                self._study_layout_profile, profile))
            self._study_layout_profile = profile
            self._study_layout_applied_sig = None
        if not self._qwin_alive():
            return
        self._sync_kritarc_layout_state(profile)
        if self._is_session1() or profile == "A":
            self._lock_dock_panels_layout_a(self._qwin)
        else:
            self._apply_study_layout(self._qwin)

    def _invalidate_dock_cache(self):
        # Drop only dead references. The PresetDocker intermittently drops out
        # of findChild, and a live cached ref is the only way to recover it —
        # wiping live refs here used to lose the brushes panel permanently.
        self._dock_refs = {
            name: ref for name, ref in self._dock_refs.items()
            if _qt_alive(ref)}
        self._dock_ref_warned = set()
        self._brushes_toolbar_ref = None

    def _minimize_preset_dock_title(self, dock):
        """Thin preset strips need every pixel for brush icons, not a title row."""
        if dock is None or not _qt_alive(dock):
            return
        spacer = QWidget()
        spacer.setFixedHeight(1)
        spacer.setMaximumHeight(1)
        dock.setTitleBarWidget(spacer)

    def _ensure_preset_chooser_visible(self, root):
        """Force brush preset views to keep non-zero size (prevents title-only panels)."""
        if root is None or not _qt_alive(root):
            return
        root.show()
        root.setMinimumHeight(PRESET_STRIP_HEIGHT - 4)
        root.setMaximumHeight(PRESET_STRIP_HEIGHT)
        root.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_preset_icon_metrics(root)
        for chooser in root.findChildren(QWidget):
            if chooser.metaObject().className() != "KisResourceItemChooser":
                continue
            chooser.show()
            chooser.setMinimumHeight(PRESET_STRIP_HEIGHT - 4)
            chooser.setMaximumHeight(PRESET_STRIP_HEIGHT)
            chooser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for view in chooser.findChildren(QAbstractItemView):
                view.show()
                view.setMinimumHeight(PRESET_STRIP_HEIGHT - 4)
                view.setMaximumHeight(PRESET_STRIP_HEIGHT)
                view.setMinimumWidth(120)
                view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _apply_preset_icon_metrics(self, root):
        """Keep thumbnails sharp inside the 32px strip (fixed icon cell, no stretch)."""
        if root is None or not _qt_alive(root):
            return
        icon = QSize(PRESET_ICON_SIZE, PRESET_ICON_SIZE)
        cell = QSize(PRESET_ICON_CELL, PRESET_STRIP_HEIGHT)
        for view in root.findChildren(QAbstractItemView):
            try:
                if hasattr(view, "setIconSize"):
                    view.setIconSize(icon)
                if hasattr(view, "setGridSize"):
                    view.setGridSize(cell)
                if hasattr(view, "setUniformItemSizes"):
                    view.setUniformItemSizes(True)
                if hasattr(view, "setSpacing"):
                    view.setSpacing(2)
                if hasattr(view, "setFlow"):
                    view.setFlow(QListView.LeftToRight)
                if hasattr(view, "setWrapping"):
                    view.setWrapping(False)
            except Exception:
                pass
        for view in root.findChildren(QListView):
            try:
                view.setViewMode(QListView.IconMode)
                view.setMovement(QListView.Static)
                view.setResizeMode(QListView.Adjust)
                view.setWrapping(False)
                view.setFlow(QListView.LeftToRight)
                view.setIconSize(icon)
                view.setGridSize(cell)
                view.setUniformItemSizes(True)
                view.setSpacing(2)
            except Exception:
                pass

    def _configure_top_preset_docker(self, preset):
        """Horizontal brush strip across the top (A_C1 / A_C1_C2 / B)."""
        if preset is None or not _qt_alive(preset):
            return
        strip_h = TOP_PRESET_DOCK_HEIGHT
        self._clear_dock_constraints(preset)
        preset.show()
        self._minimize_preset_dock_title(preset)
        preset.setMinimumHeight(strip_h)
        preset.setMaximumHeight(strip_h + 8)
        preset.setMinimumWidth(0)
        preset.setMaximumWidth(16777215)
        content = preset.widget()
        if content is not None and content is not self._preset_dock_placeholder:
            self._configure_preset_horizontal(content)
            self._ensure_preset_chooser_visible(content)
        for delay in (100, 400, 1200):
            QTimer.singleShot(
                delay,
                lambda p=preset: self._ensure_preset_chooser_visible(
                    p.widget() if p is not None and p.widget() is not None else p))

    def _place_presets_in_top_dock(self, qwin):
        """Deprecated — presets belong inline in BrushesAndStuff."""
        self._embed_presets_in_toolbar(qwin)

    def _preset_popup_is_placed(self, qwin, profile):
        """True when the brush preset widget is visible in the right place."""
        from .layout_profiles import profile_flags
        flags = profile_flags(profile)
        popup = self._preset_popup_widget
        if popup is None or not _qt_alive(popup):
            popup = self._find_preset_popup_widget(qwin)
        if popup is None or not _qt_alive(popup):
            return False
        if not self._preset_widget_has_chooser(popup):
            return False
        if flags["presets_in_toolbar"]:
            if not self._presets_in_toolbar:
                return False
            tb = self._find_brushes_toolbar(qwin)
            action = self._preset_toolbar_action
            if tb is None or not tb.isVisible():
                return False
            if action is None or action not in tb.actions():
                return False
            if popup is None or not popup.isVisible() or popup.height() < 20:
                return False
            dock = self._dock_by_name(qwin, "PresetDocker")
            if dock is not None and dock.isVisible():
                return False
            return True
        dock = self._dock_by_name(qwin, "PresetDocker")
        if dock is None:
            return False
        w = dock.widget()
        if w is self._preset_dock_placeholder:
            return False
        if w is not popup or self._preset_widget_has_chooser(w):
            if qwin.isVisible() and not dock.isVisible():
                return False
            return popup.isVisible()
        return False

    def _preset_panel_broken(self, qwin, profile):
        return not self._preset_popup_is_placed(qwin, profile)

    def _heal_preset_panel(self, qwin):
        """Self-heal pass: put the brushes back wherever the profile wants them."""
        if (self._quitting or not _qt_alive(qwin)
                or self._phase_transition_busy or not qwin.isVisible()
                or self._is_welcome_visible(qwin)):
            return
        profile = getattr(self, "_study_layout_profile", "A")
        if self._is_session1():
            profile = "A"
        try:
            if not self._preset_panel_broken(qwin, profile):
                return
            _log("preset panel broken for profile %s — healing" % profile)
            self._ensure_presets_for_profile(qwin, profile)
            if self._preset_panel_broken(qwin, profile):
                _log("preset panel still broken after heal attempt")
            else:
                _log("preset panel healed for profile %s" % profile)
                if self._recall_active:
                    self._refresh_preset_docker_recall(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _run_ui_polish_pass(self, qwin):
        """One deferred pass for trim/slider/hook work after layout settles."""
        if self._quitting or not _qt_alive(qwin):
            return
        try:
            self._prime_dock_cache(qwin)
            self._heal_preset_panel(qwin)
            self._trim_brush_presets(qwin)
            self._trim_panel_commands(qwin)
            self._configure_native_brush_slider(qwin)
            self._hook_toolbox_tool_tracking(qwin)
            self._hook_study_brush_size_sync(qwin)
            self._configure_layers_panel(qwin)
            self._disable_krita_shortcuts(qwin)
            self._update_text_tool_ui(qwin)
            self._ensure_default_brush()
            self._order_study_toolbar(qwin)
            self._hide_document_chrome(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _schedule_ui_polish(self, qwin):
        self._run_ui_polish_pass(qwin)
        for delay in (400, 1200):
            QTimer.singleShot(
                delay, lambda q=qwin: self._run_ui_polish_pass(q))

    def _dock_by_name(self, qwin, name):
        dock = qwin.findChild(QDockWidget, name)
        if dock is not None:
            self._dock_refs[name] = dock
            return dock
        # The PresetDocker intermittently drops out of findChild after its
        # content is embedded in the toolbar; fall back to the live reference
        # so layout code can still reposition and restore it.
        cached = self._dock_refs.get(name)
        if cached is not None and _qt_alive(cached):
            if name not in self._dock_ref_warned:
                self._dock_ref_warned.add(name)
                _log("dock %s recovered via cached reference" % name)
            return cached
        # Last resort: scan every widget in the app. Slow, but only runs in
        # the already-broken state and rescues the dock wherever it ended up.
        try:
            for w in QApplication.allWidgets():
                if isinstance(w, QDockWidget) and w.objectName() == name:
                    if not _qt_alive(w):
                        continue
                    self._dock_refs[name] = w
                    _log("dock %s recovered via allWidgets scan" % name)
                    return w
        except Exception:
            _log(traceback.format_exc())
        return None

    def _prime_dock_cache(self, qwin):
        """Cache live refs for the study dockers while findChild still works."""
        if not _qt_alive(qwin):
            return
        for dock in qwin.findChildren(QDockWidget):
            if dock.objectName() in KEEP_DOCKERS:
                self._dock_refs[dock.objectName()] = dock

    def _find_brushes_toolbar(self, qwin):
        if self._brushes_toolbar_ref is not None and _qt_alive(self._brushes_toolbar_ref):
            return self._brushes_toolbar_ref
        for tb in qwin.findChildren(QToolBar):
            if tb.objectName() == "BrushesAndStuff":
                self._brushes_toolbar_ref = tb
                return tb
        return None

    def _clear_dock_constraints(self, dock):
        if dock is None:
            return
        dock.setMinimumWidth(0)
        dock.setMaximumWidth(16777215)
        dock.setMinimumHeight(0)
        dock.setMaximumHeight(16777215)

    def _add_single_dock(self, qwin, area, dock, width, height=None):
        if dock is None:
            return
        self._clear_dock_constraints(dock)
        dock.show()
        dock.setMinimumWidth(width)
        dock.setMaximumWidth(width)
        if height is not None:
            dock.setMinimumHeight(height)
            dock.setMaximumHeight(height)
        qwin.addDockWidget(area, dock)

    def _add_dock_column(self, qwin, area, specs):
        """Stack docks vertically in one main-window edge (specs: dock, width, height)."""
        specs = [(d, w, h) for d, w, h in specs if d is not None]
        if not specs:
            return
        first, width, height = specs[0]
        self._clear_dock_constraints(first)
        first.show()
        first.setMinimumWidth(width)
        first.setMaximumWidth(width)
        qwin.addDockWidget(area, first)
        prev = first
        docks = [first]
        heights = [height]
        for dock, width, height in specs[1:]:
            self._clear_dock_constraints(dock)
            dock.show()
            dock.setMinimumWidth(width)
            dock.setMaximumWidth(width)
            qwin.splitDockWidget(prev, dock, Qt.Vertical)
            prev = dock
            docks.append(dock)
            heights.append(height)
        if len(docks) > 1:
            qwin.resizeDocks(docks, heights, Qt.Vertical)
        self._lock_dock_panel_heights(qwin)

    def _is_preset_strip_dock(self, qwin, dock):
        """Top/bottom horizontal preset bars must not get a title row."""
        if dock is None or dock.objectName() != "PresetDocker":
            return False
        try:
            area = qwin.dockWidgetArea(dock)
        except Exception:
            return False
        return area in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea)

    def _preset_dock_embedded_in_toolbar(self, profile=None):
        """True when brushes live in BrushesAndStuff, not the PresetDocker."""
        if self._presets_in_toolbar:
            return True
        if profile is None:
            profile = getattr(self, "_study_layout_profile", "A")
        try:
            from .layout_profiles import profile_flags
            return bool(profile_flags(profile).get("presets_in_toolbar"))
        except Exception:
            return False

    def _park_preset_dock_for_toolbar_embed(self, qwin, dock):
        """Remove PresetDocker from the dock column so its title cannot overlap neighbors."""
        if dock is None or not _qt_alive(dock):
            return
        try:
            area = qwin.dockWidgetArea(dock)
            if area != Qt.NoDockWidgetArea:
                qwin.removeDockWidget(dock)
        except Exception:
            pass
        self._minimize_preset_dock_title(dock)
        dock.hide()

    def _apply_dock_title(self, dock):
        """Non-closable dock header showing the panel name."""
        if dock is None or not _qt_alive(dock):
            return
        if getattr(self, "_recall_active", False):
            self._minimize_preset_dock_title(dock)
            try:
                dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
            except Exception:
                pass
            return
        title = dock.windowTitle() or dock.objectName() or ""
        label = dock.findChild(QLabel, "hideuiDockTitle")
        if label is None:
            label = QLabel()
            label.setObjectName("hideuiDockTitle")
            label.setMargin(4)
        label.setText("  " + title)
        dock.setTitleBarWidget(label)
        try:
            dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        except Exception:
            pass

    def _apply_all_dock_titles(self, qwin):
        if not _qt_alive(qwin):
            return
        profile = getattr(self, "_study_layout_profile", "A")
        for dock in qwin.findChildren(QDockWidget):
            name = dock.objectName()
            if name not in KEEP_DOCKERS:
                continue
            if name == "PresetDocker" and self._preset_dock_embedded_in_toolbar(profile):
                self._park_preset_dock_for_toolbar_embed(qwin, dock)
                continue
            if not dock.isVisible():
                continue
            if self._is_preset_strip_dock(qwin, dock):
                self._minimize_preset_dock_title(dock)
                continue
            self._apply_dock_title(dock)

    def _trim_preset_chooser_extras(self, root):
        """Hide import / storage / tag controls on brush preset choosers."""
        if root is None:
            return
        for chooser in root.findChildren(QWidget):
            if chooser.metaObject().className() != "KisResourceItemChooser":
                continue
            for method, arg in (
                    ("showImportExportBtns", False),
                    ("showTaggingBar", False),
                    ("showViewModeBtn", False),
                    ("showStorageBtn", False)):
                try:
                    getattr(chooser, method)(arg)
                except Exception:
                    pass
            for w in chooser.findChildren(QWidget):
                cls = w.metaObject().className()
                obj = w.objectName()
                if cls in HIDE_BY_CLASS:
                    w.hide()
                elif obj in HIDE_BY_OBJNAME:
                    w.hide()
                elif (w.toolTip() or "") in HIDE_BY_TOOLTIP:
                    w.hide()
            for btn in chooser.findChildren(QToolButton):
                # Keep only buttons living inside the preset item view.
                # Everything else (scroll arrows, import/storage/tag/view
                # buttons) is dead weight in the study strip. Krita re-show()s
                # the scroll arrows on every resize/layout change, so hiding
                # alone is not sticky — a zero fixed size is.
                anc = btn.parent()
                in_view = False
                while anc is not None and anc is not chooser:
                    if isinstance(anc, QAbstractItemView):
                        in_view = True
                        break
                    anc = anc.parent()
                if in_view:
                    continue
                btn.hide()
                btn.setEnabled(False)
                btn.setFixedSize(0, 0)

    def _configure_preset_horizontal(self, root):
        if root is None:
            return
        from .layout_profiles import PRESET_LIST_HORIZONTAL
        self._trim_preset_chooser_extras(root)
        for chooser in root.findChildren(QWidget):
            if chooser.metaObject().className() != "KisResourceItemChooser":
                continue
            try:
                chooser.setResponsiveness(True)
            except Exception:
                pass
            try:
                chooser.setListViewMode(PRESET_LIST_HORIZONTAL)
            except Exception:
                pass
            for view in chooser.findChildren(QAbstractItemView):
                try:
                    if hasattr(view, "setListViewMode"):
                        view.setListViewMode(PRESET_LIST_HORIZONTAL)
                except Exception:
                    pass
        # setListViewMode re-shows the scroll arrows; trim again afterwards.
        self._trim_preset_chooser_extras(root)
        self._apply_preset_icon_metrics(root)

    def _schedule_preset_arrow_suppression(self, root):
        """Krita re-shows preset scroll arrows on every resize; keep killing them."""
        if root is None:
            return
        for delay in (0, 50, 150, 400, 800, 1500, 3000):
            QTimer.singleShot(
                delay, lambda r=root: self._trim_preset_chooser_extras(r))

    def _preset_widget_has_chooser(self, widget):
        if widget is None or not _qt_alive(widget):
            return False
        if widget.metaObject().className() == "KisResourceItemChooser":
            return True
        for child in widget.findChildren(QWidget):
            if child.metaObject().className() == "KisResourceItemChooser":
                return True
        return False

    def _find_preset_popup_widget(self, qwin):
        """Find the PresetDocker content widget wherever it was reparented."""
        if not _qt_alive(qwin):
            return None
        candidates = []
        if self._preset_popup_widget is not None and _qt_alive(self._preset_popup_widget):
            candidates.append(self._preset_popup_widget)
        dock = self._dock_by_name(qwin, "PresetDocker")
        if dock is not None:
            w = dock.widget()
            if w is not None and _qt_alive(w):
                candidates.append(w)
        for host in qwin.findChildren(QWidget, "hideuiPresetToolbarHost"):
            lay = host.layout()
            if lay is None:
                continue
            for i in range(lay.count()):
                item = lay.itemAt(i)
                w = item.widget() if item is not None else None
                if w is not None and w.objectName() != "hideuiPresetToolbarTitle":
                    candidates.append(w)
        for ch in qwin.findChildren(QWidget):
            if ch.metaObject().className() != "KisResourceItemChooser":
                continue
            node = ch
            while node.parent() is not None and node.parent() is not qwin:
                node = node.parent()
            if node.parent() is qwin:
                candidates.append(node)
        seen = set()
        for w in candidates:
            wid = id(w)
            if wid in seen:
                continue
            seen.add(wid)
            if w is self._preset_dock_placeholder:
                continue
            if self._preset_widget_has_chooser(w):
                return w
        return None

    def _ensure_presets_for_profile(self, qwin, profile):
        """Make brush presets visible in the right place for this layout profile."""
        from .layout_profiles import profile_flags
        flags = profile_flags(profile)
        popup = self._find_preset_popup_widget(qwin)
        if popup is not None:
            self._preset_popup_widget = popup
        if flags["presets_in_toolbar"]:
            if popup is None:
                _log("ensure_presets: no widget to embed for profile %s" % profile)
                for delay in (200, 600, 1200):
                    QTimer.singleShot(
                        delay,
                        lambda q=qwin, p=profile: self._retry_toolbar_presets(q, p))
                return
            self._embed_presets_in_toolbar(qwin)
            self._trim_brush_presets(qwin)
            self._ensure_toolbar_presets_visible(qwin)
            self._schedule_preset_arrow_suppression(
                self._preset_popup_widget or popup)
        else:
            self._unembed_presets_from_toolbar(qwin)
            popup = self._find_preset_popup_widget(qwin)
            if popup is None:
                _log("ensure_presets: no widget for docker layout %s" % profile)
                return
            dock = self._dock_by_name(qwin, "PresetDocker")
            if dock is None:
                # The original docker was lost/deleted; host the surviving
                # preset widget in a replacement dock so the panel never
                # disappears from Layout A.
                dock = self._recreate_preset_dock(qwin, popup)
            if dock is not None:
                if dock.widget() is not popup:
                    popup.setParent(dock)
                    dock.setWidget(popup)
                dock.show()
                popup.show()
                w = DEFAULT_DOCK_WIDTHS["PresetDocker"]
                dock.setMinimumWidth(w)
                dock.setMaximumWidth(w)
                self._apply_dock_title(dock)
                self._ensure_preset_chooser_visible(popup)
            self._trim_brush_presets(qwin)
            self._fix_preset_gap(qwin)
            self._schedule_preset_gap_fix(qwin)

    def _retry_toolbar_presets(self, qwin, profile):
        if self._quitting or not _qt_alive(qwin):
            return
        from .layout_profiles import profile_flags
        if not profile_flags(profile).get("presets_in_toolbar"):
            return
        if self._preset_popup_is_placed(qwin, profile):
            self._ensure_toolbar_presets_visible(qwin)
            return
        popup = self._find_preset_popup_widget(qwin)
        if popup is None:
            _log("retry_toolbar_presets: still no preset widget")
            return
        self._preset_popup_widget = popup
        self._presets_in_toolbar = False
        self._embed_presets_in_toolbar(qwin)
        self._trim_brush_presets(qwin)
        self._ensure_toolbar_presets_visible(qwin)

    def _ensure_toolbar_presets_visible(self, qwin):
        """Keep toolbar brush strip visible (Session 2 A_C1 / A_C1_C2 / B)."""
        if not _qt_alive(qwin) or self._quitting:
            return
        from .layout_profiles import profile_flags
        profile = getattr(self, "_study_layout_profile", "A")
        if not profile_flags(profile).get("presets_in_toolbar"):
            return
        try:
            tb = self._find_brushes_toolbar(qwin)
            if tb is not None:
                tb.show()
                tb.setVisible(True)
            popup = self._preset_popup_widget
            if popup is None or not _qt_alive(popup):
                popup = self._find_preset_popup_widget(qwin)
                self._preset_popup_widget = popup
            if popup is not None and _qt_alive(popup):
                popup.show()
                self._configure_preset_horizontal(popup)
                self._ensure_preset_chooser_visible(popup)
                host = popup.parentWidget()
                while host is not None and host.objectName() != "hideuiPresetToolbarHost":
                    host = host.parentWidget()
                if host is not None:
                    host.show()
                    host.setMinimumWidth(220)
                    host.setMinimumHeight(28)
                _log(
                    "toolbar presets visible=%s size=%sx%s"
                    % (
                        popup.isVisible(),
                        popup.width(),
                        popup.height()))
        except Exception:
            _log(traceback.format_exc())

    def _recreate_preset_dock(self, qwin, popup):
        """Build a replacement PresetDocker around a surviving preset widget."""
        try:
            dock = QDockWidget("Brush Presets", qwin)
            dock.setObjectName("PresetDocker")
            popup.setParent(dock)
            dock.setWidget(popup)
            popup.show()
            qwin.addDockWidget(Qt.RightDockWidgetArea, dock)
            dock.show()
            self._dock_refs["PresetDocker"] = dock
            self._apply_dock_title(dock)
            _log("PresetDocker recreated around surviving preset widget")
            return dock
        except Exception:
            _log(traceback.format_exc())
            return None

    def _embed_presets_in_toolbar(self, qwin):
        """Brush presets inline on BrushesAndStuff — same row as undo/redo/size."""
        profile = getattr(self, "_study_layout_profile", "A")
        tb = self._find_brushes_toolbar(qwin)
        if tb is None:
            _log("embed presets failed: BrushesAndStuff toolbar not found")
            return
        if self._presets_in_toolbar:
            if self._preset_popup_is_placed(qwin, profile):
                popup = self._preset_popup_widget
                self._configure_preset_horizontal(popup)
                self._ensure_preset_chooser_visible(popup)
                host = popup.parentWidget() if popup is not None else None
                while host is not None and host.objectName() != "hideuiPresetToolbarHost":
                    host = host.parentWidget()
                dock = self._dock_by_name(qwin, "PresetDocker")
                if host is not None:
                    title_lbl = host.findChild(QLabel, "hideuiPresetToolbarTitle")
                    if title_lbl is not None:
                        title = (dock.windowTitle() if dock is not None else "") \
                            or "Brush Presets"
                        title_lbl.setText("  " + title)
                    host.setFixedHeight(PRESET_STRIP_HEIGHT)
                    host.setMinimumHeight(PRESET_STRIP_HEIGHT)
                self._apply_preset_icon_metrics(popup)
                if dock is not None:
                    self._park_preset_dock_for_toolbar_embed(qwin, dock)
                return
            action = self._preset_toolbar_action
            if action is not None and action in tb.actions():
                tb.removeAction(action)
            self._presets_in_toolbar = False
            self._preset_toolbar_action = None

        dock = self._dock_by_name(qwin, "PresetDocker")
        popup = self._find_preset_popup_widget(qwin)
        if popup is None or popup is self._preset_dock_placeholder:
            _log("embed presets skipped: no preset widget found")
            return
        if not self._preset_widget_has_chooser(popup):
            _log("embed presets skipped: widget has no chooser")
            return

        if dock is not None:
            placeholder = self._preset_dock_placeholder
            if placeholder is None or not _qt_alive(placeholder):
                placeholder = dock.widget()
            if placeholder is None or placeholder is popup:
                placeholder = QWidget()
                placeholder.hide()
                dock.setWidget(placeholder)
            self._preset_dock_placeholder = placeholder
            self._park_preset_dock_for_toolbar_embed(qwin, dock)

        preset_title = (dock.windowTitle() if dock is not None else "") \
            or "Brush Presets"
        strip_h = PRESET_STRIP_HEIGHT
        host = QWidget()
        host.setObjectName("hideuiPresetToolbarHost")
        host.setFixedHeight(strip_h)
        host.setMaximumHeight(strip_h)
        host.setMinimumHeight(strip_h)
        host.setMinimumWidth(220)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(host)
        lay.setContentsMargins(2, 0, 4, 0)
        lay.setSpacing(4)
        title_lbl = QLabel("  " + preset_title)
        title_lbl.setObjectName("hideuiPresetToolbarTitle")
        title_lbl.setMargin(0)
        lay.addWidget(title_lbl, 0, Qt.AlignVCenter)
        popup.setParent(host)
        lay.addWidget(popup, 1)
        popup.setMinimumHeight(PRESET_STRIP_HEIGHT - 4)
        popup.setMaximumHeight(PRESET_STRIP_HEIGHT)
        popup.show()
        self._configure_preset_horizontal(popup)
        self._ensure_preset_chooser_visible(popup)
        self._apply_preset_icon_metrics(popup)

        action = QWidgetAction(tb)
        action.setObjectName("hideuiPresetToolbarAction")
        action.setDefaultWidget(host)
        tb.addAction(action)
        if not tb.property("hideui_preset_rescue"):
            tb.setProperty("hideui_preset_rescue", True)
            tb.destroyed.connect(
                lambda *a: self._rescue_preset_popup_from_teardown())

        self._preset_toolbar_action = action
        self._preset_popup_widget = popup
        self._presets_in_toolbar = True
        host.show()
        tb.show()
        tb.raise_()
        _log("brush presets embedded in BrushesAndStuff toolbar (same row)")
        # Krita sometimes collapses the strip after layout; re-apply shortly.
        for delay in (150, 500, 1200):
            QTimer.singleShot(
                delay,
                lambda q=qwin: self._ensure_toolbar_presets_visible(q))

    def _unembed_presets_from_toolbar(self, qwin):
        # No early return on the _presets_in_toolbar flag: a soft detach
        # during document churn clears it while the popup is still parked on
        # the main window, which used to leave the docker empty afterwards.
        if self._presets_in_toolbar:
            tb = self._find_brushes_toolbar(qwin)
            action = self._preset_toolbar_action
            if tb is not None and action is not None:
                tb.removeAction(action)
        popup = self._preset_popup_widget
        dock = self._dock_by_name(qwin, "PresetDocker")
        restored = False
        if popup is not None and _qt_alive(popup) and dock is not None:
            if dock.widget() is not popup:
                popup.setParent(dock)
                dock.setWidget(popup)
            popup.show()
            if qwin.dockWidgetArea(dock) == Qt.NoDockWidgetArea:
                from .layout_profiles import profile_flags
                flags = profile_flags(
                    getattr(self, "_study_layout_profile", "A"))
                if flags.get("presets_in_toolbar"):
                    pass  # re-embed will park it again
                else:
                    qwin.addDockWidget(Qt.RightDockWidgetArea, dock)
            dock.show()
            restored = True
        self._presets_in_toolbar = False
        self._preset_toolbar_action = None
        if restored:
            self._preset_popup_widget = None
            self._preset_dock_placeholder = None
            _log("brush presets restored to PresetDocker")

    def _rescue_preset_popup_from_teardown(self):
        """Reparent the docker's preset widget out of a dying toolbar."""
        if self._quitting:
            return
        try:
            popup = self._preset_popup_widget
            if popup is None or not _qt_alive(popup):
                return
            if not self._qwin_alive():
                return
            popup.hide()
            popup.setParent(self._qwin)
            self._presets_in_toolbar = False
            self._preset_toolbar_action = None
            _log("preset popup rescued from toolbar teardown")
        except Exception:
            _log(traceback.format_exc())

    def _is_condition_c_session2(self):
        if not self.session or self._quitting:
            return False
        return (
            int(self.session.get("session", 0)) == 2
            and (self.session.get("condition") or "A").upper() == "C"
        )

    def _toolbox_uses_horizontal_row(self):
        """Bottom toolbox: one tool per slot in a horizontal row."""
        return (
            bool(self.session) and not self._quitting
            and self._study_uses_bottom_toolbox()
        )

    def _apply_condition_c_toolbox_layout(self, toolbox, qwin):
        """Enforce study toolbox command order (all conditions / sessions)."""
        self._apply_study_toolbox_order(toolbox, qwin)

    def _apply_study_toolbox_order(self, toolbox, qwin):
        """text -> brush -> line -> rect -> ellipse -> move -> gradient -> fill."""
        if toolbox is None or not _qt_alive(toolbox):
            return
        if not bool(self.session) or self._quitting:
            return
        if self._study_uses_bottom_toolbox():
            self._apply_horizontal_toolbox_row(toolbox, qwin)
        else:
            self._apply_ordered_left_toolbox(toolbox, qwin)

    def _schedule_condition_c_toolbox_layout(self, qwin, toolbox):
        if toolbox is None or not bool(self.session):
            return
        for delay in (0, 300):
            QTimer.singleShot(
                delay,
                lambda t=toolbox, q=qwin: self._apply_study_toolbox_order(t, q))

    def _restore_toolbox_custom_host(self, toolbox):
        """Put the native KoToolBox back and recover tool buttons."""
        if toolbox is None or not _qt_alive(toolbox):
            return
        if not (toolbox.property("hideui_toolbox_row_host")
                or toolbox.property("hideui_single_col_host")):
            return
        host = toolbox.widget()
        orphaned = []
        if host is not None and _qt_alive(host):
            oname = host.objectName() or ""
            if oname in ("hideuiToolboxRowHost", "hideuiToolboxSingleColHost"):
                orphaned = [
                    b for b in host.findChildren(QToolButton)
                    if self._keep_toolbox_button(b)
                ]
        original = (
            toolbox.property("hideui_toolbox_row_original")
            or toolbox.property("hideui_single_col_original"))
        if original is not None and _qt_alive(original):
            toolbox.setWidget(original)
        _, ko_toolbox = self._find_toolbox_internals(toolbox)
        if ko_toolbox is not None and orphaned:
            for btn in orphaned:
                btn.setParent(ko_toolbox)
                btn.show()
                btn.setEnabled(True)
        toolbox.setProperty("hideui_toolbox_row_host", False)
        toolbox.setProperty("hideui_single_col_host", False)
        toolbox.setProperty("hideui_toolbox_row_original", None)
        toolbox.setProperty("hideui_single_col_original", None)
        self._force_study_toolbox_visible(toolbox)
        _log("toolbox: restored native widget (%d buttons recovered)" % len(orphaned))

    def _apply_horizontal_toolbox_row(self, toolbox, qwin):
        """One tool per slot in a centered horizontal row — explicit button layout."""
        if toolbox is None or not _qt_alive(toolbox) or not self._study_uses_bottom_toolbox():
            return None
        self._restore_toolbox_custom_host(toolbox)
        self._unwrap_bottom_toolbox(toolbox)
        buttons = self._ordered_study_toolbox_buttons(toolbox)
        if not buttons:
            return None
        btn_size = max(28, max(
            btn.iconSize().width() for btn in buttons) + 4)
        count = len(buttons)
        strip_w = count * btn_size + max(0, count - 1) * 4 + 24
        strip_h = btn_size + 16

        if not toolbox.property("hideui_toolbox_row_host"):
            if not toolbox.property("hideui_toolbox_row_original"):
                toolbox.setProperty("hideui_toolbox_row_original", toolbox.widget())
            host = QWidget()
            host.setObjectName("hideuiToolboxRowHost")
            lay = QHBoxLayout(host)
            lay.setContentsMargins(4, 4, 4, 4)
            lay.setSpacing(4)
            lay.addStretch(1)
            for btn in buttons:
                btn.setParent(host)
                btn.setFixedSize(btn_size, btn_size)
                btn.show()
                btn.setEnabled(True)
                lay.addWidget(btn, 0, Qt.AlignCenter)
            lay.addStretch(1)
            toolbox.setWidget(host)
            toolbox.setProperty("hideui_toolbox_row_host", True)
            toolbox.setProperty("hideui_single_col_host", False)
            _log("toolbox: horizontal row host (%d tools)" % count)
        else:
            host = toolbox.widget()
            lay = host.layout() if host is not None else None
            if lay is not None:
                while lay.count():
                    item = lay.takeAt(0)
                    w = item.widget()
                    if w is not None:
                        w.setParent(host)
                lay.addStretch(1)
                for btn in buttons:
                    btn.setFixedSize(btn_size, btn_size)
                    btn.show()
                    btn.setEnabled(True)
                    lay.addWidget(btn, 0, Qt.AlignCenter)
                lay.addStretch(1)

        self._apply_dock_title(toolbox)
        self._clear_dock_constraints(toolbox)
        toolbox.setMinimumHeight(strip_h)
        toolbox.setMaximumHeight(strip_h + 12)
        toolbox.setMinimumWidth(strip_w)
        toolbox.setMaximumWidth(16777215)
        toolbox.show()
        return strip_w, strip_h, btn_size

    def _apply_ordered_left_toolbox(self, toolbox, qwin):
        """Left toolbox during study: one tool icon per row in fixed order."""
        if toolbox is None or not _qt_alive(toolbox):
            return None
        if self._study_uses_bottom_toolbox():
            return None
        if not bool(self.session) or self._quitting:
            return None
        self._restore_toolbox_custom_host(toolbox)
        self._unwrap_bottom_toolbox(toolbox)
        buttons = self._ordered_study_toolbox_buttons(toolbox)
        if not buttons:
            return None
        btn_size = max(28, max(
            btn.iconSize().width() for btn in buttons) + 4)
        col_w = btn_size + 12
        count = len(buttons)
        col_h = count * (btn_size + 4) + 12

        if not toolbox.property("hideui_single_col_host"):
            if not toolbox.property("hideui_single_col_original"):
                toolbox.setProperty("hideui_single_col_original", toolbox.widget())
            host = QWidget()
            host.setObjectName("hideuiToolboxSingleColHost")
            lay = QVBoxLayout(host)
            lay.setContentsMargins(2, 4, 2, 4)
            lay.setSpacing(2)
            lay.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            for btn in buttons:
                btn.setParent(host)
                btn.setFixedSize(btn_size, btn_size)
                btn.show()
                btn.setEnabled(True)
                lay.addWidget(btn, 0, Qt.AlignHCenter)
            lay.addStretch(1)
            toolbox.setWidget(host)
            toolbox.setProperty("hideui_single_col_host", True)
            _log("toolbox: ordered left column (%d tools)" % count)
        else:
            host = toolbox.widget()
            lay = host.layout() if host is not None else None
            if lay is not None:
                while lay.count():
                    item = lay.takeAt(0)
                    w = item.widget()
                    if w is not None:
                        w.setParent(host)
                for btn in buttons:
                    btn.setFixedSize(btn_size, btn_size)
                    btn.show()
                    btn.setEnabled(True)
                    lay.addWidget(btn, 0, Qt.AlignHCenter)
                lay.addStretch(1)

        self._clear_dock_constraints(toolbox)
        toolbox.setMinimumWidth(col_w)
        toolbox.setMaximumWidth(col_w + 6)
        toolbox.setMinimumHeight(col_h)
        toolbox.setMaximumHeight(max(col_h + 40, 320))
        toolbox.show()
        return col_w, col_h, btn_size

    def _ensure_white_canvas_background(self, doc=None):
        """Show a white canvas instead of the default transparency checkerboard."""
        try:
            if doc is None:
                doc = Krita.instance().activeDocument()
            if doc is None:
                return
            doc.setBackgroundColor(QColor(255, 255, 255))
            doc.refreshProjection()
            doc.waitForDone()
        except Exception:
            _log(traceback.format_exc())

    def _study_uses_bottom_toolbox(self):
        if self._is_session1():
            return False
        from .layout_profiles import profile_flags
        return profile_flags(
            getattr(self, "_study_layout_profile", "A")).get("toolbox_bottom", False)

    def _ordered_study_toolbox_buttons(self, toolbox):
        by_id = {}
        eraser = None
        extras = []
        for btn in toolbox.findChildren(QToolButton):
            if not self._keep_toolbox_button(btn):
                continue
            oid = btn.objectName() or ""
            if oid:
                by_id[oid] = btn
            elif "eraser" in (btn.toolTip() or "").lower():
                eraser = btn
            else:
                extras.append(btn)
        out = []
        for oid in STUDY_TOOLBOX_ORDER:
            if oid in by_id:
                out.append(by_id[oid])
        if eraser is not None:
            out.append(eraser)
        for btn in extras:
            if btn not in out:
                out.append(btn)
        return out

    def _study_toolbox_visibility_codes(self, toolbox):
        codes = list(STUDY_TOOLBOX_ORDER)
        for btn in toolbox.findChildren(QToolButton):
            if not self._keep_toolbox_button(btn):
                continue
            oid = btn.objectName() or ""
            if oid and oid not in codes:
                codes.append(oid)
        return codes

    def _force_study_toolbox_visible(self, toolbox):
        if toolbox is None or not _qt_alive(toolbox):
            return
        _, ko_toolbox = self._find_toolbox_internals(toolbox)
        codes = self._study_toolbox_visibility_codes(toolbox)
        if ko_toolbox is not None and codes:
            try:
                ko_toolbox.setButtonsVisible(codes)
            except Exception:
                _log(traceback.format_exc())
        for btn in self._ordered_study_toolbox_buttons(toolbox):
            btn.show()
            btn.setEnabled(True)

    def _find_toolbox_internals(self, toolbox):
        scroll = None
        ko_toolbox = None
        if toolbox is None:
            return scroll, ko_toolbox
        for w in toolbox.findChildren(QWidget):
            cls = w.metaObject().className()
            if cls == "KoToolBoxScrollArea":
                scroll = w
            elif cls == "KoToolBox":
                ko_toolbox = w
        return scroll, ko_toolbox

    def _unwrap_bottom_toolbox(self, toolbox):
        if toolbox is None or not _qt_alive(toolbox):
            return
        self._restore_toolbox_custom_host(toolbox)
        if not toolbox.property("hideui_bottom_host"):
            return
        original = toolbox.property("hideui_bottom_original")
        if original is not None and _qt_alive(original):
            toolbox.setWidget(original)
        toolbox.setProperty("hideui_bottom_host", None)
        toolbox.setProperty("hideui_bottom_original", None)

    def _configure_bottom_toolbox(self, toolbox, qwin):
        """Bottom toolbox: one tool per slot in a centered horizontal row."""
        if toolbox is None or not _qt_alive(toolbox):
            return
        self._trim_toolbox(qwin)
        if bool(self.session) and not self._quitting:
            self._apply_horizontal_toolbox_row(toolbox, qwin)
            self._apply_dock_title(toolbox)
            return

        try:
            k = Krita.instance()
            k.writeSetting("KoToolBox", "compact", "false")
            k.writeSetting("KoToolBox", "orientation", "1")
        except Exception:
            pass

        scroll, ko_toolbox = self._find_toolbox_internals(toolbox)
        if ko_toolbox is not None:
            try:
                ko_toolbox.setCompact(False)
                ko_toolbox.setOrientation(Qt.Horizontal)
            except Exception:
                pass
        if scroll is not None:
            try:
                scroll.setOrientation(Qt.Horizontal)
            except Exception:
                pass

        self._force_study_toolbox_visible(toolbox)
        buttons = self._ordered_study_toolbox_buttons(toolbox)
        btn_size = 32
        if buttons:
            btn_size = max(28, max(
                btn.iconSize().width() for btn in buttons) + 4)
        count = max(len(buttons), 1)
        strip_w = count * btn_size + max(0, count - 1) * 4 + 20
        strip_h = btn_size + 12

        self._apply_dock_title(toolbox)

        if not toolbox.property("hideui_bottom_host"):
            original = scroll if scroll is not None else toolbox.widget()
            host = QWidget()
            host.setObjectName("hideuiToolboxBottomHost")
            lay = QHBoxLayout(host)
            lay.setContentsMargins(0, 4, 0, 4)
            lay.setSpacing(0)
            lay.addStretch(1)
            if original is not None and _qt_alive(original):
                original.setParent(host)
                lay.addWidget(original, 0, Qt.AlignCenter)
            lay.addStretch(1)
            toolbox.setWidget(host)
            toolbox.setProperty("hideui_bottom_host", True)
            toolbox.setProperty("hideui_bottom_original", original)
            scroll, ko_toolbox = self._find_toolbox_internals(toolbox)

        self._clear_dock_constraints(toolbox)
        toolbox.setMinimumHeight(strip_h + 8)
        toolbox.setMaximumHeight(strip_h + 20)
        toolbox.setMinimumWidth(0)
        toolbox.setMaximumWidth(16777215)
        toolbox.show()

        if scroll is not None:
            scroll.setMinimumSize(strip_w, strip_h)
            scroll.resize(strip_w, strip_h)
            scroll.updateGeometry()
        if ko_toolbox is not None:
            ko_toolbox.setMinimumSize(strip_w, strip_h)
            ko_toolbox.resize(strip_w, strip_h)
            ko_toolbox.updateGeometry()
            ko_toolbox.update()

        self._force_study_toolbox_visible(toolbox)

    def _configure_bottom_preset_docker(self, preset):
        """Layout B: horizontal preset strip in a bottom docker (not the toolbar)."""
        if preset is None or not _qt_alive(preset):
            return
        strip_h = BOTTOM_PRESET_DOCK_HEIGHT
        self._clear_dock_constraints(preset)
        preset.show()
        preset.setMinimumHeight(strip_h)
        preset.setMaximumHeight(strip_h + 8)
        preset.setMinimumWidth(0)
        preset.setMaximumWidth(16777215)
        self._minimize_preset_dock_title(preset)
        content = preset.widget()
        if content is not None and content is not self._preset_dock_placeholder:
            self._configure_preset_horizontal(content)
            self._ensure_preset_chooser_visible(content)
        for delay in (100, 400, 1200):
            QTimer.singleShot(
                delay,
                lambda p=preset: self._trim_preset_chooser_extras(p))

    def _add_bottom_dock_stack(self, qwin, preset, toolbox):
        """Stack preset bar above toolbox on the bottom edge (Layout B)."""
        bottom = []
        if preset is not None:
            qwin.addDockWidget(Qt.BottomDockWidgetArea, preset)
            bottom.append(preset)
        if toolbox is not None:
            toolbox.show()
            qwin.addDockWidget(Qt.BottomDockWidgetArea, toolbox)
            self._configure_bottom_toolbox(toolbox, qwin)
            if bottom:
                qwin.splitDockWidget(bottom[0], toolbox, Qt.Vertical)
            bottom.append(toolbox)
        if len(bottom) > 1:
            heights = [BOTTOM_PRESET_DOCK_HEIGHT, BOTTOM_TOOLBOX_DOCK_HEIGHT]
            qwin.resizeDocks(bottom, heights, Qt.Vertical)
        elif len(bottom) == 1 and bottom[0] is toolbox:
            toolbox.setMinimumHeight(BOTTOM_TOOLBOX_DOCK_HEIGHT)
            toolbox.setMaximumHeight(BOTTOM_TOOLBOX_DOCK_HEIGHT + 20)

    def _restore_layout_a_dock_positions(self, qwin, docks):
        """Layout A: Toolbox left; Color, Layers, Brushes stacked right (that order)."""
        toolbox = docks.get("ToolBox")
        preset = docks.get("PresetDocker")
        color = docks.get("ColorSelectorNg")
        layers = docks.get("KisLayerBox")
        if toolbox is not None:
            self._restore_toolbox_custom_host(toolbox)
            self._unwrap_bottom_toolbox(toolbox)
        for dock in docks.values():
            if dock is not None:
                qwin.removeDockWidget(dock)
        if toolbox is not None:
            self._add_dock_column(
                qwin, Qt.LeftDockWidgetArea, [(toolbox, 38, 320)])
        right_specs = []
        if color is not None:
            right_specs.append((color, 220, 300))
        if layers is not None:
            right_specs.append((layers, 220, 240))
        if preset is not None:
            # Height not locked: brushes take the remaining column space.
            right_specs.append((preset, 220, 160))
        if right_specs:
            self._add_dock_column(qwin, Qt.RightDockWidgetArea, right_specs)
        self._fix_preset_gap(qwin)
        self._schedule_preset_gap_fix(qwin)

    def _lock_dock_panels_layout_a(self, qwin):
        """Session 1 / Layout A — original dock positions, widths only locked."""
        if not _qt_alive(qwin):
            return
        self._unembed_presets_from_toolbar(qwin)
        try:
            try:
                qwin.setDockNestingEnabled(False)
            except (AttributeError, TypeError):
                pass
            docks = {}
            for d in qwin.findChildren(QDockWidget):
                if d.objectName() in KEEP_DOCKERS:
                    docks[d.objectName()] = d
            toolbox = docks.get("ToolBox")
            layers = docks.get("KisLayerBox")
            preset = docks.get("PresetDocker")
            color = docks.get("ColorSelectorNg")
            misplaced = False
            if toolbox is not None:
                self._restore_toolbox_custom_host(toolbox)
                self._unwrap_bottom_toolbox(toolbox)
                area = qwin.dockWidgetArea(toolbox)
                if area not in (Qt.LeftDockWidgetArea, Qt.NoDockWidgetArea):
                    misplaced = True
            if layers is not None and qwin.dockWidgetArea(layers) == Qt.LeftDockWidgetArea:
                misplaced = True
            # Layout A: brushes belong in the right column, below Layers.
            if preset is not None and qwin.dockWidgetArea(preset) != Qt.RightDockWidgetArea:
                misplaced = True
            if not misplaced and qwin.isVisible():
                stack = [d for d in (color, layers, preset)
                         if d is not None and d.isVisible()]
                ys = [d.y() for d in stack]
                if ys != sorted(ys):
                    misplaced = True  # right column out of order
            rebuilt = False
            if misplaced:
                from .layout_profiles import profile_flags as _pf
                if not self._try_restore_layout_state(qwin, "A", _pf("A")):
                    self._restore_layout_a_dock_positions(qwin, docks)
                    rebuilt = True
                docks = {
                    name: self._dock_by_name(qwin, name) for name in KEEP_DOCKERS}
            for d in docks.values():
                if d is None:
                    continue
                w = DEFAULT_DOCK_WIDTHS.get(d.objectName(), 130)
                d.setMinimumWidth(w)
                d.setMaximumWidth(w)
                d.show()
            if preset is not None:
                preset.show()
            left = [docks[n] for n in ("ToolBox",) if n in docks]
            right = [docks[n] for n in
                     ("ColorSelectorNg", "KisLayerBox", "PresetDocker")
                     if n in docks]
            if left:
                sizes = [DEFAULT_DOCK_WIDTHS.get(d.objectName(), 200) for d in left]
                qwin.resizeDocks(left, sizes, Qt.Horizontal)
            if right:
                sizes = [DEFAULT_DOCK_WIDTHS.get(d.objectName(), 262) for d in right]
                qwin.resizeDocks(right, sizes, Qt.Horizontal)
            self._lock_dock_splitters(qwin)
            self._lock_dock_panel_heights(qwin)
            self._apply_all_dock_titles(qwin)
            toolbox = docks.get("ToolBox")
            if toolbox is not None:
                self._apply_study_toolbox_order(toolbox, qwin)
                self._schedule_condition_c_toolbox_layout(qwin, toolbox)
            self._ensure_presets_for_profile(qwin, "A")
            self._fix_preset_gap(qwin)
            self._schedule_preset_gap_fix(qwin)
            if rebuilt or not self._has_layout_state(qwin, "A"):
                self._schedule_verified_capture(qwin, "A")
        except Exception:
            _log(traceback.format_exc())

    def _layout_state_key(self, qwin, profile):
        """Cache key for native state blobs: profile + toolbox variant + window size."""
        variant = "C" if self._is_condition_c_session2() else "N"
        _, size = self._compute_geometry(qwin)
        return "%s_%s" % (profile, variant), size.width(), size.height()

    def _try_restore_layout_state(self, qwin, profile, flags):
        """Apply a study layout with one native restoreState call (no dock churn).

        Returns True when a cached blob for this profile existed and applied.
        """
        try:
            # Never tear presets out of the toolbar when the live layout
            # already matches — that unembed→restore→re-embed cycle is what
            # makes brushes flash for a split second then vanish.
            ok, problems = self._verify_study_layout(qwin, profile)
            if ok and self._preset_popup_is_placed(qwin, profile):
                _log("layout %s already correct, skipping blob restore" % profile)
                return True

            from .layout_state import (
                load_state_blob, sync_state_to_kritarc, delete_state_blob)
            key, w, h = self._layout_state_key(qwin, profile)
            blob = load_state_blob(key, w, h)
            if blob is None:
                return False
            # Park presets in the docker before restoreState; toolbar embedding
            # is widget plumbing and must be re-applied after the blob lands.
            self._unembed_presets_from_toolbar(qwin)
            popup = self._find_preset_popup_widget(qwin)
            if popup is not None:
                self._preset_popup_widget = popup
            # Fixed min/max sizes would prevent restoreState from sizing docks.
            for name in KEEP_DOCKERS:
                self._clear_dock_constraints(self._dock_by_name(qwin, name))
            if not qwin.restoreState(QByteArray(bytes(blob))):
                _log("layout blob restore failed for %s, falling back" % profile)
                return False
            self._finalize_layout_after_restore(qwin, profile, flags)
            self._ensure_presets_for_profile(qwin, profile)
            # Self-heal: a blob that restores to the wrong layout is poisoned;
            # delete it and let the scripted path rebuild + recapture.
            ok, problems = self._verify_study_layout(qwin, profile)
            if not ok:
                _log("restored blob failed verification for %s: %s"
                     % (profile, "; ".join(problems)))
                delete_state_blob(key, w, h)
                return False
            # Keep kritarc in agreement so Krita's own restores keep this layout.
            sync_state_to_kritarc(blob)
            _log("layout %s applied from cached state blob (verified)" % profile)
            return True
        except Exception:
            _log(traceback.format_exc())
            return False

    def _finalize_layout_after_restore(self, qwin, profile, flags):
        """Re-apply widget-level details after a native restoreState call."""
        toolbox = self._dock_by_name(qwin, "ToolBox")
        preset = self._dock_by_name(qwin, "PresetDocker")
        if toolbox is not None:
            if flags["toolbox_bottom"]:
                self._configure_bottom_toolbox(toolbox, qwin)
            else:
                self._restore_toolbox_custom_host(toolbox)
                self._unwrap_bottom_toolbox(toolbox)
                self._apply_study_toolbox_order(toolbox, qwin)
                if profile == "A":
                    w = DEFAULT_DOCK_WIDTHS["ToolBox"]
                    toolbox.setMinimumWidth(w)
                    toolbox.setMaximumWidth(w)
        if preset is not None and not flags["presets_in_toolbar"]:
            if flags["toolbox_bottom"]:
                self._configure_bottom_preset_docker(preset)
            else:
                preset.show()
                w = DEFAULT_DOCK_WIDTHS["PresetDocker"]
                preset.setMinimumWidth(w)
                preset.setMaximumWidth(w)
                self._apply_dock_title(preset)
                content = preset.widget()
                if content is not None:
                    self._ensure_preset_chooser_visible(content)
        for name in ("ColorSelectorNg", "KisLayerBox"):
            dock = self._dock_by_name(qwin, name)
            if dock is not None and dock.isVisible():
                w = DEFAULT_DOCK_WIDTHS.get(name, 220)
                dock.setMinimumWidth(w)
                dock.setMaximumWidth(w)
        self._trim_brush_presets(qwin)
        self._lock_dock_splitters(qwin)
        self._lock_dock_panel_heights(qwin)
        self._apply_all_dock_titles(qwin)
        self._order_study_toolbar(qwin)

    def _expected_dock_areas(self, profile):
        """Dock area each of the four study dockers must occupy per profile.

        A:        ToolBox left; Color, Layers, Brushes right (top to bottom).
        A_C1:     ToolBox left; Color+Layers right; brushes in top toolbar.
        A_C1_C2:  ToolBox bottom; Color+Layers right; brushes in top toolbar.
        B:        Layers left; Color right; ToolBox bottom; brushes in toolbar.
        """
        from .layout_profiles import profile_flags
        flags = profile_flags(profile)
        toolbox_area = (Qt.BottomDockWidgetArea if flags["toolbox_bottom"]
                        else Qt.LeftDockWidgetArea)
        if flags["presets_in_toolbar"]:
            preset_area = None  # inline in BrushesAndStuff; docker hidden
        else:
            preset_area = Qt.RightDockWidgetArea  # Layout A only
        layers_area = (Qt.LeftDockWidgetArea if flags["layers_left"]
                       else Qt.RightDockWidgetArea)
        return {
            "ToolBox": toolbox_area,
            "PresetDocker": preset_area,
            "ColorSelectorNg": Qt.RightDockWidgetArea,
            "KisLayerBox": layers_area,
        }

    def _verify_study_layout(self, qwin, profile):
        """Compare the live dock layout against the profile's design.

        Dock areas are always checked. Visibility is only checked while the
        main window is shown — a hidden window reports every dock invisible,
        which previously poisoned cached blobs.
        Returns (ok, problems).
        """
        problems = []
        try:
            from .layout_profiles import profile_flags
            flags = profile_flags(profile)
            check_vis = qwin.isVisible()
            expected = self._expected_dock_areas(profile)
            for name, area in expected.items():
                dock = self._dock_by_name(qwin, name)
                if dock is None:
                    problems.append("%s: missing" % name)
                    continue
                if area is None:
                    if check_vis and dock.isVisible():
                        problems.append("%s: should be hidden (in toolbar)" % name)
                    continue
                actual = qwin.dockWidgetArea(dock)
                if actual != area:
                    problems.append("%s: area=%d expected=%d"
                                    % (name, int(actual), int(area)))
                elif check_vis and not dock.isVisible():
                    problems.append("%s: not visible" % name)
            # Right column must read top-to-bottom in the designed order
            # (Color, Layers, then Brushes in Layout A).
            if check_vis and not problems:
                order = [n for n in
                         ("ColorSelectorNg", "KisLayerBox", "PresetDocker")
                         if expected.get(n) == Qt.RightDockWidgetArea]
                stack = []
                for name in order:
                    dock = self._dock_by_name(qwin, name)
                    if dock is not None and dock.isVisible():
                        stack.append((name, dock.y()))
                for (n1, y1), (n2, y2) in zip(stack, stack[1:]):
                    if y1 >= y2:
                        problems.append("%s should sit above %s" % (n1, n2))
        except Exception:
            _log(traceback.format_exc())
            problems.append("verify raised (see log)")
        return (not problems), problems

    def _cancel_pending_layout_capture(self):
        timer = getattr(self, "_capture_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._capture_timer = None

    def _schedule_verified_capture(self, qwin, profile,
                                   attempts=10, interval_ms=300):
        """Cache a layout blob only once the live layout verifies correct.

        Replaces the old blind 1200 ms capture: polls until verification
        passes, and never captures during transitions, recall, the welcome
        page, or while the window is hidden. At most one pending capture;
        phase changes cancel it via _halt_deferred_work.
        """
        self._cancel_pending_layout_capture()
        self._capture_attempts = int(attempts)

        def tick():
            try:
                self._capture_timer = None
                if (self._quitting or not _qt_alive(qwin)
                        or getattr(self, "_study_layout_profile", "A") != profile):
                    return
                settled = not (
                    self._recall_active or self._phase_transition_busy
                    or self._is_welcome_visible(qwin) or not qwin.isVisible())
                if settled:
                    ok, problems = self._verify_study_layout(qwin, profile)
                    if ok:
                        _log("layout verified for %s, caching blob" % profile)
                        self._capture_layout_state(qwin, profile)
                        return
                    _log("layout verify failed profile=%s: %s"
                         % (profile, "; ".join(problems)))
                self._capture_attempts -= 1
                if self._capture_attempts <= 0:
                    _log("layout capture abandoned for %s (never verified)"
                         % profile)
                    return
                self._capture_timer = QTimer()
                self._capture_timer.setSingleShot(True)
                self._capture_timer.timeout.connect(tick)
                self._capture_timer.start(interval_ms)
            except Exception:
                _log(traceback.format_exc())

        self._capture_timer = QTimer()
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(tick)
        self._capture_timer.start(interval_ms)

    def _capture_layout_state(self, qwin, profile):
        """Save the settled layout as a native state blob for instant reuse."""
        try:
            if (self._quitting or not _qt_alive(qwin)
                    or self._recall_active or self._phase_transition_busy):
                return
            if getattr(self, "_study_layout_profile", "A") != profile:
                return
            # Welcome page uses a different dock arrangement; never cache it.
            if self._is_welcome_visible(qwin):
                return
            # A hidden window reports all docks invisible — saving that state
            # poisons the cache (seen in session-1 gateway captures).
            if not qwin.isVisible():
                return
            ok, problems = self._verify_study_layout(qwin, profile)
            if not ok:
                _log("capture refused for %s: %s" % (profile, "; ".join(problems)))
                return
            from .layout_state import save_state_blob, sync_state_to_kritarc
            key, w, h = self._layout_state_key(qwin, profile)
            data = bytes(qwin.saveState())
            if save_state_blob(key, w, h, data):
                sync_state_to_kritarc(data)
        except Exception:
            _log(traceback.format_exc())

    def _has_layout_state(self, qwin, profile):
        try:
            from .layout_state import load_state_blob
            key, w, h = self._layout_state_key(qwin, profile)
            return load_state_blob(key, w, h) is not None
        except Exception:
            return False

    def _apply_study_layout(self, qwin):
        """Place study dockers for Session 2 experimental layouts (not Layout A)."""
        if self._quitting or not _qt_alive(qwin):
            return
        profile = getattr(self, "_study_layout_profile", "A")
        if self._is_session1() or profile == "A":
            self._lock_dock_panels_layout_a(qwin)
            return
        try:
            from .layout_profiles import profile_flags
            flags = profile_flags(profile)
            sig = self._study_layout_signature(qwin, profile, flags)
            if sig == self._study_layout_applied_sig:
                self._lock_dock_panel_heights(qwin)
                self._lock_dock_splitters(qwin)
                self._apply_all_dock_titles(qwin)
                toolbox = self._dock_by_name(qwin, "ToolBox")
                if toolbox is not None:
                    self._apply_study_toolbox_order(toolbox, qwin)
                self._ensure_presets_for_profile(qwin, profile)
                return

            # Fast path: one atomic native restoreState from a cached blob.
            if self._try_restore_layout_state(qwin, profile, flags):
                self._ensure_presets_for_profile(qwin, profile)
                self._study_layout_applied_sig = self._study_layout_signature(
                    qwin, profile, flags)
                return

            self._invalidate_dock_cache()
            docks = {
                name: self._dock_by_name(qwin, name) for name in KEEP_DOCKERS}
            for dock in docks.values():
                if dock is not None:
                    qwin.removeDockWidget(dock)

            self._unembed_presets_from_toolbar(qwin)
            popup = self._find_preset_popup_widget(qwin)
            if popup is not None:
                self._preset_popup_widget = popup

            toolbox = docks.get("ToolBox")
            preset = docks.get("PresetDocker")
            color = docks.get("ColorSelectorNg")
            layers = docks.get("KisLayerBox")

            if flags["layers_left"]:
                self._add_single_dock(
                    qwin, Qt.LeftDockWidgetArea, layers, 220,
                    DEFAULT_DOCK_HEIGHTS["KisLayerBox"])
                self._add_single_dock(
                    qwin, Qt.RightDockWidgetArea, color, 220,
                    DEFAULT_DOCK_HEIGHTS["ColorSelectorNg"])
            elif flags["toolbox_bottom"]:
                right_specs = []
                if color is not None:
                    right_specs.append((color, 220, 300))
                if layers is not None:
                    right_specs.append((layers, 220, 240))
                if right_specs:
                    self._add_dock_column(qwin, Qt.RightDockWidgetArea, right_specs)
            else:
                left_specs = []
                if toolbox is not None:
                    left_specs.append((toolbox, 38, 320))
                if preset is not None and not flags["presets_in_toolbar"]:
                    left_specs.append((preset, 130, 220))
                if left_specs:
                    self._add_dock_column(qwin, Qt.LeftDockWidgetArea, left_specs)
                right_specs = []
                if color is not None:
                    right_specs.append((color, 220, 300))
                if layers is not None:
                    right_specs.append((layers, 220, 240))
                if right_specs:
                    self._add_dock_column(qwin, Qt.RightDockWidgetArea, right_specs)

            if flags["toolbox_bottom"]:
                bottom_preset = None
                if preset is not None and not flags["presets_in_toolbar"]:
                    self._configure_bottom_preset_docker(preset)
                    bottom_preset = preset
                elif preset is not None:
                    self._park_preset_dock_for_toolbar_embed(qwin, preset)
                self._add_bottom_dock_stack(qwin, bottom_preset, toolbox)
                if toolbox is not None:
                    for delay in (150, 600):
                        QTimer.singleShot(
                            delay,
                            lambda q=qwin, t=toolbox: (
                                self._configure_bottom_toolbox(t, q)))
                if bottom_preset is not None:
                    for delay in (150, 600):
                        QTimer.singleShot(
                            delay,
                            lambda p=bottom_preset: self._configure_bottom_preset_docker(p))

            elif preset is not None and flags["presets_in_toolbar"]:
                self._park_preset_dock_for_toolbar_embed(qwin, preset)

            self._lock_dock_splitters(qwin)
            if flags["presets_in_toolbar"]:
                self._trim_brush_presets(qwin)
            self._lock_dock_panel_heights(qwin)
            self._apply_all_dock_titles(qwin)
            if flags.get("toolbox_bottom") and toolbox is not None:
                self._schedule_condition_c_toolbox_layout(qwin, toolbox)
            self._ensure_presets_for_profile(qwin, profile)
            self._study_layout_applied_sig = self._study_layout_signature(
                qwin, profile, flags)
            # Cache the settled layout once it verifies correct.
            self._schedule_verified_capture(qwin, profile)
        except Exception:
            _log(traceback.format_exc())

    def _schedule_study_layout_refresh(self, qwin):
        if self._quitting or self._recall_active or not _qt_alive(qwin):
            return
        if self._is_session1() or getattr(self, "_study_layout_profile", "A") == "A":
            self._lock_dock_panels_layout_a(qwin)
            return
        self._apply_study_layout(qwin)
        QTimer.singleShot(250, lambda q=qwin: self._apply_study_layout(q))

    def _lock_dock_splitters(self, qwin):
        """Freeze docker splitters so participants cannot drag panel edges."""
        try:
            try:
                qwin.setDockNestingEnabled(False)
            except (AttributeError, TypeError):
                pass
            for sp in qwin.findChildren(QSplitter):
                sp.setChildrenCollapsible(False)
                sp.setHandleWidth(0)
                for i in range(1, sp.count()):
                    h = sp.handle(i)
                    if h is None:
                        continue
                    h.setEnabled(False)
                    h.hide()
                    if not h.property("hideui_handle_filter"):
                        h.installEventFilter(self)
                        h.setProperty("hideui_handle_filter", True)
                if not sp.property("hideui_sizes_locked"):
                    sp.setProperty("hideui_saved_sizes", sp.sizes())
                    sp.splitterMoved.connect(
                        lambda pos, index, s=sp: self._on_splitter_moved(s))
                    sp.setProperty("hideui_sizes_locked", True)
        except Exception:
            _log(traceback.format_exc())

    def _lock_dock_panels(self, qwin):
        """Apply the active study layout and freeze docker geometry."""
        if self._phase_transition_busy or self._recall_active:
            self._stabilize_study_layout_for_recall(qwin)
            return
        if self._is_session1() or getattr(self, "_study_layout_profile", "A") == "A":
            self._lock_dock_panels_layout_a(qwin)
        else:
            self._apply_study_layout(qwin)

    def _start_position_guard(self):
        """Snap window back if the OS allows a drag — only while Krita is visible."""
        try:
            if self._pos_guard is None:
                self._pos_guard = QTimer()
                self._pos_guard.setInterval(2000)
                self._pos_guard.timeout.connect(self._enforce_window_geometry)
            if not self._pos_guard.isActive():
                self._pos_guard.start()
        except Exception:
            _log(traceback.format_exc())

    def _enforce_window_geometry(self):
        if (self._geom_busy or self._quitting or self._phase_transition_busy
                or not self._win_locked or not self._qwin_alive()):
            return
        if not self._qwin.isVisible():
            return
        self._geom_busy = True
        try:
            layout = self._compute_layout(self._qwin)
            pos, size = layout["krita_pos"], layout["krita_size"]
            self._fixed_pos = pos
            self._fixed_size = size
            if self._qwin.isMaximized() or self._qwin.isFullScreen():
                self._qwin.showNormal()
            if self._qwin.size() != size:
                self._qwin.setFixedSize(size)
            if self._qwin.pos() != pos:
                self._qwin.move(pos)
            self._lock_dock_panel_heights(self._qwin)
            self._lock_dock_splitters(self._qwin)
            self._suppress_canvas_floating_messages(self._qwin)
            if self._study_toolbar is not None:
                self._study_toolbar.show()
            if self._recall_active:
                self._order_study_toolbar(self._qwin)
            if not self._quitting:
                if self._break_active or self._recall_active:
                    self._update_video_panel(self._qwin)
                    if self._recall_active:
                        self._position_recall_question_banner(self._qwin)
                elif self._should_show_video(self._qwin):
                    vlayout = self._compute_layout(self._qwin)
                    if (self._video_panel is not None
                            and self._video_panel.is_showing()):
                        self._video_panel.reposition(
                            vlayout["video_pos"], vlayout["video_size"])
                elif self._video_panel is not None and self._video_panel.isVisible():
                    self._video_panel.hide_panel()
                    self._video_shown_for_canvas = False
        except RuntimeError:
            self._invalidate_qwin()
        except Exception:
            _log(traceback.format_exc())
        finally:
            self._geom_busy = False

    def _safe_view_changed(self):
        if self._qwin_alive():
            self._on_view_changed(self._qwin)

    def _install_new_override(self, qwin):
        # 1) The "New" menu item / Cmd+N action.
        try:
            act = Krita.instance().action("file_new")
            if act is not None and not act.property("hideui_done"):
                try:
                    act.triggered.disconnect()
                except Exception:
                    pass
                act.triggered.connect(self._new_default)
                act.setProperty("hideui_done", True)
                _log("file_new action overridden")
        except Exception:
            _log(traceback.format_exc())
        # 2) Welcome "New File" — C++ slotNewFileClicked cannot be disconnected
        # from Python; intercept the click with an event filter instead.
        try:
            for b in qwin.findChildren(QAbstractButton):
                if b.objectName() == "newFileLink" and not b.property("hideui_filter"):
                    b.installEventFilter(self)
                    b.setProperty("hideui_filter", True)
                    _log("newFileLink event filter installed")
        except Exception:
            _log(traceback.format_exc())

    def _set_skip_learning_visible(self, visible):
        try:
            if self._skip_learn_btn is not None:
                self._skip_learn_btn.setVisible(bool(visible))
                if visible and not self._break_active:
                    self._skip_learn_btn.setToolTip(
                        "Experimenter: skip this learning phase (password required)")
        except Exception:
            _log(traceback.format_exc())

    def _set_skip_break_visible(self, visible, learn_num=0):
        try:
            self._current_break_learn_num = int(learn_num) if visible else 0
            if self._skip_learn_btn is not None:
                self._skip_learn_btn.setVisible(bool(visible))
                if visible:
                    self._skip_learn_btn.setToolTip("Skip this break")
        except Exception:
            _log(traceback.format_exc())

    def _set_skip_recall_visible(self, visible, learn_num=0):
        try:
            self._current_recall_learn_num = int(learn_num) if visible else 0
            if self._skip_learn_btn is not None:
                show = bool(visible and learn_num > 0)
                self._skip_learn_btn.setVisible(show)
                if show:
                    self._skip_learn_btn.setToolTip(
                        "Experimenter: skip this recall phase (password required)")
            if not visible:
                self._set_next_recall_visible(False)
        except Exception:
            _log(traceback.format_exc())

    def _set_next_recall_visible(self, visible, is_last=False, label=None):
        try:
            if self._next_recall_btn is None:
                return
            show = bool(visible)
            if show:
                if label:
                    self._next_recall_btn.setText(label)
                else:
                    self._next_recall_btn.setText(
                        "Continue" if is_last else "Next question")
            self._next_recall_btn.setVisible(show)
            if show:
                self._next_recall_btn.raise_()
        except Exception:
            _log(traceback.format_exc())

    def _prompt_begin_first_recall_question(self, qwin):
        """Legacy entry; recall now auto-starts under a full-screen cover."""
        self._begin_recall_auto_start(qwin)

    def _on_recall_start_from_panel(self):
        """Kept for compatibility; Start footer is no longer shown."""
        if self._quitting or not self._recall_active:
            return
        qwin = self._qwin
        if not _qt_alive(qwin):
            return
        if getattr(self, "_recall_auto_starting", False):
            return
        _log("recall Start clicked (legacy) -> auto-start")
        self._begin_recall_auto_start(qwin)

    def _reveal_krita_for_active_recall(self, qwin, under_cover=False):
        """Show Krita for recall; under_cover keeps it behind the loading curtain."""
        if not _qt_alive(qwin):
            return
        self._recall_krita_hidden_until_start = False
        try:
            if under_cover:
                qwin.show()
                QApplication.processEvents()
            else:
                self._present_krita(qwin)
            self._ensure_study_chrome(qwin)
            self._show_study_toolbars(qwin)
            self._schedule_study_toolbar_order(qwin)
            learn_num = getattr(self, "_pending_recall_learn_num", 0)
            self._set_skip_recall_visible(True, learn_num)
            self._hide_document_chrome(qwin)
            self._lock_window(qwin, show=True)
            self._enforce_window_geometry()
            QApplication.processEvents()
            self._build_recall_overlays(qwin, prepare=True)
            if under_cover:
                self._cover_recall_prep(
                    "Placing command covers…", percent=70)
            else:
                self._focus_canvas(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _cover_recall_prep(self, message="Preparing recall…", percent=50):
        """Full-screen opaque curtain; Krita may exist underneath for layout."""
        self._arm_loading_screen(
            message,
            percent=percent,
            hide_krita=False,
            raise_only=True,
            title="Preparing recall")

    def _prompt_next_recall_question(self, qwin):
        """Pause after an answer/timeout until the participant clicks Next."""
        if self._quitting or not self._recall_active:
            return
        self._recall_waiting_for_next = True
        if self._recall_timer is not None:
            self._recall_timer.stop()
        self._set_recall_timer_visible(False)
        is_last = self._recall_index >= len(self._recall_questions) - 1
        self._set_next_recall_visible(True, is_last=is_last)
        banner = self._ensure_recall_question_banner(qwin)
        if banner is not None:
            if is_last:
                banner.set_question(
                    "Answer recorded. Click Continue when you are ready.")
            else:
                banner.set_question(
                    "Answer recorded. Click Next question when you are ready.")
            banner.show()
            self._position_recall_question_banner(qwin)
        _log("recall waiting for Next question (index=%d last=%s)"
             % (self._recall_index, is_last))

    def _on_next_recall_click(self):
        if self._quitting or not self._recall_active:
            return
        if not self._recall_waiting_for_next:
            return
        self._recall_waiting_for_next = False
        self._set_next_recall_visible(False)
        qwin = self._qwin
        if not _qt_alive(qwin):
            return
        if self._recall_awaiting_first_question:
            self._recall_awaiting_first_question = False
            _log("recall Next/Start -> auto-start")
            self._begin_recall_auto_start(qwin)
            return
        _log("recall Next question clicked -> advancing")
        self._advance_recall_question(qwin)

    def _learning_skip_password(self, learn_num):
        from .session_flow import learning_skip_password
        if not self.session or not learn_num:
            return ""
        return learning_skip_password(
            self.session.get("condition", "A"),
            self.session.get("session", 1),
            learn_num)

    def _recall_skip_password(self, learn_num):
        from .session_flow import recall_skip_password
        if not self.session or not learn_num:
            return ""
        return recall_skip_password(
            self.session.get("condition", "A"),
            self.session.get("session", 1),
            learn_num)

    def _on_skip_learning_click(self):
        if self._quitting:
            return
        self._recall_input_blocked = True
        try:
            if self._recall_active and self._current_recall_learn_num:
                learn_num = self._current_recall_learn_num
                expected = self._recall_skip_password(learn_num)
                if not expected:
                    _log("recall skip rejected: no password configured")
                    return
                dlg = _SkipLearningDialog(
                    self._qwin if self._qwin_alive() else None)
                if not dlg.run(
                        expected,
                        title="Enter the skip password for this recall phase.",
                        window_title="Skip recall"):
                    return
                _log("recall phase skipped: %s" % expected)
                from .experiment_log import log_t
                log_t("skip", phase="recall",
                      learn_num=int(self._current_recall_learn_num or 0))
                if self._qwin_alive():
                    self._skip_recall_phase(self._qwin)
                return
            if not self._learning_done_cb:
                return
            learn_num = self._current_learning_num
            dlg_title = "Enter the skip password for this learning phase."
            win_title = "Skip learning phase"
            phase = "learning"
            expected = self._learning_skip_password(learn_num)
            if not expected:
                _log("%s skip rejected: no password configured" % phase)
                return
            dlg = _SkipLearningDialog(self._qwin if self._qwin_alive() else None)
            if not dlg.run(expected, title=dlg_title, window_title=win_title):
                return
            _log("%s phase skipped: %s" % (phase, expected))
            self._finish_learning_phase("experimenter_skip")
        finally:
            if QApplication.activeModalWidget() is None:
                self._recall_input_blocked = False

    def _skip_recall_phase(self, qwin):
        """Experimenter skip — end recall immediately."""
        if self._quitting or not self._recall_active:
            return
        self._recall_question_answered = True
        self._recall_waiting_for_next = False
        if self._recall_timer is not None:
            self._recall_timer.stop()
        self._set_next_recall_visible(False)
        self._set_skip_recall_visible(False)
        self._set_recall_timer_visible(False)
        self._recall_end_reason = "experimenter_skip"
        self._finish_recall_phase(qwin)

    def _set_tutorial_timer_visible(self, visible, seconds=0):
        try:
            if self._timer_label is not None:
                if visible:
                    self._update_timer_display(seconds)
                    self._timer_label.show()
                else:
                    self._timer_label.hide()
                    self._timer_label.setStyleSheet(TIMER_STYLE_NORMAL)
            self._stop_timer_blink()
        except Exception:
            _log(traceback.format_exc())

    def _stop_timer_blink(self):
        self._timer_urgent_active = False
        self._timer_blink_on = True
        try:
            if self._timer_blink_timer is not None:
                self._timer_blink_timer.stop()
        except Exception:
            pass

    def _start_timer_blink(self):
        self._timer_urgent_active = True
        if self._timer_blink_timer is None:
            self._timer_blink_timer = QTimer()
            self._timer_blink_timer.timeout.connect(self._on_timer_blink)
        self._timer_blink_timer.setInterval(TIMER_BLINK_MS)
        if not self._timer_blink_timer.isActive():
            self._timer_blink_timer.start()

    def _on_timer_blink(self):
        try:
            if not self._timer_urgent_active or self._timer_label is None:
                return
            self._timer_blink_on = not self._timer_blink_on
            self._timer_label.setStyleSheet(
                TIMER_STYLE_URGENT if self._timer_blink_on
                else TIMER_STYLE_URGENT_TEXT_HIDDEN)
        except Exception:
            _log(traceback.format_exc())

    def _play_timer_beep(self):
        """Short bip when the countdown enters the final seconds."""
        try:
            if sys.platform == "darwin":
                for path in (
                    "/System/Library/Sounds/Tink.aiff",
                    "/System/Library/Sounds/Ping.aiff",
                    "/System/Library/Sounds/Pop.aiff",
                ):
                    if os.path.isfile(path):
                        subprocess.Popen(
                            ["afplay", "-v", "0.75", path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
                        return
            elif sys.platform == "win32":
                import winsound
                winsound.Beep(880, 130)
                return
            QApplication.beep()
        except Exception:
            try:
                QApplication.beep()
            except Exception:
                pass

    def _format_time_left(self, seconds):
        sec = max(0, int(seconds))
        m, s = divmod(sec, 60)
        return "Time left: %d:%02d" % (m, s)

    def _update_timer_display(self, seconds_left):
        try:
            if self._timer_label is None:
                return
            self._timer_label.setText(self._format_time_left(seconds_left))
            sec = max(0, int(seconds_left))
            urgent_enabled = getattr(self, "_timer_urgent_enabled", True)
            urgent = urgent_enabled and sec <= TIMER_URGENT_SEC and sec > 0
            if urgent:
                if not self._timer_urgent_active:
                    self._timer_blink_on = True
                    self._timer_label.setStyleSheet(TIMER_STYLE_URGENT)
                self._start_timer_blink()
                self._play_timer_beep()
            else:
                self._stop_timer_blink()
                self._timer_label.setStyleSheet(TIMER_STYLE_NORMAL)
        except Exception:
            _log(traceback.format_exc())

    def _learning_phase_index(self, learn_num):
        from .learning_instructions import _phase_index
        session_num = 1
        if self.session:
            session_num = int(self.session.get("session", 1) or 1)
        return _phase_index(session_num, int(learn_num or 1))

    def _start_learning_event_tracking(self, qwin, learn_num):
        if self._quitting or not self.session:
            return
        try:
            from .learning_instructions import get_learning_instructions
            from .learning_tracker import LearningTracker
            from .experiment_log import log_learning_step
            inst = get_learning_instructions(self.session, learn_num)
            if self._learning_tracker is None:
                self._learning_tracker = LearningTracker(log_learning_step)
            self._learning_tracker.start(
                learn_num, inst.get("phase", 1), inst.get("steps", []))
            self._ensure_learning_click_hooks(qwin)
            self._ensure_text_app_filter()
            self._start_learning_pointer_poll()
        except Exception:
            _log(traceback.format_exc())

    def _save_learning_drawing(self, learn_num):
        """Save PNG to run_folder/learning_drawings/tutorial_N/drawing.png"""
        try:
            import os
            from krita import Krita
            from .experiment_log import learning_drawing_path

            path = learning_drawing_path(int(learn_num or 0))
            if not path:
                _log("learning export: no run folder")
                return
            os.makedirs(os.path.dirname(path), exist_ok=True)

            if self._qwin_alive():
                self._focus_canvas(self._qwin)
            QApplication.processEvents()

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
                _log("learning export: no document open")
                return

            doc.waitForDone()
            doc.refreshProjection()
            doc.waitForDone()
            QApplication.processEvents()

            image = doc.projection()
            if image is None or image.isNull():
                try:
                    bounds = doc.bounds()
                    tw = max(1, min(int(bounds.width()), 2400))
                    th = max(1, min(int(bounds.height()), 2400))
                    image = doc.thumbnail(tw, th)
                except Exception:
                    image = doc.thumbnail(1200, 1200)

            if image is None or image.isNull():
                _log("learning export: could not read canvas image")
                return

            if not image.save(path, "PNG"):
                _log("learning export: QImage.save failed for %s" % path)
                return

            if os.path.isfile(path) and os.path.getsize(path) > 0:
                _log("learning export saved: %s" % path)
            else:
                _log("learning export: file missing after save %s" % path)
        except Exception:
            _log(traceback.format_exc())

    def _stop_learning_event_tracking(self, learn_num=0):
        try:
            self._stop_learning_pointer_poll()
            if self._learning_tracker is not None:
                self._learning_tracker.stop()
        except Exception:
            _log(traceback.format_exc())

    def _start_learning_pointer_poll(self):
        self._stop_learning_pointer_poll()
        self._learning_pointer_timer = QTimer()
        self._learning_pointer_timer.timeout.connect(self._poll_learning_pointer)
        self._learning_pointer_timer.start(10)

    def _stop_learning_pointer_poll(self):
        if self._learning_pointer_timer is not None:
            self._learning_pointer_timer.stop()
            self._learning_pointer_timer = None

    def _poll_learning_pointer(self):
        if not self._learning_click_active():
            return
        tracker = self._learning_tracker
        if tracker is None:
            return
        try:
            gp = QCursor.pos()
            x = gp.x()
            y = gp.y()
            if self._qwin_alive():
                local = self._qwin.mapFromGlobal(gp)
                x = local.x()
                y = local.y()
            tracker.on_pointer_event("move", x, y, "")
        except Exception:
            pass

    def _qt_mouse_button_name(self, button):
        if button == Qt.LeftButton:
            return "left"
        if button == Qt.RightButton:
            return "right"
        if button == Qt.MiddleButton:
            return "middle"
        try:
            return str(int(button))
        except Exception:
            return ""

    def _describe_learning_click_target(self, obj):
        """Human-readable target under a learning-phase mouse click."""
        if not isinstance(obj, QWidget):
            return ""
        try:
            from .learning_tracker import toolbox_command_name
            w = obj
            while w is not None:
                name = w.objectName() or ""
                cls = w.metaObject().className() if w.metaObject() else ""

                if name in ("bnDelete", "bnRaise", "bnLower"):
                    labels = {
                        "bnDelete": "Delete layer",
                        "bnRaise": "Move up",
                        "bnLower": "Move down",
                    }
                    return labels.get(name, name)

                tool = toolbox_command_name(name)
                if tool:
                    return tool

                if isinstance(w, QToolButton):
                    tip = (w.toolTip() or w.text() or "").strip()
                    if tip:
                        return tip.split("\n")[0].strip()

                if self._widget_in_docker(w, "ColorSelectorNg"):
                    return "color wheel"
                if self._widget_in_docker(w, "PresetDocker"):
                    return "Brush Presets"
                if (self._preset_popup_widget is not None
                        and _qt_alive(self._preset_popup_widget)):
                    p = w
                    while p is not None:
                        if p is self._preset_popup_widget:
                            return "Brush Presets"
                        p = _widget_parent(p)
                if self._widget_in_docker(w, "KisLayerBox"):
                    if name == "bnAdd":
                        return "Add layer"
                    return "Layers"
                if self._widget_in_docker(w, "ToolBox"):
                    return "ToolBox"
                if "Canvas" in cls or w is self._canvas_w:
                    return "canvas"
                if isinstance(w, QDockWidget) and name:
                    return name
                w = _widget_parent(w)

            name = obj.objectName() or ""
            cls = obj.metaObject().className() if obj.metaObject() else ""
            return name or cls or "widget"
        except Exception:
            return ""

    def _log_learning_pointer_click(self, event_type, event, obj=None):
        if not self._learning_click_active():
            return
        tracker = self._learning_tracker
        if tracker is None:
            return
        try:
            gp = event.globalPos()
            x = gp.x()
            y = gp.y()
            if self._qwin_alive():
                local = self._qwin.mapFromGlobal(gp)
                x = local.x()
                y = local.y()
            target = self._describe_learning_click_target(obj) if obj else ""
            tracker.on_pointer_event(
                event_type, x, y, target)
        except Exception:
            pass

    def _refresh_learning_step_panel(self, qwin=None):
        if not self._learning_steps:
            return
        qwin = qwin or self._qwin
        if not self._qwin_alive() or not _qt_alive(qwin):
            return
        self._ensure_learning_click_hooks(qwin)
        try:
            from .video_panel import get_video_panel
            panel = get_video_panel()
            if panel is None:
                return
            self._video_panel = panel
            layout = self._compute_layout(qwin)
            idx = int(self._learning_step_index or 0)
            idx = max(0, min(idx, len(self._learning_steps) - 1))
            panel.show_learning_step_panel(
                layout["video_pos"], layout["video_size"],
                self._learning_panel_title,
                self._learning_steps[idx],
                idx + 1,
                len(self._learning_steps),
                phase=self._learning_panel_phase,
                on_next=self._on_learning_step_next,
                on_back=self._on_learning_step_back)
        except Exception:
            _log(traceback.format_exc())

    def _on_learning_step_next(self):
        if self._learning_phase_finished or not self._learning_steps:
            return
        learn_num = int(self._current_learning_num or 0)
        is_last = self._learning_step_index >= len(self._learning_steps) - 1
        tracker = self._learning_tracker
        if tracker is not None and tracker.active:
            tracker.on_step_next()
        if is_last:
            self._finish_learning_phase("complete")
            return
        self._learning_step_index += 1
        if self._qwin_alive():
            self._refresh_learning_step_panel(self._qwin)

    def _on_learning_step_back(self):
        if self._learning_phase_finished or not self._learning_steps:
            return
        if self._learning_step_index <= 0:
            return
        tracker = self._learning_tracker
        if tracker is not None and tracker.active:
            tracker.on_step_back()
        self._learning_step_index -= 1
        if self._qwin_alive():
            self._refresh_learning_step_panel(self._qwin)

    def _finish_learning_phase(self, reason="complete"):
        if self._learning_phase_finished:
            return
        self._learning_phase_finished = True
        learn_num = int(self._current_learning_num or 0)
        self._set_skip_learning_visible(False)
        self._set_tutorial_timer_visible(False)
        if self._tutorial_timer is not None:
            self._tutorial_timer.stop()
            self._tutorial_timer = None
        self._tutorial_remaining_sec = None
        self._stop_timer_blink()
        self._save_learning_drawing(learn_num)
        self._stop_learning_event_tracking(learn_num)
        from .experiment_log import log_e
        log_e(
            "learning",
            action="end",
            phase=self._learning_phase_index(learn_num),
            learn_num=learn_num,
            reason=reason)
        self._learning_steps = None
        cb = self._learning_done_cb
        self._learning_done_cb = None
        if self._qwin_alive():
            self._soft_pause_tutorial(self._qwin)
        if cb is not None:
            cb()

    def _ensure_learning_recall_ui_cleared(self, qwin):
        """Drop recall masks/overlays so learning blocks stay fully usable."""
        if self._recall_active or not _qt_alive(qwin):
            return
        try:
            self._recall_overlay_generation += 1
            self._recall_awaiting_first_question = False
            self._clear_recall_overlays(qwin)
            if self._recall_mask_state:
                self._unmask_recall_commands(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _start_step_by_step_learning(self, on_done, learn_num=0, time_sec=None):
        """Learning with step-by-step instructions; session 1 also runs a phase timer."""
        if self._quitting:
            return
        if self._qwin_alive():
            self._ensure_learning_recall_ui_cleared(self._qwin)
        self._learning_done_cb = on_done
        self._learning_phase_finished = False
        self._current_learning_num = int(learn_num or 0)
        self._set_skip_recall_visible(False)
        self._set_skip_learning_visible(True)
        phase_seconds = int(time_sec) if time_sec else 0
        self._set_tutorial_timer_visible(
            bool(phase_seconds), phase_seconds if phase_seconds else 0)
        from .learning_instructions import get_learning_instructions
        from .experiment_log import log_e
        inst = get_learning_instructions(self.session, learn_num)
        self._learning_steps = list(inst.get("steps", []))
        self._learning_step_index = 0
        self._learning_panel_title = inst.get("title", "")
        self._learning_panel_phase = int(inst.get("phase", 1) or 1)
        log_fields = dict(
            action="start",
            phase=self._learning_phase_index(learn_num),
            learn_num=int(learn_num or 0),
            layout=str(getattr(self, "_study_layout_profile", "")),
            practice=bool(self._is_session1() and int(learn_num or 0) == 1))
        if phase_seconds:
            log_fields["duration_sec"] = phase_seconds
        log_e("learning", **log_fields)
        from .experiment_log import learning_drawing_path
        learning_drawing_path(int(learn_num or 0))
        self._start_learning_event_tracking(self._qwin, learn_num)
        if self._qwin_alive():
            self._refresh_learning_step_panel(self._qwin)
        if phase_seconds:
            self._start_learning_phase_timer(phase_seconds)

    def _start_learning_phase_timer(self, seconds):
        """Countdown for session 1 learning blocks (step-by-step UI stays active)."""
        if self._quitting or seconds <= 0:
            return
        self._timer_urgent_enabled = True
        self._tutorial_phase_sec = int(seconds)
        self._tutorial_remaining_sec = max(0, int(seconds))
        if self._tutorial_timer is not None:
            self._tutorial_timer.stop()
        self._tutorial_timer = QTimer()
        remaining = [self._tutorial_remaining_sec]

        def tick():
            remaining[0] -= 1
            self._tutorial_remaining_sec = max(0, remaining[0])
            self._update_timer_display(self._tutorial_remaining_sec)
            if remaining[0] <= 0:
                self._tutorial_timer.stop()
                if not self._learning_phase_finished:
                    self._finish_learning_phase("timer")

        self._tutorial_timer.timeout.connect(tick)
        self._update_timer_display(remaining[0])
        self._tutorial_timer.start(1000)

    def _learning_click_active(self):
        return (self._tutorial_active and not self._recall_active
                and self._learning_tracker is not None
                and self._learning_tracker.active)

    def _ensure_learning_click_hooks(self, qwin):
        if not _qt_alive(qwin):
            return
        self._ensure_text_app_filter()
        self._hook_learning_preset_clicks(qwin)
        self._hook_learning_toolbox_clicks(qwin)

    def _hook_learning_preset_clicks(self, qwin):
        roots = []
        dock = self._dock_by_name(qwin, "PresetDocker")
        if dock is not None:
            roots.append(dock)
        if self._preset_popup_widget is not None:
            roots.append(self._preset_popup_widget)
        for root in roots:
            for view in root.findChildren(QAbstractItemView):
                if view.property("hideui_learning_preset_click"):
                    continue
                try:
                    view.clicked.connect(
                        lambda idx, v=view: self._on_learning_preset_clicked(
                            v, idx))
                except Exception:
                    pass
                view.setProperty("hideui_learning_preset_click", True)

    def _on_learning_preset_clicked(self, view, index):
        if not self._learning_click_active():
            return
        try:
            model = view.model()
            if model is None or not index.isValid():
                return
            name = model.data(index)
            if name is None:
                name = model.data(index, Qt.DisplayRole)
            if name:
                self._learning_tracker.on_preset_clicked(str(name))
        except Exception:
            _log(traceback.format_exc())

    def _hook_learning_toolbox_clicks(self, qwin):
        dock = self._dock_by_name(qwin, "ToolBox")
        if dock is None:
            return
        for btn in dock.findChildren(QToolButton):
            if not self._keep_toolbox_button(btn):
                continue
            if btn.property("hideui_learning_tool_click"):
                continue
            try:
                btn.clicked.connect(
                    lambda checked=False, b=btn: self._log_learning_tool_clicked(
                        b))
            except Exception:
                pass
            btn.setProperty("hideui_learning_tool_click", True)

    def _log_learning_tool_clicked(self, btn):
        if not self._learning_click_active():
            return
        if not isinstance(btn, QToolButton):
            return
        from .learning_tracker import toolbox_command_name
        cmd = toolbox_command_name(btn.objectName())
        if cmd:
            self._learning_tracker.on_tool_selected(cmd)

    def _log_learning_color_clicked(self):
        if not self._learning_click_active():
            return
        self._learning_tracker.on_color_wheel_clicked()

    def _log_learning_layer_button(self, button_name):
        if not self._learning_click_active():
            return
        mapping = {
            "bnDelete": ("layer_deleted", "Delete layer"),
            "bnRaise": ("layer_moved_up", "Move up"),
            "bnLower": ("layer_moved_down", "Move down"),
        }
        pair = mapping.get(button_name)
        if pair:
            self._learning_tracker.on_layer_event(pair[0], pair[1])

    def _wait_for_tutorial_timer(self, seconds, on_done, skippable=False,
                                learn_num=0, urgent=True, break_learn_num=0):
        """Non-blocking countdown — Krita stays interactive while the timer runs."""
        if self._quitting:
            return
        self._timer_urgent_enabled = bool(urgent)
        self._tutorial_phase_sec = int(seconds)
        self._tutorial_remaining_sec = max(0, int(seconds))
        self._tutorial_timer_done_cb = on_done
        self._current_learning_num = learn_num if skippable else 0
        if break_learn_num:
            self._set_skip_learning_visible(False)
            self._set_skip_recall_visible(False)
            self._set_skip_break_visible(True, break_learn_num)
        else:
            self._set_skip_break_visible(False)
            self._set_skip_recall_visible(False)
            self._set_skip_learning_visible(skippable)
        self._set_tutorial_timer_visible(True, self._tutorial_remaining_sec)
        remaining = [self._tutorial_remaining_sec]

        if self._tutorial_timer is not None:
            self._tutorial_timer.stop()

        self._tutorial_timer = QTimer()

        def tick():
            remaining[0] -= 1
            self._tutorial_remaining_sec = max(0, remaining[0])
            self._update_timer_display(self._tutorial_remaining_sec)
            if remaining[0] <= 0:
                self._tutorial_timer.stop()
                self._tutorial_remaining_sec = None
                self._set_tutorial_timer_visible(False)
                self._set_skip_learning_visible(False)
                self._set_skip_break_visible(False)
                self._set_skip_recall_visible(False)
                cb = self._tutorial_timer_done_cb
                self._tutorial_timer_done_cb = None
                if cb is not None:
                    cb()

        self._tutorial_timer.timeout.connect(tick)
        self._update_timer_display(remaining[0])
        self._tutorial_timer.start(1000)

    def _layout_for_tutorial(self, qwin):
        try:
            pos, size = self._compute_geometry(qwin)
            self._fixed_pos = pos
            self._fixed_size = size
            qwin.setFixedSize(size)
            qwin.move(pos)
            self._enforce_window_geometry()
        except Exception:
            _log(traceback.format_exc())

    def _soft_detach_presets_for_document_churn(self, qwin):
        """Detach presets from the toolbar without reparenting into PresetDocker.

        Moving the preset popup back into its dock while a document is open
        segfaults Krita on macOS; keep the widget detached until after churn.
        """
        if not self._presets_in_toolbar:
            return
        tb = self._find_brushes_toolbar(qwin)
        action = self._preset_toolbar_action
        popup = self._preset_popup_widget
        if tb is not None and action is not None:
            tb.removeAction(action)
        if popup is not None and _qt_alive(popup):
            popup.hide()
            popup.setParent(qwin)
        self._presets_in_toolbar = False
        self._preset_toolbar_action = None
        _log("brush presets soft-detached for document churn")

    def _unembed_presets_for_document_churn(self, qwin):
        """Only detach presets — do not reposition docks (that crashes with doc churn)."""
        if not self._presets_in_toolbar:
            return
        self._soft_detach_presets_for_document_churn(qwin)

    def _can_reset_document_for_churn(self, label, layout_after):
        """Prefer in-place reset whenever an image is already open.

        createDocument while Session 2 experimental layouts are active segfaults
        Krita on macOS; clearing layers is enough for a fresh blank canvas.
        """
        del label, layout_after
        try:
            return bool(Krita.instance().documents())
        except Exception:
            return False

    def _reset_active_document_blank(self, qwin):
        """Replace canvas content without createDocument (avoids macOS segfaults)."""
        try:
            k = Krita.instance()
            docs = list(k.documents())
            if not docs:
                return False
            doc = k.activeDocument() or docs[-1]
            root = doc.rootNode()
            if root is None:
                return False
            doc.setModified(False)
            for node in list(root.childNodes()):
                node.remove()
            layer = doc.createNode("Paint Layer", "paintlayer")
            if layer is None:
                _log("document reset: createNode failed")
                return False
            root.addChildNode(layer, None)
            doc.setActiveNode(layer)
            doc.refreshProjection()
            doc.waitForDone()
            self._ensure_white_canvas_background(doc)
            self._canvas_w = None
            self._session1_doc_ready = False
            if not self._switch_to_canvas(qwin):
                return False
            _log("document reset: blank paint layer ready")
            return True
        except Exception:
            _log(traceback.format_exc())
            return False

    def _neutralize_for_document_churn(self, qwin):
        """Return visible dock state to Layout A before createDocument."""
        if not _qt_alive(qwin):
            return
        from .layout_profiles import profile_flags
        profile = getattr(self, "_study_layout_profile", "A")
        if self._is_session1() or profile == "A":
            if self._presets_in_toolbar:
                self._soft_detach_presets_for_document_churn(qwin)
            preset = self._dock_by_name(qwin, "PresetDocker")
            if preset is not None:
                preset.show()
            return
        flags = profile_flags(profile)
        if self._presets_in_toolbar:
            self._soft_detach_presets_for_document_churn(qwin)
        preset = self._dock_by_name(qwin, "PresetDocker")
        if preset is not None:
            preset.show()
        if flags.get("toolbox_bottom") or flags.get("layers_left"):
            docks = {
                name: self._dock_by_name(qwin, name) for name in KEEP_DOCKERS}
            toolbox = docks.get("ToolBox")
            if toolbox is not None:
                self._unwrap_bottom_toolbox(toolbox)
            self._restore_layout_a_dock_positions(qwin, docks)
        self._study_layout_applied_sig = None
        _log("layout neutralized for document churn (was %s)" % profile)

    def _restore_layout_after_document_churn(self, qwin, profile):
        if not _qt_alive(qwin):
            return
        if not profile or profile == "A":
            self._study_layout_profile = "A"
            self._study_layout_applied_sig = None
            self._lock_dock_panels_layout_a(qwin)
            QApplication.processEvents()
            return
        self._study_layout_profile = profile
        self._study_layout_applied_sig = None
        if profile and profile != "A":
            self._learning_layout_profile = profile
        self._apply_study_layout(qwin)
        self._ensure_presets_for_profile(qwin, profile)
        QApplication.processEvents()

    def _prepare_study_canvas(self, qwin, on_ready, label="phase", layout_after=None):
        """New blank image for every study phase — staged to avoid Krita segfaults."""
        try:
            if self._quitting or not _qt_alive(qwin):
                if on_ready:
                    on_ready(False)
                return
            restore = layout_after
            if restore is None:
                restore = getattr(self, "_study_layout_profile", "A")
            self._phase_transition_busy = True
            _log("prepare_study_canvas: %s (layout_after=%s)" % (label, restore))
            self._arm_loading_screen("Preparing canvas…", 2)
            self._halt_deferred_work()
            # Krita re-applies kritarc's [MainWindow] State during document
            # churn. Point it at the layout we're entering, not the one we're
            # leaving, so Krita's own restores work for us instead of racing us.
            self._sync_kritarc_layout_state(restore)
            self._pause_video_for_phase_change()
            QApplication.processEvents()

            def fail():
                self._phase_transition_busy = False
                if on_ready:
                    on_ready(False)

            def succeed():
                self._phase_transition_busy = False
                _log("prepare_study_canvas: ready (%s)" % label)
                if on_ready:
                    on_ready(True)

            def step_restore():
                try:
                    if self._quitting or not _qt_alive(qwin):
                        fail()
                        return
                    self._restore_layout_after_document_churn(qwin, restore)
                    succeed()
                except Exception:
                    _log(traceback.format_exc())
                    fail()

            def step_wait_canvas(attempts=None):
                if attempts is None:
                    attempts = [0]
                if self._quitting or not _qt_alive(qwin):
                    fail()
                    return
                if self._switch_to_canvas(qwin):
                    QTimer.singleShot(CHURN_STEP_MS, step_restore)
                    return
                attempts[0] += 1
                if attempts[0] > 60:
                    _log("prepare_study_canvas: timeout (%s)" % label)
                    fail()
                else:
                    QTimer.singleShot(CANVAS_WAIT_MS, lambda: step_wait_canvas(attempts))

            def step_close_old(old_docs):
                try:
                    if self._quitting or not _qt_alive(qwin):
                        fail()
                        return
                    k = Krita.instance()
                    for doc in old_docs:
                        try:
                            if doc in k.documents():
                                doc.setModified(False)
                                doc.close()
                        except Exception:
                            _log(traceback.format_exc())
                        QApplication.processEvents()
                    self._canvas_w = None
                    self._session1_doc_ready = False
                    _log("closed old documents (%s)" % label)
                    QTimer.singleShot(CHURN_STEP_MS_SLOW, step_wait_canvas)
                except Exception:
                    _log(traceback.format_exc())
                    fail()

            def step_create():
                try:
                    if self._quitting or not _qt_alive(qwin):
                        fail()
                        return
                    old_docs = list(Krita.instance().documents())
                    self._creating_doc = False
                    self._new_default(force=True)
                    QApplication.processEvents()
                    _log("new document created (%s)" % label)
                    QTimer.singleShot(CHURN_STEP_MS_SLOW, lambda: step_close_old(old_docs))
                except Exception:
                    _log(traceback.format_exc())
                    fail()

            def step_reset_in_place():
                try:
                    if self._quitting or not _qt_alive(qwin):
                        fail()
                        return
                    if self._reset_active_document_blank(qwin):
                        _log("document reset in place (%s)" % label)
                        QTimer.singleShot(CHURN_STEP_MS, step_restore)
                    else:
                        _log("document reset failed, using createDocument (%s)" % label)
                        step_neutralize_then_create()
                except Exception:
                    _log(traceback.format_exc())
                    fail()

            def step_neutralize_then_create():
                try:
                    if self._quitting or not _qt_alive(qwin):
                        fail()
                        return
                    self._neutralize_for_document_churn(qwin)
                    QTimer.singleShot(CHURN_NEUTRALIZE_MS, step_create)
                except Exception:
                    _log(traceback.format_exc())
                    fail()

            def step_begin_churn():
                try:
                    if self._quitting or not _qt_alive(qwin):
                        fail()
                        return
                    self._canvas_w = None
                    qwin.hide()
                    QApplication.processEvents()
                    if self._can_reset_document_for_churn(label, restore):
                        _log(
                            "prepare_study_canvas: reset path (%s -> %s)"
                            % (label, restore))
                        QTimer.singleShot(CHURN_STEP_MS, step_reset_in_place)
                    else:
                        _log(
                            "prepare_study_canvas: create path (%s -> %s)"
                            % (label, restore))
                        QTimer.singleShot(CHURN_STEP_MS_SLOW, step_neutralize_then_create)
                except Exception:
                    _log(traceback.format_exc())
                    fail()

            step_begin_churn()
        except Exception:
            _log(traceback.format_exc())
            self._phase_transition_busy = False
            if on_ready:
                on_ready(False)

    def _close_all_documents(self):
        """Close every open image so the next tutorial starts on a blank canvas."""
        try:
            k = Krita.instance()
            docs = list(k.documents())
            for doc in docs:
                try:
                    doc.setModified(False)
                except Exception:
                    _log(traceback.format_exc())
            for doc in docs:
                try:
                    doc.close()
                except Exception:
                    _log(traceback.format_exc())
                QApplication.processEvents()
            self._canvas_w = None
            self._session1_doc_ready = False
            QApplication.processEvents()
            _log("closed all documents for fresh tutorial canvas")
        except Exception:
            _log(traceback.format_exc())

    def _prepare_fresh_canvas(self, qwin, on_ready):
        """Close every open image and open one blank default canvas."""
        layout = getattr(self, "_study_layout_profile", "A")
        self._prepare_study_canvas(qwin, on_ready, label="fresh", layout_after=layout)

    def _prepare_recall_canvas(self, qwin, on_ready):
        """New blank image for every recall phase."""
        layout_after = self._recall_layout_profile()
        _log("prepare_recall_canvas: layout=%s" % layout_after)
        current = getattr(self, "_study_layout_profile", "A")
        if (layout_after == current
                and self._is_canvas_ready(qwin)
                and self._can_reset_document_for_churn("recall", layout_after)):
            _log("prepare_recall_canvas: fast path (reuse canvas)")
            self._phase_transition_busy = True
            self._arm_loading_screen("Preparing canvas…", 2)
            try:
                self._halt_deferred_work()
                self._sync_kritarc_layout_state(layout_after)
                if self._reset_active_document_blank(qwin):
                    self._restore_layout_after_document_churn(qwin, layout_after)
                    self._phase_transition_busy = False
                    if on_ready:
                        on_ready(True)
                    return
            except Exception:
                _log(traceback.format_exc())
            self._phase_transition_busy = False
        self._prepare_study_canvas(
            qwin, on_ready, label="recall", layout_after=layout_after)

    def _pause_session_ui(self, qwin):
        """Hide Krita + video between tutorial blocks."""
        try:
            self._tutorial_active = False
            self._tutorial_remaining_sec = None
            self._set_skip_learning_visible(False)
            self._tutorial_timer_done_cb = None
            if self._tutorial_timer is not None:
                self._tutorial_timer.stop()
            self._video_shown_for_canvas = False
            self._pause_video_for_phase_change()
            self._stop_recall_click_capture()
            self._stop_position_guard()
            if self._video_panel is not None:
                self._video_panel.stop_tutorial()
            if _qt_alive(qwin):
                self._clear_recall_overlays(qwin)
                qwin.hide()
        except Exception:
            _log(traceback.format_exc())

    def _switch_to_canvas(self, qwin):
        """Activate an open document view without showing the welcome page."""
        try:
            if not _qt_alive(qwin):
                return False
            if self._is_canvas_ready(qwin):
                return True
            docs = list(Krita.instance().documents())
            if not docs:
                return False
            win = Krita.instance().activeWindow()
            if win is not None:
                win.addView(docs[-1])
            QApplication.processEvents()
            return self._is_canvas_ready(qwin)
        except Exception:
            _log(traceback.format_exc())
            return False

    def _begin_tutorial(self, qwin, restart=False, on_ready=None):
        try:
            self._recall_active = False
            self._ensure_learning_recall_ui_cleared(qwin)
            self._tutorial_active = True
            self._video_shown_for_canvas = False
            self._session1_doc_ready = False

            def finish_ready():
                try:
                    if not self._switch_to_canvas(qwin):
                        _log("finish_ready: canvas not ready")
                        if on_ready:
                            on_ready(False)
                        return

                    def prepare():
                        self._ensure_ui_customized(qwin)
                        if self._is_session1() and not self._ui_hooks_done:
                            self._ui_hooks_done = True
                            try:
                                notifier = Krita.instance().notifier()
                                notifier.setActive(True)
                                notifier.imageCreated.connect(
                                    lambda *a: self._schedule_apply(qwin))
                                notifier.viewCreated.connect(
                                    lambda *a: self._schedule_apply(qwin))
                            except Exception:
                                _log(traceback.format_exc())
                            try:
                                for st in qwin.findChildren(QStackedWidget):
                                    if not st.property("hideui_stack"):
                                        st.currentChanged.connect(
                                            lambda idx, q=qwin: (
                                                self._on_view_changed(q)))
                                        st.setProperty("hideui_stack", True)
                            except Exception:
                                _log(traceback.format_exc())
                        self._layout_for_tutorial(qwin)
                        self._lock_dock_panels(qwin)
                        if restart:
                            self._video_restart_pending = True
                        self._session1_doc_ready = True

                    def after_reveal(ok):
                        if not ok:
                            if on_ready:
                                on_ready(False)
                            return

                        def _step(fn, label):
                            try:
                                fn()
                            except Exception:
                                _log("%s failed:\n%s" % (
                                    label, traceback.format_exc()))

                        self._start_position_guard()
                        _step(lambda: self._present_krita(qwin), "present_krita")
                        _step(lambda: self._ensure_study_chrome(qwin), "study_chrome")
                        _step(lambda: self._show_study_toolbars(qwin), "toolbars")
                        _step(lambda: self._hide_document_chrome(qwin), "hide_chrome")
                        QTimer.singleShot(
                            400, lambda q=qwin: self._hide_document_chrome(q))

                        def _maybe_lock_docks(q=qwin):
                            if (not self._recall_active
                                    and not self._phase_transition_busy):
                                self._lock_dock_panels(q)

                        QTimer.singleShot(600, _maybe_lock_docks)
                        _step(
                            lambda: self._configure_native_brush_slider(qwin),
                            "brush_slider")
                        _step(lambda: self._ensure_default_brush(), "default_brush")
                        _step(
                            lambda: self._hook_toolbox_tool_tracking(qwin),
                            "toolbox_hooks")
                        if self._is_condition_c_session2():
                            toolbox = self._dock_by_name(qwin, "ToolBox")
                            if toolbox is not None:
                                _step(
                                    lambda t=toolbox: (
                                        self._apply_condition_c_toolbox_layout(
                                            t, qwin)),
                                    "condition_c_toolbox")
                                self._schedule_condition_c_toolbox_layout(
                                    qwin, toolbox)
                        _step(lambda: self._update_text_tool_ui(qwin), "text_tool_ui")
                        _step(lambda: self._update_video_panel(qwin), "video_panel")
                        self._schedule_ui_polish(qwin)
                        QTimer.singleShot(200, lambda: self._focus_canvas(qwin))
                        _log("finish_ready: Krita canvas shown")
                        if on_ready:
                            on_ready(True)

                    self._run_polished_reveal(qwin, prepare, on_ready=after_reveal)
                except Exception:
                    _log(traceback.format_exc())
                    if on_ready:
                        on_ready(False)

            def canvas_ready():
                return self._switch_to_canvas(qwin)

            # Canvas is prepared by _run_tutorial_block before this runs.
            qwin.hide()
            if canvas_ready():
                finish_ready()
                return

            attempts = [0]

            def tick():
                attempts[0] += 1
                if canvas_ready():
                    finish_ready()
                elif attempts[0] > 40:
                    _log("timeout waiting for canvas")
                    if on_ready:
                        on_ready(False)
                else:
                    QTimer.singleShot(50, tick)

            QTimer.singleShot(0, tick)
        except Exception:
            _log(traceback.format_exc())
            if on_ready:
                on_ready(False)

    def _begin_recall(self, qwin):
        try:
            self._halt_deferred_work()
            override = getattr(self, "_recall_layout_profile_override", None)
            if override:
                self._study_layout_profile = override
            else:
                self._study_layout_profile = self._recall_layout_profile()
            _log("begin_recall: layout profile=%s" % self._study_layout_profile)
            self._tutorial_active = False
            self._recall_active = True
            self._video_shown_for_canvas = False
            if self._tutorial_timer is not None:
                self._tutorial_timer.stop()

            def prepare():
                self._phase_transition_busy = True
                self._switch_to_canvas(qwin)
                self._layout_for_tutorial(qwin)
                self._ensure_ui_customized(qwin)

            def after_reveal(ok):
                self._phase_transition_busy = False
                if not ok:
                    return
                self._finish_recall_setup(qwin)

            self._recall_krita_hidden_until_start = True
            self._run_polished_reveal(
                qwin, prepare, on_ready=after_reveal, skip_krita_reveal=True)
            return True
        except Exception:
            _log(traceback.format_exc())
            self._phase_transition_busy = False
            return False

    def _finish_recall_setup(self, qwin):
        """Deferred recall UI setup — keeps phase transitions from doing too much at once."""
        if self._quitting or not self._recall_active or not _qt_alive(qwin):
            return
        try:
            self._stabilize_study_layout_for_recall(qwin)
            self._configure_layers_panel(qwin)
            self._trim_panel_commands(qwin)
            self._configure_native_brush_slider(qwin)
            self._ensure_study_dockers_visible(qwin)
            if self._recall_mask_state:
                self._unmask_recall_commands(qwin)
            self._clear_recall_overlays(qwin)
            self._mask_recall_commands(qwin)
            self._suppress_recall_tooltips(qwin)
            QToolTip.hideText()
            self._trim_brush_presets(qwin)
            QApplication.processEvents()
            self._build_recall_overlays(qwin, prepare=True)
            self._start_recall_click_capture()
            self._start_position_guard()
            self._recall_overlay_generation += 1
            self._set_tutorial_timer_visible(False)
            if getattr(self, "_recall_krita_hidden_until_start", False):
                from .experiment import suppress_krita_ui
                suppress_krita_ui()
                qwin.hide()
            self._update_video_panel(qwin)
            # Auto-start under cover — no Start first question click.
            self._begin_recall_auto_start(qwin)
        except Exception:
            _log(traceback.format_exc())
            try:
                self._begin_recall_auto_start(qwin)
            except Exception:
                _log(traceback.format_exc())
                self._hide_loading_screen()
                if _qt_alive(qwin) and self._recall_active:
                    self._recall_auto_start_go(qwin)

    def _begin_recall_auto_start(self, qwin):
        """Cover Krita until overlays settle, then start question 1 automatically."""
        if self._quitting or not self._recall_active or not _qt_alive(qwin):
            return
        if getattr(self, "_recall_auto_starting", False):
            _log("recall auto-start already in progress")
            return
        self._recall_auto_starting = True
        self._recall_auto_start_token = int(
            getattr(self, "_recall_auto_start_token", 0) or 0) + 1
        token = self._recall_auto_start_token
        self._recall_awaiting_first_question = False
        self._recall_waiting_for_next = False
        self._set_recall_timer_visible(False)
        self._set_next_recall_visible(False)
        self._hide_recall_question(qwin)
        if self._video_panel is not None:
            try:
                self._video_panel.hide_recall_start_footer()
            except Exception:
                pass
        self._cover_recall_prep("Preparing recall…", percent=35)
        self._update_video_panel(qwin)
        _log("recall auto-start: preparing under full-screen cover (token=%d)"
             % token)
        QTimer.singleShot(
            40, lambda q=qwin, t=token: self._recall_auto_start_settle(q, t))
        QTimer.singleShot(
            RECALL_AUTO_START_FAILSAFE_MS,
            lambda q=qwin, t=token: self._recall_auto_start_failsafe(q, t))

    def _recall_auto_start_failsafe(self, qwin, token):
        if token != getattr(self, "_recall_auto_start_token", 0):
            return
        if not getattr(self, "_recall_auto_starting", False):
            return
        _log("recall auto-start FAILSAFE — forcing question 1")
        self._recall_auto_start_go(qwin)

    def _recall_auto_start_settle(self, qwin, token=None):
        if token is None:
            token = getattr(self, "_recall_auto_start_token", 0)
        if token != getattr(self, "_recall_auto_start_token", 0):
            return
        if (not getattr(self, "_recall_auto_starting", False)
                or not self._recall_active or self._quitting
                or not _qt_alive(qwin)):
            self._hide_loading_screen()
            self._recall_auto_starting = False
            return
        try:
            self._cover_recall_prep("Preparing recall…", percent=55)
            self._reveal_krita_for_active_recall(qwin, under_cover=True)
            self._cover_recall_prep("Placing command covers…", percent=70)
            self._build_recall_overlays(qwin, prepare=True)
            self._cover_recall_prep("Placing command covers…", percent=75)
            delays = RECALL_OVERLAY_WARMUP_DELAYS_MS
            for i, delay in enumerate(delays):
                last = (i == len(delays) - 1)
                QTimer.singleShot(
                    delay,
                    lambda q=qwin, t=token, last=last, idx=i:
                        self._recall_auto_start_tick(q, t, last, idx))
        except Exception:
            _log(traceback.format_exc())
            self._recall_auto_start_go(qwin)

    def _recall_auto_start_tick(self, qwin, token, last, idx):
        if token != getattr(self, "_recall_auto_start_token", 0):
            return
        if not getattr(self, "_recall_auto_starting", False):
            return
        if self._quitting or not self._recall_active:
            self._hide_loading_screen()
            self._recall_auto_starting = False
            return
        if not _qt_alive(qwin):
            if last:
                QTimer.singleShot(
                    100 + LOADING_EXTRA_SETTLE_MS,
                    lambda q=qwin, t=token: self._recall_auto_start_go_if_token(
                        q, t))
            return
        try:
            self._build_recall_overlays(qwin, prepare=False)
            self._cover_recall_prep(
                "Preparing recall…",
                percent=min(95, 75 + idx * 8))
            if last:
                QTimer.singleShot(
                    100 + LOADING_EXTRA_SETTLE_MS,
                    lambda q=qwin, t=token: self._recall_auto_start_go_if_token(
                        q, t))
        except Exception:
            _log(traceback.format_exc())
            self._recall_auto_start_go(qwin)

    def _recall_auto_start_go_if_token(self, qwin, token):
        if token != getattr(self, "_recall_auto_start_token", 0):
            return
        self._recall_auto_start_go(qwin)

    def _recall_auto_start_go(self, qwin):
        """Drop the cover and start question 1."""
        try:
            if not getattr(self, "_recall_auto_starting", False):
                if self._loading_armed:
                    self._hide_loading_screen()
                return
            self._hide_loading_screen()
            self._recall_auto_starting = False
            self._recall_krita_hidden_until_start = False
            if self._quitting or not self._recall_active:
                return
            if not _qt_alive(qwin):
                qwin = self._qwin
            if not _qt_alive(qwin):
                _log("recall auto-start go: no alive qwin")
                return
            self._present_krita(qwin)
            self._ensure_study_chrome(qwin)
            self._lock_window(qwin, show=True)
            self._build_recall_overlays(qwin, prepare=False)
            self._focus_canvas(qwin)
            self._update_video_panel(qwin)
            _log("recall auto-start: starting question 1")
            self._start_recall_question(qwin)
        except Exception:
            _log(traceback.format_exc())
            self._hide_loading_screen()
            self._recall_auto_starting = False
            try:
                if self._recall_active and _qt_alive(qwin):
                    self._present_krita(qwin)
                    self._start_recall_question(qwin)
            except Exception:
                _log(traceback.format_exc())

    def _start_recall_click_capture(self):
        app = QApplication.instance()
        if app is not None and not self._recall_app_filter_active:
            app.installEventFilter(self)
            self._recall_app_filter_active = True

    def _stop_recall_click_capture(self):
        app = QApplication.instance()
        if app is not None and self._recall_app_filter_active:
            app.removeEventFilter(self)
            self._recall_app_filter_active = False

    def _clear_recall_overlays(self, qwin):
        if not _qt_alive(qwin):
            return
        for name in (RECALL_OVERLAY_NAME, RECALL_PRESET_BACKDROP_NAME):
            for w in qwin.findChildren(QWidget, name):
                try:
                    w.hide()
                    w.setParent(None)
                except Exception:
                    pass

    def _ensure_study_dockers_visible(self, qwin):
        """Keep size slider and color selector visible during the study."""
        if not _qt_alive(qwin):
            return
        try:
            for tb in qwin.findChildren(QToolBar):
                if tb.objectName() == "BrushesAndStuff":
                    tb.setProperty("hideui_recall_hidden", None)
                    tb.show()
            for dock in qwin.findChildren(QDockWidget):
                if dock.objectName() == "ColorSelectorNg":
                    dock.setProperty("hideui_recall_hidden", None)
                    dock.show()
        except Exception:
            _log(traceback.format_exc())

    def _refresh_preset_docker_recall(self, qwin):
        """Keep only the two study brushes visible; overlays hide them."""
        if not _qt_alive(qwin):
            return
        self._trim_brush_presets(qwin)

    def _build_recall_preset_overlays(self, root, host=None):
        """White boxes on the two brush preset rows (docker or toolbar strip)."""
        if root is None:
            return 0
        if host is None:
            host = self._recall_docker_host(root) if isinstance(
                root, QDockWidget) else root
        placed = 0
        for chooser in root.findChildren(QWidget):
            if chooser.metaObject().className() != "KisResourceItemChooser":
                continue
            for view in chooser.findChildren(QAbstractItemView):
                model = view.model()
                if model is None:
                    continue
                viewport = view.viewport()
                if viewport is None:
                    continue
                for row in self._pick_brush_preset_rows(model):
                    idx = model.index(row, 0)
                    rect = view.visualRect(idx)
                    if not rect.isValid() or rect.isEmpty():
                        row_h = 32
                        if hasattr(view, "sizeHintForRow"):
                            try:
                                hint = view.sizeHintForRow(row)
                                if hint > 0:
                                    row_h = hint
                            except Exception:
                                pass
                        list_w = max(view.width(), viewport.width(), 40)
                        rect = QRect(0, row * row_h, list_w, row_h)
                    cmd_id = self._preset_recall_cmd_id(model, row)
                    if not cmd_id:
                        continue
                    ov = _RecallOverlay(cmd_id, view, viewport)
                    ov.setGeometry(rect)
                    ov.show()
                    ov.raise_()
                    placed += 1
                if view not in self._recall_command_widgets:
                    self._recall_command_widgets.append(view)
        if placed:
            _log("recall preset overlays: %d brush target(s)" % placed)
        return placed

    def _build_recall_color_overlays(self, dock, host):
        """White box over the full color selector panel."""
        inner = dock.widget()
        target = inner
        if inner is None or not _qt_alive(inner) or inner.width() < 20:
            target = dock
            host = dock
        if target is None or not _qt_alive(target):
            return False
        if not target.isVisible():
            target.show()
        self._place_recall_overlay(
            host, target, "color:wheel",
            max(100, target.width()), max(120, target.height()))
        _log("recall color overlay placed")
        return True

    def _find_recall_size_slider(self, qwin):
        """Return (toolbar, KisWidgetChooser frame) for the brush size slider."""
        if not _qt_alive(qwin):
            return None, None
        for tb in qwin.findChildren(QToolBar):
            if tb.objectName() != "BrushesAndStuff" or not tb.isVisible():
                continue
            for frame in tb.findChildren(QFrame):
                if frame.metaObject().className() != "KisWidgetChooser":
                    continue
                return tb, frame
        return None, None

    def _recall_size_slider_rect(self, tb, frame):
        """Stable toolbar-local rect — capture while the slider still has natural size."""
        if not self._recall_active:
            return QRect()
        saved = frame.property("hideui_recall_size_rect")
        if isinstance(saved, QRect) and saved.width() >= 20:
            return saved
        frame.show()
        rect = frame.geometry()
        if rect.width() < 20 or rect.height() < 12:
            top_left = tb.mapFromGlobal(frame.mapToGlobal(QPoint(0, 0)))
            w = max(120, frame.width(), frame.sizeHint().width())
            h = max(24, frame.height(), frame.sizeHint().height(), tb.height())
            rect = QRect(top_left.x(), top_left.y(), w, h)
        if rect.width() < 20:
            rect = QRect(
                max(0, tb.width() - 220), 0,
                200, max(28, tb.height()))
        frame.setProperty("hideui_recall_size_rect", rect)
        return rect

    def _build_recall_size_overlay(self, qwin):
        """White box over the brush size slider — overlay only, do not mutate the slider."""
        tb, frame = self._find_recall_size_slider(qwin)
        if tb is None or frame is None:
            return False
        rect = self._recall_size_slider_rect(tb, frame)
        if rect.isEmpty():
            return False
        ov = _RecallOverlay("toolbar:brush_size", frame, tb)
        ov.setGeometry(rect)
        ov.show()
        ov.raise_()
        if frame not in self._recall_command_widgets:
            self._recall_command_widgets.append(frame)
        for child_ov in tb.findChildren(QWidget, RECALL_OVERLAY_NAME):
            child_ov.raise_()
        _log(
            "recall size overlay placed %dx%d at (%d,%d)"
            % (rect.width(), rect.height(), rect.x(), rect.y()))
        return True

    def _canvas_rect_in_qwin(self, qwin):
        canvas = self._canvas_w
        if canvas is None or not _qt_alive(canvas):
            for w in qwin.findChildren(QWidget):
                if "Canvas" in w.metaObject().className() and w.isVisible():
                    canvas = w
                    self._canvas_w = w
                    break
        if canvas is None or not _qt_alive(canvas) or not canvas.isVisible():
            return QRect()
        top_left = qwin.mapFromGlobal(canvas.mapToGlobal(QPoint(0, 0)))
        return QRect(top_left, canvas.size())

    def _ensure_recall_question_banner(self, qwin):
        if not _qt_alive(qwin):
            return None
        banner = self._recall_question_banner
        if banner is None or not _qt_alive(banner):
            banner = qwin.findChild(QFrame, RECALL_QUESTION_NAME)
        if banner is None:
            banner = _RecallQuestionBanner(qwin)
            self._recall_question_banner = banner
        elif self._recall_question_banner is None:
            self._recall_question_banner = banner
        return banner

    def _position_recall_question_banner(self, qwin):
        banner = self._recall_question_banner
        if banner is None or not _qt_alive(banner) or not banner.isVisible():
            return
        rect = self._canvas_rect_in_qwin(qwin)
        if rect.isEmpty():
            return
        margin = 14
        height = min(130, max(72, rect.height() // 5))
        banner.setGeometry(QRect(
            rect.x() + margin,
            rect.y() + margin,
            max(220, rect.width() - 2 * margin),
            height))
        banner.show()
        banner.raise_()

    def _show_recall_question(self, qwin, question):
        from .recall_test import format_recall_prompt_html
        banner = self._ensure_recall_question_banner(qwin)
        if banner is None:
            return
        text, rich = format_recall_prompt_html(question)
        banner.set_question(text, rich=rich)
        banner.show()
        self._position_recall_question_banner(qwin)

    def _hide_recall_question(self, qwin):
        if self._recall_question_banner is not None and _qt_alive(
                self._recall_question_banner):
            self._recall_question_banner.hide()
        if _qt_alive(qwin):
            existing = qwin.findChild(QFrame, RECALL_QUESTION_NAME)
            if existing is not None:
                existing.hide()

    def _global_hit(self, widget, global_pos):
        if widget is None or not _qt_alive(widget) or not widget.isVisible():
            return False
        local = widget.mapFromGlobal(global_pos)
        return widget.rect().contains(local)

    def _is_recall_ui_excluded_click(self, obj, global_pos):
        """Ignore recall answer capture on study chrome and modal dialogs."""
        if getattr(self, "_recall_input_blocked", False):
            return True
        modal = QApplication.activeModalWidget()
        if modal is not None:
            if isinstance(obj, QWidget):
                w = obj
                while w is not None:
                    if w is modal:
                        return True
                    w = _widget_parent(w)
            if self._global_hit(modal, global_pos):
                return True
        if isinstance(obj, QWidget):
            w = obj
            while w is not None:
                if w is self._skip_learn_btn or w is self._next_recall_btn or w is self._timer_label:
                    return True
                if w is self._study_toolbar or w.objectName() == STUDY_CHROME_TOOLBAR:
                    return True
                if w.objectName() in (RECALL_QUESTION_NAME, "hideuiRecallQuestion"):
                    return True
                if isinstance(w, QDialog):
                    return True
                w = _widget_parent(w)
        for w in (
                self._skip_learn_btn, self._next_recall_btn, self._timer_label,
                self._study_toolbar, self._close_btn,
                self._recall_question_banner):
            if w is not None and _qt_alive(w) and self._global_hit(w, global_pos):
                return True
        return False

    def _recall_overlay_at(self, global_pos):
        if not self._qwin_alive():
            return None, None, None
        pt = (global_pos if isinstance(global_pos, QPoint)
              else QPoint(int(global_pos.x()), int(global_pos.y())))
        w = QApplication.widgetAt(pt)
        while w is not None:
            if w.objectName() == RECALL_OVERLAY_NAME:
                cmd = w.property("hideui_recall_cmd")
                target = w.property("hideui_recall_feedback") or w.parentWidget()
                if cmd:
                    return str(cmd), target, w
            w = _widget_parent(w)
        hits = []
        for ov in self._qwin.findChildren(QWidget, RECALL_OVERLAY_NAME):
            if ov.isVisible() and self._global_hit(ov, global_pos):
                hits.append(ov)
        if not hits:
            return None, None, None
        ov = min(hits, key=lambda o: max(1, o.width()) * max(1, o.height()))
        cmd = ov.property("hideui_recall_cmd")
        target = ov.property("hideui_recall_feedback") or ov.parentWidget()
        if cmd:
            return str(cmd), target, ov
        return None, None, None

    def _recall_docker_host(self, dock):
        host = dock.widget()
        return host if host is not None else dock

    def _widget_rect_on_host(self, widget, host, min_w=28, min_h=28):
        if widget is None or host is None:
            return QRect()
        top_left = host.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
        w = max(min_w, widget.width())
        h = max(min_h, widget.height())
        return QRect(top_left, QSize(w, h))

    def _place_recall_overlay(self, host, target, cmd_id, min_w=28, min_h=28):
        if host is None or target is None or not _qt_alive(host) or not _qt_alive(target):
            return None
        rect = self._widget_rect_on_host(target, host, min_w, min_h)
        if rect.isEmpty():
            return None
        ov = _RecallOverlay(cmd_id, target, host)
        ov.setGeometry(rect)
        ov.show()
        ov.raise_()
        if target not in self._recall_command_widgets:
            self._recall_command_widgets.append(target)
        return ov

    def _count_visible_recall_overlays(self, qwin):
        if not _qt_alive(qwin):
            return 0
        count = 0
        for ov in qwin.findChildren(QWidget, RECALL_OVERLAY_NAME):
            if _qt_alive(ov) and ov.isVisible():
                count += 1
        return count

    def _ensure_recall_command_widgets_visible(self, qwin):
        if not _qt_alive(qwin):
            return
        try:
            for dock in qwin.findChildren(QDockWidget):
                name = dock.objectName()
                if name == "ToolBox":
                    dock.show()
                    for btn in dock.findChildren(QToolButton):
                        if self._keep_toolbox_button(btn):
                            btn.show()
                            btn.setEnabled(True)
                elif name in KEEP_DOCKERS:
                    dock.show()
            for tb in qwin.findChildren(QToolBar):
                if tb.objectName() == "BrushesAndStuff":
                    tb.show()
        except Exception:
            _log(traceback.format_exc())

    def _prepare_recall_overlay_targets(self, qwin):
        """Light widget/layout refresh for overlay placement — never re-mask."""
        if not self._recall_active or not _qt_alive(qwin):
            return
        try:
            self._ensure_study_dockers_visible(qwin)
            self._configure_layers_panel(qwin)
            self._configure_native_brush_slider(qwin)
            from .layout_profiles import profile_flags
            flags = profile_flags(
                getattr(self, "_study_layout_profile", "A"))
            if flags.get("presets_in_toolbar"):
                self._embed_presets_in_toolbar(qwin)
            self._trim_brush_presets(qwin)
            if self._preset_popup_widget is None or not _qt_alive(
                    self._preset_popup_widget):
                found = self._find_preset_popup_widget(qwin)
                if found is not None:
                    self._preset_popup_widget = found
            self._ensure_recall_command_widgets_visible(qwin)
            QApplication.processEvents()
        except Exception:
            _log(traceback.format_exc())

    def _schedule_recall_overlay_warmup(self, qwin):
        """Place white boxes repeatedly after Krita is visible (light rebuilds)."""
        if not self._recall_active or not _qt_alive(qwin):
            return
        for delay in RECALL_OVERLAY_WARMUP_DELAYS_MS:
            self._schedule_recall_overlay_rebuild(qwin, delay, prepare=False)

    def _schedule_recall_overlay_rebuild(self, qwin, delay_ms, prepare=False):
        """Rebuild recall overlays later; stale timers are ignored."""
        gen = self._recall_overlay_generation
        def run():
            if gen != self._recall_overlay_generation:
                return
            if not self._recall_active or self._phase_transition_busy:
                return
            if self._recall_question_answered:
                return
            self._build_recall_overlays(qwin, prepare=prepare)
        QTimer.singleShot(delay_ms, run)

    def _build_recall_overlays(self, qwin, prepare=True):
        if not self._recall_active or not _qt_alive(qwin):
            return 0
        if self._recall_question_answered:
            return 0
        try:
            if prepare:
                self._prepare_recall_overlay_targets(qwin)
            self._clear_recall_overlays(qwin)
            self._recall_command_widgets = []
            from .layout_profiles import profile_flags
            layout_flags = profile_flags(
                getattr(self, "_study_layout_profile", "A"))
            for dock in qwin.findChildren(QDockWidget):
                name = dock.objectName()
                if name not in KEEP_DOCKERS:
                    continue
                host = self._recall_docker_host(dock)
                if name == "ToolBox":
                    for btn in dock.findChildren(QToolButton):
                        if not self._keep_toolbox_button(btn):
                            continue
                        if not btn.isVisible():
                            btn.show()
                            btn.setEnabled(True)
                        oid = btn.objectName() or ""
                        tip = (btn.toolTip() or "").lower()
                        if oid:
                            cmd = "toolbox:%s" % oid
                        elif "eraser" in tip:
                            cmd = "toolbox:eraser"
                        else:
                            continue
                        self._place_recall_overlay(host, btn, cmd, 30, 30)
                elif name == "KisLayerBox":
                    tagged = []
                    for btn_name in LAYER_RECALL_BUTTONS:
                        btn = self._find_layer_box_button(dock, btn_name)
                        if btn is None:
                            continue
                        if not btn.isVisible():
                            btn.show()
                            btn.setEnabled(True)
                        self._prepare_layer_recall_button(btn)
                        self._place_recall_overlay(
                            host, btn, "layer:%s" % btn_name, 32, 32)
                        tagged.append(btn_name)
                    _log("recall layer overlays: %s" % tagged)
                elif name == "PresetDocker" and not layout_flags["presets_in_toolbar"]:
                    self._build_recall_preset_overlays(dock)
                elif name == "ColorSelectorNg":
                    self._build_recall_color_overlays(dock, host)
                for ov in host.findChildren(QWidget, RECALL_OVERLAY_NAME):
                    ov.raise_()
            if layout_flags["presets_in_toolbar"]:
                popup = self._preset_popup_widget
                if popup is not None and _qt_alive(popup):
                    tb = self._find_brushes_toolbar(qwin)
                    self._build_recall_preset_overlays(
                        popup, host=tb or qwin)
            self._build_recall_size_overlay(qwin)
            for ov in qwin.findChildren(QWidget, RECALL_OVERLAY_NAME):
                if _qt_alive(ov):
                    ov.raise_()
            placed = self._count_visible_recall_overlays(qwin)
            _log("recall overlays built: %d widget(s)" % placed)
            self._suppress_recall_tooltips(qwin)
            QToolTip.hideText()
            self._position_recall_question_banner(qwin)
            return placed
        except Exception:
            _log(traceback.format_exc())
            return 0

    def _refresh_recall_panel_message(self, learn_num=0, trial=False):
        from .recall_test import recall_side_panel_message
        learn_num = int(learn_num or 0)
        opening = bool(
            self.session
            and int(self.session.get("session", 0) or 0) == 2
            and learn_num == 0)
        practice = (
            not opening
            and self._is_session1()
            and learn_num == 1
            and bool(trial))
        q_sec = (self._recall_meta or {}).get("question_time_sec", 15)
        self._recall_panel_message = recall_side_panel_message(
            opening=opening,
            practice=practice,
            question_time_sec=q_sec)

    def _run_recall_phase(self, qwin):
        if self._quitting:
            return
        try:
            from .recall_test import prepare_recall_questions, recall_timing
            trial = bool(self._recall_skip_save)
            self._recall_meta = recall_timing(trial=trial)
            self._recall_questions = prepare_recall_questions(trial=trial)
            self._recall_index = 0
            self._recall_results = []
            self._recall_awaiting_first_question = False
            self._recall_question_time_sec = self._recall_meta["question_time_sec"]
            self._recall_phase_time_sec = self._recall_meta.get("phase_time_sec")
            self._recall_phase_remaining_sec = self._recall_phase_time_sec
            self._recall_cold_attempts = 0
            _log("recall phase: trial=%s questions=%d q_time=%ss phase=%ss" % (
                trial, len(self._recall_questions),
                self._recall_question_time_sec,
                self._recall_phase_time_sec or "none"))
            learn_num = int(getattr(self, "_pending_recall_learn_num", 0) or 0)
            from .experiment_log import log_e, register_recall_questions
            log_e(
                "recall",
                action="start",
                learn_num=learn_num,
                trial=trial,
                opening=bool(
                    self.session
                    and int(self.session.get("session", 0) or 0) == 2
                    and learn_num == 0),
                question_count=len(self._recall_questions or []),
                layout=str(getattr(self, "_study_layout_profile", "")))
            register_recall_questions(self._recall_questions, learn_num=learn_num)
            self._refresh_recall_panel_message(learn_num=learn_num, trial=trial)
            self._prepare_recall_canvas(
                qwin, lambda ok: self._on_fresh_canvas_for_recall(qwin, ok))
        except Exception:
            _log(traceback.format_exc())
            self._request_quit(force=True)

    def _start_recall_phase_timer(self, qwin):
        if not self._recall_phase_time_sec or self._recall_phase_remaining_sec is None:
            return
        if self._recall_phase_timer is not None:
            self._recall_phase_timer.stop()

        def phase_tick():
            if not self._recall_active or self._quitting:
                if self._recall_phase_timer is not None:
                    self._recall_phase_timer.stop()
                return
            self._recall_phase_remaining_sec -= 1
            if self._recall_phase_remaining_sec <= 0:
                self._recall_phase_timer.stop()
                self._on_recall_phase_timeout(qwin)

        self._recall_phase_timer = QTimer()
        self._recall_phase_timer.timeout.connect(phase_tick)
        self._recall_phase_timer.start(1000)

    def _on_recall_phase_timeout(self, qwin):
        if self._quitting or not self._recall_active:
            return
        if self._recall_timer is not None:
            self._recall_timer.stop()
        self._recall_waiting_for_next = False
        self._set_next_recall_visible(False)
        if (not self._recall_question_answered
                and self._recall_index < len(self._recall_questions)):
            self._recall_question_answered = True
            self._record_recall_answer(None, False, timeout=True)
        _log("recall phase time limit reached")
        self._finish_recall_phase(qwin)

    def _on_fresh_canvas_for_recall(self, qwin, ok):
        if self._quitting:
            return
        if not ok:
            attempts = getattr(self, "_recall_cold_attempts", 0) + 1
            self._recall_cold_attempts = attempts
            if attempts < 3:
                _log("recall canvas failed, retry %d/3" % attempts)
                QTimer.singleShot(
                    300,
                    lambda: self._prepare_recall_canvas(
                        qwin,
                        lambda o: self._on_fresh_canvas_for_recall(qwin, o)))
                return
            _log("recall canvas prep failed after retries")
            self._request_quit(force=True)
            return
        self._recall_cold_attempts = 0
        try:
            override = getattr(self, "_recall_layout_profile_override", None)
            if override:
                self._study_layout_profile = override
            if not self._begin_recall(qwin):
                self._request_quit(force=True)
                return
            self._start_recall_phase_timer(qwin)
        except Exception:
            _log(traceback.format_exc())
            self._request_quit(force=True)

    def _start_recall_question(self, qwin):
        if self._quitting or not self._recall_active:
            return
        if self._recall_index >= len(self._recall_questions):
            self._finish_recall_phase(qwin)
            return
        if (self._recall_phase_remaining_sec is not None
                and self._recall_phase_remaining_sec <= 0):
            self._finish_recall_phase(qwin)
            return
        question = self._recall_questions[self._recall_index]
        self._recall_overlay_generation += 1
        self._recall_question_answered = False
        self._recall_waiting_for_next = False
        self._set_next_recall_visible(False)
        self._clear_recall_feedback()
        self._show_recall_question(qwin, question)
        self._recall_question_shown_ms = int(time.time() * 1000)
        from .experiment_log import log_e
        log_e(
            "recall_question",
            num=int(self._recall_index + 1),
            question_id=question.get("id", ""),
            prompt=question.get("prompt", ""),
            presented_ms=self._recall_question_shown_ms)
        per_q = self._recall_question_time_sec
        if self._recall_phase_remaining_sec is not None:
            per_q = min(per_q, max(1, int(self._recall_phase_remaining_sec)))
        self._recall_remaining_sec = per_q
        self._update_recall_timer_display()
        self._set_recall_timer_visible(True)
        for delay in (0, 250, 700):
            self._schedule_recall_overlay_rebuild(qwin, delay, prepare=False)
        QTimer.singleShot(80, lambda: self._position_recall_question_banner(qwin))
        if self._recall_timer is not None:
            self._recall_timer.stop()

        def tick():
            self._recall_remaining_sec -= 1
            self._update_recall_timer_display()
            if self._recall_remaining_sec <= 0:
                self._recall_timer.stop()
                if not self._recall_question_answered:
                    self._recall_question_answered = True
                    self._recall_overlay_generation += 1
                    self._record_recall_answer(None, False, timeout=True)
                    self._prompt_next_recall_question(qwin)

        self._recall_timer = QTimer()
        self._recall_timer.timeout.connect(tick)
        self._recall_timer.start(1000)

    def _set_recall_timer_visible(self, visible):
        try:
            if self._timer_label is None:
                return
            if visible:
                self._stop_timer_blink()
                self._update_recall_timer_display()
                self._timer_label.setStyleSheet(TIMER_STYLE_NORMAL)
                self._timer_label.show()
            else:
                self._timer_label.hide()
        except Exception:
            _log(traceback.format_exc())

    def _update_recall_timer_display(self):
        if self._timer_label is None:
            return
        self._timer_label.setText(self._format_time_left(self._recall_remaining_sec))

    def _recall_cmd_for_widget(self, widget):
        w = widget
        while w is not None:
            if self._widget_in_docker(w, "KisLayerBox"):
                name = w.objectName() or ""
                if name in LAYER_RECALL_BUTTONS:
                    return "layer:%s" % name
            if isinstance(w, QToolButton) and self._widget_in_docker(w, "ToolBox"):
                if self._keep_toolbox_button(w):
                    oid = w.objectName() or ""
                    if oid:
                        return "toolbox:%s" % oid
            cmd = w.property("hideui_recall_cmd")
            if cmd:
                return str(cmd)
            w = _widget_parent(w)
        return None

    def _on_recall_click(self, widget, cmd_id, overlay=None, click_global=None):
        if self._recall_awaiting_first_question:
            return
        if getattr(self, "_recall_auto_starting", False):
            return
        if self._recall_question_answered or self._quitting or not self._recall_active:
            return
        if self._recall_index >= len(self._recall_questions):
            return
        self._recall_question_answered = True
        self._recall_overlay_generation += 1
        if self._recall_timer is not None:
            self._recall_timer.stop()
        question = self._recall_questions[self._recall_index]
        from .recall_test import recall_answer_matches
        correct = recall_answer_matches(question["answer"], cmd_id)
        _log("recall click q=%s clicked=%s expected=%s correct=%s" % (
            question["id"], cmd_id, question["answer"], correct))
        self._show_recall_feedback(widget, correct, overlay=overlay)
        click_xy = None
        if click_global is not None:
            try:
                click_xy = (int(click_global.x()), int(click_global.y()))
            except Exception:
                click_xy = None
        self._record_recall_answer(
            cmd_id, correct, timeout=False, click_xy=click_xy)
        self._prompt_next_recall_question(self._qwin)

    def _collect_recall_overlay_geometry(self, qwin=None):
        """List visible recall overlays with global centers for error metrics."""
        qwin = qwin or self._qwin
        if not _qt_alive(qwin):
            return []
        items = []
        try:
            for ov in qwin.findChildren(QWidget, RECALL_OVERLAY_NAME):
                if not _qt_alive(ov) or not ov.isVisible():
                    continue
                cmd = ov.property("hideui_recall_cmd")
                if not cmd:
                    continue
                center = ov.mapToGlobal(ov.rect().center())
                items.append({
                    "cmd_id": str(cmd),
                    "cx": int(center.x()),
                    "cy": int(center.y()),
                    "w": int(ov.width()),
                    "h": int(ov.height()),
                })
        except Exception:
            _log(traceback.format_exc())
        return items

    def _record_recall_answer(self, clicked_cmd, correct, timeout=False,
                              click_xy=None):
        if self._recall_index >= len(self._recall_questions):
            return
        question = self._recall_questions[self._recall_index]
        answered_ms = int(time.time() * 1000)
        shown_ms = int(getattr(self, "_recall_question_shown_ms", 0) or 0)
        if shown_ms > 0:
            time_taken_ms = max(0, answered_ms - shown_ms)
        else:
            time_taken_ms = 0
        error = {
            "slot_offset_x": "",
            "slot_offset_y": "",
            "slot_distance": "",
            "pixel_offset_x": "",
            "pixel_offset_y": "",
            "pixel_distance": "",
        }
        if clicked_cmd and not timeout:
            try:
                from .recall_test import compute_recall_click_error
                overlays = self._collect_recall_overlay_geometry()
                cx = cy = None
                if click_xy is not None:
                    cx, cy = click_xy
                error = compute_recall_click_error(
                    overlays,
                    question.get("answer"),
                    clicked_cmd,
                    click_x=cx,
                    click_y=cy)
            except Exception:
                _log(traceback.format_exc())
        result = {
            "question_id": question["id"],
            "prompt": question["prompt"],
            "expected": question["answer"],
            "clicked": clicked_cmd,
            "correct": bool(correct),
            "timeout": bool(timeout),
            "unanswered": bool(timeout) or not clicked_cmd,
            "presented_ms": shown_ms,
            "answered_ms": answered_ms,
            "time_taken_ms": time_taken_ms,
        }
        result.update(error)
        self._recall_results.append(result)
        from .experiment_log import log_t
        log_t(
            "recall",
            question_id=question.get("id", ""),
            num=self._recall_index + 1,
            prompt=question.get("prompt", ""),
            correct=bool(correct),
            clicked=str(clicked_cmd or ""),
            timeout=bool(timeout),
            time_taken_ms=time_taken_ms,
            **error)

    def _advance_recall_question(self, qwin):
        if self._quitting:
            return
        self._recall_index += 1
        self._start_recall_question(qwin)

    def _show_recall_feedback(self, widget, correct, overlay=None):
        target = overlay
        if target is None and self._qwin_alive():
            for ov in self._qwin.findChildren(QWidget, RECALL_OVERLAY_NAME):
                if ov.property("hideui_recall_feedback") is widget or ov is widget:
                    target = ov
                    break
        if target is None:
            target = widget
        if target is None:
            return
        if target.objectName() == RECALL_OVERLAY_NAME:
            if target not in self._recall_feedback_widgets:
                self._recall_feedback_widgets.append(target)
            if hasattr(target, "set_recall_result"):
                target.set_recall_result(correct)
            else:
                target.setProperty(
                    "hideui_recall_result", "correct" if correct else "wrong")
                target.setStyleSheet("")
                target.update()
                target.repaint()
            target.show()
            target.raise_()
            return
        if target not in self._recall_feedback_widgets:
            self._recall_feedback_widgets.append(target)
        base = target.property("hideui_recall_orig_style")
        if not base:
            base = target.styleSheet() or ""
            target.setProperty("hideui_recall_orig_style", base)
        feedback = RECALL_FEEDBACK_CORRECT if correct else RECALL_FEEDBACK_WRONG
        target.setStyleSheet(("%s %s" % (base, feedback)).strip())

    def _clear_recall_feedback(self):
        self._recall_feedback_widgets = []
        if self._qwin_alive():
            self._build_recall_overlays(self._qwin)

    def _layer_docker_inner(self, dock):
        inner = dock.widget()
        return inner if inner is not None else dock

    def _find_layer_box_button(self, dock, name):
        inner = self._layer_docker_inner(dock)
        btn = inner.findChild(QAbstractButton, name)
        if btn is not None:
            return btn
        return inner.findChild(QWidget, name)

    def _prepare_layer_recall_button(self, btn):
        if btn is None or not _qt_alive(btn):
            return
        btn.setProperty(
            "hideui_recall_saved_geom",
            (btn.minimumSize(), btn.maximumSize(), btn.size()))
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setMinimumSize(32, 32)
        btn.setMaximumSize(32, 32)
        btn.setFixedSize(32, 32)
        btn.setIconSize(QSize(22, 22))
        pix = QPixmap(22, 22)
        pix.fill(Qt.transparent)
        btn.setIcon(QIcon(pix))
        btn.setText("")
        btn.setToolTip("")
        btn.setProperty("hideui_recall_tooltip_stripped", True)
        btn.show()
        btn.setEnabled(True)

    def _remember_recall_mask(self, widget, **props):
        saved = {"widget": widget}
        for key, value in props.items():
            saved[key] = value
        self._recall_mask_state.append(saved)

    def _mask_recall_commands(self, qwin):
        self._recall_mask_state = []
        empty_icon = QIcon()
        try:
            for dock in qwin.findChildren(QDockWidget):
                if dock.objectName() not in KEEP_DOCKERS:
                    continue
                name = dock.objectName()
                if name == "ToolBox":
                    for btn in dock.findChildren(QToolButton):
                        if not self._keep_toolbox_button(btn):
                            continue
                        self._remember_recall_mask(
                            btn,
                            icon=btn.icon(),
                            text=btn.text(),
                            tooltip=btn.toolTip(),
                            style=btn.styleSheet())
                        btn.setIcon(empty_icon)
                        btn.setText("")
                        btn.setToolTip("")
                        btn.setProperty("hideui_recall_tooltip_stripped", True)
                        btn.setStyleSheet(RECALL_MASK_BTN_STYLE)
                elif name == "KisLayerBox":
                    for btn_name in LAYER_RECALL_BUTTONS:
                        w = self._find_layer_box_button(dock, btn_name)
                        if w is None:
                            continue
                        self._remember_recall_mask(
                            w,
                            tooltip=w.toolTip(),
                            text=getattr(w, "text", lambda: "")(),
                            icon=w.icon() if hasattr(w, "icon") else None,
                            style=w.styleSheet())
                        if hasattr(w, "setToolTip"):
                            w.setToolTip("")
                        if hasattr(w, "setText"):
                            w.setText("")
                        self._prepare_layer_recall_button(w)
                        w.setStyleSheet(RECALL_MASK_GENERIC_STYLE)
                    tree = dock.findChild(QWidget, "listLayers")
                    if tree is not None:
                        self._remember_recall_mask(
                            tree, style=tree.styleSheet())
                        tree.setStyleSheet(
                            (tree.styleSheet() or "")
                            + " QTreeWidget { color: transparent; }"
                            + " QTreeWidget::item { color: transparent; }")
                elif name == "ColorSelectorNg":
                    inner = dock.widget()
                    if inner is not None:
                        self._remember_recall_mask(inner, style=inner.styleSheet())
                        inner.setStyleSheet(RECALL_MASK_GENERIC_STYLE)
                    for w in dock.findChildren(QWidget):
                        if w.metaObject().className() != "KisColorSelector":
                            continue
                        if w is inner:
                            continue
                        self._remember_recall_mask(w, style=w.styleSheet())
                        w.setStyleSheet(RECALL_MASK_GENERIC_STYLE)
        except Exception:
            _log(traceback.format_exc())

    def _strip_widget_tooltip_for_recall(self, widget):
        """Clear hover hints on a widget (and its QAction) during recall."""
        if not _qt_alive(widget) or not hasattr(widget, "toolTip"):
            return
        action = None
        action_tip = ""
        if isinstance(widget, QToolButton):
            action = widget.defaultAction()
            if action is not None:
                action_tip = action.toolTip() or ""
        if widget.property("hideui_recall_tooltip_stripped"):
            if action is not None and action_tip:
                action.setToolTip("")
                self._recall_mask_state.append({
                    "widget": widget,
                    "tooltip": "",
                    "action": action,
                    "action_tooltip": action_tip,
                })
            return
        tip = widget.toolTip() or ""
        if not tip and not action_tip:
            return
        widget.setToolTip("")
        if action is not None and action_tip:
            action.setToolTip("")
        widget.setProperty("hideui_recall_tooltip_stripped", True)
        saved = {"widget": widget, "tooltip": tip}
        if action is not None:
            saved["action"] = action
            saved["action_tooltip"] = action_tip
        self._recall_mask_state.append(saved)

    def _suppress_recall_tooltips(self, qwin):
        """Strip all hover tooltips from study panels so recall cannot be cheated."""
        if not _qt_alive(qwin):
            return
        try:
            for dock in qwin.findChildren(QDockWidget):
                if dock.objectName() not in KEEP_DOCKERS:
                    continue
                for w in dock.findChildren(QWidget):
                    self._strip_widget_tooltip_for_recall(w)
            for tb in qwin.findChildren(QToolBar):
                if tb.objectName() not in NATIVE_TOOLBARS:
                    continue
                for w in tb.findChildren(QWidget):
                    self._strip_widget_tooltip_for_recall(w)
        except Exception:
            _log(traceback.format_exc())

    def _recall_tooltip_allowed(self, obj):
        """Study chrome may still show tooltips (skip button, etc.)."""
        if not isinstance(obj, QWidget):
            return False
        modal = QApplication.activeModalWidget()
        w = obj
        while w is not None:
            if modal is not None and w is modal:
                return True
            if w in (
                    self._skip_learn_btn, self._next_recall_btn, self._timer_label,
                    self._close_btn, self._recall_question_banner):
                return True
            if w.objectName() in (STUDY_CHROME_TOOLBAR, RECALL_QUESTION_NAME):
                return True
            w = _widget_parent(w)
        return False

    def _unmask_recall_commands(self, qwin):
        for saved in reversed(self._recall_mask_state):
            try:
                w = saved.get("widget")
                if not _qt_alive(w):
                    continue
                if "text" in saved and hasattr(w, "setText"):
                    w.setText(saved["text"] or "")
                if "tooltip" in saved and hasattr(w, "setToolTip"):
                    w.setToolTip(saved["tooltip"] or "")
                action = saved.get("action")
                if action is not None and "action_tooltip" in saved:
                    try:
                        action.setToolTip(saved["action_tooltip"] or "")
                    except Exception:
                        pass
                w.setProperty("hideui_recall_tooltip_stripped", None)
                if "icon" in saved and saved["icon"] is not None and hasattr(w, "setIcon"):
                    w.setIcon(saved["icon"])
                if "icon_size" in saved and hasattr(w, "setIconSize"):
                    w.setIconSize(saved["icon_size"])
                if "style" in saved:
                    w.setStyleSheet(saved["style"] or "")
                if "min" in saved and hasattr(w, "setMinimumSize"):
                    w.setMinimumSize(saved["min"])
                if "max" in saved and hasattr(w, "setMaximumSize"):
                    w.setMaximumSize(saved["max"])
                if "visible" in saved and hasattr(w, "setVisible"):
                    w.setVisible(bool(saved["visible"]))
                if saved.get("mouse_transparent"):
                    w.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                w.setProperty("hideui_preset_recall_masked", False)
                w.setProperty("hideui_size_masked", False)
                w.setProperty("hideui_recall_size_rect", None)
                geom = w.property("hideui_recall_saved_geom")
                if geom:
                    min_sz, max_sz, _size = geom
                    w.setMinimumSize(min_sz)
                    w.setMaximumSize(max_sz)
                    w.setProperty("hideui_recall_saved_geom", None)
                w.setProperty("hideui_recall_orig_style", None)
            except Exception:
                pass
        self._recall_mask_state = []

    def _finish_recall_phase(self, qwin):
        if self._quitting:
            return
        try:
            self._recall_overlay_generation += 1
            self._recall_active = False
            self._recall_waiting_for_next = False
            self._recall_awaiting_first_question = False
            self._recall_auto_starting = False
            self._recall_auto_start_token = int(
                getattr(self, "_recall_auto_start_token", 0) or 0) + 1
            self._recall_krita_hidden_until_start = False
            self._recall_panel_message = None
            self._hide_loading_screen()
            self._stop_recall_click_capture()
            if self._recall_timer is not None:
                self._recall_timer.stop()
            if self._recall_phase_timer is not None:
                self._recall_phase_timer.stop()
            self._set_recall_timer_visible(False)
            self._set_next_recall_visible(False)
            self._set_skip_recall_visible(False)
            self._hide_recall_question(qwin)
            self._clear_recall_feedback()
            self._clear_recall_overlays(qwin)
            if self._video_panel is not None:
                self._video_panel.end_recall_instructions_panel()
            from .recall_test import recall_score_percent
            total_q = len(self._recall_questions or [])
            phase_skipped = (
                getattr(self, "_recall_end_reason", "complete") == "experimenter_skip")
            end_reason = getattr(self, "_recall_end_reason", "complete")
            from .experiment_log import finalize_recall_block, log_e
            partial_results = list(self._recall_results or [])
            self._recall_results = finalize_recall_block(
                self._recall_questions,
                partial_results,
                phase_skipped=phase_skipped)
            if phase_skipped and partial_results:
                score_pct = recall_score_percent(partial_results, total_q)
            else:
                score_pct = recall_score_percent(self._recall_results, total_q)
            log_e(
                "recall",
                action="end",
                learn_num=int(getattr(self, "_pending_recall_learn_num", 0) or 0),
                reason=end_reason)
            self._recall_end_reason = "complete"
            self._recall_skip_save = False
            self._recall_layout_profile_override = None
            self._ensure_study_dockers_visible(qwin)
            self._apply_all_dock_titles(qwin)
            self._unmask_recall_commands(qwin)
            self._restore_brush_size_slider(qwin)
            self._pause_session_ui(qwin)
            from .session_flow import run_recall_score_screen
            if not run_recall_score_screen(score_pct):
                self._request_quit(force=True)
                return
            fn = self._after_recall_fn
            self._after_recall_fn = None
            if fn is not None:
                fn(qwin)
            else:
                self._return_to_login(qwin)
        except Exception:
            _log(traceback.format_exc())
            self._request_quit(force=True)

    def _start_recall_block(self, qwin, after_fn, skip_save=False,
                            panel_message=None, learn_num=0,
                            layout_profile=None):
        self._after_recall_fn = after_fn
        self._recall_skip_save = skip_save
        self._recall_panel_message = panel_message
        self._pending_recall_learn_num = int(learn_num)
        self._recall_layout_profile_override = layout_profile
        if layout_profile is not None:
            self._study_layout_profile = layout_profile
            if not self._is_session1() and layout_profile != "A":
                self._learning_layout_profile = layout_profile
        _log("recall block layout profile: %s" % self._recall_layout_profile())
        self._run_recall_phase(qwin)

    def _soft_pause_tutorial(self, qwin):
        """Stop learning/video but keep Krita window geometry."""
        try:
            self._halt_deferred_work()
            self._tutorial_active = False
            self._tutorial_remaining_sec = None
            self._set_skip_learning_visible(False)
            self._set_skip_recall_visible(False)
            self._tutorial_timer_done_cb = None
            if self._tutorial_timer is not None:
                self._tutorial_timer.stop()
            self._video_shown_for_canvas = False
            self._pause_video_for_phase_change()
            if self._video_panel is not None:
                self._video_panel.end_learning_instructions_panel()
        except Exception:
            _log(traceback.format_exc())

    def _run_tutorial_block(self, qwin, title, body, time_sec,
                            restart, after_learning_fn, learn_num,
                            layout_after=None):
        from .session_flow import run_tutorial_intro
        self._ensure_learning_recall_ui_cleared(qwin)
        if not run_tutorial_intro(title, body):
            self._request_quit(force=True)
            return
        if self._is_session1() and int(learn_num) == 1:
            from .video_panel import run_krita_environment_intro
            if not run_krita_environment_intro():
                self._request_quit(force=True)
                return
        self._active_learn_num = int(learn_num)
        self._tutorial_phase_sec = time_sec
        layout = layout_after or getattr(self, "_study_layout_profile", "A")
        self._learning_layout_profile = layout
        self._study_layout_profile = layout
        _log("learning block layout: %s (tutorial %s)" % (layout, learn_num))

        def after_canvas(canvas_ok):
            if not canvas_ok:
                self._request_quit(force=True)
                return
            self._begin_tutorial(qwin, restart=restart, on_ready=lambda ok: (
                self._request_quit(force=True) if not ok else
                self._start_step_by_step_learning(
                    after_learning_fn,
                    learn_num=learn_num,
                    time_sec=time_sec if self._learning_uses_phase_timer() else None)))

        self._prepare_study_canvas(
            qwin, after_canvas,
            label="learning_%d" % learn_num, layout_after=layout)

    def _after_learning_hold_then_recall(self, qwin, hold, skip_save, after_recall,
                                         learn_num=0):
        from .session_flow import run_hold_screen
        from .recall_test import recall_side_panel_message
        self._soft_pause_tutorial(qwin)
        if not run_hold_screen(hold["title"], hold["body"]):
            self._request_quit(force=True)
            return
        from .layout_profiles import LAYOUT_A
        if self._is_session1():
            recall_layout = LAYOUT_A
        else:
            recall_layout = self._recall_layout_profile()
        practice_recall = self._is_session1() and int(learn_num) == 1
        self._start_recall_block(
            qwin, after_recall, skip_save=skip_save,
            panel_message=recall_side_panel_message(
                opening=False, practice=practice_recall),
            learn_num=learn_num,
            layout_profile=recall_layout)

    def _run_break(self, qwin, after_fn, learn_num=0, break_body=None):
        """Timed break in a standalone gateway window; Krita stays hidden."""
        if self._quitting:
            return
        self._pending_break_learn_num = int(learn_num)
        self._pending_break_body = break_body
        # No canvas/loading prep for breaks — go straight to the break screen.
        self._hide_loading_screen()
        self._start_break_window(qwin, after_fn, True)

    def _start_break_window(self, qwin, after_fn, ok):
        from .session_flow import run_timed_break, BREAK_SEC
        from .video_panel import suspend_playback_for_phase_change
        from .experiment_log import log_e
        if self._quitting:
            return
        if not ok:
            self._request_quit(force=True)
            return
        self._tutorial_active = False
        self._recall_active = False
        suspend_playback_for_phase_change()
        self._pause_session_ui(qwin)
        learn_num = getattr(self, "_pending_break_learn_num", 0)
        break_body = getattr(self, "_pending_break_body", None)
        allow_skip = bool(learn_num and self.session)
        log_e(
            "break",
            action="start",
            learn_num=int(learn_num or 0),
            duration_sec=BREAK_SEC)
        ok, break_reason = run_timed_break(
            allow_skip=allow_skip, body=break_body)
        if not ok:
            self._request_quit(force=True)
            return
        log_e(
            "break",
            action="end",
            learn_num=int(learn_num or 0),
            reason=break_reason or "complete")
        if after_fn is not None:
            after_fn(qwin)

    def _end_tutorial(self, qwin):
        self._pause_session_ui(qwin)

    def _run_session1(self, qwin):
        if self._session1_running:
            return
        self._session1_running = True
        self._session_tutorial_index = 0
        self._set_study_layout_profile("A")
        _log("session 1 flow starting (condition %s)" % (
            self.session.get("condition") if self.session else "?"))
        try:
            self._tutorial_active = False
            self._recall_active = False
            self._session1_next_tutorial(qwin)
        except Exception:
            _log(traceback.format_exc())

    def _session1_next_tutorial(self, qwin):
        from .session_flow import SESSION_1_TUTORIALS, HOLD_AFTER_TUTORIAL
        idx = self._session_tutorial_index
        if idx >= len(SESSION_1_TUTORIALS):
            self._return_to_login(qwin)
            return
        tut = SESSION_1_TUTORIALS[idx]
        which = idx + 1
        hold = HOLD_AFTER_TUTORIAL[which]
        learn_sec = tut.get("learn_sec", 720)

        def after_learn():
            skip = not tut.get("logged", True)
            self._after_learning_hold_then_recall(
                qwin, hold, skip,
                lambda q: self._session1_after_recall(q),
                learn_num=which)

        self._run_tutorial_block(
            qwin, tut["title"], tut["body"], learn_sec,
            restart=(idx > 0), after_learning_fn=after_learn,
            learn_num=which)

    def _session1_after_recall(self, qwin):
        from .session_flow import SESSION_1_TUTORIALS
        learn_num = int(getattr(self, "_pending_recall_learn_num", 0) or 0) \
            or (self._session_tutorial_index + 1)

        def after_survey(_responses=None):
            def advance(q):
                self._session_tutorial_index += 1
                if self._session_tutorial_index >= len(SESSION_1_TUTORIALS):
                    self._return_to_login(q)
                else:
                    self._session1_next_tutorial(q)

            # No break after the final tutorial — go straight to session end.
            if self._session_tutorial_index >= len(SESSION_1_TUTORIALS) - 1:
                advance(qwin)
            else:
                self._run_break(qwin, advance, learn_num=learn_num)

        self._pause_session_ui(qwin)
        from .survey import run_post_recall_survey
        responses = run_post_recall_survey(learn_num=learn_num)
        if responses is None:
            self._request_quit(force=True)
            return
        after_survey(responses)

    def _run_session2(self, qwin):
        if self._session2_running:
            return
        self._session2_running = True
        self._session_tutorial_index = 0
        cond = self.session.get("condition") if self.session else "A"
        _log("session 2 flow starting (condition %s)" % cond)
        try:
            from .layout_profiles import LAYOUT_A
            from .recall_test import recall_side_panel_message
            self._start_recall_block(
                qwin,
                lambda q: self._session2_after_opening_recall(q),
                skip_save=False,
                panel_message=recall_side_panel_message(opening=True),
                layout_profile=LAYOUT_A)
        except Exception:
            _log(traceback.format_exc())

    def _session2_after_opening_recall(self, qwin):
        self._session_tutorial_index = 0
        self._session2_next_tutorial(qwin)

    def _session2_next_tutorial(self, qwin):
        from .session_flow import (
            session2_tutorial_count, TUTORIAL_LEARN_SEC,
            SESSION_2_TUTORIAL, HOLD_SESSION2_AFTER_TUTORIAL,
            learning_intro_body_for_session)
        cond = self.session.get("condition") if self.session else "A"
        total = session2_tutorial_count(cond)
        idx = self._session_tutorial_index
        if idx >= total:
            self._session2_finish_survey(qwin)
            return
        from .layout_profiles import resolve_layout_profile
        target_profile = resolve_layout_profile(cond, 2, tutorial_index=idx)
        which = idx + 1
        title = SESSION_2_TUTORIAL["title"] % which
        sess = int(self.session.get("session", 2) or 2) if self.session else 2
        intro_body = learning_intro_body_for_session(sess, which)
        learn_sec = SESSION_2_TUTORIAL.get("learn_sec", TUTORIAL_LEARN_SEC)
        hold = HOLD_SESSION2_AFTER_TUTORIAL.get(
            which, HOLD_SESSION2_AFTER_TUTORIAL[2])
        if which >= total:
            hold = HOLD_SESSION2_AFTER_TUTORIAL[3]

        def after_learn():
            self._after_learning_hold_then_recall(
                qwin, hold, False,
                lambda q: self._session2_after_tutorial_recall(q),
                learn_num=which)

        self._run_tutorial_block(
            qwin, title, intro_body, learn_sec,
            restart=(idx > 0), after_learning_fn=after_learn,
            learn_num=which, layout_after=target_profile)

    def _session2_after_tutorial_recall(self, qwin):
        from .session_flow import session2_tutorial_count, BREAK_MESSAGE_SESSION2_FINAL

        learn_num = int(getattr(self, "_pending_recall_learn_num", 0) or 0) \
            or (self._session_tutorial_index + 1)
        cond = self.session.get("condition") if self.session else "A"
        total = session2_tutorial_count(cond)

        def after_survey(_responses=None):
            if learn_num >= total:
                self._session_tutorial_index += 1
                self._session2_finish_survey(qwin)
                return

            def after_break(q):
                self._session_tutorial_index += 1
                self._session2_next_tutorial(q)

            break_body = None
            if learn_num >= total - 1:
                break_body = BREAK_MESSAGE_SESSION2_FINAL["body"]
            self._run_break(
                qwin, after_break, learn_num=learn_num, break_body=break_body)

        self._pause_session_ui(qwin)
        from .survey import run_post_recall_survey
        responses = run_post_recall_survey(learn_num=learn_num)
        if responses is None:
            self._request_quit(force=True)
            return
        after_survey(responses)

    def _session2_finish_survey(self, qwin):
        self._pause_session_ui(qwin)
        from .survey import run_final_session_survey
        if run_final_session_survey() is None:
            self._request_quit(force=True)
            return
        from .session_flow import run_session_complete
        if not run_session_complete(2):
            self._request_quit(force=True)
            return
        from .experiment_log import end_session
        end_session("complete")
        self._show_login_screen(qwin)

    def _show_login_screen(self, qwin):
        """Return to login after a session ends — do not quit Krita."""
        try:
            self._session1_running = False
            self._session2_running = False
            self._tutorial_active = False
            self._recall_active = False
            self._break_active = False
            self._quitting = False
            from .video_panel import shutdown_all_video, reset_video_state
            shutdown_all_video()
            self._video_panel = None
            from .experiment import suppress_krita_ui, LoginWindow, load_password_hashes
            suppress_krita_ui()
            if self._qwin_alive():
                qwin.hide()
            info = LoginWindow(load_password_hashes()).run_blocking()
            if info is None:
                self._request_quit(force=True)
                return
            import datetime
            info["started_at"] = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session = info
            from .experiment_log import start_session
            start_session(self.session)
            self._on_new_session_started()
            _log("returned to login: %s" % info)
            self._ensure_shortcuts_blocked(qwin)
            try:
                reset_video_state()
            except Exception:
                _log(traceback.format_exc())
            if info.get("session") == 1:
                self._setup_after_gateway(qwin, light=True)
                self._lock_window(qwin, show=False)
                self._run_session1(qwin)
            elif info.get("session") == 2:
                self._setup_after_gateway(qwin, light=True)
                self._lock_window(qwin, show=False)
                self._run_session2(qwin)
            else:
                if self._qwin_alive():
                    qwin.show()
                    qwin.raise_()
                    qwin.activateWindow()
                    self._enforce_window_geometry()
                QTimer.singleShot(300, lambda: self._update_video_panel(qwin))
        except Exception:
            _log(traceback.format_exc())
            self._request_quit(force=True)

    def _return_to_login(self, qwin):
        """After session 1 tutorials, hide Krita and show the login screen again."""
        try:
            self._session1_running = False
            self._tutorial_active = False
            self._video_shown_for_canvas = False
            from .video_panel import shutdown_all_video
            shutdown_all_video()
            self._video_panel = None

            from .experiment import suppress_krita_ui
            suppress_krita_ui()
            if self._qwin_alive():
                qwin.hide()

            from .session_flow import run_session_complete
            run_session_complete(1)
            from .experiment_log import end_session
            end_session("complete")
            self._show_login_screen(qwin)
        except Exception:
            _log(traceback.format_exc())
            self._request_quit(force=True)

    def _new_default(self, *args, force=False):
        try:
            if self._creating_doc:
                _log("ignored reentrant _new_default")
                return
            # Guard against spurious triggers during startup (no user action).
            if not force and time.monotonic() - self._start < 3.0:
                _log("ignored early _new_default")
                return
            self._creating_doc = True
            k = Krita.instance()

            def _read(key, default):
                try:
                    v = k.readSetting("", key, str(default))
                    return v if v not in (None, "") else str(default)
                except Exception:
                    return str(default)

            w = int(float(_read("imageWidthDef", 2480)))
            h = int(float(_read("imageHeightDef", 3508)))
            res = float(_read("imageResolutionDef", 300.0))
            model = _read("colorModelDef", "RGBA")
            depth = _read("colorDepthDef", "U8")
            profile = k.readSetting("", "colorProfileDef", "") or ""

            doc = k.createDocument(w, h, "Untitled", model, depth, profile, res)
            win = k.activeWindow()
            if win is not None:
                win.addView(doc)
            self._ensure_white_canvas_background(doc)
            _log("default document created (%dx%d @%g)" % (w, h, res))
            if self._qwin_alive():
                QTimer.singleShot(400, self._safe_view_changed)
        except Exception:
            _log(traceback.format_exc())
        finally:
            self._creating_doc = False

    def _on_focus_changed(self, old, now):
        try:
            dlg = QApplication.activeModalWidget()
            if (dlg is not None
                    and dlg.metaObject().className() == "KisDlgCreateNewDocument"
                    and dlg not in self._autodone):
                self._autodone.add(dlg)
                _log("Suppressed native New Document dialog")
                QTimer.singleShot(0, dlg.reject)
        except Exception:
            _log(traceback.format_exc())

    def eventFilter(self, obj, event):
        modal = self._active_modal_dialog()
        if self._study_ui_locked() and modal is None:
            et = event.type()
            if et in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease):
                if not self._study_keyboard_allowed(obj, event):
                    if et == QEvent.ShortcutOverride:
                        event.accept()
                    return True
            if et == QEvent.ContextMenu:
                if not self._study_context_menu_allowed(obj):
                    return True
            if et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                      QEvent.MouseButtonDblClick):
                if (event.button() == Qt.RightButton
                        and not self._study_context_menu_allowed(obj)):
                    return True
            if et == QEvent.Show and isinstance(obj, QMenu):
                if not self._study_text_editing_active():
                    obj.hide()
                    return True
        elif modal is not None:
            et = event.type()
            if et in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease):
                if self._study_modal_keyboard_allowed(obj):
                    return False

        if isinstance(obj, QWidget) and event.type() == QEvent.Show:
            cls = obj.metaObject().className()
            if cls == "KisFloatingMessage":
                text = ""
                for lbl in obj.findChildren(QLabel):
                    text += lbl.text() or ""
                if "zoom" in text.lower():
                    QTimer.singleShot(0, obj.hide)
                    return True
            if cls == "KisView":
                try:
                    obj.setShowFloatingMessage(False)
                except Exception:
                    pass

        if (self._text_tool_active
                and event.type() == QEvent.KeyRelease
                and not self._recall_active):
            self._schedule_study_text_style()

        if isinstance(obj, QWidget) and event.type() in (
                QEvent.MouseButtonPress,
                QEvent.MouseButtonRelease,
                QEvent.MouseButtonDblClick):
            if self._is_layer_list_inline_icon_click(obj, event):
                return True

        if (self._text_tool_active
                and isinstance(obj, QWidget)
                and event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton):
            cls = obj.metaObject().className()
            on_canvas = ("Canvas" in cls or obj is self._canvas_w)
            if on_canvas:
                self._schedule_study_text_style()

        if (self._learning_click_active()
                and isinstance(obj, QWidget)
                and event.type() in (
                    QEvent.MouseButtonPress,
                    QEvent.MouseButtonRelease,
                    QEvent.MouseButtonDblClick)):
            etype = {
                QEvent.MouseButtonPress: "press",
                QEvent.MouseButtonRelease: "release",
                QEvent.MouseButtonDblClick: "dblclick",
            }.get(event.type(), "click")
            self._log_learning_pointer_click(etype, event, obj)
            if (event.type() == QEvent.MouseButtonRelease
                    and event.button() == Qt.LeftButton):
                layer_name = obj.objectName() or ""
                if (layer_name in ("bnDelete", "bnRaise", "bnLower")
                        and self._widget_in_docker(obj, "KisLayerBox")):
                    self._log_learning_layer_button(layer_name)
                elif self._widget_in_docker(obj, "ColorSelectorNg"):
                    self._log_learning_color_clicked()

        if (self._recall_active
                and event.type() in (
                    QEvent.ToolTip, QEvent.StatusTip, QEvent.WhatsThis)):
            if not self._recall_tooltip_allowed(obj):
                QToolTip.hideText()
                return True

        if (self._recall_app_filter_active and self._recall_active
                and event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.LeftButton):
            if self._is_recall_ui_excluded_click(obj, event.globalPos()):
                return False
            if self._recall_awaiting_first_question or getattr(
                    self, "_recall_auto_starting", False):
                cmd_id, _, _ = self._recall_overlay_at(event.globalPos())
                if cmd_id is not None:
                    return True
                return False
            if not self._recall_question_answered:
                cmd_id, target, overlay = self._recall_overlay_at(
                    event.globalPos())
                if cmd_id is not None:
                    self._on_recall_click(
                        target or obj, cmd_id, overlay,
                        click_global=event.globalPos())
                    return True

        if obj is self._skip_learn_btn and self._recall_active:
            if event.type() == QEvent.MouseButtonPress:
                self._recall_input_blocked = True

        if obj.metaObject().className() == "QSplitterHandle":
            if event.type() in (
                    QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                    QEvent.MouseButtonDblClick):
                return True
            if (event.type() == QEvent.MouseMove
                    and event.buttons() & Qt.LeftButton):
                return True

        if (isinstance(obj, QWidget)
                and getattr(obj, "objectName", lambda: "")() == "bnAdd"
                and self._widget_in_docker(obj, "KisLayerBox")):
            if self._recall_active:
                return True
            if (event.type() == QEvent.MouseButtonRelease
                    and event.button() == Qt.LeftButton):
                if (self._learning_tracker is not None
                        and self._learning_tracker.active
                        and not self._recall_active):
                    self._learning_tracker.on_layer_event(
                        "layer_added", "Add layer")
                self._on_add_paint_layer()
                return True

        if getattr(obj, "objectName", lambda: "")() == "newFileLink":
            if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                if event.button() == Qt.LeftButton:
                    if event.type() == QEvent.MouseButtonRelease:
                        self._new_default()
                    return True

        # Keep main window pinned (no move / no resize).
        if self._win_locked and not self._geom_busy and self._qwin_alive() and obj is self._qwin:
            t = event.type()
            if t == QEvent.Move and self._fixed_pos is not None:
                if self._qwin.pos() != self._fixed_pos:
                    self._geom_busy = True
                    try:
                        self._qwin.move(self._fixed_pos)
                    finally:
                        self._geom_busy = False
                    return True
            elif t == QEvent.Resize and self._fixed_size is not None:
                if self._qwin.size() != self._fixed_size:
                    self._geom_busy = True
                    try:
                        self._qwin.setFixedSize(self._fixed_size)
                    finally:
                        self._geom_busy = False
                    return True
            elif t == QEvent.WindowStateChange:
                if self._qwin.isMaximized() or self._qwin.isFullScreen():
                    self._qwin.showNormal()
            elif t == QEvent.Close:
                if not self._quitting:
                    event.ignore()
                    QTimer.singleShot(0, lambda: self._request_quit(force=False))
                    return True
                event.accept()
                return False

        # Block welcome page during session 1 controlled flow.
        if (event.type() == QEvent.Show
                and self._in_session1_flow()
                and obj.metaObject().className() == "KisWelcomePageWidget"):
            QTimer.singleShot(0, lambda: self._force_canvas_if_needed(self._qwin))
            return True

        # Block any attempt to show a non-kept docker.
        if event.type() == QEvent.Show:
            try:
                allowed = self._visible_dockers()
                if isinstance(obj, QDockWidget):
                    name = obj.objectName()
                    if name == TEXT_PROPERTIES_DOCKER or name not in allowed:
                        obj.hide()
                        return True
                cls = obj.metaObject().className()
                if cls in BLOCKED_TEXT_WINDOW_CLASSES:
                    obj.hide()
                    return True
                if cls == "KXmlGuiWindow" and hasattr(obj, "windowTitle"):
                    if "Edit Text" in obj.windowTitle():
                        obj.hide()
                        return True
                if (isinstance(obj, QToolButton)
                        and self._widget_in_docker(obj, "ToolBox")
                        and not self._keep_toolbox_button(obj)):
                    obj.hide()
                    return True
                if (isinstance(obj, QToolButton)
                        and self._widget_in_docker(obj, "ToolBox")
                        and self._keep_toolbox_button(obj)
                        and self._study_uses_bottom_toolbox()):
                    obj.show()
                    obj.setEnabled(True)
                    dock = self._dock_by_name(self._qwin, "ToolBox")
                    if dock is not None:
                        QTimer.singleShot(
                            0, lambda d=dock: self._force_study_toolbox_visible(d))
                if obj.objectName() in HIDE_LAYER_WIDGETS and self._widget_in_docker(
                        obj, "KisLayerBox"):
                    obj.hide()
                    return True
            except Exception:
                pass
        return False

    def _widget_in_docker(self, widget, docker_name):
        if not isinstance(widget, QWidget):
            return False
        p = widget
        while p is not None:
            if isinstance(p, QDockWidget) and p.objectName() == docker_name:
                return True
            p = _widget_parent(p)
        return False

    def _layer_list_root(self, widget):
        if not isinstance(widget, QWidget):
            return None
        p = widget
        while p is not None:
            if getattr(p, "objectName", lambda: "")() == "listLayers":
                return p
            p = _widget_parent(p)
        return None

    def _is_layer_list_inline_icon_click(self, widget, event):
        """Block clicks on inline right-side layer row controls."""
        if event is None or not hasattr(event, "pos"):
            return False
        root = self._layer_list_root(widget)
        if root is None:
            return False
        if not self._widget_in_docker(root, "KisLayerBox"):
            return False
        x = int(event.pos().x())
        w = int(getattr(widget, "width", lambda: 0)())
        if w <= 0:
            return False
        return x >= max(0, w - LAYER_ROW_INLINE_ICON_ZONE_PX)

    def _keep_toolbox_button(self, btn):
        oid = btn.objectName() or ""
        if oid in KEEP_TOOLBOX_IDS:
            return True
        tip = (btn.toolTip() or "").lower()
        for needle in KEEP_TOOLBOX_TOOLTIP_NEEDLES:
            if needle in tip:
                return True
        return False

    def _trim_toolbox(self, qwin):
        for dock in qwin.findChildren(QDockWidget):
            if dock.objectName() != "ToolBox":
                continue
            for btn in dock.findChildren(QToolButton):
                if not self._keep_toolbox_button(btn):
                    btn.hide()
                    btn.setEnabled(False)
            if self._study_uses_bottom_toolbox():
                self._apply_horizontal_toolbox_row(dock, qwin)
            elif bool(self.session) and not self._quitting:
                self._apply_ordered_left_toolbox(dock, qwin)
        self._hook_toolbox_tool_tracking(qwin)

    def _find_preset_resource(self, stems):
        presets = Krita.instance().resources("preset")
        want = [self._normalize_preset_stem(s) for s in stems]
        for res in presets.values():
            fn = self._normalize_preset_stem(res.filename())
            if fn in want:
                return res
        for res in presets.values():
            fn = self._normalize_preset_stem(res.filename())
            for stem in want:
                if stem and (fn == stem or fn.endswith(stem) or stem in fn):
                    return res
        return None

    def _visible_dockers(self):
        return set(KEEP_DOCKERS)

    def _is_text_tool_active(self, qwin=None):
        try:
            root = None
            if qwin is not None and _qt_alive(qwin) and isinstance(qwin, QWidget):
                root = qwin
            elif self._qwin_alive():
                root = self._qwin
            if root is None:
                return False
            for dock in root.findChildren(QDockWidget):
                if dock.objectName() != "ToolBox":
                    continue
                for btn in dock.findChildren(QToolButton):
                    oid = btn.objectName() or ""
                    tip = (btn.toolTip() or "").lower()
                    if not btn.isChecked():
                        continue
                    if oid == "SvgTextTool" or "text tool" in tip:
                        return True
        except Exception:
            _log(traceback.format_exc())
        return False

    def _iter_text_shapes(self, doc):
        shapes = []

        def walk(node):
            if node is None:
                return
            if node.type() == "vectorlayer":
                try:
                    if not hasattr(node, "shapes"):
                        return
                    for shape in node.shapes():
                        try:
                            stype = shape.type()
                        except Exception:
                            continue
                        if stype == "KoSvgTextShapeID":
                            shapes.append((node, shape))
                except Exception:
                    _log("text shapes walk failed on %s: %s"
                         % (node.name(), traceback.format_exc()))
            for child in node.childNodes():
                walk(child)

        try:
            walk(doc.rootNode())
        except Exception:
            _log(traceback.format_exc())
        return shapes

    def _text_shape_height(self, shape):
        return float(shape.boundingBox().height())

    def _doc_svg_size_pt(self, doc):
        xres = max(float(doc.resolution()), 1.0)
        w_pt = float(doc.width()) * 72.0 / xres
        h_pt = float(doc.height()) * 72.0 / xres
        return w_pt, h_pt

    def _patch_text_svg(self, svg):
        """Only change font size/weight — keep the original transform untouched."""
        style_add = "font-size:%dpt;font-weight:bold" % STUDY_TEXT_HEIGHT_PT

        def patch_open_text_tag(match):
            tag = match.group(0)
            if 'style="' in tag:
                def repl_style(sm):
                    inner = sm.group(1)
                    inner = re.sub(r"font-size:\s*[^;\"]+;?", "", inner)
                    inner = re.sub(r"font-weight:\s*[^;\"]+;?", "", inner)
                    inner = inner.strip().strip(";")
                    if inner:
                        inner += ";"
                    inner += style_add
                    return 'style="%s"' % inner
                return re.sub(r'style="([^"]*)"', repl_style, tag, count=1)
            return tag[:-1] + ' style="%s">' % style_add

        return re.sub(r"<text\b[^>]*>", patch_open_text_tag, svg, count=1)

    def _align_shape_bbox_top_left(self, shape, target_tl):
        bb = shape.boundingBox()
        dx = float(target_tl.x()) - float(bb.x())
        dy = float(target_tl.y()) - float(bb.y())
        if abs(dx) < 0.05 and abs(dy) < 0.05:
            return
        pos = shape.position()
        shape.setPosition(QPointF(pos.x() + dx, pos.y() + dy))
        shape.update()

    def _wrap_svg_fragment(self, fragment, doc):
        w_pt, h_pt = self._doc_svg_size_pt(doc)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:krita="http://krita.org/namespaces/svg/krita" '
            'width="%.4fpt" height="%.4fpt" viewBox="0 0 %.4f %.4f">'
            % (w_pt, h_pt, w_pt, h_pt)
            + fragment + "</svg>")

    def _shape_pos_key(self, shape):
        bb = shape.boundingBox()
        return (round(bb.x(), 1), round(bb.y(), 1))

    def _text_needs_styling(self, shape):
        height = self._text_shape_height(shape)
        if height < STUDY_TEXT_MIN_HEIGHT_PT:
            return False
        return height < float(STUDY_TEXT_HEIGHT_PT) * 0.85

    def _style_text_shape(self, layer, shape):
        """Replace small text with 35pt bold at the same position."""
        if not self._text_needs_styling(shape):
            return False
        doc = Krita.instance().activeDocument()
        if doc is None:
            return False
        try:
            anchor_tl = shape.boundingBox().topLeft()
            saved_pos = shape.position()
            fragment = shape.toSvg(True)
            if not fragment or "<text" not in fragment:
                return False
            patched = self._patch_text_svg(fragment)
            wrapped = self._wrap_svg_fragment(patched, doc)
            if not shape.remove():
                return False
            added = layer.addShapesFromSvg(wrapped)
            if not added:
                return False
            new_shape = added[0]
            new_shape.setPosition(saved_pos)
            self._align_shape_bbox_top_left(new_shape, anchor_tl)
            new_shape.update()
            return True
        except Exception:
            _log(traceback.format_exc())
            return False

    def _schedule_study_text_style(self, delay_ms=None):
        self._text_idle_timer.start(
            delay_ms if delay_ms is not None else STUDY_TEXT_STYLE_DELAY_MS)

    def _apply_study_text_style(self):
        if self._text_style_busy:
            return
        doc = Krita.instance().activeDocument()
        if doc is None:
            return
        self._text_style_busy = True
        try:
            styled = 0
            for layer, shape in self._iter_text_shapes(doc):
                sid = id(shape)
                pos_key = self._shape_pos_key(shape)
                if sid in self._styled_text_shape_ids:
                    continue
                if pos_key in self._styled_text_positions:
                    continue
                if not self._text_needs_styling(shape):
                    continue
                if self._style_text_shape(layer, shape):
                    self._styled_text_shape_ids.add(sid)
                    self._styled_text_positions.add(pos_key)
                    styled += 1
            if styled:
                doc.refreshProjection()
                _log("study text replaced: %s shape(s) -> %spt bold"
                     % (styled, STUDY_TEXT_HEIGHT_PT))
        except Exception:
            _log(traceback.format_exc())
        finally:
            self._text_style_busy = False

    def _set_text_tool_polling(self, active):
        if not active:
            self._text_idle_timer.stop()

    def _update_text_tool_ui(self, qwin):
        if _qt_alive(qwin) and not self._is_welcome_visible(qwin):
            active = self._is_text_tool_active(qwin)
            self._text_tool_active = active
            self._set_text_tool_polling(active)

    def _ensure_text_app_filter(self):
        app = QApplication.instance()
        if app is not None and not self._text_app_filter_active:
            app.installEventFilter(self)
            self._text_app_filter_active = True

    def _on_text_tool_toggled(self, checked, qwin):
        self._update_text_tool_ui(qwin)
        if not checked:
            QTimer.singleShot(250, self._apply_study_text_style)

    def _hook_toolbox_tool_tracking(self, qwin):
        """Track Text tool (T) for auto-styling and blocking property windows."""
        try:
            self._ensure_text_app_filter()
            if not self._toolbox_hooks_done:
                act = Krita.instance().action("SvgTextTool")
                if act is not None:
                    act.triggered.connect(
                        lambda checked=False, q=qwin: QTimer.singleShot(
                            0, lambda: self._update_text_tool_ui(q)))
            for dock in qwin.findChildren(QDockWidget):
                if dock.objectName() != "ToolBox":
                    continue
                for btn in dock.findChildren(QToolButton):
                    if not self._keep_toolbox_button(btn):
                        continue
                    if btn.property("hideui_tool_track"):
                        continue
                    if btn.objectName() == "SvgTextTool":
                        btn.toggled.connect(
                            lambda checked, q=qwin: self._on_text_tool_toggled(
                                checked, q))
                    else:
                        btn.toggled.connect(
                            lambda checked, q=qwin: QTimer.singleShot(
                                0, lambda: self._update_text_tool_ui(q)))
                    btn.setProperty("hideui_tool_track", True)
            self._toolbox_hooks_done = True
            self._update_text_tool_ui(qwin)
            self._hook_study_brush_size_sync(qwin)
            tp = qwin.findChild(QDockWidget, TEXT_PROPERTIES_DOCKER)
            if tp is not None:
                tp.hide()
        except Exception:
            _log(traceback.format_exc())

    def _ensure_default_brush(self):
        """Paint brush tool + basic round preset (not eraser) on first canvas show."""
        try:
            k = Krita.instance()
            brush_action = k.action("KritaShape/KisToolBrush")
            if brush_action is not None:
                brush_action.trigger()
            win = k.activeWindow()
            if win is None or not win.views():
                return
            preset = self._find_preset_resource(DEFAULT_BRUSH_STEMS)
            if preset is not None:
                win.views()[0].activateResource(preset)
                _log("default brush: %s" % preset.name())
            self._schedule_study_brush_size_apply()
        except Exception:
            _log(traceback.format_exc())

    def _normalize_preset_stem(self, value):
        if not value:
            return ""
        stem = str(value).strip()
        if stem.lower().endswith(".kpp"):
            stem = stem[:-4]
        return stem.lower()

    def _preset_row_stem(self, model, row):
        idx = model.index(row, 0)
        for role in (_PRESET_ROLE_FILENAME, _PRESET_ROLE_NAME, Qt.DisplayRole, Qt.ToolTipRole):
            val = model.data(idx, role)
            stem = self._normalize_preset_stem(val)
            if stem:
                return stem
        return ""

    def _preset_recall_cmd_id(self, model, row):
        """Map a preset row to the canonical recall answer id (whitelist casing)."""
        stem = self._preset_row_stem(model, row)
        if not stem:
            return None
        for slot in BRUSH_PRESET_WHITELIST:
            for candidate in slot:
                if self._normalize_preset_stem(candidate) == stem:
                    return "preset:%s" % slot[0]
        return "preset:%s" % stem

    def _reset_brush_preset_filter(self, root):
        """Show all presets — kritarc may still have the Erasers tag selected."""
        if root is None:
            return
        for w in root.findChildren(QWidget):
            cls = w.metaObject().className()
            if cls == "KisTagFilterWidget":
                try:
                    w.clear()
                except Exception:
                    pass
            elif cls == "KisTagChooserWidget":
                try:
                    w.setCurrentItem("All")
                except Exception:
                    pass
            elif cls == "KisResourceItemChooser":
                try:
                    tag_model = w.tagFilterModel()
                    if tag_model is not None:
                        tag_model.setFilterInCurrentTag(False)
                        tag_model.setSearchText("")
                except Exception:
                    pass

    def _pick_brush_preset_rows(self, model):
        rows = model.rowCount()
        by_stem = {}
        for row in range(rows):
            stem = self._preset_row_stem(model, row)
            if stem and stem not in by_stem:
                by_stem[stem] = row
        keep = []
        for slot in BRUSH_PRESET_WHITELIST:
            found = None
            for candidate in slot:
                key = self._normalize_preset_stem(candidate)
                if key in by_stem:
                    found = by_stem[key]
                    break
            if found is not None:
                keep.append(found)
        return keep

    def _trim_brush_presets(self, qwin):
        roots = []
        dock = self._dock_by_name(qwin, "PresetDocker")
        if dock is not None:
            roots.append(dock)
        popup = self._preset_popup_widget
        if popup is not None and popup not in roots:
            roots.append(popup)
        if not roots:
            found = self._find_preset_popup_widget(qwin)
            if found is not None:
                self._preset_popup_widget = found
                roots.append(found)
        for root in roots:
            if root is None or not _qt_alive(root):
                continue
            self._reset_brush_preset_filter(root)
            self._trim_preset_chooser_extras(root)
            self._ensure_preset_chooser_visible(root)
            for chooser in root.findChildren(QWidget):
                if chooser.metaObject().className() != "KisResourceItemChooser":
                    continue
                for view in chooser.findChildren(QAbstractItemView):
                    model = view.model()
                    if model is None:
                        continue
                    rows = model.rowCount()
                    if rows <= 0:
                        continue
                    keep_rows = self._pick_brush_preset_rows(model)
                    if not keep_rows:
                        _log("brush presets: no whitelist match (%d rows visible)" % rows)
                        continue
                    keep_set = set(keep_rows)
                    for row in range(rows):
                        view.setRowHidden(row, row not in keep_set)
                    for row in keep_rows:
                        view.setRowHidden(row, False)
                    view.show()
                    chooser.show()
                    self._apply_preset_icon_metrics(root)
                    names = [self._preset_row_stem(model, r) for r in keep_rows]
                    _log("brush presets: showing %s" % names)
        self._hook_study_brush_size_on_presets(qwin)
        self._fix_preset_gap(qwin)
        if not getattr(self, "_brush_preset_keepalive_armed", False):
            self._brush_preset_keepalive_armed = True
            for delay in (200, 600, 1500, 3000):
                QTimer.singleShot(
                    delay,
                    lambda q=qwin: self._keep_brush_presets_visible(q))

    def _keep_brush_presets_visible(self, qwin):
        """Re-apply whitelist and icon metrics after delayed layout changes."""
        if self._quitting or not _qt_alive(qwin):
            self._brush_preset_keepalive_armed = False
            return
        if not (self._tutorial_active or self._recall_active):
            self._brush_preset_keepalive_armed = False
            return
        try:
            from .layout_profiles import profile_flags
            profile = getattr(self, "_study_layout_profile", "A")
            if profile_flags(profile).get("presets_in_toolbar"):
                self._ensure_toolbar_presets_visible(qwin)
            self._brush_preset_keepalive_armed = True
            roots = []
            dock = self._dock_by_name(qwin, "PresetDocker")
            if dock is not None:
                roots.append(dock)
            popup = self._preset_popup_widget or self._find_preset_popup_widget(qwin)
            if popup is not None and popup not in roots:
                self._preset_popup_widget = popup
                roots.append(popup)
            for root in roots:
                if root is None or not _qt_alive(root):
                    continue
                self._reset_brush_preset_filter(root)
                self._ensure_preset_chooser_visible(root)
                for chooser in root.findChildren(QWidget):
                    if chooser.metaObject().className() != "KisResourceItemChooser":
                        continue
                    for view in chooser.findChildren(QAbstractItemView):
                        model = view.model()
                        if model is None or model.rowCount() <= 0:
                            continue
                        keep_rows = self._pick_brush_preset_rows(model)
                        if not keep_rows:
                            continue
                        keep_set = set(keep_rows)
                        for row in range(model.rowCount()):
                            view.setRowHidden(row, row not in keep_set)
                        for row in keep_rows:
                            view.setRowHidden(row, False)
                        view.show()
                        self._apply_preset_icon_metrics(root)
        except Exception:
            _log(traceback.format_exc())
        finally:
            self._brush_preset_keepalive_armed = False

    def _on_add_paint_layer(self):
        """Add a paint layer via the Python API (reliable when bnAdd menu is stripped)."""
        try:
            k = Krita.instance()
            doc = k.activeDocument()
            if doc is None:
                _log("add layer: no active document")
                return False
            root = doc.rootNode()
            active = doc.activeNode()
            layer = doc.createNode("Paint Layer", "paintlayer")
            if layer is None:
                _log("add layer: createNode failed")
                return False
            if active is not None:
                parent = active.parentNode() or root
                parent.addChildNode(layer, active)
            else:
                root.addChildNode(layer, None)
            doc.setActiveNode(layer)
            doc.refreshProjection()
            _log("add layer: created '%s'" % layer.name())
            return True
        except Exception:
            _log("add layer api failed:\n%s" % traceback.format_exc())
        try:
            act = Krita.instance().action("add_new_paint_layer")
            if act is not None:
                act.trigger()
                _log("add layer: fell back to action trigger")
                return True
        except Exception:
            _log(traceback.format_exc())
        return False

    def _wire_layer_add_button(self, dock):
        bn_add = dock.findChild(QWidget, "bnAdd")
        if bn_add is None:
            return
        if not bn_add.property("hideui_add_filter"):
            bn_add.installEventFilter(self)
            bn_add.setProperty("hideui_add_filter", True)
        bn_add.show()
        bn_add.setEnabled(True)

    def _configure_layers_panel(self, qwin):
        """Hide extra layer docker controls — widget hide only, no overlays."""
        try:
            dock = qwin.findChild(QDockWidget, "KisLayerBox")
            if dock is None:
                return
            for old in dock.findChildren(QWidget, "hideuiLayerIconCover"):
                old.setParent(None)
                old.deleteLater()
            for name in HIDE_LAYER_WIDGETS:
                w = dock.findChild(QWidget, name)
                if w is not None:
                    w.hide()
            for name in HIDE_BY_OBJNAME:
                if name in KEEP_LAYER_WIDGETS:
                    continue
                w = dock.findChild(QWidget, name)
                if w is not None:
                    w.hide()
            bn_add = dock.findChild(QWidget, "bnAdd")
            if bn_add is not None:
                self._wire_layer_add_button(dock)
            self._apply_dock_title(dock)
            layer_tree = dock.findChild(QWidget, "listLayers")
            if layer_tree is not None and not layer_tree.property("hideui_list_filter"):
                layer_tree.installEventFilter(self)
                layer_tree.setProperty("hideui_list_filter", True)
            if layer_tree is not None:
                viewport = getattr(layer_tree, "viewport", lambda: None)()
                if viewport is not None and not viewport.property("hideui_list_filter"):
                    viewport.installEventFilter(self)
                    viewport.setProperty("hideui_list_filter", True)
        except Exception:
            _log(traceback.format_exc())

    def _trim_layers_panel(self, qwin):
        for dock in qwin.findChildren(QDockWidget):
            if dock.objectName() != "KisLayerBox":
                continue
            for w in dock.findChildren(QWidget):
                obj = w.objectName()
                if obj in HIDE_LAYER_WIDGETS or obj in HIDE_BY_OBJNAME:
                    w.hide()
                elif obj and obj not in KEEP_LAYER_WIDGETS:
                    if isinstance(w, QAbstractButton):
                        w.hide()
            bn_add = dock.findChild(QWidget, "bnAdd")
            if bn_add is not None:
                bn_add.show()
                bn_add.setEnabled(True)
        self._configure_layers_panel(qwin)

    def _trim_color_selector(self, qwin):
        for dock in qwin.findChildren(QDockWidget):
            if dock.objectName() != "ColorSelectorNg":
                continue
            self._apply_dock_title(dock)
            for w in dock.findChildren(QWidget):
                if w.metaObject().className() in HIDE_COLOR_SELECTOR_CLASSES:
                    w.hide()

    def _trim_panel_commands(self, qwin):
        try:
            self._trim_toolbox(qwin)
            self._trim_brush_presets(qwin)
            self._trim_layers_panel(qwin)
            self._trim_color_selector(qwin)
            _log("panel commands trimmed to study set")
        except Exception:
            _log(traceback.format_exc())

    def _hide_extras(self, qwin):
        if self._extras_hidden:
            return
        # Scope the panel-widget hiding to the kept dockers only, so we never
        # accidentally hit similar widgets elsewhere in the UI.
        for dock in qwin.findChildren(QDockWidget):
            if dock.objectName() not in KEEP_DOCKERS:
                continue
            self._trim_preset_chooser_extras(dock)
            for w in dock.findChildren(QWidget):
                cls = w.metaObject().className()
                obj = w.objectName()
                if cls in HIDE_BY_CLASS:
                    w.hide()
                elif obj in HIDE_BY_OBJNAME:
                    w.hide()
                elif w.toolTip() in HIDE_BY_TOOLTIP:
                    w.hide()

            # Hide the settings button overlaid on the color wheel and the
            # clear-history / reload buttons in the color selector.
            for w in dock.findChildren(QWidget):
                if w.metaObject().className() in (
                        "KisColorSelector", "KisColorHistory", "KisCommonColors"):
                    for btn in w.findChildren(QToolButton):
                        btn.hide()

        # Brush Presets panel: after hiding the tag/filter/import rows, the
        # grid stays pinned to the bottom with a big empty gap above it. Force
        # the grid's QGridLayout so the only stretching row is the grid row.
        self._fix_preset_gap(qwin)
        self._trim_panel_commands(qwin)
        self._extras_hidden = True

    def _schedule_preset_gap_fix(self, qwin):
        """Re-apply preset docker compaction after Krita relayouts the chooser."""
        if not _qt_alive(qwin):
            return
        for delay in (0, 50, 150, 400, 800, 1500, 3000):
            QTimer.singleShot(
                delay, lambda q=qwin: self._fix_preset_gap(q))

    def _fix_preset_chooser_layout(self, chooser):
        """Remove dead space above the brush grid inside one KisResourceItemChooser."""
        if chooser is None or not _qt_alive(chooser):
            return
        chooser.setContentsMargins(0, 0, 0, 0)
        lay = chooser.layout()
        try:
            from PyQt5 import sip
            lay = sip.cast(lay, QGridLayout)
        except Exception:
            pass
        if isinstance(lay, QGridLayout):
            for r in range(lay.rowCount()):
                lay.setRowStretch(r, 0)
                lay.setRowMinimumHeight(r, 0)
            # Row 1 holds the resources splitter (the preset grid).
            if lay.rowCount() > 1:
                lay.setRowStretch(1, 1)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setVerticalSpacing(0)
            lay.setHorizontalSpacing(0)
        for sp in chooser.findChildren(QSplitter):
            sp.setHandleWidth(0)
            if sp.count() >= 2:
                preview = sp.widget(1)
                if preview is not None:
                    preview.hide()
                    preview.setFixedSize(0, 0)
                sp.setSizes([100000, 0])
        for view in chooser.findChildren(QAbstractItemView):
            view.setContentsMargins(0, 0, 0, 0)

    def _fix_preset_gap(self, qwin):
        """Layout A docker: collapse empty rows above the brush preset grid."""
        if not _qt_alive(qwin):
            return
        try:
            roots = []
            dock = self._dock_by_name(qwin, "PresetDocker")
            if dock is not None and not self._presets_in_toolbar:
                roots.append(dock)
                dock.setContentsMargins(0, 0, 0, 0)
                content = dock.widget()
                if content is not None and content is not self._preset_dock_placeholder:
                    content.setContentsMargins(0, 0, 0, 0)
                    content.setSizePolicy(
                        QSizePolicy.Preferred, QSizePolicy.Preferred)
                    outer = content.layout()
                    if outer is not None:
                        outer.setContentsMargins(0, 0, 0, 0)
                        outer.setSpacing(0)
            for root in roots:
                for chooser in root.findChildren(QWidget):
                    if chooser.metaObject().className() != "KisResourceItemChooser":
                        continue
                    self._fix_preset_chooser_layout(chooser)
        except Exception:
            _log(traceback.format_exc())

    def _clean_welcome(self, qwin):
        # Hide the Community links and News column on the welcome page.
        try:
            for w in qwin.findChildren(QWidget):
                if w.objectName() in WELCOME_HIDE:
                    w.hide()
        except Exception:
            _log(traceback.format_exc())

    def _apply(self, qwin):
        if self._quitting or not _qt_alive(qwin):
            return
        if self._ui_applied:
            return
        if self._in_session1_flow() and self._is_welcome_visible(qwin):
            QTimer.singleShot(0, lambda: self._force_canvas_if_needed(qwin))
            return
        try:
            self._clean_welcome(qwin)
            sb = qwin.statusBar()
            if sb is not None:
                sb.setVisible(False)
                sb.setMaximumHeight(0)

            for dock in qwin.findChildren(QDockWidget):
                name = dock.objectName()
                if name in KEEP_DOCKERS:
                    self._apply_dock_title(dock)
                else:
                    dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
                    dock.hide()
                    # Install the event filter once per docker so Krita can
                    # never re-show it (e.g. Tool Options on tool switch).
                    if name not in self._filtered:
                        dock.installEventFilter(self)
                        self._filtered.add(name)

            self._hide_extras(qwin)
            if not self._is_session1():
                self._schedule_study_layout_refresh(qwin)
            else:
                self._lock_dock_panels_layout_a(qwin)
            if qwin.isVisible() or getattr(self, "_polish_reveal_active", False):
                self._ensure_study_chrome(qwin)
                self._show_study_toolbars(qwin)
                self._hide_document_chrome(qwin)
                self._configure_native_brush_slider(qwin)
            self._schedule_ui_polish(qwin)
            self._update_content_zone(qwin)
            self._suppress_canvas_floating_messages(qwin)
        except Exception:
            _log(traceback.format_exc())
