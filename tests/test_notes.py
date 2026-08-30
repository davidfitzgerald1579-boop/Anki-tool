"""End-to-end note creation against a real (temporary) Anki collection."""

import json
import tempfile
from pathlib import Path

import pytest
from anki.collection import Collection

from snip_occlusion import notes as notes_mod
from snip_occlusion.consts import FIELDS, MODE_HIDE_ALL, MODE_HIDE_ONE, MODEL_NAME
from snip_occlusion.shapes import Shape


@pytest.fixture
def col():
    tmp = tempfile.mkdtemp()
    c = Collection(str(Path(tmp) / "collection.anki2"))
    yield c
    c.close()


def sample_shapes():
    return [
        Shape(kind="rect", x=100, y=100, w=200, h=40, group="g1"),
        Shape(kind="rect", x=100, y=160, w=200, h=40),
        Shape(kind="ellipse", x=100, y=220, w=200, h=40, group="g1"),
        Shape(kind="erase", x=0, y=0, w=50, h=20, color="#fbf3e4"),
    ]


def test_ensure_note_type_creates_and_reuses(col):
    nt = notes_mod.ensure_note_type(col, "#FFEBA2", "#FF7E7E")
    assert nt["name"] == MODEL_NAME
    assert [f["name"] for f in nt["flds"]] == FIELDS
    assert len(nt["tmpls"]) == 1
    nt2 = notes_mod.ensure_note_type(col, "#FFEBA2", "#FF7E7E")
    assert nt2["id"] == nt["id"]
    assert len(col.models.all()) == len(col.models.all())


def test_add_notes_one_card_per_group(col):
    deck_id = col.decks.id("SQE::Public Law")
    n = notes_mod.add_occlusion_notes(
        col,
        deck_id,
        "snip-test.png",
        sample_shapes(),
        800,
        500,
        MODE_HIDE_ALL,
        "Administrative Court",
        "Senior Courts Act 1981",
        "SQE public-law",
        "#FFEBA2",
        "#FF7E7E",
    )
    # g1 (rect+ellipse) is one card, the ungrouped rect is another
    assert n == 2
    assert col.card_count() == 2
    nids = col.find_notes("")
    assert len(nids) == 2
    targets = set()
    for nid in nids:
        note = col.get_note(nid)
        assert note["Mode"] == MODE_HIDE_ALL
        assert note["Header"] == "Administrative Court"
        assert note["Footer"] == "Senior Courts Act 1981"
        assert '<img src="snip-test.png">' in note["Image"]
        assert set(note.tags) == {"SQE", "public-law"}  # Anki sorts tags
        payload = json.loads(note["Masks"])
        assert len(payload["shapes"]) == 3  # erase shape excluded
        targets.add(note["Target"])
        # cards land in the chosen deck
        for card in note.cards():
            assert card.did == deck_id
    assert "g1" in targets and len(targets) == 2


def test_rendered_card_contains_masks_and_scripts(col):
    deck_id = col.decks.id("Default")
    notes_mod.add_occlusion_notes(
        col, deck_id, "x.png", sample_shapes(), 800, 500,
        MODE_HIDE_ONE, "", "", "", "#FFEBA2", "#FF7E7E",
    )
    nid = col.find_notes("")[0]
    card = col.get_note(nid).cards()[0]
    q = card.question()
    a = card.answer()
    assert "io-wrap" in q and "io-payload" in q
    assert '"shapes"' in q  # JSON survived template rendering
    assert 'IO_SIDE = "q"' in q
    assert 'IO_SIDE = "a"' in a


def test_search_text_field_saved_and_searchable(col):
    deck_id = col.decks.id("Default")
    notes_mod.add_occlusion_notes(
        col, deck_id, "x.png", sample_shapes(), 800, 500,
        MODE_HIDE_ALL, "", "", "", "#FFEBA2", "#FF7E7E",
        search_text="The Administrative Court reviews lawfulness",
    )
    nids = col.find_notes("")
    for nid in nids:
        assert "Administrative" in col.get_note(nid)["Search Text"]
    # Anki search finds the image-only cards via the hidden field
    assert set(col.find_notes("lawfulness")) == set(nids)


def test_old_note_type_upgraded_in_place_with_new_field(col):
    # simulate a note type created by v0.3 (no "Search Text" field)
    mm = col.models
    old = mm.new(MODEL_NAME)
    for fname in FIELDS:
        if fname == "Search Text":
            continue
        mm.add_field(old, mm.new_field(fname))
    t = mm.new_template("Occlusion Card")
    t["qfmt"] = "{{Image}}"
    t["afmt"] = "{{Image}}"
    mm.add_template(old, t)
    mm.add(old)
    old = mm.by_name(MODEL_NAME)
    note = col.new_note(old)
    note["Occlusion ID"] = "legacy-1"
    col.add_note(note, col.decks.id("Default"))

    nt = notes_mod.ensure_note_type(col, "#FFEBA2", "#FF7E7E")
    # upgraded in place: same id, no "Snip Occlusion 2", field added
    assert nt["id"] == old["id"]
    assert mm.by_name(MODEL_NAME + " 2") is None
    assert "Search Text" in {f["name"] for f in nt["flds"]}
    legacy = col.get_note(col.find_notes("legacy-1")[0])
    assert legacy["Search Text"] == ""


def test_shapes_roundtrip_through_note(col):
    deck_id = col.decks.id("Default")
    src = sample_shapes()
    notes_mod.add_occlusion_notes(
        col, deck_id, "img.png", src, 800, 500,
        MODE_HIDE_ALL, "", "", "", "#FFEBA2", "#FF7E7E",
    )
    note = col.get_note(col.find_notes("")[0])
    assert notes_mod.is_occlusion_note(note)
    assert notes_mod.parse_image_fname(note) == "img.png"
    loaded = notes_mod.shapes_from_note(note, 800, 500)
    masks = [s for s in src if s.kind in ("rect", "ellipse")]
    assert len(loaded) == len(masks)
    by_id = {s.id: s for s in loaded}
    for orig in masks:
        got = by_id[orig.id]  # ids survive, so targets keep matching
        assert got.kind == orig.kind
        assert abs(got.x - orig.x) < 0.05 and abs(got.w - orig.w) < 0.05
        assert got.group == orig.group  # explicit group kept, singleton None
        assert got.effective_group() == orig.effective_group()


def test_update_occlusion_notes_edits_siblings(col):
    deck_id = col.decks.id("Default")
    src = sample_shapes()
    notes_mod.add_occlusion_notes(
        col, deck_id, "img.png", src, 800, 500,
        MODE_HIDE_ALL, "Old header", "", "", "#FFEBA2", "#FF7E7E",
    )
    base = col.get_note(col.find_notes("Target:g1")[0])

    # edit: move the singleton box, delete the g1 pair, add a new box
    shapes = notes_mod.shapes_from_note(base, 800, 500)
    keep = [s for s in shapes if s.group is None]
    keep[0].x += 40
    new = Shape(kind="rect", x=500, y=300, w=100, h=30)
    edited = keep + [new]

    assert notes_mod.count_missing_targets(col, base, edited) == 1
    other_deck = col.decks.id("Edited::New")
    updated, added, removed = notes_mod.update_occlusion_notes(
        col, base, other_deck, edited, 800, 500,
        MODE_HIDE_ONE, "New header", "New footer", "extra-tag",
        "#FFEBA2", "#FF7E7E", "found text", delete_missing=True,
    )
    assert (updated, added, removed) == (1, 1, 1)

    nids = col.find_notes("")
    assert len(nids) == 2  # g1's note gone, singleton kept, one new
    prefix = notes_mod.session_prefix(base)
    targets = {}
    for nid in nids:
        n = col.get_note(nid)
        assert notes_mod.session_prefix(n) == prefix
        assert n["Mode"] == MODE_HIDE_ONE
        assert n["Header"] == "New header"
        assert n["Search Text"] == "found text"
        payload = json.loads(n["Masks"])
        assert len(payload["shapes"]) == 2
        targets[n["Target"]] = n
    # the untouched singleton kept its identity; the new box got a card
    assert keep[0].effective_group() in targets
    assert new.effective_group() in targets
    new_note = targets[new.effective_group()]
    assert new_note.cards()[0].did == other_deck
    assert "extra-tag" in new_note.tags
    # the surviving old note kept its original deck and tags
    old_note = targets[keep[0].effective_group()]
    assert old_note.cards()[0].did == deck_id
    assert "extra-tag" not in old_note.tags


def test_incompatible_existing_model_gets_suffixed_name(col):
    mm = col.models
    bogus = mm.new(MODEL_NAME)
    mm.add_field(bogus, mm.new_field("Front"))
    mm.add_field(bogus, mm.new_field("Back"))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Front}}"
    t["afmt"] = "{{Back}}"
    mm.add_template(bogus, t)
    mm.add(bogus)

    nt = notes_mod.ensure_note_type(col, "#FFEBA2", "#FF7E7E")
    assert nt["name"] == MODEL_NAME + " 2"
    assert {f["name"] for f in nt["flds"]} == set(FIELDS)
