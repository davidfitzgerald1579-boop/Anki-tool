"""Turn source text into flashcards using a local LLM."""

import json
import re

from . import llm_client

SYSTEM_PROMPT = (
    "You are an expert Anki flashcard author. You write clear, atomic "
    "flashcards: one fact or idea per card, short unambiguous questions, "
    "concise answers. You respond with JSON only - no commentary, no "
    "markdown fences."
)

PROMPT_TEMPLATE = """Create up to {max_cards} high-quality Anki flashcards from the source text below.

Rules:
- Each card tests exactly one fact or concept from the text.
- The front is a specific question; the back is a short, direct answer.
- Do not invent information that is not in the text.
- Respond with ONLY a JSON array, in this exact shape:

[
  {{"front": "Question here", "back": "Answer here"}},
  {{"front": "...", "back": "..."}}
]

Source text:
---
{source_text}
---"""


def generate_cards(config, source_text, max_cards):
    """Return a list of {"front": ..., "back": ...} dicts.

    Raises llm_client.LLMError on connection/response problems.
    """
    prompt = PROMPT_TEMPLATE.format(
        max_cards=max_cards, source_text=source_text.strip()
    )
    raw = llm_client.chat(config, prompt, system=SYSTEM_PROMPT)
    cards = parse_cards(raw)
    if not cards:
        raise llm_client.LLMError(
            "The model's reply did not contain any usable flashcards. "
            "Reply was:\n%s" % raw[:800]
        )
    return cards[:max_cards]


def parse_cards(raw):
    """Leniently extract a list of front/back cards from model output.

    Local models vary in how strictly they follow format instructions, so
    this accepts: a bare JSON array, an object like {"cards": [...]}, and
    either of those wrapped in markdown code fences or surrounding prose.
    """
    if not raw:
        return []
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    data = _try_load(text)
    if data is None:
        # Fall back to the outermost JSON array embedded in the reply.
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            data = _try_load(text[start : end + 1])
    if data is None:
        # Or the outermost JSON object (e.g. {"cards": [...]}).
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            data = _try_load(text[start : end + 1])
    if data is None:
        return []

    if isinstance(data, dict):
        for key in ("cards", "flashcards", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []

    cards = []
    for item in data:
        if not isinstance(item, dict):
            continue
        front = _field(item, "front", "question", "q")
        back = _field(item, "back", "answer", "a")
        if front and back:
            cards.append({"front": front, "back": back})
    return cards


def _try_load(text):
    try:
        return json.loads(text)
    except ValueError:
        return None


def _field(item, *names):
    for name in names:
        value = item.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
