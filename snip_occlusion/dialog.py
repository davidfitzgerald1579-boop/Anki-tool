"""The Snip Occlusion dialog.

Workflow: snip a slide (Win+Shift+S etc.) -> the image lands here straight
from the clipboard -> draw masks / erase junk text -> Add Cards.
"""

from __future__ import annotations

from aqt import mw
from aqt.utils import showWarning, tooltip

from .qtshim import *  # noqa: F401,F403
from . import notes as notes_mod
from .consts import (
    ADDON_NAME,
    DEFAULT_CONFIG,
    MODE_HIDE_ALL,
    MODE_HIDE_ONE,
    TOOL_ELLIPSE,
    TOOL_ERASE,
    TOOL_RECT,
    TOOL_SELECT,
)
from .editor_canvas import OcclusionCanvas
from .shapes import target_groups

_HELP_TEXT = """<b>Tools</b><br>
<b>S</b> Select &nbsp; <b>R</b> Rectangle &nbsp; <b>E</b> Ellipse &nbsp; \
<b>C</b> Cover-up (erase text)<br><br>
<b>Selection</b><br>
Click = select one &middot; Shift+click = add/remove from selection \
(never moves anything)<br>
Drag on empty area = rubber-band select &middot; Ctrl+A = select all<br><br>
<b>Moving</b><br>
Drag a shape = move <i>only that shape</i> &middot; \
Ctrl+drag = move all selected shapes together<br>
Arrow keys = nudge &middot; Shift+arrows = bigger nudge<br><br>
<b>Groups</b> (shapes revealed together, one card per group)<br>
<b>G</b> group selected &middot; <b>U</b> ungroup<br><br>
<b>Cover-up boxes</b><br>
Filled with the slide's majority colour by default. Right-click or \
double-click one to sample the local background or pick a colour.<br><br>
<b>Other</b><br>
Ctrl+Z / Ctrl+Y undo &middot; redo &middot; Del = delete &middot; \
Ctrl+wheel = zoom &middot; F = fit &middot; middle-drag = pan<br>
Ctrl+Enter = Add Cards"""


def get_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        user = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
        cfg.update(user)
    except Exception:
        pass
    return cfg


class SnipOcclusionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.config = get_config()
        self.setWindowTitle(ADDON_NAME)
        self.setMinimumSize(900, 620)
        self._build_ui()

        self._clipboard = QApplication.clipboard()
        qconnect(self._clipboard.dataChanged, self._on_clipboard_changed)
        self._load_clipboard_image(initial=True)

    # ------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- toolbar
        bar = QHBoxLayout()
        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for tool, label, tip in [
            (TOOL_SELECT, "Select", "Select / move / resize (S)"),
            (TOOL_RECT, "▭ Box", "Draw occlusion rectangle (R)"),
            (TOOL_ELLIPSE, "◯ Oval", "Draw occlusion ellipse (E)"),
            (TOOL_ERASE, "⌫ Cover-up", "Erase slide text: draws a box filled "
                                        "with the background colour (C)"),
        ]:
            btn = QToolButton(self)
            btn.setText(label)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            self.tool_group.addButton(btn)
            self.tool_buttons[tool] = btn
            qconnect(btn.clicked, lambda _=False, t=tool: self._pick_tool(t))
            bar.addWidget(btn)
        self.tool_buttons[TOOL_SELECT].setChecked(True)

        bar.addSpacing(12)
        for label, tip, cb in [
            ("Group", "Group selected shapes (G)", self._group),
            ("Ungroup", "Ungroup selected shapes (U)", self._ungroup),
            ("Delete", "Delete selected shapes (Del)", self._delete),
            ("Undo", "Undo (Ctrl+Z)", self._undo),
            ("Redo", "Redo (Ctrl+Y)", self._redo),
            ("Fit", "Fit image to window (F)", self._fit),
        ]:
            btn = QToolButton(self)
            btn.setText(label)
            btn.setToolTip(tip)
            qconnect(btn.clicked, lambda _=False, f=cb: f())
            bar.addWidget(btn)

        bar.addSpacing(12)
        self.swatch_btn = QToolButton(self)
        self.swatch_btn.setToolTip(
            "Cover-up fill colour (auto-detected majority colour of the "
            "slide). Click to change."
        )
        self.swatch_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        swatch_menu = QMenu(self)
        qconnect(
            swatch_menu.addAction("Auto (slide's majority colour)").triggered,
            self._swatch_auto,
        )
        qconnect(
            swatch_menu.addAction("Choose colour…").triggered,
            self._swatch_pick,
        )
        self.swatch_btn.setMenu(swatch_menu)
        bar.addWidget(self.swatch_btn)

        bar.addStretch(1)

        self.clip_btn = QPushButton("📋 Load new snip from clipboard", self)
        qconnect(self.clip_btn.clicked, self._load_clipboard_clicked)
        bar.addWidget(self.clip_btn)

        help_btn = QToolButton(self)
        help_btn.setText("?")
        help_btn.setToolTip("Shortcuts and tips")
        qconnect(help_btn.clicked, self._show_help)
        bar.addWidget(help_btn)
        layout.addLayout(bar)

        # --- canvas / placeholder stack
        self.stack = QStackedWidget(self)
        placeholder = QLabel(
            "<div style='color:#bbb;font-size:16px'>"
            "<p><b>Snip a slide to get started.</b></p>"
            "<p>Take a screenshot snip (e.g. <b>Win+Shift+S</b>) of your BPP "
            "slide —<br>it will appear here automatically from the clipboard."
            "</p></div>",
            self,
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("background:#3b3b3b;")
        self.canvas = OcclusionCanvas(self.config, self)
        self.stack.addWidget(placeholder)
        self.stack.addWidget(self.canvas)
        layout.addWidget(self.stack, 1)

        qconnect(self.canvas.shapes_changed, self._refresh_counts)
        qconnect(self.canvas.tool_changed, self._tool_synced)

        # --- bottom form
        form = QGridLayout()
        form.setColumnStretch(1, 2)
        form.setColumnStretch(3, 2)

        form.addWidget(QLabel("Deck:"), 0, 0)
        self.deck_box = QComboBox(self)
        self._populate_decks()
        form.addWidget(self.deck_box, 0, 1)

        form.addWidget(QLabel("Tags:"), 0, 2)
        self.tags_edit = QLineEdit(self)
        self.tags_edit.setPlaceholderText("space-separated, e.g. SQE public-law")
        form.addWidget(self.tags_edit, 0, 3)

        form.addWidget(QLabel("Header:"), 1, 0)
        self.header_edit = QLineEdit(self)
        self.header_edit.setPlaceholderText(
            "shown above the image, e.g. Administrative Court"
        )
        form.addWidget(self.header_edit, 1, 1)

        form.addWidget(QLabel("Footer:"), 1, 2)
        self.footer_edit = QLineEdit(self)
        self.footer_edit.setPlaceholderText("shown on the answer side")
        form.addWidget(self.footer_edit, 1, 3)
        layout.addLayout(form)

        # --- mode + add row
        bottom = QHBoxLayout()
        self.mode_hag = QRadioButton("Hide All, Guess One", self)
        self.mode_hag.setToolTip(
            "Question: every mask hidden, target highlighted.\n"
            "Answer: target revealed, other masks stay (click to peek)."
        )
        self.mode_hog = QRadioButton("Hide One, Guess One", self)
        self.mode_hog.setToolTip(
            "Question: only the target group is masked.\n"
            "Answer: target revealed."
        )
        if self.config.get("default_mode", MODE_HIDE_ALL) == MODE_HIDE_ONE:
            self.mode_hog.setChecked(True)
        else:
            self.mode_hag.setChecked(True)
        bottom.addWidget(self.mode_hag)
        bottom.addWidget(self.mode_hog)
        bottom.addStretch(1)

        self.count_label = QLabel("", self)
        bottom.addWidget(self.count_label)
        bottom.addSpacing(12)

        self.add_btn = QPushButton("Add Cards", self)
        self.add_btn.setDefault(False)
        self.add_btn.setAutoDefault(False)
        qconnect(self.add_btn.clicked, self.add_cards)
        bottom.addWidget(self.add_btn)
        layout.addLayout(bottom)

        add_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        qconnect(add_shortcut.activated, self.add_cards)

        self._update_swatch()
        self._refresh_counts()

    def _populate_decks(self) -> None:
        self.deck_box.clear()
        try:
            current_id = mw.col.decks.get_current_id()
        except AttributeError:
            current_id = mw.col.decks.current()["id"]
        index = 0
        for i, entry in enumerate(mw.col.decks.all_names_and_ids()):
            self.deck_box.addItem(entry.name, entry.id)
            if entry.id == current_id:
                index = i
        self.deck_box.setCurrentIndex(index)

    # ------------------------------------------------------------- clipboard

    def _load_clipboard_image(self, initial: bool = False) -> bool:
        md = self._clipboard.mimeData()
        if md is None or not md.hasImage():
            return False
        img = self._clipboard.image()
        if img.isNull():
            return False
        self.canvas.set_image(img)
        self.stack.setCurrentWidget(self.canvas)
        self.canvas.setFocus()
        self._update_swatch()
        self._refresh_counts()
        self.clip_btn.setStyleSheet("")
        return True

    def _on_clipboard_changed(self) -> None:
        md = self._clipboard.mimeData()
        if md is None or not md.hasImage():
            return
        if not self.canvas.has_image() or not self.canvas.has_shapes():
            # nothing to lose: load the new snip straight away
            self._load_clipboard_image()
        else:
            # don't interrupt work in progress; light the button up instead
            self.clip_btn.setStyleSheet(
                "background:#1a73e8;color:white;font-weight:bold;"
            )

    def _load_clipboard_clicked(self) -> None:
        if self.canvas.has_shapes():
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "Load the new snip and discard the current masks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        if not self._load_clipboard_image():
            showWarning(
                "No image on the clipboard. Snip a slide first "
                "(e.g. Win+Shift+S).",
                parent=self,
                title=ADDON_NAME,
            )

    # ------------------------------------------------------------- callbacks

    def _pick_tool(self, tool: str) -> None:
        self.canvas.set_tool(tool)
        self.canvas.setFocus()

    def _tool_synced(self, tool: str) -> None:
        btn = self.tool_buttons.get(tool)
        if btn and not btn.isChecked():
            btn.setChecked(True)

    def _group(self) -> None:
        if not self.canvas.group_selected():
            tooltip("Select 2+ boxes first (Shift+click)", parent=self)
        self.canvas.setFocus()

    def _ungroup(self) -> None:
        self.canvas.ungroup_selected()
        self.canvas.setFocus()

    def _delete(self) -> None:
        self.canvas.delete_selected()
        self.canvas.setFocus()

    def _undo(self) -> None:
        self.canvas.undo()
        self.canvas.setFocus()

    def _redo(self) -> None:
        self.canvas.redo()
        self.canvas.setFocus()

    def _fit(self) -> None:
        self.canvas.fit()
        self.canvas.setFocus()

    def _swatch_auto(self) -> None:
        self.canvas.erase_color_override = None
        self._update_swatch()

    def _swatch_pick(self) -> None:
        base = self.canvas.erase_color_override or self.canvas.majority
        c = QColorDialog.getColor(base, self)
        if c.isValid():
            self.canvas.erase_color_override = c
            self._update_swatch()

    def _update_swatch(self) -> None:
        color = self.canvas.erase_color_override or self.canvas.majority
        pix = QPixmap(18, 18)
        pix.fill(color)
        self.swatch_btn.setIcon(QIcon(pix))
        auto = self.canvas.erase_color_override is None
        self.swatch_btn.setText(
            "Fill: auto" if auto else "Fill: custom"
        )
        self.swatch_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )

    def _refresh_counts(self) -> None:
        n = len(target_groups(self.canvas.shapes))
        self.count_label.setText(
            "Will create <b>%d</b> card%s" % (n, "" if n == 1 else "s")
        )
        self.add_btn.setEnabled(n > 0)
        self._update_swatch()

    def _show_help(self) -> None:
        QMessageBox.information(self, ADDON_NAME + " – shortcuts", _HELP_TEXT)

    # ------------------------------------------------------------- add cards

    def add_cards(self) -> None:
        if not self.canvas.has_image():
            showWarning("Snip a slide first.", parent=self, title=ADDON_NAME)
            return
        shapes = list(self.canvas.shapes)
        if not target_groups(shapes):
            showWarning(
                "Draw at least one occlusion box first.",
                parent=self,
                title=ADDON_NAME,
            )
            return

        baked = self.canvas.bake_erasures()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        baked.save(buf, "PNG")
        buf.close()
        import uuid as _uuid

        fname = mw.col.media.write_data(
            "snip-occlusion-%s.png" % _uuid.uuid4().hex[:10], bytes(buf.data())
        )

        deck_id = self.deck_box.currentData()
        mode = MODE_HIDE_ALL if self.mode_hag.isChecked() else MODE_HIDE_ONE
        n = notes_mod.add_occlusion_notes(
            mw.col,
            deck_id,
            fname,
            shapes,
            baked.width(),
            baked.height(),
            mode,
            self.header_edit.text().strip(),
            self.footer_edit.text().strip(),
            self.tags_edit.text().strip(),
            self.config.get("mask_fill", "#FFEBA2"),
            self.config.get("target_fill", "#FF7E7E"),
        )
        mw.reset()
        tooltip("Added %d card%s" % (n, "" if n == 1 else "s"), parent=self)

        if self.config.get("close_after_add", False):
            self.accept()
        else:
            # clear the workspace for the next snip (undo-able)
            self.canvas.push_undo()
            self.canvas.shapes = []
            self.canvas.selection = set()
            self.canvas._emit_changed()
            self.canvas.setFocus()

    # ---------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        if self.canvas.has_shapes():
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "Close and discard the current masks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        try:
            self._clipboard.dataChanged.disconnect(self._on_clipboard_changed)
        except TypeError:
            pass
        event.accept()


def open_dialog() -> None:
    if mw.col is None:
        showWarning("Open a profile first.", title=ADDON_NAME)
        return
    existing = getattr(mw, "_snip_occlusion_dialog", None)
    if existing is not None and existing.isVisible():
        existing.raise_()
        existing.activateWindow()
        existing._load_clipboard_image()
        return
    dlg = SnipOcclusionDialog(mw)
    mw._snip_occlusion_dialog = dlg  # keep a reference (GC gotcha)
    dlg.show()
