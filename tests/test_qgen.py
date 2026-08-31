"""Tests for AI question generation (server mocked - no network)."""

import io
import json
import urllib.error

import pytest

from snip_occlusion import qgen


def test_prompt_contains_text_and_limit():
    p = qgen.build_prompt("Private members bills are brought forward.", 5)
    assert "Private members bills" in p
    assert "up to 5" in p
    assert "JSON array" in p


def test_parse_cards_plain_and_fenced():
    raw = '[{"front": "Who?", "back": "Individual MPs"}]'
    assert qgen.parse_cards(raw) == [
        {"front": "Who?", "back": "Individual MPs"}
    ]
    fenced = "```json\n%s\n```" % raw
    assert qgen.parse_cards(fenced)[0]["back"] == "Individual MPs"
    chatty = "Here you go!\n%s\nEnjoy." % raw
    assert len(qgen.parse_cards(chatty)) == 1


def test_parse_cards_skips_junk_and_errors():
    mixed = '[{"front": "Q", "back": "A"}, {"front": ""}, "noise"]'
    assert qgen.parse_cards(mixed) == [{"front": "Q", "back": "A"}]
    with pytest.raises(qgen.QGenError):
        qgen.parse_cards("no json here")
    with pytest.raises(qgen.QGenError):
        qgen.parse_cards("[]")


class _FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


_CARD_JSON = (
    '[{"front": "Who brings forward private members\' bills?", '
    '"back": "Individual MPs"}]'
)


def test_generate_cards_via_ollama(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return _FakeResponse(
            {"message": {"role": "assistant", "content": _CARD_JSON}}
        )

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fake_urlopen)
    cards = qgen.generate_cards(
        "Private members bills are brought forward by individual MPs.",
        {"qgen_max_cards": 6},  # ollama is the default provider
    )
    assert cards[0]["back"] == "Individual MPs"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["model"] == qgen.DEFAULT_MODEL
    assert captured["body"]["stream"] is False
    assert captured["body"]["keep_alive"] == "30m"
    assert "individual MPs" in captured["body"]["messages"][0]["content"]
    assert captured["timeout"] == qgen.DEFAULT_TIMEOUT_S


def test_generate_cards_via_openai_compatible(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            {"choices": [{"message": {"content": _CARD_JSON}}]}
        )

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fake_urlopen)
    cards = qgen.generate_cards(
        "Some slide text.",
        {
            "qgen_provider": "openai_compatible",
            "qgen_openai_base_url": "http://localhost:1234/v1",
            "qgen_model": "local-model",
            "qgen_api_key": "secret123",
        },
    )
    assert cards[0]["back"] == "Individual MPs"
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["auth"] == "Bearer secret123"
    assert captured["body"]["model"] == "local-model"


def test_unknown_provider_raises():
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {"qgen_provider": "claude"})
    assert "qgen_provider" in str(exc.value)


def test_ollama_missing_model_error(monkeypatch):
    monkeypatch.setattr(
        qgen.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(
            {"error": 'model "llama3.1:8b" not found'}
        ),
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {})
    assert "ollama pull" in str(exc.value)


def test_generate_cards_connection_and_http_errors(monkeypatch):
    def fail_conn(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fail_conn)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {})
    # the error walks the user through installing/starting Ollama
    assert "ollama.com" in str(exc.value)
    assert "ollama pull" in str(exc.value)

    def fail_500(request, timeout=None):
        raise urllib.error.HTTPError(
            "http://localhost:11434/api/chat",
            500,
            "boom",
            {},
            io.BytesIO(b"{}"),
        )

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fail_500)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {})
    assert "500" in str(exc.value)


def test_empty_text_raises():
    with pytest.raises(qgen.QGenError):
        qgen.generate_cards("   ", {})
