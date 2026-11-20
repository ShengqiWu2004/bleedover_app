"""Native "choose folder" dialog. A browser page can't see absolute paths, so the server opens it.

macOS uses AppleScript (no extra packages); elsewhere a short tkinter
subprocess (tk must own its main thread, which the server's threads don't).
"""

import subprocess
import sys
from pathlib import Path

TIMEOUT = 600


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def choose_folder(prompt: str, start: str | None = None) -> str | None:
    """Absolute path of the chosen folder, or None if the user cancelled."""
    start = start if start and Path(start).is_dir() else str(Path.home())
    if sys.platform == "darwin":
        script = (f"POSIX path of (choose folder with prompt {_applescript_string(prompt)} "
                  f"default location (POSIX file {_applescript_string(start)}))")
        done = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=TIMEOUT)
    else:
        code = ("import sys, tkinter as tk; from tkinter import filedialog; r = tk.Tk(); r.withdraw(); "
                "r.attributes('-topmost', True); print(filedialog.askdirectory(title=sys.argv[1], initialdir=sys.argv[2]))")
        done = subprocess.run([sys.executable, "-c", code, prompt, start], capture_output=True, text=True,
                              timeout=TIMEOUT)
    path = done.stdout.strip()
    if done.returncode != 0 or not path:
        return None                      # cancelled (osascript exits with -128)
    return path.rstrip("/") or "/"
