"""The "AI model for card suggestions" section of the ⚙ Settings window.

Lets the user pick WHERE the model runs (this computer, a hosted
service, any other server), which model, and an optional second model
for the bake-off - then prove it works with a Test button before
saving. Pure Qt on top of qgen / qgen_providers; nothing here touches
Anki, so it runs (and is tested) offscreen.
"""

from __future__ import annotations

import threading

from .qtshim import *  # noqa: F401,F403
from . import qgen, qgen_providers

_MUTED = "color:#8a8171"
_OK = "color:#2f7d4a"
_BAD = "color:#b3402b"


class ProviderSettings(QWidget):
    """Editable view of the qgen_provider / model / key config keys.

    `values()` returns the keys to write back. Network probes run in a
    background thread and report through `_probe_done`.
    """

    # seq, provider probed, kind, result-or-exception
    _probe_done = pyqtSignal(int, str, str, object)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = dict(config)
        # the model last chosen for each provider, so switching back and
        # forth doesn't lose the local model name while trying Groq
        self._model_memory: dict = {}
        self._alt_memory: dict = {}  # bake-off partner, per provider
        # one key per provider: a key pasted for Groq must never be sent
        # to OpenRouter, or to a server the user points the add-on at
        self._key_memory: dict = {}
        stored = self.config.get("qgen_api_keys")
        if isinstance(stored, dict):
            for k, v in stored.items():
                if isinstance(v, str) and v.strip():
                    self._key_memory[qgen_providers.normalise(k)] = v.strip()
        provider = qgen_providers.normalise(self.config.get("qgen_provider"))
        legacy = str(self.config.get("qgen_api_key") or "").strip()
        if legacy:
            self._key_memory[provider] = legacy
        if self.config.get("qgen_model"):
            self._model_memory[provider] = str(self.config["qgen_model"])
        self._probing = False
        self._probe_seq = 0
        self._build_ui()
        self._load(provider)
        qconnect(self._probe_done, self._on_probe_done)

    # ------------------------------------------------------------- build

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel("<b>AI model for card suggestions</b>", self))

        self.mode_group = QButtonGroup(self)
        self.local_radio = QRadioButton(
            "On this computer — free and private, but slow (Ollama)", self
        )
        self.hosted_radio = QRadioButton(
            "A hosted service — many times faster, pay-per-use "
            "(often free); the text is sent to that service",
            self,
        )
        self.custom_radio = QRadioButton(
            "Another server — any OpenAI-compatible URL (LM Studio, "
            "vLLM, a rented GPU box…)",
            self,
        )
        for radio in (self.local_radio, self.hosted_radio, self.custom_radio):
            self.mode_group.addButton(radio)
            lay.addWidget(radio)
            qconnect(radio.toggled, self._mode_changed)

        # --- local pane
        self.local_pane = QWidget(self)
        local_form = QFormLayout(self.local_pane)
        local_form.setContentsMargins(24, 0, 0, 4)
        self.ollama_url = QLineEdit(self.local_pane)
        self.ollama_url.setPlaceholderText(qgen.DEFAULT_OLLAMA_URL)
        self.ollama_url.setToolTip(
            "Ollama's address. Leave as is for this computer; point it at "
            "another machine on your network (http://192.168.x.x:11434) "
            "to run the model there instead."
        )
        local_form.addRow("Ollama server:", self.ollama_url)
        self.local_key = QLineEdit(self.local_pane)
        self.local_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.local_key.setPlaceholderText(
            "only for a proxy in front of a remote Ollama"
        )
        self.local_key.setToolTip(
            "Sent as a Bearer token. An Ollama on this computer needs "
            "none; a rented box behind an authenticating proxy does."
        )
        local_form.addRow("API key:", self.local_key)
        local_hint = QLabel(
            "<span style='%s'>Install <a href='https://ollama.com/download'>"
            "Ollama</a>, then in a terminal: <code>ollama pull "
            "llama3.1:8b</code></span>" % _MUTED,
            self.local_pane,
        )
        local_hint.setOpenExternalLinks(True)
        local_form.addRow("", local_hint)
        lay.addWidget(self.local_pane)

        # --- hosted pane
        self.hosted_pane = QWidget(self)
        hosted_form = QFormLayout(self.hosted_pane)
        hosted_form.setContentsMargins(24, 0, 0, 4)
        self.service_box = QComboBox(self.hosted_pane)
        for p in qgen_providers.HOSTED:
            self.service_box.addItem(p.label, p.key)
        qconnect(self.service_box.currentIndexChanged, self._service_changed)
        hosted_form.addRow("Service:", self.service_box)
        key_row = QHBoxLayout()
        self.api_key = QLineEdit(self.hosted_pane)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("paste your API key")
        key_row.addWidget(self.api_key, 1)
        self.key_link = QLabel(self.hosted_pane)
        self.key_link.setOpenExternalLinks(True)
        key_row.addWidget(self.key_link)
        hosted_form.addRow("API key:", key_row)
        self.service_note = QLabel(self.hosted_pane)
        self.service_note.setWordWrap(True)
        self.service_note.setOpenExternalLinks(True)
        hosted_form.addRow("", self.service_note)
        lay.addWidget(self.hosted_pane)

        # --- custom pane
        self.custom_pane = QWidget(self)
        custom_form = QFormLayout(self.custom_pane)
        custom_form.setContentsMargins(24, 0, 0, 4)
        self.custom_url = QLineEdit(self.custom_pane)
        self.custom_url.setPlaceholderText(qgen.DEFAULT_OPENAI_BASE_URL)
        self.custom_url.setToolTip(
            "The server's base URL, including /v1 if it uses one."
        )
        custom_form.addRow("Server URL:", self.custom_url)
        self.custom_key = QLineEdit(self.custom_pane)
        self.custom_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.custom_key.setPlaceholderText("only if the server wants one")
        custom_form.addRow("API key:", self.custom_key)
        lay.addWidget(self.custom_pane)

        # --- model row (shared)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:", self))
        self.model_box = QComboBox(self)
        self.model_box.setEditable(True)
        self.model_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_box.setMinimumWidth(260)
        model_row.addWidget(self.model_box, 1)
        self.fetch_btn = QPushButton("↻ Fetch list", self)
        self.fetch_btn.setToolTip(
            "Ask the server which models it has and fill the list"
        )
        qconnect(self.fetch_btn.clicked, self._fetch_models)
        model_row.addWidget(self.fetch_btn)
        lay.addLayout(model_row)

        alt_row = QHBoxLayout()
        self.bakeoff_check = QCheckBox("Alternate at random with:", self)
        self.bakeoff_check.setToolTip(
            "Each generation randomly picks one of the two models; your "
            "Use/★/Skip/✗ verdicts and generation times are tallied per "
            "model in the scoreboard, so you can see which one earns its "
            "keep."
        )
        alt_row.addWidget(self.bakeoff_check)
        self.alt_box = QComboBox(self)
        self.alt_box.setEditable(True)
        self.alt_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        alt_row.addWidget(self.alt_box, 1)
        qconnect(self.bakeoff_check.toggled, self.alt_box.setEnabled)
        lay.addLayout(alt_row)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test connection", self)
        qconnect(self.test_btn.clicked, self._test_connection)
        test_row.addWidget(self.test_btn)
        self.test_result = QLabel(self)
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        test_row.addWidget(self.test_result, 1)
        lay.addLayout(test_row)

        self.privacy = QLabel(self)
        self.privacy.setWordWrap(True)
        lay.addWidget(self.privacy)

        for edit in (self.ollama_url, self.custom_url):
            qconnect(edit.textChanged, self._refresh_privacy)

    # -------------------------------------------------------------- load

    def _load(self, provider: str) -> None:
        cfg = self.config
        self.ollama_url.setText(
            str(cfg.get("qgen_ollama_url") or qgen.DEFAULT_OLLAMA_URL)
        )
        self.custom_url.setText(
            str(cfg.get("qgen_openai_base_url") or qgen.DEFAULT_OPENAI_BASE_URL)
        )
        self.local_key.setText(self._key_memory.get(qgen_providers.LOCAL, ""))
        self.custom_key.setText(
            self._key_memory.get(qgen_providers.CUSTOM, "")
        )
        preset = qgen_providers.preset(provider)
        if preset is not None:
            self.service_box.setCurrentIndex(
                max(0, self.service_box.findData(preset.key))
            )
            self.hosted_radio.setChecked(True)
        elif provider == qgen_providers.CUSTOM:
            self.custom_radio.setChecked(True)
        else:
            self.local_radio.setChecked(True)
        self.bakeoff_check.setChecked(bool(cfg.get("qgen_bakeoff", False)))
        self.alt_box.setEnabled(self.bakeoff_check.isChecked())
        # the bake-off partner: whichever configured contender isn't
        # the main model - those names belong to the saved provider
        contenders = [
            m
            for m in (cfg.get("qgen_bakeoff_models") or [])
            if isinstance(m, str) and m.strip()
        ]
        main = self.model_box.currentText().strip()
        partner = next((m for m in contenders if m != main), "")
        if partner:
            self._alt_memory[provider] = partner
        self._mode_changed()
        self.alt_box.setEditText(partner or self._default_partner(provider))

    # ------------------------------------------------------------- state

    def mode(self) -> str:
        if self.hosted_radio.isChecked():
            return "hosted"
        if self.custom_radio.isChecked():
            return "custom"
        return "local"

    def provider(self) -> str:
        """The qgen_provider value the current widget state means."""
        m = self.mode()
        if m == "hosted":
            return str(self.service_box.currentData() or "")
        if m == "custom":
            return qgen_providers.CUSTOM
        return qgen_providers.LOCAL

    def current_preset(self):
        return qgen_providers.preset(self.provider())

    def values(self) -> dict:
        """Config keys as the widget stands (for saving)."""
        provider = self.provider()
        model = self.model_box.currentText().strip()
        alt = self.alt_box.currentText().strip()
        self._remember_key()
        keys = {k: v for k, v in self._key_memory.items() if v}
        out = {
            "qgen_provider": provider,
            "qgen_model": model,
            "qgen_ollama_url": (
                self.ollama_url.text().strip() or qgen.DEFAULT_OLLAMA_URL
            ),
            "qgen_openai_base_url": (
                self.custom_url.text().strip() or qgen.DEFAULT_OPENAI_BASE_URL
            ),
            "qgen_api_key": keys.get(provider, ""),
            "qgen_api_keys": keys,
            "qgen_bakeoff": bool(
                self.bakeoff_check.isChecked() and alt and alt != model
            ),
        }
        if alt and alt != model:
            out["qgen_bakeoff_models"] = [model, alt]
        return out

    def probe_config(self) -> dict:
        """The saved config with the widget's current choices on top."""
        cfg = dict(self.config)
        cfg.update(self.values())
        return cfg

    def problem(self) -> str:
        """Why the current state can't be saved, or "" when it can."""
        model = self.model_box.currentText().strip()
        if not model:
            return "Choose a model (or press Fetch list)."
        if self.bakeoff_check.isChecked():
            alt = self.alt_box.currentText().strip()
            if not alt or alt == model:
                return (
                    "Choose a second, different model for the bake-off "
                    "(or untick it)."
                )
        if self.mode() == "hosted":
            preset = self.current_preset()
            if preset is not None and not self.api_key.text().strip():
                try:
                    if qgen_providers.resolve(self.probe_config()).api_key:
                        return ""  # supplied by the environment
                except qgen_providers.UnknownProvider:
                    pass
                return "%s needs an API key." % preset.label
        return ""

    # ---------------------------------------------------------- reactions

    def _remember_model(self) -> None:
        text = self.model_box.currentText().strip()
        if text:
            self._model_memory[self._loaded_provider] = text
        alt = self.alt_box.currentText().strip()
        if alt:
            self._alt_memory[self._loaded_provider] = alt
        self._remember_key()

    def _key_box(self, provider: str) -> QLineEdit:
        if provider == qgen_providers.LOCAL:
            return self.local_key
        if provider == qgen_providers.CUSTOM:
            return self.custom_key
        return self.api_key

    def _remember_key(self) -> None:
        """Stash the key box of the provider currently shown."""
        provider = self._loaded_provider
        if not provider:
            return
        text = self._key_box(provider).text().strip()
        if text:
            self._key_memory[provider] = text
        else:
            self._key_memory.pop(provider, None)  # cleared on purpose

    @staticmethod
    def _default_partner(provider: str) -> str:
        """A sensible second model for the bake-off on `provider`."""
        preset = qgen_providers.preset(provider)
        if preset is not None:
            return preset.models[1][0] if len(preset.models) > 1 else ""
        if provider == qgen_providers.LOCAL:
            return "llama3.2:3b"
        return ""

    _loaded_provider = ""

    def _mode_changed(self, *_args) -> None:
        mode = self.mode()
        self.local_pane.setVisible(mode == "local")
        self.hosted_pane.setVisible(mode == "hosted")
        self.custom_pane.setVisible(mode == "custom")
        self._switch_provider(self.provider())
        if mode == "hosted":
            self._service_changed()
        self._refresh_privacy()

    def _service_changed(self, *_args) -> None:
        preset = self.current_preset()
        if preset is None:
            return
        self.key_link.setText(
            "<a href='%s'>Get a key ↗</a>" % preset.key_url
        )
        bits = [preset.free_tier]
        if preset.note:
            bits.append(preset.note)
        if preset.pricing_url:
            bits.append("<a href='%s'>Pricing ↗</a>" % preset.pricing_url)
        self.service_note.setText(
            "<span style='%s'>%s</span>" % (_MUTED, " ".join(bits))
        )
        self._switch_provider(preset.key)
        self._refresh_privacy()

    def _switch_provider(self, provider: str) -> None:
        if provider == self._loaded_provider:
            return
        if self._loaded_provider:
            self._remember_model()
        self._loaded_provider = provider
        preset = qgen_providers.preset(provider)
        # the hosted pane's key box is shared by all services: show only
        # the key entered for THIS one (empty if none yet)
        if preset is not None:
            self.api_key.setText(self._key_memory.get(provider, ""))
        if preset is not None:
            choices = list(preset.models)
        elif provider == qgen_providers.LOCAL:
            choices = list(qgen_providers.LOCAL_MODELS)
        else:
            choices = []
        remembered = self._model_memory.get(provider)
        if not remembered and preset is not None:
            remembered = preset.models[0][0]
        elif not remembered and provider == qgen_providers.LOCAL:
            remembered = qgen.DEFAULT_MODEL
        self._fill(self.model_box, choices, remembered or "")
        # the partner must be a model of the SAME provider: a partner
        # carried over from another provider would 404 half the time
        alt = self._alt_memory.get(provider) or self._default_partner(provider)
        main = self.model_box.currentText().strip()
        if alt == main:
            alt = next(
                (
                    (c[0] if isinstance(c, (tuple, list)) else str(c))
                    for c in choices
                    if (c[0] if isinstance(c, (tuple, list)) else str(c)) != main
                ),
                "",
            )
        self._fill(self.alt_box, choices, alt)
        self.test_result.setText("")

    @staticmethod
    def _fill(box: QComboBox, choices: list, text: str) -> None:
        """Repopulate an editable combo, keeping `text` as its entry.

        `choices` items are either plain ids or (id, description)."""
        box.blockSignals(True)
        try:
            box.clear()
            for item in choices:
                if isinstance(item, (tuple, list)):
                    mid, desc = item[0], item[1] if len(item) > 1 else ""
                else:
                    mid, desc = str(item), ""
                box.addItem(mid)
                if desc:
                    box.setItemData(
                        box.count() - 1, desc, Qt.ItemDataRole.ToolTipRole
                    )
            box.setEditText(text)
        finally:
            box.blockSignals(False)

    def _refresh_privacy(self, *_args) -> None:
        try:
            target = qgen_providers.resolve(self.probe_config())
        except qgen_providers.UnknownProvider:
            self.privacy.setText("")
            return
        if not target.remote:
            text = "Nothing leaves this computer."
        else:
            where = (
                "%s at %s" % (target.label, target.host)
                if target.preset is not None
                else target.host
            )
            when = (
                "the moment a snip lands in the editor (background "
                "pre-generation is on)"
                if self.config.get("qgen_prefetch", True)
                else "when you ask for suggestions"
            )
            text = (
                "The slide or lesson text - never the image - is sent to "
                "%s %s, together with a few of your kept/flagged example "
                "cards as style guidance. Your API key is kept in this "
                "add-on's config on this computer and is only ever sent "
                "to %s." % (where, when, where.split(" at ")[0])
            )
        self.privacy.setText("<span style='%s'>%s</span>" % (_MUTED, text))

    # ------------------------------------------------------------ probes

    def _run_in_background(self, kind: str, fn) -> None:
        """Run fn() off the UI thread; deliver via _probe_done.

        The answer is stamped with the probe's sequence number and the
        provider it was started for, so a slow reply that arrives after
        the user has switched provider (or clicked again) is dropped
        instead of being applied to the wrong list.
        """
        self._probe_seq += 1
        seq = self._probe_seq
        provider = self.provider()

        def work():
            try:
                result = fn()
            except Exception as exc:  # reported, never raised in a thread
                result = exc
            try:
                self._probe_done.emit(seq, provider, kind, result)
            except RuntimeError:
                pass  # the Settings window was closed mid-probe

        threading.Thread(target=work, daemon=True, name="qgen-probe").start()

    def _set_probing(self, on: bool, note: str = "") -> None:
        self._probing = on
        self.fetch_btn.setEnabled(not on)
        self.test_btn.setEnabled(not on)
        if note:
            self.test_result.setText(
                "<span style='%s'>%s</span>" % (_MUTED, note)
            )

    def _fetch_models(self) -> None:
        if self._probing:
            return
        cfg = self.probe_config()
        self._set_probing(True, "asking the server for its models…")
        self._run_in_background("models", lambda: qgen.list_models(cfg))

    def _test_connection(self) -> None:
        if self._probing:
            return
        cfg = self.probe_config()
        self._set_probing(True, "testing…")
        self._run_in_background("test", lambda: qgen.check_connection(cfg))

    def _on_probe_done(self, seq: int, provider: str, kind: str, result) -> None:
        if seq != self._probe_seq:
            return  # superseded by a later probe
        self._set_probing(False)
        if provider != self.provider():
            self.test_result.setText("")  # answered for a provider no longer shown
            return
        if isinstance(result, Exception):
            self.test_result.setText(
                "<span style='%s'>%s</span>"
                % (_BAD, _escape(str(result)).replace("\n", "<br>"))
            )
            return
        if kind == "models":
            models = list(result or [])
            current = self.model_box.currentText().strip()
            self._fill(self.model_box, models, current)
            self._fill(self.alt_box, models, self.alt_box.currentText().strip())
            if not models:
                self.test_result.setText(
                    "<span style='%s'>The server listed no models.</span>"
                    % _BAD
                )
            elif current and not qgen.model_listed(current, models):
                self.test_result.setText(
                    "<span style='%s'>%d model%s listed — but %r isn't one "
                    "of them; pick from the list.</span>"
                    % (_BAD, len(models), "" if len(models) == 1 else "s", current)
                )
            else:
                self.test_result.setText(
                    "<span style='%s'>%d model%s listed.</span>"
                    % (_OK, len(models), "" if len(models) == 1 else "s")
                )
            return
        self.test_result.setText(
            "<span style='%s'>%s</span>" % (_OK, _escape(str(result)))
        )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
