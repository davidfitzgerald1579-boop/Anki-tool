"""Where the AI runs: on this computer, on a hosted service, or anywhere.

The add-on itself is free and open source and always will be; the model
it talks to is open-weight (Llama, Qwen, gpt-oss, ...). What differs is
whose computer runs the model:

  "ollama"  - Ollama on this machine (the default). Free, private, slow
              on a laptop CPU (a minute or more per slide).

  a hosted preset ("groq", "cerebras", "together", ...) - a company
              that runs the same open models on datacentre GPUs and
              charges per use, typically a fraction of a cent per
              slide, often with a free tier. Tens of times faster. The
              slide text is sent to that company, and the user brings
              their own API key.

  "openai_compatible" - any other server speaking the OpenAI
              chat-completions API: LM Studio or llama.cpp on this
              machine, a GPU box the user rents and runs vLLM/Ollama on,
              a friend's PC across the network, ...

Every hosted service serves its models through the same two wire
protocols (the OpenAI chat-completions API or Ollama's native API), so
a preset is just a known base URL, a few good model ids, where the key
comes from, and the odd extra header. No SDKs: everything goes through
the standard library, which is all Anki's bundled Python has.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

LOCAL = "ollama"
CUSTOM = "openai_compatible"

API_OLLAMA = "ollama"
API_OPENAI = "openai"

# suggestions for the local Ollama model box; the actual list comes from
# the running server when the user presses Fetch
LOCAL_MODELS = (
    ("llama3.1:8b", "good all-rounder, ~5 GB download, 8 GB RAM"),
    ("qwen2.5:7b", "strong at structured output, ~5 GB"),
    ("mistral:7b", "fast, ~4 GB"),
    ("llama3.2:3b", "for low-RAM machines, ~2 GB"),
)


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    api: str  # API_OPENAI | API_OLLAMA
    base_url: str
    key_url: str  # where to create an API key
    env_var: str  # consulted when qgen_api_key is empty
    models: tuple  # ((model id, short description), ...) - first = default
    free_tier: str  # one line, shown in Settings
    note: str = ""  # one line, shown in Settings
    headers: tuple = ()  # extra request headers, ((name, value), ...)
    pricing_url: str = ""
    # how to ask a "thinking" model (gpt-oss, Qwen 3, DeepSeek R1...) to
    # think briefly: flashcards need no long deliberation, and hidden
    # reasoning tokens cost money and time. "reasoning_effort" is the
    # OpenAI-style field (Groq, Cerebras, ...); "reasoning" is
    # OpenRouter's {"effort": ...} object; "" sends nothing.
    reasoning_param: str = "reasoning_effort"


# Ordered as they appear in the Settings drop-down: the recommended
# one first.
HOSTED = (
    Preset(
        key="groq",
        label="Groq",
        api=API_OPENAI,
        base_url="https://api.groq.com/openai/v1",
        key_url="https://console.groq.com/keys",
        env_var="GROQ_API_KEY",
        models=(
            ("openai/gpt-oss-20b", "gpt-oss 20B - small, ~1000 tokens/s, cheapest"),
            ("openai/gpt-oss-120b", "gpt-oss 120B - noticeably better cards, still ~500 tokens/s"),
            ("qwen/qwen3.6-27b", "Qwen 3.6 27B (preview - may change)"),
        ),
        free_tier="Free tier, no card needed (about 200,000 tokens a day per model - over a hundred slides).",
        note="Fast, and the free tier needs no card. Recommended.",
        pricing_url="https://groq.com/pricing",
    ),
    Preset(
        key="openrouter",
        label="OpenRouter",
        api=API_OPENAI,
        base_url="https://openrouter.ai/api/v1",
        key_url="https://openrouter.ai/keys",
        env_var="OPENROUTER_API_KEY",
        models=(
            ("openai/gpt-oss-20b", "gpt-oss 20B"),
            ("openai/gpt-oss-120b", "gpt-oss 120B"),
            ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B"),
            ("openai/gpt-oss-20b:free", "gpt-oss 20B, free variant (rate-limited)"),
        ),
        free_tier="Models ending in ':free' cost nothing (50 requests a day; 1,000 after a one-off $10 top-up).",
        note="One key for hundreds of models across many hosts; Fetch list shows them all.",
        headers=(
            ("HTTP-Referer", "https://github.com/davidfitzgerald1579-boop/Anki-tool"),
            ("X-Title", "Snip Occlusion"),
        ),
        pricing_url="https://openrouter.ai/models",
        reasoning_param="reasoning",
    ),
    Preset(
        key="cerebras",
        label="Cerebras",
        api=API_OPENAI,
        base_url="https://api.cerebras.ai/v1",
        key_url="https://cloud.cerebras.ai/platform",
        env_var="CEREBRAS_API_KEY",
        models=(
            ("gpt-oss-120b", "gpt-oss 120B - ~3000 tokens/s"),
            ("gemma-4-31b", "Gemma 4 31B (preview)"),
        ),
        free_tier="$5 trial credit for 30 days once a card is added; then pay as you go.",
        note="The fastest chips of all; a small catalogue.",
        pricing_url="https://www.cerebras.ai/pricing",
    ),
    Preset(
        key="together",
        label="Together AI",
        api=API_OPENAI,
        base_url="https://api.together.xyz/v1",
        key_url="https://api.together.ai/settings/api-keys",
        env_var="TOGETHER_API_KEY",
        models=(
            ("openai/gpt-oss-20b", "gpt-oss 20B"),
            ("openai/gpt-oss-120b", "gpt-oss 120B"),
            ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B"),
        ),
        free_tier="Small free credit on sign-up; then pay as you go.",
        note="200+ models; press Fetch list to see them.",
        pricing_url="https://www.together.ai/pricing",
    ),
    Preset(
        key="fireworks",
        label="Fireworks AI",
        api=API_OPENAI,
        base_url="https://api.fireworks.ai/inference/v1",
        key_url="https://app.fireworks.ai/settings/users/api-keys",
        env_var="FIREWORKS_API_KEY",
        models=(
            ("accounts/fireworks/models/gpt-oss-20b", "gpt-oss 20B"),
            ("accounts/fireworks/models/gpt-oss-120b", "gpt-oss 120B"),
            ("accounts/fireworks/models/llama-v3p3-70b-instruct", "Llama 3.3 70B"),
        ),
        free_tier="Small free credit on sign-up; then pay as you go.",
        pricing_url="https://fireworks.ai/pricing",
    ),
    Preset(
        key="deepinfra",
        label="DeepInfra",
        api=API_OPENAI,
        base_url="https://api.deepinfra.com/v1/openai",
        key_url="https://deepinfra.com/dash/api_keys",
        env_var="DEEPINFRA_API_KEY",
        models=(
            ("openai/gpt-oss-20b", "gpt-oss 20B"),
            ("openai/gpt-oss-120b", "gpt-oss 120B - about 4 cents per million words in"),
            ("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B"),
        ),
        free_tier="Pay as you go - among the cheapest per token; no free tier.",
        pricing_url="https://deepinfra.com/pricing",
    ),
    Preset(
        key="huggingface",
        label="Hugging Face",
        api=API_OPENAI,
        base_url="https://router.huggingface.co/v1",
        key_url="https://huggingface.co/settings/tokens",
        env_var="HF_TOKEN",
        models=(
            ("openai/gpt-oss-20b", "gpt-oss 20B"),
            ("openai/gpt-oss-120b", "gpt-oss 120B"),
            ("meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B"),
        ),
        free_tier="Small monthly free allowance on every account ($2/month of credit on PRO).",
        note="Routes each model to a partner host. The token needs the 'Make calls to Inference Providers' permission.",
        pricing_url="https://huggingface.co/docs/inference-providers/pricing",
    ),
    Preset(
        key="ollama_cloud",
        label="Ollama Cloud",
        api=API_OLLAMA,
        base_url="https://ollama.com",
        key_url="https://ollama.com/settings/keys",
        env_var="OLLAMA_API_KEY",
        models=(
            ("gpt-oss:20b", "gpt-oss 20B"),
            ("gpt-oss:120b", "gpt-oss 120B"),
            ("deepseek-v3.1:671b", "DeepSeek V3.1"),
        ),
        free_tier="Free tier, no card needed (limits reset every 5 hours and weekly); Pro from $20/month.",
        note="The same Ollama API as the local option, run on Ollama's own GPUs. Metered by GPU time, not tokens.",
        pricing_url="https://ollama.com/pricing",
    ),
    Preset(
        key="mistral",
        label="Mistral AI",
        api=API_OPENAI,
        base_url="https://api.mistral.ai/v1",
        key_url="https://console.mistral.ai/api-keys",
        env_var="MISTRAL_API_KEY",
        models=(
            ("mistral-small-latest", "Mistral Small (Apache-2.0 open weights)"),
            ("ministral-8b-latest", "Ministral 8B"),
        ),
        free_tier="Free 'Experiment' plan (about 1 billion tokens a month, phone verification, no card).",
        pricing_url="https://mistral.ai/pricing",
    ),
)

_BY_KEY = {p.key: p for p in HOSTED}

# model-id fragments of models that may "think" before answering; they
# get a roomier reply cap, since the thinking shares the token budget
REASONING_MODELS = ("gpt-oss", "deepseek-r1", "qwen3", "qwq", "-thinking")


def is_reasoning_model(model: str) -> bool:
    m = str(model or "").lower()
    return any(frag in m for frag in REASONING_MODELS)


def is_gpt_oss(model: str) -> bool:
    """The one family whose "think less" switch is the same everywhere.

    gpt-oss takes an effort level (low/medium/high) as reasoning_effort
    on the OpenAI-style APIs and as think="low" on Ollama. Other
    thinking models spell it differently per host - Ollama rejects a
    string level for them, Groq's Qwen wants "none"/"default" - so
    they are simply left to their defaults.
    """
    return "gpt-oss" in str(model or "").lower()


def normalise(provider) -> str:
    return str(provider or LOCAL).strip().lower().replace("-", "_")


def preset(provider) -> Preset | None:
    """The hosted preset for a `qgen_provider` value, else None."""
    return _BY_KEY.get(normalise(provider))


def valid_providers() -> list:
    return [LOCAL, CUSTOM] + [p.key for p in HOSTED]


def netloc(url: str) -> str:
    """host[:port] of `url`, or the raw string when it doesn't parse.

    urlsplit raises ValueError on a half-typed IPv6 address such as
    "http://[::1" - which is exactly what the Settings box holds
    between two keystrokes.
    """
    try:
        return urlsplit(str(url or "")).netloc or str(url or "")
    except ValueError:
        return str(url or "")


def is_loopback(url: str) -> bool:
    """True when `url` points at this computer (localhost / 127.x / ::1).

    Decided by address, not by how the host is spelt: a DNS name such as
    127.example.com is NOT local, an IPv4-mapped ::ffff:127.0.0.1 is.
    """
    try:
        host = (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a DNS name: it resolves to wherever it resolves
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_loopback or ip.is_unspecified


@dataclass
class Target:
    """Everything a request needs, resolved from the config."""

    provider: str  # normalised qgen_provider
    api: str  # API_OLLAMA | API_OPENAI
    base_url: str
    model: str
    api_key: str
    label: str  # for status lines: "Groq", "Ollama on this computer"
    remote: bool  # the text leaves this computer
    preset: Preset | None = None
    headers: tuple = ()

    @property
    def host(self) -> str:
        return netloc(self.base_url)

    @property
    def key_url(self) -> str:
        return self.preset.key_url if self.preset else ""


class UnknownProvider(ValueError):
    pass


def api_key_for(config: dict, provider: str) -> str:
    """The key entered for `provider`, never one entered for another.

    Keys live in "qgen_api_keys" ({provider: key}); "qgen_api_key" is
    the documented single key and belongs to the provider the config
    is set to - editing it by hand keeps working - and wins for that
    provider. Hosted presets fall back to their usual environment
    variable. A key pasted for Groq is thus never sent to a server the
    user later points the add-on at.
    """
    provider = normalise(provider)
    legacy = str(config.get("qgen_api_key") or "").strip()
    if legacy and provider == normalise(config.get("qgen_provider")):
        return legacy
    keys = config.get("qgen_api_keys")
    if isinstance(keys, dict):
        stored = str(keys.get(provider) or "").strip()
        if stored:
            return stored
    p = _BY_KEY.get(provider)
    if p is not None and p.env_var:
        return os.environ.get(p.env_var, "").strip()
    return ""


def resolve(config: dict) -> Target:
    """Turn the qgen_* config keys into a Target. Raises UnknownProvider."""
    provider = normalise(config.get("qgen_provider"))
    model = str(config.get("qgen_model") or "").strip()
    api_key = api_key_for(config, provider)
    if provider == LOCAL:
        base = str(config.get("qgen_ollama_url") or "http://localhost:11434")
        base = base.strip().rstrip("/")
        local = is_loopback(base)
        return Target(
            provider=provider,
            api=API_OLLAMA,
            base_url=base,
            model=model or "llama3.1:8b",
            api_key=api_key,
            label=(
                "Ollama on this computer"
                if local
                else "Ollama at %s" % netloc(base)
            ),
            remote=not local,
        )
    if provider == CUSTOM:
        base = str(
            config.get("qgen_openai_base_url") or "http://localhost:1234/v1"
        )
        base = base.strip().rstrip("/")
        local = is_loopback(base)
        return Target(
            provider=provider,
            api=API_OPENAI,
            base_url=base,
            model=model,
            api_key=api_key,
            label=(
                "the local server at %s"
                if local
                else "the server at %s"
            )
            % netloc(base),
            remote=not local,
        )
    p = _BY_KEY.get(provider)
    if p is None:
        raise UnknownProvider(provider)
    return Target(
        provider=provider,
        api=p.api,
        base_url=p.base_url,
        model=model or p.models[0][0],
        api_key=api_key,
        label=p.label,
        remote=True,
        preset=p,
        headers=p.headers,
    )


def describe(config: dict) -> str:
    """Short phrase for status lines, e.g. "on your machine (llama3.1:8b)"."""
    try:
        t = resolve(config)
    except UnknownProvider as exc:
        return "with unknown provider %r" % str(exc)
    where = "on your machine" if not t.remote else "via %s" % t.label
    if t.preset is None and t.remote:
        where = "via %s" % t.host
    return "%s (%s)" % (where, t.model or "no model set")
