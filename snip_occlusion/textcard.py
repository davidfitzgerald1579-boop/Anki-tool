"""Text-side pages: AI-suggested cards, and writing cards by hand.

Two widgets, matching the main window's three-view layout:

- SuggestionsPage ("Suggested Cards" view, also the ⧉ pop-out window):
  the AI suggestions at the top, and the source (OCR/pasted) text
  underneath. Clicking 🔎 on a card highlights, inline in that text,
  the sentences the card most likely came from - no popups.
- TextCardPanel ("Write Card" view, and the Use →/Ctrl+Shift+T window):
  Front/Back/Notes with simple formatting. In the main window it shows
  the source text at the top for reference; the standalone window is
  just the fields.
"""

from __future__ import annotations

import re

from aqt import mw
from aqt.utils import showWarning

from .qtshim import *  # noqa: F401,F403
from . import notes as notes_mod
from . import qgen, qgen_bakeoff, qgen_doc, qgen_feedback, qgen_prefetch
from .consts import ADDON_NAME
from .dialog import _STYLE, get_config, get_previous_snip_text
from .uitools import notify as tooltip

_SIZES = ["10", "12", "14", "16", "18", "20", "24", "28", "32"]


def _body_html(edit: QTextEdit) -> str:
    """The editor's content as field-ready HTML ('' when empty)."""
    if not edit.toPlainText().strip():
        return ""
    m = re.search(r"<body[^>]*>(.*)</body>", edit.toHtml(), re.S)
    return (m.group(1) if m else edit.toHtml()).strip()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


class TextCardPanel(QWidget):
    """Front/Back/Notes editor; optionally with the source text on top."""

    def __init__(
        self,
        parent=None,
        show_source: bool = False,
        standalone_shortcuts: bool = False,
    ):
        super().__init__(parent)
        self.show_source = show_source
        self._active_edit: QTextEdit | None = None
        self.added_any = False  # did add_card() succeed at least once
        self.on_added = None  # callback(front, back, notes) after an add
        self._src_user_sized = False
        self._build_ui(standalone_shortcuts)

    def _build_ui(self, standalone_shortcuts: bool) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        deck_row = QHBoxLayout()
        deck_row.addWidget(QLabel("Deck:", self))
        self.deck_box = QComboBox(self)
        try:
            current_id = mw.col.decks.get_current_id()
        except AttributeError:
            current_id = mw.col.decks.current()["id"]
        for i, entry in enumerate(mw.col.decks.all_names_and_ids()):
            self.deck_box.addItem(entry.name, entry.id)
            if entry.id == current_id:
                self.deck_box.setCurrentIndex(i)
        deck_row.addWidget(self.deck_box, 1)
        outer.addLayout(deck_row)

        if self.show_source:
            # source text on top, fields below, divider draggable
            source_host = QWidget(self)
            src_lay = QVBoxLayout(source_host)
            src_lay.setContentsMargins(0, 0, 0, 0)
            src_lay.setSpacing(4)
            src_lay.addWidget(
                QLabel(
                    "<b>📄 Source text</b> <span style='color:#8a8171'>"
                    "(from your snip or pasted lesson — select and copy "
                    "freely)</span>",
                    self,
                )
            )
            self.source_browser = QTextBrowser(self)
            self.source_browser.setMinimumHeight(80)
            self.source_browser.setPlaceholderText(
                "Snip a slide or paste a lesson — its text appears here."
            )
            src_lay.addWidget(self.source_browser)
            fields_host = QWidget(self)
            lay = QVBoxLayout(fields_host)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(8)
            self.vsplit = QSplitter(Qt.Orientation.Vertical, self)
            self.vsplit.setHandleWidth(7)
            self.vsplit.setChildrenCollapsible(False)
            self.vsplit.addWidget(source_host)
            self.vsplit.addWidget(fields_host)
            self.vsplit.setStretchFactor(0, 1)
            self.vsplit.setStretchFactor(1, 2)
            qconnect(self.vsplit.splitterMoved, self._src_splitter_dragged)
            outer.addWidget(self.vsplit, 1)
            min_front, min_back, min_notes = 44, 44, 32
        else:
            lay = outer
            min_front, min_back, min_notes = 110, 130, 70

        # --- formatting bar (applies to whichever box you're typing in)
        bar = QHBoxLayout()
        for label, tip, cb in [
            ("B", "Bold (Ctrl+B)", self._bold),
            ("I", "Italic (Ctrl+I)", self._italic),
            ("U", "Underline (Ctrl+U)", self._underline),
        ]:
            btn = QToolButton(self)
            btn.setText(label)
            btn.setToolTip(tip)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep typing focus
            f = btn.font()
            if label == "B":
                f.setBold(True)
            elif label == "I":
                f.setItalic(True)
            else:
                f.setUnderline(True)
            btn.setFont(f)
            qconnect(btn.clicked, lambda _=False, c=cb: c())
            bar.addWidget(btn)
        bar.addSpacing(8)
        bar.addWidget(QLabel("Size:", self))
        self.size_box = QComboBox(self)
        self.size_box.addItems(_SIZES)
        self.size_box.setCurrentText("16")
        self.size_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        qconnect(self.size_box.textActivated, self._size)
        bar.addWidget(self.size_box)
        bar.addStretch(1)
        snip_btn = QPushButton("📋 Copy text from previous snip", self)
        snip_btn.setToolTip(
            "Insert the OCR text of your most recent snip into the Front"
        )
        qconnect(snip_btn.clicked, self._copy_previous_snip)
        bar.addWidget(snip_btn)
        lay.addLayout(bar)

        def make_edit(min_h: int) -> QTextEdit:
            edit = QTextEdit(self)
            edit.setMinimumHeight(min_h)
            edit.setAcceptRichText(True)
            edit.installEventFilter(self)
            font = edit.font()
            font.setPointSize(12)
            edit.setFont(font)
            return edit

        lay.addWidget(QLabel("<b>Front</b>", self))
        self.front = make_edit(min_front)
        lay.addWidget(self.front, 2)
        lay.addWidget(QLabel("<b>Back</b>", self))
        self.back = make_edit(min_back)
        lay.addWidget(self.back, 3)
        lay.addWidget(QLabel("Notes <span style='color:#8a8171'>(shown "
                             "small under the answer)</span>", self))
        self.notes = make_edit(min_notes)
        lay.addWidget(self.notes, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.add_btn = QPushButton("Add Card", self)
        self.add_btn.setObjectName("addBtn")
        self.add_btn.setDefault(False)
        self.add_btn.setAutoDefault(False)
        qconnect(self.add_btn.clicked, self.add_card)
        bottom.addWidget(self.add_btn)
        lay.addLayout(bottom)

        shortcuts = [
            ("Ctrl+B", self._bold),
            ("Ctrl+I", self._italic),
            ("Ctrl+U", self._underline),
        ]
        if standalone_shortcuts:
            # embedded, the main window routes Ctrl+Return by active view
            shortcuts.append(("Ctrl+Return", self.add_card))
        for seq, cb in shortcuts:
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            qconnect(sc.activated, cb)

    def set_source_text(self, text: str) -> None:
        if not self.show_source:
            return
        paragraphs = [
            _escape(" ".join(p.split()))
            for p in re.split(r"\n\s*\n", text or "")
            if p.strip()
        ]
        self.source_browser.setHtml(
            "<div style='color:#3d3929;font-size:13px;'>%s</div>"
            % "<br><br>".join(paragraphs)
        )
        self._src_user_sized = False  # new text auto-sizes again
        QTimer.singleShot(0, self._fit_source)

    def _src_splitter_dragged(self, *_args) -> None:
        self._src_user_sized = True  # a manual drag takes over

    def _fit_source(self) -> None:
        """Size the source pane to show the WHOLE text, no scrolling.

        The fields below compress as needed (they have small minimums);
        only when the text is taller than the window itself does the
        pane cap out and scroll. A manual splitter drag takes over
        until the next source text arrives.
        """
        if not self.show_source or self._src_user_sized:
            return
        sizes = self.vsplit.sizes()
        total = sum(sizes)
        if total <= 0:
            return  # not laid out yet; showEvent refits
        doc = self.source_browser.document()
        doc.setTextWidth(max(60, self.source_browser.viewport().width()))
        needed = int(doc.size().height()) + 20
        host_lay = self.vsplit.widget(0).layout()
        item = host_lay.itemAt(0)  # the "Source text" label
        if item is not None:
            needed += item.sizeHint().height() + host_lay.spacing()
        bottom_min = max(
            self.vsplit.widget(1).minimumSizeHint().height(), 200
        )
        top = max(60, min(needed, total - bottom_min))
        self.vsplit.setSizes([top, total - top])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.show_source:
            QTimer.singleShot(0, self._fit_source)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.show_source:
            # width changes reflow the text, changing its height
            QTimer.singleShot(0, self._fit_source)

    def focus_front(self) -> None:
        self.front.setFocus()

    def has_unsaved_text(self) -> bool:
        return any(
            e.toPlainText().strip()
            for e in (self.front, self.back, self.notes)
        )

    # ---------------------------------------------------------- formatting

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.FocusIn and isinstance(obj, QTextEdit):
            self._active_edit = obj
        return super().eventFilter(obj, event)

    def _target(self) -> QTextEdit:
        w = QApplication.focusWidget()
        if isinstance(w, QTextEdit):
            return w
        return self._active_edit or self.front

    def _bold(self) -> None:
        e = self._target()
        heavy = e.fontWeight() > QFont.Weight.Normal
        e.setFontWeight(
            QFont.Weight.Normal if heavy else QFont.Weight.Bold
        )
        e.setFocus()

    def _italic(self) -> None:
        e = self._target()
        e.setFontItalic(not e.fontItalic())
        e.setFocus()

    def _underline(self) -> None:
        e = self._target()
        e.setFontUnderline(not e.fontUnderline())
        e.setFocus()

    def _size(self, value: str) -> None:
        e = self._target()
        try:
            e.setFontPointSize(float(value))
        except ValueError:
            pass
        e.setFocus()

    # ------------------------------------------------------------- actions

    def _copy_previous_snip(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            text = get_previous_snip_text()
        finally:
            QApplication.restoreOverrideCursor()
        if not text:
            tooltip(
                "No snip text available yet — snip a slide (or add its "
                "cards) first.",
                parent=self,
            )
            return
        cursor = self.front.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.front.toPlainText().strip():
            cursor.insertText("\n")
        cursor.insertText(text)
        self.front.setTextCursor(cursor)
        self.front.setFocus()

    def add_card(self) -> None:
        front = _body_html(self.front)
        if not front:
            showWarning(
                "The front of the card is empty.",
                parent=self,
                title=ADDON_NAME,
            )
            return
        plain = (
            self.front.toPlainText().strip(),
            self.back.toPlainText().strip(),
            self.notes.toPlainText().strip(),
        )
        notes_mod.add_text_note(
            mw.col,
            self.deck_box.currentData(),
            front,
            _body_html(self.back),
            _body_html(self.notes),
        )
        mw.reset()
        self.added_any = True
        if self.on_added is not None:
            try:
                self.on_added(*plain)
            except Exception:
                pass
        tooltip("Card added", parent=self)
        self.front.clear()
        self.back.clear()
        self.notes.clear()
        self.front.setFocus()


class SuggestionsPage(QWidget):
    """AI suggestions on top; the source text underneath.

    🔎 on a card highlights, inline in the source text below, the
    sentences the card (and separately its Notes line) most likely came
    from - yellow for question/answer, orange for notes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shown_state = None  # the prefetch whose cards are displayed
        self._busy = False
        self._doc_job = 0  # incremented to cancel a pasted-text run
        self._doc_running = False
        self._undo_stack: list = []  # (card, verdict|None, row index)
        self._batch_id = 0  # bumped when the row list is replaced
        self._current_source = ""
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self.suggest_panel = QWidget(self)
        panel_lay = QVBoxLayout(self.suggest_panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("<b>✨ Suggested cards</b>", self))
        self.suggest_status = QLabel("", self)
        self.suggest_status.setStyleSheet("color:#8a8171;")
        title_row.addWidget(self.suggest_status, 1)
        self.undo_btn = QToolButton(self)
        self.undo_btn.setText("↶")
        self.undo_btn.setToolTip(
            "Undo the last Skip / ★ Great / ✗ Bad — bring the card "
            "back and forget the verdict"
        )
        self.undo_btn.setEnabled(False)
        qconnect(self.undo_btn.clicked, self._undo_verdict)
        title_row.addWidget(self.undo_btn)
        paste_btn = QPushButton("📄 Paste text…", self)
        paste_btn.setToolTip(
            "Paste a whole lesson or element text; cards are "
            "generated section by section and stream in above"
        )
        qconnect(paste_btn.clicked, self._open_paste_dialog)
        title_row.addWidget(paste_btn)
        self.regen_btn = QToolButton(self)
        self.regen_btn.setText("↻")
        self.regen_btn.setToolTip(
            "Regenerate suggestions from the current snip"
        )
        qconnect(self.regen_btn.clicked, self._regen_clicked)
        title_row.addWidget(self.regen_btn)
        panel_lay.addLayout(title_row)
        self.suggest_scroll = QScrollArea(self)
        self.suggest_scroll.setWidgetResizable(True)
        self.suggest_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.suggest_scroll.setMinimumHeight(40)
        inner = QWidget(self)
        inner.setStyleSheet("background:transparent;")
        self.suggest_lay = QVBoxLayout(inner)
        self.suggest_lay.setContentsMargins(0, 0, 4, 0)
        self.suggest_lay.setSpacing(6)
        self.suggest_lay.addStretch(1)
        self.suggest_scroll.setWidget(inner)
        panel_lay.addWidget(self.suggest_scroll)

        # the source text lives directly below the suggestions
        source_host = QWidget(self)
        src_lay = QVBoxLayout(source_host)
        src_lay.setContentsMargins(0, 0, 0, 0)
        src_lay.setSpacing(4)
        self.source_legend = QLabel(
            "<b>📄 Source text</b> <span style='color:#8a8171'>— click "
            "🔎 on a card to highlight where it came from.</span>",
            self,
        )
        self.source_legend.setWordWrap(True)
        src_lay.addWidget(self.source_legend)
        self.source_browser = QTextBrowser(self)
        self.source_browser.setMinimumHeight(90)
        self.source_browser.setPlaceholderText(
            "Snip a slide or paste a lesson — its text appears here."
        )
        src_lay.addWidget(self.source_browser)

        self.vsplit = QSplitter(Qt.Orientation.Vertical, self)
        self.vsplit.setHandleWidth(7)
        self.vsplit.setChildrenCollapsible(False)
        self.vsplit.addWidget(self.suggest_panel)
        self.vsplit.addWidget(source_host)
        self.vsplit.setStretchFactor(0, 0)
        self.vsplit.setStretchFactor(1, 1)
        self._user_sized = False
        qconnect(self.vsplit.splitterMoved, self._splitter_dragged)
        outer.addWidget(self.vsplit, 1)
        self._set_suggest_status(
            "Snip a slide — suggestions appear here automatically."
        )

    # ------------------------------------------------------- source view

    def current_source(self) -> str:
        return self._current_source

    def set_source_text(self, text: str) -> None:
        """Show plain source text (no highlights) and remember it."""
        self._current_source = text or ""
        paragraphs = [
            _escape(" ".join(p.split()))
            for p in re.split(r"\n\s*\n", self._current_source)
            if p.strip()
        ]
        self.source_browser.setHtml(
            "<div style='color:#3d3929;font-size:13px;'>%s</div>"
            % "<br><br>".join(paragraphs)
        )
        self.source_legend.setText(
            "<b>📄 Source text</b> <span style='color:#8a8171'>— click "
            "🔎 on a card to highlight where it came from.</span>"
        )

    def _show_card_source(self, card: dict) -> None:
        """🔎: highlight the card's origin inline in the browser below."""
        source = card.get("_source") or self._current_source
        if not source.strip():
            tooltip("No source text stored for this card.", parent=self)
            return
        from . import qgen_trace

        body, matches, notes_matches = qgen_trace.highlight_html(
            card, source
        )
        # anchor the first highlight so the browser scrolls right to it
        first = body.find("<span")
        if first != -1:
            body = body[:first] + "<a name='hit'></a>" + body[first:]
        parts = []
        if matches:
            parts.append(
                "<span style='%s'>&nbsp;yellow&nbsp;</span> = "
                "question/answer" % qgen_trace.HIGHLIGHT_STYLE
            )
        else:
            parts.append(
                "<span style='color:#b3261e'>⚠ no close match for the "
                "question/answer — read with suspicion</span>"
            )
        if card.get("notes"):
            if notes_matches:
                parts.append(
                    "<span style='%s'>&nbsp;orange&nbsp;</span> = the "
                    "Notes line" % qgen_trace.NOTE_HIGHLIGHT_STYLE
                )
            else:
                parts.append(
                    "<span style='color:#b3261e'>⚠ NOTHING matches the "
                    "Notes line — likely invented (flag it with "
                    "⚠ Ref)</span>"
                )
        self.source_legend.setText(
            "<b>📄 Source of</b> “%s” <span style='color:#8a8171'>· "
            "%s</span>"
            % (_escape(card.get("front", ""))[:80], " · ".join(parts))
        )
        self.source_browser.setHtml(
            "<div style='color:#3d3929;font-size:13px;'>%s</div>" % body
        )
        self.source_browser.scrollToAnchor("hit")

    # --------------------------------------------------------- status/fit

    def _set_suggest_status(self, text: str) -> None:
        self.suggest_status.setText(text)

    def _splitter_dragged(self, *_args) -> None:
        # once the user drags the divider, stop auto-sizing this batch
        self._user_sized = True

    def _fit_suggestions_if_auto(self) -> None:
        if not self._user_sized:
            self._fit_suggestions()

    def _fit_suggestions(self) -> None:
        """Show every card without scrolling; the source pane shrinks."""
        sizes = self.vsplit.sizes()
        total = sum(sizes)
        if total <= 0:
            return  # not laid out yet (view not shown); showEvent refits
        inner = self.suggest_scroll.widget()
        if inner.layout() is not None:
            inner.layout().activate()
        needed = inner.sizeHint().height() + 6  # rows
        panel_lay = self.suggest_panel.layout()
        item = panel_lay.itemAt(0)  # title row
        if item is not None:
            needed += item.sizeHint().height() + panel_lay.spacing()
        bottom_min = 150  # keep a useful strip of source text visible
        top = max(60, min(needed, total - bottom_min))
        self.vsplit.setSizes([top, total - top])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_suggestions_if_auto)

    # -------------------------------------------- pasted-text generation

    def _regen_clicked(self) -> None:
        if self._doc_running:
            # the ↻ button reads ■ while a pasted-text run is going
            self._doc_job += 1  # workers see the change and bail
            self._doc_finish("stopped")
            return
        self.refresh_suggestions(force=True)

    def _open_paste_dialog(self) -> None:
        if self._busy or self._doc_running:
            tooltip("Still generating — one moment.", parent=self)
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(ADDON_NAME + " — Cards from pasted text")
        dlg.setMinimumSize(560, 420)
        dlg.setStyleSheet(_STYLE)
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "Paste a whole lesson or element text below. It is split "
            "into sections and the cards stream in above as each "
            "section finishes — start reviewing them straight away.",
            dlg,
        )
        info.setWordWrap(True)
        lay.addWidget(info)
        edit = QPlainTextEdit(dlg)
        edit.setPlaceholderText("Paste the text here…")
        lay.addWidget(edit, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            dlg,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Generate cards"
        )
        qconnect(buttons.accepted, dlg.accept)
        qconnect(buttons.rejected, dlg.reject)
        lay.addWidget(buttons)
        edit.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = edit.toPlainText().strip()
        if len(text) < 40:
            tooltip("Paste a longer piece of text first.", parent=self)
            return
        self._start_doc_job(text)

    def _start_doc_job(self, text: str) -> None:
        config = get_config()
        chunks = qgen_doc.split_into_chunks(text)
        if not chunks:
            tooltip("Nothing to work with in that text.", parent=self)
            return
        self._doc_job += 1
        job = self._doc_job
        self._doc_running = True
        self._busy = True  # blocks snip refreshes while this runs
        self._user_sized = False
        self._clear_rows()
        self.set_source_text(text)
        self.regen_btn.setText("■")
        self.regen_btn.setToolTip("Stop generating")
        self._set_suggest_status("section 1/%d…" % len(chunks))

        def work():
            for i, chunk in enumerate(chunks):
                if self._doc_job != job:
                    return
                try:
                    cards = qgen_bakeoff.generate(
                        chunk, config, source="document"
                    )
                except qgen.EmptyReplyError:
                    cards = []  # a section with nothing card-worthy is fine
                except qgen.QGenError as exc:
                    mw.taskman.run_on_main(
                        lambda m=str(exc): self._doc_finish(
                            "failed — ↻ to retry", m
                        )
                    )
                    return
                mw.taskman.run_on_main(
                    lambda c=cards, done_count=i + 1: self._doc_progress(
                        job, c, done_count, len(chunks)
                    )
                )
            mw.taskman.run_on_main(lambda: self._doc_finish(""))

        def done(future) -> None:
            try:
                future.result()
            except Exception as exc:
                self._doc_finish("failed — ↻ to retry", str(exc))

        mw.taskman.run_in_background(work, done)

    def _doc_progress(
        self, job: int, cards: list, done_count: int, total: int
    ) -> None:
        if job != self._doc_job:
            return
        for card in cards:
            self._add_card_row(card)
        if done_count < total:
            self._set_suggest_status(
                "section %d/%d…" % (done_count + 1, total)
            )
        QTimer.singleShot(0, self._fit_suggestions_if_auto)

    def _doc_finish(self, status: str, detail: str | None = None) -> None:
        if not self._doc_running:
            return
        self._doc_running = False
        self._busy = False
        self.regen_btn.setText("↻")
        self.regen_btn.setToolTip(
            "Regenerate suggestions from the current snip"
        )
        self._set_suggest_status(status)
        # mark the current snip's prefetch as already shown so merely
        # toggling views doesn't clobber these results; a NEW snip (or ↻)
        # still takes the panel over
        self._shown_state = qgen_prefetch.current()
        if detail:
            tooltip("Card generation: %s" % detail, parent=self, period=6000)

    # ------------------------------------------------------ AI suggestions

    def refresh_suggestions(self, force: bool = False) -> None:
        """Show the pre-generated suggestions for the current snip.

        Generation starts when the snip is loaded (qgen_prefetch); this
        just displays the result - with a loading note while it's still
        in flight. Safe to call repeatedly: showing the same prefetch
        twice is a no-op unless force=True (the ↻ button), which
        regenerates from scratch.
        """
        if self._busy:
            return
        config = get_config()
        state = qgen_prefetch.current()
        if state is None and not force:
            return  # nothing snipped yet; keep the hint text
        if state is not None and state is self._shown_state and not force:
            return  # already showing (or loading) this snip's cards
        fallback_text = ""
        if force and (state is None or not state.text.strip()):
            # OCR touches the canvas widget: main thread only
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                fallback_text = get_previous_snip_text()
            finally:
                QApplication.restoreOverrideCursor()
            if state is None and not fallback_text:
                self._set_suggest_status(
                    "no snip yet — snip a slide first"
                )
                return
        self._shown_state = state
        self._busy = True
        self._user_sized = False  # a fresh batch auto-sizes again
        self._clear_rows()
        self._set_suggest_status("generating on your machine…")

        def work():
            if force:
                text = (state.text if state else "").strip() or fallback_text
                if not text:
                    raise qgen.QGenError(
                        "No snip text available yet — snip a slide first."
                    )
                return qgen_bakeoff.generate(text, config)
            timeout = int(config.get("qgen_timeout_seconds") or 300) + 30
            try:
                return qgen_prefetch.wait_for_cards(state, timeout)
            except qgen.QGenError:
                # e.g. Ollama wasn't running when the snip landed but is
                # now - retry live before giving up
                if state.text.strip():
                    return qgen_bakeoff.generate(state.text, config)
                raise

        def done(future) -> None:
            self._busy = False
            try:
                cards = future.result()
            except Exception as exc:
                self._set_suggest_status("failed — ↻ to retry")
                tooltip("Suggestions: %s" % exc, parent=self, period=6000)
                return
            self._set_suggest_status("")
            self.set_source_text(
                (state.text if state else "").strip() or fallback_text
            )
            for card in cards:
                self._add_card_row(card)
            QTimer.singleShot(0, self._fit_suggestions_if_auto)

        mw.taskman.run_in_background(work, done)

    def _clear_rows(self) -> None:
        self._batch_id += 1  # invalidates undo entries and Use-returns
        self._undo_stack.clear()
        self.undo_btn.setEnabled(False)
        while self.suggest_lay.count() > 1:
            item = self.suggest_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _push_undo(
        self,
        row_card: dict,
        index: int,
        unrecord_card=None,
        tally: str | None = None,
    ) -> None:
        """Remember how to reverse a verdict: which card comes back to
        the list, which feedback entry to forget, which tally to undo."""
        self._undo_stack.append((row_card, index, unrecord_card, tally))
        self.undo_btn.setEnabled(True)

    def _undo_verdict(self) -> None:
        if not self._undo_stack:
            return
        row_card, index, unrecord_card, tally = self._undo_stack.pop()
        self.undo_btn.setEnabled(bool(self._undo_stack))
        try:
            if unrecord_card is not None:
                qgen_feedback.unrecord(unrecord_card)
            if tally:
                qgen_bakeoff.tally(row_card, tally, undo=True)
        except Exception:
            pass
        self._add_card_row(row_card, index=index)
        QTimer.singleShot(0, self._fit_suggestions_if_auto)

    def _teach_correction(
        self, card: dict, corrected: dict, index: int
    ) -> None:
        """Record the user's corrected card as the lesson (no card added).

        The model's original is recorded nowhere - its style was fine,
        so no negative example - but the correction counts as "fixed"
        against the generating model in the bake-off.
        """
        try:
            qgen_feedback.record(corrected, qgen_feedback.KEPT)
            qgen_bakeoff.tally(card, "fixed")
        except Exception:
            pass
        self._push_undo(card, index, unrecord_card=corrected, tally="fixed")
        tooltip(
            "Corrected version learned — future cards imitate yours.",
            parent=self,
        )

    def _open_fix_dialog(self, card: dict, index: int) -> bool:
        """✎ Fix: edit the card's content purely to teach the AI.

        Returns True when a correction was saved (the row then clears).
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(ADDON_NAME + " — Correct this card")
        dlg.setMinimumSize(520, 420)
        dlg.setStyleSheet(_STYLE)
        lay = QVBoxLayout(dlg)
        info = QLabel(
            "Fix the content below (the style stays). Your corrected "
            "version is saved as an example for future generations — "
            "no flashcard is added.",
            dlg,
        )
        info.setWordWrap(True)
        lay.addWidget(info)
        edits = {}
        for key, label in (
            ("front", "Front"),
            ("back", "Back"),
            ("notes", "Notes (optional)"),
        ):
            lay.addWidget(QLabel("<b>%s</b>" % label, dlg))
            edit = QPlainTextEdit(dlg)
            edit.setPlainText(card.get(key, ""))
            edit.setMinimumHeight(56)
            lay.addWidget(edit, 1)
            edits[key] = edit
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            dlg,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Teach corrected version"
        )
        qconnect(buttons.accepted, dlg.accept)
        qconnect(buttons.rejected, dlg.reject)
        lay.addWidget(buttons)
        edits["front"].setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        corrected = {
            "front": edits["front"].toPlainText().strip(),
            "back": edits["back"].toPlainText().strip(),
        }
        notes_value = edits["notes"].toPlainText().strip()
        if notes_value:
            corrected["notes"] = notes_value
        if not corrected["front"] or not corrected["back"]:
            tooltip("Front and Back can't be empty.", parent=self)
            return False
        if (
            corrected["front"] == card.get("front", "")
            and corrected["back"] == card.get("back", "")
            and notes_value == card.get("notes", "")
        ):
            tooltip(
                "No changes made — use ★ Great if the card is fine "
                "as-is.",
                parent=self,
            )
            return False
        self._teach_correction(card, corrected, index)
        return True

    def _add_suggestion_row(
        self,
        front: str,
        back: str,
        notes: str = "",
        index=None,
        model: str = "",
        warn: str = "",
    ) -> None:
        """Compatibility wrapper: build the card dict and add its row."""
        card = {"front": front, "back": back}
        if notes:
            card["notes"] = notes
        if model:
            card["_model"] = model
        if warn:
            card["_warn"] = warn
        self._add_card_row(card, index=index)

    def _add_card_row(self, source_card: dict, index=None) -> None:
        card = dict(source_card)
        front = card.get("front", "")
        back = card.get("back", "")
        notes = card.get("notes", "")
        warn = card.get("_warn", "")
        row = QFrame(self)
        row.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e3dcd0;"
            "border-radius:8px;}"
        )
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(8, 6, 8, 6)
        body = "<b>Q:</b> %s<br><b>A:</b> %s" % (
            _escape(front),
            _escape(back),
        )
        if notes:
            body += (
                "<br><span style='color:#8a8272;font-size:11px;'>%s</span>"
                % _escape(notes)
            )
        if warn:
            body += (
                "<br><span style='color:#b3261e;font-size:11px;'>⚠ %s"
                "</span>" % _escape(warn)
            )
        text = QLabel(body, row)
        text.setWordWrap(True)
        # the preview text is selectable, so references etc. can be
        # copied out and checked against the source material
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        row_lay.addWidget(text, 1)

        def row_index() -> int:
            return max(0, self.suggest_lay.indexOf(row))

        def remove_row() -> None:
            row.setParent(None)
            row.deleteLater()
            # shrink back to fit the remaining cards (unless hand-sized)
            QTimer.singleShot(0, self._fit_suggestions_if_auto)

        def use() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.KEPT)
                qgen_bakeoff.tally(card, "use")
            except Exception:
                pass
            batch = self._batch_id
            index = row_index()

            def on_discard() -> None:
                # the Use window was closed without adding: the card
                # comes back, and the "kept" verdict is forgotten so a
                # ✗ Bad afterwards is what the learning loop remembers
                try:
                    qgen_feedback.unrecord(card)
                    qgen_bakeoff.tally(card, "use", undo=True)
                except Exception:
                    pass
                if self._batch_id == batch:
                    self._add_card_row(card, index=index)
                    QTimer.singleShot(0, self._fit_suggestions_if_auto)
                    tooltip(
                        "Card returned to the suggestions — no longer "
                        "counted as kept.",
                        parent=self,
                    )

            open_text_card_dialog(
                front_text=front,
                back_text=back,
                notes_text=notes,
                on_discard=on_discard,
                original_card=card,
            )
            remove_row()

        def skip() -> None:
            try:
                qgen_bakeoff.tally(card, "skip")
            except Exception:
                pass
            self._push_undo(card, row_index(), tally="skip")
            remove_row()

        def great() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.KEPT)
                qgen_bakeoff.tally(card, "great")
            except Exception:
                pass
            self._push_undo(
                card, row_index(), unrecord_card=card, tally="great"
            )
            remove_row()

        def bad() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.BAD)
                qgen_bakeoff.tally(card, "bad")
            except Exception:
                pass
            self._push_undo(
                card, row_index(), unrecord_card=card, tally="bad"
            )
            remove_row()

        def fix() -> None:
            if self._open_fix_dialog(card, row_index()):
                remove_row()

        def fake_ref() -> None:
            detected = qgen._citations(
                " ".join([notes or "", back, front])
            )
            value, ok = QInputDialog.getText(
                self,
                ADDON_NAME,
                "Which reference did it invent? Paste/edit the exact "
                "text — it will be stripped from all future cards:",
                text=detected[0] if detected else "",
            )
            if not ok or not value.strip():
                return
            try:
                qgen_feedback.record_phantom(value)
                qgen_feedback.record(card, qgen_feedback.BAD)
                qgen_bakeoff.tally(card, "bad")
            except Exception:
                pass
            self._push_undo(
                card, row_index(), unrecord_card=card, tally="bad"
            )
            remove_row()
            tooltip(
                "Noted — that reference is now blocklisted and will be "
                "stripped from future suggestions.",
                parent=self,
            )

        def show_source() -> None:
            self._show_card_source(card)

        # buttons sit in a compact 2-wide, 3-tall grid so the card text
        # keeps most of the width even at half-screen
        grid = QGridLayout()
        grid.setSpacing(4)
        buttons = [
            (
                "Use →",
                "Open this card in its own window to tweak and add — and "
                "teach the AI to write more like this",
                use,
                "",
            ),
            (
                "Skip",
                "Discard — you just don't want this card (teaches the AI "
                "nothing)",
                skip,
                "",
            ),
            (
                "★ Great",
                "Not using this card, but it's well written — teach the "
                "AI to write more like this",
                great,
                "color:#2e7d32;",
            ),
            (
                "✗ Bad",
                "Discard — this card is badly written; teach the AI to "
                "write less like this",
                bad,
                "color:#b3261e;",
            ),
            (
                "⚠ Ref",
                "It invented a reference (case, statute, year…) — tell "
                "me which, and it will be stripped from every future "
                "card. Also counts as Bad for the learning loop.",
                fake_ref,
                "color:#b3261e;",
            ),
            (
                "✎ Fix",
                "The style is right but the content is wrong — correct "
                "it, and the AI learns YOUR version instead. No "
                "flashcard is added.",
                fix,
                "color:#8a5a00;",
            ),
        ]
        if card.get("_source"):
            buttons.append(
                (
                    "🔎",
                    "Highlight, in the source text below, the sentences "
                    "this card most likely came from",
                    show_source,
                    "",
                )
            )
        for i, (label, tip, cb, style) in enumerate(buttons):
            btn = QPushButton(label, row)
            btn.setToolTip(tip)
            css = "QPushButton{padding:4px 8px;%s}" % style
            btn.setStyleSheet(css)
            qconnect(btn.clicked, lambda _=False, c=cb: c())
            grid.addWidget(btn, i // 2, i % 2)
        row_lay.addLayout(grid)
        row_lay.setAlignment(grid, Qt.AlignmentFlag.AlignTop)
        last = self.suggest_lay.count() - 1  # keep the stretch at the end
        if index is None or not (0 <= index < last):
            index = last
        self.suggest_lay.insertWidget(index, row)


class PoppedTextEditor(QDialog):
    """The Suggested Cards page in its own window.

    For side-by-side work: snap this to one half of the screen and the
    source material to the other, and check the suggested cards'
    references against it while reviewing.
    """

    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle(ADDON_NAME + " — Suggested Cards")
        self.setMinimumSize(520, 560)
        self.resize(680, 880)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self.panel = SuggestionsPage(self)
        lay.addWidget(self.panel)


class TextCardDialog(QDialog):
    """Standalone window with just the card fields (no suggestions)."""

    def __init__(
        self,
        parent=None,
        front_text: str = "",
        back_text: str = "",
        notes_text: str = "",
        on_discard=None,
        original_card=None,
    ):
        super().__init__(parent or mw)
        self._on_discard = on_discard
        self.setWindowTitle(ADDON_NAME + " — Text Card")
        self.setMinimumSize(560, 560)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(_STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        self.panel = TextCardPanel(
            self, show_source=False, standalone_shortcuts=True
        )
        lay.addWidget(self.panel)
        if front_text:
            self.panel.front.insertPlainText(front_text)
        if back_text:
            self.panel.back.insertPlainText(back_text)
        if notes_text:
            self.panel.notes.insertPlainText(notes_text)
        if front_text or back_text:
            self.panel.back.setFocus()
        else:
            self.panel.focus_front()
        if original_card:
            # the learning loop should remember the card AS ADDED, not
            # as suggested: if the user corrects wrong content before
            # adding, the corrected version replaces the original in
            # the kept-examples store
            orig = dict(original_card)

            def learn_corrected(front, back, notes) -> None:
                self.panel.on_added = None  # first add only
                edited = {"front": front, "back": back}
                if notes:
                    edited["notes"] = notes
                if (
                    edited["front"] == orig.get("front", "")
                    and edited["back"] == orig.get("back", "")
                    and notes == orig.get("notes", "")
                ):
                    return  # unchanged - the original example stands
                try:
                    from . import qgen_feedback

                    qgen_feedback.unrecord(orig)
                    qgen_feedback.record(edited, qgen_feedback.KEPT)
                except Exception:
                    pass

            self.panel.on_added = learn_corrected

    def closeEvent(self, event) -> None:
        if self.panel.has_unsaved_text():
            resp = QMessageBox.question(
                self,
                ADDON_NAME,
                "Close and discard the unsaved card?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
        # closed without ever adding: hand the card back to the caller
        # (the suggestions panel restores it and forgets the verdict)
        if self._on_discard is not None and not self.panel.added_any:
            try:
                self._on_discard()
            except Exception:
                pass


def open_text_card_dialog(
    front_text: str = "",
    back_text: str = "",
    notes_text: str = "",
    on_discard=None,
    original_card=None,
) -> None:
    if mw.col is None:
        showWarning("Open a profile first.", title=ADDON_NAME)
        return
    if not front_text and not back_text:
        # the plain dialog is a singleton; prefilled ones (from AI
        # suggestions) each open their own window
        existing = getattr(mw, "_snip_occlusion_text_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
    dlg = TextCardDialog(
        mw,
        front_text=front_text,
        back_text=back_text,
        notes_text=notes_text,
        on_discard=on_discard,
        original_card=original_card,
    )
    if not front_text and not back_text:
        mw._snip_occlusion_text_dialog = dlg  # keep a reference (GC gotcha)
    else:
        refs = getattr(mw, "_snip_occlusion_text_dialogs", None)
        if refs is None:
            refs = mw._snip_occlusion_text_dialogs = []
        refs[:] = [d for d in refs if d.isVisible()]
        refs.append(dlg)
    dlg.show()
