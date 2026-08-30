"""The 'New card queue' panel: lives at the bottom of the left toolbar.

Each queued card shows a live thumbnail and accepts snip patches dropped
onto it straight from the canvas. Cards can also be created empty, have
their background colour changed, or be deleted. 'Start next' loads the
first queued card into the editor as a fresh image to occlude.
"""

from __future__ import annotations

from .qtshim import *  # noqa: F401,F403
from .newcard import NewCardQueue, QueuedCard

PATCH_MIME = "application/x-snip-occlusion-patch"

_CARD_STYLE = """
QFrame#queueCard {
    background: #ffffff;
    border: 1px solid #e3dcd0;
    border-radius: 8px;
}
QFrame#queueCard[dropHover="true"] {
    border: 2px solid #d97757;
    background: #fdf1e8;
}
QToolButton {
    border: none;
    background: transparent;
    padding: 1px 4px;
    font-size: 9pt;
}
QToolButton:hover {
    background: #f6eee2;
    border-radius: 4px;
}
"""


class QueueCardWidget(QFrame):
    """One card in the queue: thumbnail + background/delete buttons."""

    def __init__(self, card: QueuedCard, panel: "NewCardQueuePanel"):
        super().__init__(panel)
        self.card = card
        self.panel = panel
        self.setObjectName("queueCard")
        self.setStyleSheet(_CARD_STYLE)
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 4)
        lay.setSpacing(3)
        self.thumb = QLabel(self)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setMinimumHeight(48)
        lay.addWidget(self.thumb)

        row = QHBoxLayout()
        row.setSpacing(2)
        self.count_label = QLabel(self)
        self.count_label.setStyleSheet("color:#8a8171;font-size:8.5pt;")
        row.addWidget(self.count_label)
        row.addStretch(1)
        bg_btn = QToolButton(self)
        bg_btn.setText("🎨")
        bg_btn.setToolTip("Change this card's background colour")
        qconnect(bg_btn.clicked, self._pick_bg)
        row.addWidget(bg_btn)
        del_btn = QToolButton(self)
        del_btn.setText("✕")
        del_btn.setToolTip("Delete this queued card")
        qconnect(del_btn.clicked, lambda: self.panel.delete_card(self.card.id))
        row.addWidget(del_btn)
        lay.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        img = self.card.compose()
        pix = QPixmap.fromImage(img).scaledToWidth(
            132, Qt.TransformationMode.SmoothTransformation
        )
        self.thumb.setPixmap(pix)
        n = len(self.card.snips)
        self.count_label.setText(
            "empty — drop snips here" if n == 0 else "%d snip%s" % (n, "" if n == 1 else "s")
        )

    def _pick_bg(self) -> None:
        c = QColorDialog.getColor(self.card.bg, self)
        if c.isValid():
            self.card.bg = c
            self.refresh()

    # ------------------------------------------------------------ drag&drop

    def _set_hover(self, on: bool) -> None:
        self.setProperty("dropHover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(PATCH_MIME):
            self._set_hover(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)

    def dropEvent(self, event) -> None:
        self._set_hover(False)
        patch_id = bytes(event.mimeData().data(PATCH_MIME)).decode("ascii")
        if self.panel.on_patch_dropped(self.card.id, patch_id):
            event.acceptProposedAction()


class NewCardQueuePanel(QWidget):
    """The queue section of the left toolbar."""

    start_next_requested = pyqtSignal()
    # dialog wires this to the canvas: (card_id, patch_id) -> bool
    patch_drop_handler = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue = NewCardQueue()
        self.default_bg = QColor("#ffffff")
        self._widgets: dict = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        title = QLabel("New card queue", self)
        title.setStyleSheet("font-weight:600;")
        lay.addWidget(title)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setMaximumHeight(300)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inner = QWidget(self)
        inner.setStyleSheet("background:transparent;")
        self.cards_layout = QVBoxLayout(inner)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch(1)
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll)

        row = QHBoxLayout()
        add_btn = QPushButton("+ Card", self)
        add_btn.setToolTip(
            "Add an empty card to the queue, then drop snips onto it"
        )
        qconnect(add_btn.clicked, self.add_empty_card)
        row.addWidget(add_btn)
        self.start_btn = QPushButton("Start ▸", self)
        self.start_btn.setToolTip(
            "Load the first queued card into the editor to draw its boxes"
        )
        qconnect(self.start_btn.clicked, self.start_next_requested.emit)
        row.addWidget(self.start_btn)
        lay.addLayout(row)
        self._refresh_buttons()

    # --------------------------------------------------------------- queue

    def has_cards(self) -> bool:
        return len(self.queue) > 0

    def add_empty_card(self) -> QueuedCard:
        card = self.queue.new_card(self.default_bg)
        self._insert_widget(card)
        self._refresh_buttons()
        return card

    def add_card_with_snip(self, img) -> QueuedCard:
        card = self.queue.new_card(self.default_bg)
        card.add_snip(img)
        self._insert_widget(card)
        self._refresh_buttons()
        return card

    def delete_card(self, card_id: int) -> None:
        self.queue.remove(card_id)
        w = self._widgets.pop(card_id, None)
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        self._refresh_buttons()

    def pop_next(self):
        card = self.queue.pop_next()
        if card is not None:
            w = self._widgets.pop(card.id, None)
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._refresh_buttons()
        return card

    def on_patch_dropped(self, card_id: int, patch_id: str) -> bool:
        if self.patch_drop_handler is None:
            return False
        ok = self.patch_drop_handler(card_id, patch_id)
        if ok:
            w = self._widgets.get(card_id)
            if w is not None:
                w.refresh()
        return ok

    # ------------------------------------------------------------- helpers

    def _insert_widget(self, card: QueuedCard) -> None:
        w = QueueCardWidget(card, self)
        self._widgets[card.id] = w
        # keep the trailing stretch at the end
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, w)

    def _refresh_buttons(self) -> None:
        n = len(self.queue)
        self.start_btn.setEnabled(n > 0)
        self.start_btn.setText("Start ▸" if n == 0 else "Start ▸ (%d)" % n)
