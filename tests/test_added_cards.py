"""Tests for the session registry of added text cards."""

import pytest

from snip_occlusion import added_cards


@pytest.fixture(autouse=True)
def _clean():
    added_cards.clear()
    added_cards._listeners.clear()
    yield
    added_cards.clear()
    added_cards._listeners.clear()


def test_record_get_forget():
    added_cards.record(1, 5, "<b>F</b>", "B", "", "  What is  mens rea? ")
    entry = added_cards.get(1)
    assert entry["front"] == "<b>F</b>" and entry["deck_id"] == 5
    assert entry["label"] == "What is mens rea?"  # whitespace collapsed
    assert len(added_cards.entries()) == 1
    added_cards.forget(1)
    assert added_cards.get(1) is None
    assert added_cards.entries() == []


def test_replace_swaps_note_and_content():
    added_cards.record(1, 5, "F", "B", "", "old label")
    added_cards.replace(1, 2, 6, "F2", "B2", "N2", "new label")
    assert added_cards.get(1) is None
    entry = added_cards.get(2)
    assert entry["front"] == "F2" and entry["deck_id"] == 6
    assert entry["label"] == "new label"
    assert len(added_cards.entries()) == 1
    # replacing an unknown id still tracks the new note
    added_cards.replace(99, 3, 7, "F3", "B3", "", "x")
    assert added_cards.get(3) is not None


def test_listeners_fire_and_broken_ones_are_dropped():
    events = []
    added_cards.add_listener(lambda: events.append("ok"))

    def broken():
        raise RuntimeError("window closed")

    added_cards.add_listener(broken)
    added_cards.record(1, 5, "F", "B", "", "label")
    assert events == ["ok"]
    assert broken not in added_cards._listeners  # dropped on failure
    added_cards.forget(1)
    assert events == ["ok", "ok"]


def test_empty_label_gets_placeholder():
    added_cards.record(1, 5, "<img>", "B", "", "   ")
    assert added_cards.get(1)["label"] == "(untitled card)"


def test_source_kept_through_record_and_replace():
    src = '<img src="snip-occlusion-src-ab12.png">'
    added_cards.record(1, 5, "F", "B", "", "label", source=src)
    assert added_cards.get(1)["source"] == src
    # a redeploy carries the source over to the replacement entry
    added_cards.replace(1, 2, 5, "F2", "B2", "", "label", source=src)
    assert added_cards.get(2)["source"] == src
    # replacing an unknown id records the source too
    added_cards.replace(99, 3, 7, "F3", "B3", "", "x", source=src)
    assert added_cards.get(3)["source"] == src
    # and by default the field is present but empty
    added_cards.record(4, 5, "F", "B", "", "label")
    assert added_cards.get(4)["source"] == ""
