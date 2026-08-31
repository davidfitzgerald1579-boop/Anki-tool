"""Spot slide words printed in an accent colour.

Course slides mark key terms by colouring them differently from the
rest of the sentence. OCR alone flattens that signal away, so this
module re-reads the snip with word bounding boxes (ocr.extract_words),
samples each word's ink colour from the image, and flags the words
whose ink clearly differs from the page's dominant ink - but only on
lines that MIX both colours, so a heading set entirely in the accent
colour doesn't flag every word. The flagged phrases are handed to the
LLM as must-incorporate key terms.

Everything is best-effort: any failure returns [] and generation
continues without the hint.
"""

from __future__ import annotations

from . import ocr

# a word's ink must differ from the page's dominant ink by at least
# this much (RGB euclidean, 0-441) to count as accent-coloured
_DEFAULT_THRESHOLD = 110
# pixels further than this from the local background count as ink
_INK_CONTRAST = 60
_MAX_PHRASES = 8


def _dist(a, b) -> float:
    return (
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    ) ** 0.5


def ink_color(img, x: int, y: int, w: int, h: int):
    """Mean colour of the 'ink' pixels in a word's box, or None.

    The most common (quantised) colour in the box is taken as the
    background; pixels far from it are the letter strokes.
    """
    x0, y0 = max(0, x), max(0, y)
    x1 = min(img.width(), x + max(1, w))
    y1 = min(img.height(), y + max(1, h))
    if x1 <= x0 or y1 <= y0:
        return None
    # sample at most ~40x20 points per word
    step_x = max(1, (x1 - x0) // 40)
    step_y = max(1, (y1 - y0) // 20)
    pixels = []
    for py in range(y0, y1, step_y):
        for px in range(x0, x1, step_x):
            rgb = img.pixel(px, py)
            pixels.append(
                ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)
            )
    if len(pixels) < 12:
        return None
    buckets: dict = {}
    for p in pixels:
        key = (p[0] // 32, p[1] // 32, p[2] // 32)
        buckets[key] = buckets.get(key, 0) + 1
    bg_key = max(buckets, key=buckets.get)
    bg = tuple(c * 32 + 16 for c in bg_key)
    ink = [p for p in pixels if _dist(p, bg) > _INK_CONTRAST]
    if len(ink) < 6:
        return None
    n = len(ink)
    return (
        sum(p[0] for p in ink) // n,
        sum(p[1] for p in ink) // n,
        sum(p[2] for p in ink) // n,
    )


def attach_colors(img, words: list) -> None:
    """Sample each word's ink colour into word["rgb"] (None if unclear)."""
    for word in words:
        word["rgb"] = ink_color(
            img, word["x"], word["y"], word["w"], word["h"]
        )


def _median_color(colors: list):
    def med(values):
        values = sorted(values)
        return values[len(values) // 2]

    return (
        med([c[0] for c in colors]),
        med([c[1] for c in colors]),
        med([c[2] for c in colors]),
    )


def accent_phrases(words: list, threshold: float = _DEFAULT_THRESHOLD):
    """Phrases (adjacent flagged words joined) in the accent colour.

    A word is flagged when its ink is far from the page's dominant ink
    AND its line also contains normally-coloured words - a line that is
    entirely accent-coloured (a heading) flags nothing.
    """
    colored = [w for w in words if w.get("rgb") is not None]
    if len(colored) < 4:
        return []
    dominant = _median_color([w["rgb"] for w in colored])

    def flagged(word) -> bool:
        return _dist(word["rgb"], dominant) > threshold

    # group by line, preserving word order
    lines: dict = {}
    for word in colored:
        lines.setdefault(word["l"], []).append(word)

    phrases = []
    seen = set()
    for line_words in lines.values():
        flags = [flagged(w) for w in line_words]
        if all(flags) or not any(flags):
            continue  # uniform line: a heading, or nothing special
        run: list = []
        for word, is_accent in zip(line_words, flags):
            if is_accent and any(ch.isalnum() for ch in word["t"]):
                run.append(word["t"])
            elif run:
                phrases.append(" ".join(run))
                run = []
        if run:
            phrases.append(" ".join(run))
    unique = []
    for phrase in phrases:
        key = phrase.lower()
        if key not in seen:
            seen.add(key)
            unique.append(phrase)
    return unique[:_MAX_PHRASES]


def extract_accents(img, config: dict) -> list:
    """Accent-coloured phrases on the snip, best-effort ([] on failure)."""
    try:
        raw = config.get("ocr_accent_threshold", _DEFAULT_THRESHOLD)
        try:
            threshold = float(raw)
        except (TypeError, ValueError):
            threshold = _DEFAULT_THRESHOLD
        if threshold <= 0:  # 0 disables the feature
            return []
        words, scaled = ocr.extract_words(img, config)
        if not words or scaled is None:
            return []
        attach_colors(scaled, words)
        return accent_phrases(words, threshold=threshold)
    except Exception:
        return []
