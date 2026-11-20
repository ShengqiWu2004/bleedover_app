"""Run one app job: ``python -m bleedover_app.pipeline <run_dir>/app_job.json``.

The job file (written by ``bleedover_app.jobs``) holds ``kind`` (``correct`` or
``report``), the experiment ``root``, the ``model`` path, the ``calibrate`` and
``correct`` settings and the ``images`` to fit. Progress goes to stdout as
events (``pipeline.events``).
"""

import json
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:      # worker processes re-import this module, so set it at import time
    sys.path.insert(0, str(REPO_ROOT))

from bleedover_app import layout  # noqa: E402
from bleedover_app.pipeline.events import emit  # noqa: E402

layout.install()            # experiment folders without _metadata.csv; worker processes install it too


def main(argv: list[str]) -> int:
    job = json.loads(Path(argv[0]).read_text())
    run_dir = Path(job["run_dir"])
    try:
        model_path = job.get("model")
        if job["kind"] == "correct":
            if job["calibrate"]["enabled"]:
                from bleedover_app.pipeline import calibrate
                emit("stage", stage="calibrate")
                model_path = calibrate.run(job, run_dir)
            from bleedover_app.pipeline import correct
            emit("stage", stage="correct")
            correct.run(job, model_path, run_dir)
        if job["kind"] in ("correct", "report"):
            from bleedover_app.pipeline import report
            emit("stage", stage="report")
            report.build(run_dir)
        if (job.get("library") or {}).get("enabled"):
            library_stage(job, run_dir)
        emit("finished", run_dir=str(run_dir))
        return 0
    except Exception as error:
        emit("failed", error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        return 1


def library_stage(job: dict, run_dir: Path) -> None:
    """Optional library analysis. After a correction it must not fail the run: problems become a log line."""
    from bleedover_app.pipeline import library_report
    emit("stage", stage="library")
    try:
        library_report.build(run_dir, job["library"])
    except Exception as error:
        if job["kind"] == "library":
            raise
        emit("log", message=f"library analysis failed ({type(error).__name__}: {error}); the correction is complete")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
