"""The end-of-run report: headline numbers, a per-cycle table and the default figures.

Works on any correction run folder, including runs started from
``scripts/correct_experiment.py``. Figures and ``report.json`` go to
``<run>/app_report/``.

Cluster-level numbers use **trusted** Feather clusters only (inside the image
and >= 100 px inside Feather's coverage, as in ``correction.correction_metrics``),
from a sample of images: one tile per cycle, up to ``MAX_IMAGES`` cycles.
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from correction import correction_metrics
from simulator import SinglePointModel
from utils import read_paths

from ..config import REPORT_DIRNAME
from ..model_catalog import resolve_model_path
from ..roles import read_alignment_matrix, lit_roles, family_role, sample_family
from . import plots

MAX_IMAGES, PER_IMAGE, MIN_PER_BIN = 12, 100_000, 200
DISTANCE_EDGES = [0, 1.5, 2, 2.5, 3, 4, 6, np.inf]
COLUMNS = ["key", "source", "x", "y", "rfu_start", "rfu_corrected", "flux_corrected", "interior", "coverage_px"]


def experiment_folder(run_dir: Path) -> Path:
    found = sorted(p.parent for p in run_dir.glob("*/summary.csv"))
    if not found:
        raise FileNotFoundError(f"{run_dir} has no <experiment>/summary.csv: the correction didn't finish")
    return found[0]


def experiment_root(run_dir: Path, name: str) -> Path | None:
    """The experiment folder: the app records ``root``; script runs record the paths file instead."""
    try:
        settings = json.loads((run_dir / "config.json").read_text())["settings"]
    except (OSError, ValueError, KeyError):
        return None
    if settings.get("root"):
        return Path(settings["root"])
    try:
        paths_file = Path(settings["paths"])
        if not paths_file.is_absolute():             # saved relative to the repo the script ran in
            paths_file = run_dir.resolve().parent.parent / paths_file
        return next((r for r in read_paths(paths_file) if r.name == name), None)
    except (OSError, KeyError):
        return None


def _image_sample(path: Path, cycle: str, matrix, rng) -> pd.DataFrame:
    table = pd.read_feather(path, columns=COLUMNS)
    lit = (table["flux_corrected"] >= 1).to_numpy()
    xy = table[["x", "y"]].to_numpy()
    distance, _ = cKDTree(xy[lit]).query(xy, k=2)
    table["nearest_lit_px"] = np.where(lit, distance[:, 1], distance[:, 0])   # a lit cluster finds itself first
    table = table[(table["source"] == "feather") & table["interior"] & (table["coverage_px"] >= 100)]
    if len(table) > PER_IMAGE:
        table = table.iloc[np.sort(rng.choice(len(table), PER_IMAGE, replace=False))]
    family = table["key"].str.split("|", n=1).str[0].map(sample_family)
    roles = lit_roles(matrix, cycle)
    return pd.DataFrame({"cycle": cycle, "family": family.to_numpy(), "feather": table["rfu_start"].to_numpy(),
                         "corrected": table["rfu_corrected"].to_numpy(),
                         "change_pct": 100 * (table["rfu_corrected"] - table["rfu_start"]).to_numpy()
                         / max(float(table["rfu_start"].median()), 1.0),
                         "nearest_lit_px": table["nearest_lit_px"].to_numpy(),
                         "lit": family.map(lambda f: None if roles is None else family_role(f) in roles).to_numpy()})


def cluster_sample(folder: Path, ok: pd.DataFrame, cycles: list[str], matrix) -> pd.DataFrame:
    cycles = [c for c in cycles if (ok["cycle"] == c).any()]      # cycles where every image failed have nothing
    picks = [cycles[i] for i in np.unique(np.linspace(0, len(cycles) - 1, min(len(cycles), MAX_IMAGES)).astype(int))]
    rng, parts = np.random.default_rng(0), []
    for cycle in picks:
        tiles = sorted(ok.loc[ok["cycle"] == cycle, "tile"].astype(str))
        parts.append(_image_sample(folder / cycle / f"{tiles[len(tiles) // 2]}.feather", cycle, matrix, rng))
    return pd.concat(parts, ignore_index=True)


def _distance_table(sample: pd.DataFrame) -> pd.DataFrame:
    bins = pd.cut(sample["nearest_lit_px"], DISTANCE_EDGES, right=False)
    g = sample.groupby(bins, observed=True)["change_pct"]
    table = pd.DataFrame({"median": g.median(), "q25": g.quantile(0.25), "q75": g.quantile(0.75), "n": g.size()})
    table["bin"] = [f"{i.left:g}-{i.right:g}" if np.isfinite(i.right) else f"≥{i.left:g}" for i in table.index]
    return table[table["n"] >= MIN_PER_BIN].reset_index(drop=True)


def _origin_table(sample: pd.DataFrame) -> pd.DataFrame:
    def state(values):
        known = set(values.dropna())
        return "unknown" if not known else ("varies" if len(known) > 1 else ("lit" if known.pop() else "dark"))
    g = sample.groupby("family")
    table = pd.DataFrame({"feather": g["feather"].median(), "corrected": g["corrected"].median(),
                          "clusters": g.size(), "state": g["lit"].agg(state)}).reset_index()
    return table[table["clusters"] >= 50].sort_values(["state", "family"]).reset_index(drop=True)


def _headline(metrics: dict, origins: pd.DataFrame, zero: float) -> list[dict]:
    r2 = metrics["2 fit quality, median R² start -> corrected"]
    change = metrics["3 median RFU change of trusted clusters"]
    out = [{"label": "Images corrected", "value": metrics["1 images corrected"]},
           {"label": "Image explained (median R²)", "value": f"{r2[0]:.2f} → {r2[1]:.2f}",
            "hint": "1.0 means the simulated image accounts for every pixel of the real one"},
           {"label": "Typical cluster change", "value": f"{change['rfu']:+,.0f} RFU"
            + (f" ({100 * change['relative to median Feather RFU']:+.0f}%)" if change.get("relative to median Feather RFU") is not None else ""),
            "hint": "median over trusted clusters; negative = light that belonged to neighbours"},
           {"label": "Clusters set to zero light", "value": f"{100 * (metrics['4 trusted clusters set to zero light'] or 0):.1f}%"}]
    dark = origins[origins["state"] == "dark"]
    if len(dark):
        before = np.average(dark["feather"] - zero, weights=dark["clusters"])
        after = np.average(dark["corrected"] - zero, weights=dark["clusters"])
        if before > 0:
            out.append({"label": "Signal removed from dark samples", "value": f"{100 * (1 - after / before):.0f}%",
                        "hint": "samples marked not lit in alignment_matrix.json; their RFU above zero light is bleedover"})
    return out


def build(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    folder = experiment_folder(run_dir)
    name, out = folder.name, run_dir / REPORT_DIRNAME
    out.mkdir(exist_ok=True)
    summary = pd.read_csv(folder / "summary.csv", dtype={"tile": str})
    ok = summary[summary["status"].isin(["done", "cached"])]
    cycles = list(dict.fromkeys(summary["cycle"]))
    metrics = correction_metrics(run_dir, name)
    model = SinglePointModel.load(resolve_model_path(ok["model"].iloc[0], run_dir))
    gain, offset = model.calibrations[name]
    zero = -offset / gain
    root = experiment_root(run_dir, name)
    matrix = read_alignment_matrix(root) if root else None

    sample = cluster_sample(folder, ok, cycles, matrix)
    distance, origins = _distance_table(sample), _origin_table(sample)
    figures = [("r2.png", plots.r2_by_cycle(ok, cycles)),
               ("feather_vs_corrected.png", plots.feather_vs_corrected(sample["feather"], sample["corrected"], zero)),
               ("change_vs_distance.png", plots.change_vs_distance(distance)),
               ("origins.png", plots.origins(origins, zero))]
    for file, fig in figures:
        plots.save(fig, out / file)
    per_cycle = ok.groupby("cycle", sort=False).agg(
        images=("tile", "size"), r2_start=("r2_start", "median"), r2_corrected=("r2_end", "median"),
        median_rfu_change=("median_rfu_change", "median"), zero_light_pct=("zero_light", "mean"),
        seconds=("seconds", "median")).reset_index()
    per_cycle["zero_light_pct"] *= 100
    calibration = json.loads((out / "calibration.json").read_text()) if (out / "calibration.json").exists() else None
    report = {"experiment": name, "root": str(root) if root else None, "run_dir": str(run_dir),
              "created": time.strftime("%Y-%m-%d %H:%M"), "zero_point_rfu": zero, "gain": gain, "offset": offset,
              "model": str(resolve_model_path(ok["model"].iloc[0], run_dir)), "renderer": str(ok["renderer"].iloc[0]) if "renderer" in ok else "additive",
              "headline": _headline(metrics, origins, zero), "metrics": metrics, "calibration": calibration,
              "sampled_cycles": sorted(sample["cycle"].unique(), key=cycles.index),
              "tables": {"per_cycle": per_cycle.round(3).to_dict("records"), "distance": distance.round(2).to_dict("records"),
                         "origins": origins.round(1).to_dict("records")},
              "images": ok[["cycle", "tile"]].astype(str).to_dict("records"),
              "failed": summary.loc[~summary.index.isin(ok.index), ["cycle", "tile", "status"]].astype(str).to_dict("records")}
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float))
    return report
