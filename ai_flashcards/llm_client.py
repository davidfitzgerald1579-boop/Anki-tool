"""Provider-agnostic client for local, open-source LLM servers.

Uses only the Python standard library (urllib), so the add-on has no
external dependencies and runs inside Anki's bundled Python as-is.

Supported providers:

  "ollama"
      The Ollama server (https://ollama.com), default http://localhost:11434.
      Free, open source, runs entirely on the user's machine.

  "openai_compatible"
      Any server that exposes the OpenAI chat-completions API. This covers
      LM Studio, llama.cpp's built-in server, Jan, KoboldCpp, vLLM,
      text-generation-webui, and most other local inference servers, as
      well as any remote endpoint the user chooses to point it at.
"""

import json
import urllib.error
import urllib.request


class LLMError(Exception):
    """Raised for any failure talking to the LLM server."""


def chat(config, prompt, system=None):
    """Send a single-turn chat request and return the model's reply text."""
    provider = str(config.get("provider", "ollama")).strip().lower().replace("-", "_")
    if provider == "ollama":
        return _chat_ollama(config, prompt, system)
    if provider == "openai_compatible":
        return _chat_openai_compatible(config, prompt, system)
    raise LLMError(
        "Unknown provider %r in the add-on config. "
        "Use \"ollama\" or \"openai_compatible\"." % provider
    )


def _messages(prompt, system):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _chat_ollama(config, prompt, system):
    base = str(config.get("ollama_url", "http://localhost:11434")).rstrip("/")
    model = config.get("model", "llama3.1:8b")
    body = {
        "model": model,
        "messages": _messages(prompt, system),
        "stream": False,
    }
    data = _post_json(
        base + "/api/chat",
        body,
        headers={},
        timeout=_timeout(config),
        server_hint=(
            "Could not reach the Ollama server at %s.\n\n"
            "Is Ollama installed and running? Install it from https://ollama.com, "
            "then download a model with:\n\n    ollama pull %s\n\n"
            "Ollama normally starts automatically; if not, run \"ollama serve\"."
            % (base, model)
        ),
    )
    try:
        return data["message"]["content"]
    except (KeyError, TypeError):
        raise LLMError(
            "Unexpected response from Ollama:\n%s" % _truncate(json.dumps(data))
        )


def _chat_openai_compatible(config, prompt, system):
    base = str(config.get("openai_base_url", "http://localhost:1234/v1")).rstrip("/")
    model = config.get("model", "")
    headers = {}
    api_key = config.get("api_key", "")
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    body = {
        "model": model,
        "messages": _messages(prompt, system),
        "stream": False,
    }
    data = _post_json(
        base + "/chat/completions",
        body,
        headers=headers,
        timeout=_timeout(config),
        server_hint=(
            "Could not reach the LLM server at %s.\n\n"
            "Make sure your local server (LM Studio, llama.cpp, Jan, ...) is "
            "running and that \"openai_base_url\" in the add-on config points "
            "at it (including the /v1 suffix if the server uses one)." % base
        ),
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError(
            "Unexpected response from the server:\n%s" % _truncate(json.dumps(data))
        )


def _timeout(config):
    try:
        return max(5, int(config.get("timeout_seconds", 300)))
    except (TypeError, ValueError):
        return 300


def _post_json(url, body, headers, timeout, server_hint):
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        detail = ""
        try:
            detail = err.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise LLMError(
            "The LLM server returned HTTP %s for %s.\n%s"
            % (err.code, url, _truncate(detail))
        )
    except urllib.error.URLError as err:
        raise LLMError("%s\n\n(Underlying error: %s)" % (server_hint, err.reason))
    except TimeoutError:
        raise LLMError(
            "The request to %s timed out. Local models can be slow on first "
            "load; you can raise \"timeout_seconds\" in the add-on config or "
            "try a smaller model." % url
        )
    try:
        return json.loads(raw)
    except ValueError:
        raise LLMError(
            "The server at %s did not return JSON:\n%s" % (url, _truncate(raw))
        )


def _truncate(text, limit=800):
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text
