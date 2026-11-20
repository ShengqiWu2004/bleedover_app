"""Entry point of the standalone app (PyInstaller freezes this file).

One executable does four jobs:

- no arguments (a double-click): start the server in the background if it isn't running, open a
  window, and exit. The launcher must exit: the server can't answer macOS's "app, come to the front"
  request, so a second double-click on a still-running app process fails with error -600;
- ``--serve``: the background server; it quits 10 minutes after its last window closes;
- ``--pipeline <job.json>``: one calibrate/correct/report job (started by the server);
- multiprocessing workers for the parallel correction (handled by ``freeze_support``).
"""

import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

PORT = 8765
START_TIMEOUT = 300           # s; the very first launch waits while macOS checks the whole app


def launch() -> None:
    from bleedover_app.__main__ import already_running, open_window
    url = f"http://127.0.0.1:{PORT}/"
    if not already_running(url):
        log_path = Path.home() / "Library" / "Logs" / "BleedoverCorrector.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as log:
            server = subprocess.Popen([sys.executable, "--serve"], stdin=subprocess.DEVNULL, stdout=log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.time() + START_TIMEOUT
        while not already_running(url):
            if server.poll() is not None or time.time() > deadline:
                sys.exit(f"the server didn't start; see {log_path}")
            time.sleep(0.5)
    open_window(url)


if __name__ == "__main__":
    # PyInstaller points matplotlib at a new temporary folder in every process, which rebuilds the font
    # cache each time (seconds per worker). Use one persistent folder instead; set before workers start.
    cache = Path.home() / "Library" / "Caches" / "BleedoverCorrector" / "matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache)
    multiprocessing.freeze_support()
    if len(sys.argv) >= 3 and sys.argv[1] == "--pipeline":
        from bleedover_app.pipeline.__main__ import main as pipeline_main
        sys.exit(pipeline_main(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "--serve":
        from bleedover_app.__main__ import main
        sys.argv = [sys.argv[0], "--port", str(PORT), "--no-window", "--idle-exit", "10"]
        main()
    else:
        launch()
