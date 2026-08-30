"""Background-colour detection for the cover-up (text eraser) tool.

The user erases irrelevant slide text by drawing rectangles that get filled
with the slide's background colour. Two strategies:

- majority_color: the most common colour across the whole image (slides have
  one dominant background, so this is the requested default).
- local_background: per-channel median of the pixels in a thin band just
  outside a given rect - useful when erasing text sitting on a coloured
  callout box rather than the main background.
"""

from __future__ import annotations

from .qtshim import QColor, QImage


def majority_color(img: QImage, max_samples: int = 60000) -> QColor:
    """Most common colour, via a quantized histogram over sampled pixels.

    Pixels are bucketed at 4 bits per channel; the winning bucket's true
    average is returned so slight gradients/JPEG noise still resolve to a
    sensible fill colour.
    """
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return QColor("#ffffff")
    step = max(1, int(((w * h) / float(max_samples)) ** 0.5))
    buckets: dict = {}
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = img.pixelColor(x, y)
            key = (c.red() >> 4, c.green() >> 4, c.blue() >> 4)
            b = buckets.get(key)
            if b is None:
                buckets[key] = [1, c.red(), c.green(), c.blue()]
            else:
                b[0] += 1
                b[1] += c.red()
                b[2] += c.green()
                b[3] += c.blue()
    n, r, g, b = max(buckets.values(), key=lambda v: v[0])
    return QColor(round(r / n), round(g / n), round(b / n))


def local_background(
    img: QImage,
    x: float,
    y: float,
    w: float,
    h: float,
    band: int = 4,
    max_samples: int = 4000,
) -> QColor:
    """Per-channel median of a `band`-px frame just outside the given rect.

    The frame excludes the rect interior (that's the text being erased), so
    the median lands on whatever the text is sitting on.
    """
    iw, ih = img.width(), img.height()
    if iw == 0 or ih == 0:
        return QColor("#ffffff")
    x0 = max(0, int(x) - band)
    y0 = max(0, int(y) - band)
    x1 = min(iw, int(x + w) + band)
    y1 = min(ih, int(y + h) + band)
    ix0, iy0 = int(x), int(y)
    ix1, iy1 = int(x + w), int(y + h)

    coords = []
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            if ix0 <= xx < ix1 and iy0 <= yy < iy1:
                continue  # inside the rect itself
            coords.append((xx, yy))
    if not coords:
        return majority_color(img)
    step = max(1, len(coords) // max_samples)
    coords = coords[::step]

    rs, gs, bs = [], [], []
    for xx, yy in coords:
        c = img.pixelColor(xx, yy)
        rs.append(c.red())
        gs.append(c.green())
        bs.append(c.blue())
    rs.sort()
    gs.sort()
    bs.sort()
    mid = len(rs) // 2
    return QColor(rs[mid], gs[mid], bs[mid])
