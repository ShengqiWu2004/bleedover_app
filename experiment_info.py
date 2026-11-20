"""What an experiment folder holds, read without loading any image: what the app shows after Browse.

An experiment folder has ``ptirf/`` (raw images) and usually ``_metadata.csv``
(cycles -> raw image folders) and ``exp_details.txt`` (flowcell ID and notes).
Both are optional: without ``_metadata.csv`` the cycles are matched to the
image folders by ``bleedover_app.layout``; without ``exp_details.txt`` the user
types the flowcell ID. The
correction also needs MAPA's outputs: ``analysis/img_transformations/`` (one
``.tr`` per cycle and tile; a tile without one was not aligned and can't be
corrected) and ``img_results/results.feather`` with ``x, y`` positions.
"""

import csv
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather_io
import pyarrow.ipc as ipc

from utils import load_experiment

from . import layout
from .roles import ROLE_LABELS, cycle_type, family_role, read_alignment_matrix, sample_family

REQUIRED = ("ptirf",)
OPTIONAL = ("_metadata.csv", "exp_details.txt")     # cycles are rebuilt without _metadata.csv (see .layout)

layout.install()
_FLOWCELL = re.compile(r"flow\s*-?\s*cell\s*(?:id)?\s*[:=]\s*([A-Za-z0-9-]+)", re.IGNORECASE)


def exp_details_path(root: Path) -> Path | None:
    """``exp_details.txt``, or a close variant (``exp_detail.txt``); macOS ``._`` shadow files are skipped."""
    exact = root / "exp_details.txt"
    if exact.is_file():
        return exact
    found = sorted(p for p in root.glob("exp_detail*.txt") if not p.name.startswith("._"))
    return found[0] if found else None


def read_exp_details(root: str | Path) -> dict:
    """Flowcell ID (as written; matching ignores case) and the free-text notes."""
    path = exp_details_path(Path(root))
    if path is None:
        return {"file": None, "flowcell_id": None, "notes": ""}
    text = path.read_text(errors="replace")
    match = _FLOWCELL.search(text)
    notes = text.split("Notes:", 1)[1].strip() if "Notes:" in text else ""
    return {"file": path.name, "flowcell_id": match.group(1) if match else None, "notes": notes}


def read_metadata_values(root: Path) -> dict[str, str]:
    if not (root / "_metadata.csv").is_file():
        return {}
    with open(root / "_metadata.csv", newline="") as handle:
        return {row[0].strip(): row[1].strip() for row in csv.reader(handle) if len(row) >= 2}


def feather_summary(path: Path) -> dict:
    """Row count, tiles with clusters, and whether ``x, y`` exist (reads only the ``tile`` column, ~0.1 s)."""
    if not path.is_file():
        return {"exists": False, "rows": 0, "tiles": 0, "has_xy": False}
    with pa.memory_map(str(path)) as source:
        names = ipc.open_file(source).schema.names
    tiles = feather_io.read_table(path, columns=["tile"]).column("tile") if "tile" in names else None
    rows = len(tiles) if tiles is not None else 0
    return {"exists": True, "rows": rows, "tiles": len(tiles.unique()) if tiles is not None else 0,
            "has_xy": {"x", "y"} <= set(names)}


def aligned_tiles(exp) -> dict[str, list[str]]:
    """Tiles with a registration transform, per cycle (MAPA skips tiles it couldn't align)."""
    out = {}
    for cycle in exp.cycles:
        folder = exp.transform_path(cycle, exp.device.tiles[0]).parent
        present = {p.name for p in folder.glob("*.tr")} if folder.is_dir() else set()
        out[cycle] = [t for t in exp.device.tiles if exp.transform_path(cycle, t).name in present]
    return out


def inspect_experiment(root: str | Path) -> dict:
    """Everything the setup screen shows; ``ready`` says whether a correction can run."""
    root = Path(root).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a folder: {root}")
    details = read_exp_details(root)
    checks = {"_metadata.csv": (root / "_metadata.csv").is_file(), "exp_details.txt": details["file"] is not None,
              "ptirf": (root / "ptirf").is_dir()}
    info = {"path": str(root), "name": root.name, "checks": checks, "optional": list(OPTIONAL), "problems": [],
            "notes": [], "details": details}
    try:
        exp = load_experiment(root)
    except (FileNotFoundError, ValueError, KeyError) as error:
        info["problems"].append(f"Can't read this experiment folder: {error}" if checks["_metadata.csv"]
                                else f"Not readable as an experiment folder: {error}")
        info["ready"] = False
        return info
    meta = read_metadata_values(root)
    if not checks["_metadata.csv"]:
        info["notes"].append(f"No _metadata.csv: the {len(exp.cycles)} cycles were matched to the ptirf/ folders "
                             f"in order ({exp.cycles[0]} → {exp.cycle_folders[exp.cycles[0]]}, …).")
    if not checks["exp_details.txt"]:
        info["notes"].append("No exp_details.txt: type the flowcell ID to find the FASTQ files.")
    tiles = aligned_tiles(exp)
    feather = feather_summary(exp.results_path)
    matrix = read_alignment_matrix(root)
    info.update({
        "date": meta.get("EXP_DATE", ""), "person": meta.get("EXP_PERSON", ""),
        "channel": exp.device.channel, "device_tiles": exp.device.tiles,
        "cycles": [{"cycle": c, "folder": f, "type": cycle_type(c), "aligned_tiles": tiles[c]}
                   for c, f in exp.cycle_folders.items()],
        "images_aligned": sum(len(t) for t in tiles.values()),
        "images_total": len(exp.cycles) * len(exp.device.tiles),
        "feather": feather, "alignment_matrix": matrix,
        "clusters_per_tile": round(feather["rows"] / max(feather["tiles"], 1)),
    })
    if not checks["ptirf"]:
        info["problems"].append("Missing ptirf/ (the raw images).")
    if not feather["exists"]:
        info["problems"].append("No img_results/results.feather: run MAPA's intensity extraction first.")
    elif not feather["has_xy"]:
        info["problems"].append("results.feather has no x, y columns, so clusters can't be placed on images.")
    if not info["images_aligned"]:
        info["problems"].append("No tile has a registration transform (analysis/img_transformations).")
    if matrix is None:
        info["problems"].append("No alignment_matrix.json: the report can't tell lit from dark samples.")
    info["ready"] = bool(feather["has_xy"] and info["images_aligned"] and checks["ptirf"])
    return info


def origin_summary(root: str | Path, fastq_samples: list[str] | None = None) -> list[dict]:
    """Clusters per sequencing sample, its role, whether it should glow per cycle type, and its FASTQ file.

    Reads only the ``origin`` column (a few seconds for ~10M clusters).
    """
    root = Path(root)
    table = feather_io.read_table(root / "img_results" / "results.feather", columns=["origin"])
    counts = table.column("origin").value_counts().to_pylist()
    matrix = read_alignment_matrix(root) or {}
    fastq = {s.upper() for s in (fastq_samples or [])}
    rows = {}
    for item in counts:
        family = sample_family(item["values"])
        row = rows.setdefault(family, {"family": family, "clusters": 0})
        row["clusters"] += int(item["counts"])
    for row in rows.values():
        role = family_role(row["family"])
        row.update({"role": role, "role_label": ROLE_LABELS[role],
                    "lit": {t: m.get(role) for t, m in matrix.items()},
                    "in_fastq": row["family"].upper() in fastq if fastq_samples is not None else None})
    return sorted(rows.values(), key=lambda r: (r["role"] == "undetermined", r["family"]))
