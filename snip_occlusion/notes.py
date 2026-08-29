"""Note type management and note creation.

This module only needs a `Collection` (no aqt), so it is fully testable
against a temporary collection outside of Anki's GUI.
"""

from __future__ import annotations

import json
import uuid

from . import template
from .consts import CARD_NAME, FIELDS, MODEL_NAME
from .shapes import normalized_payload, target_groups


def _by_name(models, name: str):
    getter = getattr(models, "by_name", None) or getattr(models, "byName")
    return getter(name)


def ensure_note_type(col, mask_fill: str, target_fill: str):
    """Find or create the Snip Occlusion note type.

    If a note type with our name exists and has all required fields it is
    reused untouched (so user customizations survive). If the name is taken
    by something incompatible, a suffixed variant is created instead.
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
        if tag_list:
            note.tags = list(tag_list)
        col.add_note(note, deck_id)
    return len(targets)
