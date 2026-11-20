"""Draw the two pictures in the Model and Correction "?" popups, as clean PNGs (no frames, ticks or titles;
the page adds the captions, so they follow light/dark mode).

- ``static/help/psf.png``: the Standard model's point-spread function for a cluster of typical brightness,
  rendered on the camera's pixel grid by ``simulator.psf.render`` (black and white).
- ``static/help/renderers.png``: one crop of ``20261018_qc_perct`` (img_10, tile 2112): the real image, then
  the image simulated after correction by the additive run and by the Voronoi run of the same images.
- ``static/help/footprints.png``: the additive counterpart: each cluster's light footprint (a 2σ circle).
- ``static/help/territory.png``: the same crop in grey with each cluster's Voronoi cell, as in section 3 of
  ``notebooks/261111_voronoi_growth_model.ipynb``.

Needs the T7 drive and the two qc_perct runs in ``results/``. Run once:
``python bleedover_app/packaging/make_help_figures.py``.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import PowerNorm  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from bleedover_app.model_catalog import model_path  # noqa: E402
from bleedover_app.viewer import Viewer  # noqa: E402
from correction.image_correction_gradient_descent import make_renderer  # noqa: E402
from simulator import SinglePointModel  # noqa: E402
from simulator.psf import render  # noqa: E402

OUT = REPO / "bleedover_app" / "static" / "help"
RUNS = {"additive": REPO / "results" / "261103_145443_correct_20261018_qc_perct_sparse",
        "voronoi": REPO / "results" / "261111_120352_correct_20261018_qc_perct_sparse_voronoi"}
CYCLE, TILE, SIZE = "img_10", "2112", 64
ZOOM = 32                                   # px; the territory/footprint diagrams show the centre of the crop
CMAP = "magma"


def save(fig, path: Path) -> None:
    fig.savefig(path, dpi=200, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    print("wrote", path.relative_to(REPO))


def psf_figure() -> float:
    """One cluster of typical brightness, rendered by the simulator itself (``simulator.psf.render``)."""
    model = SinglePointModel.load(model_path("standard"))
    flux = float(np.exp(np.log(model.flux_centers).mean()))          # middle of the trained brightness range
    params = model.params_for_flux([flux])[0]
    psf = render(model.psf, params, [[0.0, 0.0]], half_size=5)[0]     # pixel-integrated, as in a correction
    fig, ax = plt.subplots(figsize=(2.6, 2.6))
    ax.imshow(psf, cmap="gray", vmin=0, interpolation="nearest")
    ax.set_axis_off()
    save(fig, OUT / "psf.png")
    print("PSF centre pixel holds", f"{psf.max():.1%}", "of the light; 3×3 block", f"{psf[4:7, 4:7].sum():.1%}")
    return float(params[0])


def territory_figure(real: np.ndarray, xy: np.ndarray, x0: int, y0: int, fine: int = 8) -> None:
    """The crop in grey with each cluster's Voronoi cell (cyan) and centre (orange), like section 3 of
    ``notebooks/261111_voronoi_growth_model.ipynb``. Cells are found on a grid ``fine``× finer than the pixels
    so their borders are thin lines, not pixel blocks."""
    n = real.shape[0]
    margin = 6                                           # clusters just outside still own cells inside
    near = ((xy[:, 0] >= x0 - margin) & (xy[:, 0] < x0 + n + margin)
            & (xy[:, 1] >= y0 - margin) & (xy[:, 1] < y0 + n + margin))
    local = xy[near] - [x0, y0]
    axis = (np.arange(n * fine) + 0.5) / fine - 0.5   # pixel centres at integers, as in the images
    gx, gy = np.meshgrid(axis, axis)
    owner = cKDTree(local).query(np.column_stack([gx.ravel(), gy.ravel()]))[1].reshape(gx.shape)
    edge = np.zeros_like(owner, dtype=bool)
    edge[:, 1:] |= owner[:, 1:] != owner[:, :-1]
    edge[1:, :] |= owner[1:, :] != owner[:-1, :]
    fig, ax = _grey_crop(real)
    extent = (-0.5, n - 0.5, n - 0.5, -0.5)
    overlay = np.zeros((*edge.shape, 4))
    overlay[edge] = (0.15, 0.85, 0.9, 0.9)
    ax.imshow(overlay, interpolation="nearest", extent=extent)
    inside = (local[:, 0] >= -0.5) & (local[:, 0] < n - 0.5) & (local[:, 1] >= -0.5) & (local[:, 1] < n - 0.5)
    ax.scatter(local[inside, 0], local[inside, 1], s=3, c="#f5a623", linewidths=0)
    ax.set_xlim(-0.5, n - 0.5); ax.set_ylim(n - 0.5, -0.5)
    ax.set_axis_off()
    save(fig, OUT / "territory.png")


def _grey_crop(real: np.ndarray):
    n = real.shape[0]
    lo, hi = np.percentile(real, [1, 99.7])
    fig, ax = plt.subplots(figsize=(3.2, 3.2))
    ax.imshow(np.clip(real, max(lo, 0), None), cmap="gray", norm=PowerNorm(0.5, vmin=max(lo, 0), vmax=hi),
              interpolation="nearest", extent=(-0.5, n - 0.5, n - 0.5, -0.5))
    return fig, ax


def footprint_figure(real: np.ndarray, xy: np.ndarray, sigma: np.ndarray, x0: int, y0: int) -> None:
    """The additive counterpart of ``territory_figure``: each cluster's light footprint as a circle of radius
    2σ (σ from the model at the cluster's corrected brightness; the circle holds ~86% of its light). Circles
    overlap where clusters crowd, and the additive model adds their light there."""
    n = real.shape[0]
    from matplotlib.collections import EllipseCollection
    local = xy - [x0, y0]
    near = ((local[:, 0] > -6) & (local[:, 0] < n + 6) & (local[:, 1] > -6) & (local[:, 1] < n + 6))
    local, sigma = local[near], sigma[near]
    fig, ax = _grey_crop(real)
    d = 4 * sigma                                        # diameter of the 2σ circle
    ax.add_collection(EllipseCollection(d, d, 0, units="xy", offsets=local, offset_transform=ax.transData,
                                        facecolors="none", edgecolors=(0.15, 0.85, 0.9, 0.75), linewidths=0.4))
    inside = (local[:, 0] >= -0.5) & (local[:, 0] < n - 0.5) & (local[:, 1] >= -0.5) & (local[:, 1] < n - 0.5)
    ax.scatter(local[inside, 0], local[inside, 1], s=3, c="#f5a623", linewidths=0)
    ax.set_xlim(-0.5, n - 0.5); ax.set_ylim(n - 0.5, -0.5)
    ax.set_axis_off()
    save(fig, OUT / "footprints.png")


def renderer_figure() -> dict:
    viewer, crops, r2 = Viewer(), {}, {}
    for name, run in RUNS.items():
        state = viewer._load(run, CYCLE, TILE)
        if name == "additive":          # the crop: many separate dots, no debris (nothing far brighter than a cluster)
            real_full = state.real
            h, w = real_full.shape
            ceiling = np.percentile(real_full, 99.9)
            best, x0, y0 = -1, 0, 0
            for y in range(256, h - 256, SIZE // 2):
                for x in range(256, w - 256, SIZE // 2):
                    window = real_full[y:y + SIZE, x:x + SIZE]
                    if window.max() > 1.5 * ceiling:
                        continue
                    score = np.mean(window > np.percentile(real_full, 97))
                    if score > best:
                        best, x0, y0 = score, x, y
            crops["real"] = real_full[y0:y0 + SIZE, x0:x0 + SIZE]
        t, s = state.table, state.summary
        renderer = make_renderer(state.model, t[["x", "y"]].to_numpy(), t["flux_start"].to_numpy(),
                                 window=(x0, y0, SIZE, SIZE), renderer=name, softness=s.get("softness", 1.0))
        sim = renderer.render(t["flux_corrected"].to_numpy()[renderer.cluster_index])
        crops[name] = sim + state.background[y0:y0 + SIZE, x0:x0 + SIZE]
        c = (SIZE - ZOOM) // 2                       # the two diagrams zoom into the crop's centre
        zoom = crops["real"][c:c + ZOOM, c:c + ZOOM]
        if name == "voronoi":
            territory_figure(zoom, t[["x", "y"]].to_numpy(), x0 + c, y0 + c)
        else:
            sigma = state.model.params_for_flux(t["flux_corrected"].to_numpy())[:, 0]
            footprint_figure(zoom, t[["x", "y"]].to_numpy(), sigma, x0 + c, y0 + c)
        real = crops["real"]
        r2[name] = float(1 - ((real - crops[name]) ** 2).sum() / ((real - real.mean()) ** 2).sum())
    lo, hi = np.percentile(crops["real"], [1, 99.7])
    norm = PowerNorm(0.5, vmin=max(lo, 0), vmax=hi)            # square-root scale: dim clusters stay visible
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4), gridspec_kw={"wspace": 0.04})
    for ax, key in zip(axes, ["real", "additive", "voronoi"]):
        ax.imshow(np.clip(crops[key], max(lo, 0), None), cmap=CMAP, norm=norm, interpolation="nearest")
        ax.set_axis_off()
    save(fig, OUT / "renderers.png")
    return {"x0": x0, "y0": y0, **{f"r2_{k}": round(v, 3) for k, v in r2.items()}}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print("PSF sigma (px):", round(psf_figure(), 2))
    print("crop:", renderer_figure())
