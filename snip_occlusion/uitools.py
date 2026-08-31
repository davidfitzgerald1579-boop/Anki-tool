"""Small shared UI helpers.

notify() replaces aqt's tooltip() popups inside the add-on's windows:
same transient behaviour, but crisp dark-on-cream text matching the
add-on's theme instead of the hard-to-read dark bubble.

cream_tooltips() does the same for HOVER tooltips (setToolTip text).
Styling those with a `QToolTip { ... }` stylesheet rule on the dialog
does not work: Qt shows a tooltip in its own top-level window parented
to the SCREEN, not to the widget it belongs to, so only the
application-wide stylesheet/palette applies - and that is Anki's (dark
in dark mode), which we must not touch. Instead an application-level
event filter intercepts the tooltip event for widgets inside opted-in
windows and shows a styled label of our own.
"""

from __future__ import annotations

from .qtshim import *  # noqa: F401,F403

_active: list = []

_TIP_STYLE = (
    "QLabel{background:#fffdf6;color:#2f2b1e;"
    "border:1px solid #c9bda8;border-radius:6px;padding:6px 10px;"
    "font-family:'Segoe UI','SF Pro Text','Helvetica Neue',Arial,"
    "sans-serif;font-size:10pt;}"
)
_TIP_PROP = "snip_cream_tips"
_tip_label: QLabel | None = None
_tip_timer: QTimer | None = None
_tip_filter = None


def _hide_tip() -> None:
    if _tip_label is not None and _tip_label.isVisible():
        _tip_label.hide()


def _show_tip(global_pos, text: str) -> None:
    global _tip_label, _tip_timer
    if _tip_label is None:
        _tip_label = QLabel()
        _tip_label.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        _tip_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        _tip_label.setStyleSheet(_TIP_STYLE)
        _tip_label.setWordWrap(True)
        _tip_timer = QTimer(_tip_label)
        _tip_timer.setSingleShot(True)
        qconnect(_tip_timer.timeout, _hide_tip)
    _tip_label.setMaximumWidth(420)
    _tip_label.setText(text)
    _tip_label.adjustSize()
    x, y = global_pos.x() + 12, global_pos.y() + 16
    screen = QApplication.screenAt(global_pos)
    if screen is not None:  # keep the tip on-screen near edges
        geo = screen.availableGeometry()
        x = min(x, geo.right() - _tip_label.width() - 4)
        y = min(y, geo.bottom() - _tip_label.height() - 4)
    _tip_label.move(max(0, x), max(0, y))
    _tip_label.show()
    # linger long enough to read, then bow out like a native tooltip
    _tip_timer.start(max(4000, 60 * len(text)))


class _TipFilter(QObject):
    """App-wide filter: cream tooltips for widgets in opted-in windows."""

    def eventFilter(self, obj, event) -> bool:
        try:
            etype = event.type()
            if etype == QEvent.Type.ToolTip and isinstance(obj, QWidget):
                window = obj.window()
                if window is not None and window.property(_TIP_PROP):
                    text = obj.toolTip()
                    if text:
                        _show_tip(event.globalPos(), text)
                    else:
                        _hide_tip()
                    return True  # suppress the native (dark) tooltip
            elif etype in (
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.Wheel,
                QEvent.Type.WindowDeactivate,
            ):
                _hide_tip()
        except Exception:
            pass  # a broken tooltip must never break the app
        return False


def cream_tooltips(window) -> None:
    """Opt a window in: its widgets' tooltips render dark-on-cream."""
    global _tip_filter
    app = QApplication.instance()
    if app is None:
        return
    if _tip_filter is None:
        _tip_filter = _TipFilter(app)
        app.installEventFilter(_tip_filter)
    window.setProperty(_TIP_PROP, True)


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
