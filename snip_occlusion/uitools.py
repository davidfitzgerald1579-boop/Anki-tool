"""Small shared UI helpers.

notify() replaces aqt's tooltip() popups inside the add-on's windows:
same transient behaviour, but crisp dark-on-cream text matching the
add-on's theme instead of the hard-to-read dark bubble.
"""

from __future__ import annotations

from .qtshim import *  # noqa: F401,F403

_active: list = []


def notify(message: str, parent=None, period: int = 3000, **_ignored) -> None:
    label = QLabel(message)
    label.setWindowFlags(
        Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
    )
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    label.setStyleSheet(
        "QLabel{background:#fffdf6;color:#2f2b1e;"
        "border:1px solid #c9bda8;border-radius:6px;padding:8px 14px;"
        "font-family:'Segoe UI','SF Pro Text','Helvetica Neue',Arial,"
        "sans-serif;font-size:10.5pt;}"
    )
    label.setWordWrap(True)
    label.setMaximumWidth(480)
    label.adjustSize()
    window = parent.window() if parent is not None else None
    if window is not None and window.isVisible():
        geo = window.frameGeometry()
        x = geo.center().x() - label.width() // 2
        y = geo.bottom() - label.height() - 48
    else:
        pos = QCursor.pos()
        x, y = pos.x() + 12, pos.y() + 12
    label.move(x, y)
    label.show()
    _active.append(label)

    def _close() -> None:
        try:
            label.hide()
            label.deleteLater()
        finally:
            if label in _active:
                _active.remove(label)

    QTimer.singleShot(max(800, int(period)), _close)
