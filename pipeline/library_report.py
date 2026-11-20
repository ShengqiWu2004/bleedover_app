"""Library analysis of a finished correction run: group clusters by library member, compare before and after.

Each library member (one designed sequence, see ``bleedover_app.library``) has
many replicate clusters on the flowcell. They carry the same molecule, so they
should be equally bright; the spread between them is measurement noise, and
part of it is bleedover from whichever neighbours each replicate happens to
have. Correction should therefore keep each member's typical signal but
**tighten its replicates**.

Values are compared on one light scale: RFU above zero light (``RFU − zero
point``, with the zero point ``−offset / gain`` of the run's calibration). For
corrected values that is exactly the fitted light; for Feather values it is
the light the original measurement implies. Spread is the **normalized SD**
(SD ÷ mean of a member's replicates, i.e. every member scaled to a mean of 1),
so the overall drop in RFU after correction doesn't shrink it by itself.

Only trusted clusters count (inside the image and ≥ 100 px inside Feather's
coverage, judged in each tile's first corrected cycle), and only members with
at least ``min_replicates`` of them. Outputs in ``<run>/app_report/library/``.
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from simulator import SinglePointModel
from utils import cluster_keys

from ..config import REPORT_DIRNAME
from ..library import extract_members, read_sample, replicate_summary
from ..model_catalog import resolve_model_path
from . import library_plots, library_stats, plots
from .events import emit
from .report import experiment_folder, experiment_root

COVERAGE_PX = 100


def _trusted_keys(folder: Path, ok: pd.DataFrame) -> set[str]:
    keys = set()
    for tile, rows in ok.groupby("tile"):
        table = pd.read_feather(folder / rows["cycle"].iloc[0] / f"{tile}.feather",
                                columns=["key", "source", "interior", "coverage_px"])
        keep = (table["source"] == "feather") & table["interior"] & (table["coverage_px"] >= COVERAGE_PX)
        keys.update(table.loc[keep, "key"])
    return keys


def _member_stats(values: pd.DataFrame, codes: np.ndarray) -> dict[str, pd.DataFrame]:
    grouped = values.groupby(codes)
    mean = grouped.mean()
    return {"mean": mean, "median": grouped.median(), "cv": grouped.std() / mean.where(mean > 0)}


def build(run_dir: str | Path, config: dict) -> dict:
    run_dir = Path(run_dir)
    folder = experiment_folder(run_dir)
    name = folder.name
    root = experiment_root(run_dir, name)
    if root is None or not root.is_dir():
        raise FileNotFoundError(f"experiment folder of {name} not found (is the drive mounted?)")
    summary = pd.read_csv(folder / "summary.csv", dtype={"tile": str})
    ok = summary[summary["status"].isin(["done", "cached"])]
    cycles = list(dict.fromkeys(ok["cycle"]))
    gain, offset = SinglePointModel.load(resolve_model_path(ok["model"].iloc[0], run_dir)).calibrations[name]
    zero = -offset / gain

    emit("log", message=f"library: reading {config['family']} reads and finding library members")
    corrected = pd.read_feather(folder / "corrected_results.feather")
    columns = [c for c in corrected.columns if c.rsplit("_", 1)[0] in cycles]
    frame = read_sample(root / "img_results" / "results.feather", config["family"], extra=columns)
    reads = len(frame)
    frame["member"] = extract_members(frame["seq"], config["template"])
    frame["key"] = cluster_keys(frame).to_numpy()
    matched = frame["member"].notna()
    trusted = _trusted_keys(folder, ok)
    frame = frame[matched & frame["key"].isin(trusted)].drop_duplicates("key")
    corrected = corrected.set_index("key").reindex(frame["key"])[columns]

    feather_light = frame[columns].astype("float32").to_numpy() - zero
    corrected_light = corrected.astype("float32").to_numpy() - zero
    labels = [c.rsplit("_", 1)[0] for c in columns]
    codes, members = pd.factorize(frame["member"])
    replicates = np.bincount(codes)
    enough = replicates >= config["min_replicates"]
    emit("log", message=f"library: {len(frame):,} trusted clusters of {matched.sum():,} matching reads, "
                        f"{len(members):,} members ({enough.sum():,} with ≥ {config['min_replicates']} replicates)")
    before = _member_stats(pd.DataFrame(feather_light, columns=labels), codes)
    after = _member_stats(pd.DataFrame(corrected_light, columns=labels), codes)

    rows = []
    for cycle in labels:
        both = enough & (before["mean"][cycle] > 0).to_numpy() & (after["mean"][cycle] > 0).to_numpy()
        fb, fa = before["median"][cycle][both], after["median"][cycle][both]
        rows.append({"cycle": cycle, "members": int(both.sum()),
                     "median_signal_feather": float(fb.median()), "median_signal_corrected": float(fa.median()),
                     "median_ratio": float((fa / fb).median()),
                     "rank_agreement": float(fb.rank().corr(fa.rank())) if both.sum() > 2 else None,
                     "median_cv_feather": float(before["cv"][cycle][both].median()),
                     "median_cv_corrected": float(after["cv"][cycle][both].median())})
    per_cycle = pd.DataFrame(rows)
    show = per_cycle.loc[per_cycle["median_signal_feather"].idxmax(), "cycle"]
    mask = enough & (before["mean"][show] > 0).to_numpy() & (after["mean"][show] > 0).to_numpy()

    out = run_dir / REPORT_DIRNAME / "library"
    out.mkdir(parents=True, exist_ok=True)
    col = labels.index(show)
    rng = np.random.default_rng(0)
    within = {name: library_stats.within_sequence(light[:, col], codes, stats["mean"][show].to_numpy(), mask, rng)
              for name, light, stats in (("feather", feather_light, before), ("corrected", corrected_light, after))}
    grid = library_stats.base_grid(members, before["median"][show].to_numpy(), after["median"][show].to_numpy(), mask)
    cv_before, cv_after = before["cv"][show][mask], after["cv"][show][mask]
    tighter = float(np.mean(cv_after.to_numpy() < cv_before.to_numpy())) if mask.any() else None
    figures = {"replicates.png": library_plots.replicates(replicates, config["min_replicates"]),
               "member_medians.png": library_plots.member_medians(before["median"][show][mask],
                                                                  after["median"][show][mask], show),
               "member_cv.png": library_plots.cv_distribution(cv_before, cv_after, show),
               "cv_each.png": library_plots.cv_each_sequence(cv_before, cv_after, show, tighter),
               "within.png": library_plots.within_sequence(within["feather"], within["corrected"], show),
               "cv_by_cycle.png": library_plots.cv_by_cycle(per_cycle)}
    if grid:
        figures["bases.png"] = library_plots.base_heatmaps(grid, show)
    for file, fig in figures.items():
        plots.save(fig, out / file)

    long = pd.concat({version: pd.concat({s: stats[s].stack() for s in ("mean", "median", "cv")}, axis=1)
                      for version, stats in (("feather", before), ("corrected", after))}, axis=1)
    long.columns = [f"{v}_{s}" for v, s in long.columns]
    long.index.names = ["code", "cycle"]
    long = long.reset_index()
    code = long.pop("code").to_numpy()
    long.insert(0, "member", members[code])
    long.insert(1, "replicates", replicates[code])
    long.to_feather(out / "by_member.feather")
    long[long["cycle"] == show].to_csv(out / f"by_member_{show}.csv", index=False)

    result = {"created": time.strftime("%Y-%m-%d %H:%M"), "config": config, "zero_point_rfu": zero,
              "reads": reads, "matched_reads": int(matched.sum()), "trusted_clusters": int(len(frame)),
              "replicates": replicate_summary(replicates), "members_used": int(enough.sum()), "shown_cycle": show,
              "tighter_fraction": tighter, "has_base_grid": bool(grid),
              "within_sd": {k: float(np.std(v)) for k, v in within.items()},
              "per_cycle": per_cycle.round(4).to_dict("records"),
              "files": {"table": "by_member.feather", "csv": f"by_member_{show}.csv"}}
    (out / "library.json").write_text(json.dumps(result, indent=1, default=float))
    return result
