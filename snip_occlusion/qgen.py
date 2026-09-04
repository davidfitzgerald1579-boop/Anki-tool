"""AI question generation: turn a snip's OCR text into flashcard drafts.

Talks to an open-weight LLM (raw HTTPS via the standard library - Anki's
bundled Python cannot install SDKs). Where that model runs is decided by
the qgen_provider config key, see qgen_providers:

  "ollama" (default)
      Ollama (https://ollama.com) on this computer: no account, no API
      key, no cost, and the slide text never leaves the machine. Point
      qgen_ollama_url at another machine and the text goes there
      instead (with a Bearer key, if a proxy in front of it wants one).

  a hosted preset: "groq", "cerebras", "openrouter", "together", ...
      The same open models on a company's datacentre GPUs, paid per use
      (often free at student volumes) and tens of times faster. Needs an
      API key; the slide text is sent to that company.

  "openai_compatible"
      Any other server exposing the OpenAI chat-completions API: LM
      Studio, llama.cpp's server, Jan, KoboldCpp, vLLM, a rented GPU box.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from . import qgen_feedback, qgen_providers

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
    text: str,
    max_cards: int,
    feedback=None,
    source: str = "slide",
    focus=None,
    emphasis=None,
) -> str:
    """`focus` passages are must-cover; max_cards then means EXACTLY
    that many cards about them (one per passage when the counts match).
    `emphasis` lists words the slide printed in an accent colour - the
    model is told to work them into the cards.
    """
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
        "---\n%s\n---%s%s"
    ) % (
        feedback_block,
        max_cards,
        intro.rstrip(":"),
        text.strip(),
        _emphasis_block(emphasis),
        _focus_block(focus, max_cards),
    )


def _emphasis_block(emphasis) -> str:
    """Accent-coloured slide terms, placed after the source text."""
    if not emphasis:
        return ""
    listed = "; ".join(" ".join(term.split()) for term in emphasis)
    return (
        "\n\nOn the slide, these words are printed in a DIFFERENT "
        "COLOUR from the rest of their sentence - the course author "
        "marked them as key terms. Make sure the cards test the "
        "points these terms belong to, and use the terms themselves "
        "in the question or answer: %s" % listed
    )


def _focus_block(focus, n: int) -> str:
    """The must-cover passages block, placed LAST for recency anchoring."""
    if not focus:
        return ""
    numbered = "\n".join(
        "%d. %s" % (i, " ".join(p.split()))
        for i, p in enumerate(focus, 1)
    )
    if n == len(focus):
        instruction = (
            "Write EXACTLY one card per passage, in the same order, "
            "each testing precisely what its passage says."
        )
    else:
        instruction = (
            "Write EXACTLY %d flashcard%s in total, testing ONLY what "
            "these passages say%s."
            % (
                n,
                "" if n == 1 else "s",
                " - spread them across the passages" if n > 1 else "",
            )
        )
    return (
        "\n\nThe student highlighted these passages from the source "
        "text as MUST-COVER. %s "
        "Use the rest of the source only as context:\n%s"
        % (instruction, numbered)
    )


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


def generate_cards(
    text: str,
    config: dict,
    source: str = "slide",
    focus=None,
    focus_cards=None,
    emphasis=None,
) -> list:
    """Blocking call: source text -> [{front, back}, ...]. Raises QGenError.

    `focus` is an optional list of passages the user highlighted; the
    model is told to write exactly one card per passage - or exactly
    `focus_cards` cards in total about them, when that is given.
    """
    if not text.strip():
        raise QGenError("There is no snip text to work from.")
    if focus:
        max_cards = int(focus_cards) if focus_cards else len(focus)
    else:
        max_cards = int(config.get("qgen_max_cards", 4) or 4)
    prompt = build_prompt(
        text,
        max_cards,
        feedback=qgen_feedback.examples(config),
        source=source,
        focus=focus,
        emphasis=emphasis,
    )
    cfg = dict(config)
    cfg[_REPLY_CARDS_KEY] = max_cards
    try:
        target = qgen_providers.resolve(cfg)
    except qgen_providers.UnknownProvider as exc:
        raise QGenError(
            'Unknown "qgen_provider" %r in the add-on config. '
            "Use one of: %s."
            % (str(exc), ", ".join(qgen_providers.valid_providers()))
        )
    if target.api == qgen_providers.API_OLLAMA:
        reply = _chat_ollama(cfg, prompt)
    else:
        reply = _chat_openai_compatible(cfg, prompt)
    cards = _drop_off_topic(parse_cards(reply), text)
    _verify_references(cards, text)
    for card in cards:
        # kept locally so the 🔎 button can show where a card came from;
        # never sent anywhere and stripped before feedback storage
        card["_source"] = text
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


# generate_cards stashes the card count here so the transports can cap
# the reply length (internal; never a documented config key)
_REPLY_CARDS_KEY = "_qgen_reply_cards"
_TOKENS_PER_CARD = 256
_TOKENS_SLACK = 128


def _reply_token_cap(config: dict, target=None):
    """Upper bound on reply tokens, or None to leave the server's default.

    A card is ~100-150 tokens of JSON; the cap is generous so a full
    answer never hits it, but a model that starts rambling or looping
    (small ones occasionally do) is cut off after a couple of minutes on
    a CPU rather than running until the timeout. "Thinking" models
    spend hidden reasoning tokens inside the same budget, so they get
    several times the room.
    """
    try:
        n = int(config.get(_REPLY_CARDS_KEY) or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return None
    cap = _TOKENS_PER_CARD * n + _TOKENS_SLACK
    if target is not None and qgen_providers.is_reasoning_model(target.model):
        cap = cap * 4 + 1024
    return cap


def _ollama_options(config: dict, target) -> dict:
    """Per-request Ollama options: thread limiting and a reply cap.

    Generation on CPU pegs every core, which can make the rest of the
    machine (Anki included) feel frozen. Leaving a core or two free
    slows generation slightly but keeps the laptop responsive - and the
    background prefetch hides the difference anyway. Only for a server
    on THIS computer: a remote box has its own core count.
    """
    options = {}
    cap = _reply_token_cap(config, target)
    if cap:
        options["num_predict"] = cap
    if target.remote:
        return options
    try:
        reserve = int(config.get("qgen_leave_cores_free", 1))
    except (TypeError, ValueError):
        reserve = 1
    if reserve <= 0:
        return options
    cores = os.cpu_count() or 0
    if cores > reserve:
        options["num_thread"] = cores - reserve
    return options


def _auth_headers(target) -> dict:
    headers = dict(target.headers)
    if target.api_key:
        headers["Authorization"] = "Bearer %s" % target.api_key
    return headers


def _chat_ollama(config: dict, prompt: str) -> str:
    target = qgen_providers.resolve(config)
    model = target.model or DEFAULT_MODEL
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if not target.remote or target.preset is None:
        # keep the model in RAM between requests so only the first
        # generation of a study session pays the model-load wait
        # (meaningless for Ollama Cloud, which manages its own fleet)
        body["keep_alive"] = config.get("qgen_keep_alive") or "30m"
    options = _ollama_options(config, target)
    if options:
        body["options"] = options
    if qgen_providers.is_gpt_oss(model):
        # think briefly - cards need no long deliberation (other
        # thinking models reject a string level; they keep their default)
        body["think"] = "low"
    if target.preset is not None:
        hint = _hosted_hint(target)
    elif target.remote:
        hint = (
            "Could not reach the Ollama server at %s.\n\n"
            "Make sure that machine is on, Ollama is running there with "
            "OLLAMA_HOST=0.0.0.0 (so it accepts connections from other "
            'computers), and that "qgen_ollama_url" in the add-on config '
            "is right." % target.base_url
        )
    else:
        hint = (
            "Could not reach the Ollama server at %s.\n\n"
            "Suggesting cards uses a free AI model running on your own "
            "computer via Ollama (https://ollama.com).\n\n"
            "1. Install Ollama and make sure it is running\n"
            "2. Download the model once:  ollama pull %s\n"
            "3. Click Suggest cards again\n\n"
            "Too slow on your machine? A hosted service (⚙ Settings → "
            "AI model) runs the same open models many times faster."
            % (target.base_url, model)
        )
    payload = _post_json(
        target.base_url + "/api/chat",
        body,
        headers=_auth_headers(target),
        timeout=_timeout(config),
        server_hint=hint,
        target=target,
    )
    if "error" in payload:
        message = payload["error"]
        if target.preset is None:
            message += (
                "\n\nIf the model is missing, download it with:  "
                "ollama pull %s" % model
            )
        raise QGenError("Ollama reported an error: %s" % message)
    try:
        return payload["message"]["content"]
    except (KeyError, TypeError):
        raise QGenError("Unexpected reply from Ollama: %r" % payload)


def _chat_openai_compatible(config: dict, prompt: str) -> str:
    target = qgen_providers.resolve(config)
    body = {
        "model": target.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    cap = _reply_token_cap(config, target)
    if cap:
        body["max_tokens"] = cap
    if target.preset is not None and qgen_providers.is_gpt_oss(target.model):
        param = target.preset.reasoning_param
        if param == "reasoning":
            body["reasoning"] = {"effort": "low"}
        elif param:
            body[param] = "low"
    if target.preset is not None:
        hint = _hosted_hint(target)
    else:
        hint = (
            "Could not reach the LLM server at %s.\n\n"
            "Make sure your server (LM Studio, llama.cpp, Jan, vLLM, ...) "
            'is running and that "qgen_openai_base_url" in the add-on '
            "config points at it (including the /v1 suffix if the server "
            "uses one)." % target.base_url
        )
    if target.preset is not None and not target.model:
        raise QGenError(
            'No model chosen for %s - set "qgen_model" (⚙ Settings → '
            "AI model)." % target.label
        )
    payload = _post_json(
        target.base_url + "/chat/completions",
        body,
        headers=_auth_headers(target),
        timeout=_timeout(config),
        server_hint=hint,
        target=target,
    )
    if isinstance(payload, dict) and "error" in payload and not payload.get(
        "choices"
    ):
        err = payload["error"]
        if isinstance(err, dict):
            err = err.get("message") or json.dumps(err)
        raise QGenError("%s reported an error: %s" % (target.label, err))
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise QGenError("Unexpected reply from the server: %r" % payload)


def _hosted_hint(target) -> str:
    return (
        "Could not reach %s at %s.\n\n"
        "Check your internet connection. If the service is down, switch "
        "back to the free model on your own computer in ⚙ Settings → "
        "AI model." % (target.label, target.host)
    )


def _timeout(config: dict) -> int:
    try:
        value = int(config.get("qgen_timeout_seconds") or DEFAULT_TIMEOUT_S)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_S
    return max(5, value)


def _http_error_message(exc, target, detail: str) -> str:
    label = target.label if target else "The LLM server"
    key_help = ""
    if target is not None and target.key_url:
        key_help = " Keys are created at %s" % target.key_url
    if 300 <= exc.code < 400:
        location = ""
        try:
            location = exc.headers.get("Location") or ""
        except Exception:
            pass
        return (
            "%s redirected the request (HTTP %d)%s. Redirects are not "
            "followed, so that your API key is only ever sent to the "
            "address you configured - set the server URL to the "
            "redirect target instead." % (
                label,
                exc.code,
                " to %s" % location if location else "",
            )
        )
    if exc.code in (401, 403):
        if target is not None and target.preset is not None:
            return (
                "%s rejected the API key (HTTP %d).\n\nPaste the key into "
                "⚙ Settings → AI model, or set \"qgen_api_key\" in the "
                "add-on config.%s\n%s" % (label, exc.code, key_help, detail)
            )
        return (
            "%s refused the request (HTTP %d) - it wants an API key or "
            "a different one.\n%s" % (label, exc.code, detail)
        )
    if exc.code == 402:
        return (
            "%s reports no credit left (HTTP 402). Top up your account "
            "there, or switch to another provider or the free local model "
            "in ⚙ Settings.\n%s" % (label, detail)
        )
    if exc.code == 404:
        model = target.model if target else ""
        return (
            "%s could not find that endpoint or model (HTTP 404). Check "
            "the model name%s - the Fetch button in ⚙ Settings → AI model "
            "lists the ones the server knows.\n%s"
            % (label, " (%r)" % model if model else "", detail)
        )
    if exc.code == 429:
        return (
            "%s is rate-limiting you (HTTP 429) - a free tier's "
            "per-minute or per-day allowance, or a busy server. Wait a "
            "little and try again.\n%s" % (label, detail)
        )
    return "%s returned an error (HTTP %d).\n%s" % (label, exc.code, detail)


def _post_json(url, body, headers, timeout, server_hint, target=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    return _send(request, timeout, server_hint, target)


def _get_json(url, headers, timeout, server_hint, target=None):
    request = urllib.request.Request(url, headers=headers, method="GET")
    return _send(request, timeout, server_hint, target)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects.

    urllib would otherwise re-send the request - Authorization header
    included - to wherever the server points, and turn a POST into a
    GET while at it. A wrong base URL should produce a clear message
    naming the right one, not a leaked key or a baffling 405.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def _urlopen(request, timeout):
    return urllib.request.build_opener(_NoRedirect()).open(
        request, timeout=timeout
    )


_TAG_RE = re.compile(r"<[^>]*>")


def _plain(text: str, limit: int = 500) -> str:
    """A server's error body as plain text, for showing in a tooltip.

    Error pages from CDNs arrive as HTML; the popups that show QGenError
    messages render rich text, so the markup is stripped rather than
    displayed.
    """
    text = _TAG_RE.sub(" ", str(text or ""))
    return " ".join(text.split())[:limit]


def _send(request, timeout, server_hint, target):
    try:
        with _urlopen(request, timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = _plain(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            pass
        raise QGenError(_http_error_message(exc, target, detail))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            raise QGenError(_timeout_message(target))
        raise QGenError("%s\n\n(Underlying error: %s)" % (server_hint, reason))
    except TimeoutError:
        raise QGenError(_timeout_message(target))
    try:
        return json.loads(raw)
    except ValueError:
        raise QGenError("The server did not return JSON:\n%s" % _plain(raw))


def _timeout_message(target) -> str:
    if target is not None and target.remote:
        return (
            "%s took too long to reply. Try again; if it keeps "
            "happening, pick a different model or provider in ⚙ Settings "
            "→ AI model." % target.label
        )
    return (
        "The local model took too long to reply. The first request "
        "after Ollama loads a model can be slow; try again, raise "
        '"qgen_timeout_seconds" in the config, use a smaller model - or '
        "switch to a hosted service in ⚙ Settings → AI model, which is "
        "many times faster."
    )


# ------------------------------------------------- Settings-dialog helpers


def list_models(config: dict, timeout: int = 20) -> list:
    """Model ids the configured server offers, as it names them.

    Ollama: GET /api/tags. OpenAI-compatible: GET /models, whose reply
    is {"data": [{"id": ...}]} on most servers and a bare list on a few.
    Raises QGenError when the server can't be reached or refuses.
    """
    try:
        target = qgen_providers.resolve(config)
    except qgen_providers.UnknownProvider as exc:
        raise QGenError('Unknown "qgen_provider" %r.' % str(exc))
    headers = _auth_headers(target)
    hint = "Could not reach %s at %s." % (target.label, target.base_url)
    if target.api == qgen_providers.API_OLLAMA:
        payload = _get_json(
            target.base_url + "/api/tags", headers, timeout, hint, target
        )
        items = payload.get("models") if isinstance(payload, dict) else None
        names = [
            m.get("name") or m.get("model")
            for m in (items or [])
            if isinstance(m, dict)
        ]
    else:
        payload = _get_json(
            target.base_url + "/models", headers, timeout, hint, target
        )
        items = payload.get("data") if isinstance(payload, dict) else payload
        names = [
            m.get("id") or m.get("name")
            for m in (items or [])
            if isinstance(m, dict)
        ]
    return sorted({str(n) for n in names if n}, key=str.lower)


def model_listed(model: str, known: list) -> bool:
    """Is `model` in a server's listing, allowing Ollama's ":latest"?

    `ollama pull llama3.2` lists as "llama3.2:latest" but answers to
    "llama3.2" - the two are the same model.
    """
    model = str(model or "").strip()
    if not model:
        return False
    wanted = {model, model + ":latest"}
    if model.endswith(":latest"):
        wanted.add(model[: -len(":latest")])
    return any(name in wanted for name in known)


def check_connection(config: dict, timeout: int = 30) -> str:
    """Probe the configured server; return a one-line human verdict.

    Lists models when the server can, then sends a minimal chat request
    to prove the chosen model actually answers (and how quickly).
    Raises QGenError with the same friendly messages generation uses.
    """
    try:
        target = qgen_providers.resolve(config)
    except qgen_providers.UnknownProvider as exc:
        raise QGenError('Unknown "qgen_provider" %r.' % str(exc))
    if not target.model:
        raise QGenError("Pick a model first.")
    if target.preset is not None and not target.api_key:
        raise QGenError(
            "%s needs an API key - create one at %s and paste it in."
            % (target.label, target.key_url)
        )
    known = None
    try:
        known = list_models(config, timeout=min(timeout, 20))
    except QGenError:
        pass  # listing is optional; the chat below is the real test
    if known and not model_listed(target.model, known):
        if target.api == qgen_providers.API_OLLAMA and not target.remote:
            raise QGenError(
                "Connected, but %r is not downloaded yet. In a terminal "
                "run:  ollama pull %s\n\nModels already there: %s"
                % (target.model, target.model, ", ".join(known[:12]))
            )
        # remote listings can be partial (aliases, hidden models):
        # fall through and let the chat probe decide
    started = time.monotonic()
    probe_cfg = dict(config)
    probe_cfg[_REPLY_CARDS_KEY] = 0  # no cap; a tiny reply anyway
    probe_cfg["qgen_timeout_seconds"] = timeout  # a probe, not a generation
    prompt = "Reply with exactly one word: OK"
    if target.api == qgen_providers.API_OLLAMA:
        reply = _chat_ollama(probe_cfg, prompt)
    else:
        reply = _chat_openai_compatible(probe_cfg, prompt)
    elapsed = time.monotonic() - started
    reply = " ".join(str(reply or "").split())[:40]
    summary = "✓ %s answered with %s in %.1f s" % (
        target.label,
        target.model,
        elapsed,
    )
    if known:
        summary += " · %d model%s listed" % (
            len(known),
            "" if len(known) == 1 else "s",
        )
    if reply:
        summary += " · said %r" % reply
    return summary
