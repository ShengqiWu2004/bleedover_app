############TOYTOYTOY#########
"""FASTQ library matching on a made-up library layout (no real library exists yet to test against)."""

import pytest

from bleedover_app import fastq


@pytest.fixture
def library(tmp_path):
    for folder in ["251009_MHFVK_miseq", "MF62G", "XMHFVKY", "2026/LGG4L", "2026/deeper/MCW83", ".hidden_MHFVK"]:
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / "251009_MHFVK_miseq" / "FM_S9_L001_R1_001.fastq").write_text("@r\nACGT\n+\nIIII\n")
    (tmp_path / "MF62G" / "Lib_S1_L001_R1_001.fastq.gz").write_bytes(b"")
    return tmp_path


def test_match_ignores_case_and_needs_a_whole_token(library):
    assert [p.name for p in fastq.find_in_library(library, "mhfvk")] == ["251009_MHFVK_miseq"]   # not XMHFVKY, not hidden
    assert [p.name for p in fastq.find_in_library(library, "MF62g")] == ["MF62G"]


def test_searches_two_levels_deep_only(library):
    assert [p.name for p in fastq.find_in_library(library, "LGG4L")] == ["LGG4L"]
    assert fastq.find_in_library(library, "MCW83") == []


def test_resolve_library_mode(library, tmp_path):
    exp = tmp_path / "exp"
    exp.mkdir()
    found = fastq.resolve(exp, mode="library", library=str(library), flowcell_id="MHFVk")
    assert found["found"] and found["flowcell_id"] == "MHFVK"
    assert found["samples"] == [{"sample": "FM", "file": "FM_S9_L001_R1_001.fastq", "size_mb": 0.0}]
    missing = fastq.resolve(exp, mode="library", library=str(library), flowcell_id="ZZZZZ")
    assert not missing["found"] and missing["needs_id"]
    no_id = fastq.resolve(exp, mode="library", library=str(library), flowcell_id=None)
    assert no_id["needs_id"]


def test_rejects_bad_ids():
    with pytest.raises(ValueError):
        fastq.normalize_flowcell_id("MH/../FVK")
