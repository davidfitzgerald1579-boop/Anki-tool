"""Word detection for the double-click occlusion feature.

Pure pixel analysis (no OCR): around a clicked point we find the text
line's exact vertical extent, then split it into words by looking at the
gaps between ink columns. Inter-letter gaps (and the tiny gaps around a
hyphen) are much narrower than inter-word gaps, so hyphenated words come
out as a single word naturally.

All coordinates are full-image pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

from .color_utils import majority_color
from .qtshim import QImage

INK_THRESHOLD = 90  # manhattan RGB distance from background to count as ink
BAND_HALF = 60  # rows examined above/below the click
MAX_LINE_H = 64  # sanity cap on a text line's height
ROW_GAP_TOLERANCE = 2  # empty rows allowed inside one line (accents, dots)
MIN_RUN_W = 2  # ignore single-column specks


@dataclass
class Line:
    top: int  # inclusive, image coords
    bottom: int  # inclusive
    runs: list  # [(x0, x1)] inclusive ink column spans, left to right
    img_w: int
    img_h: int

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


def _ink_rows(img: QImage, y0: int, y1: int):
    """Boolean ink map for rows y0..y1 (exclusive), full image width."""
    crop = img.copy(0, y0, img.width(), y1 - y0).convertToFormat(
        QImage.Format.Format_RGB32
    )
    bg = majority_color(crop)
    br, bgc, bb = bg.red(), bg.green(), bg.blue()
    ptr = crop.constBits()
    ptr.setsize(crop.sizeInBytes())
    data = bytes(ptr)
    bpl = crop.bytesPerLine()
    w = crop.width()
    rows = []
    for r in range(crop.height()):
        base = r * bpl
        row = bytearray(w)
        for c in range(w):
            o = base + c * 4  # Format_RGB32 little-endian: B, G, R, A
            if (
                abs(data[o + 2] - br)
                + abs(data[o + 1] - bgc)
                + abs(data[o] - bb)
            ) > INK_THRESHOLD:
                row[c] = 1
        rows.append(row)
    return rows


def analyze_line(img: QImage, cx: float, cy: float):
    """Find the text line under (cx, cy) and its word runs, or None."""
    w, h = img.width(), img.height()
    cxi, cyi = int(cx), int(cy)
    if not (0 <= cxi < w and 0 <= cyi < h):
        return None
    y0 = max(0, cyi - BAND_HALF)
    y1 = min(h, cyi + BAND_HALF)
    rows = _ink_rows(img, y0, y1)
    has_ink = [1 if any(row) else 0 for row in rows]

    # anchor on the nearest inky row to the click
    rel = cyi - y0
    anchor = None
    for d in range(0, 13):
        for cand in (rel - d, rel + d):
            if 0 <= cand < len(rows) and has_ink[cand]:
                anchor = cand
                break
        if anchor is not None:
            break
    if anchor is None:
        return None

    # expand up/down, tolerating tiny internal gaps (dots on i, accents)
    top = anchor
    gap = 0
    while top - 1 >= 0 and (anchor - top) < MAX_LINE_H:
        if has_ink[top - 1]:
            top -= 1
            gap = 0
        elif gap < ROW_GAP_TOLERANCE:
            top -= 1
            gap += 1
        else:
            break
    while not has_ink[top]:
        top += 1
    bottom = anchor
    gap = 0
    while bottom + 1 < len(rows) and (bottom - anchor) < MAX_LINE_H:
        if has_ink[bottom + 1]:
            bottom += 1
            gap = 0
        elif gap < ROW_GAP_TOLERANCE:
            bottom += 1
            gap += 1
        else:
            break
    while not has_ink[bottom]:
        bottom -= 1

    line_h = bottom - top + 1
    col_ink = bytearray(w)
    for r in range(top, bottom + 1):
        row = rows[r]
        for c in range(w):
            if row[c]:
                col_ink[c] = 1

    # split ink columns into words: gaps narrower than the threshold
    # (inter-letter spacing, the sliver around a hyphen) merge into one run
    gap_thr = min(8, max(3, round(line_h * 0.22)))
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
    if not runs:
        return None
    return Line(top=y0 + top, bottom=y0 + bottom, runs=runs, img_w=w, img_h=h)


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


def box_for_runs(line: Line, first, last) -> tuple:
    """Padded rect covering the runs first..last completely, with padding
    that stops inside the gaps so it never overlaps a neighbouring word."""
    pad = max(2.0, line.height * 0.15)
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

    x0 = max(0.0, first[0] - left_pad)
    x1 = min(float(line.img_w), last[1] + 1 + right_pad)
    y0 = max(0.0, line.top - pad)
    y1 = min(float(line.img_h), line.bottom + 1 + pad)
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
