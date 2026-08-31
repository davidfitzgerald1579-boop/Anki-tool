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


def test_prompt_focus_block_comes_last():
    p = qgen.build_prompt(
        "The Court tries all summary offences. Other sentence here.",
        1,
        focus=["The Court tries  all summary offences"],
    )
    assert "EXACTLY one card per passage" in p
    assert "1. The Court tries all summary offences" in p  # whitespace fixed
    # the focus block sits AFTER the source text (recency anchoring)
    assert p.rfind("MUST-COVER") > p.rfind("Other sentence here")
    # and without focus there is no block at all
    assert "MUST-COVER" not in qgen.build_prompt("text", 4)


def test_prompt_focus_with_chosen_total():
    # counts differ from the passage count -> "EXACTLY n in total"
    p = qgen.build_prompt("source", 3, focus=["one passage"])
    assert "EXACTLY 3 flashcards in total" in p
    assert "spread them across the passages" in p
    assert "one card per passage" not in p
    p1 = qgen.build_prompt("source", 1, focus=["a", "b"])
    assert "EXACTLY 1 flashcard in total" in p1
    # matching counts keep the crisper one-per-passage instruction
    p2 = qgen.build_prompt("source", 2, focus=["a", "b"])
    assert "EXACTLY one card per passage" in p2


def test_generate_cards_focus_cards_overrides_count(monkeypatch):
    prompts = []

    def fake_chat(config, prompt):
        prompts.append(prompt)
        return '[{"front": "Q", "back": "A"}]'

    monkeypatch.setattr(qgen, "_chat_ollama", fake_chat)
    cfg = {"qgen_provider": "ollama", "qgen_feedback": False,
           "qgen_max_cards": 4}
    qgen.generate_cards("source text", cfg, focus=["passage"], focus_cards=3)
    assert "up to 3 flashcards" in prompts[0]
    assert "EXACTLY 3 flashcards in total" in prompts[0]


def test_generate_cards_focus_caps_to_passage_count(monkeypatch):
    prompts = []

    def fake_chat(config, prompt):
        prompts.append(prompt)
        return '[{"front": "Q", "back": "A"}]'

    monkeypatch.setattr(qgen, "_chat_ollama", fake_chat)
    cfg = {"qgen_provider": "ollama", "qgen_feedback": False,
           "qgen_max_cards": 4}
    qgen.generate_cards(
        "source text about offences", cfg, focus=["passage one", "two x"]
    )
    assert "up to 2 flashcards" in prompts[0]
    assert "1. passage one" in prompts[0] and "2. two x" in prompts[0]


def test_parse_cards_keeps_optional_notes():
    raw = (
        '[{"front": "Q", "back": "A", "notes": "Lister [2002]"},'
        ' {"front": "Q2", "back": "A2", "notes": ""}]'
    )
    cards = qgen.parse_cards(raw)
    assert cards[0]["notes"] == "Lister [2002]"
    assert "notes" not in cards[1]


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
    # cards remember their source text for the 🔎 trace view
    assert cards[0]["_source"].startswith("Private members bills")


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


def test_ollama_leaves_cores_free(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode())
        return _FakeResponse(
            {"message": {"role": "assistant", "content": _CARD_JSON}}
        )

    monkeypatch.setattr(qgen.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qgen.os, "cpu_count", lambda: 8)
    # default: one core left free
    qgen.generate_cards("text", {})
    assert captured["body"]["options"] == {"num_thread": 7}
    # explicit reserve
    qgen.generate_cards("text", {"qgen_leave_cores_free": 3})
    assert captured["body"]["options"] == {"num_thread": 5}
    # 0 = use every core: no options sent at all
    qgen.generate_cards("text", {"qgen_leave_cores_free": 0})
    assert "options" not in captured["body"]
    # never reserve the machine into nothing
    monkeypatch.setattr(qgen.os, "cpu_count", lambda: 1)
    qgen.generate_cards("text", {})
    assert "options" not in captured["body"]


def test_prompt_puts_source_last_and_examples_first():
    feedback = (
        [{"front": "StyleQ", "back": "StyleA"}],
        [{"front": "WeakQ", "back": "WeakA"}],
    )
    p = qgen.build_prompt("The defendant bears no burden.", 4, feedback)
    # examples come before the rules; the source text is the very end,
    # right where the model's attention is when it starts writing
    assert p.index("StyleQ") < p.index("Rules:")
    assert p.index("Rules:") < p.index("The defendant bears no burden.")
    assert p.rstrip().endswith("---")
    assert "off-limits" in p  # example topics are explicitly fenced off
    assert "must test a fact stated in the source text" in p


def test_off_topic_cards_are_dropped():
    source = (
        "The prosecution bears the burden of proof in criminal "
        "proceedings and must prove its case beyond reasonable doubt."
    )
    on_topic = {
        "front": "Who bears the burden of proof in criminal proceedings?",
        "back": "The prosecution, beyond reasonable doubt.",
    }
    bleed = {
        "front": "What is the priority of an additional mortgage loan?",
        "back": "If the lender had notice and agreed, it takes priority.",
    }
    kept = qgen._drop_off_topic([on_topic, bleed], source)
    assert kept == [on_topic]
    # fails open: if everything would be dropped, keep the originals
    assert qgen._drop_off_topic([bleed], source) == [bleed]
    # no usable source words -> untouched
    assert qgen._drop_off_topic([bleed], "a b c") == [bleed]


SOURCE_WITH_CITES = (
    "In R v Brown [1970] 1 QBD 105 the prosecution acted for the Crown. "
    "Consumer rights arise under s 9 CRA 2015 and the Human Rights Act "
    "1998; see also Article 8(1)."
)


def test_citation_extraction():
    cites = qgen._citations(SOURCE_WITH_CITES)
    joined = " | ".join(cites)
    assert "R v Brown [1970]" in joined
    assert "Human Rights Act 1998" in joined
    assert "Article 8(1)" in joined
    assert "s 9 CRA 2015" in joined


def test_verified_references_survive(monkeypatch):
    monkeypatch.setattr(qgen.qgen_feedback, "phantom_refs", lambda: [])
    card = {
        "front": "Which case names the Crown as prosecutor?",
        "back": "R v Brown [1970].",
        "notes": "Human Rights Act 1998",
    }
    qgen._verify_references([card], SOURCE_WITH_CITES)
    assert card["notes"] == "Human Rights Act 1998"
    assert "_warn" not in card


def test_invented_references_stripped_and_warned(monkeypatch):
    monkeypatch.setattr(qgen.qgen_feedback, "phantom_refs", lambda: [])
    card = {
        "front": "What did Donoghue v Stevenson [1932] decide?",
        "back": "The neighbour principle.",
        "notes": "See also Sale of Goods Act 1979",  # not in source
    }
    qgen._verify_references([card], SOURCE_WITH_CITES)
    assert "notes" not in card  # invented citation -> notes dropped
    assert "Donoghue v Stevenson" in card["_warn"]  # invented case flagged


def test_invented_year_on_real_case_is_caught(monkeypatch):
    monkeypatch.setattr(qgen.qgen_feedback, "phantom_refs", lambda: [])
    card = {
        "front": "Who prosecutes?",
        "back": "The Crown: R v Brown [1994].",  # real case, wrong year
    }
    qgen._verify_references([card], SOURCE_WITH_CITES)
    assert "_warn" in card and "[1994]" in card["_warn"]


def test_phantom_blocklist_applies(monkeypatch):
    monkeypatch.setattr(
        qgen.qgen_feedback,
        "phantom_refs",
        lambda: ["Smith v Jones [2001]"],
    )
    card = {
        "front": "Q about the burden of proof and the prosecution?",
        "back": "The prosecution bears it.",
        "notes": "smith v jones [2001] confirms this",
    }
    qgen._verify_references([card], SOURCE_WITH_CITES)
    assert "notes" not in card
