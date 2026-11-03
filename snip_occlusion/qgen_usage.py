"""What the AI has cost: tokens per model per month, and a budget.

Every reply that reports its token counts (Claude, the OpenAI-style
hosted services, Ollama) is tallied here by calendar month and model.
For Claude models the cost is estimated from Anthropic's list prices
(qgen_providers.CLAUDE_PRICES); other providers are tracked in tokens
only, since their prices vary by plan.

The optional "qgen_monthly_budget_usd" stops further paid (priced)
requests once this month's estimated spend reaches it - a guard
against a runaway month, not an invoice: the Claude Console's usage
page stays the authority on what was actually billed.

Stored in user_files/qgen_usage.json, which Anki preserves across
add-on updates. Nothing here leaves the computer.
"""

from __future__ import annotations

import json
import os
import threading
import time

from . import qgen_providers

_lock = threading.Lock()
_KEEP_MONTHS = 24


def _path() -> str:
    return os.path.join(
        os.path.dirname(__file__), "user_files", "qgen_usage.json"
    )


def month_key(now: float | None = None) -> str:
    return time.strftime("%Y-%m", time.localtime(now))


def _load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        months = data.get("months")
        return {"months": months if isinstance(months, dict) else {}}
    except Exception:
        return {"months": {}}


def _save(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        os.replace(tmp, _path())
    except Exception:
        pass  # usage tracking must never break card generation


def cost_of(model: str, input_tokens: int, output_tokens: int):
    """Estimated dollars for one request, or None when unpriced."""
    price = qgen_providers.claude_price(model)
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


def record(
    provider: str,
    model: str,
    input_tokens,
    output_tokens,
    now: float | None = None,
):
    """Add one request's token counts; return its estimated cost (or None)."""
    try:
        tin = max(0, int(input_tokens or 0))
        tout = max(0, int(output_tokens or 0))
    except (TypeError, ValueError):
        return None
    model = str(model or "unknown")
    cost = cost_of(model, tin, tout)
    key = month_key(now)
    with _lock:
        data = _load()
        months = data["months"]
        month = months.setdefault(key, {})
        row = month.setdefault(
            model,
            {
                "provider": qgen_providers.normalise(provider),
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            },
        )
        row["requests"] = int(row.get("requests", 0)) + 1
        row["input_tokens"] = int(row.get("input_tokens", 0)) + tin
        row["output_tokens"] = int(row.get("output_tokens", 0)) + tout
        if cost is not None:
            row["cost_usd"] = float(row.get("cost_usd", 0.0)) + cost
        for old in sorted(months)[:-_KEEP_MONTHS]:
            months.pop(old, None)
        _save(data)
    return cost


def month_rows(now: float | None = None) -> dict:
    """{model: {provider, requests, input_tokens, output_tokens, cost_usd?}}"""
    with _lock:
        return dict(_load()["months"].get(month_key(now), {}))


def month_cost(now: float | None = None) -> float:
    return sum(
        float(r.get("cost_usd", 0.0))
        for r in month_rows(now).values()
        if isinstance(r, dict)
    )


def reset_month(now: float | None = None) -> None:
    with _lock:
        data = _load()
        data["months"].pop(month_key(now), None)
        _save(data)


def budget(config: dict) -> float:
    """The monthly budget in dollars; 0 means no limit."""
    try:
        return max(0.0, float(config.get("qgen_monthly_budget_usd") or 0))
    except (TypeError, ValueError):
        return 0.0


def budget_problem(config: dict, model: str, now: float | None = None) -> str:
    """Why a request to `model` must not be sent, or "" when it may.

    Only priced models are held back: the budget is in dollars, and a
    free local model costs nothing whatever the month's total.
    """
    limit = budget(config)
    if limit <= 0 or qgen_providers.claude_price(model) is None:
        return ""
    spent = month_cost(now)
    if spent < limit:
        return ""
    return (
        "This month's AI budget of $%.2f is used up (about $%.2f spent "
        "so far). Raise or clear the budget in ⚙ Settings → AI model, "
        "or switch to a free model until next month." % (limit, spent)
    )


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return "%.1fM" % (n / 1_000_000)
    if n >= 10_000:
        return "%dk" % round(n / 1000)
    if n >= 1000:
        return "%.1fk" % (n / 1000)
    return str(n)


def _fmt_cost(c: float) -> str:
    if 0 < c < 0.01:
        return "under $0.01"
    return "≈ $%.2f" % c


def summary(config: dict | None = None, now: float | None = None) -> str:
    """A few lines for the Settings window: this month, per model."""
    rows = month_rows(now)
    title = time.strftime("%B %Y", time.localtime(now))
    if not rows:
        text = "No AI requests yet in %s." % title
    else:
        lines = []
        total_cost = 0.0
        priced = False
        for model in sorted(rows):
            r = rows[model]
            if not isinstance(r, dict):
                continue
            n = int(r.get("requests", 0))
            line = "%s: %d request%s · %s in / %s out tokens" % (
                model,
                n,
                "" if n == 1 else "s",
                _fmt_tokens(int(r.get("input_tokens", 0))),
                _fmt_tokens(int(r.get("output_tokens", 0))),
            )
            if "cost_usd" in r:
                c = float(r["cost_usd"])
                total_cost += c
                priced = True
                line += " · %s" % _fmt_cost(c)
            lines.append(line)
        head = "%s so far" % title
        if priced:
            head += ": %s on Claude" % _fmt_cost(total_cost)
        text = "\n".join([head] + lines)
    limit = budget(config or {})
    if limit > 0:
        text += "\nMonthly budget: $%.2f ($%.2f left)" % (
            limit,
            max(0.0, limit - month_cost(now)),
        )
    return text
