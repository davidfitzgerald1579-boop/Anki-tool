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
    assert len(kept) == 4  # 3 rotating seed examples + 1 live
    assert all(k["front"].startswith("S") for k in kept[:3])
    assert bad == []


def test_examples_flow_into_prompt():
    qgen_feedback.record({"front": "GoodQ", "back": "GoodA"}, qgen_feedback.KEPT)
    qgen_feedback.record({"front": "BadQ", "back": "BadA"}, qgen_feedback.BAD)
    prompt = qgen.build_prompt("slide", 4, feedback=qgen_feedback.examples({}))
    assert "GoodQ" in prompt and "BadQ" in prompt
    assert "FORM to copy" in prompt
    assert "failure modes to avoid" in prompt
    # softly steered, never hard-banned
    assert "NEVER" not in prompt


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
