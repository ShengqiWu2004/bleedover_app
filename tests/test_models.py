"""Built-in models, saved calibrations, and the model file a run uses."""

import json

from bleedover_app import model_catalog
from bleedover_app.calibrations import CalibrationStore
from simulator import SinglePointModel


def test_two_built_in_models_with_their_calibrations():
    models = model_catalog.list_models("20261116_accperct_qc")
    assert [m["id"] for m in models] == ["standard", "qc_psf"]
    assert models[0]["recommended"] and models[0]["calibration"]["source"] == "built-in"
    assert models[1]["calibration"] is None                 # QC-only PSF was never calibrated on accperct


def test_saved_calibration_wins_and_can_be_deleted(tmp_path, monkeypatch):
    store = CalibrationStore(tmp_path / "calibrations.json")
    monkeypatch.setattr(model_catalog, "store", store)
    entry = store.add(model_id="qc_psf", experiment="20261116_accperct_qc", gain=2.0, offset=-1000.0, single_points=10)
    store.add(model_id="qc_psf", experiment="20261116_accperct_qc", gain=2.1, offset=-900.0)   # replaces the first
    assert len(store.entries()) == 1 and store.entries()[0]["gain"] == 2.1
    cal = model_catalog.calibration_for("qc_psf", "20261116_accperct_qc")
    assert cal["source"] == "yours"
    path = model_catalog.write_run_model("qc_psf", "20261116_accperct_qc", tmp_path / "model.json")
    assert SinglePointModel.load(path).calibrations["20261116_accperct_qc"] == (2.1, -900.0)
    store.delete(store.entries()[0]["id"])
    assert model_catalog.calibration_for("qc_psf", "20261116_accperct_qc") is None
    assert entry["id"] not in json.dumps(store.entries())
