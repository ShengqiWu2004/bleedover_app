"""The report's default figures (matplotlib, saved as PNG next to the run's outputs).

One visual language everywhere: blue is the original Feather value, orange is
the corrected value (a validated colourblind-safe pair), raw microscope images
are grey, and signed differences use blue - grey - red. Grids and axes stay
quiet; every axis names its scale (RFU, R², px).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

FEATHER, CORRECTED = "#2a78d6", "#eb6834"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
DIVERGING = LinearSegmentedColormap.from_list("blue_gray_red", ["#104281", "#3987e5", "#f0efec", "#e66767", "#8f1d1d"])
SEQUENTIAL = LinearSegmentedColormap.from_list("blue", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 10,
    "legend.frameon": False, "image.interpolation": "nearest", "lines.linewidth": 2,
})


def save(fig, path: Path) -> None:
    fig.savefig(path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def calibration(rfu, flux, gain, offset, calibrations: dict, experiment: str):
    """Each single point's fitted image counts against its Feather RFU, with the fitted line."""
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    lo, hi = np.percentile(rfu, [0.5, 99.5])
    flo, fhi = np.percentile(flux, [0.5, 99.5])
    hb = ax.hexbin(rfu, flux, gridsize=70, bins="log", cmap=SEQUENTIAL, mincnt=1, extent=(lo, hi, flo, fhi))
    r = np.linspace(lo, hi, 50)
    ax.plot(r, gain * r + offset, color=CORRECTED, label=f"this experiment: {gain:.2f} × RFU {offset:+,.0f}")
    ax.set(xlabel="Feather RFU of the dot", ylabel="light in the image (counts)",
           title=f"Calibration from {len(rfu):,} isolated dots")
    ax.legend(loc="upper left")
    fig.colorbar(hb, ax=ax, label="dots (log scale)")
    return fig


def r2_by_cycle(summary, cycles: list[str]):
    """Per image: how much of the real image the simulation explains, before and after correction."""
    fig, ax = plt.subplots(figsize=(max(7.5, 0.42 * len(cycles) + 3), 3.8))
    index = summary["cycle"].map({c: i for i, c in enumerate(cycles)}).to_numpy(dtype=float)
    jitter = np.random.default_rng(0).uniform(-0.18, 0.18, len(summary))
    for column, color, label in [("r2_start", FEATHER, "from Feather RFU"), ("r2_end", CORRECTED, "after correction")]:
        ax.plot(index + jitter, summary[column], "o", ms=5, color=color, alpha=0.75, mec=SURFACE, mew=0.6,
                label=label)
    ax.set_xticks(range(len(cycles)), cycles, rotation=45 if len(cycles) > 8 else 0, ha="right" if len(cycles) > 8 else "center")
    ax.set(ylabel="image R²", title="Does the simulated image match the real one?")
    ax.axhline(1, color=MUTED, lw=0.8, ls=":")
    ax.legend(loc="lower right")
    return fig


def feather_vs_corrected(feather, corrected, zero_point: float):
    """Every trusted cluster: corrected RFU against its Feather RFU (a sample)."""
    fig, ax = plt.subplots(figsize=(6.2, 5))
    lo = min(np.percentile(feather, 0.5), np.percentile(corrected, 0.5), zero_point)
    hi = max(np.percentile(feather, 99.5), np.percentile(corrected, 99.5))
    lo -= 0.03 * (hi - lo)
    hb = ax.hexbin(feather, corrected, gridsize=80, bins="log", cmap=SEQUENTIAL, mincnt=1, extent=(lo, hi, lo, hi))
    ax.plot([lo, hi], [lo, hi], color=MUTED, ls="--", lw=1.2, label="no change")
    ax.axhline(zero_point, color=CORRECTED, ls=":", lw=1.5, label=f"zero light ({zero_point:,.0f} RFU)")
    ax.set(xlabel="Feather RFU (original)", ylabel="corrected RFU", xlim=(lo, hi), ylim=(lo, hi),
           title="Each cluster before and after correction")
    ax.grid(False)
    ax.legend(loc="upper left")
    fig.colorbar(hb, ax=ax, label="clusters (log scale)")
    return fig


def change_vs_distance(table):
    """Median RFU change against the distance to the nearest lit neighbour (bleedover is local)."""
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    x = np.arange(len(table))
    ax.fill_between(x, table["q25"], table["q75"], color=CORRECTED, alpha=0.15, lw=0, label="middle half of clusters")
    ax.plot(x, table["median"], "o-", color=CORRECTED, ms=7, mec=SURFACE, mew=1, label="median")
    ax.axhline(0, color=MUTED, lw=1)
    ax.set_xticks(x, table["bin"])
    ax.set(xlabel="distance to the nearest lit neighbour (px; one PSF is ~1.6 px wide)",
           ylabel="RFU change (% of Feather)", title="RFU change by crowding")
    ax.legend(loc="lower right")
    return fig


def origins(table, zero_point: float):
    """Per sequencing sample: median Feather vs corrected RFU, marked lit or dark from the alignment matrix."""
    table = table.iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(table) + 1.4))
    y = np.arange(len(table))
    ax.hlines(y, table["feather"], table["corrected"], color=GRID, lw=3)
    ax.plot(table["feather"], y, "o", color=FEATHER, ms=9, mec=SURFACE, mew=1, label="Feather")
    ax.plot(table["corrected"], y, "o", color=CORRECTED, ms=9, mec=SURFACE, mew=1, label="corrected")
    ax.axvline(zero_point, color=MUTED, ls=":", lw=1.2, label="zero light")
    ax.set_yticks(y, [f"{f}  ({s})" for f, s in zip(table["family"], table["state"])])
    ax.set_ylim(-0.6, len(table) - 0.4)
    ax.grid(axis="y", visible=False)
    ax.set(xlabel="median RFU")
    ax.set_title("Median RFU per sequencing sample", pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, borderaxespad=0.2)
    return fig
