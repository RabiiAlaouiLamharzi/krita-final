"""Native QMainWindow state blobs for instant, atomic study-layout switching.

Krita restores its dock layout from kritarc ([MainWindow] State) at window
creation and on every welcome-page -> canvas switch. Instead of fighting that
mechanism with retries, we keep kritarc's State equal to the layout we want
and apply layouts with a single QMainWindow.restoreState() call from cached
per-profile blobs. Krita's own restores then reproduce our layout exactly.
"""

import base64
import os
import traceback

from .experiment import BASE_DIR

STATE_DIR = os.path.join(os.path.dirname(BASE_DIR), "layout_states")
# Bump when the docker set / capture semantics change so stale blobs
# from older plugin versions are ignored.
# v2: captures are verification-gated; v1 blobs may hold unsettled layouts.
# v3: layout definitions changed (A: presets right column; B: presets in toolbar).
# v4: layers docker height reduced to 240.
# v5: preset recovery + toolbar order + quit fix.
STATE_VERSION = 5

LOG = os.path.expanduser("~/krita_hide_ui_log.txt")


def _log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass


def _blob_path(profile, width, height):
    name = "v%d_%s_%dx%d.state" % (STATE_VERSION, profile, int(width), int(height))
    return os.path.join(STATE_DIR, name)


def load_state_blob(profile, width, height):
    """Return cached QMainWindow state bytes for a profile, or None."""
    path = _blob_path(profile, width, height)
    try:
        if os.path.isfile(path):
            with open(path, "rb") as f:
                data = f.read()
            if data:
                return data
    except Exception:
        _log(traceback.format_exc())
    return None


def save_state_blob(profile, width, height, data):
    """Persist QMainWindow state bytes for a profile."""
    if not data:
        return False
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(_blob_path(profile, width, height), "wb") as f:
            f.write(bytes(data))
        _log("layout state cached: %s (%d bytes)" % (profile, len(data)))
        return True
    except Exception:
        _log(traceback.format_exc())
        return False


def delete_state_blob(profile, width, height):
    """Remove a cached blob that failed post-restore verification."""
    path = _blob_path(profile, width, height)
    try:
        if os.path.isfile(path):
            os.remove(path)
            _log("layout state deleted (failed verification): %s"
                 % os.path.basename(path))
            return True
    except Exception:
        _log(traceback.format_exc())
    return False


def sync_state_to_kritarc(data):
    """Write the state blob into kritarc so Krita's own restores agree with us.

    Krita re-applies [MainWindow] State on every welcome->canvas switch and at
    startup; keeping it equal to the active study layout makes those restores
    no-ops instead of layout resets.
    """
    if not data:
        return False
    try:
        from krita import Krita
        encoded = base64.b64encode(bytes(data)).decode("ascii")
        Krita.instance().writeSetting("MainWindow", "State", encoded)
        return True
    except Exception:
        _log(traceback.format_exc())
        return False
