"""Figures of the library analysis (same visual language as ``plots``: blue Feather, orange corrected)."""

import numpy as np

from .plots import CORRECTED, FEATHER, MUTED, SEQUENTIAL, plt


def replicates(counts: np.ndarray, min_replicates: int):
    """Replicate clusters per library member: histogram (log-log) and cumulative share, as in the notebook."""
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 3.8))
    values, freq = np.unique(counts, return_counts=True)
    ax2.step(np.r_[0.5, values], np.r_[0, np.cumsum(freq) / len(counts)], where="post", color=FEATHER)
    ax2.axvline(min_replicates - 0.5, color=MUTED, ls="--", lw=1.2)
    ax2.set(xscale="log", ylim=(0, 1.02), xlabel="replicate clusters per library member",
            ylabel="share of members with ≤ this many", title="Cumulative")
    edges = np.unique(np.r_[0.5, np.floor(np.geomspace(1, max(counts.max(), 2), 35)) + 0.5])
    ax.hist(counts, bins=edges, color=FEATHER, edgecolor="white", linewidth=0.5)
    ax.axvline(min_replicates - 0.5, color=MUTED, ls="--", lw=1.2, label=f"used: ≥ {min_replicates} replicates")
    ax.set(xscale="log", yscale="log", xlabel="replicate clusters per library member", ylabel="library members")
    ax.set_title("Replicates per library member", pad=24)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), borderaxespad=0.2)
    return fig


def member_medians(before, after, cycle: str):
    """Each member's median signal after correction against before (light above zero, RFU)."""
    fig, ax = plt.subplots(figsize=(6.2, 5))
    keep = (before > 0) & (after > 0)
    x, y = before[keep], after[keep]
    lo, hi = np.percentile(np.r_[x, y], [0.5, 99.5])
    hb = ax.hexbin(x, y, gridsize=60, bins="log", cmap=SEQUENTIAL, mincnt=1, xscale="log", yscale="log",
                   extent=(np.log10(lo), np.log10(hi), np.log10(lo), np.log10(hi)))
    ax.plot([lo, hi], [lo, hi], color=MUTED, ls="--", lw=1.2, label="no change")
    ax.set(xlabel="median signal, Feather (RFU above zero light)", ylabel="median signal, corrected",
           title=f"Each library member before and after ({cycle})")
    ax.grid(False)
    ax.legend(loc="upper left")
    fig.colorbar(hb, ax=ax, label="library members (log scale)")
    return fig


def cv_distribution(before, after, cycle: str):
    """Distribution of each member's normalized SD (SD ÷ mean of its replicates), before and after."""
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    both = np.r_[before, after]
    lo, hi = (float(v) for v in np.nanpercentile(both, [1, 99]))
    bins = np.linspace(lo, hi, 40 if len(before) < 2000 else 60)
    for values, color, label in [(before, FEATHER, "Feather"), (after, CORRECTED, "corrected")]:
        ax.hist(np.clip(values, lo, hi), bins=bins, histtype="step", lw=2, color=color,
                label=f"{label} (median {np.nanmedian(values):.2f})")
    ax.set(xlabel=f"normalized SD of replicates (SD ÷ mean; the end bars hold all < {lo:.2f} and > {hi:.2f})", ylabel="library members",
           title=f"Replicate spread per library member ({cycle})")
    ax.legend(loc="upper right")
    return fig


def cv_each_sequence(before, after, cycle: str, tighter):
    """Heatmap of every sequence's normalized SD after correction against before."""
    fig, ax = plt.subplots(figsize=(6.2, 5))
    lo, hi = (float(v) for v in np.nanpercentile(np.r_[before, after], [1, 99]))
    hb = ax.hexbin(before, after, gridsize=45, bins="log", cmap=SEQUENTIAL, mincnt=1, extent=(lo, hi, lo, hi))
    ax.plot([lo, hi], [lo, hi], color=MUTED, ls="--", lw=1.2, label="no change")
    ax.set(xlabel="normalized SD, Feather", ylabel="normalized SD, corrected", xlim=(lo, hi), ylim=(lo, hi),
           title=f"Replicate spread of each sequence ({cycle})")
    ax.grid(False)
    if tighter is not None:
        ax.text(0.98, 0.03, f"{100 * tighter:.0f}% of sequences tighter after\n(below the dashed line)",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=9, color=MUTED)
    ax.legend(loc="upper left")
    fig.colorbar(hb, ax=ax, label="sequences (log scale)")
    return fig


def within_sequence(before, after, cycle: str):
    """Each cluster's value ÷ its own sequence's mean, pooled: the width around 1 is the replicate spread."""
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    lo, hi = (float(v) for v in np.nanpercentile(np.r_[before, after], [0.5, 99.5]))
    bins = np.linspace(lo, hi, 80)
    for values, color, label in [(before, FEATHER, "Feather"), (after, CORRECTED, "corrected")]:
        ax.hist(np.clip(values, lo, hi), bins=bins, histtype="step", lw=2, color=color, density=True,
                label=f"{label} (SD {np.std(values):.2f})")
    ax.axvline(1, color=MUTED, lw=1)
    ax.set(xlabel="cluster value ÷ its sequence's mean (1 = the sequence's mean)", ylabel="density of clusters",
           title=f"Clusters within their own sequence ({cycle})")
    ax.legend(loc="upper right")
    return fig


def base_heatmaps(grid: dict, cycle: str):
    """Median signal by base and variable position, before and after (relative to all), and the change."""
    from matplotlib.colors import TwoSlopeNorm
    from .plots import DIVERGING
    width = grid["width"]
    fig, axes = plt.subplots(1, 3, figsize=(max(9.5, 0.9 * width * 3 + 2), 3.4), layout="constrained")
    vmax = float(np.nanmax(np.abs(np.r_[grid["before"].ravel(), grid["after"].ravel()] - 1))) or 0.1
    change = grid["change"]
    centre = float(np.nanmedian(change))
    span = float(np.nanmax(np.abs(change - centre))) or 0.05
    panels = [("Feather", grid["before"], TwoSlopeNorm(1, 1 - vmax, 1 + vmax), "relative signal"),
              ("Corrected", grid["after"], TwoSlopeNorm(1, 1 - vmax, 1 + vmax), "relative signal"),
              ("Change (corrected ÷ Feather)", change, TwoSlopeNorm(centre, centre - span, centre + span), "median change")]
    for ax, (title, values, norm, label) in zip(axes, panels):
        im = ax.imshow(values, cmap=DIVERGING, norm=norm, aspect="auto")
        ax.set_xticks(range(width), [str(i + 1) for i in range(width)])
        ax.set_yticks(range(4), list("ACGT"))
        ax.set(xlabel="variable position", title=title)
        ax.grid(False)
        if width <= 16:              # cells labelled as % away from all sequences (or from the median change)
            ref = centre if values is change else 1.0
            for (i, j), v in np.ndenumerate(values):
                if np.isfinite(v):
                    ax.text(j, i, f"{100 * (v / ref - 1):+.1f}%", ha="center", va="center", fontsize=9.5, color="#0b0b0b")
        fig.colorbar(im, ax=ax, label=label, shrink=0.85)
    fig.suptitle(f"Signal by base and position ({cycle})", x=0.01, ha="left", fontweight="bold", fontsize=11)
    return fig


def cv_by_cycle(per_cycle):
    """Median normalized SD over members, per cycle, before and after."""
    cycles = per_cycle["cycle"].tolist()
    fig, ax = plt.subplots(figsize=(max(7.5, 0.4 * len(cycles) + 3), 3.8))
    x = np.arange(len(cycles))
    for column, color, label in [("median_cv_feather", FEATHER, "Feather"), ("median_cv_corrected", CORRECTED, "corrected")]:
        ax.plot(x, per_cycle[column], "o-", color=color, ms=6, mec="white", mew=0.8, label=label)
    ax.set_xticks(x, cycles, rotation=45 if len(cycles) > 8 else 0, ha="right" if len(cycles) > 8 else "center")
    ax.set(ylabel="median normalized SD", title="Replicate spread in every cycle", ylim=(0, None))
    ax.legend(loc="lower right")
    return fig
