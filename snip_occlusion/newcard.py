"""Model for the new-card queue.

A QueuedCard collects one or more snips (pixel-exact crops taken from
slides) plus a background colour. compose() stacks the snips onto that
background to produce the image for a brand-new card. Snips are stored as
copied QImages at full resolution and drawn at 1:1 scale with no
resampling, so quality is identical to the original screenshots.
"""

from __future__ import annotations

import itertools

from .qtshim import QColor, QImage, QPainter, QPoint

PAD = 24  # breathing room around/between snips
MIN_WIDTH = 320  # so a single short sentence doesn't make a cramped card

_ids = itertools.count(1)


class QueuedCard:
    def __init__(self, bg: QColor):
        self.id = next(_ids)
        self.bg = QColor(bg)
        self.snips: list = []  # QImage, in drop order (stacked top->bottom)

    def add_snip(self, img: QImage) -> None:
        self.snips.append(img.copy())

    def compose(self) -> QImage:
        """Stack the snips on the background colour, 1:1 pixels."""
        if not self.snips:
            img = QImage(MIN_WIDTH, 120, QImage.Format.Format_RGB32)
            img.fill(self.bg)
            return img
        width = max(MIN_WIDTH, max(s.width() for s in self.snips) + 2 * PAD)
        height = sum(s.height() for s in self.snips) + PAD * (
            len(self.snips) + 1
        )
        img = QImage(width, height, QImage.Format.Format_RGB32)
        img.fill(self.bg)
        painter = QPainter(img)
        y = PAD
        for snip in self.snips:
            painter.drawImage(QPoint(PAD, y), snip)
            y += snip.height() + PAD
        painter.end()
        return img


class NewCardQueue:
    def __init__(self):
        self.cards: list = []

    def new_card(self, bg: QColor) -> QueuedCard:
        card = QueuedCard(bg)
        self.cards.append(card)
        return card

    def card_by_id(self, card_id: int):
        for c in self.cards:
            if c.id == card_id:
                return c
        return None

    def remove(self, card_id: int) -> None:
        self.cards = [c for c in self.cards if c.id != card_id]

    def pop_next(self):
        return self.cards.pop(0) if self.cards else None

    def __len__(self) -> int:
        return len(self.cards)
