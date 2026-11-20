"""Draw the app icon as PNGs (192, 512, and a macOS .icns), matching static/icons/icon.svg.

Run once after changing the icon: ``python bleedover_app/packaging/make_icons.py``.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch  # noqa: E402

ICONS = Path(__file__).resolve().parent.parent / "static" / "icons"
CIRCLES = [(27, 34, 15, "#eb6834", 0.28), (27, 34, 9, "#eb6834", 1), (44, 22, 9, "#ffffff", 0.25),
           (44, 22, 5.5, "#ffffff", 1), (45, 44, 7, "#ffffff", 0.25), (45, 44, 4, "#ffffff", 1)]


def draw(path: Path, pixels: int) -> None:
    fig = plt.figure(figsize=(1, 1), dpi=pixels)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, 64), ylim=(64, 0), aspect="equal")
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 64, 64, boxstyle="round,pad=0,rounding_size=14", color="#1c5cab"))
    for x, y, r, color, alpha in CIRCLES:
        ax.add_patch(Circle((x, y), r, color=color, alpha=alpha, lw=0))
    fig.savefig(path, dpi=pixels, transparent=True)
    plt.close(fig)


def main() -> None:
    for size in (192, 512):
        draw(ICONS / f"icon-{size}.png", size)
    if sys.platform == "darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                draw(iconset / f"icon_{size}x{size}.png", size)
                draw(iconset / f"icon_{size}x{size}@2x.png", size * 2)
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICONS / "icon.icns")], check=True)
    print(f"icons written to {ICONS}")


if __name__ == "__main__":
    main()
