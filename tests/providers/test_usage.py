"""Tests for provider usage normalization."""

from orchestrator.providers.usage import add_usage, estimate_cost, normalize_usage


def test_normalize_chat_completion_usage():
    usage = normalize_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "total_tokens": 125,
            "completion_tokens_details": {"reasoning_tokens": 5},
            "prompt_tokens_details": {"cached_tokens": 20},
        }
    )

    assert usage == {
        "input_tokens": 100,
        "output_tokens": 25,
        "reasoning_tokens": 5,
        "cached_tokens": 20,
        "total_tokens": 125,
    }


def test_normalize_responses_usage():
    usage = normalize_usage(
        {
            "input_tokens": 200,
            "output_tokens": 50,
            "output_tokens_details": {"reasoning_tokens": 10},
        }
    )

    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 50
    assert usage["reasoning_tokens"] == 10
    assert usage["total_tokens"] == 250


def test_add_usage_accumulates_all_fields():
    total = normalize_usage({"prompt_tokens": 10, "completion_tokens": 5})
    add_usage(total, normalize_usage({"prompt_tokens": 3, "completion_tokens": 7}))

    assert total["input_tokens"] == 13
    assert total["output_tokens"] == 12
    assert total["total_tokens"] == 25


def test_estimate_cost_returns_none_without_pricing():
    assert estimate_cost(normalize_usage({"prompt_tokens": 10}), None, 1.0) is None


def test_estimate_cost_uses_per_million_prices():
    cost = estimate_cost(
        {"input_tokens": 1_000_000, "output_tokens": 500_000},
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
    )

    assert cost is not None
    assert cost["estimated"] is True
    assert cost["total_cost"] == 2.0


def test_estimate_cost_uses_cached_input_price():
    cost = estimate_cost(
        {"input_tokens": 1_000_000, "cached_tokens": 250_000, "output_tokens": 500_000},
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
        cached_input_cost_per_million=0.2,
    )

    assert cost is not None
    assert cost["input_cost"] == 0.75
    assert cost["cached_input_cost"] == 0.05
    assert cost["output_cost"] == 1.0
    assert cost["total_cost"] == 1.8
