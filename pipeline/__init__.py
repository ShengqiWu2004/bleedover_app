"""The work the app runs in a separate process: calibrate (optional) -> correct -> report.

A separate process keeps the app responsive, frees all memory at the end, and
can be cancelled cleanly. Entry point: ``python -m bleedover_app.pipeline <job.json>``.
"""
