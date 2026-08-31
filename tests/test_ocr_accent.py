"""Tests for accent-colour word detection (no OCR backend needed)."""

import pytest

from snip_occlusion import ocr, ocr_accent


def _word(text, line, rgb):
    return {"t": text, "x": 0, "y": 0, "w": 10, "h": 10,
            "l": line, "rgb": rgb}


BLACK = (20, 20, 20)
RED = (200, 30, 30)


def test_accent_words_on_mixed_lines_are_flagged():
    words = [
        _word("The", 0, BLACK),
        _word("burden", 0, RED),
        _word("of", 0, RED),
        _word("proof", 0, RED),
        _word("rests", 0, BLACK),
        _word("on", 0, BLACK),
        _word("the", 1, BLACK),
        _word("prosecution", 1, BLACK),
    ]
    assert ocr_accent.accent_phrases(words) == ["burden of proof"]


def test_uniform_accent_line_is_a_heading_not_a_flag():
    words = [_word(t, 0, RED) for t in ["Criminal", "Courts"]] + [
        _word(t, 1, BLACK) for t in ["Some", "body", "text", "here"]
    ]
    assert ocr_accent.accent_phrases(words) == []


def test_separate_runs_make_separate_phrases_and_dedupe():
    # the page's dominant ink must be the majority colour (black)
    words = [
        _word("either", 0, RED),
        _word("way", 0, RED),
        _word("or", 0, BLACK),
        _word("summary", 0, RED),
        _word("offences", 1, BLACK),
        _word("either", 1, RED),
        _word("way", 1, RED),
        _word("only", 1, BLACK),
    ] + [_word(t, 2, BLACK) for t in ["More", "plain", "body", "text"]]
    assert ocr_accent.accent_phrases(words) == ["either way", "summary"]


def test_threshold_and_small_pages():
    words = [
        _word("a", 0, BLACK),
        _word("b", 0, (60, 60, 60)),  # dark grey: not an accent
        _word("c", 0, BLACK),
        _word("d", 0, BLACK),
    ]
    assert ocr_accent.accent_phrases(words) == []
    # fewer than 4 usable words: too little signal
    assert ocr_accent.accent_phrases(words[:3]) == []


def test_words_without_colour_are_ignored():
    words = [
        _word("The", 0, BLACK),
        _word("mens", 0, RED),
        {"t": "rea", "x": 0, "y": 0, "w": 1, "h": 1, "l": 0, "rgb": None},
        _word("test", 0, BLACK),
        _word("applies", 0, BLACK),
    ]
    assert ocr_accent.accent_phrases(words) == ["mens"]


def test_ink_color_from_image():
    pytest.importorskip("PyQt6")
    from PyQt6.QtGui import QColor, QImage, QPainter

    img = QImage(120, 30, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    # letter strokes are thin - the background must stay the majority
    p.fillRect(8, 10, 40, 4, QColor("#c81e1e"))  # "red word" strokes
    p.fillRect(70, 10, 40, 4, QColor("#141414"))  # "black word"
    p.end()
    red = ocr_accent.ink_color(img, 4, 4, 50, 22)
    black = ocr_accent.ink_color(img, 66, 4, 50, 22)
    assert red is not None and red[0] > 150 and red[1] < 90
    assert black is not None and max(black) < 60
    # a blank region has no ink
    assert ocr_accent.ink_color(img, 0, 0, 6, 6) is None


def test_tesseract_tsv_parsing():
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext",
            "1\t1\t0\t0\t0\t0\t0\t0\t600\t400\t-1\t",
            "5\t1\t1\t1\t1\t1\t10\t12\t50\t20\t96\tThe",
            "5\t1\t1\t1\t1\t2\t70\t12\t80\t20\t95\tburden",
            "5\t1\t1\t1\t2\t1\t10\t40\t90\t20\t91\tprosecution",
            "5\t1\t1\t1\t2\t2\t110\t40\t30\t20\t-1\t ",
        ]
    )
    words = ocr._parse_tesseract_tsv(tsv)
    assert [w["t"] for w in words] == ["The", "burden", "prosecution"]
    assert words[0]["l"] == words[1]["l"] != words[2]["l"]
    assert words[1]["x"] == 70 and words[1]["w"] == 80


def test_extract_accents_never_raises(monkeypatch):
    monkeypatch.setattr(
        ocr, "extract_words", lambda img, cfg: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
    )
    assert ocr_accent.extract_accents(object(), {}) == []
    # threshold 0 disables without touching OCR at all
    monkeypatch.setattr(
        ocr, "extract_words",
        lambda img, cfg: pytest.fail("should not OCR when disabled"),
    )
    assert ocr_accent.extract_accents(
        object(), {"ocr_accent_threshold": 0}
    ) == []
