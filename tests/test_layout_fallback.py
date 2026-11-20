"""Experiment folders without ``_metadata.csv`` / ``exp_details.txt`` still work (real data; skipped without T7).

The rebuilt cycle -> folder map must equal what ``_metadata.csv`` says for every experiment that has the file,
experiments the map can't be rebuilt for must be refused rather than guessed, and a copy of
``20261116_accperct_qc`` without both files (symlinks to everything else) must open ready to correct.
"""

import os
from pathlib import Path

import pytest

from bleedover_app import layout
from bleedover_app.experiment_info import inspect_experiment
from utils import load_experiment

IMAGES = Path(os.environ.get("IMAGER_IMAGES", "/Volumes/T7_SW/images"))
pytestmark = pytest.mark.skipif(not IMAGES.is_dir(), reason="needs the T7 drive")


def experiments_with_metadata():
    return [p for p in sorted(IMAGES.iterdir())
            if (p / "_metadata.csv").is_file() and (p / "img_results" / "results.feather").is_file()]


@pytest.mark.parametrize("root", experiments_with_metadata(), ids=lambda p: p.name)
def test_rebuilt_map_equals_metadata_or_is_refused(root):
    written = layout._original(root / "_metadata.csv")
    if len({c.rsplit("_", 1)[0] for c in written}) > 1:       # several cycle types: order unknown, so refuse
        with pytest.raises(ValueError, match="cycle types"):
            layout.infer_cycle_folders(root)
    else:
        assert layout.infer_cycle_folders(root) == written


def test_folder_without_metadata_or_details_is_ready(tmp_path):
    source = IMAGES / "20261116_accperct_qc"
    root = tmp_path / source.name                      # same name: calibrations are keyed by experiment name
    root.mkdir()
    for item in source.iterdir():
        if item.name not in ("_metadata.csv", "exp_details.txt") and not item.name.startswith("."):
            (root / item.name).symlink_to(item)
    info = inspect_experiment(root)
    assert info["ready"] and not info["problems"]
    assert info["checks"] == {"_metadata.csv": False, "exp_details.txt": False, "ptirf": True}
    assert len(info["notes"]) == 2 and info["details"]["flowcell_id"] is None
    exp = load_experiment(root)
    assert exp.cycle_folders == layout._original(source / "_metadata.csv")
    assert exp.image_path("img_13", "2105").parent.name == "Cycle_06_2"
