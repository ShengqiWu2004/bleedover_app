"""Fit this experiment's ``counts = gain × RFU + offset`` line, keeping a base model's PSF shape.

The recipe is the one in ``notebooks/261117_accperct_calibration.ipynb``:

1. Pick **single points**: clusters that are lit (a detected peak within 1.5 px)
   and at least 6 px from any other light source (``simulator.collect_single_points``).
2. **Isolation is judged against lit sources only** when ``alignment_matrix.json``
   says which samples carry dye in the calibration cycles. On dense flowcells
   almost no cluster is 6 px from *every* cluster, but most neighbours are dark.
   Lit samples are trusted by their index (FM reads fail whole-read quality).
   Without a matrix, the classic rule is used: every cluster counts as a
   neighbour, and trusted clusters pass the read-quality filter.
3. Fit each dot's flux in image counts with the base model's shape, then a
   straight line of flux against Feather RFU.

The PSF is the only part of the model used here; the image model (additive or
Voronoi) plays no part, because an isolated dot has no neighbours to share
light or territory with. So one calibration serves both image models.

The line is saved to the app's calibration store right away (before the
correction starts, so a failed correction doesn't lose it), and the run's
model (built-in shape + this line) is written to ``<run>/model.json``.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from simulator import SinglePointModel, calibrate_linear, collect_single_points, evaluate, fit_flux
from utils import load_experiment, read_dataframe

from ..config import REPORT_DIRNAME
from ..model_catalog import model_path, store
from ..roles import family_role, lit_roles, read_alignment_matrix, sample_family
from . import plots
from .events import emit

MIN_DOTS = 200


def _cluster_sets(exp, cycles: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, str, list[str]]:
    """(clusters placed on the image, trusted clusters, recipe name, lit roles)."""
    columns = ["origin", "tile", "ID", "x", "y", *(exp.intensity_column(c) for c in cycles)]
    clusters = pd.read_feather(exp.results_path, columns=columns)
    matrix = read_alignment_matrix(exp.root)
    lit = [lit_roles(matrix, c) for c in cycles]
    if all(roles for roles in lit):
        roles = set.union(*lit)
        origin = clusters["origin"].astype(str)
        role = origin.map({o: family_role(sample_family(o)) for o in origin.unique()})
        mine = clusters[role.isin(roles).to_numpy()]
        return mine, mine, "lit sources only (alignment_matrix.json)", sorted(roles)
    trusted = read_dataframe(exp.results_path)
    return clusters, trusted, "every cluster, read-quality filtered", []


def run(job: dict, run_dir: Path) -> str:
    options = job["calibrate"]
    exp = load_experiment(job["root"])
    model_id = job["model_id"]
    base = SinglePointModel.load(model_path(model_id))
    cycles, tiles = list(options["cycles"]), [str(t) for t in options["tiles"]]
    total = len(cycles) * len(tiles)
    emit("progress", stage="calibrate", done=0, total=total, workers=1)
    shown, trusted, recipe, roles = _cluster_sets(exp, cycles)
    emit("log", message=f"calibration: {len(trusted):,} candidate clusters ({recipe})")

    done = []

    def on_image(cycle, tile, kept):
        done.append(kept)
        emit("image", stage="calibrate", done=len(done), total=total, cycle=cycle, tile=tile, status="done",
             detail=f"{kept:,} single points")

    data = collect_single_points(exp, shown, trusted, cycles, tiles, max_per_image=int(options["max_per_image"]),
                                 on_image=on_image)
    data = data.subset(np.flatnonzero(np.isfinite(data.rfu)))
    if len(data) < MIN_DOTS:
        raise ValueError(f"only {len(data)} single points found (need {MIN_DOTS}); choose sparser cycles or more tiles")
    flux = fit_flux(base, data, np.full(len(data), float(np.median(base.flux_centers))))
    gain, offset = calibrate_linear(flux, data.rfu)
    model = base.with_calibration(exp.root.name, gain, offset)
    out = run_dir / "model.json"
    model.save(out)

    sample = np.random.default_rng(0).choice(len(data), min(len(data), 3000), replace=False)
    fit = evaluate(model, data.subset(np.sort(sample)))
    report_dir = run_dir / REPORT_DIRNAME
    report_dir.mkdir(parents=True, exist_ok=True)
    plots.save(plots.calibration(data.rfu, flux, gain, offset, model.calibrations, exp.root.name),
               report_dir / "calibration.png")
    record = {"model": str(out), "model_id": model_id, "gain": gain, "offset": offset,
              "zero_point_rfu": -offset / gain, "single_points": len(data), "recipe": recipe, "lit_roles": roles,
              "cycles": cycles, "tiles": tiles, "median_r2_shape": float(fit["shape_r2"].median()),
              "median_r2_generative": float(fit["generative_r2"].median())}
    (report_dir / "calibration.json").write_text(json.dumps(record, indent=1))
    store.add(model_id=model_id, experiment=exp.root.name, gain=gain, offset=offset, single_points=len(data),
              recipe=recipe, cycles=cycles, tiles=tiles, median_r2=record["median_r2_generative"], run=run_dir.name)
    emit("log", message=f"calibration: counts = {gain:.3f} × RFU + {offset:,.0f} from {len(data):,} dots, saved for later runs")
    return str(out)
