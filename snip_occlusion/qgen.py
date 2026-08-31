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
        noun = "extract"
    else:
        intro = "Slide text (from OCR, may contain small errors):"
        noun = "slide"
    kept, bad = feedback or ([], [])
    feedback_block = ""
    if kept:
        feedback_block += (
            "Match the style, structure and depth of these cards the "
            "student kept - they show the FORM to copy, not topics to "
            "repeat:\n" + "\n".join(_example_lines(kept)) + "\n\n"
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
        "%s\n"
        "---\n%s\n---\n\n"
        "Write up to %d flashcards testing the exam-relevant law on this "
        "%s. If it contains little that is exam-relevant, "
        "write fewer - or return an empty array - rather than padding "
        "with filler.\n"
        "Rules:\n"
        "- One specific point of law per card, answerable without seeing "
        "the slide.\n"
        "- Questions are direct and well-structured. They need not be "
        "short - up to three sentences is fine, and a short scenario is "
        "often best where the point is about application, e.g.: \"A pays "
        "B less than the agreed sum. B accepts. Is this good "
        "consideration?\"\n"
        "- Answers give the legal position precisely: \"Yes, but...\" / "
        "\"No, unless...\" where the law is conditional; numbered steps "
        "for procedures; include the statute section or case name when "
        "the slide provides it.\n"
        "- Prefer testable, legally significant material: rules, tests, "
        "time limits, procedures, exceptions. Skip headings and "
        "boilerplate. Fix obvious OCR typos silently.\n\n"
        "%s"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"front": "...", "back": "...", "notes": "..."}, ...]\n'
        "\"notes\" is optional brief context (an authority, a caveat) "
        "shown small under the answer; omit it when there is nothing "
        "worth adding."
    ) % (intro, text.strip(), max_cards, noun, feedback_block)


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
    return parse_cards(reply)


def _chat_ollama(config: dict, prompt: str) -> str:
    base = str(config.get("qgen_ollama_url") or DEFAULT_OLLAMA_URL).rstrip("/")
    model = config.get("qgen_model") or DEFAULT_MODEL
    payload = _post_json(
        base + "/api/chat",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            # keep the model in RAM between requests so only the first
            # generation of a study session pays the model-load wait
            "keep_alive": config.get("qgen_keep_alive") or "30m",
        },
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
