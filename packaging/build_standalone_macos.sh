#!/bin/bash
# Build a standalone "Bleedover Corrector.app" (Python and all packages inside) and a .dmg to share.
#
#   conda activate bleedover-build          # see "Build the app" in bleedover_app/README.md
#   bash bleedover_app/packaging/build_standalone_macos.sh             # -> dist/BleedoverCorrector-<arch>.dmg
#   bash bleedover_app/packaging/build_standalone_macos.sh --install   # also install into ~/Applications
#
# The working copy of the app is built in build.noindex/: Spotlight and Launchpad skip folders ending in
# .noindex, so it doesn't show up as a second "Bleedover Corrector" next to the installed one.
# The app runs only on the CPU type it was built on (arm64 = Apple silicon, x86_64 = Intel).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ARCH="$(uname -m)"
WORK="$HERE/build.noindex"
APP="$WORK/dist/Bleedover Corrector.app"
DMG="$HERE/dist/BleedoverCorrector-$ARCH.dmg"
URL="http://127.0.0.1:8765"
cd "$HERE"
python -c "import PyInstaller" 2>/dev/null || { echo "PyInstaller missing: conda activate bleedover-build" >&2; exit 1; }

job_status() {   # status of the running app's current job, or "none" when no app is running
  curl -s -m 2 "$URL/api/state" | python -c "import json,sys; print(json.load(sys.stdin)['job']['status'])" 2>/dev/null || echo none
}

rm -rf "$WORK" "$HERE/build" "$HERE/dist"          # (build/ and dist/*.app are from older versions of this script)
pyinstaller --noconfirm --clean --distpath "$WORK/dist" --workpath "$WORK/work" bleedover.spec
codesign --force --deep --sign - "$APP"          # ad-hoc signature (no Apple developer account)

mkdir -p "$HERE/dist"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$HERE/../INSTALL.md" "$STAGE/Read me first (install).md"
hdiutil create -quiet -volname "Bleedover Corrector" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"
du -sh "$DMG"
echo "Built $DMG"

if [ "${1:-}" = "--install" ]; then
  status="$(job_status)"
  if [ "$status" = running ]; then
    echo "A correction is running in the app; not replacing it now. Run again with --install when it finishes." >&2
    exit 1
  fi
  [ "$status" != none ] && { curl -s -m 3 -X POST -H 'Content-Type: application/json' -d '{}' "$URL/api/quit" >/dev/null; sleep 2; }
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/Bleedover Corrector.app"
  cp -R "$APP" "$HOME/Applications/"
  open "$HOME/Applications/Bleedover Corrector.app"
  echo "Installed and opened ~/Applications/Bleedover Corrector.app"
fi
