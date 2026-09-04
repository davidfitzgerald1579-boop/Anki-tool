"""Tests for the AI-provider section of the Settings window (offscreen)."""

import pytest

from snip_occlusion import qgen, qgen_providers
from snip_occlusion.qgen_settings import ProviderSettings


@pytest.fixture
def sync_probes(monkeypatch):
    """Run the widget's background probes inline, on the calling thread."""

    def run(self, kind, fn):
        self._probe_seq += 1
        try:
            result = fn()
        except Exception as exc:
            result = exc
        self._on_probe_done(self._probe_seq, self.provider(), kind, result)

    monkeypatch.setattr(ProviderSettings, "_run_in_background", run)


def test_defaults_load_as_local(qapp):
    w = ProviderSettings({})
    assert w.mode() == "local"
    assert w.local_pane.isVisibleTo(w) and not w.hosted_pane.isVisibleTo(w)
    assert w.model_box.currentText() == "llama3.1:8b"
    assert w.ollama_url.text() == qgen.DEFAULT_OLLAMA_URL
    assert not w.bakeoff_check.isChecked()
    assert not w.alt_box.isEnabled()
    assert "Nothing leaves this computer" in w.privacy.text()
    v = w.values()
    assert v["qgen_provider"] == "ollama"
    assert v["qgen_model"] == "llama3.1:8b"
    assert v["qgen_bakeoff"] is False
    assert v["qgen_bakeoff_models"] == ["llama3.1:8b", "llama3.2:3b"]
    assert w.problem() == ""


def test_hosted_config_loads_and_saves(qapp, monkeypatch):
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    w = ProviderSettings(
        {
            "qgen_provider": "cerebras",
            "qgen_model": "llama-3.3-70b",
            "qgen_api_key": "csk-1",
            "qgen_bakeoff": True,
            "qgen_bakeoff_models": ["llama-3.3-70b", "llama3.1-8b"],
        }
    )
    assert w.mode() == "hosted"
    assert w.service_box.currentData() == "cerebras"
    assert w.model_box.currentText() == "llama-3.3-70b"
    assert w.api_key.text() == "csk-1"
    assert w.bakeoff_check.isChecked() and w.alt_box.isEnabled()
    assert w.alt_box.currentText() == "llama3.1-8b"
    assert "cloud.cerebras.ai" in w.key_link.text()
    assert "api.cerebras.ai" in w.privacy.text()
    assert "Cerebras" in w.privacy.text()
    v = w.values()
    assert v == {
        "qgen_provider": "cerebras",
        "qgen_model": "llama-3.3-70b",
        "qgen_ollama_url": qgen.DEFAULT_OLLAMA_URL,
        "qgen_openai_base_url": qgen.DEFAULT_OPENAI_BASE_URL,
        "qgen_api_key": "csk-1",
        "qgen_api_keys": {"cerebras": "csk-1"},
        "qgen_bakeoff": True,
        "qgen_bakeoff_models": ["llama-3.3-70b", "llama3.1-8b"],
    }
    assert w.problem() == ""


def test_switching_to_hosted_offers_preset_models(qapp, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    w = ProviderSettings({"qgen_model": "qwen2.5:7b"})
    w.hosted_radio.setChecked(True)
    assert w.mode() == "hosted"
    assert w.hosted_pane.isVisibleTo(w) and not w.local_pane.isVisibleTo(w)
    groq = qgen_providers.preset("groq")
    assert w.service_box.currentData() == "groq"  # recommended = first
    assert w.model_box.currentText() == groq.models[0][0]
    listed = [w.model_box.itemText(i) for i in range(w.model_box.count())]
    assert listed == [m for m, _ in groq.models]
    # the free-tier note and key link follow the service
    assert "console.groq.com" in w.key_link.text()
    assert "Free tier" in w.service_note.text()
    # no key yet -> can't save
    assert "needs an API key" in w.problem()
    w.api_key.setText("gsk_abc")
    assert w.problem() == ""
    assert w.values()["qgen_api_key"] == "gsk_abc"
    assert w.values()["qgen_provider"] == "groq"
    # switching back restores the local model that was there before
    w.local_radio.setChecked(True)
    assert w.model_box.currentText() == "qwen2.5:7b"
    assert w.values()["qgen_provider"] == "ollama"
    # ...and forward again remembers the Groq choice
    w.hosted_radio.setChecked(True)
    assert w.model_box.currentText() == groq.models[0][0]


def test_environment_key_satisfies_hosted(qapp, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    w = ProviderSettings({"qgen_provider": "groq"})
    assert w.api_key.text() == ""
    assert w.problem() == ""  # the environment supplies it


def test_changing_service_changes_models_and_privacy(qapp, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    w = ProviderSettings({"qgen_provider": "groq", "qgen_api_key": "k"})
    w.service_box.setCurrentIndex(w.service_box.findData("openrouter"))
    assert w.provider() == "openrouter"
    assert w.model_box.currentText() == (
        qgen_providers.preset("openrouter").models[0][0]
    )
    assert "openrouter.ai" in w.privacy.text()
    assert w.values()["qgen_provider"] == "openrouter"


def test_custom_server_pane(qapp):
    w = ProviderSettings(
        {
            "qgen_provider": "openai_compatible",
            "qgen_openai_base_url": "https://gpu.example.com/v1",
            "qgen_model": "meta-llama/Llama-3.1-8B-Instruct",
            "qgen_api_key": "tok",
        }
    )
    assert w.mode() == "custom"
    assert w.custom_url.text() == "https://gpu.example.com/v1"
    assert w.custom_key.text() == "tok"
    assert "gpu.example.com" in w.privacy.text()
    w.custom_url.setText("http://localhost:8000/v1")
    assert "Nothing leaves this computer" in w.privacy.text()
    v = w.values()
    assert v["qgen_provider"] == "openai_compatible"
    assert v["qgen_openai_base_url"] == "http://localhost:8000/v1"
    assert v["qgen_api_key"] == "tok"
    w.model_box.setEditText("")
    assert "Choose a model" in w.problem()


def test_remote_ollama_url_is_flagged(qapp):
    w = ProviderSettings({})
    w.ollama_url.setText("http://192.168.1.20:11434")
    assert "192.168.1.20" in w.privacy.text()
    assert w.values()["qgen_ollama_url"] == "http://192.168.1.20:11434"
    w.ollama_url.setText("")
    assert w.values()["qgen_ollama_url"] == qgen.DEFAULT_OLLAMA_URL


def test_bakeoff_needs_a_distinct_partner(qapp):
    w = ProviderSettings({})
    w.bakeoff_check.setChecked(True)
    assert w.values()["qgen_bakeoff"] is True
    assert w.values()["qgen_bakeoff_models"] == ["llama3.1:8b", "llama3.2:3b"]
    assert w.problem() == ""
    w.alt_box.setEditText("llama3.1:8b")  # same as the main model
    assert w.values()["qgen_bakeoff"] is False
    assert "qgen_bakeoff_models" not in w.values()
    assert "second, different model" in w.problem()
    w.alt_box.setEditText("")
    assert "second, different model" in w.problem()
    w.bakeoff_check.setChecked(False)
    assert w.problem() == ""


def test_bakeoff_partner_follows_the_provider(qapp, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    w = ProviderSettings(
        {
            "qgen_bakeoff": True,
            "qgen_bakeoff_models": ["llama3.1:8b", "llama3.2:3b"],
        }
    )
    assert w.alt_box.currentText() == "llama3.2:3b"
    # switching to Groq must not keep an Ollama partner: half of all
    # generations would 404
    w.hosted_radio.setChecked(True)
    groq = qgen_providers.preset("groq")
    assert w.model_box.currentText() == groq.models[0][0]
    assert w.alt_box.currentText() == groq.models[1][0]
    w.api_key.setText("k")
    assert w.values()["qgen_bakeoff_models"] == [
        groq.models[0][0],
        groq.models[1][0],
    ]
    # a custom server has no suggestions: the partner is left blank,
    # and a ticked bake-off then refuses to save
    w.custom_radio.setChecked(True)
    assert w.alt_box.currentText() == ""
    w.model_box.setEditText("m")
    assert "second, different model" in w.problem()
    # ...and coming back restores each provider's own pair
    w.local_radio.setChecked(True)
    assert w.model_box.currentText() == "llama3.1:8b"
    assert w.alt_box.currentText() == "llama3.2:3b"


def test_half_typed_ipv6_url_does_not_raise(qapp):
    w = ProviderSettings({})
    for text in ("http://[", "http://[::1", "http://[::1]", "http://[::1]:11434"):
        w.ollama_url.setText(text)  # textChanged -> privacy refresh
        assert w.values()["qgen_ollama_url"] == text
    assert "Nothing leaves this computer" in w.privacy.text()
    w.custom_radio.setChecked(True)
    w.custom_url.setText("http://[")
    assert w.problem() in ("", "Choose a model (or press Fetch list).")


def test_stale_probe_answers_are_dropped(qapp, monkeypatch):
    """A slow reply for provider A must not land on provider B's list."""
    pending = []

    def run(self, kind, fn):
        self._probe_seq += 1
        pending.append((self._probe_seq, self.provider(), kind, fn))

    monkeypatch.setattr(ProviderSettings, "_run_in_background", run)
    monkeypatch.setattr(qgen, "list_models", lambda cfg: ["llama3.1:8b", "x:7b"])
    w = ProviderSettings({})
    w.fetch_btn.click()
    assert not w.fetch_btn.isEnabled()
    w.hosted_radio.setChecked(True)  # user moves on before the reply
    seq, provider, kind, fn = pending.pop()
    w._on_probe_done(seq, provider, kind, fn())
    groq = qgen_providers.preset("groq")
    listed = [w.model_box.itemText(i) for i in range(w.model_box.count())]
    assert listed == [m for m, _ in groq.models]  # untouched
    assert w.fetch_btn.isEnabled()  # but the buttons are back
    # a superseded probe (an older seq) is ignored entirely; a second
    # click is refused while one is in flight, so simulate the first
    # one being abandoned
    w.fetch_btn.click()
    w._set_probing(False)
    w.fetch_btn.click()
    first, second = pending[-2], pending[-1]
    assert first[0] < second[0]
    w._on_probe_done(first[0], first[1], first[2], ["stale"])
    assert not w.fetch_btn.isEnabled()  # still waiting for the latest
    w._on_probe_done(second[0], second[1], second[2], ["fresh"])
    assert [w.model_box.itemText(i) for i in range(w.model_box.count())] == ["fresh"]


def test_fetch_accepts_untagged_ollama_name(qapp, sync_probes, monkeypatch):
    monkeypatch.setattr(qgen, "list_models", lambda cfg: ["llama3.2:latest"])
    w = ProviderSettings({"qgen_model": "llama3.2"})
    w.fetch_btn.click()
    assert "isn't one of them" not in w.test_result.text()
    assert "1 model listed" in w.test_result.text()


def test_fetch_models_fills_the_lists(qapp, sync_probes, monkeypatch):
    seen = {}

    def fake_list(cfg):
        seen["cfg"] = cfg
        return ["llama3.1:8b", "mistral:7b", "qwen2.5:7b"]

    monkeypatch.setattr(qgen, "list_models", fake_list)
    w = ProviderSettings({"qgen_model": "mistral:7b"})
    w.ollama_url.setText("http://10.0.0.5:11434")
    w.fetch_btn.click()
    # probed with the widget's CURRENT (unsaved) choices
    assert seen["cfg"]["qgen_ollama_url"] == "http://10.0.0.5:11434"
    listed = [w.model_box.itemText(i) for i in range(w.model_box.count())]
    assert listed == ["llama3.1:8b", "mistral:7b", "qwen2.5:7b"]
    assert w.model_box.currentText() == "mistral:7b"  # entry kept
    assert "3 models listed" in w.test_result.text()
    assert w.fetch_btn.isEnabled() and w.test_btn.isEnabled()
    # the partner list is refreshed too
    alt = [w.alt_box.itemText(i) for i in range(w.alt_box.count())]
    assert alt == listed


def test_fetch_warns_when_current_model_is_missing(qapp, sync_probes, monkeypatch):
    monkeypatch.setattr(qgen, "list_models", lambda cfg: ["llama3.2:3b"])
    w = ProviderSettings({"qgen_model": "llama3.1:8b"})
    w.fetch_btn.click()
    assert "isn't one of them" in w.test_result.text()
    assert w.model_box.currentText() == "llama3.1:8b"  # not silently changed


def test_probe_errors_are_shown_not_raised(qapp, sync_probes, monkeypatch):
    def boom(cfg):
        raise qgen.QGenError("Could not reach <server>")

    monkeypatch.setattr(qgen, "check_connection", boom)
    w = ProviderSettings({})
    w.test_btn.click()
    assert "Could not reach &lt;server&gt;" in w.test_result.text()
    assert w.test_btn.isEnabled()
    monkeypatch.setattr(qgen, "check_connection", lambda cfg: "✓ fine")
    w.test_btn.click()
    assert "✓ fine" in w.test_result.text()


# ------------------------------------------------------- key isolation


def test_a_hosted_key_never_follows_the_user_to_another_server(qapp, monkeypatch):
    """A Groq key must not ride along to a LAN Ollama, a custom server
    or another hosted service - the exact leak the review found."""
    for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    w = ProviderSettings({"qgen_provider": "groq", "qgen_api_key": "gsk_SECRET"})
    assert w.api_key.text() == "gsk_SECRET"
    # -> local pane, pointed at another machine: empty key, none sent
    w.local_radio.setChecked(True)
    w.ollama_url.setText("http://192.168.1.20:11434")
    assert w.local_key.text() == ""
    v = w.values()
    assert v["qgen_api_key"] == ""
    assert v["qgen_api_keys"] == {"groq": "gsk_SECRET"}  # kept for Groq
    assert qgen_providers.resolve(w.probe_config()).api_key == ""
    # -> custom pane: box empty too
    w.custom_radio.setChecked(True)
    assert w.custom_key.text() == ""
    w.custom_url.setText("http://10.0.0.7:1234/v1")
    assert qgen_providers.resolve(w.probe_config()).api_key == ""
    # -> another hosted service: box empty, and Save refuses until filled
    w.hosted_radio.setChecked(True)
    assert w.api_key.text() == "gsk_SECRET"  # Groq again: its own key
    w.service_box.setCurrentIndex(w.service_box.findData("openrouter"))
    assert w.api_key.text() == ""
    assert "needs an API key" in w.problem()
    w.api_key.setText("sk-or-1")
    assert w.values()["qgen_api_key"] == "sk-or-1"
    assert w.values()["qgen_api_keys"] == {
        "groq": "gsk_SECRET",
        "openrouter": "sk-or-1",
    }
    # back to Groq: its key is still there
    w.service_box.setCurrentIndex(w.service_box.findData("groq"))
    assert w.api_key.text() == "gsk_SECRET"
    assert w.values()["qgen_api_key"] == "gsk_SECRET"


def test_local_pane_key_is_for_a_proxy(qapp):
    w = ProviderSettings({})
    w.ollama_url.setText("https://mybox.example.com")
    w.local_key.setText("proxy-token")
    v = w.values()
    assert v["qgen_provider"] == "ollama"
    assert v["qgen_api_key"] == "proxy-token"
    assert v["qgen_api_keys"] == {"ollama": "proxy-token"}
    assert "mybox.example.com" in w.privacy.text()
    assert "only ever sent to mybox.example.com" in w.privacy.text()
    # reloading from that saved config puts the key back in the local box
    w2 = ProviderSettings(v)
    assert w2.local_key.text() == "proxy-token"
    assert w2.api_key.text() == "" and w2.custom_key.text() == ""
    # clearing the box on purpose drops the stored key
    w2.local_key.setText("")
    assert w2.values()["qgen_api_keys"] == {}


def test_stored_key_map_survives_a_session_without_edits(qapp, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    w = ProviderSettings(
        {
            "qgen_provider": "ollama",
            "qgen_api_keys": {"groq": "gsk_1", "openai_compatible": "tok"},
        }
    )
    assert w.local_key.text() == "" and w.custom_key.text() == "tok"
    v = w.values()  # untouched: everything comes back out
    assert v["qgen_api_key"] == ""
    assert v["qgen_api_keys"] == {"groq": "gsk_1", "openai_compatible": "tok"}
    w.hosted_radio.setChecked(True)
    assert w.api_key.text() == "gsk_1"
    assert w.problem() == ""


def test_privacy_note_mentions_prefetch_and_examples(qapp, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    w = ProviderSettings({"qgen_provider": "groq", "qgen_api_key": "k"})
    text = w.privacy.text()
    assert "the moment a snip lands" in text
    assert "example cards" in text
    assert "never the image" in text
    assert "only ever sent to Groq" in text
    w2 = ProviderSettings(
        {"qgen_provider": "groq", "qgen_api_key": "k", "qgen_prefetch": False}
    )
    assert "when you ask for suggestions" in w2.privacy.text()
