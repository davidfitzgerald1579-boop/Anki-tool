"""Qt import shim.

Inside Anki we import from aqt.qt so the add-on works on both Qt5 and Qt6
builds (per the add-on docs). Outside Anki (tests, headless previews) we fall
back to PyQt6 directly.
"""

try:
    from aqt.qt import *  # noqa: F401,F403
except ImportError:  # running outside Anki (tests)
    from PyQt6.QtCore import *  # noqa: F401,F403
    from PyQt6.QtGui import *  # noqa: F401,F403
    from PyQt6.QtWidgets import *  # noqa: F401,F403

try:
    qconnect  # noqa: B018  # provided by aqt.qt on recent Anki versions
except NameError:

    def qconnect(signal, func):
        signal.connect(func)
