"""A deliberately simple text card: Front, Back, Notes.

For the facts you'd rather phrase yourself than occlude. Formatting is
just bold / italic / underline / font size, and one button pulls the OCR
text of your most recent snip onto the front.
"""

from __future__ import annotations

import re

from aqt import mw
from aqt.utils import showWarning, tooltip

from .qtshim import *  # noqa: F401,F403
from . import notes as notes_mod
from . import qgen, qgen_feedback, qgen_prefetch
from .consts import ADDON_NAME
from .dialog import _STYLE, get_config, get_previous_snip_text

_SIZES = ["10", "12", "14", "16", "18", "20", "24", "28", "32"]


def _body_html(edit: QTextEdit) -> str:
    """The editor's content as field-ready HTML ('' when empty)."""
    if not edit.toPlainText().strip():
        return ""
    m = re.search(r"<body[^>]*>(.*)</body>", edit.toHtml(), re.S)
    return (m.group(1) if m else edit.toHtml()).strip()


class TextCardDialog(QDialog):
    def __init__(
        self,
        parent=None,
        front_text: str = "",
        back_text: str = "",
        notes_text: str = "",
    ):
        super().__init__(parent or mw)
        self.setWindowTitle(ADDON_NAME + " — Text Card")
        self.setMinimumSize(560, 640)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setStyleSheet(_STYLE)
        self._active_edit: QTextEdit | None = None
        self._build_ui()
        if front_text:
            self.front.insertPlainText(front_text)
        if back_text:
            self.back.insertPlainText(back_text)
        if notes_text:
            self.notes.insertPlainText(notes_text)
        if front_text or back_text:
            self.back.setFocus()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
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
        self.suggest_btn = QPushButton("✨ Suggest cards", self)
        self.suggest_btn.setToolTip(
            "Ask a local AI model to draft question/answer cards from "
            "your most recent snip's text — then pick your favourites.\n"
            "Free and private: runs on your own computer via Ollama "
            "(install from ollama.com, then: ollama pull llama3.1:8b)."
        )
        qconnect(self.suggest_btn.clicked, self._suggest_cards)
        bar.addWidget(self.suggest_btn)
        lay.addLayout(bar)

        # --- AI suggestions panel (hidden until suggestions arrive)
        self.suggest_panel = QWidget(self)
        panel_lay = QVBoxLayout(self.suggest_panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(4)
        self.suggest_title = QLabel(
            "<b>Suggested cards</b> — pick your favourites; each opens in "
            "its own window", self
        )
        panel_lay.addWidget(self.suggest_title)
        self.suggest_scroll = QScrollArea(self)
        self.suggest_scroll.setWidgetResizable(True)
        self.suggest_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.suggest_scroll.setMinimumHeight(140)
        self.suggest_scroll.setMaximumHeight(240)
        inner = QWidget(self)
        inner.setStyleSheet("background:transparent;")
        self.suggest_lay = QVBoxLayout(inner)
        self.suggest_lay.setContentsMargins(0, 0, 4, 0)
        self.suggest_lay.setSpacing(6)
        self.suggest_lay.addStretch(1)
        self.suggest_scroll.setWidget(inner)
        panel_lay.addWidget(self.suggest_scroll)
        self.suggest_panel.hide()
        lay.addWidget(self.suggest_panel)

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
        self.front = make_edit(110)
        lay.addWidget(self.front, 2)
        lay.addWidget(QLabel("<b>Back</b>", self))
        self.back = make_edit(130)
        lay.addWidget(self.back, 3)
        lay.addWidget(QLabel("Notes <span style='color:#8a8171'>(shown "
                             "small under the answer)</span>", self))
        self.notes = make_edit(70)
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

        for seq, cb in [
            ("Ctrl+Return", self.add_card),
            ("Ctrl+B", self._bold),
            ("Ctrl+I", self._italic),
            ("Ctrl+U", self._underline),
        ]:
            qconnect(QShortcut(QKeySequence(seq), self).activated, cb)
        self.front.setFocus()

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

    # ------------------------------------------------------ AI suggestions

    def _suggest_cards(self) -> None:
        config = get_config()
        # generation usually started the moment the snip was loaded (see
        # qgen_prefetch) - clicking the button mostly just reveals it
        prefetched = qgen_prefetch.current()
        text = ""
        if prefetched is None:
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
        self.suggest_btn.setEnabled(False)
        self.suggest_btn.setText("✨ Generating…")

        def work():
            if prefetched is not None:
                timeout = int(config.get("qgen_timeout_seconds") or 300) + 30
                try:
                    return qgen_prefetch.wait_for_cards(prefetched, timeout)
                except qgen.QGenError:
                    # e.g. Ollama wasn't running when the snip landed but
                    # is now, or the snip had no readable text - retry
                    # live with the current (baked) snip text
                    if prefetched.text.strip():
                        return qgen.generate_cards(prefetched.text, config)
                    raise
            return qgen.generate_cards(text, config)

        def done(future) -> None:
            self.suggest_btn.setEnabled(True)
            self.suggest_btn.setText("✨ Suggest cards")
            try:
                cards = future.result()
            except qgen.QGenError as exc:
                showWarning(str(exc), parent=self, title=ADDON_NAME)
                return
            except Exception as exc:
                showWarning(
                    "Card suggestion failed: %s" % exc,
                    parent=self,
                    title=ADDON_NAME,
                )
                return
            self._show_suggestions(cards)

        mw.taskman.run_in_background(work, done)

    def _show_suggestions(self, cards: list) -> None:
        # clear previous suggestions, keep the trailing stretch
        while self.suggest_lay.count() > 1:
            item = self.suggest_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for card in cards:
            self._add_suggestion_row(
                card["front"], card["back"], card.get("notes", "")
            )
        self.suggest_panel.show()

    def _add_suggestion_row(
        self, front: str, back: str, notes: str = ""
    ) -> None:
        row = QFrame(self)
        row.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e3dcd0;"
            "border-radius:8px;}"
        )
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(8, 6, 8, 6)
        body = "<b>Q:</b> %s<br><b>A:</b> %s" % (
            front.replace("<", "&lt;"),
            back.replace("<", "&lt;"),
        )
        if notes:
            body += "<br><span style='color:#8a8272;font-size:11px;'>%s</span>" % (
                notes.replace("<", "&lt;")
            )
        text = QLabel(body, row)
        text.setWordWrap(True)
        row_lay.addWidget(text, 1)
        card = {"front": front, "back": back}
        if notes:
            card["notes"] = notes

        def remove_row() -> None:
            row.setParent(None)
            row.deleteLater()
            # hide the panel once every suggestion has been used/deleted
            if self.suggest_lay.count() <= 1:
                self.suggest_panel.hide()

        def use() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.KEPT)
            except Exception:
                pass
            open_text_card_dialog(
                front_text=front, back_text=back, notes_text=notes
            )
            remove_row()

        def discard_bad() -> None:
            try:
                qgen_feedback.record(card, qgen_feedback.BAD)
            except Exception:
                pass
            remove_row()

        use_btn = QPushButton("Use →", row)
        use_btn.setToolTip(
            "Open this card in a new window to tweak and add — and teach "
            "the AI to write more like this"
        )
        qconnect(use_btn.clicked, use)
        row_lay.addWidget(use_btn)
        del_btn = QPushButton("✕", row)
        del_btn.setFixedWidth(28)
        del_btn.setToolTip(
            "Discard — you just don't want this card (teaches the AI "
            "nothing)"
        )
        qconnect(del_btn.clicked, remove_row)
        row_lay.addWidget(del_btn)
        bad_btn = QPushButton("👎", row)
        bad_btn.setFixedWidth(28)
        bad_btn.setToolTip(
            "Discard — this is a badly written card; teach the AI to "
            "write less like this"
        )
        qconnect(bad_btn.clicked, discard_bad)
        row_lay.addWidget(bad_btn)
        self.suggest_lay.insertWidget(self.suggest_lay.count() - 1, row)

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
        tooltip("Card added", parent=self)
        self.front.clear()
        self.back.clear()
        self.notes.clear()
        self.front.setFocus()

    def closeEvent(self, event) -> None:
        if any(
            e.toPlainText().strip()
            for e in (self.front, self.back, self.notes)
        ):
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


def open_text_card_dialog(
    front_text: str = "", back_text: str = "", notes_text: str = ""
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
        mw, front_text=front_text, back_text=back_text, notes_text=notes_text
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
