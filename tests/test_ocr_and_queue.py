"""Tests for the OCR pipeline (logic level) and the new-card queue."""

import sys

import pytest
from PyQt6.QtGui import QColor

from snip_occlusion import ocr
from snip_occlusion.newcard import MIN_WIDTH, PAD, NewCardQueue
from tests.slide_fixture import make_slide


# ------------------------------------------------------------------- OCR


def test_apply_corrections_whole_words_only():
    corrections = {"K80": "KBD", "UTlAC": "UTIAC"}
    text = "The K80 and UTlAC. But K800 stays and SK80 stays."
    fixed = ocr.apply_corrections(text, corrections)
    assert "The KBD and UTIAC." in fixed
    assert "K800" in fixed and "SK80" in fixed


def test_backend_selection(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    if sys.platform == "win32":
        assert ocr.available_backend({"ocr_backend": "auto"}) == "windows"
    else:
        assert ocr.available_backend({"ocr_backend": "auto"}) == "none"
    assert ocr.available_backend({"ocr_backend": "none"}) == "none"
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/usr/bin/tesseract")
    assert ocr.available_backend({"ocr_backend": "tesseract"}) == "tesseract"


def test_extract_text_via_fake_tesseract(monkeypatch, qapp):
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/fake/tesseract")

    class FakeProc:
        returncode = 0
        stdout = "  The Administrative Court\n\n  K80 review  \n".encode()
        stderr = b""

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    text = ocr.extract_text(
        make_slide(),
        {"ocr_backend": "tesseract", "ocr_corrections": {"K80": "KBD"}},
    )
    assert text == "The Administrative Court\nKBD review"
    assert captured["cmd"][0] == "/fake/tesseract"
    assert captured["cmd"][2] == "stdout"


def test_large_images_downscaled_for_ocr_only(qapp, tmp_path):
    big = make_slide(3200, 1000)
    out = str(tmp_path / "ocr.png")
    ocr._prepare_ocr_png(big, out)
    from PyQt6.QtGui import QImage

    saved = QImage(out)
    assert max(saved.width(), saved.height()) <= ocr._MAX_OCR_DIM
    assert big.width() == 3200  # original untouched


# ------------------------------------------------------- new card queue


def test_compose_stacks_snips_on_background(qapp):
    q = NewCardQueue()
    card = q.new_card(QColor("#fbf3e4"))
    a = make_slide(400, 60)
    b = make_slide(500, 90)
    card.add_snip(a)
    card.add_snip(b)
    img = card.compose()
    assert img.width() == 500 + 2 * PAD
    assert img.height() == 60 + 90 + 3 * PAD
    # background colour where no snip sits
    assert img.pixelColor(3, 3).name() == "#fbf3e4"
    # snips are pixel-identical at their expected offsets
    assert img.pixelColor(PAD + 5, PAD + 5) == a.pixelColor(5, 5)
    assert img.pixelColor(PAD + 5, PAD + 60 + PAD + 5) == b.pixelColor(5, 5)


def test_compose_minimum_width_and_empty_card(qapp):
    q = NewCardQueue()
    card = q.new_card(QColor("#ffffff"))
    tiny = make_slide(80, 30)
    card.add_snip(tiny)
    img = card.compose()
    assert img.width() == MIN_WIDTH
    empty = q.new_card(QColor("#ffffff")).compose()
    assert empty.width() == MIN_WIDTH and empty.height() > 0


def test_queue_order_and_removal(qapp):
    q = NewCardQueue()
    a = q.new_card(QColor("#ffffff"))
    b = q.new_card(QColor("#ffffff"))
    c = q.new_card(QColor("#ffffff"))
    q.remove(b.id)
    assert len(q) == 2
    assert q.pop_next() is a
    assert q.pop_next() is c
    assert q.pop_next() is None


# ---------------------------------------------------- queue panel widget


def test_queue_panel_widget_lifecycle(qapp):
    from snip_occlusion.newcard_panel import NewCardQueuePanel

    panel = NewCardQueuePanel()
    panel.default_bg = QColor("#fbf3e4")
    assert not panel.has_cards()
    card = panel.add_card_with_snip(make_slide(300, 60))
    empty = panel.add_empty_card()
    assert panel.has_cards() and len(panel.queue) == 2
    assert panel.start_btn.isEnabled()

    # simulate a drop routed through the dialog's handler
    dropped = {}

    def handler(card_id, patch_id):
        dropped["args"] = (card_id, patch_id)
        panel.queue.card_by_id(card_id).add_snip(make_slide(200, 40))
        return True

    panel.patch_drop_handler = handler
    assert panel.on_patch_dropped(empty.id, "abc123")
    assert dropped["args"] == (empty.id, "abc123")
    assert len(empty.snips) == 1

    panel.delete_card(card.id)
    assert len(panel.queue) == 1
    assert panel.pop_next() is empty
    assert not panel.has_cards()
    assert not panel.start_btn.isEnabled()
