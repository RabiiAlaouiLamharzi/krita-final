# krita-final (study experiment)

Krita UI learning study — plugin + packaging for **macOS** and **Windows** participant downloads.

**Standard Krita version: 5.3.2** (same minor on both platforms).

## Participant download (recommended)

1. Open the [download page](https://rabiialaouilamharzi.github.io/krita-final/) **or** [Releases](https://github.com/RabiiAlaouiLamharzi/krita-final/releases)
2. Download **KritaStudy-macOS-*.zip** or **KritaStudy-Windows-*.zip**
3. Unzip → double-click **Launch Study** → log in with experimenter credentials

See [experiment/dist/README.md](experiment/dist/README.md) to build those zips.

## Developer install (plugin only)

### macOS

```bash
cd experiment
bash install-mac.sh
open -a /Applications/krita.app --args -nosplash
```

### Windows

```powershell
cd experiment
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
# then start krita.exe -nosplash
```

## Notes

- Right panel uses **text + step images** only (`STUDY_USE_VIDEO = False`). No ffmpeg.
- Plain-text passwords stay local (`passwords_plain.json` is gitignored). Hashed `passwords.json` ships in the pack.
- Tutorial videos are not included.
