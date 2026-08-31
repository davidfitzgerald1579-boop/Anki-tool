"""Trace a suggested card back to the source sentences it came from.

Computed locally by word overlap - the model is never asked, never
slowed, and never given the chance to hallucinate an attribution. The
result is a best-guess: the sentences sharing the card's substance,
highlighted inside the full source text so the user can verify the
card (and its references) against what the material actually says.
"""

from __future__ import annotations

import html
import re

_WORD_RE = re.compile(r"[a-z]{4,}")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PARA_SPLIT = re.compile(r"\n\s*\n")
MAX_HIGHLIGHTS = 8
_MIN_OVERLAP = 3  # shared substantial words for a confident match

HIGHLIGHT_STYLE = "background:#ffe58a;border-radius:3px;"


def _words(text: str) -> set:
    return set(_WORD_RE.findall((text or "").lower()))


def _sentence_grid(source: str) -> list:
    """Source as paragraphs of sentences (both orders preserved)."""
    grid = []
    for para in _PARA_SPLIT.split(source or ""):
        para = " ".join(para.split())
        if not para:
            continue
        grid.append([s for s in _SENT_SPLIT.split(para) if s.strip()])
    return grid


def highlight_html(card: dict, source: str) -> tuple:
    """(HTML of the full source with matches highlighted, match count).

    Sentences sharing >= 3 substantial words with the card are
    highlighted; if none reach that, the single best-overlapping
    sentence is (when it shares anything at all). Zero matches means
    the card may not come from this text - worth suspicion.
    """
    card_words = _words(
        " ".join(
            [
                card.get("front", ""),
                card.get("back", ""),
                card.get("notes", ""),
            ]
        )
    )
    grid = _sentence_grid(source)
    scored = []
    for pi, sentences in enumerate(grid):
        for si, sentence in enumerate(sentences):
            scored.append((len(_words(sentence) & card_words), pi, si))
    best = max((s[0] for s in scored), default=0)
    chosen = {(pi, si) for ov, pi, si in scored if ov >= _MIN_OVERLAP}
    if not chosen and best >= 1:
        chosen = {(pi, si) for ov, pi, si in scored if ov == best}
    if len(chosen) > MAX_HIGHLIGHTS:
        top = sorted(scored, reverse=True)[:MAX_HIGHLIGHTS]
        chosen = {(pi, si) for _, pi, si in top}
    rendered = []
    for pi, sentences in enumerate(grid):
        parts = []
        for si, sentence in enumerate(sentences):
            escaped = html.escape(sentence)
            if (pi, si) in chosen:
                escaped = "<span style='%s'>%s</span>" % (
                    HIGHLIGHT_STYLE,
                    escaped,
                )
            parts.append(escaped)
        rendered.append(" ".join(parts))
    return "<br><br>".join(rendered), len(chosen)
