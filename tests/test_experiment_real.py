"""Real-data checks of what the app reads from experiment folders (skipped without the T7 drive).

Run from the repo root: ``python -m pytest bleedover_app/tests``.
"""

import os
from pathlib import Path

import pytest

from bleedover_app import api, fastq, timing
from bleedover_app.experiment_info import inspect_experiment, origin_summary, read_exp_details
from bleedover_app.roles import family_role, lit_roles, read_alignment_matrix, sample_family

IMAGES = Path(os.environ.get("IMAGER_IMAGES", "/Volumes/T7_SW/images"))
ACC = IMAGES / "20261116_accperct_qc"
pytestmark = pytest.mark.skipif(not ACC.is_dir(), reason="T7 drive not mounted")


def test_flowcell_ids_from_exp_details():
    assert read_exp_details(ACC)["flowcell_id"] == "MHFVK"
    assert read_exp_details(IMAGES / "20261009_qc_align")["flowcell_id"] == "MHFVk"   # as written; matching ignores case
    assert read_exp_details(IMAGES / "20250228_qc_experiment")["flowcell_id"] == "LGG4L"


def test_inspect_accperct():
    info = inspect_experiment(ACC)
    assert info["ready"] and not info["problems"]
    assert len(info["cycles"]) == 18
    assert info["images_aligned"] == 234                 # 13 aligned tiles x 18 cycles
    assert 900_000 < info["clusters_per_tile"] < 960_000
    defaults = api.calibration_defaults(info)
    assert defaults["cycles"] == ["img_0", "img_1", "img_2"]    # same choice as 261117_accperct_calibration
    assert defaults["tiles"] == ["2101", "2113", "2119"]


def test_sparsest_cycle_chosen_for_qc_experiment():
    info = inspect_experiment(IMAGES / "20250228_qc_experiment")
    assert api.calibration_defaults(info)["cycles"][0] == "qc1_000_qc2_000_0"      # only FM lit


def test_alignment_matrix_key_variants():
    ep = read_alignment_matrix(IMAGES / "20260820_EPVIII05")
    assert ep == {"img": {"library": True, "fm": True, "undetermined": False}}
    bubble = read_alignment_matrix(IMAGES / "260921_bubble_align2")
    assert bubble == {"img": {"library": True, "fm": False, "undetermined": False}}
    assert lit_roles(read_alignment_matrix(ACC), "img_5") == {"fm"}


def test_sample_roles_on_real_origins():
    assert family_role(sample_family("EPVIII03FM_S2_L001_R1_001")) == "fm"
    assert family_role(sample_family("EPVIII02E_S1_L001_R1_001")) == "library"
    assert family_role(sample_family("QC1-s1_S2_L001_R1_001")) == "qc1"
    rows = {r["family"]: r for r in origin_summary(ACC, ["FM", "QC1S1"])}
    assert rows["FM"]["role"] == "fm" and rows["FM"]["lit"] == {"img": True}
    assert rows["Undetermined"]["lit"] == {"img": False}
    assert rows["FM"]["in_fastq"] and not rows["QC2S1"]["in_fastq"]


def test_fastq_inside_experiment():
    result = fastq.resolve(ACC, mode="experiment")
    assert result["found"] and {"FM", "QC1S1", "QC2S4"} <= {s["sample"] for s in result["samples"]}


def test_estimate_uses_past_runs():
    seconds, basis = timing.seconds_per_image("voronoi", 3, 930_000)
    assert 20 < seconds < 200
    assert "run" in basis or "default" in basis
