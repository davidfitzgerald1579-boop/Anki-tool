"""Qt dialog for generating flashcards with a local LLM."""

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)
from aqt.utils import showInfo, showWarning, tooltip

from . import card_generator
from .llm_client import LLMError

ADDON_MODULE = __name__.split(".")[0]


def get_config():
    return mw.addonManager.getConfig(ADDON_MODULE) or {}


def show_dialog():
    dialog = GenerateDialog(mw)
    dialog.show()


class GenerateDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Generate AI Flashcards (Local LLM)")
        self.setMinimumSize(700, 600)
        self._build_ui()

    def _build_ui(self):
        config = get_config()
        layout = QVBoxLayout(self)

        provider = config.get("provider", "ollama")
        model = config.get("model", "llama3.1:8b")
        info = QLabel(
            "Using <b>%s</b> via <b>%s</b> &mdash; change this in "
            "Tools &rsaquo; Add-ons &rsaquo; Config." % (model, provider)
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("Paste your notes, textbook excerpt, or article:"))
        self.source_edit = QTextEdit()
        self.source_edit.setAcceptRichText(False)
        self.source_edit.setPlaceholderText(
            "Paste the material you want turned into flashcards..."
        )
        layout.addWidget(self.source_edit, stretch=2)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Deck:"))
        self.deck_combo = QComboBox()
        current_deck = mw.col.decks.current()["name"]
        for name_id in mw.col.decks.all_names_and_ids():
            self.deck_combo.addItem(name_id.name)
        index = self.deck_combo.findText(current_deck)
        if index >= 0:
            self.deck_combo.setCurrentIndex(index)
        options_row.addWidget(self.deck_combo, stretch=1)

        options_row.addWidget(QLabel("Max cards:"))
        self.max_cards_spin = QSpinBox()
        self.max_cards_spin.setRange(1, 100)
        self.max_cards_spin.setValue(int(config.get("max_cards", 15)))
        options_row.addWidget(self.max_cards_spin)

        self.generate_button = QPushButton("Generate")
        self.generate_button.clicked.connect(self.on_generate)
        options_row.addWidget(self.generate_button)
        layout.addLayout(options_row)

        layout.addWidget(QLabel("Preview (double-click a cell to edit):"))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Front", "Back"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, stretch=3)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self.add_button = QPushButton("Add cards to deck")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.on_add)
        buttons_row.addWidget(self.add_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons_row.addWidget(close_button)
        layout.addLayout(buttons_row)

    def on_generate(self):
        source_text = self.source_edit.toPlainText().strip()
        if not source_text:
            showWarning("Paste some source text first.", parent=self)
            return
        config = get_config()
        max_cards = self.max_cards_spin.value()

        self.generate_button.setEnabled(False)
        self.generate_button.setText("Generating...")

        op = QueryOp(
            parent=self,
            op=lambda col: card_generator.generate_cards(
                config, source_text, max_cards
            ),
            success=self.on_generated,
        )
        op.failure(self.on_generate_failed)
        op.with_progress("Asking the local LLM to write flashcards...")
        op.run_in_background()

    def on_generated(self, cards):
        self._reset_generate_button()
        self.table.setRowCount(0)
        for card in cards:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(card["front"]))
            self.table.setItem(row, 1, QTableWidgetItem(card["back"]))
        self.table.resizeRowsToContents()
        self.add_button.setEnabled(self.table.rowCount() > 0)
        tooltip("Generated %d cards - review them, then add." % len(cards), parent=self)

    def on_generate_failed(self, exc):
        self._reset_generate_button()
        if isinstance(exc, LLMError):
            showWarning(str(exc), parent=self, title="LLM error")
        else:
            showWarning(
                "Unexpected error while generating cards:\n%s" % exc, parent=self
            )

    def _reset_generate_button(self):
        self.generate_button.setEnabled(True)
        self.generate_button.setText("Generate")

    def on_add(self):
        cards = []
        for row in range(self.table.rowCount()):
            front_item = self.table.item(row, 0)
            back_item = self.table.item(row, 1)
            front = front_item.text().strip() if front_item else ""
            back = back_item.text().strip() if back_item else ""
            if front and back:
                cards.append((front, back))
        if not cards:
            showWarning("There are no cards to add.", parent=self)
            return

        config = get_config()
        deck_name = self.deck_combo.currentText()
        notetype_name = config.get("note_type", "Basic")
        notetype = mw.col.models.by_name(notetype_name)
        if notetype is None:
            showWarning(
                "Note type %r (from the add-on config) does not exist in "
                "this collection." % notetype_name,
                parent=self,
            )
            return
        field_names = [field["name"] for field in notetype["flds"]]
        if len(field_names) < 2:
            showWarning(
                "Note type %r needs at least two fields." % notetype_name,
                parent=self,
            )
            return

        deck_id = mw.col.decks.id(deck_name)
        added = 0
        for front, back in cards:
            note = mw.col.new_note(notetype)
            note[field_names[0]] = front
            note[field_names[1]] = back
            mw.col.add_note(note, deck_id)
            added += 1

        mw.reset()
        showInfo(
            "Added %d cards to deck %r." % (added, deck_name), parent=self
        )
        self.table.setRowCount(0)
        self.add_button.setEnabled(False)
