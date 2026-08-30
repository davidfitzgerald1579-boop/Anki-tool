"""Screenshot the full Snip Occlusion dialog headlessly (no Anki needed).

Stubs the bits of aqt the dialog touches (mw.col.decks) so the real dialog
code runs, then populates it with demo content and grabs PNGs for docs.

Run from the repo root:  python3 tools/dialog_screenshot.py
"""

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (aqt requires this first)
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])

# ---- fake just enough of aqt for the dialog to run outside Anki
import snip_occlusion.dialog as dialog_mod  # noqa: E402


class _Deck:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class _Decks:
    def all_names_and_ids(self):
        return [
            _Deck(1, "Default"),
            _Deck(2, "SQE1::BPP Flashcards::Public Law"),
            _Deck(3, "SQE1::BPP Flashcards::Business Law"),
        ]

    def get_current_id(self):
        return 2


fake_mw = types.SimpleNamespace(col=types.SimpleNamespace(decks=_Decks()))
dialog_mod.mw = fake_mw

from snip_occlusion.shapes import Shape  # noqa: E402
from slide_fixture import make_slide  # noqa: E402


def main() -> None:
    out_dir = ROOT / "docs"
    out_dir.mkdir(exist_ok=True)

    parent = QWidget()  # real QWidget parent so `parent or mw` stays a widget
    dlg = dialog_mod.SnipOcclusionDialog(parent)
    dlg.resize(1280, 860)

    # load the demo slide as if it came from the clipboard
    QApplication.clipboard().setImage(make_slide())
    dlg._load_clipboard_image()

    canvas = dlg.canvas
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
    canvas.shapes.append(
        Shape(kind="highlight", x=40, y=150, w=560, h=34)
    )
    canvas._group_counter = 2
    canvas.selection = {shapes[1].id}

    # populate the new-card queue: one card with a snip, one empty
    snip = make_slide().copy(40, 280, 480, 32)
    dlg.queue_panel.default_bg = canvas.majority
    dlg.queue_panel.add_card_with_snip(snip)
    dlg.queue_panel.add_empty_card()

    dlg.header_edit.setText("Business and Property Courts")
    dlg.tags_edit.setText("SQE public-law")
    dlg._refresh_counts()

    dlg.show()
    app.processEvents()
    canvas.fit()
    app.processEvents()
    dlg.grab().save(str(out_dir / "dialog.png"))
    print("wrote", out_dir / "dialog.png")

    # second shot: sidebar collapsed for full-screen editing
    dlg._toggle_sidebar()
    app.processEvents()
    canvas.fit()
    app.processEvents()
    dlg.grab().save(str(out_dir / "dialog_collapsed.png"))
    print("wrote", out_dir / "dialog_collapsed.png")


if __name__ == "__main__":
    main()
