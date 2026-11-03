"""Tests for the AI usage / cost tally and the monthly budget."""

import time

import pytest

from snip_occlusion import qgen_usage

NOV = time.mktime((2026, 11, 15, 12, 0, 0, 0, 0, -1))
DEC = time.mktime((2026, 12, 2, 12, 0, 0, 0, 0, -1))


def test_record_accumulates_per_model_and_month():
    c = qgen_usage.record("anthropic", "claude-sonnet-5-5", 2000, 1000, now=NOV)
    assert c == pytest.approx((2000 * 2 + 1000 * 10) / 1e6)
    qgen_usage.record("anthropic", "claude-sonnet-5-5", 2000, 1000, now=NOV)
    qgen_usage.record("ollama", "llama3.1:8b", 500, 100, now=NOV)
    qgen_usage.record("anthropic", "claude-sonnet-5-5", 10, 10, now=DEC)
    rows = qgen_usage.month_rows(now=NOV)
    assert rows["claude-sonnet-5-5"]["requests"] == 2
    assert rows["claude-sonnet-5-5"]["input_tokens"] == 4000
    assert "cost_usd" not in rows["llama3.1:8b"]  # free, unpriced
    assert qgen_usage.month_cost(now=NOV) == pytest.approx(0.028)
    assert qgen_usage.month_rows(now=DEC)["claude-sonnet-5-5"]["requests"] == 1


def test_bad_counts_are_ignored():
    assert qgen_usage.record("anthropic", "claude-opus-5-5", "x", None) is None
    assert qgen_usage.month_rows() == {}


def test_budget_only_holds_back_priced_models():
    qgen_usage.record("anthropic", "claude-opus-5-5", 500_000, 0, now=NOV)  # $2
    cfg = {"qgen_monthly_budget_usd": 2}
    assert qgen_usage.budget_problem(cfg, "claude-opus-5-5", now=NOV)
    assert qgen_usage.budget_problem(cfg, "llama3.1:8b", now=NOV) == ""
    assert qgen_usage.budget_problem({"qgen_monthly_budget_usd": 0}, "claude-opus-5-5", now=NOV) == ""
    assert qgen_usage.budget_problem({"qgen_monthly_budget_usd": 5}, "claude-opus-5-5", now=NOV) == ""
    # a new month starts from zero
    assert qgen_usage.budget_problem(cfg, "claude-opus-5-5", now=DEC) == ""
    assert qgen_usage.budget({"qgen_monthly_budget_usd": "junk"}) == 0.0


def test_summary_and_reset():
    assert qgen_usage.summary(now=NOV).startswith("No AI requests yet")
    qgen_usage.record("anthropic", "claude-haiku-5-5", 12_000, 3_000, now=NOV)
    text = qgen_usage.summary({"qgen_monthly_budget_usd": 1}, now=NOV)
    assert "November 2026" in text
    assert "claude-haiku-5-5: 1 request · 12k in / 3.0k out tokens" in text
    assert "Monthly budget: $1.00" in text
    qgen_usage.reset_month(now=NOV)
    assert qgen_usage.month_rows(now=NOV) == {}
