"""Capture the AI section of the Settings window for the guide, offscreen.

Stubs the parts of aqt the dialog imports, opens the real Settings
dialog with Groq selected and a successful test shown, and saves the
AI section as docs/guide/settings_ai.png. Run from the repo root:

    QT_QPA_PLATFORM=offscreen python3 tools/settings_screenshot.py
"""

import sys
import time
import types
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "guide" / "settings_ai.png"

aqt = types.ModuleType("aqt")
aqt.mw = None
aqt.gui_hooks = None
aqt_utils = types.ModuleType("aqt.utils")
aqt_utils.showWarning = lambda *a, **k: None
aqt_utils.askUser = lambda *a, **k: False
aqt_utils.tooltip = lambda *a, **k: None
aqt_utils.qconnect = lambda sig, fn: sig.connect(fn)
aqt_qt = types.ModuleType("aqt.qt")
for mod in (QtCore, QtGui, QtWidgets):
    for name in dir(mod):
        if not name.startswith("_"):
            setattr(aqt_qt, name, getattr(mod, name))
aqt_qt.qconnect = aqt_utils.qconnect
aqt.utils = aqt_utils
aqt.qt = aqt_qt
sys.modules.update({"aqt": aqt, "aqt.utils": aqt_utils, "aqt.qt": aqt_qt})
sys.path.insert(0, str(ROOT))

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from snip_occlusion import dialog as dialog_mod  # noqa: E402
from snip_occlusion.qgen_settings import ProviderSettings  # noqa: E402


def settle(n: int = 8) -> None:
    for _ in range(n):
        app.processEvents()
        time.sleep(0.03)


def fake_exec(self):
    self.resize(720, 980)
    self.show()
    settle()
    w = self.findChild(ProviderSettings)
    w.hosted_radio.setChecked(True)
    w.api_key.setText("gsk_" + "x" * 32)
    w.test_result.setText(
        "<span style='color:#2f7d4a'>✓ Groq answered with openai/gpt-oss-20b "
        "in 0.6 s · 14 models listed · said 'OK'</span>"
    )
    settle()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    w.grab().save(str(OUT))
    print("wrote", OUT)
    return QtWidgets.QDialog.DialogCode.Rejected


QtWidgets.QDialog.exec = fake_exec


class _Stub(QtWidgets.QWidget):
    config = {"qgen_provider": "ollama"}
    _view_mode = "image"

    def _apply_sidebar_mode(self, *_args) -> None:
        pass


dialog_mod.SnipOcclusionDialog._open_settings(_Stub())
