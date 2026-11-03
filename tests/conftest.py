import gc
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    # Nothing of Qt's may outlive the QApplication, which goes right
    # after this: a window freed later (say a "Card added" notice still
    # waiting to close itself) can segfault the run after every test
    # has passed. Delete what is left while Qt is still up.
    for widget in app.topLevelWidgets():
        widget.hide()
        widget.deleteLater()
    QTest.qWait(50)
    gc.collect()
    QTest.qWait(50)


@pytest.fixture(autouse=True)
def _usage_file_in_tmp(tmp_path, monkeypatch):
    """No test writes the real user_files/qgen_usage.json."""
    from snip_occlusion import qgen_usage

    monkeypatch.setattr(
        qgen_usage, "_path", lambda: str(tmp_path / "qgen_usage.json")
    )
