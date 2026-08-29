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
