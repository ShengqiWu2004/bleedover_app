"""Run one pipeline job at a time in a subprocess, and keep its live state for the UI.

The state (stage, images done, ETA, recent log lines) is a plain dict the
server streams to the page. ``wait`` blocks until it changes, for server-sent
events. Cancel stops the whole process group, worker processes included;
images finished before that stay in the run folder.
"""

import collections
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import FROZEN, REPO_ROOT
from .pipeline.events import parse
from .timing import REPORT_SECONDS, StageClock

STAGE_LABELS = {"calibrate": "Calibrating the model", "correct": "Correcting images", "report": "Building the report",
                "library": "Analysing the library"}
LIBRARY_SECONDS = 120.0


class JobManager:
    def __init__(self):
        self._cond = threading.Condition()
        self._proc: subprocess.Popen | None = None
        self._clock: StageClock | None = None
        self._version = 0
        self._state = {"status": "idle"}

    # ---- reading -------------------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        with self._cond:
            state = dict(self._state, version=self._version, log=list(self._state.get("log", [])))
            if state.get("status") == "running":
                state["elapsed_seconds"] = time.time() - state["started_at"]
                state["eta_seconds"] = self._eta()
            return state

    def wait(self, version: int, timeout: float = 15.0) -> dict:
        with self._cond:
            self._cond.wait_for(lambda: self._version != version, timeout=timeout)
        return self.snapshot()

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ---- control -------------------------------------------------------------------------------------------
    def start(self, job: dict, priors: dict) -> dict:
        """``priors``: seconds per item for each stage (``timing``), used until real timings arrive."""
        if self.running():
            raise RuntimeError("A job is already running; cancel it or wait for it to finish")
        run_dir = Path(job["run_dir"])
        job_path = run_dir / ("app_job.json" if job["kind"] == "correct" else f"app_{job['kind']}_job.json")
        job_path.write_text(json.dumps(job, indent=1))
        stages = {"correct": ["calibrate", "correct", "report"], "report": ["report"], "library": []}[job["kind"]]
        if job["kind"] == "correct" and not job["calibrate"]["enabled"]:
            stages = stages[1:]
        if (job.get("library") or {}).get("enabled"):
            stages = [*stages, "library"]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO_ROOT), os.environ.get("PYTHONPATH")])),
               "PYTHONUNBUFFERED": "1", "MPLBACKEND": "Agg"}
        command = [sys.executable, "--pipeline", str(job_path)] if FROZEN else \
            [sys.executable, "-m", "bleedover_app.pipeline", str(job_path)]   # the standalone app runs itself
        self._proc = subprocess.Popen(command, cwd=REPO_ROOT if not FROZEN else Path.home(),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                      env=env, start_new_session=True)
        with self._cond:
            self._state = {"status": "running", "kind": job["kind"], "experiment": job.get("experiment"),
                           "run_dir": str(run_dir), "started_at": time.time(), "stages": stages, "stage": stages[0],
                           "done": 0, "total": 0, "last": "", "log": collections.deque(maxlen=400),
                           "priors": priors, "images_total": len(job.get("images", [])),
                           "workers": int(job.get("correct", {}).get("workers", 1))}
            self._clock = None
            self._bump()
        threading.Thread(target=self._read, args=(self._proc,), daemon=True).start()
        return self.snapshot()

    def cancel(self) -> None:
        if self.running():
            try:
                os.killpg(self._proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            with self._cond:
                self._state["cancel_requested"] = True
                self._bump()

    # ---- internals -----------------------------------------------------------------------------------------
    def _bump(self) -> None:
        self._version += 1
        self._cond.notify_all()

    def _eta(self) -> float | None:
        s = self._state
        stages = s["stages"][s["stages"].index(s["stage"]):]
        later = 0.0
        for stage in stages[1:]:
            if stage == "correct":
                per = s["priors"].get("correct", 60.0)
                later += -(-s["images_total"] // max(s["workers"], 1)) * per
            elif stage == "report":
                later += REPORT_SECONDS
            elif stage == "library":
                later += LIBRARY_SECONDS
        flat = {"report": REPORT_SECONDS, "library": LIBRARY_SECONDS}.get(s["stage"])
        current = self._clock.remaining_seconds() if self._clock else flat
        return None if current is None else current + later

    def _read(self, proc: subprocess.Popen) -> None:
        log_file = open(Path(self._state["run_dir"]) / "app_log.txt", "a", buffering=1)    # survives the next job
        log_file.write(f"=== {self._state['kind']} job started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        for line in proc.stdout:
            log_file.write(line)
            event = parse(line.rstrip("\n"))
            with self._cond:
                if event is None:
                    if line.strip():
                        self._state["log"].append(line.rstrip("\n"))
                else:
                    self._apply(event)
                self._bump()
        code = proc.wait()
        log_file.write(f"=== exited with code {code} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_file.close()
        with self._cond:
            s = self._state
            if s.get("status") == "running":
                s["status"] = "cancelled" if s.get("cancel_requested") else ("done" if code == 0 else "failed")
                if s["status"] == "failed" and not s.get("error"):
                    s["error"] = f"pipeline exited with code {code}"
            s["finished_at"] = time.time()
            s["elapsed_seconds"] = s["finished_at"] - s["started_at"]
            self._bump()

    def _apply(self, event: dict) -> None:
        s, kind = self._state, event["kind"]
        if kind == "stage":
            s.update(stage=event["stage"], done=0, total=0, last=STAGE_LABELS.get(event["stage"], event["stage"]))
            self._clock = None
            s["log"].append(f"— {STAGE_LABELS.get(event['stage'], event['stage'])}")
        elif kind == "progress":
            s.update(done=event["done"], total=event["total"])
            self._clock = StageClock(event["total"], s["priors"].get(event["stage"], 60.0), event.get("workers", 1))
        elif kind == "image":
            s.update(done=event["done"], total=event["total"])
            if self._clock:
                self._clock.item(cached=event.get("status") == "cached")
            r2 = f", R² {event['r2_start']:.2f} → {event['r2_end']:.2f}" if event.get("r2_end") is not None else ""
            secs = f", {event['seconds']:.0f} s" if event.get("seconds") else ""
            s["last"] = f"{event['cycle']} tile {event['tile']}: {event['detail']}{r2}{secs}"
            s["log"].append(f"[{event['done']}/{event['total']}] {s['last']}")
        elif kind == "log":
            s["log"].append(event["message"])
        elif kind == "finished":
            s["status"] = "done"
        elif kind == "failed":
            s.update(status="failed", error=event["error"])
            s["log"].extend(event.get("traceback", "").splitlines())

