"""The 'New card queue' panel: lives at the bottom of the left toolbar.

Each queued card is shown PowerPoint-style: a numbered slide thumbnail
(the card's background colour, thin border, soft shadow) with its snips
letterboxed inside. Cards accept snip patches dropped straight from the
canvas, can be created empty, recoloured, or deleted. 'Start' loads the
first queued card into the editor as a fresh image to occlude.
"""

from __future__ import annotations

import re

from .qtshim import *  # noqa: F401,F403
from . import added_cards
from .newcard import NewCardQueue, QueuedCard

PATCH_MIME = "application/x-snip-occlusion-patch"

THUMB_ASPECT = 0.625  # 16:10, like a slide

_CARD_STYLE = """
QFrame#queueCard {
    background: transparent;
    border: 2px solid transparent;
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
    """One card in the queue: slide-style thumbnail + controls."""

    def __init__(self, card: QueuedCard, panel: "NewCardQueuePanel"):
        super().__init__(panel)
        self.card = card
        self.panel = panel
        self.index = 1
        self._composed: QImage | None = None
        self.setObjectName("queueCard")
        self.setStyleSheet(_CARD_STYLE)
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 2)
        lay.setSpacing(2)
        self.thumb = QLabel(self)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.thumb)

        row = QHBoxLayout()
        row.setSpacing(2)
        self.num_label = QLabel(self)
        self.num_label.setStyleSheet(
            "color:#8a8171;font-size:8.5pt;font-weight:600;"
        )
        row.addWidget(self.num_label)
        self.count_label = QLabel(self)
        self.count_label.setStyleSheet("color:#8a8171;font-size:8.5pt;")
        row.addWidget(self.count_label)
        row.addStretch(1)
        self.bg_btn = QToolButton(self)
        self.bg_btn.setToolTip("Change this card's background colour")
        qconnect(self.bg_btn.clicked, self._pick_bg)
        row.addWidget(self.bg_btn)
        del_btn = QToolButton(self)
        del_btn.setText("×")
        del_btn.setToolTip("Delete this queued card")
        qconnect(del_btn.clicked, lambda: self.panel.delete_card(self.card.id))
        row.addWidget(del_btn)
        lay.addLayout(row)
        self.refresh()

    def set_index(self, index: int) -> None:
        self.index = index
        self.num_label.setText("Card %d" % index)

    def refresh(self) -> None:
        """Recompose the card content and redraw the thumbnail."""
        self._composed = self.card.compose() if self.card.snips else None
        self._render_thumb()
        n = len(self.card.snips)
        self.count_label.setText(
            "· drop snips here" if n == 0
            else "· %d snip%s" % (n, "" if n == 1 else "s")
        )
        swatch = QPixmap(14, 14)
        swatch.fill(self.card.bg)
        self.bg_btn.setIcon(QIcon(swatch))
        self.set_index(self.index)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_thumb()

    def _render_thumb(self) -> None:
        """A PowerPoint-style slide: shadow, border, content letterboxed."""
        width = max(110, self.width() - 14)
        height = int(width * THUMB_ASPECT)
        pm = QPixmap(width, height)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        slide = QRectF(0.5, 0.5, width - 4, height - 4)
        # soft shadow, then the slide itself
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 26))
        p.drawRoundedRect(slide.translated(2.5, 2.5), 3, 3)
        p.setBrush(QBrush(self.card.bg))
        p.setPen(QPen(QColor("#c9c0b0"), 1))
        p.drawRoundedRect(slide, 3, 3)

        if self._composed is not None:
            inner = slide.adjusted(5, 5, -5, -5)
            img = self._composed
            scale = min(
                inner.width() / img.width(), inner.height() / img.height(), 1.0
            )
            w, h = img.width() * scale, img.height() * scale
            target = QRectF(
                inner.x() + (inner.width() - w) / 2,
                inner.y() + (inner.height() - h) / 2,
                w,
                h,
            )
            p.drawImage(target, img, QRectF(0, 0, img.width(), img.height()))
        else:
            # empty card: a ghost plus sign, like an empty new slide
            p.setPen(QPen(QColor(0, 0, 0, 45), 2))
            cx, cy = slide.center().x(), slide.center().y()
            arm = min(12.0, slide.height() / 5)
            p.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
            p.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))
        p.end()
        self.thumb.setPixmap(pm)

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
        self.scroll.setMinimumHeight(90)
        self.scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
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
        lay.addWidget(self.scroll, 1)

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
        self._renumber()

    def _renumber(self) -> None:
        for i, card in enumerate(self.queue.cards, 1):
            w = self._widgets.get(card.id)
            if w is not None:
                w.set_index(i)

    def _refresh_buttons(self) -> None:
        n = len(self.queue)
        self.start_btn.setEnabled(n > 0)
        self.start_btn.setText("Start ▸" if n == 0 else "Start ▸ (%d)" % n)
        self._renumber()


# --------------------------------------------------------- added cards


def _html_to_text(html: str) -> str:
    """Plain preview text from a field's HTML."""
    text = re.sub(r"<br\s*/?>", " ", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    for entity, ch in (
        ("&nbsp;", " "),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&amp;", "&"),
    ):
        text = text.replace(entity, ch)
    return " ".join(text.split())


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class AddedCardWidget(QFrame):
    """One added card, slide-style: readable Q and A preview, clickable."""

    def __init__(self, entry: dict, index: int, owner: "AddedCardsList"):
        super().__init__(owner)
        self.note_id = entry["note_id"]
        self.owner = owner
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e3dcd0;"
            "border-radius:8px;}"
            "QFrame:hover{border-color:#d97757;background:#fdf6ee;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        front = _clip(_html_to_text(entry.get("front", "")), 160)
        back = _clip(_html_to_text(entry.get("back", "")), 140)
        body = QLabel(
            "<span style='color:#8a8171;font-size:8.5pt;'>Card %d</span>"
            "<br><b>Q:</b> %s<br><b>A:</b> %s"
            % (
                index,
                front.replace("&", "&amp;").replace("<", "&lt;"),
                back.replace("&", "&amp;").replace("<", "&lt;"),
            ),
            self,
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction
        )
        lay.addWidget(body)
        self.setToolTip(
            "Click to edit & redeploy this card (replacing it in your "
            "deck) or delete it."
        )

    def activate(self) -> None:
        self.owner.open(self.note_id)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activate()
        super().mousePressEvent(event)


class AddedCardsList(QWidget):
    """Sidebar list of text cards added this session (newest first)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.open_added_handler = None  # set by the dialog

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.title = QLabel("Added cards", self)
        self.title.setStyleSheet("font-weight:600;")
        self.title.setToolTip(
            "Text cards added this session — click one to edit and "
            "redeploy it (replacing the card in your deck) or delete it"
        )
        lay.addWidget(self.title)
        self.hint = QLabel(
            "Cards you add appear here — click one to fix or delete it.",
            self,
        )
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#8a8171;font-size:9pt;")
        lay.addWidget(self.hint)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setMinimumHeight(70)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inner = QWidget(self)
        inner.setStyleSheet("background:transparent;")
        self.cards_lay = QVBoxLayout(inner)
        self.cards_lay.setContentsMargins(0, 0, 4, 0)
        self.cards_lay.setSpacing(6)
        self.cards_lay.addStretch(1)
        self.scroll.setWidget(inner)
        lay.addWidget(self.scroll, 1)

        added_cards.add_listener(self.refresh)
        self.refresh()

    def open(self, note_id: int) -> None:
        if self.open_added_handler is not None:
            self.open_added_handler(note_id)

    def refresh(self) -> None:
        while self.cards_lay.count() > 1:
            item = self.cards_lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        entries = added_cards.entries()
        self.title.setText(
            "Added cards (%d)" % len(entries) if entries else "Added cards"
        )
        self.hint.setVisible(not entries)
        self.scroll.setVisible(bool(entries))
        for i, entry in enumerate(reversed(entries)):  # newest on top
            w = AddedCardWidget(entry, len(entries) - i, self)
            self.cards_lay.insertWidget(
                self.cards_lay.count() - 1, w
            )
