# krita-final (study experiment)

Krita UI learning study — plugin + packaging for **macOS** and **Windows** participant downloads.

**Standard Krita version: 5.3.3** (same minor on both platforms). Do not use Krita 6.

## Participant download (recommended)

1. Install **Krita 5.3.3** from [krita.org/download](https://krita.org/en/download/)
2. Open the [download page](https://rabiialaouilamharzi.github.io/krita-final/) **or** [Releases](https://github.com/RabiiAlaouiLamharzi/krita-final/releases) and get **KritaStudy-pack.zip**
3. Unzip → run **Launch Study** (Mac: Right‑click → Open; Windows: double‑click the `.bat`)
4. Log in with experimenter credentials

See [experiment/dist/README.md](experiment/dist/README.md) to rebuild packages.

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
