"""Bleedover Corrector: a local desktop app around this repo's bleedover correction.

The app is a thin layer. All science lives in the existing packages (``utils``,
``simulator``, ``correction``) and is imported unchanged; this folder only adds:

- reading an experiment folder (``experiment_info``, ``roles``, ``fastq``);
- choosing a model and optionally calibrating it (``pipeline.calibrate``);
- running the correction with live progress and an ETA (``jobs``, ``timing``,
  ``pipeline.correct``);
- a report with headline metrics and default plots (``pipeline.report``,
  ``pipeline.plots``) and an image viewer for corrected images (``viewer``);
- a small local web server (``server``) and the browser UI (``static/``).

Start it with ``python -m bleedover_app`` from the repo root (``mapa`` env).
"""
