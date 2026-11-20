"""Nothing in the app is ever cut off: runs ``tests/ui/layout_check.mjs`` against a real app server.

It loads ``20261116_accperct_qc`` at five window widths (1024-1920 px) and visits every tab, metric and dialog.
Needs Node, Google Chrome and the T7 drive; skipped otherwise. Takes about two minutes.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(os.environ.get("IMAGER_IMAGES", "/Volumes/T7_SW/images")) / "20261116_accperct_qc"
CHROME = Path(os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))

pytestmark = pytest.mark.skipif(not (shutil.which("node") and CHROME.exists() and EXPERIMENT.is_dir()),
                                reason="needs node, Google Chrome and the T7 drive")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def app_url():
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "bleedover_app", "--no-window", "--port", str(port)], cwd=REPO,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "api/state", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    yield url
    server.terminate()
    server.wait(timeout=10)


def test_nothing_is_cut_off_at_any_width(app_url):
    done = subprocess.run(["node", str(Path(__file__).parent / "ui" / "layout_check.mjs"), app_url, str(EXPERIMENT)],
                          capture_output=True, text=True, timeout=900)
    problems = json.loads(done.stdout or "[]") if done.stdout.strip().startswith("[") else [done.stdout + done.stderr]
    assert not problems, "cut off or out of view:\n" + "\n".join(problems)
