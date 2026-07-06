import json
import os
import subprocess
import traceback

from PyQt5.QtCore import Qt, QProcess, QTimer, QSize, QThread, pyqtSignal, pyqtSlot, QEventLoop, QUrl
from PyQt5.QtGui import QImage, QPixmap, QIcon, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QScrollArea, QTextEdit, QSizePolicy)

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(PLUGIN_DIR, "media")
ICONS_DIR = os.path.join(PLUGIN_DIR, "icons")
CONTROLS_H = 52
LOG = os.path.expanduser("~/krita_hide_ui_log.txt")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
INTRO_CONTINUE_UNLOCK_SEC = 60

_PANEL = None
_SHUTTING_DOWN = False
_SESSION = None
_VIDEO_PATH = None


def _log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass


def _kill_stale_mpv():
    """Stop orphan mpv windows from the old broken backend."""
    try:
        subprocess.run(
            ["pkill", "-f", "krita_hideui_mpv"],
            capture_output=True, timeout=2)
    except Exception:
        pass


def get_video_panel():
    global _PANEL, _SHUTTING_DOWN
    if _SHUTTING_DOWN:
        return None
    if _PANEL is None:
        _kill_stale_mpv()
        _PANEL = VideoPanelWindow()
        _log("video panel: created singleton (ffmpeg backend)")
    return _PANEL


def reset_video_state():
    global _SHUTTING_DOWN, _SESSION, _VIDEO_PATH
    _SHUTTING_DOWN = False
    _SESSION = None
    _VIDEO_PATH = None


def configure_video_for_tutorial(session_info, learn_num):
    """Pick tutorial video by learning phase (session 1 → 1–3, session 2 → 4–6)."""
    global _SESSION, _VIDEO_PATH, _PANEL
    _SESSION = dict(session_info) if session_info else None
    session_num = (_SESSION or {}).get("session", 1)
    _VIDEO_PATH = _resolve_tutorial_video_path(session_num, learn_num)
    if _VIDEO_PATH:
        _log("video: session %s tutorial %s -> %s" % (
            _session_label(_SESSION), learn_num, os.path.basename(_VIDEO_PATH)))
    else:
        _log("video: no tutorial file for session %s learn %s" % (
            session_num, learn_num))
        _VIDEO_PATH = _resolve_video_path(_SESSION)
    if _PANEL is not None:
        _PANEL.set_video_path(_VIDEO_PATH)


def configure_video_session(session_info, video_override=None):
    """Pick the tutorial video for this login (condition + session)."""
    global _SESSION, _VIDEO_PATH, _PANEL
    _SESSION = dict(session_info) if session_info else None
    _VIDEO_PATH = None
    if video_override:
        for d in (MEDIA_DIR, PLUGIN_DIR):
            path = os.path.join(d, video_override)
            if _is_video_file(path):
                _VIDEO_PATH = os.path.abspath(path)
                break
    if not _VIDEO_PATH:
        _VIDEO_PATH = _resolve_video_path(_SESSION)
    if _VIDEO_PATH:
        _log("video: session %s -> %s" % (
            _session_label(_SESSION), os.path.basename(_VIDEO_PATH)))
    else:
        _log("video: no file for session %s" % _session_label(_SESSION))
    if _PANEL is not None:
        _PANEL.set_video_path(_VIDEO_PATH)


def _session_label(session_info):
    if not session_info:
        return "?"
    return "%s-%s" % (session_info.get("session"), session_info.get("condition"))


def _load_video_manifest():
    path = os.path.join(MEDIA_DIR, "videos.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _tutorial_video_phase(session_num, learn_num):
    """Global tutorial index: session 1 L1–3 → 1–3; session 2 L1–3 → 4–6."""
    return (max(1, int(session_num)) - 1) * 3 + max(1, int(learn_num))


def _resolve_tutorial_video_path(session_num, learn_num):
    phase = _tutorial_video_phase(session_num, learn_num)
    names = [
        "tutorial %d.mov" % phase,
        "tutorial%d.mov" % phase,
        "tutorial_%d.mov" % phase,
        "Tutorial %d.mov" % phase,
        "tutorial %d.mp4" % phase,
        "tutorial%d.mp4" % phase,
    ]
    manifest = _load_video_manifest()
    key = "tutorial%d" % phase
    entry = manifest.get(key)
    if entry:
        names.insert(0, str(entry))
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        for d in (MEDIA_DIR, PLUGIN_DIR):
            path = os.path.join(d, name)
            if _is_video_file(path):
                return os.path.abspath(path)
    for d in (MEDIA_DIR, PLUGIN_DIR):
        if not os.path.isdir(d):
            continue
        token = str(phase)
        for fname in sorted(os.listdir(d)):
            path = os.path.join(d, fname)
            if not _is_video_file(path):
                continue
            lower = fname.lower()
            if "tutorial" in lower and token in lower.replace("_", " "):
                return os.path.abspath(path)
    return None


def _is_video_file(path):
    return os.path.isfile(path) and path.lower().endswith(VIDEO_EXTS)


def _candidate_names(session_info):
    """Names to try, in order — supports arbitrary names via videos.json."""
    names = []
    manifest = _load_video_manifest()
    if session_info:
        s = session_info.get("session")
        c = session_info.get("condition")
        keys = (
            "%s-%s" % (s, c),
            "%s-%s" % (c, s),
            "session%s" % s,
            "video%s" % s,
        )
        for key in keys:
            entry = manifest.get(key)
            if entry:
                names.append(str(entry))
        names += [
            "%s-%s.mp4" % (s, c),
            "%s-%s.mov" % (c, s),
            "%s-%s.mp4" % (c, s),
            "session%s.mp4" % s,
            "video%s.mp4" % s,
            "video%s.mov" % s,
        ]
    default = manifest.get("default")
    if default:
        names.append(str(default))
    names += ["default.mp4", "video.mp4", "video1.mp4"]
    # de-dupe while preserving order
    seen = set()
    out = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _single_video_fallback():
    found = []
    for d in (MEDIA_DIR, PLUGIN_DIR):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            path = os.path.join(d, name)
            if _is_video_file(path):
                found.append(os.path.abspath(path))
    if len(found) == 1:
        return found[0]
    return None


def resolve_krita_intro_video_path():
    """Video shown once before Session 1 Tutorial 1 learning phase."""
    names = []
    manifest = _load_video_manifest()
    for key in ("krita_intro", "intro", "environment"):
        entry = manifest.get(key)
        if entry:
            names.append(str(entry))
    names += [
        "krita intro.mov",
        "krita intro.mp4",
        "intro.mov",
        "intro.mp4",
        "environment.mov",
        "tutorial 1.mp4",
        "tutorial 1.mov",
    ]
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        for d in (MEDIA_DIR, PLUGIN_DIR):
            path = os.path.join(d, name)
            if _is_video_file(path):
                return os.path.abspath(path)
    return _resolve_tutorial_video_path(1, 1)


class KritaIntroWindow(QWidget):
    """Full-screen Krita environment intro with playback controls."""

    def __init__(self, video_path):
        super().__init__(None)
        from .session_flow import STUDY_PRESENTATION
        from .experiment import _WINDOW_FLAGS, suppress_krita_ui
        self.setWindowTitle("Welcome to Krita")
        self.setWindowFlags(_WINDOW_FLAGS)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setStyleSheet("""
            QWidget { background-color: #2b2b2b; color: #e0e0e0; }
            QPushButton#introContinueBtn {
                background-color: #4a6fa5; color: white;
                border: none; padding: 10px 24px; min-width: 120px;
            }
            QPushButton#introContinueBtn:hover { background-color: #5a7fb5; }
            QPushButton#introContinueBtn:disabled {
                background-color: #444; color: #aaa;
            }
            QPushButton#introPlayBtn {
                background: transparent; border: none;
                padding: 0; margin: 0; min-width: 0; max-width: 28px;
            }
        """)
        self._loop = None
        self._result = None
        self._duration_sec = 0.0
        self._continue_enabled = False
        self._unlock_remaining_sec = 0
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_continue_countdown)
        self._video_path = video_path
        self._ffmpeg = None
        self._intro_controls = None
        self._probe_worker = None

        heading = QLabel("Welcome to Krita")
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet(
            "color: #ffffff; font-size: 24px; font-weight: bold; padding: 8px;")

        presentation = QLabel(STUDY_PRESENTATION)
        presentation.setWordWrap(True)
        presentation.setAlignment(Qt.AlignCenter)
        presentation.setMaximumWidth(680)
        presentation.setStyleSheet(
            "color: #b8b8b8; font-size: 13px; padding: 0 24px;")

        self._video_frame = QWidget()
        self._video_frame.setMinimumSize(720, 405)
        self._video_frame.setStyleSheet("background-color: #000;")
        frame_lay = QVBoxLayout(self._video_frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        self._loading = QLabel("Loading video…")
        self._loading.setAlignment(Qt.AlignCenter)
        self._loading.setStyleSheet("color: #ddd; font-size: 14px;")
        frame_lay.addWidget(self._loading)

        self._controls_row = QWidget()
        self._controls_row.setFixedWidth(720)
        self._controls_row.hide()
        controls_lay = QHBoxLayout(self._controls_row)
        controls_lay.setContentsMargins(0, 0, 0, 0)

        self._continue_btn = QPushButton("Continue")
        self._continue_btn.setDefault(True)
        self._continue_btn.setEnabled(False)
        self._continue_btn.setObjectName("introContinueBtn")
        self._continue_btn.clicked.connect(lambda: self._finish(True))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 24)
        lay.setSpacing(12)
        lay.addWidget(heading)
        lay.addWidget(presentation)
        lay.addWidget(self._video_frame, 1, Qt.AlignCenter)
        lay.addWidget(self._controls_row, 0, Qt.AlignCenter)
        lay.addWidget(self._continue_btn, 0, Qt.AlignCenter)
        self.setMinimumSize(820, 640)
        self._suppress = suppress_krita_ui

    def _toggle_playback(self):
        if not self._ffmpeg:
            return
        if self._ffmpeg._paused:
            self._ffmpeg.resume()
            if self._intro_controls:
                self._intro_controls.set_paused(False)
        else:
            self._ffmpeg.pause()
            if self._intro_controls:
                self._intro_controls.set_paused(True)

    def seek_to_sec(self, sec):
        if self._ffmpeg:
            self._ffmpeg.seek(sec)

    def _finish(self, result):
        self._result = result
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()
        if self._ffmpeg:
            self._ffmpeg.stop()
        self.hide()
        if self._loop is not None:
            self._loop.quit()

    def closeEvent(self, event):
        self._finish(None)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def _center_on_screen(self):
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2)

    def _update_continue_label(self):
        if self._continue_enabled:
            self._continue_btn.setText("Continue")
            return
        sec = max(0, int(self._unlock_remaining_sec))
        self._continue_btn.setText("Continue (%s)" % _fmt_time(sec))

    def _tick_continue_countdown(self):
        if self._continue_enabled:
            self._countdown_timer.stop()
            return
        self._unlock_remaining_sec = max(0, self._unlock_remaining_sec - 1)
        self._update_continue_label()
        if self._unlock_remaining_sec <= 0:
            self._countdown_timer.stop()
            self._enable_continue()

    def _enable_continue(self):
        if self._continue_enabled:
            return
        self._continue_enabled = True
        self._countdown_timer.stop()
        self._continue_btn.setEnabled(True)
        self._continue_btn.setText("Continue")
        _log("krita intro: continue unlocked after %ss" % int(self._duration_sec))

    def _on_position_changed(self, pos):
        if self._intro_controls:
            self._intro_controls.set_position_sec(pos)
        unlock_at = min(
            float(self._duration_sec),
            float(INTRO_CONTINUE_UNLOCK_SEC))
        if unlock_at > 0 and pos >= max(0.0, unlock_at - 0.75):
            self._enable_continue()

    def _start_video(self):
        ffprobe = _find_tool("ffprobe")
        ffmpeg = _find_tool("ffmpeg")
        if not ffmpeg or not ffprobe:
            self._loading.setText("Video playback is unavailable.")
            self._enable_continue()
            return
        self._ffmpeg = _FfmpegVideoWidget(self._video_frame)
        self._ffmpeg.set_loop(False)
        self._ffmpeg.position_changed.connect(self._on_position_changed)
        self._ffmpeg.begin(self._video_path, out_w=720)
        frame_lay = self._video_frame.layout()
        frame_lay.removeWidget(self._loading)
        self._loading.hide()
        frame_lay.addWidget(self._ffmpeg, 1)
        self._intro_controls = _YoutubeControls(
            self, transparent=True, compact=True)
        row_lay = self._controls_row.layout()
        row_lay.addWidget(self._intro_controls)
        self._controls_row.show()
        self._probe_worker = _ProbeWorker(self._video_path, ffprobe)
        self._probe_worker.done.connect(self._on_probe_done)
        self._probe_worker.failed.connect(self._on_probe_failed)
        self._probe_worker.start()

    def _on_probe_done(self, src_w, src_h, fps, duration, nb_frames):
        if not self._ffmpeg:
            return
        self._ffmpeg.apply_probe(src_w, src_h, fps, duration, nb_frames)
        self._duration_sec = max(1.0, float(duration))
        self._unlock_remaining_sec = max(
            1,
            min(INTRO_CONTINUE_UNLOCK_SEC, int(round(self._duration_sec))))
        self._update_continue_label()
        c = self._intro_controls
        c.set_duration_sec(self._duration_sec)
        c.set_position_sec(0.0)
        c.set_paused(False)
        self._ffmpeg.play()
        self._countdown_timer.start()
        _log("krita intro: %.1fs video, continue unlock in %ss" % (
            self._duration_sec, self._unlock_remaining_sec))

    def _on_probe_failed(self, err):
        _log("krita intro probe failed: %s" % err)
        self._loading.setText("Could not load the introduction video.")
        self._enable_continue()

    def run_blocking(self):
        self._loop = QEventLoop()
        guard = QTimer()
        guard.setInterval(100)
        guard.timeout.connect(lambda: self._suppress(self))
        guard.start()
        self._center_on_screen()
        self._suppress(self)
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self._start_video)
        self._loop.exec_()
        guard.stop()
        self._loop = None
        return self._result


def run_krita_environment_intro():
    """Show the Krita workspace intro before Tutorial 1. Returns True to continue."""
    path = resolve_krita_intro_video_path()
    if not path:
        _log("krita intro: no video file found, skipping")
        return True
    try:
        win = KritaIntroWindow(path)
        from .experiment import suppress_krita_ui
        suppress_krita_ui(win)
        return win.run_blocking() is True
    except Exception:
        _log(traceback.format_exc())
        return False


def _resolve_video_path(session_info=None):
    if _VIDEO_PATH and os.path.isfile(_VIDEO_PATH):
        return _VIDEO_PATH
    for name in _candidate_names(session_info):
        for d in (MEDIA_DIR, PLUGIN_DIR):
            path = os.path.join(d, name)
            if _is_video_file(path):
                return os.path.abspath(path)
    only = _single_video_fallback()
    if only:
        _log("video: using only file in media/: %s" % os.path.basename(only))
        return only
    return None


def shutdown_all_video():
    global _PANEL, _SHUTTING_DOWN
    _SHUTTING_DOWN = True
    _kill_stale_mpv()
    if _PANEL is not None:
        try:
            _PANEL.destroy()
        except Exception:
            pass
    for w in QApplication.topLevelWidgets():
        if w.objectName() in ("hideui_video_panel", "hideui_video_shield"):
            try:
                w.hide()
                w.close()
            except Exception:
                pass
    _PANEL = None
    try:
        QApplication.processEvents()
    except Exception:
        pass
    _log("video panel: shutdown_all_video")


def suspend_playback_for_phase_change():
    """Pause ffmpeg and hide the panel without destroying it."""
    global _PANEL
    _kill_stale_mpv()
    if _PANEL is not None:
        try:
            _PANEL.hide_panel()
        except Exception:
            pass
    try:
        QApplication.processEvents()
    except Exception:
        pass
    _log("video panel: suspended for phase change")


def _find_tool(name):
    # Prefer the shell wrapper — it sets DYLD_LIBRARY_PATH for bundled .real binaries.
    for path in (
        os.path.join(PLUGIN_DIR, "bin", name),
        os.path.join(PLUGIN_DIR, "bin", name + ".real"),
        "/opt/homebrew/bin/%s" % name,
        "/usr/local/bin/%s" % name,
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _fmt_time(sec):
    sec = max(0, int(sec))
    m, s = divmod(sec, 60)
    return "%d:%02d" % (m, s)


def _svg_icon(name, size=28):
    path = os.path.join(ICONS_DIR, name)
    if not os.path.isfile(path):
        return QIcon()
    renderer = QSvgRenderer(path)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)


def _parse_fps(stream):
    raw = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1"
    if "/" in str(raw):
        num, den = str(raw).split("/", 1)
        try:
            den_f = float(den)
            if den_f > 0:
                return max(1.0, float(num) / den_f)
        except ValueError:
            pass
    try:
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return 30.0


class _YoutubeControls(QWidget):
    def __init__(self, panel, parent=None, transparent=False, compact=False):
        super().__init__(parent)
        self._panel = panel
        if transparent:
            self.setStyleSheet("background-color: transparent;")
        else:
            self.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        lay = QHBoxLayout(self)
        if compact:
            lay.setContentsMargins(0, 4, 0, 4)
        else:
            lay.setContentsMargins(10, 8, 12, 8)
        lay.setSpacing(8)

        btn_size = 28 if compact else 36
        icon_size = 20 if compact else 28
        self._play_btn = QPushButton()
        self._play_btn.setFixedSize(btn_size, btn_size)
        self._play_btn.setMaximumSize(btn_size, btn_size)
        self._play_btn.setFlat(True)
        self._play_btn.setIconSize(QSize(icon_size, icon_size))
        self._play_btn.setSizePolicy(
            QSizePolicy.Fixed, QSizePolicy.Fixed)
        if compact:
            self._play_btn.setObjectName("introPlayBtn")
            self._play_btn.setStyleSheet(
                "background: transparent; border: none; padding: 0; margin: 0;")
        else:
            btn_style = "QPushButton { background: transparent; border: none; }"
            if not transparent:
                btn_style += (
                    "QPushButton:hover { background: rgba(255,255,255,30);"
                    " border-radius: 18px; }")
            self._play_btn.setStyleSheet(btn_style)
        self._play_btn.clicked.connect(panel._toggle_playback)
        lay.addWidget(self._play_btn, 0, Qt.AlignVCenter)

        self._time = QLabel("0:00")
        self._time.setStyleSheet("color: #eee; font-size: 12px; min-width: 36px;")
        lay.addWidget(self._time)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,40);"
            "  border-radius: 2px; }"
            "QSlider::sub-page:horizontal { background: #ff0000; border-radius: 2px; }"
            "QSlider::add-page:horizontal { background: rgba(255,255,255,40); border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;"
            "  background: #ff0000; border-radius: 7px; }")
        self._slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self._slider.sliderReleased.connect(self._on_seek_end)
        lay.addWidget(self._slider, 1)

        self._duration = QLabel("0:00")
        self._duration.setStyleSheet("color: #eee; font-size: 12px; min-width: 36px;")
        lay.addWidget(self._duration)
        self._seeking = False
        self._duration_sec = 0.0
        self._set_playing(True)

    def _set_playing(self, playing):
        self._play_btn.setIcon(_svg_icon("pause.svg" if playing else "play.svg"))

    def _on_seek_end(self):
        self._seeking = False
        self._panel.seek_to_sec(self._slider.value() / 1000.0)

    def set_duration_sec(self, sec):
        sec = max(0.0, float(sec))
        self._duration_sec = sec
        self._duration.setText(_fmt_time(sec))
        self._slider.setRange(0, max(1, int(sec * 1000)))

    def set_position_sec(self, sec):
        if self._seeking:
            return
        sec = max(0.0, min(self._duration_sec, float(sec)))
        self._slider.blockSignals(True)
        self._slider.setValue(int(sec * 1000))
        self._slider.blockSignals(False)
        self._time.setText(_fmt_time(sec))

    def set_position_frac(self, frac):
        if self._duration_sec > 0:
            self.set_position_sec(frac * self._duration_sec)

    def set_time_sec(self, sec):
        self._time.setText(_fmt_time(sec))

    def set_paused(self, paused):
        self._set_playing(not paused)


class _VideoHost(QWidget):
    def __init__(self, panel, transparent_controls=False):
        super().__init__()
        self._panel = panel
        self._video = None
        self._controls = _YoutubeControls(
            panel, self, transparent=transparent_controls)

    def set_video(self, widget):
        self._video = widget
        widget.setParent(self)
        widget.show()
        self._controls.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        if self._video is not None:
            self._video.setGeometry(0, 0, w, h)
        self._controls.setGeometry(0, h - CONTROLS_H, w, CONTROLS_H)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._controls.geometry().contains(event.pos()):
                self._panel._toggle_playback()
        super().mousePressEvent(event)


class _ProbeWorker(QThread):
    done = pyqtSignal(int, int, float, float, int)
    failed = pyqtSignal(str)

    def __init__(self, path, ffprobe):
        super().__init__()
        self._path = path
        self._ffprobe = ffprobe

    def run(self):
        try:
            out = subprocess.check_output([
                self._ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_streams", "-show_format", self._path,
            ], timeout=60)
            data = json.loads(out.decode("utf-8", errors="replace"))
            fmt = data.get("format", {})
            duration = float(fmt.get("duration") or 0)
            fps = 30.0
            nb_frames = 0
            for stream in data.get("streams", []):
                if stream.get("codec_type") != "video":
                    continue
                w = int(stream.get("width") or 0)
                h = int(stream.get("height") or 0)
                if w <= 0 or h <= 0:
                    continue
                fps = _parse_fps(stream)
                try:
                    nb_frames = int(stream.get("nb_frames") or 0)
                except (TypeError, ValueError):
                    nb_frames = 0
                if nb_frames <= 0 and duration > 0:
                    nb_frames = max(1, int(round(duration * fps)))
                elif duration <= 0 and nb_frames > 0:
                    duration = nb_frames / fps
                self.done.emit(w, h, fps, duration, nb_frames)
                return
            self.failed.emit("no video stream")
        except Exception as exc:
            self.failed.emit(str(exc))


class _FfmpegVideoWidget(QWidget):
    """Decode with ffmpeg; position = frame index / native fps (from file probe)."""
    position_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background-color: #000;")
        self._proc = None
        self._path = None
        self._src_w = 0
        self._src_h = 0
        self._out_w = 500
        self._frame_w = 0
        self._frame_h = 0
        self._frame_bytes = 0
        self._buffer = bytearray()
        self._ffmpeg = _find_tool("ffmpeg")
        self._fps = 30.0
        self._duration = 0.0
        self._total_frames = 0
        self._seek_frame = 0
        self._frames_played = 0
        self._paused = False
        self._dead = False
        self._loop = True
        self._display_timer = QTimer(self)
        self._display_timer.setTimerType(Qt.PreciseTimer)
        self._display_timer.timeout.connect(self._show_next_frame)

    def _frame_interval_ms(self):
        return max(1, int(round(1000.0 / self._fps)))

    def apply_probe(self, src_w, src_h, fps, duration, nb_frames):
        self._src_w, self._src_h = src_w, src_h
        self._fps = max(1.0, float(fps))
        self._duration = max(0.0, float(duration))
        self._total_frames = max(1, int(nb_frames))

    def _position_sec(self):
        if self._fps <= 0:
            return 0.0
        frame_pos = self._seek_frame + self._frames_played
        return min(self._duration, frame_pos / self._fps)

    def _decode_size(self):
        if self._src_w <= 0:
            return self._out_w, self._out_w
        # Match ffmpeg "scale=W:-2" (nearest even height, not floor).
        out_h = int(round(self._src_h * self._out_w / self._src_w))
        if out_h % 2:
            out_h += 1
        return self._out_w, max(2, out_h)

    def _kill_process(self):
        if self._proc is not None:
            try:
                self._proc.readyReadStandardOutput.disconnect()
                self._proc.finished.disconnect()
            except Exception:
                pass
            self._proc.kill()
            self._proc.waitForFinished(2000)
            self._proc = None
        self._buffer = bytearray()

    def _reset_playhead(self, seek_sec):
        seek_sec = max(0.0, min(self._duration, float(seek_sec)))
        self._seek_frame = int(seek_sec * self._fps)
        self._frames_played = 0

    def _start_process(self, seek_sec=0.0):
        if self._dead or not self._ffmpeg or not self._path or self._paused:
            return
        self._kill_process()
        self._reset_playhead(seek_sec)
        self._frame_w, self._frame_h = self._decode_size()
        self._frame_bytes = self._frame_w * self._frame_h * 3
        args = ["-hide_banner", "-loglevel", "error"]
        if seek_sec > 0.05:
            args += ["-ss", "%.3f" % seek_sec]
        args += [
            "-re", "-i", self._path,
            "-vf", "scale=%d:-2" % self._out_w,
            "-r", "%.3f" % self._fps,
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-an", "-",
        ]
        self._proc = QProcess(self)
        self._proc.setReadChannel(QProcess.StandardOutput)
        self._proc.readyReadStandardOutput.connect(self._on_data)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.start(self._ffmpeg, args)
        if not self._paused and not self._dead:
            self._display_timer.start(self._frame_interval_ms())

    def set_loop(self, loop):
        self._loop = bool(loop)

    def begin(self, path, out_w=500):
        self._path = path
        self._out_w = out_w
        self._paused = False
        self._dead = False
        self._seek_frame = 0
        self._frames_played = 0

    def play(self):
        if self._dead or not self._path:
            return
        fw, fh = self._decode_size()
        _log("video: play %s %dx%d@%gfps %d frames %.2fs" % (
            os.path.basename(self._path), fw, fh, self._fps,
            self._total_frames, self._duration))
        self._start_process(seek_sec=0.0)

    def duration(self):
        return self._duration

    def position(self):
        return self._position_sec()

    def seek(self, sec):
        sec = max(0.0, min(self._duration, float(sec)))
        self._reset_playhead(sec)
        if not self._paused:
            self._start_process(seek_sec=sec)
        self.position_changed.emit(self._position_sec())

    def pause(self):
        if self._paused:
            return
        self._paused = True
        self._display_timer.stop()
        self._kill_process()
        self.position_changed.emit(self._position_sec())

    def resume(self):
        if self._dead or not self._paused:
            return
        self._paused = False
        self._start_process(seek_sec=self._position_sec())

    def stop(self):
        self._dead = True
        self._paused = True
        self._path = None
        self._display_timer.stop()
        try:
            self.blockSignals(True)
        except Exception:
            pass
        self._kill_process()
        try:
            self._label.clear()
        except Exception:
            pass

    @pyqtSlot()
    def _on_stderr(self):
        if self._proc is None:
            return
        err = bytes(self._proc.readAllStandardError()).decode("utf-8", errors="replace")
        if err.strip():
            _log("ffmpeg err: " + err.strip())

    @pyqtSlot(int, QProcess.ExitStatus)
    def _on_finished(self, code, status):
        if self._dead or self._paused or not self._path:
            return
        if code != 0:
            _log("ffmpeg exit %s" % code)
            return
        at_end = (
            self._seek_frame + self._frames_played >= self._total_frames - 1
            or self._position_sec() >= self._duration - (1.0 / self._fps))
        if at_end:
            if not self._loop:
                self._paused = True
                self._display_timer.stop()
                self._kill_process()
                self.position_changed.emit(self._duration)
                return
            self._reset_playhead(0.0)
            self._start_process(seek_sec=0.0)
            self.position_changed.emit(0.0)
            return
        self._start_process(seek_sec=self._position_sec())

    @pyqtSlot()
    def _on_data(self):
        if self._proc is None:
            return
        self._buffer.extend(bytes(self._proc.readAllStandardOutput()))

    def _show_next_frame(self):
        if self._paused or self._dead or self._frame_bytes <= 0:
            return
        if self._seek_frame + self._frames_played >= self._total_frames:
            self.position_changed.emit(self._position_sec())
            return
        if len(self._buffer) >= self._frame_bytes:
            frame = bytes(self._buffer[:self._frame_bytes])
            del self._buffer[:self._frame_bytes]
            self._frames_played += 1
            img = QImage(
                frame, self._frame_w, self._frame_h,
                self._frame_w * 3, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(img).scaled(
                self._label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._label.setPixmap(pix)
        self.position_changed.emit(self._position_sec())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._label.setGeometry(0, 0, self.width(), self.height())


class VideoPanelWindow(QWidget):
    """Single shared video window — one ffmpeg decode, no external mpv windows."""

    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint)
        self.setObjectName("hideui_video_panel")
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("background-color: #000;")
        self._host = None
        self._ffmpeg = None
        self._paused = False
        self._inited = False
        self._init_running = False
        self._visible_wanted = False
        self._probe_worker = None
        self._video_path = None

        self._stack = QVBoxLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._message = QLabel("Loading video…")
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #ddd; font-size: 13px; padding: 24px;")
        self._stack.addWidget(self._message)
        self._text_panel_mode = None
        self._learning_scroll = None
        self._learning_footer = None
        self._learning_next_btn = None
        self._learning_back_btn = None
        self._learning_on_next = None
        self._learning_on_back = None
        self._learning_step_number = 0
        self._learning_step_total = 0

    def _ensure_learning_footer(self):
        if self._learning_footer is not None:
            return self._learning_footer
        footer = QWidget()
        footer.setStyleSheet("background-color: #2d3a4a;")
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 12, 20, 16)
        lay.setSpacing(12)
        lay.addStretch(1)
        btn_style = (
            "QPushButton { background-color: #4a6fa5; color: white; border: none;"
            " padding: 10px 28px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #5a7fb5; }"
            "QPushButton:disabled { background-color: #3a4a5a; color: #888; }")
        back_style = (
            "QPushButton { background-color: #3a4a5a; color: white; border: none;"
            " padding: 10px 24px; font-size: 14px; }"
            "QPushButton:hover { background-color: #4a5a6a; }"
            "QPushButton:disabled { background-color: #2a3540; color: #666; }")
        back_btn = QPushButton("Back")
        back_btn.setStyleSheet(back_style)
        back_btn.clicked.connect(self._on_learning_back_clicked)
        next_btn = QPushButton("Next")
        next_btn.setStyleSheet(btn_style)
        next_btn.clicked.connect(self._on_learning_next_clicked)
        lay.addWidget(back_btn)
        lay.addWidget(next_btn)
        lay.addStretch(1)
        self._learning_footer = footer
        self._learning_back_btn = back_btn
        self._learning_next_btn = next_btn
        self._stack.addWidget(footer)
        footer.hide()
        return footer

    def _ensure_learning_scroll(self):
        if self._learning_scroll is not None:
            return self._learning_scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background-color: #2d3a4a; border: none; }")
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFrameShape(QTextEdit.NoFrame)
        view.setStyleSheet(
            "QTextEdit { background-color: #2d3a4a; color: #f2f2f2;"
            " padding: 28px 24px; border: none; }")
        scroll.setWidget(view)
        self._learning_scroll = scroll
        self._learning_view = view
        self._stack.addWidget(scroll)
        scroll.hide()
        return scroll

    def is_showing(self):
        return bool(self._visible_wanted and self.isVisible())

    def set_video_path(self, path):
        path = os.path.abspath(path) if path else None
        if path == self._video_path:
            return
        self._video_path = path
        if self._inited or self._init_running:
            self._reset_player()

    def _reset_player(self):
        if self._probe_worker is not None and self._probe_worker.isRunning():
            self._probe_worker.wait(500)
        self._probe_worker = None
        if self._ffmpeg:
            self._ffmpeg.stop()
            self._ffmpeg = None
        if self._host is not None:
            self._stack.removeWidget(self._host)
            self._host.deleteLater()
            self._host = None
        self._inited = False
        self._init_running = False
        self._paused = False
        self._message.setText("Loading video…")
        self._message.show()

    def _controls(self):
        return self._host._controls if self._host else None

    def _toggle_playback(self):
        if self._paused:
            self.resume()
        else:
            self.pause()

    def pause(self):
        self._paused = True
        c = self._controls()
        if c:
            c.set_paused(True)
        if self._ffmpeg:
            self._ffmpeg.pause()

    def resume(self):
        if _SHUTTING_DOWN:
            return
        self._paused = False
        c = self._controls()
        if c:
            c.set_paused(False)
        if self._ffmpeg:
            self._ffmpeg.resume()

    def seek_to_sec(self, sec):
        if self._ffmpeg:
            self._ffmpeg.seek(sec)

    def _on_position_changed(self, pos):
        c = self._controls()
        if c:
            c.set_position_sec(pos)

    def _begin_init(self, panel_w):
        if self._inited or self._init_running or _SHUTTING_DOWN:
            return
        path = _resolve_video_path(_SESSION)
        self._video_path = path
        if not path:
            self._message.setText(
                "Video not found for this session.\n\n"
                "Add a file to:\n  %s\n\n"
                "Name it e.g. 2-A.mp4 (session-condition),\n"
                "or map any name in media/videos.json" % MEDIA_DIR)
            return
        ffprobe = _find_tool("ffprobe")
        if not _find_tool("ffmpeg") or not ffprobe:
            self._message.setText("ffmpeg not found.\n\nRun: brew install ffmpeg")
            return
        self._init_running = True
        self._message.setText("Loading video…")
        self._message.show()
        self._host = _VideoHost(self)
        self._ffmpeg = _FfmpegVideoWidget(self._host)
        self._ffmpeg.position_changed.connect(self._on_position_changed)
        self._host.set_video(self._ffmpeg)
        self._ffmpeg.begin(path, out_w=panel_w)
        self._stack.insertWidget(0, self._host)
        self._host.hide()
        self._probe_worker = _ProbeWorker(path, ffprobe)
        self._probe_worker.done.connect(self._on_probe_done)
        self._probe_worker.failed.connect(self._on_probe_failed)
        self._probe_worker.start()
        _log("video panel: probing async")

    def _on_probe_done(self, src_w, src_h, fps, duration, nb_frames):
        self._init_running = False
        if _SHUTTING_DOWN or not self._ffmpeg:
            return
        self._ffmpeg.apply_probe(src_w, src_h, fps, duration, nb_frames)
        fw, fh = self._ffmpeg._decode_size()
        _log("video panel: %dx%d %.3ffps %d frames %.3fs" % (
            fw, fh, fps, nb_frames, duration))
        self._message.hide()
        self._host.show()
        c = self._host._controls
        c.set_duration_sec(duration)
        c.set_position_sec(0.0)
        c.set_paused(False)
        self._inited = True
        self._paused = False
        if self._visible_wanted:
            self._ffmpeg.play()
            self.show()
            self.raise_()
        _log("video panel: playback ready")

    def _on_probe_failed(self, err):
        self._init_running = False
        _log("video probe failed: %s" % err)
        self._message.setText("Could not read video.\n\nSee ~/krita_hide_ui_log.txt")

    def _restore_video_view(self):
        """Show the ffmpeg surface again after break/recall text panels."""
        if self._inited and self._host is not None:
            self._message.hide()
            self._host.show()
        elif not self._inited and not self._init_running:
            self._message.setStyleSheet(
                "color: #ddd; font-size: 13px; padding: 24px;")
            self._message.setAlignment(Qt.AlignCenter)
            self._message.setText("Loading video…")
            self._message.show()

    def show_at(self, pos, size):
        if _SHUTTING_DOWN:
            return
        if self._text_panel_mode:
            self._text_panel_mode = None
        self._restore_video_view()
        self._visible_wanted = True
        self.setFixedSize(size)
        self.move(pos)
        if not self._inited and not self._init_running:
            self._begin_init(size.width())
        elif self._inited and self._ffmpeg:
            if self._paused:
                self.resume()
            elif self._ffmpeg._proc is None:
                self._ffmpeg.play()
        self.show()
        self.raise_()
        _log("video panel shown at %s size %s" % (pos, size))

    def hide_panel(self):
        if _SHUTTING_DOWN:
            return
        self._text_panel_mode = None
        self._visible_wanted = False
        if self._learning_scroll is not None:
            self._learning_scroll.hide()
        if self._learning_footer is not None:
            self._learning_footer.hide()
        self.pause()
        self.hide()

    def reposition(self, pos, size):
        if _SHUTTING_DOWN or not self._visible_wanted:
            return
        if self.pos() == pos and self.size() == size:
            return
        self.setFixedSize(size)
        self.move(pos)

    def restart_playback(self):
        if _SHUTTING_DOWN or not self._visible_wanted or not self._ffmpeg:
            return
        self._restore_video_view()
        self._paused = False
        c = self._controls()
        if c:
            c.set_paused(False)
            c.set_position_sec(0.0)
        self._ffmpeg._paused = False
        self._ffmpeg.play()
        _log("video panel: restart_playback")

    def stop_tutorial(self):
        self.hide_panel()

    def _format_text_panel_html(self, title, body):
        lines = [line.strip() for line in body.strip().split("\n") if line.strip()]
        html = "<div style='text-align:center;'>"
        html += (
            "<p style='font-size:26px; font-weight:bold; margin-bottom:20px;'>"
            "%s</p>" % title)
        for line in lines:
            html += (
                "<p style='font-size:17px; line-height:1.5; margin:8px 0;'>"
                "%s</p>" % line)
        html += "</div>"
        return html

    def _show_text_panel(self, pos, size, title, body, mode, bg_color):
        if _SHUTTING_DOWN:
            return
        self._text_panel_mode = mode
        self._visible_wanted = True
        if self._ffmpeg:
            self.pause()
        if self._host is not None:
            self._host.hide()
        scroll = self._ensure_learning_scroll()
        scroll.hide()
        self._message.setText(self._format_text_panel_html(title, body))
        self._message.setAlignment(Qt.AlignCenter)
        self._message.setStyleSheet(
            "color: #f2f2f2; background-color: %s;"
            " font-size: 16px; padding: 36px 28px;" % bg_color)
        self._message.show()
        self.setFixedSize(size)
        self.move(pos)
        self.show()
        self.raise_()
        _log("video panel: %s text at %s" % (mode, pos))

    def _on_learning_next_clicked(self):
        cb = self._learning_on_next
        if cb is not None:
            cb()

    def _on_learning_back_clicked(self):
        cb = self._learning_on_back
        if cb is not None:
            cb()

    def _update_learning_nav_buttons(self):
        if self._learning_next_btn is not None:
            if self._learning_step_number >= self._learning_step_total:
                self._learning_next_btn.setText("Continue")
            else:
                self._learning_next_btn.setText("Next")
        if self._learning_back_btn is not None:
            on_first = int(self._learning_step_number or 1) <= 1
            self._learning_back_btn.setEnabled(not on_first)
            self._learning_back_btn.setVisible(not on_first)

    def _show_learning_panel(self, pos, size, title, steps, phase=1):
        """Legacy: show all steps (used only if caller passes a full list)."""
        if isinstance(steps, (list, tuple)) and len(steps) == 1:
            self.show_learning_step_panel(
                pos, size, title, steps[0], 1, 1, phase=phase,
                on_next=self._learning_on_next)
            return
        if _SHUTTING_DOWN:
            return
        from .learning_instructions import (
            format_learning_steps_html, PLUGIN_DIR)
        self._text_panel_mode = "learning"
        self._visible_wanted = True
        if self._ffmpeg:
            self.pause()
        if self._host is not None:
            self._host.hide()
        self._message.hide()
        scroll = self._ensure_learning_scroll()
        if self._learning_footer is not None:
            self._learning_footer.hide()
        self._learning_view.document().setBaseUrl(
            QUrl.fromLocalFile(PLUGIN_DIR + os.sep))
        self._learning_view.setHtml(
            format_learning_steps_html(title, steps, phase=phase))
        scroll.show()
        self.setFixedSize(size)
        self.move(pos)
        self.show()
        self.raise_()
        _log("video panel: learning steps at %s" % pos)

    def show_learning_step_panel(
            self, pos, size, title, step_text, step_number, total_steps,
            phase=1, on_next=None, on_back=None):
        """One step at a time with reference image, Back and Next buttons."""
        if _SHUTTING_DOWN:
            return
        from .learning_instructions import (
            format_learning_step_html, PLUGIN_DIR)
        self._text_panel_mode = "learning"
        self._visible_wanted = True
        self._learning_on_next = on_next
        self._learning_on_back = on_back
        self._learning_step_number = int(step_number or 1)
        self._learning_step_total = int(total_steps or 1)
        if self._ffmpeg:
            self.pause()
        if self._host is not None:
            self._host.hide()
        self._message.hide()
        scroll = self._ensure_learning_scroll()
        footer = self._ensure_learning_footer()
        self._learning_view.document().setBaseUrl(
            QUrl.fromLocalFile(PLUGIN_DIR + os.sep))
        self._learning_view.setHtml(format_learning_step_html(
            title, step_text, step_number, total_steps, phase=phase))
        self._update_learning_nav_buttons()
        scroll.show()
        footer.show()
        self.setFixedSize(size)
        self.move(pos)
        self.show()
        self.raise_()
        _log("video panel: learning step %d/%d at %s" % (
            step_number, total_steps, pos))

    def _end_text_panel(self, mode):
        if self._text_panel_mode != mode:
            return
        self._text_panel_mode = None
        if self._learning_scroll is not None:
            self._learning_scroll.hide()
        if self._learning_footer is not None:
            self._learning_footer.hide()
        self._message.setStyleSheet("color: #ddd; font-size: 13px; padding: 24px;")
        self._message.setText("Loading video…")
        self.hide_panel()

    def show_learning_instructions_panel(self, pos, size, title, steps, phase=1):
        """Replace the video area with step-by-step learning instructions."""
        self._show_learning_panel(pos, size, title, steps, phase=phase)

    def end_learning_instructions_panel(self):
        self._end_text_panel("learning")

    def show_recall_instructions_panel(self, pos, size, title, body):
        """Replace the video area with recall instructions; Krita stays in place."""
        self._show_text_panel(pos, size, title, body, "recall", "#1a3d5f")

    def end_recall_instructions_panel(self):
        self._end_text_panel("recall")

    def destroy(self):
        self._visible_wanted = False
        if self._probe_worker is not None:
            try:
                if self._probe_worker.isRunning():
                    self._probe_worker.wait(1000)
            except Exception:
                pass
            self._probe_worker = None
        if self._ffmpeg:
            try:
                self._ffmpeg.stop()
            except Exception:
                pass
            self._ffmpeg = None
        try:
            self.hide()
        except Exception:
            pass
        _log("video panel: destroyed")
