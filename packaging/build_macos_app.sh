#!/bin/bash
# Build "Bleedover Corrector.app": a double-clickable launcher for this repo's app.
#
#   bash bleedover_app/packaging/build_macos_app.sh            # -> ~/Applications/Bleedover Corrector.app
#   bash bleedover_app/packaging/build_macos_app.sh /Applications
#
# The .app runs `python -m bleedover_app` from this repo with the Python of the
# environment active when you build it (activate `mapa` first). It doesn't copy
# the code, so pulling new code updates the app. Rebuild if the repo or the
# environment moves.
set -euo pipefail

DEST="${1:-$HOME/Applications}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-$(command -v python)}"
APP="$DEST/Bleedover Corrector.app"

"$PYTHON" -c "import numpy, pandas, scipy, pyarrow, matplotlib, psutil" 2>/dev/null || {
  echo "The Python at $PYTHON lacks the pipeline's packages. Run 'conda activate mapa' first." >&2; exit 1; }

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/launcher" <<EOF
#!/bin/bash
cd "$REPO"
exec "$PYTHON" -m bleedover_app >> "\$HOME/Library/Logs/BleedoverCorrector.log" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/launcher"
[ -f "$REPO/bleedover_app/static/icons/icon.icns" ] && cp "$REPO/bleedover_app/static/icons/icon.icns" "$APP/Contents/Resources/icon.icns"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Bleedover Corrector</string>
  <key>CFBundleDisplayName</key><string>Bleedover Corrector</string>
  <key>CFBundleIdentifier</key><string>edu.stanford.sohlab.bleedover</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
EOF
echo "Built $APP (repo: $REPO, python: $PYTHON)"
