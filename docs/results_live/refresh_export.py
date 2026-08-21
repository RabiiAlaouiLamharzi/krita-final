#!/usr/bin/env python3
"""Refresh docs/results_live CSV exports from the latest local data folder.

  export KRITA_ANALYSIS_DIR="$HOME/Desktop/krita-main/experiment/internship_report/analysis"
  python docs/results_live/refresh_export.py

Then commit and push the updated CSV/meta files so Colab sees new participants.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE

DEFAULT_ANALYSIS = (
    Path.home() / "Desktop/krita-main/experiment/internship_report/analysis"
)
ANALYSIS = Path(os.environ.get("KRITA_ANALYSIS_DIR", str(DEFAULT_ANALYSIS)))
if not (ANALYSIS / "update_results_v2.py").exists():
    raise SystemExit(
        "Cannot find update_results_v2.py in %s\n"
        "Set KRITA_ANALYSIS_DIR to that folder." % ANALYSIS
    )
sys.path.insert(0, str(ANALYSIS))

import update_results_v2 as ur  # noqa: E402

EXCLUDE = {"P12", "P21", "P35", "P36"}


def pick_data() -> Path:
    for name in ("data 4", "data 3", "data 2"):
        p = REPO / "experiment" / name
        if p.is_dir():
            return p
    raise SystemExit("No experiment/data folder found under " + str(REPO))


def main() -> None:
    ur.DATA = str(pick_data())
    ur.EXCLUDE = EXCLUDE
    print("DATA =", ur.DATA)
    t = ur.load_trials()
    pids = set(t.pid.unique())
    sv = ur.load_surveys(pids)
    L = ur.load_learning(pids)
    t.to_csv(OUT / "trials.csv", index=False)
    sv.to_csv(OUT / "surveys.csv", index=False)
    L.to_csv(OUT / "learning.csv", index=False)
    meta = {
        "data_source_folder": Path(ur.DATA).name,
        "exclude": sorted(EXCLUDE),
        "n_participants": int(t.pid.nunique()),
        "n_abrupt": int(t[t.condition == "Abrupt"].pid.nunique()),
        "n_incremental": int(t[t.condition == "Incremental"].pid.nunique()),
        "n_trials": int(len(t)),
        "n_unanswered": int((~t.answered).sum()),
        "pids": sorted(map(str, t.pid.unique())),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("wrote exports to", OUT)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
