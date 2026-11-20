"""See a corrected image: real vs simulated, before and after, for any crop of any corrected tile.

Nothing simulated is stored on disk; a crop is re-rendered from the run's saved
per-image table (positions, starting and corrected flux) and background
coefficients, exactly as ``correction.reconstruct_image`` does for a whole
tile, but only for the crop (a renderer for a 128 px window takes well under a
second; Voronoi territories are computed with a margin around the window, so
the crop matches the whole-image fit).

Per tile, the real image, the full background and the table are loaded once and
kept for the next crops (one tile at a time, ~250 MB).
"""

import io
import json
import threading
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import PowerNorm, TwoSlopeNorm  # noqa: E402

from correction import output_paths, spline_background_basis  # noqa: E402
from correction.image_correction_gradient_descent import make_renderer  # noqa: E402
from simulator import SinglePointModel  # noqa: E402
from utils import load_experiment, read_image, subtract_baseline  # noqa: E402

from . import layout  # noqa: E402

layout.install()

from .model_catalog import resolve_model_path  # noqa: E402
from .pipeline.plots import DIVERGING, SURFACE  # noqa: E402
from .pipeline.report import experiment_folder, experiment_root  # noqa: E402

CROP_SIZES = (64, 128, 256)


@dataclass
class TileState:
    key: tuple
    real: np.ndarray
    background: np.ndarray
    table: pd.DataFrame
    model: SinglePointModel
    summary: dict


def _png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return buffer.getvalue()


def _r2(real: np.ndarray, sim: np.ndarray) -> float:
    return float(1 - ((real - sim) ** 2).sum() / max(((real - real.mean()) ** 2).sum(), 1e-12))


class Viewer:
    def __init__(self):
        self._lock = threading.Lock()
        self._tile: TileState | None = None

    def forget(self, run_dir: Path) -> None:
        """Drop the cached tile if it belongs to ``run_dir`` (the run was deleted)."""
        with self._lock:
            if self._tile and self._tile.key[0] == str(run_dir):
                self._tile = None

    def _load(self, run_dir: Path, cycle: str, tile: str) -> TileState:
        key = (str(run_dir), cycle, tile)
        if self._tile and self._tile.key == key:
            return self._tile
        self._tile = None                                   # free the previous tile before loading the next
        name = experiment_folder(run_dir).name
        root = experiment_root(run_dir, name)
        if root is None or not root.is_dir():
            raise FileNotFoundError(f"experiment folder for {name} not found (is the drive mounted?)")
        table_path, summary_path = output_paths(run_dir, name, cycle, tile)
        summary = json.loads(summary_path.read_text())
        real = subtract_baseline(read_image(load_experiment(root).image_path(cycle, tile)))
        h, w = real.shape
        coef = np.load(table_path.with_suffix(".background.npy"))
        background = (spline_background_basis(h, w, summary["background_spacing"]) @ coef).reshape(h, w)
        table = pd.read_feather(table_path, columns=["x", "y", "source", "flux_start", "flux_corrected",
                                                     "rfu_start", "rfu_corrected"])
        self._tile = TileState(key, real.astype(np.float32), background.astype(np.float32), table,
                               SinglePointModel.load(resolve_model_path(summary["model"], run_dir)), summary)
        return self._tile

    def overview(self, run_dir: str | Path, cycle: str, tile: str) -> dict:
        """A small picture of the whole tile, for choosing where to zoom."""
        with self._lock:
            state = self._load(Path(run_dir), cycle, tile)
            h, w = state.real.shape
            step = max(h, w) // 640
            small = state.real[: h - h % step, : w - w % step].reshape(h // step, step, w // step, step).mean(axis=(1, 3))
            lo, hi = np.percentile(small, [1, 99.7])
            buffer = io.BytesIO()
            plt.imsave(buffer, np.clip((small - lo) / max(hi - lo, 1e-9), 0, 1), cmap="gray", format="png")
            return {"png": buffer.getvalue(), "width": w, "height": h, "summary": state.summary}

    def crop(self, run_dir: str | Path, cycle: str, tile: str, x0: int, y0: int, size: int) -> dict:
        """Six panels for one crop, plus the crop's fit numbers."""
        if size not in CROP_SIZES:
            raise ValueError(f"crop size must be one of {CROP_SIZES}")
        with self._lock:
            state = self._load(Path(run_dir), cycle, tile)
            h, w = state.real.shape
            x0, y0 = int(np.clip(x0, 0, w - size)), int(np.clip(y0, 0, h - size))
            window = (x0, y0, size, size)
            t, s = state.table, state.summary
            renderer = make_renderer(state.model, t[["x", "y"]].to_numpy(), t["flux_start"].to_numpy(), window=window,
                                     renderer=s.get("renderer", "additive"), softness=s.get("softness", 1.0))
            cols = renderer.cluster_index
            bg = state.background[y0:y0 + size, x0:x0 + size]
            real = state.real[y0:y0 + size, x0:x0 + size]
            before = renderer.render(t["flux_start"].to_numpy()[cols]) + bg
            after = renderer.render(t["flux_corrected"].to_numpy()[cols]) + bg
            inside = t[(t.x >= x0) & (t.x < x0 + size) & (t.y >= y0) & (t.y < y0 + size) & (t.source == "feather")]
            png = self._figure(real, before, after, inside, x0, y0, size)
            change = inside["rfu_corrected"] - inside["rfu_start"]
            return {"png": png, "x0": x0, "y0": y0, "size": size,
                    "stats": {"r2_feather": _r2(real, before), "r2_corrected": _r2(real, after),
                              "clusters": len(inside), "median_rfu_start": float(inside["rfu_start"].median()),
                              "median_rfu_change": float(change.median()) if len(inside) else None}}

    @staticmethod
    def _figure(real, before, after, inside, x0, y0, size) -> bytes:
        fig, axes = plt.subplots(2, 3, figsize=(9.6, 6.8), layout="constrained")
        norm = PowerNorm(0.5, vmin=max(float(np.percentile(real, 1)), 0), vmax=float(np.percentile(real, 99.8)))
        extent = (x0 - 0.5, x0 + size - 0.5, y0 + size - 0.5, y0 - 0.5)
        for ax, image, title in [(axes[0, 0], real, "Real image"), (axes[0, 1], before, "Simulated from Feather RFU"),
                                 (axes[0, 2], after, "Simulated after correction")]:
            ax.imshow(image, cmap="gray", norm=norm, extent=extent)
            ax.set_title(title, loc="left")
        lim = float(np.percentile(np.abs(real - before), 99)) or 1.0
        for ax, residual, title in [(axes[1, 1], real - before, "Residual, Feather"),
                                    (axes[1, 2], real - after, "Residual, corrected")]:
            im = ax.imshow(residual, cmap=DIVERGING, vmin=-lim, vmax=lim, extent=extent)
            ax.set_title(title, loc="left")
        fig.colorbar(im, ax=axes[1, 2], shrink=0.85, label="counts (red: real is brighter)")
        ax = axes[1, 0]
        ax.imshow(real, cmap="gray", norm=norm, extent=extent, alpha=0.55)
        change = (inside["rfu_corrected"] - inside["rfu_start"]).to_numpy()
        span = float(np.percentile(np.abs(change), 98)) if len(change) else 1.0
        sc = ax.scatter(inside["x"], inside["y"], c=change, cmap=DIVERGING,
                        norm=TwoSlopeNorm(0, -span or -1, span or 1), s=22 if size <= 128 else 8,
                        edgecolors=SURFACE, linewidths=0.4)
        ax.set(xlim=extent[:2], ylim=extent[2:])
        ax.set_title("Change per cluster", loc="left")
        fig.colorbar(sc, ax=ax, shrink=0.85, label="RFU change (blue: lost light)")
        for a in axes.ravel():
            a.grid(False)
            a.tick_params(labelsize=8)
            for side in ("top", "right"):
                a.spines[side].set_visible(True)
        return _png(fig)
