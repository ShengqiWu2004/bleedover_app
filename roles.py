"""Biological roles of sequencing samples, and which ones should fluoresce in a cycle.

Feather ``origin`` values are FASTQ sample names such as ``QC1S1_S1_L001_R1_001``,
``EPVIII03FM_S2_L001_R1_001`` or ``Undetermined_S0_L001_R1_001``. The *family* drops
the Illumina suffix (``QC1S1``), and the *role* groups families into what the
experiment's ``alignment_matrix.json`` talks about: ``fm`` (fiducial markers),
``qc1`` / ``qc2`` (QC constructs), ``library`` and ``undetermined`` (reads whose
barcode matched no sample).

``alignment_matrix.json`` says, per cycle type, which roles carry dye. Its keys
vary between experiments (``fm`` / ``FM``, ``Lib`` / ``Library``, ``UNDET`` /
``undetermined``), so they are normalised here. A role that is *not* lit is a
built-in control: whatever RFU it shows comes from neighbours' light
(bleedover) or background, so correction should push it toward zero light.
"""

import json
import re
from pathlib import Path

ROLES = ("fm", "qc1", "qc2", "library", "undetermined")
ROLE_LABELS = {"fm": "Fiducial markers (FM)", "qc1": "QC1 constructs", "qc2": "QC2 constructs",
               "library": "Library", "undetermined": "Undetermined (no barcode match)"}
_SUFFIX = re.compile(r"_S\d+(_L\d+)?(_R\d+)?(_\d+)?$")


def sample_family(origin: str) -> str:
    """``QC1S1_S1_L001_R1_001`` -> ``QC1S1``; ``QC1-s1_S2_L001_R1_001`` -> ``QC1-s1``."""
    return _SUFFIX.sub("", str(origin))


def family_role(family: str) -> str:
    name = family.lower()
    if name.startswith("undet"):
        return "undetermined"
    if name.startswith("qc1"):
        return "qc1"
    if name.startswith("qc2"):
        return "qc2"
    if name == "fm" or name.endswith("fm"):
        return "fm"
    return "library"


def _key_role(key: str) -> str | None:
    name = key.lower()
    if name.startswith("undet"):
        return "undetermined"
    if name.startswith("lib"):
        return "library"
    return name if name in ROLES else None


def read_alignment_matrix(root: str | Path) -> dict[str, dict[str, bool]] | None:
    """``{cycle type: {role: lit}}`` from ``alignment_matrix.json``, or None if the file is missing or empty."""
    path = Path(root) / "alignment_matrix.json"
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    out = {}
    for cycle_type, entry in raw.items():
        roles = {_key_role(k): bool(v) for k, v in entry.items() if _key_role(k)}
        if roles:
            out[cycle_type] = roles
    return out or None


def cycle_type(cycle: str) -> str:
    """``img_3`` -> ``img``; ``qc1_100_qc2_066_0`` -> ``qc1_100_qc2_066``."""
    return cycle.rsplit("_", 1)[0]


def lit_roles(matrix: dict | None, cycle: str) -> set[str] | None:
    """Roles expected to fluoresce in ``cycle``; None when the matrix doesn't cover it."""
    if not matrix or cycle_type(cycle) not in matrix:
        return None
    return {role for role, lit in matrix[cycle_type(cycle)].items() if lit}
