"""Tests for provider presets and the hosted / remote transports.

All network calls are mocked - nothing here touches the internet.
"""

import io
import json
import urllib.error

import pytest

from snip_occlusion import qgen, qgen_providers


class _FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


_CARD_JSON = '[{"front": "Who prosecutes?", "back": "The Crown"}]'


# ------------------------------------------------------------ resolution


def test_every_preset_is_well_formed():
    keys = set()
    for p in qgen_providers.HOSTED:
        assert p.key not in keys, "duplicate preset key %s" % p.key
        keys.add(p.key)
        assert p.key == p.key.lower().replace("-", "_")
        assert p.base_url.startswith("https://")
        assert not p.base_url.endswith("/")
        assert p.key_url.startswith("https://")
        assert p.api in (qgen_providers.API_OPENAI, qgen_providers.API_OLLAMA)
        assert p.models and all(mid and desc for mid, desc in p.models)
        assert p.env_var.isupper()
        assert p.free_tier
    assert qgen_providers.valid_providers()[:2] == [
        "ollama",
        "openai_compatible",
    ]
    assert "groq" in qgen_providers.valid_providers()
    # the recommended provider leads the drop-down
    assert qgen_providers.HOSTED[0].key == "groq"


def test_preset_lookup_normalises():
    assert qgen_providers.preset("Groq").key == "groq"
    assert qgen_providers.preset("ollama-cloud").key == "ollama_cloud"
    assert qgen_providers.preset("ollama") is None
    assert qgen_providers.preset("") is None


def test_loopback_detection():
    assert qgen_providers.is_loopback("http://localhost:11434")
    assert qgen_providers.is_loopback("http://127.0.0.1:1234/v1")
    assert qgen_providers.is_loopback("http://127.5.0.1:1234/v1")
    assert qgen_providers.is_loopback("http://[::1]:11434")
    assert qgen_providers.is_loopback("http://[::ffff:127.0.0.1]:11434")
    assert qgen_providers.is_loopback("http://0.0.0.0:11434")
    assert not qgen_providers.is_loopback("http://192.168.1.20:11434")
    assert not qgen_providers.is_loopback("https://api.groq.com/openai/v1")
    # a NAME that merely starts with 127. resolves wherever it likes
    assert not qgen_providers.is_loopback("http://127.0.0.1.example.com:11434")
    assert not qgen_providers.is_loopback("http://127.example.com")
    assert not qgen_providers.is_loopback("http://localhost.example.com")
    assert not qgen_providers.is_loopback("")
    assert not qgen_providers.is_loopback("not a url")


def test_api_key_belongs_to_its_provider(monkeypatch):
    for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = {
        "qgen_provider": "groq",
        "qgen_api_key": "gsk_legacy",
        "qgen_api_keys": {"groq": "gsk_map", "openrouter": "sk-or"},
    }
    # the documented single key wins for the provider the config names
    assert qgen_providers.api_key_for(cfg, "groq") == "gsk_legacy"
    assert qgen_providers.api_key_for(cfg, "openrouter") == "sk-or"
    # ...and is never handed to any other provider
    assert qgen_providers.api_key_for(cfg, "ollama") == ""
    assert qgen_providers.api_key_for(cfg, "openai_compatible") == ""
    assert qgen_providers.api_key_for(cfg, "together") == ""
    # the Settings window rewrites qgen_api_key on every save, so after
    # switching to a remote Ollama it is empty and no hosted key goes there
    switched = dict(
        cfg,
        qgen_provider="ollama",
        qgen_api_key="",
        qgen_ollama_url="http://10.0.0.5:11434",
    )
    assert qgen_providers.resolve(switched).api_key == ""
    # environment fallback is per hosted preset only
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-or")
    assert qgen_providers.api_key_for({}, "openrouter") == "env-or"
    assert qgen_providers.api_key_for({}, "openai_compatible") == ""
    # a key saved for the local proxy case is used for local only
    local = {"qgen_provider": "ollama", "qgen_api_key": "proxy"}
    assert qgen_providers.resolve(local).api_key == "proxy"
    assert qgen_providers.api_key_for(local, "groq") == ""


def test_html_error_bodies_become_plain_text(monkeypatch):
    page = (b"<!DOCTYPE html><html><body><h1>502 Bad Gateway</h1>"
            b"<p>cloudflare</p><a href='x'>retry</a></body></html>")
    monkeypatch.setattr(qgen, "_urlopen", _http_error(502, page))
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text", {"qgen_provider": "groq", "qgen_api_key": "k"}
        )
    message = str(exc.value)
    assert "<" not in message and ">" not in message
    assert "502 Bad Gateway cloudflare retry" in message

    monkeypatch.setattr(
        qgen, "_urlopen",
        lambda request, timeout=None: _RawResponse(b"<html><b>oops</b></html>"),
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {})
    assert "did not return JSON" in str(exc.value)
    assert "<b>" not in str(exc.value)


class _RawResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_resolve_local_ollama_defaults():
    t = qgen_providers.resolve({})
    assert t.provider == "ollama"
    assert t.api == qgen_providers.API_OLLAMA
    assert t.base_url == "http://localhost:11434"
    assert t.model == "llama3.1:8b"
    assert not t.remote
    assert t.preset is None
    assert "this computer" in t.label
    assert qgen_providers.describe({}) == "on your machine (llama3.1:8b)"


def test_resolve_remote_ollama_is_marked_remote():
    t = qgen_providers.resolve(
        {"qgen_ollama_url": "http://192.168.1.20:11434/", "qgen_model": "x"}
    )
    assert t.remote
    assert t.base_url == "http://192.168.1.20:11434"  # trailing / dropped
    assert "192.168.1.20" in t.label
    assert qgen_providers.describe(
        {"qgen_ollama_url": "http://192.168.1.20:11434", "qgen_model": "x"}
    ).startswith("via 192.168.1.20")


def test_resolve_custom_server():
    t = qgen_providers.resolve(
        {
            "qgen_provider": "openai-compatible",
            "qgen_openai_base_url": "http://localhost:1234/v1/",
            "qgen_model": "local-model",
            "qgen_api_key": " k ",
        }
    )
    assert t.api == qgen_providers.API_OPENAI
    assert t.base_url == "http://localhost:1234/v1"
    assert not t.remote
    assert t.api_key == "k"
    remote = qgen_providers.resolve(
        {
            "qgen_provider": "openai_compatible",
            "qgen_openai_base_url": "https://gpu.example.com/v1",
        }
    )
    assert remote.remote and remote.label == "the server at gpu.example.com"


def test_resolve_hosted_preset(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    t = qgen_providers.resolve({"qgen_provider": "groq"})
    assert t.remote and t.preset.key == "groq"
    assert t.base_url == "https://api.groq.com/openai/v1"
    assert t.model == qgen_providers.preset("groq").models[0][0]
    assert t.api_key == ""
    assert t.key_url == "https://console.groq.com/keys"
    assert t.host == "api.groq.com"
    assert qgen_providers.describe(
        {"qgen_provider": "groq", "qgen_model": "llama-3.1-8b-instant"}
    ) == "via Groq (llama-3.1-8b-instant)"
    # the environment can supply the key, config wins when both are set
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert qgen_providers.resolve({"qgen_provider": "groq"}).api_key == "from-env"
    assert (
        qgen_providers.resolve(
            {"qgen_provider": "groq", "qgen_api_key": "from-config"}
        ).api_key
        == "from-config"
    )


def test_resolve_unknown_provider():
    with pytest.raises(qgen_providers.UnknownProvider):
        qgen_providers.resolve({"qgen_provider": "claude"})
    assert "unknown provider" in qgen_providers.describe(
        {"qgen_provider": "claude"}
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {"qgen_provider": "claude"})
    assert "groq" in str(exc.value)  # the valid options are listed


# ------------------------------------------------------------ transports


def test_hosted_openai_preset_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            {"choices": [{"message": {"content": _CARD_JSON}}]}
        )

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    cards = qgen.generate_cards(
        "The Crown prosecutes criminal cases.",
        {
            "qgen_provider": "openrouter",
            "qgen_model": "meta-llama/llama-3.3-70b-instruct",
            "qgen_api_key": "sk-or-123",
            "qgen_max_cards": 2,
        },
    )
    assert cards[0]["back"] == "The Crown"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-or-123"
    # OpenRouter's optional attribution headers ride along
    assert captured["headers"]["X-title"] == "Snip Occlusion"
    assert captured["body"]["model"] == "meta-llama/llama-3.3-70b-instruct"
    assert captured["body"]["max_tokens"] == 2 * 256 + 128
    assert "keep_alive" not in captured["body"]


def test_hosted_ollama_cloud_preset_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            {"message": {"role": "assistant", "content": _CARD_JSON}}
        )

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    monkeypatch.setattr(qgen.os, "cpu_count", lambda: 8)
    qgen.generate_cards(
        "The Crown prosecutes criminal cases.",
        {
            "qgen_provider": "ollama_cloud",
            "qgen_model": "gpt-oss:120b",
            "qgen_api_key": "ol-key",
        },
    )
    assert captured["url"] == "https://ollama.com/api/chat"
    assert captured["headers"]["Authorization"] == "Bearer ol-key"
    assert captured["body"]["model"] == "gpt-oss:120b"
    # the cloud manages its own fleet: no keep_alive, no thread limit
    assert "keep_alive" not in captured["body"]
    assert "num_thread" not in captured["body"].get("options", {})


def test_remote_ollama_sends_key_and_keep_alive(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            {"message": {"role": "assistant", "content": _CARD_JSON}}
        )

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    qgen.generate_cards(
        "The Crown prosecutes criminal cases.",
        {
            "qgen_ollama_url": "https://mybox.example.com",
            "qgen_api_key": "proxy-token",  # e.g. a reverse proxy's token
        },
    )
    assert captured["headers"]["Authorization"] == "Bearer proxy-token"
    assert captured["body"]["keep_alive"] == "30m"
    # and a local Ollama gets no Authorization header at all
    qgen.generate_cards("The Crown prosecutes criminal cases.", {})
    assert "Authorization" not in captured["headers"]


def test_hosted_needs_a_model_for_custom_servers(monkeypatch):
    monkeypatch.setattr(
        qgen, "_urlopen",
        lambda request, timeout=None: _FakeResponse(
            {"choices": [{"message": {"content": _CARD_JSON}}]}
        ),
    )
    # a preset always has a default model
    assert qgen.generate_cards("The Crown prosecutes.", {"qgen_provider": "groq"})


def test_openai_style_error_body_is_surfaced(monkeypatch):
    monkeypatch.setattr(
        qgen, "_urlopen",
        lambda request, timeout=None: _FakeResponse(
            {"error": {"message": "model decommissioned", "code": 400}}
        ),
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text", {"qgen_provider": "groq", "qgen_api_key": "k"}
        )
    assert "Groq reported an error: model decommissioned" in str(exc.value)


def _http_error(code, body=b"{}"):
    def fail(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, code, "err", {}, io.BytesIO(body)
        )

    return fail


@pytest.mark.parametrize(
    "code,needle",
    [
        (401, "rejected the API key"),
        (403, "rejected the API key"),
        (402, "no credit left"),
        (404, "could not find that endpoint or model"),
        (429, "rate-limiting"),
        (500, "HTTP 500"),
    ],
)
def test_hosted_http_errors_are_explained(monkeypatch, code, needle):
    monkeypatch.setattr(
        qgen, "_urlopen", _http_error(code, b'{"x": 1}')
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text",
            {
                "qgen_provider": "groq",
                "qgen_api_key": "bad",
                "qgen_model": "llama-3.1-8b-instant",
            },
        )
    message = str(exc.value)
    assert needle in message
    assert "Groq" in message
    if code in (401, 403):
        assert "console.groq.com" in message  # where to get a key
    if code == 404:
        assert "llama-3.1-8b-instant" in message


def test_local_401_has_no_key_url(monkeypatch):
    monkeypatch.setattr(qgen, "_urlopen", _http_error(401))
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text",
            {
                "qgen_provider": "openai_compatible",
                "qgen_model": "m",
                "qgen_openai_base_url": "http://localhost:8000/v1",
            },
        )
    assert "wants an API key" in str(exc.value)
    assert "console." not in str(exc.value)


def test_unreachable_hosted_service_hint(monkeypatch):
    def fail(request, timeout=None):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(qgen, "_urlopen", fail)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text", {"qgen_provider": "cerebras", "qgen_api_key": "k"}
        )
    message = str(exc.value)
    assert "Could not reach Cerebras" in message
    assert "internet connection" in message
    assert "ollama pull" not in message  # not local advice


def test_unreachable_remote_ollama_hint(monkeypatch):
    def fail(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(qgen, "_urlopen", fail)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text", {"qgen_ollama_url": "http://10.0.0.5:11434"}
        )
    assert "OLLAMA_HOST=0.0.0.0" in str(exc.value)


def test_timeouts_are_provider_aware(monkeypatch):
    def slow(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(qgen, "_urlopen", slow)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {})
    assert "local model took too long" in str(exc.value)
    assert "hosted service" in str(exc.value)  # the way out is mentioned
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards(
            "text", {"qgen_provider": "groq", "qgen_api_key": "k"}
        )
    assert "Groq took too long" in str(exc.value)

    # urllib wraps socket timeouts in URLError on some platforms
    def slow_urlerror(request, timeout=None):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(qgen, "_urlopen", slow_urlerror)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {})
    assert "took too long" in str(exc.value)


# ------------------------------------------------- list_models / check


def test_list_models_ollama_and_openai_shapes(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["auth"] = request.headers.get("Authorization")
        if request.full_url.endswith("/api/tags"):
            return _FakeResponse(
                {"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5:7b"}]}
            )
        if "together" in request.full_url:
            return _FakeResponse([{"id": "b-model"}, {"id": "a-model"}])
        return _FakeResponse({"data": [{"id": "llama-3.1-8b-instant"}]})

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    assert qgen.list_models({}) == ["llama3.1:8b", "qwen2.5:7b"]
    assert seen["url"] == "http://localhost:11434/api/tags"
    assert seen["method"] == "GET" and seen["auth"] is None
    assert qgen.list_models(
        {"qgen_provider": "groq", "qgen_api_key": "k"}
    ) == ["llama-3.1-8b-instant"]
    assert seen["url"] == "https://api.groq.com/openai/v1/models"
    assert seen["auth"] == "Bearer k"
    # a bare list (Together's shape) works too, sorted case-insensitively
    assert qgen.list_models(
        {"qgen_provider": "together", "qgen_api_key": "k"}
    ) == ["a-model", "b-model"]


def test_check_connection_reports_success(monkeypatch):
    def fake_urlopen(request, timeout=None):
        if request.full_url.endswith("/models"):
            return _FakeResponse({"data": [{"id": "llama-3.1-8b-instant"}]})
        return _FakeResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    verdict = qgen.check_connection(
        {
            "qgen_provider": "groq",
            "qgen_api_key": "k",
            "qgen_model": "llama-3.1-8b-instant",
        }
    )
    assert verdict.startswith("✓ Groq answered with llama-3.1-8b-instant")
    assert "1 model listed" in verdict
    assert "'OK'" in verdict


def test_check_connection_needs_key_for_hosted(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.check_connection({"qgen_provider": "groq"})
    assert "needs an API key" in str(exc.value)
    assert "console.groq.com" in str(exc.value)


def test_model_listed_allows_latest_tag():
    assert qgen.model_listed("llama3.2", ["llama3.2:latest"])
    assert qgen.model_listed("llama3.2:latest", ["llama3.2"])
    assert qgen.model_listed("llama3.1:8b", ["llama3.1:8b", "x"])
    assert not qgen.model_listed("llama3.1:8b", ["llama3.1:latest"])
    assert not qgen.model_listed("", ["x"])


def test_half_typed_ipv6_url_resolves():
    for url in ("http://[", "http://[::1", "http://loc[al"):
        t = qgen_providers.resolve({"qgen_ollama_url": url})
        assert t.host == url and t.label
        assert qgen_providers.describe({"qgen_ollama_url": url})
        c = qgen_providers.resolve(
            {"qgen_provider": "openai_compatible", "qgen_openai_base_url": url}
        )
        assert c.label.endswith(url)


def test_check_connection_bounds_the_chat_probe(monkeypatch):
    timeouts = []

    def fake_urlopen(request, timeout=None):
        timeouts.append(timeout)
        if request.full_url.endswith("/api/tags"):
            return _FakeResponse({"models": [{"name": "llama3.2:latest"}]})
        return _FakeResponse({"message": {"content": "OK"}})

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    verdict = qgen.check_connection(
        {"qgen_model": "llama3.2", "qgen_timeout_seconds": 300}, timeout=12
    )
    assert verdict.startswith("✓")  # untagged name accepted
    assert timeouts == [12, 12]  # listing and chat both bounded by the probe


def test_check_connection_local_missing_model(monkeypatch):
    monkeypatch.setattr(
        qgen, "_urlopen",
        lambda request, timeout=None: _FakeResponse(
            {"models": [{"name": "llama3.2:3b"}]}
        ),
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.check_connection({"qgen_model": "llama3.1:8b"})
    assert "ollama pull llama3.1:8b" in str(exc.value)
    assert "llama3.2:3b" in str(exc.value)


def test_check_connection_survives_missing_listing(monkeypatch):
    def fake_urlopen(request, timeout=None):
        if request.full_url.endswith("/models"):
            raise urllib.error.HTTPError(request.full_url, 404, "no", {}, None)
        return _FakeResponse({"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    verdict = qgen.check_connection(
        {
            "qgen_provider": "openai_compatible",
            "qgen_openai_base_url": "http://localhost:8080/v1",
            "qgen_model": "m",
        }
    )
    assert verdict.startswith("✓")
    assert "listed" not in verdict


# --------------------------------------------------- thinking models


def test_reasoning_models_are_asked_to_think_briefly(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode())
        if request.full_url.endswith("/chat/completions"):
            return _FakeResponse(
                {"choices": [{"message": {"content": _CARD_JSON}}]}
            )
        return _FakeResponse(
            {"message": {"role": "assistant", "content": _CARD_JSON}}
        )

    monkeypatch.setattr(qgen, "_urlopen", fake_urlopen)
    assert qgen_providers.is_reasoning_model("openai/gpt-oss-120b")
    assert qgen_providers.is_reasoning_model("gpt-oss:20b")
    assert qgen_providers.is_reasoning_model("qwen/qwen3.6-27b")
    assert not qgen_providers.is_reasoning_model("llama-3.3-70b-versatile")
    assert qgen_providers.is_gpt_oss("accounts/fireworks/models/gpt-oss-20b")
    assert not qgen_providers.is_gpt_oss("qwen3:32b")

    base = {"qgen_api_key": "k", "qgen_max_cards": 4}
    plain_cap = 4 * 256 + 128
    # OpenAI-style field on Groq
    qgen.generate_cards(
        "text", dict(base, qgen_provider="groq", qgen_model="openai/gpt-oss-20b")
    )
    assert captured["body"]["reasoning_effort"] == "low"
    assert "reasoning" not in captured["body"]
    # hidden reasoning tokens share the budget: several times the room
    assert captured["body"]["max_tokens"] == plain_cap * 4 + 1024
    # OpenRouter's object form
    qgen.generate_cards(
        "text",
        dict(base, qgen_provider="openrouter", qgen_model="openai/gpt-oss-120b"),
    )
    assert captured["body"]["reasoning"] == {"effort": "low"}
    assert "reasoning_effort" not in captured["body"]
    # a non-thinking model gets neither, and the plain cap
    qgen.generate_cards(
        "text",
        dict(base, qgen_provider="groq", qgen_model="llama-3.3-70b-versatile"),
    )
    assert "reasoning_effort" not in captured["body"]
    assert captured["body"]["max_tokens"] == plain_cap
    # custom servers are never sent provider-specific fields
    qgen.generate_cards(
        "text",
        dict(
            base,
            qgen_provider="openai_compatible",
            qgen_model="gpt-oss-20b",
            qgen_openai_base_url="http://localhost:8000/v1",
        ),
    )
    assert "reasoning_effort" not in captured["body"]
    assert "reasoning" not in captured["body"]
    # Ollama (local or cloud) uses its own "think" switch
    qgen.generate_cards("text", dict(base, qgen_model="gpt-oss:20b"))
    assert captured["body"]["think"] == "low"
    assert captured["body"]["options"]["num_predict"] == plain_cap * 4 + 1024
    qgen.generate_cards("text", dict(base, qgen_model="llama3.1:8b"))
    assert "think" not in captured["body"]
    # other thinking models: Ollama rejects a string level and Groq's
    # Qwen wants a different vocabulary, so only the cap is enlarged
    qgen.generate_cards("text", dict(base, qgen_model="qwen3:32b"))
    assert "think" not in captured["body"]
    assert captured["body"]["options"]["num_predict"] == plain_cap * 4 + 1024
    qgen.generate_cards(
        "text", dict(base, qgen_provider="groq", qgen_model="qwen/qwen3.6-27b")
    )
    assert "reasoning_effort" not in captured["body"]
    assert captured["body"]["max_tokens"] == plain_cap * 4 + 1024


# -------------------------------------------------------- redirects


def test_redirects_are_refused_and_explained():
    """A real local HTTP server: the Bearer key must not follow a redirect.

    urllib's default behaviour re-sends the request (Authorization header
    included) to the Location target, so a misconfigured or malicious
    base URL could leak the key to another host. The add-on refuses the
    redirect and tells the user which address to configure instead.
    """
    import http.server
    import threading

    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append((self.path, self.headers.get("Authorization")))
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/elsewhere/v1")
            self.end_headers()

        def do_GET(self):
            self.do_POST()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(qgen.QGenError) as exc:
            qgen.generate_cards(
                "text",
                {
                    "qgen_provider": "openai_compatible",
                    "qgen_openai_base_url": "http://127.0.0.1:%d/v1" % port,
                    "qgen_model": "m",
                    "qgen_api_key": "secret-token",
                },
            )
    finally:
        server.shutdown()
        server.server_close()
    message = str(exc.value)
    assert "redirected the request (HTTP 302)" in message
    assert "http://127.0.0.1:9/elsewhere/v1" in message  # the target is named
    assert "secret-token" not in message
    # exactly one request reached the server, and nothing was re-sent
    assert hits == [("/v1/chat/completions", "Bearer secret-token")]
