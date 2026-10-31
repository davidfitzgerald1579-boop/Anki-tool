"""Tests for the standalone text card window (TextCardDialog).

textcard.py (via dialog.py) imports Anki's `aqt` at module level, which
is not installed in the test environment, so a minimal stand-in is put
into sys.modules before the import: `mw` with the few things the window
touches (the deck list, the add-on config store, reset()), and the
`aqt.utils` helpers it calls. There is no `aqt.qt`, so the Qt shim falls
back to PyQt6 as in every other test.
"""

import gc
import sys
import types
import weakref

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

from PyQt6 import sip  # noqa: E402
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


_OPENED_WINDOW_KEYS = (
    "_snip_occlusion_text_dialog",  # the blank Ctrl+Shift+T window
    "_snip_occlusion_text_dialogs",  # Use → windows
    "_snip_occlusion_added_dialogs",  # fix-an-added-card windows
)


def _take_opened_windows(mw) -> list:
    """Forget (and return) the windows the open_*() functions keep
    on mw."""
    windows = []
    for key in _OPENED_WINDOW_KEYS:
        held = mw.__dict__.pop(key, None)
        if isinstance(held, list):
            windows.extend(held)
        elif held is not None:
            windows.append(held)
    return windows


@pytest.fixture
def mw(monkeypatch):
    """A fresh config store and a stubbed note writer for each test."""
    _mw.addonManager = _AddonManager()
    _mw.resets = 0
    added = []

    def add_text_note(col, deck_id, front, back, notes, src, **kw):
        added.append((deck_id, front, back, notes, kw.get("heading", "")))
        return _FakeNote()

    monkeypatch.setattr(textcard.notes_mod, "add_text_note", add_text_note)
    monkeypatch.setattr(textcard, "_kept_heading", None)  # per session
    monkeypatch.setattr(textcard.qgen_feedback, "record", lambda *a, **k: None)
    monkeypatch.setattr(
        textcard.qgen_feedback, "unrecord", lambda *a, **k: None
    )
    monkeypatch.setattr(textcard, "QMessageBox", _AutoYes)
    _AutoYes.asked = []
    _mw.added = added
    _mw.dialogs = []  # every window _open() made, for teardown
    _take_opened_windows(_mw)  # none left over from an earlier test
    yield _mw
    added_cards.clear()
    # let Qt delete the windows now, while the application is still
    # up, rather than leaving it to Python's garbage collector (a
    # top-level QDialog freed from a dead test frame can crash Qt)
    for dlg in _mw.dialogs + _take_opened_windows(_mw):
        if sip.isdeleted(dlg):
            continue  # already went with the window that owned it
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


# --- the added-cards list on the right


def _record(note_id, front="Q?", back="A."):
    added_cards.record(note_id, 1, front, back, "", front)


def test_added_cards_list_sits_right_of_the_fields(qapp, mw):
    _record(7, "What is mens rea?", "The guilty mind.")
    dlg = _open(mw)

    assert dlg.splitter.widget(1) is dlg.added_list  # right-hand side
    assert dlg.added_list.isVisible()
    assert dlg.added_list.x() > dlg.panel.x()
    assert dlg.added_list.title.text() == "Added cards (1)"

    dlg.panel.front.insertPlainText("Q2")
    dlg.panel.add_card()  # a card added here joins the list at once
    assert dlg.added_list.title.text() == "Added cards (2)"
    dlg.close()


def test_clicking_an_added_card_opens_it_above_this_window(
    qapp, mw, monkeypatch
):
    opened = []
    monkeypatch.setattr(
        textcard,
        "open_added_card_editor",
        lambda note_id, parent=None: opened.append((note_id, parent)),
    )
    _record(7)
    dlg = _open(mw)
    card = dlg.added_list.cards_lay.itemAt(0).widget()

    QTest.mouseClick(card, textcard.Qt.MouseButton.LeftButton)

    assert opened == [(7, dlg)]
    dlg.close()


def test_tucking_the_list_away_narrows_the_window_and_is_remembered(
    qapp, mw
):
    dlg = _open(mw)
    wide = dlg.width()
    fields = dlg.panel.width()

    dlg.added_btn.click()
    QTest.qWait(20)

    assert not dlg.added_list.isVisible()
    assert dlg.width() < wide
    assert abs(dlg.panel.width() - fields) <= 4  # the fields keep theirs
    assert mw.addonManager.config.get("text_card_show_added") is False

    dlg.added_btn.click()
    QTest.qWait(20)

    assert dlg.added_list.isVisible()
    assert abs(dlg.width() - wide) <= 4
    assert mw.addonManager.config.get("text_card_show_added") is True
    dlg.close()


def test_the_next_window_opens_with_the_list_as_left(qapp, mw):
    mw.addonManager.config["text_card_show_added"] = False
    dlg = _open(mw)
    assert not dlg.added_list.isVisible()
    assert dlg.added_btn.text() == "⟨"
    dlg.close()


def test_a_closed_window_stops_listening_for_added_cards(qapp, mw):
    dlg = _open(mw)
    assert dlg.added_list.refresh in added_cards._listeners
    dlg.close()
    assert dlg.added_list.refresh not in added_cards._listeners


# --- typing: B / I / U state, Ctrl+Tab, back to the Front after an add


def _focused(mw):
    dlg = _open(mw)
    dlg.activateWindow()
    QTest.qWaitForWindowActive(dlg)
    return dlg


def _lit(panel):
    return [btn.isChecked() for btn, _ in panel._format_buttons]


def test_format_buttons_light_up_for_the_styles_in_use(qapp, mw):
    dlg = _focused(mw)
    p = dlg.panel
    ctrl = textcard.Qt.KeyboardModifier.ControlModifier
    QTest.keyClicks(p.front, "plain ")
    assert _lit(p) == [False, False, False]

    QTest.keyClick(p.front, textcard.Qt.Key.Key_B, ctrl)
    assert _lit(p) == [True, False, False]  # before typing a letter
    QTest.keyClicks(p.front, "bold")
    QTest.keyClick(p.front, textcard.Qt.Key.Key_U, ctrl)
    QTest.keyClicks(p.front, "both")
    assert _lit(p) == [True, False, True]

    cursor = p.front.textCursor()
    cursor.setPosition(2)  # back inside "plain"
    p.front.setTextCursor(cursor)
    assert _lit(p) == [False, False, False]

    # a right-to-left selection of "bold" reads its own format
    cursor.setPosition(10)
    cursor.setPosition(6, textcard.QTextCursor.MoveMode.KeepAnchor)
    p.front.setTextCursor(cursor)
    assert _lit(p) == [True, False, False]
    p._format_buttons[0][0].click()  # B: switches the bold off...
    assert _lit(p) == [False, False, False]  # ...and goes dark
    dlg.close()


def test_ctrl_tab_moves_down_the_boxes_and_round(qapp, mw):
    dlg = _focused(mw)
    p = dlg.panel
    ctrl = textcard.Qt.KeyboardModifier.ControlModifier
    shift = textcard.Qt.KeyboardModifier.ShiftModifier
    tab = textcard.Qt.Key.Key_Tab

    QTest.keyClicks(p.front, "Question")
    QTest.keyClick(p.front, tab, ctrl)
    assert textcard.QApplication.focusWidget() is p.back
    assert p.front.toPlainText() == "Question"  # no tab typed
    QTest.keyClick(p.back, tab, ctrl)
    assert textcard.QApplication.focusWidget() is p.notes
    QTest.keyClick(p.notes, tab, ctrl)  # round to the top box
    assert textcard.QApplication.focusWidget() is p.heading_edit
    QTest.keyClick(p.heading_edit, tab, ctrl)
    assert textcard.QApplication.focusWidget() is p.front

    # Ctrl+Shift+Tab goes back up (Qt reports Shift+Tab as Backtab)
    QTest.keyClick(p.front, textcard.Qt.Key.Key_Backtab, ctrl | shift)
    assert textcard.QApplication.focusWidget() is p.heading_edit
    QTest.keyClick(p.heading_edit, textcard.Qt.Key.Key_Backtab, ctrl | shift)
    assert textcard.QApplication.focusWidget() is p.notes
    dlg.close()


def test_typing_cursor_goes_back_to_the_front_after_an_add(qapp, mw):
    dlg = _focused(mw)
    p = dlg.panel
    ctrl = textcard.Qt.KeyboardModifier.ControlModifier
    QTest.keyClicks(p.front, "Q")
    QTest.keyClick(p.front, textcard.Qt.Key.Key_Tab, ctrl)
    QTest.keyClick(p.back, textcard.Qt.Key.Key_B, ctrl)
    QTest.keyClicks(p.back, "A")

    QTest.keyClick(p.back, textcard.Qt.Key.Key_Return, ctrl)  # add
    _settle()

    assert len(mw.added) == 1
    assert textcard.QApplication.focusWidget() is p.front
    assert not p.has_unsaved_text()
    assert _lit(p) == [False, False, False]  # the bold stayed behind
    dlg.close()


def test_a_window_parked_at_the_screen_edge_stays_on_screen(qapp, mw):
    dlg = _open(mw)
    avail = dlg.screen().availableGeometry()
    right = avail.x() + avail.width()
    dlg.added_btn.click()  # tucked away: the narrow box...
    QTest.qWait(20)
    geo = dlg.geometry()
    dlg.setGeometry(right - geo.width(), geo.y(), geo.width(), geo.height())
    QTest.qWait(20)  # ...parked flush against the right edge

    dlg.added_btn.click()  # the list comes back
    QTest.qWait(20)

    assert dlg.added_list.isVisible()
    assert dlg.geometry().x() + dlg.width() <= right
    dlg.close()


# --- the heading, and Keep heading


def test_heading_goes_on_the_card_and_clears_after_the_add(qapp, mw):
    dlg = _open(mw)
    p = dlg.panel
    assert p.keep_heading_box.isVisible()
    assert not p.keep_heading_box.isChecked()  # off by default

    p.heading_edit.setText("  Contract <law>   — consideration ")
    p.front.insertPlainText("What is consideration?")
    p.add_card()

    # spaces tidied, and escaped for the field
    assert mw.added[-1][4] == "Contract &lt;law> — consideration"
    entry = added_cards.entries()[-1]
    assert entry["heading"] == "Contract <law> — consideration"  # plain
    assert p.heading_edit.text() == ""  # not kept: cleared with the card
    dlg.close()


def test_keep_heading_holds_it_for_card_after_card(qapp, mw):
    dlg = _open(mw)
    p = dlg.panel
    p.heading_edit.setText("Tort — Negligence")
    p.keep_heading_box.setChecked(True)

    for question in ("Duty?", "Breach?"):
        p.front.insertPlainText(question)
        p.add_card()
        assert p.heading_edit.text() == "Tort — Negligence"
        assert not p.has_unsaved_text()  # a kept heading is no card

    assert [a[4] for a in mw.added] == ["Tort — Negligence"] * 2
    dlg.close()
    assert _AutoYes.asked == []  # closing never asks about the heading


def test_a_kept_heading_carries_into_windows_opened_later(qapp, mw):
    first = _open(mw)
    first.panel.heading_edit.setText("Crime — Mens rea")
    first.panel.keep_heading_box.setChecked(True)
    first.panel.heading_edit.setText("Crime — Actus reus")  # edited later
    first.close()

    again = _open(mw)  # Ctrl+Shift+T reopened...
    assert again.panel.heading_edit.text() == "Crime — Actus reus"
    assert again.panel.keep_heading_box.isChecked()
    use = _use_window(mw)  # ...and a Use → window
    assert use.panel.heading_edit.text() == "Crime — Actus reus"
    assert use.panel.keep_heading_box.isChecked()

    use.panel.keep_heading_box.setChecked(False)  # unticked: let go
    use.close()
    later = _open(mw)
    assert later.panel.heading_edit.text() == ""
    assert not later.panel.keep_heading_box.isChecked()
    later.close()
    again.close()


def test_an_unkept_heading_elsewhere_leaves_the_kept_one_alone(qapp, mw):
    keeper = _open(mw)
    keeper.panel.heading_edit.setText("Land — Easements")
    keeper.panel.keep_heading_box.setChecked(True)
    other = _use_window(mw)  # opened with it, then unticked by hand
    other.panel.keep_heading_box.setChecked(False)
    keeper.panel.keep_heading_box.setChecked(False)
    keeper.panel.keep_heading_box.setChecked(True)  # the keeper re-ticks

    other.panel.heading_edit.setText("Something else")  # typed, unkept...
    other.panel.add_card()  # ...and cleared after the add

    assert mw.added[-1][4] == "Something else"
    assert other.panel.heading_edit.text() == ""
    assert textcard._kept_heading == "Land — Easements"
    other.close()
    keeper.close()


def test_enter_and_tab_in_the_heading_move_on_to_the_front(
    qapp, mw, monkeypatch
):
    snips = []
    monkeypatch.setattr(
        textcard, "get_previous_snip_text", lambda: snips.append(1) or "X"
    )
    dlg = _focused(mw)
    p = dlg.panel
    p.heading_edit.setFocus()
    QTest.keyClicks(p.heading_edit, "Land law")

    QTest.keyClick(p.heading_edit, textcard.Qt.Key.Key_Return)

    assert textcard.QApplication.focusWidget() is p.front
    assert snips == [] and mw.added == []  # no button was clicked
    assert p.heading_edit.text() == "Land law"

    p.heading_edit.setFocus()
    QTest.keyClick(p.heading_edit, textcard.Qt.Key.Key_Tab)
    assert textcard.QApplication.focusWidget() is p.front
    dlg.close()


def test_fixing_an_added_card_keeps_its_own_heading(qapp, mw, monkeypatch):
    removed = []
    monkeypatch.setattr(
        textcard.notes_mod,
        "remove_note",
        lambda col, note_id: removed.append(note_id),
    )
    host = _open(mw)
    monkeypatch.setattr(textcard, "_kept_heading", "Something kept")
    added_cards.record(7, 1, "Q?", "A.", "", "Q?", heading="Equity — Trusts")
    fix = textcard.AddedCardDialog(added_cards.get(7), parent=host)
    mw.dialogs.append(fix)
    fix.show()
    QTest.qWait(20)
    p = fix.panel
    assert p.heading_edit.text() == "Equity — Trusts"  # not the kept one
    assert not p.keep_heading_box.isVisible()

    p.heading_edit.setText("Equity — Express trusts")
    p.add_card()  # Redeploy

    assert mw.added[-1][4] == "Equity — Express trusts"
    assert removed == [7]
    assert added_cards.get(_FakeNote.id)["heading"] == "Equity — Express trusts"
    assert textcard._kept_heading == "Something kept"  # left alone
    host.close()


# --- fixing an added card after the window it came from has gone
#
# A text card window is parentless, so only Python keeps it alive: a
# closed one is let go when the next one opens, and Qt deletes the
# fix-a-card windows it owned along with it. The list of fix windows
# then held a dead one, and the next click on an added card crashed
# with "wrapped C/C++ object of type AddedCardDialog has been deleted".


def _open_window(kind: str):
    """Open a text card window the way the add-on does: the blank
    Ctrl+Shift+T one, or a Use → one for an AI suggestion."""
    if kind == "blank":
        textcard.open_text_card_dialog()
        dlg = textcard.mw._snip_occlusion_text_dialog
    else:
        textcard.open_text_card_dialog(
            front_text=_SUGGESTION["front"],
            back_text=_SUGGESTION["back"],
            original_card=dict(_SUGGESTION),
        )
        dlg = textcard.mw._snip_occlusion_text_dialogs[-1]
    QTest.qWait(20)
    assert dlg.isVisible()
    return dlg


def _fix_windows(mw) -> list:
    return list(getattr(mw, "_snip_occlusion_added_dialogs", []))


@pytest.mark.parametrize("kind", ["blank", "use"])
def test_fixing_a_card_after_the_window_is_reopened_does_not_crash(
    qapp, mw, kind
):
    _record(7)
    first = _open_window(kind)
    first.added_list.open(7)  # fix a card...
    fix = _fix_windows(mw)[-1]
    fix.reject()  # ...close the fix...
    first.close()  # ...and the window
    _settle()
    old_window = weakref.ref(first)
    del first, fix

    second = _open_window(kind)  # the old window is let go here
    gc.collect()  # Anki collects garbage on a timer

    second.added_list.open(7)  # crashed here

    fixes = _fix_windows(mw)
    assert len(fixes) == 1  # the closed fix window was dropped
    assert fixes[0].isVisible() and fixes[0].parentWidget() is second
    # and nothing is kept alive for nothing: with its fix window
    # closed and dropped, the old window is freed
    gc.collect()
    assert old_window() is None


@pytest.mark.parametrize("kind", ["blank", "use"])
def test_an_open_fix_survives_the_window_being_reopened(qapp, mw, kind):
    _record(7)
    first = _open_window(kind)
    first.added_list.open(7)
    fix = _fix_windows(mw)[-1]
    QTest.qWait(20)
    fix.panel.front.setPlainText("Q, corrected")
    first.close()  # the fix window stays up
    _settle()
    del first

    _open_window(kind)  # the old window is let go here
    gc.collect()

    # used to vanish, taking the half-done fix with it
    assert not sip.isdeleted(fix)
    assert fix.isVisible()
    assert fix.panel.front.toPlainText() == "Q, corrected"


def test_dead_windows_left_on_mw_are_skipped_not_crashed_on(qapp, mw):
    _record(7)
    host = _open(mw)
    dead_fix = textcard.AddedCardDialog(added_cards.get(7), parent=host)
    dead_blank = textcard.TextCardDialog()
    dead_use = textcard.TextCardDialog()
    for dead in (dead_fix, dead_blank, dead_use):
        sip.delete(dead)
    mw._snip_occlusion_added_dialogs = [dead_fix]
    mw._snip_occlusion_text_dialog = dead_blank
    mw._snip_occlusion_text_dialogs = [dead_use]

    textcard.open_added_card_editor(7, parent=host)
    blank = _open_window("blank")
    use = _open_window("use")

    assert _fix_windows(mw)[0].isVisible()
    assert len(_fix_windows(mw)) == 1
    assert blank is not dead_blank
    assert mw._snip_occlusion_text_dialogs == [use]


def test_is_showing_is_false_for_a_deleted_or_missing_window(qapp):
    w = textcard.QWidget()
    assert not uitools.is_showing(w)  # never shown
    w.show()
    assert uitools.is_showing(w)
    sip.delete(w)
    assert not uitools.is_showing(w)  # w.isVisible() would raise
    assert not uitools.is_showing(None)


# --- Esc closes a text card window the same way the X button does
#
# QDialog turns Esc into reject(), and since Qt 6.3 reject() hides the
# window without a close event, so closeEvent never ran: no "discard
# the unsaved card?" prompt, a Use → card not handed back, and the
# window kept listening for added cards (so it was never freed).


class _AutoNo(_AutoYes):
    @classmethod
    def question(cls, *a, **k):
        cls.asked.append(a[2] if len(a) > 2 else k.get("text"))
        return cls.StandardButton.No


def _esc(dlg):
    QTest.keyClick(dlg.panel.front, textcard.Qt.Key.Key_Escape)
    _settle(20)


def test_esc_asks_before_throwing_a_typed_card_away(qapp, mw, monkeypatch):
    dlg = _open(mw)
    dlg.panel.front.setFocus()
    dlg.panel.front.insertPlainText("half-typed card")
    monkeypatch.setattr(textcard, "QMessageBox", _AutoNo)
    _AutoNo.asked = []

    _esc(dlg)

    assert _AutoNo.asked == ["Close and discard the unsaved card?"]
    assert dlg.isVisible()  # answered No: the card is still there
    assert dlg.panel.front.toPlainText() == "half-typed card"

    monkeypatch.setattr(textcard, "QMessageBox", _AutoYes)
    _esc(dlg)

    assert _AutoYes.asked == ["Close and discard the unsaved card?"]
    assert not dlg.isVisible()
    assert dlg.added_list.refresh not in added_cards._listeners


def test_esc_on_an_empty_window_just_closes_it(qapp, mw):
    dlg = _open(mw)
    _esc(dlg)
    assert not dlg.isVisible()
    assert _AutoYes.asked == []  # nothing to lose: no question
    assert dlg.added_list.refresh not in added_cards._listeners


def test_esc_on_a_use_window_hands_the_card_back(qapp, mw):
    dlg = _use_window(mw)
    _esc(dlg)
    assert not dlg.isVisible()
    assert dlg._discards == [1]  # the suggestion returns to the list


# --- a new snip while a suggestion's ⚠ Ref / ✎ Fix box is open
#
# Both boxes are modal, but the clipboard still reaches the Snip
# Occlusion window: a snip taken meanwhile replaces the suggestions
# and the box's own event loop deletes their rows, this one included.
# Removing the row once the box closed crashed with "wrapped C/C++
# object of type QFrame has been deleted".


@pytest.fixture
def page(qapp, mw, monkeypatch):
    """A Suggested Cards page with one suggestion on it."""
    errors = []
    # an exception in a button's slot goes to sys.excepthook once it is
    # replaced (with the default hook PyQt aborts the whole test run)
    monkeypatch.setattr(sys, "excepthook", lambda t, v, tb: errors.append(v))
    monkeypatch.setattr(textcard.qgen_bakeoff, "tally", lambda *a, **k: None)
    lessons, phantoms = [], []
    monkeypatch.setattr(
        textcard.qgen_feedback,
        "record",
        lambda card, verdict, **k: lessons.append((card, verdict)),
    )
    monkeypatch.setattr(
        textcard.qgen_feedback, "record_phantom", phantoms.append
    )
    p = textcard.SuggestionsPage()
    mw.dialogs.append(p)
    p._add_card_row({"front": "Q?", "back": "A."})
    p.show()
    QTest.qWait(20)
    p.errors, p.lessons, p.phantoms = errors, lessons, phantoms
    return p


def _rows(page) -> list:
    lay = page.suggest_lay
    return [lay.itemAt(i).widget() for i in range(lay.count() - 1)]


def _new_snip_replaces_the_rows(page) -> None:
    """What a snip taken while a box is open does: refresh_suggestions()
    clears the rows, and the box's event loop runs their deleteLater()
    before the box closes."""
    rows = _rows(page)
    page._clear_rows()
    for row in rows:
        sip.delete(row)


def _click(page, label: str) -> None:
    row = _rows(page)[0]
    btn = next(
        b for b in row.findChildren(textcard.QPushButton) if b.text() == label
    )
    btn.click()


class _RefBox:
    """Stands in for the ⚠ Ref prompt (QInputDialog.getText)."""

    answer = "R v Made Up [2099]"
    meanwhile = None  # called while the box is "open"

    @classmethod
    def getText(cls, *a, **k):
        if cls.meanwhile is not None:
            cls.meanwhile()
        return cls.answer, True


def test_ref_still_clears_the_row_and_can_be_undone(page, monkeypatch):
    _RefBox.meanwhile = None
    monkeypatch.setattr(textcard, "QInputDialog", _RefBox)

    _click(page, "⚠ Ref")
    _settle(20)

    assert page.errors == []
    assert page.phantoms == [_RefBox.answer]
    assert _rows(page) == []
    assert len(page._undo_stack) == 1 and page.undo_btn.isEnabled()


def test_a_snip_during_the_ref_prompt_does_not_crash(page, monkeypatch):
    _RefBox.meanwhile = lambda: _new_snip_replaces_the_rows(page)
    monkeypatch.setattr(textcard, "QInputDialog", _RefBox)

    _click(page, "⚠ Ref")
    _settle(20)

    assert page.errors == []  # was: RuntimeError ... QFrame ... deleted
    assert page.phantoms == [_RefBox.answer]  # still blocklisted
    # ↶ on the new list must not bring back the old slide's card
    assert page._undo_stack == [] and not page.undo_btn.isEnabled()


def test_a_snip_during_the_fix_box_does_not_crash(page, monkeypatch):
    class _FixBox(textcard.QDialog):
        def exec(self):
            front = self.findChildren(textcard.QPlainTextEdit)[0]
            front.setPlainText("Q, corrected")
            _new_snip_replaces_the_rows(page)
            return textcard.QDialog.DialogCode.Accepted

    monkeypatch.setattr(textcard, "QDialog", _FixBox)

    _click(page, "✎ Fix")
    _settle(20)

    assert page.errors == []  # was: RuntimeError ... QFrame ... deleted
    # the correction is still learned...
    assert [c["front"] for c, _ in page.lessons] == ["Q, corrected"]
    # ...but ↶ on the new list must not bring back the old slide's card
    assert page._undo_stack == [] and not page.undo_btn.isEnabled()
