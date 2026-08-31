"""The text card editor: Front, Back, Notes - plus AI-suggested cards.

TextCardPanel is the reusable editor widget. It lives in two places:

- Embedded in the main Snip Occlusion window (the "Text Editor" view,
  toggled at the top). There it also shows the AI suggestions panel,
  which fills itself the moment suggestions are ready - generation
  starts when the snip is loaded, so no button press is needed.
- Wrapped in TextCardDialog, a small standalone window with just the
  card fields: opened by "Use →" on a suggestion (prefilled), or by
  Ctrl+Shift+T outside the main window.

Formatting is just bold / italic / underline / font size, and one button
pulls the OCR text of your most recent snip onto the front.
"""

from __future__ import annotations

import re

from aqt import mw
from aqt.utils import showWarning, tooltip

from .qtshim import *  # noqa: F401,F403
from . import notes as notes_mod
from . import qgen, qgen_bakeoff, qgen_doc, qgen_feedback, qgen_prefetch
from .consts import ADDON_NAME
from .dialog import _STYLE, get_config, get_previous_snip_text

_SIZES = ["10", "12", "14", "16", "18", "20", "24", "28", "32"]


def _body_html(edit: QTextEdit) -> str:
    """The editor's content as field-ready HTML ('' when empty)."""
    if not edit.toPlainText().strip():
        return ""
    m = re.search(r"<body[^>]*>(.*)</body>", edit.toHtml(), re.S)
    return (m.group(1) if m else edit.toHtml()).strip()


class TextCardPanel(QWidget):
    def __init__(
        self,
        parent=None,
        with_suggestions: bool = False,
        standalone_shortcuts: bool = False,
    ):
        super().__init__(parent)
        self.with_suggestions = with_suggestions
        self._active_edit: QTextEdit | None = None
        self._shown_state = None  # the prefetch whose cards are displayed
        self._busy = False
        self._doc_job = 0  # incremented to cancel a pasted-text run
        self._doc_running = False
        self._undo_stack: list = []  # (card, verdict|None, row index)
        self._batch_id = 0  # bumped when the row list is replaced
        self.added_any = False  # did add_card() succeed at least once
        self._source_windows: list = []  # open 🔎 viewers (GC guard)
        self._build_ui(standalone_shortcuts)

    def _build_ui(self, standalone_shortcuts: bool) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

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
        lay.addLayout(deck_row)

        # --- AI suggestions panel (embedded Text Editor view only)
        if self.with_suggestions:
            self.suggest_panel = QWidget(self)
            panel_lay = QVBoxLayout(self.suggest_panel)
            panel_lay.setContentsMargins(0, 0, 0, 0)
            panel_lay.setSpacing(4)
            title_row = QHBoxLayout()
            title_row.addWidget(
                QLabel("<b>✨ Suggested cards</b>", self)
            )
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
            # suggestions sit above the editor in a splitter: they open at
            # full height (all cards visible, editor pushed down) and the
            # divider drags up to shrink them, like resizing a box
            editor_host = QWidget(self)
            edit_lay = QVBoxLayout(editor_host)
            edit_lay.setContentsMargins(0, 0, 0, 0)
            edit_lay.setSpacing(8)
            self.vsplit = QSplitter(Qt.Orientation.Vertical, self)
            self.vsplit.setHandleWidth(7)
            self.vsplit.setChildrenCollapsible(False)
            self.vsplit.addWidget(self.suggest_panel)
            self.vsplit.addWidget(editor_host)
            self.vsplit.setStretchFactor(0, 0)
            self.vsplit.setStretchFactor(1, 1)
            self._user_sized = False
            qconnect(self.vsplit.splitterMoved, self._splitter_dragged)
            lay.addWidget(self.vsplit, 1)
            lay = edit_lay  # the editor fields build into the lower pane
            self._set_suggest_status(
                "Snip a slide — suggestions appear here automatically."
            )

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

        # embedded under the suggestions splitter the edits accept being
        # squashed (suggestions get priority); standalone they keep a
        # comfortable minimum
        if self.with_suggestions:
            min_front, min_back, min_notes = 44, 44, 32
        else:
            min_front, min_back, min_notes = 110, 130, 70
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
        notes_mod.add_text_note(
            mw.col,
            self.deck_box.currentData(),
            front,
            _body_html(self.back),
            _body_html(self.notes),
        )
        mw.reset()
        self.added_any = True
        tooltip("Card added", parent=self)
        self.front.clear()
        self.back.clear()
        self.notes.clear()
        self.front.setFocus()

    # ------------------------------------------------------ AI suggestions

    def _set_suggest_status(self, text: str) -> None:
        if self.with_suggestions:
            self.suggest_status.setText(text)

    def _splitter_dragged(self, *_args) -> None:
        # once the user drags the divider, stop auto-sizing this batch
        self._user_sized = True

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

    def _fit_suggestions_if_auto(self) -> None:
        if self.with_suggestions and not self._user_sized:
            self._fit_suggestions()

    def _fit_suggestions(self) -> None:
        """Open the suggestions pane to show every card, no scrolling.

        The editor fields get pushed down; the splitter handle still
        drags up to shrink the pane (then it scrolls internally).
        """
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
        # never squash the editor below what it needs to stay usable
        bottom_min = max(
            self.vsplit.widget(1).minimumSizeHint().height(), 170
        )
        top = max(60, min(needed, total - bottom_min))
        self.vsplit.setSizes([top, total - top])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.with_suggestions:
            QTimer.singleShot(0, self._fit_suggestions_if_auto)

    def _show_card_source(self, card: dict) -> None:
        """The 🔎 view: full source text, matching sentences highlighted.

        Computed locally by word overlap - the model is never involved,
        so this costs nothing in generation speed.
        """
        source = card.get("_source") or ""
        if not source.strip():
            tooltip("No source text stored for this card.", parent=self)
            return
        from . import qgen_trace

        body, matches = qgen_trace.highlight_html(card, source)
        dlg = QDialog(self)
        dlg.setWindowTitle(ADDON_NAME + " — Where this card came from")
        dlg.setMinimumSize(480, 420)
        dlg.resize(640, 720)
        dlg.setStyleSheet(_STYLE)
        lay = QVBoxLayout(dlg)
        head = QLabel(
            "<b>Q:</b> %s<br><b>A:</b> %s"
            % (
                card.get("front", "").replace("<", "&lt;"),
                card.get("back", "").replace("<", "&lt;"),
            ),
            dlg,
        )
        head.setWordWrap(True)
        head.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lay.addWidget(head)
        if matches:
            note = "Highlighted: the sentences this card most likely came from."
        else:
            note = (
                "⚠ No closely matching sentence found — this card may not "
                "come from this text. Read with suspicion."
            )
        note_label = QLabel(
            "<span style='color:#8a8171'>%s</span>" % note, dlg
        )
        note_label.setWordWrap(True)
        lay.addWidget(note_label)
        browser = QTextBrowser(dlg)
        browser.setOpenExternalLinks(False)
        browser.setHtml(
            "<div style='color:#3d3929;font-size:13px;'>%s</div>" % body
        )
        lay.addWidget(browser, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, dlg
        )
        qconnect(buttons.rejected, dlg.close)
        qconnect(buttons.clicked, lambda _=None: dlg.close())
        lay.addWidget(buttons)
        # non-modal: keep it open beside the suggestions while reviewing
        self._source_windows[:] = [
            w for w in self._source_windows if w.isVisible()
        ]
        self._source_windows.append(dlg)
        dlg.show()

    def refresh_suggestions(self, force: bool = False) -> None:
        """Show the pre-generated suggestions for the current snip.

        Generation starts when the snip is loaded (qgen_prefetch); this
        just displays the result - with a loading note while it's still
        in flight. Safe to call repeatedly: showing the same prefetch
        twice is a no-op unless force=True (the ↻ button), which
        regenerates from scratch.
        """
        if not self.with_suggestions or self._busy:
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

    def _push_undo(self, card: dict, verdict, index: int) -> None:
        self._undo_stack.append((card, verdict, index))
        self.undo_btn.setEnabled(True)

    def _undo_verdict(self) -> None:
        if not self._undo_stack:
            return
        card, verdict, index = self._undo_stack.pop()
        self.undo_btn.setEnabled(bool(self._undo_stack))
        try:
            if verdict is not None:
                qgen_feedback.unrecord(card)
            # reverse the bake-off tally for whichever button it was
            tally_verdict = {
                None: "skip",
                qgen_feedback.KEPT: "great",
                qgen_feedback.BAD: "bad",
            }.get(verdict)
            if tally_verdict:
                qgen_bakeoff.tally(card, tally_verdict, undo=True)
        except Exception:
            pass
        self._add_card_row(card, index=index)
        QTimer.singleShot(0, self._fit_suggestions_if_auto)

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
        if card.get("_source"):
            src_btn = QToolButton(row)
            src_btn.setText("🔎")
            src_btn.setToolTip(
                "Show where this card came from — the full source text "
                "with the matching sentences highlighted"
            )
            qconnect(
                src_btn.clicked,
                lambda _=False: self._show_card_source(card),
            )
            row_lay.addWidget(src_btn)
        body = "<b>Q:</b> %s<br><b>A:</b> %s" % (
            front.replace("<", "&lt;"),
            back.replace("<", "&lt;"),
        )
        if notes:
            body += (
                "<br><span style='color:#8a8272;font-size:11px;'>%s</span>"
                % notes.replace("<", "&lt;")
            )
        if warn:
            body += (
                "<br><span style='color:#b3261e;font-size:11px;'>⚠ %s"
                "</span>" % warn.replace("<", "&lt;")
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
            )
            remove_row()

        def skip() -> None:
            try:
                qgen_bakeoff.tally(card, "skip")
            except Exception:
                pass
            self._push_undo(card, None, row_index())
            remove_row()

        def great() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.KEPT)
                qgen_bakeoff.tally(card, "great")
            except Exception:
                pass
            self._push_undo(card, qgen_feedback.KEPT, row_index())
            remove_row()

        def bad() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.BAD)
                qgen_bakeoff.tally(card, "bad")
            except Exception:
                pass
            self._push_undo(card, qgen_feedback.BAD, row_index())
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
            self._push_undo(card, qgen_feedback.BAD, row_index())
            remove_row()
            tooltip(
                "Noted — that reference is now blocklisted and will be "
                "stripped from future suggestions.",
                parent=self,
            )

        # left to right: use / don't use (no signal) / great, not using /
        # bad, not using
        for label, tip, cb, style in [
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
                "⚠",
                "It invented a reference (case, statute, year…) — tell "
                "me which, and it will be stripped from every future "
                "card. Also counts as Bad for the learning loop.",
                fake_ref,
                "color:#b3261e;",
            ),
        ]:
            btn = QPushButton(label, row)
            btn.setToolTip(tip)
            if style:
                btn.setStyleSheet("QPushButton{%s}" % style)
            qconnect(btn.clicked, lambda _=False, c=cb: c())
            row_lay.addWidget(btn)
        last = self.suggest_lay.count() - 1  # keep the stretch at the end
        if index is None or not (0 <= index < last):
            index = last
        self.suggest_lay.insertWidget(index, row)


class PoppedTextEditor(QDialog):
    """The full Text Editor (suggestions included) in its own window.

    For side-by-side work: snap this to one half of the screen and the
    source material to the other, and check the suggested cards'
    references against it while reviewing.
    """

    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle(ADDON_NAME + " — Text Editor")
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
        self.panel = TextCardPanel(
            self, with_suggestions=True, standalone_shortcuts=True
        )
        lay.addWidget(self.panel)

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


class TextCardDialog(QDialog):
    """Standalone window with just the card fields (no suggestions)."""

    def __init__(
        self,
        parent=None,
        front_text: str = "",
        back_text: str = "",
        notes_text: str = "",
        on_discard=None,
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
            self, with_suggestions=False, standalone_shortcuts=True
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
