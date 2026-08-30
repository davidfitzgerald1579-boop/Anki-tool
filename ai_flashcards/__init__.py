"""AI Flashcards (Local LLM) - generate Anki cards with open-source models.

Connects to an LLM running on the user's own machine (Ollama by default,
or any OpenAI-compatible server such as LM Studio or llama.cpp). No API
keys, no per-request costs, and notes never leave the computer.
"""

from aqt import mw
from aqt.qt import QAction
from aqt.utils import qconnect


def _open_dialog():
    from . import gui

    gui.show_dialog()


def _setup_menu():
    action = QAction("Generate AI Flashcards (Local LLM)...", mw)
    qconnect(action.triggered, _open_dialog)
    mw.form.menuTools.addAction(action)


_setup_menu()
