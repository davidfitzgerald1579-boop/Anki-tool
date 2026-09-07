"""Render docs/guide/guide.html to docs/Snip-Occlusion-Getting-Started.pdf.

The guide is written as HTML + CSS (print stylesheet, A4) and rendered
with a headless Chromium - the same engine Anki embeds - so it can use
the repo's screenshots directly. Run from the repo root:

    python3 tools/build_guide.py

Needs a Chrome/Chromium binary on PATH (chromium, chromium-browser,
google-chrome, chrome) or in CHROME_BIN. The screenshot of the AI
settings section (docs/guide/settings_ai.png) is captured offscreen
with tools/settings_screenshot.py.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "guide" / "guide.html"
OUT = ROOT / "docs" / "Snip-Occlusion-Getting-Started.pdf"

CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


def find_chrome() -> str:
    for candidate in CANDIDATES:
        if not candidate:
            continue
        path = shutil.which(candidate) or (
            candidate if os.path.exists(candidate) else None
        )
        if path:
            return path
    # Playwright's bundled Chromium, if present
    for base in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), "/opt/pw-browsers"):
        if base and os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                exe = Path(base) / name / "chrome-linux" / "chrome"
                if exe.exists():
                    return str(exe)
    sys.exit("No Chrome/Chromium found - set CHROME_BIN to its path.")


def main() -> None:
    chrome = find_chrome()
    cmd = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-background-networking",
        "--disable-component-update",
        "--no-pdf-header-footer",
        "--virtual-time-budget=5000",
        "--print-to-pdf=%s" % OUT,
        SRC.as_uri(),
    ]
    subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
    print("wrote", OUT, "(%d KB)" % (OUT.stat().st_size // 1024))


if __name__ == "__main__":
    main()
