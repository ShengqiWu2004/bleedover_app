"""Start the app: ``python -m bleedover_app`` from the repo root, in the ``mapa`` environment.

Opens the page in its own window (Chrome or Edge "app" mode when installed,
otherwise the default browser). If the app is already running on the port, it
just opens another window to it.
"""

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PORT = 8765
APP_BROWSERS = {"darwin": ["Google Chrome", "Microsoft Edge", "Chromium"]}


def already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "api/state", timeout=2) as response:
            return "prefs" in json.loads(response.read())
    except (OSError, ValueError):
        return False


def open_window(url: str) -> None:
    """A standalone app window when a Chromium browser exists; otherwise a normal browser tab."""
    if sys.platform == "darwin":
        for name in APP_BROWSERS["darwin"]:
            if Path(f"/Applications/{name}.app").exists():
                subprocess.Popen(["open", "-na", name, "--args", f"--app={url}"])
                return
    for exe in ("google-chrome", "chromium", "microsoft-edge", "chrome", "msedge"):
        if shutil.which(exe):
            subprocess.Popen([shutil.which(exe), f"--app={url}"])
            return
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bleedover Corrector")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-window", action="store_true", help="start the server without opening a window")
    parser.add_argument("--idle-exit", type=float, default=0, metavar="MINUTES",
                        help="quit when no window has been open for this long and nothing runs (the standalone app uses 10)")
    args, _ = parser.parse_known_args()     # Finder may add its own arguments to an app launch
    url = f"http://127.0.0.1:{args.port}/"
    if already_running(url):
        print(f"Bleedover Corrector is already running at {url}")
        open_window(url)
        return
    from bleedover_app.server import make_server, stop_when_idle
    server = make_server(args.port)
    if args.idle_exit:
        stop_when_idle(server, args.idle_exit * 60)
    print(f"Bleedover Corrector running at {url}  (Ctrl+C to quit)", flush=True)
    if not args.no_window:
        open_window(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        from bleedover_app.api import jobs
        jobs.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
