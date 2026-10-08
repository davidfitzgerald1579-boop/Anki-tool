"""Tests for the standalone text card window (TextCardDialog).

textcard.py (via dialog.py) imports Anki's `aqt` at module level, which
is not installed in the test environment, so a minimal stand-in is put
into sys.modules before the import: `mw` with the few things the window
touches (the deck list, the add-on config store, reset()), and the
`aqt.utils` helpers it calls. There is no `aqt.qt`, so the Qt shim falls
back to PyQt6 as in every other test.
"""

import sys
import types

import pytest

# --- stand-in for aqt (must precede the snip_occlusion.textcard import)

_module_name = "snip_occlusion"


class _Deck:
    def __init__(self, name, id):
        self.name, self.id = name, id


class _Decks:
    def get_current_id(self):
        return 1

    def all_names_and_ids(self):
        return [_Deck("Default", 1), _Deck("SQE", 2)]


class _Col:
    decks = _Decks()


class _AddonManager:
    def __init__(self):
        self.config = {}
        self.writes = []

    def getConfig(self, module):
        return dict(self.config)

    def writeConfig(self, module, cfg):
        self.config = dict(cfg)
        self.writes.append(dict(cfg))


class _MW:
    def __init__(self):
        self.col = _Col()
        self.addonManager = _AddonManager()
        self.resets = 0

    def reset(self):
        self.resets += 1


_mw = _MW()

if "aqt" not in sys.modules:
    aqt = types.ModuleType("aqt")
    aqt.mw = _mw
    utils = types.ModuleType("aqt.utils")
    utils.showWarning = lambda *a, **k: None
    utils.tooltip = lambda *a, **k: None
    utils.askUser = lambda *a, **k: False
    utils.qconnect = lambda sig, fn: sig.connect(fn)
    utils.restoreGeom = lambda *a, **k: None
    utils.saveGeom = lambda *a, **k: None
    aqt.utils = utils
    sys.modules["aqt"] = aqt
    sys.modules["aqt.utils"] = utils

from PyQt6.QtTest import QTest  # noqa: E402

from snip_occlusion import added_cards, textcard, uitools  # noqa: E402


class _FakeNote:
    """What notes_mod.add_text_note returns, as far as add_card cares."""

    id = 4242

    def keys(self):
        return []


class _AutoYes:
    """Stands in for QMessageBox: a real "discard the unsaved card?"
    box would block the test. Every ask is recorded, so a test can
    check that closing after an add (empty fields) never asked."""

    StandardButton = textcard.QMessageBox.StandardButton
    asked: list = []

    @classmethod
    def question(cls, *a, **k):
        cls.asked.append(a[2] if len(a) > 2 else k.get("text"))
        return cls.StandardButton.Yes


@pytest.fixture
def mw(monkeypatch):
    """A fresh config store and a stubbed note writer for each test."""
    _mw.addonManager = _AddonManager()
    _mw.resets = 0
    added = []

    def add_text_note(col, deck_id, front, back, notes, src, **kw):
        added.append((deck_id, front, back, notes))
        return _FakeNote()

    monkeypatch.setattr(textcard.notes_mod, "add_text_note", add_text_note)
    monkeypatch.setattr(textcard.qgen_feedback, "record", lambda *a, **k: None)
    monkeypatch.setattr(
        textcard.qgen_feedback, "unrecord", lambda *a, **k: None
    )
    monkeypatch.setattr(textcard, "QMessageBox", _AutoYes)
    _AutoYes.asked = []
    _mw.added = added
    _mw.dialogs = []  # every window _open() made, for teardown
    yield _mw
    added_cards.clear()
    # let Qt delete the windows now, while the application is still
    # up, rather than leaving it to Python's garbage collector (a
    # top-level QDialog freed from a dead test frame can crash Qt)
    for dlg in _mw.dialogs:
        dlg.hide()
        dlg.deleteLater()
    for label in list(uitools._active):
        label.hide()
    QTest.qWait(20)


def _open(mw, **kw):
    discards = []
    dlg = textcard.TextCardDialog(on_discard=lambda: discards.append(1), **kw)
    dlg._discards = discards
    mw.dialogs.append(dlg)
    dlg.show()
    QTest.qWait(20)
    assert dlg.isVisible()
    return dlg


def _settle(ms=100):
    """Let the zero-delay close timer (and anything else queued) run."""
    QTest.qWait(ms)


def _notice_showing(text="Card added") -> bool:
    return any(
        label.isVisible() and label.text() == text for label in uitools._active
    )


_SUGGESTION = {"front": "What is mens rea?", "back": "The guilty mind."}


def _use_window(mw):
    """The window "Use →" opens for an AI suggestion."""
    return _open(
        mw,
        front_text=_SUGGESTION["front"],
        back_text=_SUGGESTION["back"],
        original_card=dict(_SUGGESTION),
    )


def test_unpinned_use_window_closes_itself_after_the_add(qapp, mw):
    mw.addonManager.config["text_card_stay_on_top"] = False
    dlg = _use_window(mw)
    assert not dlg.pin_btn.isChecked()
    assert dlg.auto_closes()

    dlg.panel.add_card()

    assert len(mw.added) == 1 and mw.resets == 1
    assert _notice_showing()  # "Card added" went up before the close
    _settle()
    assert not dlg.isVisible()
    assert _AutoYes.asked == []  # fields were empty: no "discard?" box
    assert dlg._discards == []  # closed AFTER adding: nothing to undo
    assert _notice_showing()  # ...and the notice outlives the window


def test_pinned_use_window_stays_open_for_the_next_card(qapp, mw):
    # the default: 📌 on
    dlg = _use_window(mw)
    assert dlg.pin_btn.isChecked()
    assert not dlg.auto_closes()

    dlg.panel.add_card()
    _settle()

    assert len(mw.added) == 1
    assert dlg.isVisible()
    assert not dlg.panel.has_unsaved_text()  # cleared for the next one
    assert _notice_showing()
    dlg.close()


def test_pin_state_is_remembered_for_the_next_use_window(qapp, mw):
    dlg = _use_window(mw)
    assert dlg.pin_btn.isChecked()

    dlg.pin_btn.setChecked(False)  # the student unticks it once...

    assert mw.addonManager.config.get("text_card_stay_on_top") is False
    assert dlg.auto_closes()  # ...and it takes effect at once
    dlg.close()

    again = _use_window(mw)  # ...and for every Use → window after
    assert not again.pin_btn.isChecked()
    assert again.auto_closes()

    again.pin_btn.setChecked(True)  # ticking it back is remembered too
    assert mw.addonManager.config.get("text_card_stay_on_top") is True
    assert not again.auto_closes()
    again.close()


def test_blank_window_never_closes_itself(qapp, mw):
    # Ctrl+Shift+T is for writing card after card, pinned or not
    mw.addonManager.config["text_card_stay_on_top"] = False
    dlg = _open(mw)
    assert not dlg.pin_btn.isChecked()
    assert not dlg.auto_closes()

    dlg.panel.front.insertPlainText("Q")
    dlg.panel.back.insertPlainText("A")
    dlg.panel.add_card()
    _settle()

    assert len(mw.added) == 1
    assert dlg.isVisible()
    assert not dlg.panel.has_unsaved_text()
    dlg.close()


def test_suggestion_learning_runs_once_then_window_may_close(qapp, mw):
    """The one-shot "learn the corrected card" hook still fires on the
    first add, before the window decides whether to close."""
    mw.addonManager.config["text_card_stay_on_top"] = False
    calls = []
    dlg = _use_window(mw)
    original = dlg._learn_corrected
    assert original is not None

    def spy(front, back, notes):
        calls.append((front, back, notes))
        original(front, back, notes)

    dlg._learn_corrected = spy
    dlg.panel.back.insertPlainText(" Corrected.")
    dlg.panel.add_card()
    _settle()

    assert calls == [
        (_SUGGESTION["front"], _SUGGESTION["back"] + " Corrected.", "")
    ]
    assert dlg._learn_corrected is None  # consumed: first add only
    assert not dlg.isVisible()
