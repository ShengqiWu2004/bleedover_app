"""The user's own calibrations, kept in the app's data folder so they survive failed runs and app updates.

A calibration is one experiment's line ``counts = gain × RFU + offset`` for one
built-in model (its PSF shape). It is fitted from isolated dots only, so it
doesn't depend on the image model (additive or Voronoi): an isolated dot has no
neighbours to share territory with. Hence one calibration serves both.

Stored as a JSON list in ``<app data>/calibrations.json``. The pipeline
subprocess writes here as soon as a calibration is fitted, before the
correction starts, so a correction that fails later doesn't lose it. Writes
replace the file atomically.
"""

import json
import os
import time
import uuid
from pathlib import Path

from .config import app_data_dir


class CalibrationStore:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "calibrations.json"

    def entries(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []

    def _write(self, entries: list[dict]) -> None:
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(entries, indent=1))
        tmp.replace(self.path)

    def find(self, model_id: str, experiment: str) -> dict | None:
        return next((e for e in self.entries() if e["model"] == model_id and e["experiment"] == experiment), None)

    def add(self, *, model_id: str, experiment: str, gain: float, offset: float, **details) -> dict:
        """Save (replacing any earlier calibration of the same model and experiment)."""
        entry = {"id": uuid.uuid4().hex[:12], "model": model_id, "experiment": experiment, "gain": float(gain),
                 "offset": float(offset), "created": time.strftime("%Y-%m-%d %H:%M"), **details}
        others = [e for e in self.entries() if not (e["model"] == model_id and e["experiment"] == experiment)]
        self._write(others + [entry])
        return entry

    def delete(self, calibration_id: str) -> None:
        entries = self.entries()
        kept = [e for e in entries if e["id"] != calibration_id]
        if len(kept) == len(entries):
            raise FileNotFoundError(f"no saved calibration {calibration_id!r}")
        self._write(kept)
