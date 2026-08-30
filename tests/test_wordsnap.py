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
        # columns just outside the box hold no ink on this line
        for probe_x in (int(x) - 1, int(x + w) + 1):
            if probe_x < 0 or probe_x >= img.width():
                continue
            for probe_y in range(line.top, line.bottom + 1):
                c = img.pixelColor(probe_x, probe_y)
                dist = (
                    abs(c.red() - 255) + abs(c.green() - 255) + abs(c.blue() - 255)
                )
                assert dist <= wordsnap.INK_THRESHOLD


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


def test_no_word_in_empty_area(qapp):
    img = make_text_image()
    wordsnap.word_box_at(img, 740, 60)  # far corner: must not raise
    blank = QImage(200, 100, QImage.Format.Format_RGB32)
    blank.fill(QColor("#ffffff"))
    assert wordsnap.analyze_line(blank, 100, 50) is None
