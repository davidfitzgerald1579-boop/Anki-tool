"""Tests for the suggestion-feedback memory (three-verdict model)."""

import json

import pytest

from snip_occlusion import qgen, qgen_feedback


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        qgen_feedback, "_path", lambda: str(tmp_path / "feedback.json")
    )
    monkeypatch.setattr(
        qgen_feedback, "_seed_path", lambda: str(tmp_path / "seed.json")
    )
    yield tmp_path


def test_record_and_examples_roundtrip():
    qgen_feedback.record({"front": "Q1", "back": "A1"}, qgen_feedback.KEPT)
    qgen_feedback.record(
        {"front": "Q2", "back": "A2", "notes": "n"}, qgen_feedback.BAD
    )
    kept, bad = qgen_feedback.examples({})
    assert kept == [{"front": "Q1", "back": "A1"}]
    assert bad == [{"front": "Q2", "back": "A2", "notes": "n"}]


def test_latest_verdict_wins():
    card = {"front": "Q", "back": "A"}
    qgen_feedback.record(card, qgen_feedback.BAD)
    qgen_feedback.record(card, qgen_feedback.KEPT)
    kept, bad = qgen_feedback.examples({})
    assert kept == [card]
    assert bad == []


def test_invalid_verdict_and_empty_card_ignored():
    qgen_feedback.record({"front": "Q", "back": "A"}, "neutral")
    qgen_feedback.record({"front": "", "back": "A"}, qgen_feedback.KEPT)
    assert qgen_feedback.examples({}) == ([], [])


def test_disabled_or_zero_examples():
    qgen_feedback.record({"front": "Q", "back": "A"}, qgen_feedback.KEPT)
    assert qgen_feedback.examples({"qgen_feedback": False}) == ([], [])
    assert qgen_feedback.examples({"qgen_feedback_examples": 0}) == ([], [])


def test_stored_lists_are_capped():
    for i in range(qgen_feedback._MAX_STORED + 10):
        qgen_feedback.record(
            {"front": "Q%d" % i, "back": "A"}, qgen_feedback.KEPT
        )
    with open(qgen_feedback._path(), encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data[qgen_feedback.KEPT]) == qgen_feedback._MAX_STORED


def test_seed_mixed_into_positives(_isolated_store):
    seed = [{"front": "S%d" % i, "back": "A"} for i in range(10)]
    (_isolated_store / "seed.json").write_text(json.dumps(seed))
    qgen_feedback.record({"front": "live", "back": "A"}, qgen_feedback.KEPT)
    kept, bad = qgen_feedback.examples({"qgen_feedback_examples": 3})
    assert kept[-1] == {"front": "live", "back": "A"}
    # capped at 3 TOTAL: live takes priority, rotating seed fills the rest
    assert len(kept) == 3
    assert all(k["front"].startswith("S") for k in kept[:2])
    assert bad == []
    # enough live examples -> no seed padding at all
    for i in range(3):
        qgen_feedback.record(
            {"front": "live%d" % i, "back": "A"}, qgen_feedback.KEPT
        )
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 3})
    assert len(kept) == 3
    assert not any(k["front"].startswith("S") for k in kept)


def test_examples_flow_into_prompt():
    qgen_feedback.record({"front": "GoodQ", "back": "GoodA"}, qgen_feedback.KEPT)
    qgen_feedback.record({"front": "BadQ", "back": "BadA"}, qgen_feedback.BAD)
    prompt = qgen.build_prompt("slide", 4, feedback=qgen_feedback.examples({}))
    assert "GoodQ" in prompt and "BadQ" in prompt
    assert "Copy their form" in prompt
    assert "failure modes to avoid" in prompt
    # softly steered, never hard-banned
    assert "NEVER" not in prompt


def test_own_cards_take_priority_over_kept_and_seed(_isolated_store):
    seed = [{"front": "S%d" % i, "back": "A"} for i in range(10)]
    (_isolated_store / "seed.json").write_text(json.dumps(seed))
    for i in range(3):
        qgen_feedback.record(
            {"front": "kept%d" % i, "back": "A"}, qgen_feedback.KEPT
        )
    qgen_feedback.record(
        {"front": "mine", "back": "A"},
        qgen_feedback.KEPT,
        own=qgen_feedback.OWN_FULL,
    )
    qgen_feedback.record(
        {"front": "myQ", "back": "AI answer", "notes": "n"},
        qgen_feedback.KEPT,
        own=qgen_feedback.OWN_FRONT,
    )
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 3})
    # 3 total: both own cards, most important LAST, then one kept card
    # fills the remaining room; no seed needed
    assert [c["front"] for c in kept] == ["kept2", "mine", "myQ"]
    assert kept[1]["own"] == "full" and kept[2]["own"] == "front"
    assert "own" not in kept[0]
    # plenty of own cards -> they take the larger share, but a kept
    # suggestion always keeps one slot so Use →/★ verdicts still count
    for i in range(3):
        qgen_feedback.record(
            {"front": "own%d" % i, "back": "A"},
            qgen_feedback.KEPT,
            own=qgen_feedback.OWN_FULL,
        )
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 3})
    assert [c["front"] for c in kept] == ["kept2", "own1", "own2"]
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 4})
    assert [c["front"] for c in kept] == ["kept2", "own0", "own1", "own2"]
    # a single slot goes to the student's own card
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 1})
    assert [c["front"] for c in kept] == ["own2"]


def test_own_and_kept_take_over_each_others_unused_room(_isolated_store):
    seed = [{"front": "S%d" % i, "back": "A"} for i in range(10)]
    (_isolated_store / "seed.json").write_text(json.dumps(seed))
    # no own cards at all: behaviour is exactly as before
    for i in range(6):
        qgen_feedback.record(
            {"front": "kept%d" % i, "back": "A"}, qgen_feedback.KEPT
        )
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 4})
    assert [c["front"] for c in kept] == ["kept2", "kept3", "kept4", "kept5"]
    # one own card: it takes one slot, kept fills the other three
    qgen_feedback.record(
        {"front": "mine", "back": "A"}, qgen_feedback.KEPT, own="full"
    )
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 4})
    assert [c["front"] for c in kept] == ["kept3", "kept4", "kept5", "mine"]
    # no kept cards: own cards use every slot, seed only pads a shortfall
    qgen_feedback.unrecord({"front": "mine", "back": "A"})
    for i in range(6):
        qgen_feedback.unrecord({"front": "kept%d" % i, "back": "A"})
    for i in range(2):
        qgen_feedback.record(
            {"front": "own%d" % i, "back": "A"}, qgen_feedback.KEPT, own="full"
        )
    kept, _ = qgen_feedback.examples({"qgen_feedback_examples": 4})
    assert [c["front"] for c in kept[2:]] == ["own0", "own1"]
    assert all(c["front"].startswith("S") for c in kept[:2])


def test_own_cards_have_their_own_list_and_cap():
    for i in range(qgen_feedback._MAX_STORED + 5):
        qgen_feedback.record(
            {"front": "K%d" % i, "back": "A"}, qgen_feedback.KEPT
        )
    qgen_feedback.record(
        {"front": "mine", "back": "A"}, qgen_feedback.KEPT, own="full"
    )
    with open(qgen_feedback._path(), encoding="utf-8") as fh:
        data = json.load(fh)
    # a flood of kept suggestions never evicts a hand-written card
    assert [c["front"] for c in data[qgen_feedback.OWN]] == ["mine"]
    assert len(data[qgen_feedback.KEPT]) == qgen_feedback._MAX_STORED
    assert not any(c.get("own") for c in data[qgen_feedback.KEPT])


def test_own_verdict_moves_between_lists_and_unrecords():
    card = {"front": "Q", "back": "A"}
    qgen_feedback.record(card, qgen_feedback.KEPT, own="front")
    # a later plain verdict on the same card replaces the own entry
    qgen_feedback.record(card, qgen_feedback.BAD)
    kept, bad = qgen_feedback.examples({})
    assert kept == [] and bad == [card]
    qgen_feedback.record(card, qgen_feedback.KEPT, own="full")
    kept, bad = qgen_feedback.examples({})
    assert kept == [dict(card, own="full")] and bad == []
    qgen_feedback.unrecord(card)
    assert qgen_feedback.examples({}) == ([], [])
    # own marker is ignored for a BAD verdict, unknown markers count
    # as hand-written, and any falsy one is a plain keep
    qgen_feedback.record(card, qgen_feedback.BAD, own="full")
    assert qgen_feedback.examples({})[1] == [card]
    qgen_feedback.record(card, qgen_feedback.KEPT, own=True)
    assert qgen_feedback.examples({})[0] == [dict(card, own="full")]
    for falsy in (None, "", False, 0):
        qgen_feedback.record(card, qgen_feedback.KEPT, own=falsy)
        assert qgen_feedback.examples({})[0] == [card], repr(falsy)


def test_own_examples_get_their_own_prompt_block():
    qgen_feedback.record({"front": "KeptQ", "back": "A"}, qgen_feedback.KEPT)
    qgen_feedback.record(
        {"front": "MyQ", "back": "MyA"}, qgen_feedback.KEPT, own="full"
    )
    qgen_feedback.record({"front": "BadQ", "back": "BadA"}, qgen_feedback.BAD)
    prompt = qgen.build_prompt("slide", 4, feedback=qgen_feedback.examples({}))
    assert "WROTE THEMSELVES" in prompt and "MyQ" in prompt
    # own block sits after the kept block and before the bad block,
    # and it is the own block that says it takes precedence
    assert prompt.index("KeptQ") < prompt.index("MyQ") < prompt.index("BadQ")
    # the precedence instruction heads the own block, after the kept
    # examples and before the own examples it refers to
    assert (
        prompt.index("KeptQ")
        < prompt.index("these take precedence")
        < prompt.index("MyQ")
    )
    assert "MyQ" not in prompt[: prompt.index("WROTE THEMSELVES")]
    # the same block feeds the answer prompt
    answer = qgen.build_answer_prompt(
        "Q?", "slide", feedback=qgen_feedback.examples({})
    )
    assert "WROTE THEMSELVES" in answer and "BadQ" in answer
    # no own cards -> no own block at all
    qgen_feedback.unrecord({"front": "MyQ", "back": "MyA"})
    assert "WROTE THEMSELVES" not in qgen.build_prompt(
        "slide", 4, feedback=qgen_feedback.examples({})
    )


def test_bundled_seed_file_is_valid():
    # the real seed shipped with the add-on (not the tmp one)
    import os

    real = os.path.join(
        os.path.dirname(qgen_feedback.__file__), "qgen_seed.json"
    )
    with open(real, encoding="utf-8") as fh:
        seed = json.load(fh)
    assert len(seed) >= 20
    assert all(c.get("front") and c.get("back") for c in seed)


def test_unrecord_forgets_verdict_then_new_verdict_wins():
    card = {"front": "Q", "back": "A"}
    qgen_feedback.record(card, qgen_feedback.KEPT)
    qgen_feedback.unrecord(card)
    assert qgen_feedback.examples({}) == ([], [])
    # Use -> undone -> Bad: only the Bad survives
    qgen_feedback.record(card, qgen_feedback.BAD)
    kept, bad = qgen_feedback.examples({})
    assert kept == [] and bad == [card]


def test_unrecord_unknown_card_is_noop():
    qgen_feedback.record({"front": "Q", "back": "A"}, qgen_feedback.KEPT)
    qgen_feedback.unrecord({"front": "other", "back": "card"})
    kept, _ = qgen_feedback.examples({})
    assert kept == [{"front": "Q", "back": "A"}]


def test_phantom_refs_roundtrip_dedupe_and_length():
    qgen_feedback.record_phantom("  Smith v  Jones [2001] ")
    qgen_feedback.record_phantom("smith v jones [2001]")  # dupe, case-insensitive
    qgen_feedback.record_phantom("ab")  # too short, ignored
    assert qgen_feedback.phantom_refs() == ["Smith v Jones [2001]"]
    # card verdicts still work alongside the phantom list
    qgen_feedback.record({"front": "Q", "back": "A"}, qgen_feedback.KEPT)
    qgen_feedback.unrecord({"front": "Q", "back": "A"})
    assert qgen_feedback.examples({}) == ([], [])
    assert qgen_feedback.phantom_refs() == ["Smith v Jones [2001]"]
