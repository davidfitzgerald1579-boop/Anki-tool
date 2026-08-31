"""Background pre-generation of AI card suggestions.

Local models are slow, so waiting until the user clicks "Suggest cards"
wastes the minutes they spend drawing boxes. Instead, the moment a snip
lands in the editor we OCR it and start the LLM in a background thread;
by the time the user opens the text card dialog and clicks the button,
the cards usually already exist and appear instantly.

One slot only: a new snip replaces the previous prefetch (its thread is
left to finish and be ignored - threads can't be safely killed, and the
LLM server processes one request at a time anyway).

Note the prefetch works from the snip as it was when loaded; cover-ups
and patches drawn afterwards don't re-run generation. That's the point -
the suggestions are drafts to pick from, and unwanted ones can be
deleted from the list.
"""

from __future__ import annotations

import threading

from . import ocr, qgen, qgen_bakeoff


class _Prefetch:
    def __init__(self):
        self.done = threading.Event()
        self.text = ""
        self.cards: list | None = None
        self.error: Exception | None = None


_lock = threading.Lock()
_latest: _Prefetch | None = None


def start_for_image(img, config: dict, on_text=None) -> None:
    """OCR `img` and generate card suggestions, in a background thread.

    Never raises and never blocks; failures are stored and surfaced when
    (if) the user asks for the suggestions.

    `on_text(state)` is called from the worker thread the moment OCR
    finishes - minutes before the LLM is done - so the UI can show the
    source text straight away. It must hop to the main thread itself
    before touching widgets.
    """
    if not config.get("qgen_prefetch", True):
        return
    state = _Prefetch()
    global _latest
    with _lock:
        _latest = state

    def work() -> None:
        try:
            state.text = ocr.extract_text(img, config)
            if not state.text.strip():
                raise qgen.QGenError(
                    "No text could be read from the snip."
                )
            if on_text is not None:
                try:
                    on_text(state)
                except Exception:
                    pass  # display is a bonus; generation must go on
            state.cards = qgen_bakeoff.generate(state.text, config)
        except Exception as exc:
            state.error = exc
        finally:
            state.done.set()

    threading.Thread(target=work, daemon=True, name="qgen-prefetch").start()


def current() -> _Prefetch | None:
    """The prefetch for the most recent snip, or None."""
    with _lock:
        return _latest


def wait_for_cards(state: _Prefetch, timeout: float | None = None) -> list:
    """Block until `state` finishes; return its cards or raise its error.

    Call from a background thread, never the UI thread.
    """
    if not state.done.wait(timeout):
        raise qgen.QGenError(
            "The AI is still generating suggestions for this snip - "
            "try again in a moment."
        )
    if state.error is not None:
        raise state.error
    return state.cards or []
