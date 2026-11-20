"""Library statistics beyond per-member means: values within each sequence, and signal by base and position.

- ``within_sequence``: every cluster's value divided by the mean of its own sequence's replicates. Each
  sequence is then centred on 1, so the pooled spread around 1 *is* the replicate spread (normalized SD),
  shown cluster by cluster instead of one number per sequence.
- ``base_grid``: for each variable position and base, the median signal of the sequences that carry that base
  there, relative to all sequences. Bleedover shouldn't depend on sequence, so the correction should change
  every cell by about the same factor; a pattern in the change map means it treated some sequences
  differently.
"""

import numpy as np
import pandas as pd

BASES = "ACGT"
MAX_POINTS = 600_000


def within_sequence(light: np.ndarray, codes: np.ndarray, member_mean: np.ndarray, use: np.ndarray,
                    rng: np.random.Generator) -> np.ndarray:
    """Cluster value ÷ its sequence's mean, for clusters of sequences in ``use`` (a sample of at most MAX_POINTS)."""
    keep = np.flatnonzero(use[codes])
    if len(keep) > MAX_POINTS:
        keep = rng.choice(keep, MAX_POINTS, replace=False)
    values = light[keep] / member_mean[codes[keep]]
    return values[np.isfinite(values)]


def base_grid(members: pd.Index, before: np.ndarray, after: np.ndarray, use: np.ndarray) -> dict:
    """Relative median signal per (base, position), before and after, and the median change per cell."""
    lengths = members.str.len()
    if len(members) == 0 or lengths.nunique() != 1:
        return {}
    width = int(lengths[0])
    letters = np.array(list(members), dtype=f"<U{width}").view("<U1").reshape(len(members), width)
    base_before, base_after = np.median(before[use]), np.median(after[use])
    ratio = after / before
    grids = {k: np.full((4, width), np.nan) for k in ("before", "after", "change")}
    counts = np.zeros((4, width), dtype=int)
    for i, base in enumerate(BASES):
        for pos in range(width):
            cell = use & (letters[:, pos] == base)
            counts[i, pos] = cell.sum()
            if counts[i, pos]:
                grids["before"][i, pos] = np.median(before[cell]) / base_before
                grids["after"][i, pos] = np.median(after[cell]) / base_after
                grids["change"][i, pos] = np.median(ratio[cell])
    return {**grids, "counts": counts, "width": width}
