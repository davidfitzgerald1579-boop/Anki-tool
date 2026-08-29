"""Grab a headless screenshot of the editor canvas for the README.

Run from the repo root:  python3 tools/editor_screenshot.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from snip_occlusion.consts import DEFAULT_CONFIG  # noqa: E402
from snip_occlusion.editor_canvas import OcclusionCanvas  # noqa: E402
from snip_occlusion.shapes import Shape  # noqa: E402
from slide_fixture import make_slide  # noqa: E402


def main() -> None:
    app = QApplication.instance() or QApplication([])
    canvas = OcclusionCanvas(dict(DEFAULT_CONFIG))
    canvas.resize(900, 620)
    canvas.set_image(make_slide())

    shapes = [
        Shape(kind="rect", x=396, y=110, w=222, h=26, group="g1"),
        Shape(kind="rect", x=170, y=154, w=200, h=26),
        Shape(kind="rect", x=118, y=198, w=192, h=26, group="g1"),
        Shape(kind="rect", x=350, y=240, w=195, h=28, group="g2"),
        Shape(kind="rect", x=90, y=346, w=290, h=32, group="g2"),
    ]
    canvas.shapes.extend(shapes)
    erase = Shape(kind="erase", x=38, y=282, w=475, h=28)
    erase.color = canvas.default_erase_color(erase)
    canvas.shapes.append(erase)
    # a snip patch: a sentence cut out and dragged below the paragraph
    canvas.shapes.append(
        Shape(kind="patch", x=520, y=430, w=250, h=26, sx=40, sy=284)
    )
    canvas._group_counter = 2
    canvas.selection = {shapes[1].id}

    canvas.show()
    app.processEvents()
    canvas.fit()
    app.processEvents()
    out = ROOT / "docs" / "editor.png"
    canvas.grab().save(str(out))
    print("wrote", out)


if __name__ == "__main__":
    main()
