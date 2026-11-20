# PyInstaller spec for the standalone macOS app. Build with packaging/build_standalone_macos.sh.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO = Path(SPECPATH).resolve().parents[1]
APP = REPO / "bleedover_app"

a = Analysis(
    [str(APP / "packaging" / "app_entry.py")],
    pathex=[str(REPO)],
    datas=[
        (str(APP / "static"), "bleedover_app/static"),
        (str(APP / "default_models"), "bleedover_app/default_models"),
        (str(REPO / "devices" / "miseq_ptinf.json"), "devices"),      # utils.device reads <root>/devices/
    ],
    hiddenimports=collect_submodules("bleedover_app", filter=lambda name: ".tests" not in name) + collect_submodules("correction")
                  + collect_submodules("simulator") + collect_submodules("utils"),
    excludes=["tkinter", "IPython", "jupyter", "notebook", "cvxpy", "PyQt5", "PyQt6", "PySide6", "pytest",
              "bleedover_app.tests", "matplotlib.backends.backend_qtagg", "matplotlib.backends.backend_tkagg"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BleedoverCorrector", console=False,
          argv_emulation=False, target_arch=None, codesign_identity=None)
coll = COLLECT(exe, a.binaries, a.datas, name="BleedoverCorrector")
app = BUNDLE(
    coll,
    name="Bleedover Corrector.app",
    icon=str(APP / "static" / "icons" / "icon.icns"),
    bundle_identifier="edu.stanford.sohlab.bleedover",
    version="1.0.0",
    info_plist={
        "CFBundleDisplayName": "Bleedover Corrector",
        "LSUIElement": True,                 # no Dock icon: the window is the browser; quit from ⚙ System
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": "Used to open the folder picker.",
    },
)
