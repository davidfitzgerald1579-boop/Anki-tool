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


def _make_ioe_style_notes(col, image, count):
    """Mimic Image Occlusion Enhanced: each note references the shared
    slide image plus its own unique mask files."""
    mm = col.models
    nt = mm.new("Fake IOE %s" % image)
    for fname in ("ID", "Image", "QMask", "AMask"):
        mm.add_field(nt, mm.new_field(fname))
    t = mm.new_template("IO")
    t["qfmt"] = "{{Image}}{{QMask}}"
    t["afmt"] = "{{Image}}{{AMask}}"
    mm.add_template(nt, t)
    mm.add(nt)
    nt = mm.by_name("Fake IOE %s" % image)
    nids = []
    deck = col.decks.id("Default")
    for i in range(count):
        note = col.new_note(nt)
        note["ID"] = "%s-%d" % (image, i)
        note["Image"] = '<img src="%s">' % image
        note["QMask"] = '<img src="%s-Q_%d.svg">' % (image, i)
        note["AMask"] = '<img src="%s-A_%d.svg">' % (image, i)
        col.add_note(note, deck)
        nids.append(note.id)
    return nids


def test_find_notes_sharing_image_across_tools(col):
    ioe_a = _make_ioe_style_notes(col, "old-slide-a.jpg", 10)
    ioe_b = _make_ioe_style_notes(col, "old-slide-b.jpg", 4)
    # plus some of our own notes on a different image
    notes_mod.add_occlusion_notes(
        col, col.decks.id("Default"), "snip-xyz.png", sample_shapes(),
        800, 500, MODE_HIDE_ALL, "", "", "", "#FFEBA2", "#FF7E7E",
    )

    base = col.get_note(ioe_a[3])
    fnames = notes_mod.image_filenames(base)
    assert "old-slide-a.jpg" in fnames  # shared image found among masks
    fname, nids = notes_mod.find_notes_sharing_image(col, base)
    # the SHARED slide wins over the per-card mask files
    assert fname == "old-slide-a.jpg"
    assert set(nids) == set(ioe_a)  # all 10, and nothing from b or ours

    # and for our own notes the whole session is found
    ours = col.find_notes("snip-xyz")
    fname2, nids2 = notes_mod.find_notes_sharing_image(
        col, col.get_note(ours[0])
    )
    assert fname2 == "snip-xyz.png"
    assert set(nids2) == set(ours)

    # deleting the found set removes exactly that family
    col.remove_notes(nids)
    assert col.find_notes("old-slide-a") == []
    assert len(col.find_notes("old-slide-b")) == 4
    assert len(col.find_notes("snip-xyz")) == len(ours)


def test_basic_text_note_type_and_card(col):
    deck_id = col.decks.id("Own Words")
    note = notes_mod.add_text_note(
        col,
        deck_id,
        "<b>What</b> is <i>legislation</i>?",
        "Law made with the approval of Parliament.",
        "See the What is legislation slide.",
    )
    assert note.cards()[0].did == deck_id
    q = note.cards()[0].question()
    a = note.cards()[0].answer()
    assert "legislation" in q and "<b>What</b>" in q
    assert "approval of Parliament" in a
    assert 'class="sn-notes"' in a  # notes rendered on the back

    # reused, not duplicated, on the next card
    nt = notes_mod.ensure_basic_note_type(col)
    note2 = notes_mod.add_text_note(col, deck_id, "Front only", "", "")
    assert note2.note_type()["id"] == nt["id"]
    a2 = note2.cards()[0].answer()
    assert 'class="sn-notes"' not in a2  # empty notes stay hidden


def test_text_note_with_source_gets_reveal_button(col):
    deck_id = col.decks.id("Default")
    note = notes_mod.add_text_note(
        col,
        deck_id,
        "What is judicial review?",
        "A challenge to the lawfulness of a public body's decision.",
        "",
        source='<img src="snip-occlusion-src-ab12cd34ef.png">',
    )
    assert note["Source"] == '<img src="snip-occlusion-src-ab12cd34ef.png">'
    q = note.cards()[0].question()
    a = note.cards()[0].answer()
    # the snip is behind a click on the BACK only, never on the front
    assert "<details" not in q
    assert "snip-occlusion-src" not in q
    assert '<details class="sn-source">' in a
    assert "Reveal source" in a
    assert 'src="snip-occlusion-src-ab12cd34ef.png"' in a
    # and the styling for it is in the note type's CSS
    assert ".sn-source" in note.note_type()["css"]

    # a card without a source shows no reveal button at all
    note2 = notes_mod.add_text_note(col, deck_id, "F", "B", "")
    assert note2["Source"] == ""
    assert "<details" not in note2.cards()[0].answer()


def test_old_basic_note_type_upgraded_with_source(col):
    # simulate the note type as created before v0.26: no Source field,
    # back template without the reveal block, user-customised CSS
    from snip_occlusion import template

    mm = col.models
    old = mm.new("Snip Occlusion Basic")
    for fname in ("Front", "Back", "Notes"):
        mm.add_field(old, mm.new_field(fname))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Front}}"
    t["afmt"] = (
        "{{FrontSide}}\n<hr id=answer>\n{{Back}}\n"
        '{{#Notes}}<div class="sn-notes">{{Notes}}</div>{{/Notes}}\n'
        "<!-- my custom footer -->"
    )
    mm.add_template(old, t)
    old["css"] = ".card { color: purple; }"
    mm.add(old)
    old = mm.by_name("Snip Occlusion Basic")
    note = col.new_note(old)
    note["Front"] = "legacy front"
    col.add_note(note, col.decks.id("Default"))

    nt = notes_mod.ensure_basic_note_type(col)
    # upgraded in place: same id, no "Snip Occlusion Basic 2"
    assert nt["id"] == old["id"]
    assert mm.by_name("Snip Occlusion Basic 2") is None
    assert "Source" in {f["name"] for f in nt["flds"]}
    # the reveal block was appended; the customisation survived
    afmt = nt["tmpls"][0]["afmt"]
    assert "<!-- my custom footer -->" in afmt
    assert "{{Source}}" in afmt and "Reveal source" in afmt
    assert ".card { color: purple; }" in nt["css"]
    assert template.BASIC_SOURCE_CSS.strip() in nt["css"]
    # legacy note keeps working, with an empty Source
    legacy = col.get_note(col.find_notes("legacy front")[0])
    assert legacy["Source"] == ""
    assert "<details" not in legacy.cards()[0].answer()

    # a second ensure() must not append the block again
    again = notes_mod.ensure_basic_note_type(col)
    assert again["tmpls"][0]["afmt"].count("{{Source}}") == 1
    assert again["css"].count(template.BASIC_SOURCE_CSS.strip()) == 1


def _make_pre_v026_basic_model(col):
    """The 'Snip Occlusion Basic' note type as older versions made it."""
    mm = col.models
    old = mm.new("Snip Occlusion Basic")
    for fname in ("Front", "Back", "Notes"):
        mm.add_field(old, mm.new_field(fname))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Front}}"
    t["afmt"] = "{{FrontSide}}\n<hr id=answer>\n{{Back}}"
    mm.add_template(old, t)
    mm.add(old)
    return mm.by_name("Snip Occlusion Basic")


def test_declined_schema_change_still_adds_the_card(col, monkeypatch):
    old = _make_pre_v026_basic_model(col)

    def refuse(check):
        raise Exception("user declined the full sync")

    monkeypatch.setattr(col, "mod_schema", refuse)
    note = notes_mod.add_text_note(
        col, col.decks.id("Default"), "F", "B", "N",
        source='<img src="x.png">',
    )
    # the card went in; the note type was left completely alone
    assert note.id
    nt = col.models.by_name("Snip Occlusion Basic")
    assert nt["id"] == old["id"]
    assert "Source" not in {f["name"] for f in nt["flds"]}
    assert "{{Source}}" not in nt["tmpls"][0]["afmt"]
    # once consent is possible again, the upgrade happens after all
    monkeypatch.undo()
    note2 = notes_mod.add_text_note(
        col, col.decks.id("Default"), "F2", "B2", "",
        source='<img src="y.png">',
    )
    assert note2["Source"] == '<img src="y.png">'


def test_attach_source_off_leaves_note_type_untouched(col):
    old = _make_pre_v026_basic_model(col)
    note = notes_mod.add_text_note(
        col, col.decks.id("Default"), "F", "B", "N", attach_source=False
    )
    assert note.id and note["Notes"] == "N"
    nt = col.models.by_name("Snip Occlusion Basic")
    assert nt["id"] == old["id"]
    assert "Source" not in {f["name"] for f in nt["flds"]}
    assert "{{Source}}" not in nt["tmpls"][0]["afmt"]
    assert ".sn-source" not in nt["css"]


def test_user_removed_reveal_block_stays_removed(col):
    # the user upgraded, then deliberately deleted the block from the
    # back template: it must not come back on the next card add
    nt = notes_mod.ensure_basic_note_type(col)
    mm = col.models
    nt["tmpls"][0]["afmt"] = "{{FrontSide}}\n<hr id=answer>\n{{Back}}"
    mm.update_dict(nt)
    notes_mod.add_text_note(
        col, col.decks.id("Default"), "F", "B", "",
        source='<img src="x.png">',
    )
    nt = mm.by_name(nt["name"])
    assert "{{Source}}" not in nt["tmpls"][0]["afmt"]


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
