"""Word detection for the double-click occlusion feature.

Pure pixel analysis (no OCR): around a clicked point we find the text
line's exact vertical extent, then split it into words by looking at the
gaps between ink columns. Inter-letter gaps (and the tiny gaps around a
hyphen) are much narrower than inter-word gaps, so hyphenated words come
out as a single word naturally.

Ink means DARK STROKES, not "different from the background": BPP slides
put yellow highlight bands and pink callout boxes behind the text, and a
wrapped highlight fills the gap between two lines. Those are backgrounds,
not ink - only pixels substantially darker than the local background
count.

Coloured (pink) text is fainter than black, and subpixel antialiasing
lightens its strokes further - a fixed darkness bar can miss letters. So
detection runs twice: a strict first pass finds the line and measures how
dark its ink actually is, then a second pass rescans with a threshold
calibrated to that text colour. The threshold never drops below a floor
that keeps highlight bands and callout backgrounds excluded.

All coordinates are full-image pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

from .color_utils import majority_color
from .qtshim import QImage

LUMA_MARGIN = 60  # strict pass: this much darker than background = ink
ADAPTIVE_FLOOR = 36  # threshold never drops below this (yellow highlight
                     # ~33, pink callout ~32 must always stay background)
BAND_HALF = 90  # rows examined above/below the click
MAX_LINE_H = 140  # sanity cap on a text line's height
MIN_RUN_W = 2  # ignore single-column specks

# Line boundaries are found by ink DENSITY, not empty rows: in tightly-set
# justified text (BPP slides) the descenders of one line share pixel rows
# with the next line's ascenders, so a fully empty row may never exist.
# A line's body rows have dozens of inked columns; the overlap rows between
# lines have only a few stray tails - the density valley marks the split.
STRONG_FRACTION = 0.18  # of the local peak: definitely inside a line
# Below this fraction of the peak the line has ended. Calibration: a text
# line's x-height rows run 60-100% of peak and ascender-only rows 20-40%,
# while stray descender tails between lines carry only 2-8% - so 12%
# separates them. A line's own descenders may be trimmed here too; the
# per-word vertical refinement in box_for_runs adds them back.
WEAK_FRACTION = 0.12


@dataclass
class Line:
    top: int  # inclusive, image coords
    bottom: int  # inclusive
    runs: list  # [(x0, x1)] inclusive ink column spans, left to right
    img_w: int
    img_h: int
    y0: int = 0  # image row of ink[0]
    ink: list = None  # per-row ink bytearrays for the analyzed band

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


def _luma_1000(r: int, g: int, b: int) -> int:
    return r * 299 + g * 587 + b * 114  # standard weights, x1000


def _diff_rows(img: QImage, y0: int, y1: int):
    """Per-pixel darkness relative to the band's background (x1000)."""
    crop = img.copy(0, y0, img.width(), y1 - y0).convertToFormat(
        QImage.Format.Format_RGB32
    )
    bg = majority_color(crop)
    bg_luma = _luma_1000(bg.red(), bg.green(), bg.blue())
    dark_background = bg_luma < 128000  # rare: light text on a dark slide
    ptr = crop.constBits()
    ptr.setsize(crop.sizeInBytes())
    data = bytes(ptr)
    bpl = crop.bytesPerLine()
    w = crop.width()
    diffs = []
    for r in range(crop.height()):
        base = r * bpl
        row = [0] * w
        for c in range(w):
            o = base + c * 4  # Format_RGB32 little-endian: B, G, R, A
            luma = _luma_1000(data[o + 2], data[o + 1], data[o])
            row[c] = luma - bg_luma if dark_background else bg_luma - luma
        diffs.append(row)
    return diffs, w


def _binarize(diffs: list, margin: int):
    """Ink map at the given darkness margin (margin in luma units)."""
    m = margin * 1000
    return [
        bytearray(1 if d > m else 0 for d in row) for row in diffs
    ]


def _ink_rows(img: QImage, y0: int, y1: int, margin: int = LUMA_MARGIN):
    """Boolean ink map for rows y0..y1 (exclusive), full image width."""
    diffs, _w = _diff_rows(img, y0, y1)
    return _binarize(diffs, margin)


def _line_extent(rows: list, rel: int):
    """(top, bottom) rows of the text line containing `rel`, or None."""
    counts = [sum(row) for row in rows]
    n = len(rows)
    smooth = [
        (counts[max(0, r - 1)] + counts[r] + counts[min(n - 1, r + 1)]) / 3.0
        for r in range(n)
    ]

    anchor = None
    for d in range(0, 13):
        for cand in (rel - d, rel + d):
            if 0 <= cand < n and counts[cand] > 0:
                anchor = cand
                break
        if anchor is not None:
            break
    if anchor is None:
        return None

    peak_lo = max(0, anchor - MAX_LINE_H // 3)
    peak_hi = min(n, anchor + MAX_LINE_H // 3)
    local_peak = max(smooth[peak_lo:peak_hi]) or 1.0
    strong = max(3.0, local_peak * STRONG_FRACTION)
    weak = max(1.5, local_peak * WEAK_FRACTION)

    # seed inside the line's dense body (the click may be on a sparse
    # ascender/descender row)
    seed = anchor
    for d in range(0, 19):
        for cand in (anchor - d, anchor + d):
            if 0 <= cand < n and smooth[cand] >= strong:
                seed = cand
                break
        else:
            continue
        break

    # expand while the density stays above the valley floor; the stop test
    # uses RAW counts - smoothing would bridge a one-row valley between
    # tightly-set lines and merge them
    top = seed
    while top - 1 >= 0 and counts[top - 1] >= weak and (seed - top) < MAX_LINE_H:
        top -= 1
    bottom = seed
    while (
        bottom + 1 < n
        and counts[bottom + 1] >= weak
        and (bottom - seed) < MAX_LINE_H
    ):
        bottom += 1
    while top < bottom and counts[top] == 0:
        top += 1
    while bottom > top and counts[bottom] == 0:
        bottom -= 1
    return top, bottom


def _adaptive_margin(diffs: list, rows: list, top: int, bottom: int) -> int:
    """Darkness threshold tuned to this line's own ink.

    Black text sits far above the strict margin, so the threshold stays
    strict. Coloured/antialiased text hovers just above it - the lower
    quartile of its ink darkness is small, and half of that recovers the
    faint stroke pixels the strict pass missed.
    """
    samples = []
    for r in range(top, bottom + 1):
        row = rows[r]
        drow = diffs[r]
        for c in range(len(row)):
            if row[c]:
                samples.append(drow[c])
        if len(samples) > 20000:
            break
    if not samples:
        return LUMA_MARGIN
    samples.sort()
    p25 = samples[len(samples) // 4] / 1000.0
    return int(min(LUMA_MARGIN, max(ADAPTIVE_FLOOR, round(p25 * 0.5))))


def _runs_for(rows: list, top: int, bottom: int, w: int):
    line_h = bottom - top + 1
    col_ink = bytearray(w)
    for r in range(top, bottom + 1):
        row = rows[r]
        for c in range(w):
            if row[c]:
                col_ink[c] = 1

    # split ink columns into words: gaps narrower than the threshold
    # (inter-letter spacing, the sliver around a hyphen) merge into one run
    # (line_h is the dense body only, so the factor is a little higher)
    gap_thr = max(3, round(line_h * 0.3))
    runs = []
    run_start = None
    gap_len = 0
    for c in range(w):
        if col_ink[c]:
            if run_start is None:
                run_start = c
            gap_len = 0
            run_end = c
        elif run_start is not None:
            gap_len += 1
            if gap_len >= gap_thr:
                if run_end - run_start + 1 >= MIN_RUN_W:
                    runs.append((run_start, run_end))
                run_start = None
    if run_start is not None and run_end - run_start + 1 >= MIN_RUN_W:
        runs.append((run_start, run_end))
    return runs


def analyze_line(img: QImage, cx: float, cy: float):
    """Find the text line under (cx, cy) and its word runs, or None."""
    w, h = img.width(), img.height()
    cxi, cyi = int(cx), int(cy)
    if not (0 <= cxi < w and 0 <= cyi < h):
        return None
    y0 = max(0, cyi - BAND_HALF)
    y1 = min(h, cyi + BAND_HALF)
    diffs, w = _diff_rows(img, y0, y1)
    rel = cyi - y0

    # strict pass: find the line with definite ink only
    rows = _binarize(diffs, LUMA_MARGIN)
    extent = _line_extent(rows, rel)
    if extent is None:
        return None
    top, bottom = extent

    # adaptive pass: if this line's ink is faint (coloured text), rescan
    # with a threshold tuned to it so pale strokes and letters count too
    margin = _adaptive_margin(diffs, rows, top, bottom)
    if margin < LUMA_MARGIN:
        rows = _binarize(diffs, margin)
        extent = _line_extent(rows, rel)
        if extent is not None:
            top, bottom = extent

    runs = _runs_for(rows, top, bottom, w)
    if not runs:
        return None
    return Line(
        top=y0 + top,
        bottom=y0 + bottom,
        runs=runs,
        img_w=w,
        img_h=img.height(),
        y0=y0,
        ink=rows,
    )


def run_at(line: Line, cx: float):
    """The word run containing cx, else the nearest one."""
    cxi = int(cx)
    best = None
    best_dist = None
    for r in line.runs:
        if r[0] <= cxi <= r[1]:
            return r
        d = min(abs(cxi - r[0]), abs(cxi - r[1]))
        if best_dist is None or d < best_dist:
            best, best_dist = r, d
    return best


def _word_vertical_extent(line: Line, x0: int, x1: int):
    """Exact ink rows of the columns x0..x1: the words' own top/bottom.

    A safety net on top of line detection - even if the line estimate is
    generous, the box hugs the actual word pixels vertically.
    """
    if not line.ink:
        return line.top, line.bottom

    def row_has_ink(r: int) -> bool:
        row = line.ink[r]
        return any(row[c] for c in range(max(0, x0), min(len(row), x1 + 1)))

    core_lo = line.top - line.y0
    core_hi = line.bottom - line.y0
    top = bottom = None
    for r in range(core_lo, core_hi + 1):
        if row_has_ink(r):
            if top is None:
                top = r
            bottom = r
    if top is None:
        return line.top, line.bottom
    # extend CONTIGUOUSLY to pick up ascenders/descenders the density cut
    # trimmed; stopping at the first inkless row (in these columns) keeps
    # us from jumping across the gap into a neighbouring line
    lo = max(0, core_lo - 10)
    hi = min(len(line.ink) - 1, core_hi + 10)
    while top - 1 >= lo and row_has_ink(top - 1):
        top -= 1
    while bottom + 1 <= hi and row_has_ink(bottom + 1):
        bottom += 1
    return line.y0 + top, line.y0 + bottom


def box_for_runs(line: Line, first, last) -> tuple:
    """Padded rect covering the runs first..last completely, with padding
    that stops inside the gaps so it never overlaps a neighbouring word."""
    pad = max(2.0, min(line.height * 0.15, 6.0))
    idx_first = line.runs.index(first)
    idx_last = line.runs.index(last)

    left_pad = pad
    if idx_first > 0:
        gap = first[0] - line.runs[idx_first - 1][1] - 1
        left_pad = min(pad, max(1.0, gap / 2.0 - 1))
    right_pad = pad
    if idx_last < len(line.runs) - 1:
        gap = line.runs[idx_last + 1][0] - last[1] - 1
        right_pad = min(pad, max(1.0, gap / 2.0 - 1))

    w_top, w_bottom = _word_vertical_extent(line, first[0], last[1])
    x0 = max(0.0, first[0] - left_pad)
    x1 = min(float(line.img_w), last[1] + 1 + right_pad)
    y0 = max(0.0, w_top - pad)
    y1 = min(float(line.img_h), w_bottom + 1 + pad)
    return x0, y0, x1 - x0, y1 - y0


def word_box_at(img: QImage, cx: float, cy: float):
    """Box tightly covering the word at (cx, cy): (rect, line) or None."""
    line = analyze_line(img, cx, cy)
    if line is None:
        return None
    run = run_at(line, cx)
    if run is None:
        return None
    return box_for_runs(line, run, run), line


def snap_box(line: Line, left: float, right: float, anchor_cx: float):
    """Snap a dragged [left, right] extent to whole words on the line.

    Every word the extent touches is covered completely; if it touches
    none, the word nearest the anchor is kept (a word box never vanishes).
    """
    touched = [r for r in line.runs if r[1] >= left and r[0] <= right]
    if not touched:
        r = run_at(line, anchor_cx)
        touched = [r]
    return box_for_runs(line, touched[0], touched[-1])
