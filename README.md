# krita-final (study experiment)

Snapshot saved **2026-07-06** — video-tutorial version with layout profiles, loading screen, recall fixes, and brush-preset panel polish.

## What's in this version

- Layout profiles A / A_C1 / A_C1_C2 / B with session-2 condition mapping
- Loading overlay during canvas prep and UI setup (no artificial delay)
- Brush preset panel gap fix for Layout A
- Recall layout matching learning layouts
- Clean Krita quit (`os._exit`) and toolbox ordering

## Install (macOS)

```bash
cd experiment
bash install-mac.sh
open -a /Applications/krita.app --args -nosplash
```

Krita loads the plugin from `~/Library/Application Support/krita/pykrita/hide_ui/`.

## Media

Tutorial `.mov` files are **not** in git (too large). Place them under `experiment/media/` locally. Smaller `.mp4` files may be included.

## Restore this version

```bash
git clone https://github.com/RabiiAlaouiLamharzi/krita-final.git
cd krita-final/experiment
bash install-mac.sh
```
