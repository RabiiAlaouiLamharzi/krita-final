"""Participant data directory helpers."""

import os

from .experiment import BASE_DIR


def ensure_participant_dir(participant_id):
    pdir = os.path.join(BASE_DIR, str(participant_id))
    os.makedirs(pdir, exist_ok=True)
    return pdir
