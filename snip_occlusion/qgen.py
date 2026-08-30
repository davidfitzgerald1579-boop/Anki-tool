"""AI question generation: turn a snip's OCR text into flashcard drafts.

Calls the Claude API (raw HTTPS via the standard library - Anki's bundled
Python cannot install the official SDK) with the user's own API key from
the add-on config. The slide text is sent to Anthropic's API for this
feature only, and only when the user clicks the suggest button.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# server-side refusal fallbacks (see Anthropic docs): if the primary model
# declines, the API transparently retries a suitable fallback model
FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MODEL = "claude-opus-5"
TIMEOUT_S = 120


class QGenError(Exception):
    """A user-presentable failure of question generation."""


def has_api_key(config: dict) -> bool:
    return bool((config.get("anthropic_api_key") or "").strip())


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
    key = (config.get("anthropic_api_key") or "").strip()
    if not key:
        raise QGenError(
            "No Anthropic API key is configured.\n\n"
            "Create one at console.anthropic.com, then paste it into\n"
            "Tools → Add-ons → Snip Occlusion → Config as "
            '"anthropic_api_key".'
        )
    if not text.strip():
        raise QGenError("There is no snip text to work from.")

    max_cards = int(config.get("qgen_max_cards", 8) or 8)
    body = {
        "model": config.get("qgen_model") or DEFAULT_MODEL,
        "max_tokens": 4000,
        "fallbacks": "default",
        "messages": [
            {"role": "user", "content": build_prompt(text, max_cards)}
        ],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "anthropic-beta": FALLBACK_BETA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8"))["error"]["message"]
        except Exception:
            pass
        if exc.code == 401:
            raise QGenError(
                "The API key was rejected (401). Check "
                '"anthropic_api_key" in the add-on config.'
            )
        if exc.code == 429:
            raise QGenError(
                "The API is rate-limiting requests (429). Wait a moment "
                "and try again."
            )
        raise QGenError(
            "The API returned an error (%d). %s" % (exc.code, detail)
        )
    except urllib.error.URLError as exc:
        raise QGenError(
            "Could not reach the Claude API (%s). Check your internet "
            "connection." % getattr(exc, "reason", exc)
        )

    if payload.get("stop_reason") == "refusal":
        raise QGenError(
            "The AI declined to process this text. Try a different snip."
        )
    text_parts = [
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ]
    return parse_cards("".join(text_parts))
