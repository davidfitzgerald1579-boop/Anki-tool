"""Session registry of text cards added through the add-on.

A slip is often noticed right after clicking Add - the AI confused two
concepts, or a typo crept in. Every text card added in this Anki
session is remembered here so the sidebar can list it; clicking an
entry reopens the card to delete it, or to fix it and redeploy (the
old note is removed and a corrected one takes its place).

In-memory only: the list resets when Anki restarts, which is the
point - it is a "what I just made" tray, not a browser.
"""

from __future__ import annotations

_entries: list = []
_listeners: list = []


def add_listener(fn) -> None:
    """fn() is called after every change. A listener that raises is
    dropped (e.g. it belonged to a closed window)."""
    if fn not in _listeners:
        _listeners.append(fn)


def _fire() -> None:
    for fn in list(_listeners):
        try:
            fn()
        except Exception:
            try:
                _listeners.remove(fn)
            except ValueError:
                pass


def record(
    note_id: int, deck_id, front: str, back: str, notes: str, label: str
) -> None:
    """Remember a just-added note. Fields are HTML; label is plain."""
    _entries.append(
        {
            "note_id": int(note_id),
            "deck_id": deck_id,
            "front": front,
            "back": back,
            "notes": notes,
            "label": " ".join((label or "").split()) or "(untitled card)",
        }
    )
    _fire()


def get(note_id: int):
    for entry in _entries:
        if entry["note_id"] == int(note_id):
            return dict(entry)
    return None


def forget(note_id: int) -> None:
    global _entries
    before = len(_entries)
    _entries = [e for e in _entries if e["note_id"] != int(note_id)]
    if len(_entries) != before:
        _fire()


def replace(
    note_id: int,
    new_note_id: int,
    deck_id,
    front: str,
    back: str,
    notes: str,
    label: str,
) -> None:
    """A redeploy: the entry now tracks the replacement note."""
    for entry in _entries:
        if entry["note_id"] == int(note_id):
            entry.update(
                note_id=int(new_note_id),
                deck_id=deck_id,
                front=front,
                back=back,
                notes=notes,
                label=" ".join((label or "").split()) or "(untitled card)",
            )
            _fire()
            return
    # unknown original (e.g. registry cleared) - track the new note
    record(new_note_id, deck_id, front, back, notes, label)


def entries() -> list:
    return [dict(e) for e in _entries]


def clear() -> None:
    _entries.clear()
    _fire()
