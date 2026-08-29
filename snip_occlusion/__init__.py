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


if gui_hooks is not None:
    gui_hooks.main_window_did_init.append(_setup_menu)
