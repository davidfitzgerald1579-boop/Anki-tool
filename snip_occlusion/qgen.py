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

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OPENAI_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT_S = 300


class QGenError(Exception):
    """A user-presentable failure of question generation."""


def build_prompt(text: str, max_cards: int) -> str:
    return (
        "You are helping a UK law student (SQE) turn lecture-slide text "
        "into Anki flashcards.\n\n"
        "Slide text (from OCR, may contain small errors):\n"
        "---\n%s\n---\n\n"
        "Write up to %d high-quality question/answer flashcards from the "
        "facts on this slide.\n"
        "Rules:\n"
        "- One specific fact per card; the question must be answerable "
        "without seeing the slide.\n"
        "- Questions are short and direct (e.g. \"Who can bring forward "
        "private members' bills?\").\n"
        "- Answers are the fact only, as briefly as possible (e.g. "
        "\"Individual MPs\").\n"
        "- Prefer the legally significant facts; skip filler, headings "
        "and boilerplate.\n"
        "- Fix obvious OCR typos silently.\n\n"
        "Respond with ONLY a JSON array, no other text:\n"
        '[{"front": "...", "back": "..."}, ...]'
    ) % (text.strip(), max_cards)


def parse_cards(raw: str) -> list:
    """Extract [{front, back}, ...] from the model's reply, defensively."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise QGenError("The AI reply contained no card list.")
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
            cards.append({"front": front, "back": back})
    if not cards:
        raise QGenError("The AI reply contained no usable cards.")
    return cards


def generate_cards(text: str, config: dict) -> list:
    """Blocking call: OCR text -> [{front, back}, ...]. Raises QGenError."""
    if not text.strip():
        raise QGenError("There is no snip text to work from.")
    max_cards = int(config.get("qgen_max_cards", 8) or 8)
    prompt = build_prompt(text, max_cards)
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
