"""AI question generation: turn a snip's OCR text into flashcard drafts.

Talks to a free, open-source LLM running on the user's own machine (raw
HTTPS via the standard library - Anki's bundled Python cannot install
SDKs). Two providers are supported:

  "ollama" (default)
      The Ollama server (https://ollama.com), default
      http://localhost:11434. No account, no API key, no cost - and the
      slide text never leaves the computer.

  "openai_compatible"
      Any server exposing the OpenAI chat-completions API: LM Studio,
      llama.cpp's server, Jan, KoboldCpp, vLLM, or a remote endpoint the
      user chooses to point it at.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from . import qgen_feedback

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OPENAI_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT_S = 300


class QGenError(Exception):
    """A user-presentable failure of question generation."""


class EmptyReplyError(QGenError):
    """The model replied but offered no usable cards.

    Distinct from transport failures so batch (document) generation can
    treat a card-less section as fine and carry on.
    """


def _example_lines(cards: list) -> list:
    lines = []
    for c in cards:
        line = "- Q: %s | A: %s" % (c.get("front", ""), c.get("back", ""))
        if c.get("notes"):
            line += " | Notes: %s" % c["notes"]
        lines.append(line)
    return lines


def build_prompt(
    text: str, max_cards: int, feedback=None, source: str = "slide"
) -> str:
    if source == "document":
        intro = "Extract from the student's course materials:"
    else:
        intro = "Slide text (from OCR, may contain small errors):"
    kept, bad = feedback or ([], [])
    # examples go FIRST and the source text LAST: models anchor on the
    # most recent context, and small models otherwise start writing
    # cards about the example topics instead of the source
    feedback_block = ""
    if kept:
        feedback_block += (
            "Style examples - cards this student kept, from OTHER, "
            "UNRELATED topics. Copy their form, structure and depth "
            "only; their subject matter is off-limits:\n"
            + "\n".join(_example_lines(kept))
            + "\n\n"
        )
    if bad:
        feedback_block += (
            "The student flagged these earlier suggestions as poorly "
            "written. Identify what makes them weak and steer away from "
            "those habits - they show failure modes to avoid, not banned "
            "topics:\n" + "\n".join(_example_lines(bad)) + "\n\n"
        )
    return (
        "You are helping a UK law student prepare for the SQE by turning "
        "study text into Anki flashcards.\n\n"
        "%s"
        "Write up to %d flashcards testing the exam-relevant law in the "
        "source text below. If it contains little that is exam-relevant, "
        "write fewer - or return an empty array - rather than padding "
        "with filler.\n"
        "Rules:\n"
        "- Every card must test a fact stated in the source text below. "
        "If an answer cannot be found in the source text, do not write "
        "the card. Never write cards about the style examples' topics.\n"
        "- One specific point of law per card, answerable without seeing "
        "the source.\n"
        "- Questions are direct and well-structured. They need not be "
        "short - up to three sentences is fine, and a short scenario is "
        "often best where the point is about application, e.g.: \"A pays "
        "B less than the agreed sum. B accepts. Is this good "
        "consideration?\"\n"
        "- Answers give the legal position precisely: \"Yes, but...\" / "
        "\"No, unless...\" where the law is conditional; numbered steps "
        "for procedures.\n"
        "- Cite a case, statute, section number or year ONLY if it "
        "appears word-for-word in the source text. Never add citations "
        "from memory; if the source names no authority, cite nothing.\n"
        "- Prefer testable, legally significant material: rules, tests, "
        "time limits, procedures, exceptions. Skip headings and "
        "boilerplate. Fix obvious OCR typos silently.\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"front": "...", "back": "...", "notes": "..."}, ...]\n'
        "\"notes\" is optional brief context (an authority, a caveat) "
        "shown small under the answer; omit it when there is nothing "
        "worth adding.\n\n"
        "%s (write cards about THIS and nothing else):\n"
        "---\n%s\n---"
    ) % (feedback_block, max_cards, intro.rstrip(":"), text.strip())


def parse_cards(raw: str) -> list:
    """Extract [{front, back}, ...] from the model's reply, defensively."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise EmptyReplyError("The AI reply contained no card list.")
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError as exc:
        raise QGenError("The AI reply was not valid JSON (%s)." % exc)
    cards = []
    for item in data:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front") or "").strip()
        back = str(item.get("back") or "").strip()
        if front and back:
            card = {"front": front, "back": back}
            notes = str(item.get("notes") or "").strip()
            if notes:
                card["notes"] = notes
            cards.append(card)
    if not cards:
        raise EmptyReplyError("The AI reply contained no usable cards.")
    return cards


def generate_cards(text: str, config: dict, source: str = "slide") -> list:
    """Blocking call: source text -> [{front, back}, ...]. Raises QGenError."""
    if not text.strip():
        raise QGenError("There is no snip text to work from.")
    max_cards = int(config.get("qgen_max_cards", 4) or 4)
    prompt = build_prompt(
        text, max_cards, feedback=qgen_feedback.examples(config), source=source
    )
    provider = (
        str(config.get("qgen_provider") or "ollama")
        .strip()
        .lower()
        .replace("-", "_")
    )
    if provider == "ollama":
        reply = _chat_ollama(config, prompt)
    elif provider == "openai_compatible":
        reply = _chat_openai_compatible(config, prompt)
    else:
        raise QGenError(
            'Unknown "qgen_provider" %r in the add-on config. '
            'Use "ollama" or "openai_compatible".' % provider
        )
    cards = _drop_off_topic(parse_cards(reply), text)
    _verify_references(cards, text)
    return cards


_TOPIC_WORD_RE = re.compile(r"[a-z]{5,}")

# citation-shaped strings: case names (with optional [year]), Acts with
# years, Article/section references, bare bracketed years
_CITE_RES = [
    re.compile(r"\b[A-Z][\w'’-]*(?: [A-Z][\w'’-]*)* v\.? [A-Z][\w'’-]*(?: [A-Z][\w'’-]*)*(?: ?\[\d{4}\])?"),
    re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)* Act \d{4}"),
    re.compile(r"\bArticle \d+(?:\(\d+\))?"),
    re.compile(r"\bs\.? ?\d+(?:\(\d+\))?\s+[A-Z]{2,}(?: \d{4})?"),
    re.compile(r"\[\d{4}\]"),
]


def _citations(text: str) -> list:
    found = []
    for rx in _CITE_RES:
        found.extend(rx.findall(text or ""))
    return found


def _normalise_cite(text: str) -> str:
    return " ".join(text.lower().replace("v.", "v").split())


def _verify_references(cards: list, source_text: str) -> None:
    """Strip/flag citations the source text doesn't actually contain.

    Local models invent authorities (case names, years, sections),
    especially in notes. A citation is trusted only if it appears in
    the source text; anything else - including references the user has
    flagged as previously invented (the phantom blocklist) - gets the
    notes field dropped, and a warning attached when it sits in the
    question or answer. Mechanical, so the model can't talk its way
    past it.
    """
    src = _normalise_cite(source_text)
    try:
        phantoms = [
            _normalise_cite(p) for p in qgen_feedback.phantom_refs()
        ]
    except Exception:
        phantoms = []

    def suspicious(text: str) -> list:
        normalised = _normalise_cite(text)
        out = [
            c
            for c in _citations(text)
            if _normalise_cite(c) not in src
        ]
        out += [p for p in phantoms if p and p in normalised and p not in src]
        return out

    for card in cards:
        notes = card.get("notes") or ""
        if notes and suspicious(notes):
            del card["notes"]  # optional context isn't worth a fake cite
        issues = suspicious(
            "%s %s" % (card.get("front", ""), card.get("back", ""))
        )
        if issues:
            shown = sorted(set(" ".join(i.split()) for i in issues))[:3]
            card["_warn"] = "not in the source text: %s" % "; ".join(shown)


def _drop_off_topic(cards: list, source_text: str) -> list:
    """Discard cards that share no substance with the source text.

    Small models sometimes write cards about the style examples instead
    of the source. A genuine card near-always reuses several of the
    source's longer words; a bleed-through card reuses none. Lenient by
    design, and fails open: if the filter would reject everything, the
    original list is returned rather than nothing.
    """
    source_words = set(_TOPIC_WORD_RE.findall(source_text.lower()))
    if not source_words:
        return cards
    kept = []
    for card in cards:
        card_text = " ".join(
            [card.get("front", ""), card.get("back", ""), card.get("notes", "")]
        ).lower()
        overlap = set(_TOPIC_WORD_RE.findall(card_text)) & source_words
        if len(overlap) >= 2:
            kept.append(card)
    return kept or cards


def _ollama_options(config: dict) -> dict:
    """Per-request Ollama options; currently just CPU-thread limiting.

    Generation on CPU pegs every core, which can make the rest of the
    machine (Anki included) feel frozen. Leaving a core or two free
    slows generation slightly but keeps the laptop responsive - and the
    background prefetch hides the difference anyway.
    """
    try:
        reserve = int(config.get("qgen_leave_cores_free", 1))
    except (TypeError, ValueError):
        reserve = 1
    if reserve <= 0:
        return {}
    cores = os.cpu_count() or 0
    if cores <= reserve:
        return {}
    return {"num_thread": cores - reserve}


def _chat_ollama(config: dict, prompt: str) -> str:
    base = str(config.get("qgen_ollama_url") or DEFAULT_OLLAMA_URL).rstrip("/")
    model = config.get("qgen_model") or DEFAULT_MODEL
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        # keep the model in RAM between requests so only the first
        # generation of a study session pays the model-load wait
        "keep_alive": config.get("qgen_keep_alive") or "30m",
    }
    options = _ollama_options(config)
    if options:
        body["options"] = options
    payload = _post_json(
        base + "/api/chat",
        body,
        headers={},
        timeout=_timeout(config),
        server_hint=(
            "Could not reach the Ollama server at %s.\n\n"
            "Suggesting cards uses a free AI model running on your own "
            "computer via Ollama (https://ollama.com).\n\n"
            "1. Install Ollama and make sure it is running\n"
            "2. Download the model once:  ollama pull %s\n"
            "3. Click Suggest cards again" % (base, model)
        ),
    )
    if "error" in payload:
        raise QGenError(
            "Ollama reported an error: %s\n\nIf the model is missing, "
            "download it with:  ollama pull %s" % (payload["error"], model)
        )
    try:
        return payload["message"]["content"]
    except (KeyError, TypeError):
        raise QGenError("Unexpected reply from Ollama: %r" % payload)


def _chat_openai_compatible(config: dict, prompt: str) -> str:
    base = str(
        config.get("qgen_openai_base_url") or DEFAULT_OPENAI_BASE_URL
    ).rstrip("/")
    headers = {}
    api_key = (config.get("qgen_api_key") or "").strip()
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    payload = _post_json(
        base + "/chat/completions",
        {
            "model": config.get("qgen_model") or "",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        headers=headers,
        timeout=_timeout(config),
        server_hint=(
            "Could not reach the LLM server at %s.\n\n"
            "Make sure your local server (LM Studio, llama.cpp, Jan, ...) "
            'is running and that "qgen_openai_base_url" in the add-on '
            "config points at it (including the /v1 suffix if the server "
            "uses one)." % base
        ),
    )
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise QGenError("Unexpected reply from the server: %r" % payload)


def _timeout(config: dict) -> int:
    try:
        value = int(config.get("qgen_timeout_seconds") or DEFAULT_TIMEOUT_S)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_S
    return max(5, value)


def _post_json(url, body, headers, timeout, server_hint):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise QGenError(
            "The LLM server returned an error (HTTP %d).\n%s"
            % (exc.code, detail)
        )
    except urllib.error.URLError as exc:
        raise QGenError(
            "%s\n\n(Underlying error: %s)"
            % (server_hint, getattr(exc, "reason", exc))
        )
    except TimeoutError:
        raise QGenError(
            "The local model took too long to reply. The first request "
            "after Ollama loads a model can be slow; try again, raise "
            '"qgen_timeout_seconds" in the config, or use a smaller model.'
        )
    try:
        return json.loads(raw)
    except ValueError:
        raise QGenError("The server did not return JSON:\n%s" % raw[:500])
