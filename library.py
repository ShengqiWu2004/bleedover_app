"""Library structure: which reads belong to a designed library, and which library member each one is.

The user describes the library as DNA, as in ``sequence_replicates_across_flowcells.ipynb``:
``A/C/G/T`` must match exactly and each ``N`` is one variable base, e.g. the
three-way junction ``GGAGGCTCTCGGGACGAC NN GGATTTTCC NNNN ACGAAGT NN GTCGTCCCGATGCTGCAAGTAG``.
The template must match the **start** of the read (extra bases after it are
fine), and the variable segments, joined left to right, name the library
member (``library_seq``). Reads with any base other than A/C/G/T, or a
mismatching scaffold, are left out; no quality threshold is applied. Each
cluster (``origin|tile|ID``) is one replicate of its member.

One library per experiment (a sequencing sample + its template) is remembered
in the app's data folder, so the analysis can run after any correction.
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.feather as feather_io

from .config import app_data_dir
from .roles import sample_family


def clean_template(template: str) -> str:
    return "".join((template or "").split()).upper()


def template_to_pattern(template: str) -> str:
    """Start-anchored regex with one capture group per run of N."""
    template = clean_template(template)
    if not template:
        raise ValueError("The library structure is empty")
    invalid = set(template) - set("ACGTN")
    if invalid:
        raise ValueError(f"Use only A, C, G, T and N in the structure (found {''.join(sorted(invalid))})")
    if "N" not in template:
        raise ValueError("The structure needs at least one N (a variable base)")
    return "^" + re.sub(r"N+", lambda m: f"([ACGT]{{{len(m.group())}}})", template)


def describe_template(template: str) -> dict:
    template = clean_template(template)
    pattern = template_to_pattern(template)
    variable = template.count("N")
    return {"pattern": pattern, "length": len(template), "variable_bases": variable,
            "segments": len(re.findall(r"N+", template)),
            "possible_members": 4 ** variable if variable <= 20 else None}


def extract_members(seq: pd.Series, template: str) -> pd.Series:
    """Library member (joined variable bases) per read; NaN where the read doesn't fit the structure."""
    seq = seq.astype("string[python]")
    usable = seq.str.fullmatch("[ACGT]+", na=False)
    parts = seq.where(usable).str.extract(template_to_pattern(template))
    joined = parts[0]
    for column in parts.columns[1:]:            # column-wise join: fast on millions of reads
        joined = joined + parts[column]
    return joined.where(parts.notna().all(axis=1))


def read_sample(results_path: Path, family: str, columns: tuple[str, ...] = ("origin", "tile", "ID", "seq"),
                extra: list[str] | None = None) -> pd.DataFrame:
    """Rows of one sequencing sample (``QC1S1``, ``EPVIII02E``...) from the Feather table."""
    table = feather_io.read_table(results_path, columns=[*columns, *(extra or [])])
    origins = table.column("origin").unique().to_pylist()
    wanted = [o for o in origins if o is not None and sample_family(o) == family]
    if not wanted:
        raise ValueError(f"no sample {family!r} in {results_path.name}")
    table = table.filter(pc.is_in(table.column("origin").cast("string"), value_set=pc.cast(wanted, "string")))
    return table.to_pandas()


def check(root: str | Path, family: str, template: str, *, sample_size: int = 200_000) -> dict:
    """How well the structure fits this sample's reads (on a random sample of them)."""
    info = describe_template(template)
    frame = read_sample(Path(root) / "img_results" / "results.feather", family)
    n_sample = len(frame)
    if len(frame) > sample_size:
        frame = frame.sample(sample_size, random_state=0)
    members = extract_members(frame["seq"], template).dropna()
    counts = members.value_counts()
    return {**info, "family": family, "sample_reads": n_sample, "checked_reads": len(frame),
            "matched_fraction": len(members) / max(len(frame), 1), "members_seen": int(len(counts)),
            "examples": counts.head(5).index.tolist()}


class LibraryStore:
    """The library set up for each experiment: ``{experiment: {enabled, family, template, min_replicates}}``."""

    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "libraries.json"

    def all(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def get(self, experiment: str) -> dict | None:
        return self.all().get(experiment)

    def set(self, experiment: str, config: dict) -> dict:
        if config.get("enabled"):
            template_to_pattern(config["template"])          # refuse a structure that can't be used
            if not config.get("family"):
                raise ValueError("Choose the sequencing sample that holds the library")
        clean = {"enabled": bool(config.get("enabled")), "family": config.get("family", ""),
                 "template": " ".join((config.get("template") or "").upper().split()),   # spacing kept for reading
                 "min_replicates": max(2, int(config.get("min_replicates", 5)))}
        everything = {**self.all(), experiment: clean}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(everything, indent=1))
        tmp.replace(self.path)
        return clean


def replicate_summary(counts: np.ndarray) -> dict:
    return {"members": int(len(counts)), "clusters": int(counts.sum()),
            "singleton_percent": float(100 * np.mean(counts == 1)) if len(counts) else 0.0,
            "median_replicates": float(np.median(counts)) if len(counts) else 0.0,
            "p90_replicates": float(np.quantile(counts, 0.9)) if len(counts) else 0.0,
            "max_replicates": int(counts.max()) if len(counts) else 0}
