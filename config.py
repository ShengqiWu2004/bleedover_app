"""Where the app reads and writes, and the preferences it remembers between launches.

Run from the repo, every run gets the usual
``results/<YYMMDD_HHMMSS>_correct_<name>/`` folder (see ``utils.runs``). The
standalone app (``FROZEN``, built by ``packaging/build_standalone_macos.sh``)
can't write inside its own bundle, so its runs go to
``~/Documents/Bleedover Corrector/runs/`` instead. The app's own report goes in
``<run>/app_report/``.

Preferences (FASTQ library path, last folder, workers, ...) live in a JSON file
in the user's application-data folder, not in the repo.
"""

import json
import os
import sys
import threading
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))       # running as the standalone app
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
RESULTS_DIR = Path.home() / "Documents" / "Bleedover Corrector" / "runs" if FROZEN else REPO_ROOT / "results"
STATIC_DIR = PACKAGE_DIR / "static"
REPORT_DIRNAME = "app_report"
APP_NAME = "Bleedover Corrector"

FASTQ_MODES = ("experiment", "library")
DEFAULT_PREFS = {
    "fastq_mode": "experiment",   # "experiment": <experiment>/fastq; "library": match the flowcell ID in a library
    "fastq_library": "",
    "last_dir": "",
    "workers": None,              # None: the recommended number for this computer
    "run_folders": [],            # extra folders holding correction runs (e.g. the repo's results/)
    "renderer": "voronoi",
}


def app_data_dir() -> Path:
    """Per-user folder for preferences (created on first use)."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME.replace(" ", "")
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_browse_dir() -> str:
    """Where the folder picker opens the first time: mounted drives on macOS, else home."""
    volumes = Path("/Volumes")
    return str(volumes if volumes.is_dir() else Path.home())


def run_folders(prefs: dict) -> list[Path]:
    """Where to look for correction runs: the app's own folder first, then the ones the user added."""
    extra = [Path(p) for p in prefs.get("run_folders", []) if Path(p).is_dir()]
    return list(dict.fromkeys([RESULTS_DIR, *extra]))


class Prefs:
    """Thread-safe JSON preferences; unknown keys are ignored on update."""

    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "preferences.json"
        self._lock = threading.Lock()

    def load(self) -> dict:
        with self._lock:
            try:
                saved = json.loads(self.path.read_text())
            except (OSError, ValueError):
                saved = {}
        return {**DEFAULT_PREFS, **{k: v for k, v in saved.items() if k in DEFAULT_PREFS}}

    def update(self, changes: dict) -> dict:
        if "fastq_mode" in changes and changes["fastq_mode"] not in FASTQ_MODES:
            raise ValueError(f"fastq_mode must be one of {FASTQ_MODES}")
        prefs = {**self.load(), **{k: v for k, v in changes.items() if k in DEFAULT_PREFS}}
        with self._lock:
            self.path.write_text(json.dumps(prefs, indent=1))
        return prefs
