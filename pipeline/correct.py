"""Correct every chosen image of an experiment, reporting each image as it finishes.

This mirrors ``correction.correct_experiment`` exactly: same per-image function
(``correction.correct_one``), same outputs (``<cycle>/<tile>.feather/.json/.background.npy``,
``summary.csv``, ``corrected_results.feather``, ``metrics.json``), same resume
rule (images saved with the same model and settings are skipped). The only
difference is that it emits a progress event per image, which the library
function doesn't offer, and that it fits an explicit list of (cycle, tile)
images, so unaligned tiles are never attempted.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from correction import ImageSettings, combine_corrections, correct_one, correction_metrics
from simulator import SinglePointModel
from utils import write_metrics

from .. import layout
from .events import emit


def _settings(options: dict) -> ImageSettings:
    return ImageSettings(prior=float(options["prior"]), background_spacing=float(options["background_spacing"]),
                         steps=int(options["steps"]), renderer=options["renderer"], softness=float(options["softness"]))


def run(job: dict, model_path: str, run_dir: Path) -> dict:
    root, options = Path(job["root"]), job["correct"]
    model = SinglePointModel.load(model_path)
    if root.name not in model.calibrations:
        raise ValueError(f"{Path(model_path).name} has no calibration for {root.name}; tick 'Calibrate' and rerun")
    settings, workers = _settings(options), max(1, int(options["workers"]))
    images = [(str(c), str(t)) for c, t in job["images"]]
    cycles = list(dict.fromkeys(c for c, _ in images))
    kwargs = dict(channel=job.get("channel", "GG"), overwrite=bool(options.get("overwrite", False)))
    emit("progress", stage="correct", done=0, total=len(images), workers=workers)
    rows = []

    def record(image, summary):
        rows.append(summary)
        emit("image", stage="correct", done=len(rows), total=len(images), cycle=image[0], tile=image[1],
             status=summary["status"].split(":")[0], detail=summary["status"], seconds=summary.get("seconds"),
             r2_start=summary.get("r2_start"), r2_end=summary.get("r2_end"))

    def failed(image, error):
        return {"experiment": root.name, "cycle": image[0], "tile": image[1], "status": f"failed: {error!r}"}

    if workers == 1:
        for image in images:
            try:
                record(image, correct_one(root, *image, model_path, run_dir, settings, **kwargs))
            except Exception as error:      # one bad image shouldn't stop a 400-image run
                record(image, failed(image, error))
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=layout.install) as pool:
            futures = {pool.submit(correct_one, root, *image, model_path, run_dir, settings, **kwargs): image
                       for image in images}
            for future in as_completed(futures):
                try:
                    record(futures[future], future.result())
                except Exception as error:
                    record(futures[future], failed(futures[future], error))

    summary = pd.DataFrame(rows)
    order = summary["cycle"].map({c: i for i, c in enumerate(cycles)})
    summary = summary.iloc[np.lexsort((summary["tile"], order))].reset_index(drop=True)
    folder = run_dir / root.name
    folder.mkdir(parents=True, exist_ok=True)
    summary.to_csv(folder / "summary.csv", index=False)
    if not summary["status"].isin(["done", "cached"]).any():
        raise RuntimeError(f"no image was corrected; first error: {summary['status'].iloc[0]}")
    emit("log", message="combining images into corrected_results.feather")
    combine_corrections(run_dir, root.name, channel=kwargs["channel"], cycles=cycles)
    metrics = correction_metrics(run_dir, root.name)
    write_metrics(run_dir, metrics)
    return metrics
