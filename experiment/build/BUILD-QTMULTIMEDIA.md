# QtMultimedia build guide (experiment video panel)

The video panel uses **PyQt5.QtMultimedia** + **QVideoWidget** to play `test.mov` inside the right-side window. Stock Krita does not ship these modules — your custom build must include them.

## What was changed in krita-master

1. **`CMakeLists.txt`** — `KRITA_ENABLE_QTMULTIMEDIA` option (default **ON**)
   - Requires `Qt5Multimedia` and `Qt5MultimediaWidgets` at configure time
2. **`krita/CMakeLists.txt`** — links the `krita` binary against those modules so `macos-deploy.py` bundles the frameworks

## Step 1 — Rebuild Qt with Multimedia (krita-deps-management)

In your [krita-deps-management](https://invent.kde.org/packaging/krita-deps-management) build, ensure Qt includes the `multimedia` module (it usually does if you use the full Qt5 build).

## Step 2 — Rebuild PyQt5 with Multimedia enabled

When building PyQt5 against the same Qt prefix, enable:

```bash
# sip-build style (PyQt5 5.15+)
sip-build --confirm-license \
  --qmake="$PREFIX/bin/qmake" \
  --target-dir "$PREFIX/lib/python3.x/site-packages" \
  --enable QtMultimedia QtMultimediaWidgets
make -C build install
```

Or with legacy `configure.py`:

```bash
python configure.py --confirm-license \
  --qmake="$PREFIX/bin/qmake" \
  --destdir="$PREFIX/lib/python3.x/site-packages" \
  --enable=QtMultimedia --enable=QtMultimediaWidgets
make && make install
```

Verify before building Krita:

```bash
export PYTHONPATH="$PREFIX/lib/python3.x/site-packages"
python3 -c "from PyQt5.QtMultimedia import QMediaPlayer; print('ok')"
```

## Step 3 — Build Krita

```bash
cd krita-master/build
cmake .. -DCMAKE_INSTALL_PREFIX=/path/to/_install -DKRITA_ENABLE_QTMULTIMEDIA=ON
cmake --build . --target install
python3 ../packaging/macos/macos-deploy.py \
  --install-dir /path/to/_install \
  --output-dir /path/to/_dmg \
  --krita-source ..
```

After deploy, confirm these exist:

```
krita.app/Contents/Frameworks/QtMultimedia.framework
krita.app/Contents/Frameworks/QtMultimediaWidgets.framework
krita.app/Contents/Frameworks/Python.framework/.../PyQt5/QtMultimedia.so
krita.app/Contents/Frameworks/Python.framework/.../PyQt5/QtMultimediaWidgets.so
```

## Step 4 — Patch an existing .app (optional)

If frameworks/bindings are in `_install` but missing from the bundle:

```bash
cd experiment/build
chmod +x patch-krita-multimedia.sh
./patch-krita-multimedia.sh /path/to/krita.app /path/to/_install
```

## Step 5 — Install experiment plugin + video

```bash
cd experiment
./install-mac.sh
```

Place `test.mov` in `experiment/media/` (copied to the plugin folder by `install-mac.sh`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImportError: QtMultimedia` in `~/krita_hide_ui_log.txt` | PyQt5 modules missing from bundle — rerun patch script |
| Video panel says "needs QtMultimedia" | Same as above |
| Black panel, no video | Check `test.mov` path; check macOS media permissions |
| CMake fails on `Multimedia` | Rebuild Qt deps; or `-DKRITA_ENABLE_QTMULTIMEDIA=OFF` temporarily |

To disable multimedia at configure time (stock-like build):

```bash
cmake .. -DKRITA_ENABLE_QTMULTIMEDIA=OFF
```

On macOS without QtMultimedia, the plugin falls back to **QuickTime Player** in a separate window.
