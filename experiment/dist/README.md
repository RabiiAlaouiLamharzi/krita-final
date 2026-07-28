# Participant download packages

Build zips that contain **Krita + this study plugin**. Participants unzip and double-click **Launch Study**.

## Requirements

- **macOS build machine:** Krita **5.3.2** installed (or pass path to `krita.app`)
- **Windows package:** downloads portable Krita 5.3.2 automatically (needs network), or pass an extracted portable folder
- No ffmpeg / no tutorial videos (right panel = text + images)

## Build

```bash
cd experiment/dist
chmod +x build-mac-bundle.sh build-windows-bundle.sh

# Mac (uses /Applications/krita.app by default)
./build-mac-bundle.sh

# Windows zip (downloads krita-x64-5.3.2.zip if needed)
./build-windows-bundle.sh
```

Outputs land in `experiment/dist/out/`:

- `KritaStudy-macOS-5.3.2.zip`
- `KritaStudy-Windows-5.3.2.zip`

## Publish

1. Create a GitHub Release on `krita-final`
2. Upload both zip files as release assets
3. Enable GitHub Pages from `/docs` so the download site is live

Landing page: `docs/index.html` (links to latest release assets).

## Local install only (developers)

```bash
# macOS
cd experiment && bash install-mac.sh

# Windows (PowerShell)
cd experiment
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```
