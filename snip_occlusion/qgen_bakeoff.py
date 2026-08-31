"""Model bake-off: let the user's own verdicts pick the best model.

When enabled, each generation picks one of the configured models at
random. Each suggested card remembers which model wrote it; the user's
verdicts (Use / ★ Great / Skip / ✗ Bad) are tallied per model, along
with generation times. The summary reports each model's kept-rate and
speed, and says whether the quality difference is statistically
meaningful yet - so the faster model can be adopted with evidence
rather than vibes.

Stats live in user_files/qgen_bakeoff.json (kept across updates).
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time

from . import qgen

_lock = threading.Lock()

VERDICTS = ("use", "great", "skip", "bad")
_MIN_VERDICTS = 10  # per model, before a comparison is attempted
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.I)


def _path() -> str:
    return os.path.join(
        os.path.dirname(__file__), "user_files", "qgen_bakeoff.json"
    )


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        data = {}
    data.setdefault("next", 0)
    if not isinstance(data.get("models"), dict):
        data["models"] = {}
    return data


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except Exception:
        pass  # stats are best-effort; never break generation over them


def _stats(data: dict, model: str) -> dict:
    return data["models"].setdefault(
        model,
        {
            "use": 0,
            "great": 0,
            "skip": 0,
            "bad": 0,
            "seconds": 0.0,
            "gens": 0,
            "cards": 0,
        },
    )


def enabled(config: dict) -> bool:
    return bool(config.get("qgen_bakeoff", False))


def contenders(config: dict) -> list:
    raw = config.get("qgen_bakeoff_models")
    names = [
        m.strip()
        for m in (raw if isinstance(raw, list) else [])
        if isinstance(m, str) and m.strip()
    ]
    if len(names) >= 2:
        return names
    return ["llama3.1:8b", "llama3.2:3b"]


def small_large(config: dict) -> tuple:
    """(smaller model, bigger model) of the first two contenders.

    Sizes are read from the name ("3b", "8b", "1.5b"); if neither name
    carries a size, the configured order decides (second = smaller).
    """
    names = contenders(config)[:2]

    def size(name: str) -> float:
        m = _SIZE_RE.search(name)
        return float(m.group(1)) if m else float("inf")

    ordered = sorted(names, key=size)
    return ordered[0], ordered[-1]


def generate(text: str, config: dict, source: str = "slide") -> list:
    """qgen.generate_cards, randomising and timing models when enabled.

    Cards from a bake-off generation carry a "_model" key so verdicts
    can be credited to the right model.
    """
    if not enabled(config):
        return qgen.generate_cards(text, config, source=source)
    # random choice, so verdicts can't be biased by a predictable order
    model = random.choice(contenders(config))
    cfg = dict(config)
    cfg["qgen_model"] = model
    start = time.monotonic()
    cards = qgen.generate_cards(text, cfg, source=source)
    elapsed = time.monotonic() - start
    with _lock:
        data = _load()
        s = _stats(data, model)
        s["seconds"] += elapsed
        s["gens"] += 1
        s["cards"] += len(cards)
        _save(data)
    for card in cards:
        card["_model"] = model
    return cards


def tally(card: dict, verdict: str, undo: bool = False) -> None:
    """Credit (or, on undo, un-credit) a verdict to the card's model."""
    model = (card or {}).get("_model") or ""
    if not model or verdict not in VERDICTS:
        return
    with _lock:
        data = _load()
        s = _stats(data, model)
        s[verdict] = max(0, s[verdict] + (-1 if undo else 1))
        _save(data)


def summary() -> str:
    """Human-readable scoreboard, with a significance note for 2 models."""
    with _lock:
        data = _load()
    if not data["models"]:
        return (
            "No bake-off data yet - turn the bake-off on and judge some "
            "suggestions."
        )
    lines = []
    rates = []
    for model in sorted(data["models"]):
        s = _stats(data, model)
        judged = sum(s[v] for v in VERDICTS)
        kept = s["use"] + s["great"]
        parts = [model + ":"]
        if judged:
            rate = kept / judged
            parts.append("kept %d%% (%d of %d)" % (round(rate * 100), kept, judged))
            rates.append((rate, judged))
        else:
            parts.append("no verdicts yet")
        if s["gens"]:
            parts.append(
                "· avg %.0fs/generation over %d runs"
                % (s["seconds"] / s["gens"], s["gens"])
            )
        lines.append(" ".join(parts))
    if len(rates) == 2:
        (p1, n1), (p2, n2) = rates
        if min(n1, n2) < _MIN_VERDICTS:
            lines.append(
                "Verdict: too early to call - judge at least %d cards "
                "per model." % _MIN_VERDICTS
            )
        else:
            pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
            se = math.sqrt(
                max(pooled * (1 - pooled), 1e-9) * (1 / n1 + 1 / n2)
            )
            if abs(p1 - p2) > 1.96 * se:
                lines.append(
                    "Verdict: the kept-rate difference looks REAL "
                    "(beyond noise at ~95% confidence)."
                )
            else:
                lines.append(
                    "Verdict: no meaningful quality difference so far - "
                    "the faster model is winning."
                )
    return "\n".join(lines)
