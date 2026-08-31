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


@pytest.fixture
def alternate(monkeypatch):
    """Make the random model pick deterministic: cycle the contenders."""
    state = {"i": 0}

    def cycling_choice(seq):
        value = seq[state["i"] % len(seq)]
        state["i"] += 1
        return value

    monkeypatch.setattr(qgen_bakeoff.random, "choice", cycling_choice)


def test_disabled_passes_through_without_stamping(fake_generate):
    cards = qgen_bakeoff.generate("text", {"qgen_bakeoff": False})
    assert "_model" not in cards[0]
    assert fake_generate == [None]  # model untouched


def test_enabled_picks_at_random_and_stamps(fake_generate, monkeypatch):
    # the pick goes through random.choice over the contenders
    monkeypatch.setattr(
        qgen_bakeoff.random, "choice", lambda seq: seq[-1]
    )
    card = qgen_bakeoff.generate("text", CFG)[0]
    assert card["_model"] == "llama3.2:3b"
    assert fake_generate == ["llama3.2:3b"]  # config carried the model


def test_alternation_over_many_calls(fake_generate, alternate):
    stamped = [qgen_bakeoff.generate("text", CFG)[0]["_model"] for _ in range(4)]
    assert stamped == [
        "llama3.1:8b",
        "llama3.2:3b",
        "llama3.1:8b",
        "llama3.2:3b",
    ]
    assert fake_generate == stamped


def test_custom_contenders_and_fallback():
    cfg = dict(CFG, qgen_bakeoff_models=["a:1", "b:2", "c:3"])
    assert qgen_bakeoff.contenders(cfg) == ["a:1", "b:2", "c:3"]
    # a broken value falls back to the default pair
    assert len(qgen_bakeoff.contenders(dict(CFG, qgen_bakeoff_models="x"))) == 2


def test_small_large_orders_by_parameter_count():
    assert qgen_bakeoff.small_large({}) == ("llama3.2:3b", "llama3.1:8b")
    cfg = {"qgen_bakeoff_models": ["qwen2.5:14b", "qwen2.5:1.5b"]}
    assert qgen_bakeoff.small_large(cfg) == ("qwen2.5:1.5b", "qwen2.5:14b")
    # unparsable names keep configured order (second treated as smaller)
    cfg = {"qgen_bakeoff_models": ["mystery-big", "mystery-small"]}
    small, large = qgen_bakeoff.small_large(cfg)
    assert {small, large} == {"mystery-big", "mystery-small"}


def test_tally_and_undo(fake_generate, alternate):
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


def test_summary_verdicts(fake_generate, alternate):
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


def test_summary_detects_real_difference(fake_generate, alternate):
    # model A keeps everything, model B loses everything
    for _ in range(30):
        card = qgen_bakeoff.generate("text", CFG)[0]
        good = card["_model"] == "llama3.1:8b"
        qgen_bakeoff.tally(card, "great" if good else "bad")
    text = qgen_bakeoff.summary()
    assert "REAL" in text
    assert "kept 100%" in text and "kept 0%" in text


def test_fixed_verdict_judged_not_kept(fake_generate, alternate):
    # ✎ Fix: the correction counts against the model's kept-rate and
    # shows up in the scoreboard, without ever counting as "kept"
    card = qgen_bakeoff.generate("text", CFG)[0]
    qgen_bakeoff.tally(card, "use")
    qgen_bakeoff.tally(card, "fixed")
    s = qgen_bakeoff._load()["models"][card["_model"]]
    assert s["fixed"] == 1
    text = qgen_bakeoff.summary()
    assert "kept 50% (1 of 2)" in text
    assert "1 needed correcting" in text
    # undo (the ↶ button) takes the correction back out
    qgen_bakeoff.tally(card, "fixed", undo=True)
    assert "needed correcting" not in qgen_bakeoff.summary()


def test_stats_backfills_older_files(tmp_path):
    # a stats file written before the "fixed" verdict existed must not
    # crash the scoreboard - missing keys are treated as zero
    import json

    path = qgen_bakeoff._path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "next": 0,
                "models": {
                    "old:1b": {
                        "seconds": 1.0,
                        "gens": 1,
                        "cards": 2,
                        "use": 2,
                    }
                },
            },
            fh,
        )
    text = qgen_bakeoff.summary()
    assert "kept 100% (2 of 2)" in text
    assert "needed correcting" not in text


def test_focus_forwarded_only_when_set(alternate, monkeypatch):
    calls = []

    def fake(text, config, source="slide", focus=None):
        calls.append((config.get("qgen_model"), focus))
        return [{"front": "Q", "back": "A"}]

    monkeypatch.setattr(qgen_bakeoff.qgen, "generate_cards", fake)
    # focused generation goes through the bake-off machinery too
    card = qgen_bakeoff.generate("text", CFG, focus=["a passage"])[0]
    assert card["_model"] == "llama3.1:8b"
    assert calls[-1] == ("llama3.1:8b", ["a passage"])
    # without focus the kwarg is omitted, so (text, cfg, source)
    # stand-ins keep working
    qgen_bakeoff.generate(
        "text", {"qgen_bakeoff": False}, focus=None
    )
    assert calls[-1] == (None, None)


def test_timings_recorded(fake_generate, alternate):
    qgen_bakeoff.generate("text", CFG)
    s = qgen_bakeoff._load()["models"]["llama3.1:8b"]
    assert s["gens"] == 1 and s["cards"] == 1 and s["seconds"] >= 0
