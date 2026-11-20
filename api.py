"""What each button in the app does, as plain functions of JSON in -> JSON out (``server`` does the HTTP).

Kept free of HTTP details so the behaviour can be tested and reused directly.
"""

import json
import math
import shutil

import pandas as pd
from pathlib import Path

from utils import new_run_dir, write_config

from . import fastq, library, run_index, timing
from .config import RESULTS_DIR, REPORT_DIRNAME, Prefs, default_browse_dir, run_folders
from .dialogs import choose_folder
from .experiment_info import inspect_experiment, origin_summary, read_exp_details
from .jobs import JobManager
from .model_catalog import built_in_calibrations, list_models, store, write_run_model, DEFAULT_MODELS
from .roles import lit_roles

prefs = Prefs()
jobs = JobManager()
libraries = library.LibraryStore()


def state() -> dict:
    return {"prefs": prefs.load(), "machine": timing.machine(), "job": jobs.snapshot()}


def browse(body: dict) -> dict:
    current = prefs.load()
    purpose = body.get("purpose", "experiment")
    start = body.get("start") or (current["fastq_library"] if purpose == "library" else current["last_dir"])
    prompt = {"library": "Choose the FASTQ library folder",
              "runs": "Choose a folder that holds correction runs (e.g. imager_bleedover/results)"}.get(
        purpose, "Choose an experiment folder")
    path = choose_folder(prompt, start or default_browse_dir())
    if path and purpose == "library":
        prefs.update({"fastq_library": path, "fastq_mode": "library"})
    if path and purpose == "runs" and path not in current["run_folders"]:
        prefs.update({"run_folders": [*current["run_folders"], path]})
    return {"path": path}


def calibration_defaults(info: dict) -> dict:
    """Sparsest cycles first (fewest lit samples in the alignment matrix), then three tiles spread over the flowcell."""
    matrix = info.get("alignment_matrix")
    cycles = [c for c in info["cycles"] if c["aligned_tiles"]]
    def lit_count(cycle: dict) -> int:
        roles = lit_roles(matrix, cycle["cycle"])
        return 99 if roles is None else len(roles)
    ranked = sorted(cycles, key=lit_count)
    chosen = [c["cycle"] for c in ranked[:3]]
    shared = [t for t in info["device_tiles"] if all(t in c["aligned_tiles"] for c in cycles if c["cycle"] in chosen)]
    tiles = [shared[i] for i in sorted({round(k * (len(shared) - 1) / 2) for k in range(3)})] if shared else []
    return {"cycles": chosen, "tiles": tiles, "max_per_image": 2000}


def inspect(body: dict) -> dict:
    info = inspect_experiment(body["path"])
    prefs.update({"last_dir": str(Path(info["path"]).parent)})      # the folder picker opens here next time
    if "cycles" in info:
        info["calibration_defaults"] = calibration_defaults(info)
        renderer = prefs.load()["renderer"]
        info["recommended_workers"] = timing.recommended_workers(info["clusters_per_tile"], renderer)
        info["memory_per_worker_gb"] = round(timing.memory_per_worker_gb(info["clusters_per_tile"], renderer), 1)
    info["models"] = list_models(info["name"])
    info["fastq"] = resolve_fastq({"path": info["path"]})
    return info


def resolve_fastq(body: dict) -> dict:
    """FASTQ folder in the current mode; ``flowcell_id`` from the user overrides exp_details.txt."""
    changes = {k: body[k] for k in ("fastq_mode", "fastq_library") if k in body}
    current = prefs.update(changes) if changes else prefs.load()
    written = read_exp_details(body["path"])["flowcell_id"]
    typed = (body.get("flowcell_id") or "").strip() or None
    result = fastq.resolve(body["path"], mode=current["fastq_mode"], library=current["fastq_library"],
                           flowcell_id=typed or written)
    return {**result, "library": current["fastq_library"], "flowcell_from_file": written,
            "flowcell_source": "typed" if typed else ("exp_details.txt" if written else None)}


def origins(body: dict) -> dict:
    samples = body.get("fastq_samples")
    return {"origins": origin_summary(body["path"], samples)}


def estimate(body: dict) -> dict:
    return timing.estimate(renderer=body["renderer"], workers=int(body["workers"]), images=int(body["images"]),
                           sources=float(body["sources"]), calibration_images=int(body.get("calibration_images", 0)),
                           folders=run_folders(prefs.load()))


def _images(info: dict, cycles: list[str] | None, tiles: list[str] | None) -> list[tuple[str, str]]:
    return [(c["cycle"], t) for c in info["cycles"] if not cycles or c["cycle"] in cycles
            for t in c["aligned_tiles"] if not tiles or t in tiles]


def run_check(body: dict) -> dict:
    """Before starting: a stopped run of this experiment with the same method, which could be resumed instead."""
    name = Path(body["path"]).name
    found = run_index.experiment_runs(run_folders(prefs.load()), name, None)
    return {"match": run_index.resumable_match(found, run_index.method({"model_id": body["model"],
                                                                        "correct": body["correct"]}))}


def resume(body: dict) -> dict:
    """Continue a stopped run in its own folder with its own settings; finished images are skipped."""
    run_dir = run_folder(body["run"])
    saved = json.loads((run_dir / "app_job.json").read_text())
    return run({"path": saved["root"], "model": saved["model_id"], "calibrate": saved["calibrate"],
                "correct": {**saved["correct"], "workers": body.get("workers", saved["correct"]["workers"])},
                "fastq": saved.get("fastq"), "resume_run": run_dir.name})


def run(body: dict) -> dict:
    """Start calibrate (optional) -> correct -> report for the experiment in ``body['path']``.

    With ``resume_run``, the job runs again in that stopped run's folder: images already saved there are
    skipped, and a calibration it already fitted (``model.json``) is reused.
    """
    if jobs.running():
        raise RuntimeError("A job is already running")
    info = inspect_experiment(body["path"])
    if not info.get("ready"):
        raise ValueError("This experiment can't be corrected yet: " + " ".join(info["problems"]))
    options, calibrate = body["correct"], body["calibrate"]
    images = _images(info, options.get("cycles"), options.get("tiles"))
    if not images:
        raise ValueError("No aligned image matches the chosen cycles and tiles")
    model_id = body["model"]
    calibrated = next(m for m in list_models(info["name"]) if m["id"] == model_id)["calibration"]
    if not calibrate["enabled"] and not calibrated:
        raise ValueError("This model has no calibration for this experiment yet. Tick Calibrate first.")
    prefs.update({"workers": int(options["workers"]), "renderer": options["renderer"]})
    resuming = body.get("resume_run")
    if resuming:
        run_dir = run_folder(resuming)
        old = run_index.read_config(run_dir).get("settings", {})
        if old.get("experiment") != info["name"] or not run_index.same_method(
                run_index.method(old), run_index.method({"model_id": model_id, "correct": options})):
            raise ValueError(f"{resuming} used another experiment or method, so it can't be resumed with these settings")
        if (run_dir / "model.json").exists():         # its calibration (if any) was already fitted: reuse it
            calibrate = {**calibrate, "enabled": False}
    else:
        run_dir = new_run_dir("correct", f"{info['name']}_app_{options['renderer']}", RESULTS_DIR)
    model_file = run_dir / "model.json"
    if calibrate["enabled"]:
        model = None
    else:
        model = str(model_file if model_file.exists() else write_run_model(model_id, info["name"], model_file))
    job = {"kind": "correct", "experiment": info["name"], "root": info["path"], "run_dir": str(run_dir),
           "model_id": model_id, "model": model, "channel": info["channel"], "calibrate": calibrate,
           "correct": options, "images": images, "fastq": body.get("fastq"), "library": libraries.get(info["name"])}
    if not resuming:
        write_config(run_dir, {**{k: v for k, v in job.items() if k != "images"}, "workers": options["workers"],
                               "renderer": options["renderer"], "images": len(images)},
                     argv=["-m", "bleedover_app.pipeline", str(run_dir / "app_job.json")])
    sources = info["clusters_per_tile"]
    priors = {"calibrate": timing.CALIBRATION_SECONDS_PER_IMAGE,
              "correct": timing.seconds_per_image(options["renderer"], int(options["workers"]), sources,
                                                  run_folders(prefs.load()))[0]}
    return jobs.start(job, priors)


def build_report(body: dict) -> dict:
    run_dir = run_folder(body["run"])
    return jobs.start({"kind": "report", "experiment": run_dir.name, "run_dir": str(run_dir)}, {})


def library_get(query: dict) -> dict:
    return {"config": libraries.get(query["experiment"])}


def library_save(body: dict) -> dict:
    return {"config": libraries.set(body["experiment"], body["config"])}


def library_check(body: dict) -> dict:
    """Try the structure on a sample of this sequencing sample's reads."""
    return library.check(body["path"], body["family"], body["template"])


def library_run(body: dict) -> dict:
    """Run the library analysis on a finished run, with the library saved for its experiment."""
    run_dir = run_folder(body["run"])
    experiment = body["experiment"]
    config = libraries.get(experiment)
    if not (config and config.get("enabled")):
        raise ValueError("Turn on the library analysis and describe the library first (card 3 on the left)")
    if not (run_dir / experiment / "summary.csv").exists():
        raise ValueError("The library analysis needs a finished run")
    return jobs.start({"kind": "library", "experiment": experiment, "run_dir": str(run_dir), "library": config}, {})


def library_members(query: dict) -> dict:
    """One row per library sequence (the run's shown cycle): replicates, median signal and normalized SD, before/after.

    ``q`` filters by sequence (case-insensitive substring), ``sort`` picks the column, at most ``limit`` rows.
    """
    folder = run_folder(query["run"]) / REPORT_DIRNAME / "library"
    shown = json.loads((folder / "library.json").read_text())["shown_cycle"]
    table = pd.read_feather(folder / "by_member.feather")
    table = table[table["cycle"] == query.get("cycle", shown)].drop(columns="cycle")
    table["signal_change_pct"] = 100 * (table["corrected_median"] / table["feather_median"] - 1)
    table["nsd_change"] = table["corrected_cv"] - table["feather_cv"]
    if query.get("q"):
        table = table[table["member"].str.contains(query["q"].strip().upper(), regex=False)]
    key = query.get("sort", "replicates")
    if key not in table:
        raise ValueError(f"can't sort by {key!r}")
    table = table.sort_values(key, ascending=query.get("order") == "asc")
    limit = min(int(query.get("limit", 200)), 2000)
    columns = ["member", "replicates", "feather_median", "corrected_median", "signal_change_pct",
               "feather_cv", "corrected_cv", "nsd_change"]
    return {"cycle": query.get("cycle", shown), "total": len(table),
            "rows": finite(table[columns].head(limit).round(4).to_dict("records"))}


def library_result(query: dict) -> dict:
    path = run_folder(query["run"]) / REPORT_DIRNAME / "library" / "library.json"
    if not path.exists():
        raise FileNotFoundError("This run has no library analysis yet")
    return finite(json.loads(path.read_text()))


def cancel(_: dict) -> dict:
    jobs.cancel()
    return jobs.snapshot()


def system(_: dict) -> dict:
    """Built-in models (locked) with their calibrations, the user's saved calibrations, and where things live."""
    built_in = built_in_calibrations()
    return {"models": [{"id": m["id"], "label": m["label"], "summary": m["summary"],
                        "calibrations": [{"experiment": e, "gain": g, "offset": o} for e, (g, o) in built_in[m["id"]].items()]}
                       for m in DEFAULT_MODELS],
            "calibrations": sorted(store.entries(), key=lambda e: e["created"], reverse=True),
            "machine": timing.machine(),
            "paths": {"calibrations": str(store.path), "preferences": str(prefs.path), "runs": str(RESULTS_DIR)},
            "run_folders": [str(f) for f in run_folders(prefs.load())[1:]]}


def remove_run_folder(body: dict) -> dict:
    prefs.update({"run_folders": [f for f in prefs.load()["run_folders"] if f != body["path"]]})
    return system({})


def delete_calibration(body: dict) -> dict:
    store.delete(body["id"])
    return system({})


def save_prefs(body: dict) -> dict:
    return prefs.update(body)


def run_folder(run: str) -> Path:
    """A run, looked up by name in the known run folders only (never an arbitrary path)."""
    for folder in run_folders(prefs.load()):
        path = (folder / Path(run).name).resolve()
        if path.parent == folder.resolve() and path.is_dir():
            return path
    raise FileNotFoundError(f"no run {run!r} in the run folders (add its folder in ⚙ System)")


def runs(query: dict) -> dict:
    """Every version of this experiment's correction (one run folder per method), newest first."""
    current = jobs.snapshot()
    running = current.get("run_dir") if current.get("status") == "running" else None
    return {"runs": run_index.experiment_runs(run_folders(prefs.load()), query["experiment"], running)}


def delete_run(body: dict) -> dict:
    """Delete one run folder of the browsed experiment (never one that is running); returns the runs left."""
    experiment = body["experiment"]
    listed = {r["run"]: r for r in runs({"experiment": experiment})["runs"]}
    entry = listed.get(body["run"])
    if entry is None:
        raise FileNotFoundError(f"{body['run']} is not a run of {experiment}")
    if entry["status"] == "running":
        raise RuntimeError("This run is in progress; stop it before deleting it")
    run_dir = run_folder(body["run"])
    shutil.rmtree(run_dir)
    viewer_forget(run_dir)
    return runs({"experiment": experiment})


def viewer_forget(run_dir: Path) -> None:
    """Hook set by the server so the image viewer drops a deleted run from its cache."""


def run_images(query: dict) -> dict:
    """Images a run has corrected so far."""
    run_dir = run_folder(query["run"])
    return {"run": run_dir.name, "images": run_index.saved_images(run_dir)}


def report(query: dict) -> dict:
    path = run_folder(query["run"]) / REPORT_DIRNAME / "report.json"
    if not path.exists():
        raise FileNotFoundError("This run has no report yet")
    data = finite(json.loads(path.read_text()))
    return {**data, "run": Path(data["run_dir"]).name}


def report_file(query: dict) -> Path:
    """A report figure: ``<run>/app_report/<name>.png`` or, for the library analysis, ``library/<name>.png``."""
    folder = run_folder(query["run"]) / REPORT_DIRNAME
    if query.get("part") == "library":
        folder = folder / "library"
    path = (folder / Path(query["name"]).name).resolve()
    if path.parent != folder.resolve() or path.suffix != ".png" or not path.exists():
        raise FileNotFoundError(query["name"])
    return path


def finite(value):
    """NaN/inf -> None so the page always gets valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    return value
