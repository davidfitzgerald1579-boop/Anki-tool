"""The Snip Occlusion dialog.

Workflow: snip a slide (Win+Shift+S etc.) -> the image lands here straight
from the clipboard -> draw masks / erase junk text -> Add Cards.
"""

from __future__ import annotations

from aqt import mw
from aqt.utils import showWarning, tooltip

from .qtshim import *  # noqa: F401,F403
from . import notes as notes_mod
from . import ocr, qgen_prefetch
from .newcard_panel import NewCardQueuePanel
from .consts import (
    ADDON_NAME,
    DEFAULT_CONFIG,
    MODE_HIDE_ALL,
    MODE_HIDE_ONE,
    TOOL_ERASE,
    TOOL_HIGHLIGHT,
    TOOL_PATCH,
    TOOL_RECT,
    TOOL_SELECT,
)
from .editor_canvas import OcclusionCanvas
from .shapes import target_groups

_HELP_TEXT = """<b>Tools</b><br>
<b>S</b> Select &nbsp; <b>R</b> Box &nbsp; <b>H</b> Highlighter &nbsp; \
<b>C</b> Cover-up (erase text) &nbsp; <b>P</b> Snip patch<br><br>
<b>Word occlusion / highlighting</b><br>
<b>Double-click any word</b> to occlude exactly that word - or, in the \
Highlighter tool, to highlight it instead, and in the Cover-up tool, to \
erase it (hyphenated words count as one). Drag its side handles to swallow or release neighbouring words - \
whole words only, never half a word. Top/bottom handles resize freely; \
the middle of the box always drags to move. If a click grabs the wrong \
amount, press <b>Ctrl+D</b> to copy a debug picture of what was \
detected (to report it).<br><br>
<b>Moving</b> works in every tool: click and hold any box of the \
current tool's kind and drag it. Handles live on the border; the \
middle always moves.<br><br>
<b>Highlighter</b><br>
Draws a perfectly straight band; the text stays readable underneath. \
Right-click a highlight for colours. Baked into the image, never a \
card.<br><br>
<b>Selection</b><br>
Click = select one &middot; Shift+click = add/remove from selection \
(never moves anything)<br>
Drag on empty area = rubber-band select &middot; Ctrl+A = select all<br>
Ctrl+C copies the selected boxes &middot; Ctrl+V pastes them beside the \
originals (never overlapping)<br><br>
<b>Seeing underneath</b><br>
<b>T</b> (or the 👁 button) shows every box as an outline only so the \
text underneath is visible. Right-click one box &rarr; "Peek underneath" \
to see under just that box; right-click again to stop. View-only - \
cards are unaffected.<br><br>
<b>Moving</b><br>
Drag a shape = move <i>only that shape</i> &middot; \
Ctrl+drag = move all selected shapes together<br>
Arrow keys = nudge &middot; Shift+arrows = bigger nudge<br><br>
<b>Groups</b> (shapes revealed together, one card per group)<br>
<b>G</b> group selected &middot; <b>U</b> ungroup<br><br>
<b>Cover-up boxes</b><br>
Filled with the slide's majority colour by default; permanently baked into \
the image, never part of any card. Right-click or double-click one to \
sample the local background or pick a colour.<br><br>
<b>Snip patch</b> (keep one sentence, ditch the paragraph)<br>
Press <b>P</b>, drag over the text you want to KEEP - it becomes a movable \
pixel-perfect cutout. Drag it aside, cover the paragraph with <b>C</b>, \
then drag the cutout back on top. Right-click it to snap it home. Patches \
are baked into the image, never resized, never part of a card.<br><br>
<b>New card queue</b> (spin a sentence off to its own card)<br>
Drag a snip patch off the window and drop it on a queued card, or \
right-click it &rarr; "Send to new card". Several snips can be dropped on \
one card; they stack on a background matching the slide (🎨 to change). \
"Start" loads the next queued card into the editor to draw its boxes; \
queued cards also load automatically after you press Add Cards.<br><br>
<b>Search text (OCR)</b><br>
When cards are added, the text on the image is read automatically and \
stored invisibly on each card so deck search can find it. Use "Text \
preview" to check what is being read; fix recurring misreads via \
"ocr_corrections" in the add-on config.<br><br>
<b>Other</b><br>
Ctrl+Z / Ctrl+Y undo &middot; redo &middot; Del = delete &middot; \
Ctrl+wheel = zoom &middot; F = fit &middot; middle-drag = pan &middot; \
F11 = full screen &middot; ⟨ hides the toolbar<br>
Ctrl+Enter = Add Cards"""


# Warm pastel theme, scoped to this dialog only (never leaks into Anki).
_STYLE = """
* {
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial,
                 sans-serif;
    font-size: 10.5pt;
    color: #3d3929;
}
QDialog {
    background: #faf6ef;
}
QToolButton, QPushButton {
    background: #ffffff;
    border: 1px solid #e3dcd0;
    border-radius: 8px;
    padding: 6px 10px;
}
QToolButton:hover, QPushButton:hover {
    background: #f6eee2;
    border-color: #d8cdbb;
}
QToolButton:pressed, QPushButton:pressed {
    background: #f0e4d3;
}
QToolButton:checked {
    background: #f7ddc9;
    border: 2px solid #d97757;
}
QPushButton#addBtn {
    background: #d97757;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 22px;
}
QPushButton#addBtn:hover {
    background: #c96543;
}
QPushButton#addBtn:disabled {
    background: #e8ddd2;
    color: #a99f8f;
}
QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #e3dcd0;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #f0c9b0;
    selection-color: #3d3929;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #d97757;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e3dcd0;
    selection-background-color: #f6eee2;
    selection-color: #3d3929;
}
QFrame[frameShape="4"] {  /* the separator lines */
    color: #e3dcd0;
}
QRadioButton, QLabel {
    background: transparent;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #f2ece1;
    border: none;
    width: 12px;
    height: 12px;
}
QScrollBar::handle {
    background: #d8cdbb;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: #c4b7a2;
}
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0;
    width: 0;
}
QToolTip {
    background: #fffdf8;
    color: #3d3929;
    border: 1px solid #d8cdbb;
    padding: 4px 6px;
}
QSplitter::handle {
    background: #f2ece1;
    border-radius: 3px;
    margin: 24px 1px;
}
QSplitter::handle:hover {
    background: #e0d5c2;
}
"""


def get_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        user = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
        cfg.update(user)
    except Exception:
        pass
    return cfg


# the most recent OCR text of a snip, for "copy text from previous slide"
_LAST_OCR_TEXT = ""


def _remember_ocr(text: str) -> None:
    global _LAST_OCR_TEXT
    if text:
        _LAST_OCR_TEXT = text


def get_previous_snip_text() -> str:
    """OCR text of the current/most recent snip: reads the live occlusion
    editor's image if one is open, else the last OCR result remembered."""
    dlg = getattr(mw, "_snip_occlusion_dialog", None)
    if dlg is not None and dlg.isVisible() and dlg.canvas.has_image():
        try:
            text = ocr.extract_text(dlg.canvas.bake_image(), dlg.config)
        except Exception:
            text = ""
        if text:
            _remember_ocr(text)
            return text
    return _LAST_OCR_TEXT


class SnipOcclusionDialog(QDialog):
    def __init__(self, parent=None, note_id=None):
        super().__init__(parent or mw)
        self.config = get_config()
        self.edit_note_id = note_id  # editing an existing card's layout
        self._edit_fname = None
        self.setWindowTitle(ADDON_NAME)
        self.setMinimumSize(960, 680)
        # give the dialog real minimize/maximize buttons so the image can be
        # edited at full size; F11 toggles borderless full screen
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(_STYLE)
        self._build_ui()
        fs_shortcut = QShortcut(QKeySequence("F11"), self)
        qconnect(fs_shortcut.activated, self._toggle_fullscreen)

        self._clipboard = QApplication.clipboard()
        if self.edit_note_id is None:
            qconnect(self._clipboard.dataChanged, self._on_clipboard_changed)
            self._load_clipboard_image(initial=True)
        else:
            self._load_note_for_edit()

    # ------------------------------------------------------------------- UI

    def _side_button(self, label: str, tip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setText(label)
        btn.setToolTip(tip)
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        btn.setMinimumHeight(28)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return btn

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # sidebar and canvas live in a splitter: drag the divider to make
        # the toolbar any width you like
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setHandleWidth(7)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter)

        # --- left-hand toolbar
        side_widget = QWidget(self)
        side_widget.setMinimumWidth(150)
        side_widget.setMaximumWidth(400)
        side = QVBoxLayout(side_widget)
        side.setContentsMargins(0, 0, 6, 0)
        side.setSpacing(4)

        self.clip_btn = QPushButton("📋 Load new snip", self)
        self.clip_btn.setToolTip(
            "Load the image currently on the clipboard "
            "(lights up when a new snip is waiting)"
        )
        qconnect(self.clip_btn.clicked, self._load_clipboard_clicked)
        side.addWidget(self.clip_btn)
        side.addWidget(self._separator())

        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for tool, label, tip in [
            (TOOL_SELECT, "Select", "Select / move / resize (S)"),
            (TOOL_RECT, "▭ Box", "Draw occlusion rectangle (R). Tip: "
                                 "double-click any word to occlude exactly "
                                 "that word"),
            (TOOL_HIGHLIGHT, "🖍 Highlight", "Draw a straight highlighter "
                                            "band across the page — text "
                                            "stays readable underneath (H). "
                                            "Right-click one to change "
                                            "colour"),
            (TOOL_ERASE, "⌫ Cover-up", "Erase slide text: draws a box filled "
                                        "with the background colour (C). Tip: "
                                        "double-click any word to erase "
                                        "exactly that word"),
            (TOOL_PATCH, "✂ Snip patch", "Cut out a piece of the image you "
                                         "want to KEEP as a movable, "
                                         "pixel-perfect patch (P)"),
        ]:
            btn = self._side_button(label, tip)
            btn.setCheckable(True)
            self.tool_group.addButton(btn)
            self.tool_buttons[tool] = btn
            qconnect(btn.clicked, lambda _=False, t=tool: self._pick_tool(t))
            side.addWidget(btn)
        self.tool_buttons[TOOL_SELECT].setChecked(True)

        side.addWidget(self._separator())
        for label, tip, cb in [
            ("Group", "Group selected shapes (G)", self._group),
            ("Ungroup", "Ungroup selected shapes (U)", self._ungroup),
            ("Delete", "Delete selected shapes (Del)", self._delete),
            ("Undo", "Undo (Ctrl+Z)", self._undo),
            ("Redo", "Redo (Ctrl+Y)", self._redo),
            ("Fit", "Fit image to window (F)", self._fit),
        ]:
            btn = self._side_button(label, tip)
            qconnect(btn.clicked, lambda _=False, f=cb: f())
            side.addWidget(btn)

        self.xray_btn = self._side_button(
            "👁 See-through",
            "Show every box as an outline only, so the text underneath is "
            "visible while you edit (T). Right-click a single box to peek "
            "under just that one.",
        )
        self.xray_btn.setCheckable(True)
        qconnect(self.xray_btn.clicked, self._xray_clicked)
        side.addWidget(self.xray_btn)

        side.addWidget(self._separator())
        self.swatch_btn = self._side_button(
            "Fill: auto",
            "Cover-up fill colour (auto-detected majority colour of the "
            "slide). Click to change.",
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
        side.addWidget(self.swatch_btn)

        ocr_btn = self._side_button(
            "🔍 Text preview",
            "Show the text OCR reads from the current image - the same text "
            "that will be stored (invisibly) on the cards so deck search "
            "can find them. Use it to spot misreads worth adding to the "
            "corrections list in the add-on config.",
        )
        qconnect(ocr_btn.clicked, self._show_ocr_preview)
        side.addWidget(ocr_btn)

        side.addWidget(self._separator())
        self.queue_panel = NewCardQueuePanel(self)
        self.queue_panel.patch_drop_handler = self._on_patch_dropped_to_card
        qconnect(
            self.queue_panel.start_next_requested, self._start_next_clicked
        )
        # the queue soaks up all spare sidebar height (scroll area size
        # hints don't propagate reliably, so an explicit stretch it is)
        side.addWidget(self.queue_panel, 1)

        text_btn = self._side_button(
            "📝 Text card",
            "Switch to the Text Editor: write a card in your own words, "
            "with AI-suggested cards ready at the top",
        )
        qconnect(text_btn.clicked, self._open_text_card)
        side.addWidget(text_btn)

        help_btn = self._side_button("?  Shortcuts", "Shortcuts and tips")
        qconnect(help_btn.clicked, self._show_help)
        side.addWidget(help_btn)
        self._side_widget = side_widget
        self.splitter.addWidget(side_widget)

        # --- right-hand side: collapse handle + canvas + form
        right_container = QWidget(self)
        right_h = QHBoxLayout(right_container)
        right_h.setContentsMargins(0, 0, 0, 0)
        right_h.setSpacing(4)

        # thin collapse handle so the toolbar can also snap away entirely
        self.collapse_btn = QToolButton(self)
        self.collapse_btn.setText("⟨")
        self.collapse_btn.setToolTip(
            "Hide / show the toolbar (drag the divider to resize it)"
        )
        self.collapse_btn.setFixedWidth(18)
        self.collapse_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        self.collapse_btn.setStyleSheet(
            "QToolButton{border:none;background:#f2ece1;border-radius:4px;"
            "padding:0;}QToolButton:hover{background:#e8dfd0;}"
        )
        qconnect(self.collapse_btn.clicked, self._toggle_sidebar)
        right_h.addWidget(self.collapse_btn)

        right_col = QVBoxLayout()
        right_h.addLayout(right_col, 1)
        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([190, 900])

        # --- Image Editor / Text Editor view toggle (+ settings)
        toggle_row = QHBoxLayout()
        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.image_view_btn = QPushButton("🖼 Image Editor", self)
        self.text_view_btn = QPushButton("📝 Text Editor", self)
        for btn in (self.image_view_btn, self.text_view_btn):
            btn.setCheckable(True)
            self.view_group.addButton(btn)
            toggle_row.addWidget(btn)
        self.image_view_btn.setChecked(True)
        self.image_view_btn.setToolTip("Occlude a snipped slide (default)")
        self.text_view_btn.setToolTip(
            "Write a card in your own words, with AI-suggested cards from "
            "the current snip ready at the top"
        )
        qconnect(
            self.image_view_btn.clicked, lambda _=False: self._set_view(False)
        )
        qconnect(
            self.text_view_btn.clicked, lambda _=False: self._set_view(True)
        )
        toggle_row.addStretch(1)
        settings_btn = QToolButton(self)
        settings_btn.setText("⚙")
        settings_btn.setToolTip("Snip Occlusion settings")
        qconnect(settings_btn.clicked, self._open_settings)
        toggle_row.addWidget(settings_btn)
        right_col.addLayout(toggle_row)

        # the two views: the whole image-editing page, or the text editor
        self.view_stack = QStackedWidget(self)
        right_col.addWidget(self.view_stack, 1)
        self._image_page = QWidget(self)
        layout = QVBoxLayout(self._image_page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view_stack.addWidget(self._image_page)
        from .textcard import TextCardPanel  # deferred: circular import

        self.text_panel = TextCardPanel(self, with_suggestions=True)
        self.view_stack.addWidget(self.text_panel)
        self._sidebar_hidden_for_text = False

        # --- canvas / placeholder stack
        self.stack = QStackedWidget(self)
        placeholder = QLabel(
            "<div style='color:#6b6252;font-size:16px'>"
            "<p><b>Snip a slide to get started.</b></p>"
            "<p>Take a screenshot snip (e.g. <b>Win+Shift+S</b>) of your BPP "
            "slide —<br>it will appear here automatically from the clipboard."
            "</p></div>",
            self,
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(
            "background:#ece5d8;border:1px solid #e3dcd0;border-radius:8px;"
        )
        self.canvas = OcclusionCanvas(self.config, self)
        self.stack.addWidget(placeholder)
        self.stack.addWidget(self.canvas)
        layout.addWidget(self.stack, 1)

        qconnect(self.canvas.shapes_changed, self._refresh_counts)
        qconnect(self.canvas.tool_changed, self._tool_synced)
        qconnect(
            self.canvas.send_patch_to_new_card, self._send_patch_to_new_card
        )
        qconnect(self.canvas.xray_changed, self.xray_btn.setChecked)

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
        self.add_btn.setObjectName("addBtn")
        self.add_btn.setDefault(False)
        self.add_btn.setAutoDefault(False)
        qconnect(self.add_btn.clicked, self.add_cards)
        bottom.addWidget(self.add_btn)
        layout.addLayout(bottom)

        add_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        qconnect(add_shortcut.activated, self._ctrl_return)

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

    # ------------------------------------------------------------- edit mode

    def _load_note_for_edit(self) -> None:
        import os

        note = mw.col.get_note(self.edit_note_id)
        fname = notes_mod.parse_image_fname(note)
        img = QImage(os.path.join(mw.col.media.dir(), fname)) if fname else QImage()
        if img.isNull():
            showWarning(
                "This card's image could not be loaded from the media "
                "folder.",
                parent=self,
                title=ADDON_NAME,
            )
            return
        self._edit_fname = fname
        self.canvas.set_image(img)
        self.canvas.shapes = notes_mod.shapes_from_note(
            note, img.width(), img.height()
        )
        self.canvas._emit_changed()
        self.stack.setCurrentWidget(self.canvas)
        self.canvas.setFocus()
        self._update_swatch()

        self.header_edit.setText(note["Header"])
        self.footer_edit.setText(note["Footer"])
        self.tags_edit.setText(" ".join(note.tags))
        if note["Mode"] == MODE_HIDE_ONE:
            self.mode_hog.setChecked(True)
        else:
            self.mode_hag.setChecked(True)
        cards = note.cards()
        if cards:
            for i in range(self.deck_box.count()):
                if self.deck_box.itemData(i) == cards[0].did:
                    self.deck_box.setCurrentIndex(i)
                    break

        self.setWindowTitle(ADDON_NAME + " — editing existing cards")
        self.add_btn.setText("Save Changes")
        self.clip_btn.setEnabled(False)
        self.clip_btn.setToolTip(
            "Not available while editing an existing card"
        )
        self._refresh_counts()

    def _save_edits(self) -> None:
        import os

        shapes = list(self.canvas.shapes)
        if not target_groups(shapes):
            showWarning(
                "Keep at least one occlusion box, or delete the cards from "
                "the browser instead.",
                parent=self,
                title=ADDON_NAME,
            )
            return
        base_note = mw.col.get_note(self.edit_note_id)

        delete_missing = False
        missing = notes_mod.count_missing_targets(mw.col, base_note, shapes)
        if missing:
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "%d card%s no longer ha%s a box (you deleted or ungrouped "
                "their targets). Delete %s?\n\n"
                "Choosing No keeps the cards, but they will have nothing "
                "to reveal."
                % (
                    missing,
                    "" if missing == 1 else "s",
                    "s" if missing == 1 else "ve",
                    "it" if missing == 1 else "them",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            delete_missing = resp == QMessageBox.StandardButton.Yes

        baked = self.canvas.bake_image()
        search_text = ""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            search_text = ocr.extract_text(baked, self.config)
        except Exception:
            pass
        finally:
            QApplication.restoreOverrideCursor()
        _remember_ocr(search_text)

        # overwrite the media file in place so every sibling keeps its name
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        baked.save(buf, "PNG")
        buf.close()
        with open(
            os.path.join(mw.col.media.dir(), self._edit_fname), "wb"
        ) as f:
            f.write(bytes(buf.data()))

        mode = MODE_HIDE_ALL if self.mode_hag.isChecked() else MODE_HIDE_ONE
        updated, added, removed = notes_mod.update_occlusion_notes(
            mw.col,
            base_note,
            self.deck_box.currentData(),
            shapes,
            baked.width(),
            baked.height(),
            mode,
            self.header_edit.text().strip(),
            self.footer_edit.text().strip(),
            self.tags_edit.text().strip(),
            self.config.get("mask_fill", "#FFEBA2"),
            self.config.get("target_fill", "#FF7E7E"),
            search_text,
            delete_missing=delete_missing,
        )
        mw.reset()
        bits = ["%d card%s updated" % (updated, "" if updated == 1 else "s")]
        if added:
            bits.append("%d new" % added)
        if removed:
            bits.append("%d removed" % removed)
        tooltip(", ".join(bits), parent=mw)
        self.canvas.shapes = []  # nothing left unsaved; close quietly
        self.accept()

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
        # start OCR + AI card suggestions now, so they're ready the moment
        # the user switches to the Text Editor
        try:
            qgen_prefetch.start_for_image(img.copy(), self.config)
            # begin displaying (or queueing up) the new snip's suggestions
            self.text_panel.refresh_suggestions()
        except Exception:
            pass  # prefetching is best-effort, never in the user's way
        # new queue cards default to this slide's background colour
        self.queue_panel.default_bg = self.canvas.majority
        return True

    def _on_clipboard_changed(self) -> None:
        if getattr(self.canvas, "_own_clipboard_write", False):
            # a debug image we placed there ourselves - not a new snip
            self.canvas._own_clipboard_write = False
            return
        md = self._clipboard.mimeData()
        if md is None or not md.hasImage():
            return
        if not self.canvas.has_image() or not self.canvas.has_shapes():
            # nothing to lose: load the new snip straight away
            self._load_clipboard_image()
        else:
            # don't interrupt work in progress; light the button up instead
            self.clip_btn.setStyleSheet(
                "background:#d97757;color:#ffffff;font-weight:bold;"
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

    def _xray_clicked(self, checked: bool) -> None:
        self.canvas.set_xray(checked)
        self.canvas.setFocus()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_sidebar(self) -> None:
        hidden = self._side_widget.isVisible()
        self._side_widget.setVisible(not hidden)
        self.collapse_btn.setText("⟩" if hidden else "⟨")

    # ------------------------------------------------- view toggle, settings

    def _ctrl_return(self) -> None:
        if self.view_stack.currentWidget() is self.text_panel:
            self.text_panel.add_card()
        else:
            self.add_cards()

    def _set_view(self, text_mode: bool) -> None:
        self.text_view_btn.setChecked(text_mode)
        self.image_view_btn.setChecked(not text_mode)
        if text_mode:
            self.view_stack.setCurrentWidget(self.text_panel)
            if (
                self.config.get("text_editor_sidebar", "keep") == "hide"
                and self._side_widget.isVisible()
            ):
                self._sidebar_hidden_for_text = True
                self._toggle_sidebar()
            self.text_panel.refresh_suggestions()
            self.text_panel.focus_front()
        else:
            self.view_stack.setCurrentWidget(self._image_page)
            if (
                self._sidebar_hidden_for_text
                and not self._side_widget.isVisible()
            ):
                self._toggle_sidebar()
            self._sidebar_hidden_for_text = False
            self.canvas.setFocus()

    def _open_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(ADDON_NAME + " — Settings")
        dlg.setStyleSheet(_STYLE)
        lay = QVBoxLayout(dlg)
        lay.addWidget(
            QLabel("<b>When switching to the Text Editor…</b>", dlg)
        )
        keep_radio = QRadioButton("Keep the sidebar visible", dlg)
        hide_radio = QRadioButton(
            "Hide the sidebar (it comes back in the Image Editor)", dlg
        )
        if self.config.get("text_editor_sidebar", "keep") == "hide":
            hide_radio.setChecked(True)
        else:
            keep_radio.setChecked(True)
        lay.addWidget(keep_radio)
        lay.addWidget(hide_radio)
        note = QLabel(
            "<span style='color:#8a8171'>All other settings (AI model, "
            "OCR, colours…) live in Tools → Add-ons → Snip Occlusion → "
            "Config.</span>",
            dlg,
        )
        note.setWordWrap(True)
        lay.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            dlg,
        )
        qconnect(buttons.accepted, dlg.accept)
        qconnect(buttons.rejected, dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        value = "hide" if hide_radio.isChecked() else "keep"
        self.config["text_editor_sidebar"] = value
        try:
            module = __name__.split(".")[0]
            user_cfg = mw.addonManager.getConfig(module) or {}
            user_cfg["text_editor_sidebar"] = value
            mw.addonManager.writeConfig(module, user_cfg)
        except Exception:
            pass  # setting still applies for this window

    # ------------------------------------------------------- new card queue

    def _send_patch_to_new_card(self, patch_id: str) -> None:
        img = self.canvas.take_patch(patch_id)
        if img is None:
            return
        self.queue_panel.default_bg = self.canvas.majority
        self.queue_panel.add_card_with_snip(img)
        tooltip("Snip sent to a new card in the queue", parent=self)

    def _on_patch_dropped_to_card(self, card_id: int, patch_id: str) -> bool:
        card = self.queue_panel.queue.card_by_id(card_id)
        if card is None:
            return False
        img = self.canvas.take_patch(patch_id)
        if img is None:
            return False
        card.add_snip(img)
        return True

    def _start_next_clicked(self) -> None:
        if self.canvas.has_shapes():
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "Discard the current masks and start the next queued card?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        self._load_next_queued()

    def _load_next_queued(self) -> bool:
        card = self.queue_panel.pop_next()
        if card is None:
            return False
        self.canvas.set_image(card.compose())
        self.stack.setCurrentWidget(self.canvas)
        self.canvas.setFocus()
        self._update_swatch()
        self._refresh_counts()
        remaining = len(self.queue_panel.queue)
        tooltip(
            "Queued card loaded — draw boxes and Add Cards%s"
            % ("" if not remaining else " (%d more queued)" % remaining),
            parent=self,
        )
        return True

    # ------------------------------------------------------------------ OCR

    def _show_ocr_preview(self) -> None:
        if not self.canvas.has_image():
            showWarning("Snip a slide first.", parent=self, title=ADDON_NAME)
            return
        backend = ocr.available_backend(self.config)
        if backend == "none":
            QMessageBox.information(
                self,
                ADDON_NAME,
                "No OCR engine is available.\n\nOn Windows the built-in OCR "
                "is used automatically; elsewhere install Tesseract and set "
                "tesseract_path in the add-on config.",
            )
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            text = ocr.extract_text(self.canvas.bake_image(), self.config)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            showWarning("OCR failed: %s" % exc, parent=self, title=ADDON_NAME)
            return
        QApplication.restoreOverrideCursor()
        _remember_ocr(text)

        dlg = QDialog(self)
        dlg.setWindowTitle("Search text preview (%s OCR)" % backend)
        dlg.resize(560, 420)
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "This text is stored invisibly on each card so deck search can "
            "find it. Spot a misread? Add it to \"ocr_corrections\" in the "
            "add-on config (Tools → Add-ons → Snip Occlusion → Config), "
            'e.g. {"K80": "KBD"} — it will be fixed on all future cards.',
            dlg,
        )
        info.setWordWrap(True)
        lay.addWidget(info)
        box = QPlainTextEdit(dlg)
        box.setPlainText(text or "(nothing recognized)")
        box.setReadOnly(True)
        lay.addWidget(box, 1)
        close = QPushButton("Close", dlg)
        qconnect(close.clicked, dlg.accept)
        lay.addWidget(close)
        dlg.exec()

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
        verb = "save" if self.edit_note_id is not None else "create"
        self.count_label.setText(
            "Will %s <b>%d</b> card%s" % (verb, n, "" if n == 1 else "s")
        )
        self.add_btn.setEnabled(n > 0)
        self._update_swatch()

    def _open_text_card(self) -> None:
        self._set_view(True)

    def _show_help(self) -> None:
        QMessageBox.information(self, ADDON_NAME + " – shortcuts", _HELP_TEXT)

    # ------------------------------------------------------------- add cards

    def add_cards(self) -> None:
        if self.edit_note_id is not None:
            self._save_edits()
            return
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

        outside = self.canvas.patches_outside_image()
        if outside:
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "%d snip patch%s still sitting outside the slide and will "
                "be cut off in the saved image.\n\nAdd the cards anyway?"
                % (
                    len(outside),
                    " is" if len(outside) == 1 else "es are",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return

        baked = self.canvas.bake_image()

        # OCR the finished image so the cards are findable by deck search;
        # a failure must never block card creation
        search_text = ""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            search_text = ocr.extract_text(baked, self.config)
        except Exception as exc:
            tooltip("Cards added without search text (OCR failed: %s)" % exc,
                    parent=self, period=5000)
        finally:
            QApplication.restoreOverrideCursor()
        _remember_ocr(search_text)

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
            search_text,
        )
        mw.reset()
        tooltip("Added %d card%s" % (n, "" if n == 1 else "s"), parent=self)

        if self.config.get("close_after_add", False):
            self.accept()
            return
        # clear the workspace for the next snip (undo-able)
        self.canvas.push_undo()
        self.canvas.shapes = []
        self.canvas.selection = set()
        self.canvas._emit_changed()
        self.canvas.setFocus()
        # queued cards flow in automatically once the slide is done
        if self.queue_panel.has_cards():
            self._load_next_queued()

    # ---------------------------------------------------------------- close

    def closeEvent(self, event) -> None:
        losses = []
        if self.canvas.has_shapes():
            losses.append("the current masks")
        if self.queue_panel.has_cards():
            losses.append(
                "%d queued card%s"
                % (
                    len(self.queue_panel.queue),
                    "" if len(self.queue_panel.queue) == 1 else "s",
                )
            )
        if losses:
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "Close and discard %s?" % " and ".join(losses),
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


def open_edit_dialog(note_id: int) -> None:
    """Open the editor on an existing Snip Occlusion note (from the note
    editor's ✂ button)."""
    if mw.col is None:
        return
    note = mw.col.get_note(note_id)
    if not notes_mod.is_occlusion_note(note):
        showWarning(
            "This is not a Snip Occlusion card — the ✂ button only edits "
            "cards created by this add-on.",
            title=ADDON_NAME,
        )
        return
    dlg = SnipOcclusionDialog(mw, note_id=note_id)
    mw._snip_occlusion_edit_dialog = dlg  # keep a reference (GC gotcha)
    dlg.show()


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
