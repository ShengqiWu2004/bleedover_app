"""Which raw image folder is which cycle, for experiment folders without ``_metadata.csv``.

``_metadata.csv`` maps cycles to raw image folders (``IMAGER_CYCLE_ORDER`` + ``IMAGER_FOLDER_NAMES``). When it
is missing the same map can be rebuilt from two things MAPA always leaves behind:

- **cycles, in imaging order**: the intensity columns of ``img_results/results.feather`` name the cycles
  (``<cycle>_<channel>``, e.g. ``img_3_GG``), and each cycle's number is its place among cycles of its type.
  The columns themselves can be out of order (``20261018_qc_perct`` has ``img_0, img_3, …, img_1``), so only
  the numbers are used. That fixes the order when all cycles share one type (``img_0 … img_N``, the usual
  case). With several types (``qc1_000_qc2_000_0``, ``qc1_100_qc2_100_0``, …) nothing outside
  ``_metadata.csv`` records which type was imaged first, so such folders still need the file;
- **folders, in imaging order**: the cycle folders in ``ptirf/`` (``Cycle_02_1``, ``Cycle_02_2``, …) sorted by
  their numbers. Other folders (``example``, ``._*``) are ignored when ``Cycle_*`` folders exist.

The two lists are paired in order and must have the same length; otherwise the folder can't be read without
``_metadata.csv`` and the error says why. Checked against every experiment on the T7 drive that has the file
(``tests/test_layout_fallback.py``).

The repo's ``utils.load_experiment`` reads ``_metadata.csv`` through ``utils.experiment.read_cycle_folders``;
``install()`` wraps that function (in this process only) so it uses the rebuilt map when the file is absent.
The repo's files stay unchanged. Every process that loads experiments calls ``install()``: the app server, the
pipeline process and each of its worker processes.
"""

import re
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

import utils.experiment as repo_experiment

_CYCLE_COLUMN = re.compile(r"^(?P<cycle>.+_\d+)_(?P<channel>[A-Z]{2})$")
_CYCLE_FOLDER = re.compile(r"^Cycle_\d+(?:_\d+)*$", re.IGNORECASE)
_original = repo_experiment.read_cycle_folders


def _numbers(name: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", name)), name


def feather_cycles(root: Path) -> list[str]:
    """Cycle names in imaging order, from the intensity columns of ``results.feather`` (schema only)."""
    path = root / "img_results" / "results.feather"
    if not path.is_file():
        raise FileNotFoundError("no _metadata.csv and no img_results/results.feather to read the cycles from")
    with pa.memory_map(str(path)) as source:
        names = ipc.open_file(source).schema.names
    return list(dict.fromkeys(m["cycle"] for m in map(_CYCLE_COLUMN.match, names) if m))


def image_folders(root: Path, image_dir: str = "ptirf") -> list[str]:
    """Raw image folders in imaging order: ``Cycle_*`` folders if there are any, else every non-hidden folder."""
    base = root / image_dir
    if not base.is_dir():
        raise FileNotFoundError(f"no _metadata.csv and no {image_dir}/ folder")
    folders = [p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")]
    cycles = [f for f in folders if _CYCLE_FOLDER.match(f)]
    return sorted(cycles or folders, key=_numbers)


def infer_cycle_folders(root: str | Path, image_dir: str = "ptirf") -> dict[str, str]:
    """``{cycle: raw image folder}`` without ``_metadata.csv``; raises ValueError if the two lists don't pair up."""
    root = Path(root)
    cycles, folders = feather_cycles(root), image_folders(root, image_dir)
    if not cycles:
        raise ValueError("no _metadata.csv, and results.feather has no intensity columns to read the cycles from")
    types = sorted({c.rsplit("_", 1)[0] for c in cycles})
    if len(types) > 1:
        raise ValueError(f"no _metadata.csv, and this experiment has {len(types)} cycle types ({', '.join(types[:3])}, "
                         f"…) whose imaging order only _metadata.csv records. Add _metadata.csv "
                         f"(IMAGER_CYCLE_ORDER and IMAGER_FOLDER_NAMES).")
    cycles = sorted(cycles, key=lambda c: int(c.rsplit("_", 1)[1]))
    if [int(c.rsplit("_", 1)[1]) for c in cycles] != list(range(len(cycles))):
        raise ValueError("no _metadata.csv, and the cycle numbers in results.feather have gaps, so they can't be "
                         "matched to image folders. Add _metadata.csv.")
    if len(cycles) != len(folders):
        raise ValueError(f"no _metadata.csv, and the cycles can't be matched to image folders: results.feather has "
                         f"{len(cycles)} cycles but {image_dir}/ has {len(folders)} image folders. "
                         f"Add _metadata.csv (IMAGER_CYCLE_ORDER and IMAGER_FOLDER_NAMES).")
    return dict(zip(cycles, folders))


def read_cycle_folders(metadata_path: str | Path) -> dict[str, str]:
    """The repo's reader when ``_metadata.csv`` exists, the rebuilt map otherwise."""
    metadata_path = Path(metadata_path)
    if metadata_path.is_file():
        return _original(metadata_path)
    return infer_cycle_folders(metadata_path.parent)


def install() -> None:
    """Make ``utils.load_experiment`` work without ``_metadata.csv`` in this process (safe to call repeatedly)."""
    repo_experiment.read_cycle_folders = read_cycle_folders
