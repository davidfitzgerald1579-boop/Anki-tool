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
_MAX_NOTE_HIGHLIGHTS = 4
_NOTE_MIN_OVERLAP = 2  # notes are short (often just a citation)

HIGHLIGHT_STYLE = "background:#ffe58a;border-radius:3px;"
NOTE_HIGHLIGHT_STYLE = "background:#ffc9a0;border-radius:3px;"


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


def _choose(scored, min_overlap, cap):
    best = max((s[0] for s in scored), default=0)
    chosen = {(pi, si) for ov, pi, si in scored if ov >= min_overlap}
    if not chosen and best >= 1:
        chosen = {(pi, si) for ov, pi, si in scored if ov == best}
    if len(chosen) > cap:
        top = sorted(scored, reverse=True)[:cap]
        chosen = {(pi, si) for _, pi, si in top}
    return chosen


def highlight_html(card: dict, source: str) -> tuple:
    """(HTML with matches highlighted, Q/A match count, notes matches).

    The question/answer and the Notes line are traced SEPARATELY -
    notes (usually a citation or caveat) are where hallucinations
    concentrate, so they get their own colour and their own verdict.
    The third element is None when the card has no notes; 0 means the
    notes match nothing in the source - likely invented.
    """
    main_words = _words(
        "%s %s" % (card.get("front", ""), card.get("back", ""))
    )
    notes = card.get("notes", "")
    note_words = _words(notes)
    grid = _sentence_grid(source)
    scored_main, scored_notes = [], []
    for pi, sentences in enumerate(grid):
        for si, sentence in enumerate(sentences):
            words = _words(sentence)
            scored_main.append((len(words & main_words), pi, si))
            if note_words:
                scored_notes.append((len(words & note_words), pi, si))
    chosen_main = _choose(scored_main, _MIN_OVERLAP, MAX_HIGHLIGHTS)
    chosen_notes = (
        _choose(scored_notes, _NOTE_MIN_OVERLAP, _MAX_NOTE_HIGHLIGHTS)
        if note_words
        else set()
    )
    rendered = []
    for pi, sentences in enumerate(grid):
        parts = []
        for si, sentence in enumerate(sentences):
            escaped = html.escape(sentence)
            if (pi, si) in chosen_notes:  # notes colour wins overlaps
                escaped = "<span style='%s'>%s</span>" % (
                    NOTE_HIGHLIGHT_STYLE,
                    escaped,
                )
            elif (pi, si) in chosen_main:
                escaped = "<span style='%s'>%s</span>" % (
                    HIGHLIGHT_STYLE,
                    escaped,
                )
            parts.append(escaped)
        rendered.append(" ".join(parts))
    notes_result = len(chosen_notes) if note_words else None
    return "<br><br>".join(rendered), len(chosen_main), notes_result
