# Live Results Notebook

Interactive notebook for regenerating the main Results figures from the exported dataset.

## Open in Google Colab

https://colab.research.google.com/github/RabiiAlaouiLamharzi/krita-final/blob/main/docs/results_live/results_figures.ipynb

## GitHub file

https://github.com/RabiiAlaouiLamharzi/krita-final/blob/main/docs/results_live/results_figures.ipynb

## Update after new participants

```bash
# Point to the analysis helpers (default: Desktop/krita-main/.../analysis)
export KRITA_ANALYSIS_DIR="$HOME/Desktop/krita-main/experiment/internship_report/analysis"
python docs/results_live/refresh_export.py
git add docs/results_live/*.csv docs/results_live/meta.json
git commit -m "Update results export for live notebook"
git push
```

Then re-run the Colab notebook (*Runtime → Run all*).
