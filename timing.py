"""How long a run will take, from earlier runs on this computer, and how many workers fit in memory.

**Before a run.** Every finished correction run folder (``results/*/<exp>/summary.csv``
plus ``config.json``) records seconds per image, the number of workers and how
many sources each image had. The estimate picks the past run closest in image
model, workers and density, scales its seconds per image by density, and
multiplies by ``ceil(images / workers)``. The basis is reported, so the number
is never a mystery. With no history, measured defaults from AGENT.md are used.

**During a run.** Once each worker has finished an image, the observed wall time
per image replaces the prior (cached images are skipped in that average).

**Memory.** Each worker holds one whole image's sparse model: about 5 GB for an
EPVIII05 tile (334k sources, additive) and 7.6 GB for a qc_perct tile (913k
sources, Voronoi). The rule of thumb below is fitted to those two numbers.
"""

import json
import math
import os
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd
import psutil

from .config import RESULTS_DIR

# Seconds per image with no history (AGENT.md: qc_perct tile 2101, ~913k sources, 1 worker).
DEFAULT_SECONDS = {"voronoi": 64.0, "additive": 113.0}
DEFAULT_SOURCES = 913_000
CALIBRATION_SECONDS_PER_IMAGE = 20.0
REPORT_SECONDS = 60.0


def memory_per_worker_gb(sources_per_image: float, renderer: str) -> float:
    per_million = 6.7 if renderer == "voronoi" else 11.0
    return max(2.0, 1.5 + per_million * sources_per_image / 1e6)


def machine() -> dict:
    mem = psutil.virtual_memory()
    return {"cpus": os.cpu_count() or 1, "memory_gb": round(mem.total / 2**30, 1),   # GiB, as macOS reports it
            "available_gb": round(mem.available / 2**30, 1)}


def recommended_workers(sources_per_image: float, renderer: str) -> int:
    m = machine()
    by_memory = int(0.8 * m["memory_gb"] // memory_per_worker_gb(sources_per_image, renderer))
    return max(1, min(m["cpus"] - 1, by_memory))


@lru_cache(maxsize=64)
def _run_record(summary_path: str, mtime: float) -> dict | None:
    summary_path = Path(summary_path)
    try:
        settings = json.loads((summary_path.parent.parent / "config.json").read_text())["settings"]
        frame = pd.read_csv(summary_path)
    except (OSError, ValueError, KeyError):
        return None
    fresh = frame[frame["status"] == "done"]
    if len(fresh) < 3 or "seconds" not in fresh:
        return None
    return {"run": summary_path.parent.parent.name, "renderer": settings.get("renderer", "additive"),
            "workers": int(settings.get("workers") or 1), "seconds": float(fresh["seconds"].median()),
            "sources": float(fresh["sources"].median()), "images": len(fresh)}


def history(folders: list[Path] | None = None) -> list[dict]:
    """One record per past correction run (in any run folder) with at least three freshly fitted images."""
    records = []
    for path in (p for folder in folders or [RESULTS_DIR] for p in folder.glob("*_correct_*/*/summary.csv")):
        record = _run_record(str(path), path.stat().st_mtime)
        if record:
            records.append(record)
    return records


def seconds_per_image(renderer: str, workers: int, sources: float,
                      folders: list[Path] | None = None) -> tuple[float, str]:
    """Expected seconds for one image while ``workers`` run side by side, and where the number comes from."""
    records = [r for r in history(folders) if r["renderer"] == renderer]
    if not records:
        base = DEFAULT_SECONDS.get(renderer, DEFAULT_SECONDS["additive"])
        return base * sources / DEFAULT_SOURCES, f"default for {renderer} (no earlier run on this computer)"
    best = min(records, key=lambda r: (abs(r["workers"] - workers), abs(math.log(max(sources, 1) / r["sources"]))))
    contention = 1 + 0.06 * (workers - best["workers"])        # shared memory bandwidth slows each worker a little
    seconds = best["seconds"] * sources / best["sources"] * max(contention, 0.5)
    return seconds, f"run {best['run']} ({best['workers']} workers, {best['seconds']:.0f} s per image)"


def estimate(*, renderer: str, workers: int, images: int, sources: float, calibration_images: int = 0,
             folders: list[Path] | None = None) -> dict:
    """Wall-clock estimate for a whole run, plus a table of the same run with other worker counts."""
    workers = max(1, int(workers))
    m = machine()

    def wall(w: int) -> float:
        per, _ = seconds_per_image(renderer, w, sources, folders)
        return math.ceil(images / w) * per + calibration_images * CALIBRATION_SECONDS_PER_IMAGE + REPORT_SECONDS

    per, basis = seconds_per_image(renderer, workers, sources, folders)
    mem = memory_per_worker_gb(sources, renderer)
    best = recommended_workers(sources, renderer)
    options = sorted({1, 2, max(1, best - 1), best, best + 1, workers} - {0})
    return {"seconds": wall(workers), "seconds_per_image": per, "basis": basis, "memory_per_worker_gb": round(mem, 1),
            "recommended_workers": best, "machine": m,
            "options": [{"workers": w, "seconds": wall(w), "memory_gb": round(w * mem, 1),
                         "fits": w * mem <= 0.8 * m["memory_gb"]} for w in options]}


class StageClock:
    """Live ETA for one stage: observed wall time per item once every worker has finished one, else the prior."""

    def __init__(self, total: int, prior_seconds_per_item: float, workers: int = 1):
        self.total, self.prior, self.workers = total, prior_seconds_per_item, max(1, workers)
        self.started, self.done, self.fresh = time.time(), 0, 0

    def item(self, *, cached: bool = False) -> None:
        self.done += 1
        self.fresh += not cached

    def remaining_seconds(self) -> float:
        left = max(self.total - self.done, 0)
        if self.fresh >= self.workers:
            return left * (time.time() - self.started) / self.fresh
        return math.ceil(left / self.workers) * self.prior
