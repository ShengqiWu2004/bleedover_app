"""Library structure parsing (toy reads) and a check against real EPVIII05 reads (skipped without the drive)."""

from pathlib import Path

import pandas as pd
import pytest

from bleedover_app import library

THREE_WAY = "GGAGGCTCTCGGGACGAC NN GGATTTTCC NNNN ACGAAGT NN GTCGTCCCGATGCTGCAAGTAG"
EP = Path("/Volumes/T7_SW/images/20260820_EPVIII05")


def test_structure_rules():
    ############TOYTOYTOY#########
    assert library.template_to_pattern("ac NN gt n") == "^AC([ACGT]{2})GT([ACGT]{1})"
    reads = pd.Series(["ACAAGTCTTT", "ACAAGTNTTT", "TTAAGTC", None, "ACAAGTC"])
    assert library.extract_members(reads, "AC NN GT N").tolist()[0] == "AAC"
    assert library.extract_members(reads, "AC NN GT N").isna().tolist() == [False, True, True, True, False]
    for bad in ["", "ACGT", "ACXN"]:
        with pytest.raises(ValueError):
            library.template_to_pattern(bad)


@pytest.mark.skipif(not EP.is_dir(), reason="T7 drive not mounted")
def test_three_way_junction_on_epviii05():
    result = library.check(EP, "EPVIII02E", THREE_WAY, sample_size=50_000)
    assert result["possible_members"] == 4 ** 8
    assert 0.75 < result["matched_fraction"] < 0.85      # the notebook: 2,647,473 of 3,322,136 reads (79.7%)
