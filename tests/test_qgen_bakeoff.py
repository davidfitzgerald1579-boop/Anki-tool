"""Tests for the model bake-off (alternation, tallies, scoreboard)."""

import pytest

from snip_occlusion import qgen, qgen_bakeoff


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        qgen_bakeoff, "_path", lambda: str(tmp_path / "bakeoff.json")
    )
    yield tmp_path


@pytest.fixture
def fake_generate(monkeypatch):
    calls = []

    def fake(text, config, source="slide"):
        calls.append(config.get("qgen_model"))
        return [{"front": "Q", "back": "A"}]

    monkeypatch.setattr(qgen_bakeoff.qgen, "generate_cards", fake)
    return calls


CFG = {"qgen_bakeoff": True}


def test_disabled_passes_through_without_stamping(fake_generate):
    cards = qgen_bakeoff.generate("text", {"qgen_bakeoff": False})
    assert "_model" not in cards[0]
    assert fake_generate == [None]  # model untouched


def test_enabled_alternates_and_stamps(fake_generate):
    stamped = [qgen_bakeoff.generate("text", CFG)[0]["_model"] for _ in range(4)]
    assert stamped == [
        "llama3.1:8b",
        "llama3.2:3b",
        "llama3.1:8b",
        "llama3.2:3b",
    ]
    assert fake_generate == stamped  # config really carried the model


def test_custom_contenders_and_timing():
    cfg = dict(CFG, qgen_bakeoff_models=["a:1", "b:2", "c:3"])
    assert qgen_bakeoff.contenders(cfg) == ["a:1", "b:2", "c:3"]
    # a broken value falls back to the default pair
    assert len(qgen_bakeoff.contenders(dict(CFG, qgen_bakeoff_models="x"))) == 2


def test_tally_and_undo(fake_generate):
    card = qgen_bakeoff.generate("text", CFG)[0]
    qgen_bakeoff.tally(card, "great")
    qgen_bakeoff.tally(card, "bad")
    qgen_bakeoff.tally(card, "bad", undo=True)
    s = qgen_bakeoff._load()["models"][card["_model"]]
    assert s["great"] == 1 and s["bad"] == 0
    # unstamped cards and junk verdicts are ignored
    qgen_bakeoff.tally({"front": "Q", "back": "A"}, "great")
    qgen_bakeoff.tally(card, "meh")
    s = qgen_bakeoff._load()["models"][card["_model"]]
    assert s["great"] == 1
    # undo never goes below zero
    qgen_bakeoff.tally(card, "skip", undo=True)
    assert qgen_bakeoff._load()["models"][card["_model"]]["skip"] == 0


def test_summary_verdicts(fake_generate):
    assert "No bake-off data yet" in qgen_bakeoff.summary()
    # two models, few verdicts -> too early
    for _ in range(2):
        card = qgen_bakeoff.generate("text", CFG)[0]
        qgen_bakeoff.tally(card, "great")
    assert "too early" in qgen_bakeoff.summary()
    # equal kept-rates at volume -> "no meaningful difference"; verdicts
    # vary per PAIR of calls so both alternating models get the same mix
    for i in range(30):
        card = qgen_bakeoff.generate("text", CFG)[0]
        qgen_bakeoff.tally(card, "great" if (i // 2) % 2 else "bad")
    assert "no meaningful quality difference" in qgen_bakeoff.summary()


def test_summary_detects_real_difference(fake_generate):
    # model A keeps everything, model B loses everything
    for _ in range(30):
        card = qgen_bakeoff.generate("text", CFG)[0]
        good = card["_model"] == "llama3.1:8b"
        qgen_bakeoff.tally(card, "great" if good else "bad")
    text = qgen_bakeoff.summary()
    assert "REAL" in text
    assert "kept 100%" in text and "kept 0%" in text


def test_timings_recorded(fake_generate):
    qgen_bakeoff.generate("text", CFG)
    s = qgen_bakeoff._load()["models"]["llama3.1:8b"]
    assert s["gens"] == 1 and s["cards"] == 1 and s["seconds"] >= 0
