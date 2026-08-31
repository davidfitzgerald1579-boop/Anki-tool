"""Preference memory for AI card suggestions.

Three verdicts exist on a suggestion, with different meanings:

  "Use →"  the card was kept        -> saved as a positive style example
  "✕"      neutral discard          -> records NOTHING (the slide may
                                       simply not be card-worthy; that
                                       says nothing about card style)
  "👎"     the card is badly written -> saved as a negative style example

Recent examples of both lists are folded into future generation prompts,
framed as form-to-copy / habits-to-avoid rather than hard bans. The
model's weights never change - this is prompt steering, the practical
way to personalise a local model - but the effect compounds with use.

The positive list is seeded from qgen_seed.json (bundled, drawn from the
user's real deck) so the very first generation already imitates their
style; live "Use →" clicks gradually take over from the seed. A rotating
random sample of the seed is used per prompt so generations see varied
exemplars.

Live feedback is stored in user_files/qgen_feedback.json, which Anki
preserves across add-on updates. Everything stays on the user's machine.
"""

from __future__ import annotations

import json
import os
import random
import threading

_lock = threading.Lock()
_MAX_STORED = 50  # per list; only the newest few are put in prompts
_MAX_FIELD_CHARS = 300

KEPT = "kept"
BAD = "bad"
PHANTOMS = "phantom_refs"  # references the model has invented before
_MAX_PHANTOMS = 200


def _path() -> str:
    return os.path.join(
        os.path.dirname(__file__), "user_files", "qgen_feedback.json"
    )


def _seed_path() -> str:
    return os.path.join(os.path.dirname(__file__), "qgen_seed.json")


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            KEPT: list(data.get(KEPT) or []),
            BAD: list(data.get(BAD) or []),
            PHANTOMS: list(data.get(PHANTOMS) or []),
        }
    except Exception:
        return {KEPT: [], BAD: [], PHANTOMS: []}


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass  # feedback is best-effort; never break the UI over it


def _load_seed() -> list:
    try:
        with open(_seed_path(), encoding="utf-8") as fh:
            seed = json.load(fh)
        return seed if isinstance(seed, list) else []
    except Exception:
        return []


def record(card: dict, verdict: str) -> None:
    """Remember a kept ("Use →") or bad ("👎") suggestion.

    Neutral discards must simply not call this.
    """
    if verdict not in (KEPT, BAD):
        return
    entry = {
        "front": str(card.get("front") or "").strip()[:_MAX_FIELD_CHARS],
        "back": str(card.get("back") or "").strip()[:_MAX_FIELD_CHARS],
    }
    if card.get("notes"):
        entry["notes"] = str(card["notes"]).strip()[:_MAX_FIELD_CHARS]
    if not entry["front"] or not entry["back"]:
        return
    with _lock:
        data = _load()
        # a card lives in at most one list, once (latest verdict wins)
        for lst in (data[KEPT], data[BAD]):
            lst[:] = [
                c
                for c in lst
                if (c.get("front"), c.get("back"))
                != (entry["front"], entry["back"])
            ]
        data[verdict].append(entry)
        data[verdict] = data[verdict][-_MAX_STORED:]
        _save(data)


def unrecord(card: dict) -> None:
    """Forget any verdict on this card (the user undid their decision).

    Removes it from both lists; recording a new verdict afterwards
    starts fresh - so Use -> undone -> "Bad" remembers only the Bad.
    """
    front = str(card.get("front") or "").strip()[:_MAX_FIELD_CHARS]
    back = str(card.get("back") or "").strip()[:_MAX_FIELD_CHARS]
    if not front or not back:
        return
    with _lock:
        data = _load()
        changed = False
        for lst in (data[KEPT], data[BAD]):
            before = len(lst)
            lst[:] = [
                c
                for c in lst
                if (c.get("front"), c.get("back")) != (front, back)
            ]
            changed = changed or len(lst) != before
        if changed:
            _save(data)


def record_phantom(reference: str) -> None:
    """Remember a reference the model invented (user-flagged).

    Not shown to the model - repeating a fabricated citation in the
    prompt risks teaching a small model to produce it. Instead the
    generation pipeline strips or warns about any future card that
    cites a blocklisted reference.
    """
    reference = " ".join(str(reference or "").split())[:120]
    if len(reference) < 3:
        return
    with _lock:
        data = _load()
        lowered = reference.lower()
        if lowered not in (p.lower() for p in data[PHANTOMS]):
            data[PHANTOMS].append(reference)
            data[PHANTOMS] = data[PHANTOMS][-_MAX_PHANTOMS:]
            _save(data)


def phantom_refs() -> list:
    """All user-flagged invented references."""
    with _lock:
        return list(_load()[PHANTOMS])


def examples(config: dict) -> tuple[list, list]:
    """(positive style examples, negative style examples) for the prompt.

    Positives are a rotating random sample of the bundled seed plus the
    most recent live "Use →" cards; negatives are the most recent "👎"
    cards. Both empty when the feature is off.
    """
    if not config.get("qgen_feedback", True):
        return [], []
    try:
        n = int(config.get("qgen_feedback_examples", 4) or 0)
    except (TypeError, ValueError):
        n = 4
    if n <= 0:
        return [], []
    with _lock:
        data = _load()
    # cap positives at n TOTAL: small models start writing cards about
    # the example topics when shown too many, and every example costs
    # prompt-processing time. Live "Use →"/★ cards take priority; a
    # rotating seed sample fills whatever room is left.
    kept = data[KEPT][-n:]
    room = n - len(kept)
    if room > 0:
        seed = _load_seed()
        if seed:
            kept = random.sample(seed, min(room, len(seed))) + kept
    return kept, data[BAD][-n:]
