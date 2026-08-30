"""Generate a BPP-style slide image for tests and doc screenshots."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter

BG = "#fbf3e4"  # cream background (majority colour)
TITLE = "#d81b60"  # BPP pink
TEXT = "#333333"
CALLOUT = "#f8d7da"  # pink callout box


def make_slide(w: int = 800, h: int = 500) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    p.setPen(QColor(TITLE))
    f = QFont("Arial", 26)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(40, 20, w - 80, 60), Qt.AlignmentFlag.AlignLeft,
               "Administrative Court")

    p.setPen(QColor(TEXT))
    p.setFont(QFont("Arial", 13))
    lines = [
        "The Administrative Court is part of the King's Bench Division.",
        "It reviews the lawfulness of actions of public bodies.",
        "Appeals 'by way of case stated' come from the magistrates' courts.",
        "Some cases are heard by a Divisional Court of two or more judges.",
        "Totally irrelevant boilerplate the student wants to erase.",
    ]
    y = 110.0
    for line in lines:
        p.drawText(QRectF(40, y, w - 80, 30), Qt.AlignmentFlag.AlignLeft, line)
        y += 44

    # a coloured callout box with its own background (for local sampling)
    p.fillRect(QRectF(40, y + 10, 380, 70), QColor(CALLOUT))
    p.setPen(QColor(TEXT))
    p.drawText(
        QRectF(52, y + 20, 360, 50),
        Qt.AlignmentFlag.AlignLeft,
        "UTIAC has JR powers for most immigration decisions.",
    )
    p.end()
    return img
