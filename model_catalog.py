"""The two built-in models, and the calibration each one uses for an experiment.

Chosen by held-out tests on isolated dots from all five experiments (2026-11-18,
2,500 dots each; median per-dot R² of the image predicted from RFU):

| model | QC | EPVIII05 | bubble | qc_perct | accperct |
| --- | --- | --- | --- | --- | --- |
| pooled Gaussian (**standard**) | 0.920 | 0.867 | 0.825 | 0.870 | 0.864 |
| QC-only Gaussian (**qc_psf**) | 0.920 | 0.865 | 0.820 | – | – |

The other six models in ``models/`` were within 0.005 of these (Moffat and
elliptical fits run to the round Gaussian) or worse (bubble-only), and three
were the pooled model with fewer calibrations. Each built-in model ships with
the calibrations it was trained or calibrated on; the user's own
calibrations (``calibrations.CalibrationStore``) come first when both exist.
Built-in models can't be deleted; the user's calibrations can.
"""

import json
from pathlib import Path

from simulator import SinglePointModel

from .calibrations import CalibrationStore
from .config import PACKAGE_DIR, REPO_ROOT

DEFAULT_DIR = PACKAGE_DIR / "default_models"
DEFAULT_MODELS = [
    {"id": "standard", "file": "standard.json", "label": "Standard (pooled Gaussian PSF)", "recommended": True,
     "summary": "PSF learned from five experiments (QC, EPVIII05, bubble, qc_perct, accperct). "
                "Best or tied on every one in held-out tests. Use this."},
    {"id": "qc_psf", "file": "qc_psf.json", "label": "Cross-check (QC-only Gaussian PSF)", "recommended": False,
     "summary": "PSF learned only from sparse QC dots. Run it to check that a result doesn't depend on "
                "which PSF was learned."},
]
_BY_ID = {m["id"]: m for m in DEFAULT_MODELS}
store = CalibrationStore()


def model_path(model_id: str) -> Path:
    if model_id not in _BY_ID:
        raise ValueError(f"unknown model {model_id!r}; choose one of {list(_BY_ID)}")
    return DEFAULT_DIR / _BY_ID[model_id]["file"]


def resolve_model_path(path: str | Path, run_dir: Path | None = None) -> Path:
    """The model file a run used.

    App runs save an absolute path (``<run>/model.json``). Script runs save one relative to the repo
    (``models/...``); the repo is found from the run's ``config.json`` (its ``paths`` file sits in the
    repo root), which also works in the standalone app, whose own code isn't in the repo.
    """
    path = Path(path)
    if path.is_absolute():
        return path
    roots = [Path(run_dir).resolve().parent.parent] if run_dir is not None else []   # <repo>/results/<run>
    if run_dir is not None:
        try:
            paths_file = Path(json.loads((Path(run_dir) / "config.json").read_text())["settings"]["paths"])
            if paths_file.is_absolute():
                roots.append(paths_file.parent)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    roots.append(REPO_ROOT)
    for root in roots:
        if (root / path).is_file():
            return root / path
    raise FileNotFoundError(f"model {path} not found (looked in {', '.join(str(r) for r in roots)})")


def calibration_for(model_id: str, experiment: str) -> dict | None:
    """The user's saved calibration if any, else the built-in one, else None."""
    mine = store.find(model_id, experiment)
    if mine:
        return {**mine, "source": "yours"}
    built_in = SinglePointModel.load(model_path(model_id)).calibrations.get(experiment)
    if built_in:
        return {"gain": built_in[0], "offset": built_in[1], "source": "built-in"}
    return None


def list_models(experiment: str | None = None) -> list[dict]:
    out = []
    for m in DEFAULT_MODELS:
        cal = calibration_for(m["id"], experiment) if experiment else None
        if cal:
            cal["zero_point_rfu"] = -cal["offset"] / cal["gain"]
        out.append({**{k: m[k] for k in ("id", "label", "summary", "recommended")}, "calibration": cal})
    return out


def built_in_calibrations() -> dict[str, dict[str, tuple[float, float]]]:
    return {m["id"]: SinglePointModel.load(model_path(m["id"])).calibrations for m in DEFAULT_MODELS}


def write_run_model(model_id: str, experiment: str, path: Path) -> Path:
    """Save the model a run uses (built-in shape + this experiment's calibration) into the run folder.

    The run then stays self-contained: its report and image viewer read this file, even if the saved
    calibration is later deleted.
    """
    cal = calibration_for(model_id, experiment)
    if cal is None:
        raise ValueError(f"no calibration of {model_id!r} for {experiment}; calibrate first")
    model = SinglePointModel.load(model_path(model_id))
    model.with_calibration(experiment, cal["gain"], cal["offset"]).save(path)
    return path
