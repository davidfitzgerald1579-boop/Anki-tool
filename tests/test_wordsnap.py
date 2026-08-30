"""Tests for pixel-level word detection (double-click occlusion)."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from snip_occlusion import wordsnap
from tests.slide_fixture import make_slide

SENTENCE = "The solicitor-advocate spoke clearly today"
FONT = ("Arial", 14)
X0, Y0 = 20, 12


def make_text_image(text=SENTENCE, w=760, h=64):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setPen(QColor("#222222"))
    p.setFont(QFont(*FONT))
    p.drawText(QRectF(X0, Y0, w - X0, h - Y0), Qt.AlignmentFlag.AlignLeft, text)
    p.end()
    return img


def word_x_ranges(text=SENTENCE):
    """Approximate x extents of each word as rendered, via font metrics."""
    fm = QFontMetrics(QFont(*FONT))
    ranges = []
    x = X0
    for word in text.split(" "):
        wpx = fm.horizontalAdvance(word)
        ranges.append((word, x, x + wpx))
        x += wpx + fm.horizontalAdvance(" ")
    return ranges


def click_point(word_index):
    _, x0, x1 = word_x_ranges()[word_index]
    return (x0 + x1) / 2, Y0 + 12


def test_analyze_line_finds_words_and_extent(qapp):
    img = make_text_image()
    cx, cy = click_point(0)
    line = wordsnap.analyze_line(img, cx, cy)
    assert line is not None
    # the sentence has 5 space-separated tokens; the hyphenated word must
    # be ONE run, so we expect exactly 5 runs
    assert len(line.runs) == 5
    fm = QFontMetrics(QFont(*FONT))
    assert 0 < line.height <= fm.height() + 6
    assert line.top >= Y0 - 2


def test_hyphenated_word_is_one_word(qapp):
    img = make_text_image()
    cx, cy = click_point(1)  # middle of "solicitor-advocate"
    found = wordsnap.word_box_at(img, cx, cy)
    assert found is not None
    (x, y, w, h), line = found
    _, wx0, wx1 = word_x_ranges()[1]
    # box covers the whole hyphenated token...
    assert x <= wx0 + 2 and x + w >= wx1 - 2
    # ...but stops before its neighbours
    _, prev_x0, prev_x1 = word_x_ranges()[0]
    _, next_x0, next_x1 = word_x_ranges()[2]
    assert x > prev_x1 - 2
    assert x + w < next_x0 + 2


def test_word_box_never_overlaps_neighbour_ink(qapp):
    img = make_text_image()
    for i in range(5):
        cx, cy = click_point(i)
        found = wordsnap.word_box_at(img, cx, cy)
        assert found is not None, "no box for word %d" % i
        (x, y, w, h), line = found
        # columns just outside the box hold no ink (nothing much darker
        # than the white background) on this line
        for probe_x in (int(x) - 1, int(x + w) + 1):
            if probe_x < 0 or probe_x >= img.width():
                continue
            for probe_y in range(line.top, line.bottom + 1):
                c = img.pixelColor(probe_x, probe_y)
                luma = (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000
                assert 255 - luma <= wordsnap.LUMA_MARGIN


def test_snap_box_swallows_and_releases_whole_words(qapp):
    img = make_text_image()
    cx, cy = click_point(2)  # "spoke"
    (x, y, w, h), line = wordsnap.word_box_at(img, cx, cy)
    words = word_x_ranges()
    # drag the right edge into the middle of "clearly" (word 3)
    _, w3x0, w3x1 = words[3]
    nx, ny, nw, nh = wordsnap.snap_box(
        line, x, (w3x0 + w3x1) / 2, anchor_cx=cx
    )
    assert nx + nw >= w3x1 - 2  # "clearly" fully covered
    _, w4x0, _ = words[4]
    assert nx + nw < w4x0 + 2  # "today" untouched
    # shrink back to just past the original word: only "spoke" stays
    _, w2x0, w2x1 = words[2]
    sx, sy, sw, sh = wordsnap.snap_box(line, x, w2x1 - 2, anchor_cx=cx)
    assert sx + sw < w3x0 + 2


def test_analyze_line_on_bpp_style_slide(qapp):
    img = make_slide()
    # click somewhere in the first body line of the fixture slide
    line = wordsnap.analyze_line(img, 200, 122)
    assert line is not None
    assert len(line.runs) >= 6  # a full sentence of words
    assert line.height < 40


def test_tight_leading_lines_do_not_merge(qapp):
    """Regression: BPP slides set justified text so tightly that one line's
    descenders (g, j, y) share pixel rows with the next line's ascenders -
    there is NO empty row between lines. Density-based detection must
    still isolate the clicked line instead of merging both into one giant
    'line' (which produced section-sized word boxes)."""
    font = QFont("Arial", 15)
    fm = QFontMetrics(font)
    line1 = "great majority of cases enjoy judges"
    line2 = "All Court of Appeal judges are senior"
    b1 = 40
    # negative leading: line 1's descenders and line 2's ascenders share
    # rows, so no empty pixel row separates the lines (the BPP situation)
    b2 = b1 + fm.ascent() + fm.descent() - 3
    img = QImage(760, 120, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setPen(QColor("#222222"))
    p.setFont(font)
    p.drawText(QPointF(20, b1), line1)
    p.drawText(QPointF(20, b2), line2)
    p.end()

    # sanity: the failure precondition holds - no empty row between lines
    from snip_occlusion.wordsnap import _ink_rows

    rows = _ink_rows(img, b1, b2)
    assert all(any(r) for r in rows)

    # click the middle of "Appeal" on line 2
    x = 20.0
    for word in line2.split(" "):
        adv = fm.horizontalAdvance(word)
        if word == "Appeal":
            cx = x + adv / 2
            break
        x += adv + fm.horizontalAdvance(" ")
    found = wordsnap.word_box_at(img, cx, b2 - fm.ascent() / 2)
    assert found is not None
    (bx, by, bw, bh), line = found
    # a single word's height, not a merged two-line section (which would
    # be roughly two ascents tall)
    assert bh <= fm.height() + 12
    assert bh < 2 * fm.ascent()
    assert bx <= cx - fm.horizontalAdvance("Appeal") / 2 + 3
    assert bx + bw >= cx + fm.horizontalAdvance("Appeal") / 2 - 3
    assert bw < fm.horizontalAdvance("Appeal judges")  # just one word
    assert len(line.runs) == len(line2.split(" "))


from PyQt6.QtCore import QPointF  # noqa: E402


def test_wrapped_highlight_does_not_merge_lines(qapp):
    """Regression: BPP highlights words in yellow, and a highlight that
    wraps at a line break fills the whole gap between the two lines with
    colour. Ink must mean dark strokes only, so the highlight band is
    invisible to line detection."""
    font = QFont("Arial", 15)
    fm = QFontMetrics(font)
    line1 = "hear appeals on a wide range of cases"
    line2 = "All Court of Appeal judges are senior"
    b1 = 40
    b2 = b1 + fm.height() + 2

    # x-extent of "Appeal judges" on line 2 - the highlighted words
    x = 20.0
    coords = {}
    for word in line2.split(" "):
        adv = fm.horizontalAdvance(word)
        coords[word] = (x, x + adv)
        x += adv + fm.horizontalAdvance(" ")
    hl_x0 = coords["Appeal"][0] - 4
    hl_x1 = coords["judges"][1] + 4

    img = QImage(760, 120, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    # the yellow band spans from inside line 1 down through line 2,
    # bridging the entire inter-line gap (like a wrapped highlight)
    p.fillRect(
        QRectF(hl_x0, b1 - 8, hl_x1 - hl_x0, (b2 + 5) - (b1 - 8)),
        QColor("#ffe94d"),
    )
    p.setPen(QColor("#222222"))
    p.setFont(font)
    p.drawText(QPointF(20, b1), line1)
    p.drawText(QPointF(20, b2), line2)
    p.end()

    # click an unhighlighted word on line 2 ("senior")
    cx = (coords["senior"][0] + coords["senior"][1]) / 2
    found = wordsnap.word_box_at(img, cx, b2 - fm.ascent() / 2)
    assert found is not None
    (bx, by, bw, bh), line = found
    assert bh <= fm.height() + 12  # one line, not a merged section
    assert by > b1  # stays on line 2
    assert bw < fm.horizontalAdvance("are senior")  # one word only

    # click a word INSIDE the yellow highlight ("judges")
    cx2 = (coords["judges"][0] + coords["judges"][1]) / 2
    found2 = wordsnap.word_box_at(img, cx2, b2 - fm.ascent() / 2)
    assert found2 is not None
    (jx, jy, jw, jh), _ = found2
    assert jh <= fm.height() + 12
    assert jx <= coords["judges"][0] + 3
    assert jx + jw >= coords["judges"][1] - 3
    assert jw < fm.horizontalAdvance("Appeal judges")


def test_adaptive_threshold_recovers_faint_leading_word(qapp):
    """Regression for pink text losing letters at the start of a sentence:
    when a line's detected ink is faint (coloured text), the threshold is
    re-tuned to that line, so letters too pale for the strict pass are
    recovered. Simulated by painting the first word paler than the rest,
    below the strict margin but above the adaptive floor."""
    font = QFont("Arial", 15)
    fm = QFontMetrics(font)
    img = QImage(700, 70, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setFont(font)
    # "All" too faint for the strict pass (darkness ~50 < 60)
    p.setPen(QColor("#f2b8cf"))
    p.drawText(QPointF(20, 45), "All")
    # the rest barely-strong (darkness ~80), like ClearType pink
    rest_x = 20 + fm.horizontalAdvance("All ")
    p.setPen(QColor("#f08bb0"))
    p.drawText(QPointF(rest_x, 45), "Court of Appeal judges")
    p.end()

    # strict pass alone cannot see "All"...
    strict = wordsnap._ink_rows(img, 20, 60)
    assert not any(row[c] for row in strict for c in range(20, 38))
    # ...but a click on it still yields a box covering it, because the
    # adaptive pass lowers the bar to this line's actual ink darkness
    adv = fm.horizontalAdvance("All")
    found = wordsnap.word_box_at(img, 20 + adv / 2, 45 - fm.ascent() / 2)
    assert found is not None
    (x, y, w, h), line = found
    assert x <= 21  # box starts at (or before) the first letter
    assert x + w >= 20 + adv - 3  # and covers the whole word
    assert len(line.runs) == 5


def test_adaptive_threshold_stays_strict_for_dark_text(qapp):
    """Black text keeps the strict threshold: light-grey decorations near
    a dark line must not become ink via the adaptive pass."""
    font = QFont("Arial", 15)
    img = QImage(700, 70, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setFont(font)
    p.setPen(QColor("#222222"))
    p.drawText(QPointF(20, 45), "Court of Appeal judges")
    # faint grey decoration on the same rows (darkness ~42: between the
    # adaptive floor and the strict margin)
    p.fillRect(QRectF(500, 30, 12, 12), QColor("#c6c6c6"))
    p.end()
    line = wordsnap.analyze_line(img, 60, 38)
    assert line is not None
    # the decoration did not become a phantom word
    assert all(r[1] < 480 for r in line.runs)


def test_no_word_in_empty_area(qapp):
    img = make_text_image()
    wordsnap.word_box_at(img, 740, 60)  # far corner: must not raise
    blank = QImage(200, 100, QImage.Format.Format_RGB32)
    blank.fill(QColor("#ffffff"))
    assert wordsnap.analyze_line(blank, 100, 50) is None
