"""Snip Occlusion - clipboard-first image occlusion for slide snips.

Adds a Tools menu entry (default shortcut Ctrl+Shift+O) that opens the
occlusion editor pre-loaded with whatever image is on the clipboard.
"""

try:
    from aqt import gui_hooks, mw
except ImportError:
    # imported outside Anki (e.g. in tests): submodules stay importable,
    # but there is no UI to hook into
    gui_hooks = None
    mw = None

from .consts import ADDON_NAME, DEFAULT_CONFIG


def _open() -> None:
    from .dialog import open_dialog

    open_dialog()


def _editor_button_clicked(editor) -> None:
    from .dialog import open_edit_dialog

    if editor.note is None or editor.note.id == 0:
        from aqt.utils import showWarning

        showWarning(
            "Save the note first — the ✂ button edits existing "
            "Snip Occlusion cards.",
            title=ADDON_NAME,
        )
        return
    open_edit_dialog(editor.note.id)


def _setup_editor_button(buttons, editor) -> None:
    # the ✂ button in the note editor (Browse / Edit during review):
    # re-opens this card's image with all its boxes for editing
    btn = editor.addButton(
        icon=None,
        cmd="snip_occlusion_edit",
        func=_editor_button_clicked,
        tip="Edit this card's occlusions in Snip Occlusion",
        label="✂",
    )
    buttons.append(btn)


def _setup_menu() -> None:
    from aqt.qt import QAction, QKeySequence
    from aqt.utils import qconnect

    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(mw.addonManager.getConfig(__name__) or {})
    except Exception:
        pass
    action = QAction(ADDON_NAME + " — New from Clipboard…", mw)
    shortcut = cfg.get("shortcut_open") or ""
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
    qconnect(action.triggered, _open)
    mw.form.menuTools.addAction(action)


def _delete_current_card() -> None:
    """One-press deletion of the card being reviewed (undoable, Ctrl+Z)."""
    from aqt.utils import tooltip

    if mw.state != "review" or mw.reviewer.card is None:
        return
    card = mw.reviewer.card
    note = card.note()
    extra = ""
    if len(note.cards()) > 1:
        extra = " (its note had %d cards)" % len(note.cards())
    mw.col.remove_notes([card.nid])
    mw.reset()
    tooltip("Card deleted%s — Ctrl+Z to undo" % extra)


def _review_shortcuts(state, shortcuts) -> None:
    if state == "review":
        shortcuts.append(("Delete", _delete_current_card))


def _reviewer_context_menu(reviewer, menu) -> None:
    from aqt.utils import qconnect

    action = menu.addAction("🗑 Delete this card\tDel")
    qconnect(action.triggered, _delete_current_card)


if gui_hooks is not None:
    gui_hooks.main_window_did_init.append(_setup_menu)
    gui_hooks.editor_did_init_buttons.append(_setup_editor_button)
    gui_hooks.state_shortcuts_will_change.append(_review_shortcuts)
    gui_hooks.reviewer_will_show_context_menu.append(_reviewer_context_menu)
