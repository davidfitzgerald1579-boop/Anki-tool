"""Tests for AI question generation (API mocked - no network)."""

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


def test_missing_api_key_raises_helpful_error():
    assert not qgen.has_api_key({"anthropic_api_key": " "})
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("some text", {"anthropic_api_key": ""})
    assert "console.anthropic.com" in str(exc.value)


class _FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_generate_cards_request_and_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            {
                "stop_reason": "end_turn",
                "content": [
                    {
                        "type": "text",
                        "text": '[{"front": "Who brings forward private '
                        "members' bills?\", \"back\": \"Individual MPs\"}]",
                    }
                ],
            }
        )

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fake_urlopen)
    cards = qgen.generate_cards(
        "Private members bills are brought forward by individual MPs.",
        {"anthropic_api_key": "sk-test", "qgen_max_cards": 6},
    )
    assert cards[0]["back"] == "Individual MPs"
    assert captured["url"] == qgen.API_URL
    assert captured["headers"]["X-api-key"] == "sk-test"
    assert captured["headers"]["Anthropic-version"] == qgen.API_VERSION
    assert captured["headers"]["Anthropic-beta"] == qgen.FALLBACK_BETA
    assert captured["body"]["model"] == "claude-opus-5"
    assert captured["body"]["fallbacks"] == "default"
    assert "individual MPs" in captured["body"]["messages"][0]["content"]


def test_generate_cards_http_errors(monkeypatch):
    def fail_401(request, timeout=None):
        raise urllib.error.HTTPError(
            qgen.API_URL, 401, "unauthorized", {}, io.BytesIO(b"{}")
        )

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fail_401)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {"anthropic_api_key": "bad"})
    assert "401" in str(exc.value)

    def fail_conn(request, timeout=None):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fail_conn)
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {"anthropic_api_key": "k"})
    assert "internet" in str(exc.value)


def test_generate_cards_refusal(monkeypatch):
    monkeypatch.setattr(
        qgen.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(
            {"stop_reason": "refusal", "content": []}
        ),
    )
    with pytest.raises(qgen.QGenError) as exc:
        qgen.generate_cards("text", {"anthropic_api_key": "k"})
    assert "declined" in str(exc.value)
