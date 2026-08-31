"""Note type management and note creation.

This module only needs a `Collection` (no aqt), so it is fully testable
against a temporary collection outside of Anki's GUI.
"""

from __future__ import annotations

import json
import re
import uuid

from . import template
from .consts import (
    BASIC_FIELDS,
    BASIC_MODEL_NAME,
    CARD_NAME,
    FIELDS,
    MARKER_FIELDS,
    MODEL_NAME,
)
from .shapes import normalized_payload, shapes_from_payload, target_groups


def _by_name(models, name: str):
    getter = getattr(models, "by_name", None) or getattr(models, "byName")
    return getter(name)


def _save(models, nt) -> None:
    saver = getattr(models, "update_dict", None) or getattr(models, "save")
    saver(nt)


def ensure_note_type(col, mask_fill: str, target_fill: str):
    """Find or create the Snip Occlusion note type.

    An existing note type of ours that merely lacks newer fields (e.g.
    "Search Text" added in v0.4) is upgraded in place - existing notes keep
    working and simply gain the empty field. Only a name collision with an
    unrelated note type falls back to a suffixed variant.
    """
    mm = col.models
    name = MODEL_NAME
    for attempt in range(10):
        nt = _by_name(mm, name)
        if nt is None:
            break
        existing = {f["name"] for f in nt["flds"]}
        if all(f in existing for f in FIELDS):
            return nt
        if MARKER_FIELDS <= existing:
            for fname in FIELDS:
                if fname not in existing:
                    mm.add_field(nt, mm.new_field(fname))
            _save(mm, nt)
            return _by_name(mm, name)
        name = "%s %d" % (MODEL_NAME, attempt + 2)

    nt = mm.new(name)
    for fname in FIELDS:
        mm.add_field(nt, mm.new_field(fname))
    tmpl = mm.new_template(CARD_NAME)
    tmpl["qfmt"] = template.FRONT
    tmpl["afmt"] = template.BACK
    mm.add_template(nt, tmpl)
    nt["css"] = template.build_css(mask_fill, target_fill)
    mm.add(nt)
    return _by_name(mm, name)


def add_occlusion_notes(
    col,
    deck_id: int,
    image_fname: str,
    shapes: list,
    img_w: int,
    img_h: int,
    mode: str,
    header: str,
    footer: str,
    tags: str,
    mask_fill: str,
    target_fill: str,
    search_text: str = "",
) -> int:
    """Create one note (= one card) per target group. Returns notes added."""
    targets = target_groups(shapes)
    if not targets:
        return 0

    nt = ensure_note_type(col, mask_fill, target_fill)
    payload = json.dumps(
        normalized_payload(shapes, img_w, img_h), separators=(",", ":")
    )
    session_id = uuid.uuid4().hex[:8]
    tag_list = tags.split()

    for i, group in enumerate(targets, 1):
        note = col.new_note(nt)
        note["Occlusion ID"] = "%s-%d" % (session_id, i)
        note["Image"] = '<img src="%s">' % image_fname
        note["Header"] = header
        note["Footer"] = footer
        note["Masks"] = payload
        note["Target"] = group
        note["Mode"] = mode
        note["Search Text"] = search_text
        if tag_list:
            note.tags = list(tag_list)
        col.add_note(note, deck_id)
    return len(targets)


# ------------------------------------------------------ simple text cards


def ensure_basic_note_type(col):
    """Find or create the simple Front/Back/Notes note type."""
    mm = col.models
    name = BASIC_MODEL_NAME
    for attempt in range(10):
        nt = _by_name(mm, name)
        if nt is None:
            break
        existing = {f["name"] for f in nt["flds"]}
        if all(f in existing for f in BASIC_FIELDS):
            return nt
        if {"Front", "Back"} <= existing:
            for fname in BASIC_FIELDS:
                if fname not in existing:
                    mm.add_field(nt, mm.new_field(fname))
            _save(mm, nt)
            return _by_name(mm, name)
        name = "%s %d" % (BASIC_MODEL_NAME, attempt + 2)

    nt = mm.new(name)
    for fname in BASIC_FIELDS:
        mm.add_field(nt, mm.new_field(fname))
    tmpl = mm.new_template("Card 1")
    tmpl["qfmt"] = template.BASIC_FRONT
    tmpl["afmt"] = template.BASIC_BACK
    mm.add_template(nt, tmpl)
    nt["css"] = template.BASIC_CSS
    mm.add(nt)
    return _by_name(mm, name)


def add_text_note(col, deck_id: int, front: str, back: str, notes: str):
    nt = ensure_basic_note_type(col)
    note = col.new_note(nt)
    note["Front"] = front
    note["Back"] = back
    note["Notes"] = notes
    col.add_note(note, deck_id)
    return note


def remove_note(col, note_id: int) -> None:
    """Delete one note (and its cards) by id."""
    try:
        col.remove_notes([note_id])
    except AttributeError:  # pre-2.1.28 API
        col.remNotes([note_id])


# ------------------------------------------------- bulk delete by image


def image_filenames(note) -> list:
    """Every media filename referenced by any field of the note (works for
    Snip Occlusion notes and other image tools, e.g. IOE)."""
    out = []
    seen = set()
    for text in note.fields:
        for m in re.findall(r"src=[\"']([^\"']+)[\"']", text):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


def find_notes_sharing_image(col, note):
    """(filename, note_ids) for the image this note shares with the most
    other notes.

    A card generated from a slide references the slide image (shared by
    every sibling) and possibly per-card files like IOE's mask SVGs
    (unique to one note) - so the filename matching the most notes is the
    shared slide, and its matches are the whole family.
    """
    best_fname = None
    best_nids: list = []
    for fname in image_filenames(note):
        escaped = fname.replace("\\", "\\\\").replace('"', '\\"')
        nids = list(col.find_notes('"%s"' % escaped))
        if len(nids) > len(best_nids):
            best_fname, best_nids = fname, nids
    return best_fname, best_nids


# --------------------------------------------------- editing existing cards


def is_occlusion_note(note) -> bool:
    return MARKER_FIELDS <= set(note.keys())


def parse_image_fname(note) -> str | None:
    m = re.search(r'src="([^"]+)"', note["Image"])
    return m.group(1) if m else None


def shapes_from_note(note, img_w: int, img_h: int) -> list:
    try:
        payload = json.loads(note["Masks"])
    except ValueError:
        return []
    return shapes_from_payload(payload, img_w, img_h)


def session_prefix(note) -> str:
    return note["Occlusion ID"].rsplit("-", 1)[0]


def _sibling_notes(col, note):
    """All notes generated from the same editing session (same image)."""
    prefix = session_prefix(note)
    nids = col.find_notes('"Occlusion ID:%s-*"' % prefix)
    return [col.get_note(nid) for nid in nids]


def count_missing_targets(col, base_note, shapes: list) -> int:
    """Sibling cards whose target group no longer exists in `shapes`."""
    targets = set(target_groups(shapes))
    return sum(
        1 for n in _sibling_notes(col, base_note) if n["Target"] not in targets
    )


def update_occlusion_notes(
    col,
    base_note,
    deck_id: int,
    shapes: list,
    img_w: int,
    img_h: int,
    mode: str,
    header: str,
    footer: str,
    tags: str,
    mask_fill: str,
    target_fill: str,
    search_text: str = "",
    delete_missing: bool = False,
):
    """Save an edited layout back onto every sibling card of `base_note`.

    Existing cards keep their identity (and review history): their shared
    Masks/Mode/Header/Footer/Search Text fields are updated in place. New
    groups become new notes (in `deck_id`); cards whose target group was
    deleted are removed only when delete_missing is True.
    Returns (updated, added, removed).
    """
    payload = json.dumps(
        normalized_payload(shapes, img_w, img_h), separators=(",", ":")
    )
    targets_now = target_groups(shapes)
    siblings = _sibling_notes(col, base_note)
    prefix = session_prefix(base_note)
    fname = parse_image_fname(base_note)

    existing_targets = set()
    max_index = 0
    to_remove = []
    updated = 0
    for note in siblings:
        try:
            max_index = max(
                max_index, int(note["Occlusion ID"].rsplit("-", 1)[1])
            )
        except ValueError:
            pass
        if note["Target"] not in targets_now and delete_missing:
            to_remove.append(note.id)
            continue
        existing_targets.add(note["Target"])
        note["Masks"] = payload
        note["Mode"] = mode
        note["Header"] = header
        note["Footer"] = footer
        note["Search Text"] = search_text
        col.update_note(note)
        updated += 1
    if to_remove:
        col.remove_notes(to_remove)

    nt = ensure_note_type(col, mask_fill, target_fill)
    tag_list = tags.split()
    added = 0
    for group in targets_now:
        if group in existing_targets:
            continue
        max_index += 1
        note = col.new_note(nt)
        note["Occlusion ID"] = "%s-%d" % (prefix, max_index)
        note["Image"] = '<img src="%s">' % fname
        note["Header"] = header
        note["Footer"] = footer
        note["Masks"] = payload
        note["Target"] = group
        note["Mode"] = mode
        note["Search Text"] = search_text
        if tag_list:
            note.tags = list(tag_list)
        col.add_note(note, deck_id)
        added += 1
    return updated, added, len(to_remove)
