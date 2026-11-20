"""Find the FASTQ folder that belongs to an experiment.

Two sources:

- **experiment** (default): ``<experiment>/fastq``.
- **library**: a shared folder holding many flowcells' FASTQs. The experiment's
  flowcell ID (``exp_details.txt``, line ``Flowcell ID: MHFVK``) picks the
  folder whose name contains that ID. Matching ignores case (``MHFVk`` ==
  ``MHFVK``), and the ID must stand alone in the name, separated by ``_``,
  ``-``, ``.`` or a space (``260921_MHFVK`` matches, ``XMHFVKY`` doesn't). The
  library is searched two levels deep.

If ``exp_details.txt`` has no flowcell ID, the user types one in the app and
the same match runs.
"""

import os
import re
from pathlib import Path

MAX_DEPTH = 2
MAX_FOLDERS = 20000             # stop scanning a huge library after this many folders
_FASTQ = re.compile(r"\.f(ast)?q(\.gz)?$", re.IGNORECASE)
_SAMPLE_SUFFIX = re.compile(r"_S\d+(_L\d+)?(_R\d+)?(_\d+)?$")
_ID = re.compile(r"^[A-Za-z0-9-]{3,20}$")


def normalize_flowcell_id(value: str) -> str:
    value = (value or "").strip()
    if not _ID.match(value):
        raise ValueError("A flowcell ID is 3-20 letters, digits or dashes, e.g. MHFVK")
    return value.upper()


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-z0-9]+", name.upper()) if t]


def list_samples(folder: str | Path) -> list[dict]:
    """FASTQ files in ``folder``: sample name (``QC1S1``), file name and size in MB."""
    folder = Path(folder)
    samples = []
    for entry in sorted(os.scandir(folder), key=lambda e: e.name):
        if entry.is_file() and not entry.name.startswith(".") and _FASTQ.search(entry.name):
            stem = _FASTQ.sub("", entry.name)
            samples.append({"sample": _SAMPLE_SUFFIX.sub("", stem), "file": entry.name,
                            "size_mb": round(entry.stat().st_size / 1e6, 1)})
    return samples


def find_in_library(library: str | Path, flowcell_id: str) -> list[Path]:
    """Folders in ``library`` (up to two levels deep) whose name contains ``flowcell_id`` as a whole token.

    Ordered best first: an exact name, then folders that hold FASTQ files, then shallower ones.
    """
    library, wanted = Path(library), normalize_flowcell_id(flowcell_id)
    if not library.is_dir():
        raise FileNotFoundError(f"FASTQ library not found: {library}")
    matches, frontier, scanned = [], [(library, 0)], 0
    while frontier and scanned < MAX_FOLDERS:
        folder, depth = frontier.pop(0)
        try:
            entries = sorted((e for e in os.scandir(folder) if e.is_dir() and not e.name.startswith(".")),
                             key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            scanned += 1
            if wanted in _tokens(entry.name):
                matches.append(Path(entry.path))
            elif depth + 1 < MAX_DEPTH:
                frontier.append((Path(entry.path), depth + 1))

    def rank(path: Path):
        has_fastq = any(_FASTQ.search(n) for n in os.listdir(path)) if path.is_dir() else False
        return (path.name.upper() != wanted, not has_fastq, len(path.relative_to(library).parts), str(path))
    return sorted(matches, key=rank)


def resolve(root: str | Path, *, mode: str, library: str = "", flowcell_id: str | None = None) -> dict:
    """The FASTQ folder for an experiment, as shown in the app.

    Returns ``found``, ``path``, ``samples``, plus ``alternatives`` (other library matches) and a ``message``.
    """
    if mode == "experiment":
        path = Path(root) / "fastq"
        if path.is_dir():
            return {"mode": mode, "found": True, "path": str(path), "samples": list_samples(path),
                    "message": "Using the FASTQ folder inside the experiment."}
        return {"mode": mode, "found": False, "path": None, "samples": [],
                "message": "This experiment has no fastq/ folder. Switch to a FASTQ library to look it up."}
    if mode != "library":
        raise ValueError(f"unknown FASTQ mode {mode!r}")
    if not library:
        return {"mode": mode, "found": False, "path": None, "samples": [], "message": "Choose a FASTQ library folder."}
    if not flowcell_id:
        return {"mode": mode, "found": False, "path": None, "samples": [], "needs_id": True,
                "message": "No flowcell ID found (exp_details.txt is missing or has none). Type it to match."}
    matches = find_in_library(library, flowcell_id)
    if not matches:
        return {"mode": mode, "found": False, "path": None, "samples": [], "needs_id": True,
                "flowcell_id": normalize_flowcell_id(flowcell_id),
                "message": f"No folder named after {normalize_flowcell_id(flowcell_id)} in the library."}
    best = matches[0]
    return {"mode": mode, "found": True, "path": str(best), "samples": list_samples(best),
            "flowcell_id": normalize_flowcell_id(flowcell_id), "alternatives": [str(m) for m in matches[1:6]],
            "message": f"Matched flowcell {normalize_flowcell_id(flowcell_id)}."}
