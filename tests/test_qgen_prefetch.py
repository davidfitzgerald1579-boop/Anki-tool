"""Tests for background pre-generation of card suggestions."""

import threading

import pytest

from snip_occlusion import qgen, qgen_prefetch


@pytest.fixture(autouse=True)
def _clear_state():
    qgen_prefetch._latest = None
    yield
    qgen_prefetch._latest = None


def test_prefetch_generates_in_background(monkeypatch):
    monkeypatch.setattr(
        qgen_prefetch.ocr, "extract_text", lambda img, cfg: "slide text"
    )
    started = threading.Event()
    release = threading.Event()

    def slow_generate(text, cfg, source="slide"):
        started.set()
        assert release.wait(5)
        return [{"front": "Q", "back": "A"}]

    monkeypatch.setattr(qgen_prefetch.qgen, "generate_cards", slow_generate)

    qgen_prefetch.start_for_image(object(), {})
    state = qgen_prefetch.current()
    assert state is not None
    assert started.wait(5)  # generation began without anyone asking
    assert not state.done.is_set()  # still running
    release.set()
    assert qgen_prefetch.wait_for_cards(state, timeout=5) == [
        {"front": "Q", "back": "A"}
    ]
    assert state.text == "slide text"


def test_prefetch_disabled_by_config(monkeypatch):
    monkeypatch.setattr(
        qgen_prefetch.ocr,
        "extract_text",
        lambda img, cfg: pytest.fail("should not OCR"),
    )
    qgen_prefetch.start_for_image(object(), {"qgen_prefetch": False})
    assert qgen_prefetch.current() is None


def test_prefetch_error_is_stored_and_raised(monkeypatch):
    monkeypatch.setattr(
        qgen_prefetch.ocr, "extract_text", lambda img, cfg: "text"
    )

    def boom(text, cfg, source="slide"):
        raise qgen.QGenError("server down")

    monkeypatch.setattr(qgen_prefetch.qgen, "generate_cards", boom)
    qgen_prefetch.start_for_image(object(), {})
    state = qgen_prefetch.current()
    assert state.done.wait(5)
    with pytest.raises(qgen.QGenError, match="server down"):
        qgen_prefetch.wait_for_cards(state, timeout=5)
    assert state.text == "text"  # kept for a live retry


def test_prefetch_empty_ocr_is_an_error(monkeypatch):
    monkeypatch.setattr(
        qgen_prefetch.ocr, "extract_text", lambda img, cfg: "   "
    )
    monkeypatch.setattr(
        qgen_prefetch.qgen,
        "generate_cards",
        lambda text, cfg, source="slide": pytest.fail("should not generate"),
    )
    qgen_prefetch.start_for_image(object(), {})
    state = qgen_prefetch.current()
    assert state.done.wait(5)
    with pytest.raises(qgen.QGenError, match="No text"):
        qgen_prefetch.wait_for_cards(state, timeout=5)


def test_new_snip_replaces_previous_prefetch(monkeypatch):
    monkeypatch.setattr(
        qgen_prefetch.ocr, "extract_text", lambda img, cfg: "text"
    )
    monkeypatch.setattr(
        qgen_prefetch.qgen,
        "generate_cards",
        lambda text, cfg, source="slide": [{"front": "Q", "back": "A"}],
    )
    qgen_prefetch.start_for_image(object(), {})
    first = qgen_prefetch.current()
    qgen_prefetch.start_for_image(object(), {})
    second = qgen_prefetch.current()
    assert second is not first
