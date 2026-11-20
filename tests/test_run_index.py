############TOYTOYTOY#########
"""Which runs belong to an experiment, which share a method, and which can be resumed (made-up run folders)."""

import json

from bleedover_app import run_index

EXP = "20261116_accperct_qc"
OPTIONS = {"renderer": "voronoi", "prior": 0.1, "softness": 1, "steps": 300, "background_spacing": 64, "workers": 3}


def make_run(folder, name, *, experiment=EXP, done=False, images=0, app=True, options=OPTIONS):
    run = folder / name
    (run / experiment / "img_0").mkdir(parents=True)
    settings = {"experiment": experiment, "model_id": "standard", "correct": options, "images": 3}
    command = "python -m bleedover_app.pipeline x" if app else "python scripts/correct_experiment.py"
    (run / "config.json").write_text(json.dumps({"started": name[:13], "command": command, "settings": settings}))
    (run / "app_job.json").write_text("{}")
    for tile in range(images):
        for suffix in (".json", ".feather", ".background.npy"):
            (run / experiment / "img_0" / f"210{tile}{suffix}").write_text("")
    if done:
        (run / experiment / "summary.csv").write_text("")
    return run


def test_listing_resume_and_method(tmp_path):
    make_run(tmp_path, f"261118_120000_correct_{EXP}_app_voronoi", images=2)
    make_run(tmp_path, f"261118_110000_correct_{EXP}_app_voronoi", done=True, images=3)
    make_run(tmp_path, f"261118_100000_correct_{EXP}_app_voronoi", options={**OPTIONS, "prior": 0.5}, images=1)
    make_run(tmp_path, f"261118_090000_correct_{EXP}_SW_app_voronoi", experiment=EXP + "_SW", images=1)
    runs = run_index.experiment_runs([tmp_path], EXP, running_dir=None)
    assert [r["status"] for r in runs] == ["stopped", "done", "stopped"]       # the _SW experiment is excluded
    assert runs[0]["images_done"] == 2 and runs[0]["resumable"]
    wanted = run_index.method({"model_id": "standard", "correct": {**OPTIONS, "workers": 8}})    # workers don't count
    assert run_index.resumable_match(runs, wanted)["run"].startswith("261118_120000")
    other = run_index.method({"model_id": "standard", "correct": {**OPTIONS, "renderer": "additive"}})
    assert run_index.resumable_match(runs, other) is None
    assert runs[0]["method"] == "Standard PSF · voronoi · prior 0.1 · softness 1"
