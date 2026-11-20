"""Correction runs on disk: which belong to an experiment, what method each used, and which can be resumed.

Every correction is a run folder (``<stamp>_correct_<experiment>...``), one per
method, so trying another method never touches an earlier run. A run is
**done** when it has ``<experiment>/summary.csv``; otherwise it is **running**
(the app's current job) or **stopped** (cancelled, failed, or the computer
slept/quit). A stopped app run can be **resumed**: the job runs again in the
same folder and ``correction.correct_one`` skips every image already saved with
the same model and settings, so only the missing images are fitted.

Two runs use the same **method** when they share the experiment, the built-in
model, and the correction settings below (worker count doesn't matter).
"""

import json
from pathlib import Path

from .config import REPORT_DIRNAME

METHOD_KEYS = ("renderer", "prior", "softness", "steps", "background_spacing")
MODEL_LABELS = {"standard": "Standard PSF", "qc_psf": "Cross-check PSF"}


def read_config(run_dir: Path) -> dict:
    try:
        return json.loads((run_dir / "config.json").read_text())
    except (OSError, ValueError):
        return {}


def saved_images(run_dir: Path) -> list[dict]:
    """Images a run has finished: table, background and summary all saved."""
    images = []
    for summary in sorted(run_dir.glob("*/*/*.json")):
        if summary.with_suffix(".feather").exists() and summary.with_suffix(".background.npy").exists():
            images.append({"cycle": summary.parent.name, "tile": summary.stem})
    return images


def method(settings: dict) -> dict:
    """The parts of a run's settings that change its results (app runs; script runs have them flat)."""
    options = settings.get("correct", settings)
    out = {k: options.get(k) for k in METHOD_KEYS}
    out["model"] = settings.get("model_id") or Path(str(settings.get("model", ""))).stem
    return out


def same_method(a: dict, b: dict) -> bool:
    def norm(value):
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value
    return all(norm(a.get(k)) == norm(b.get(k)) for k in (*METHOD_KEYS, "model"))


def describe(settings: dict) -> str:
    """Short method label, e.g. ``Standard PSF · voronoi · prior 0.1 · softness 1``."""
    m = method(settings)
    model = MODEL_LABELS.get(m["model"]) or (m["model"] or "model ?").removeprefix("single_point_")
    parts = [model, m["renderer"] or "additive"]
    if m["prior"] is not None:
        parts.append(f"prior {float(m['prior']):g}")
    if m["renderer"] == "voronoi" and m["softness"] is not None:
        parts.append(f"softness {float(m['softness']):g}")
    return " · ".join(parts)


def experiment_runs(folders: list[Path], experiment: str, running_dir: str | None) -> list[dict]:
    """This experiment's runs only, newest first.

    A run belongs to the experiment when its folder holds ``<experiment>/`` or its settings name it; exact
    matching, so ``20261009_align_try3`` never picks up ``20261009_align_try3_SW``'s runs.
    """
    out = []
    candidates = {d for folder in folders for d in folder.glob("*_correct_*") if d.is_dir()}
    for run_dir in sorted(candidates, key=lambda d: d.name, reverse=True):
        config = read_config(run_dir)
        settings = config.get("settings", {})
        if not ((run_dir / experiment).is_dir() or settings.get("experiment") == experiment):
            continue
        app_run = "bleedover_app" in config.get("command", "")
        if str(run_dir) == running_dir:
            status = "running"
        elif (run_dir / experiment / "summary.csv").exists():
            status = "done"
        else:
            status = "stopped"
        done = len(saved_images(run_dir))
        resumable = (status == "stopped" and app_run and bool(settings.get("model_id"))   # older app runs predate
                     and (run_dir / "app_job.json").exists())                         # the built-in models
        if status == "stopped" and done == 0 and not resumable:
            continue                              # nothing to show and nothing to resume
        out.append({"run": run_dir.name, "status": status, "started": config.get("started", ""),
                    "made_by": "app" if app_run else "script", "method": describe(settings),
                    "settings": method(settings), "images_done": done, "images_total": settings.get("images"),
                    "resumable": resumable, "has_report": (run_dir / REPORT_DIRNAME / "report.json").exists()})
    return out


def resumable_match(runs: list[dict], wanted: dict) -> dict | None:
    """The newest stopped run of this experiment with the same method, if any."""
    return next((r for r in runs if r["resumable"] and same_method(r["settings"], wanted)), None)
