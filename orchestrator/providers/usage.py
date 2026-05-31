"""Provider usage normalization and cost estimation."""

from typing import Any, Optional


def normalize_usage(raw_usage: dict[str, Any] | None) -> dict[str, int]:
    """Normalize provider token usage into a stable internal shape."""
    raw = raw_usage or {}

    input_tokens = int(
        raw.get("input_tokens")
        or raw.get("prompt_tokens")
        or raw.get("prompt_token_count")
        or 0
    )
    output_tokens = int(
        raw.get("output_tokens")
        or raw.get("completion_tokens")
        or raw.get("completion_token_count")
        or 0
    )

    reasoning_tokens = 0
    details = raw.get("completion_tokens_details") or raw.get("output_tokens_details") or {}
    if isinstance(details, dict):
        reasoning_tokens = int(details.get("reasoning_tokens") or 0)
    reasoning_tokens = int(raw.get("reasoning_tokens") or reasoning_tokens or 0)

    cached_tokens = 0
    prompt_details = raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    if isinstance(prompt_details, dict):
        cached_tokens = int(prompt_details.get("cached_tokens") or 0)
    cached_tokens = int(raw.get("cached_tokens") or cached_tokens or 0)

    total_tokens = int(raw.get("total_tokens") or input_tokens + output_tokens)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
    }


def add_usage(total: dict[str, int], usage: dict[str, int]) -> dict[str, int]:
    """Add normalized usage into a cumulative total."""
    for key in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "total_tokens",
    ):
        total[key] = int(total.get(key, 0)) + int(usage.get(key, 0))
    return total


def estimate_cost(
    usage: dict[str, int],
    input_cost_per_million: Optional[float],
    output_cost_per_million: Optional[float],
    cached_input_cost_per_million: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """Estimate USD cost from token usage and per-million prices."""
    if not isinstance(input_cost_per_million, (int, float)) or not isinstance(
        output_cost_per_million, (int, float)
    ):
        return None
    if cached_input_cost_per_million is not None and not isinstance(
        cached_input_cost_per_million, (int, float)
    ):
        cached_input_cost_per_million = None

    cached_tokens = max(0, int(usage.get("cached_tokens", 0) or 0))
    input_tokens = max(0, int(usage.get("input_tokens", 0) or 0))
    uncached_input_tokens = max(0, input_tokens - cached_tokens)
    cached_price = (
        cached_input_cost_per_million
        if cached_input_cost_per_million is not None
        else input_cost_per_million
    )

    input_cost = (uncached_input_tokens / 1_000_000) * input_cost_per_million
    cached_input_cost = (cached_tokens / 1_000_000) * cached_price
    output_cost = (usage.get("output_tokens", 0) / 1_000_000) * output_cost_per_million
    total = input_cost + cached_input_cost + output_cost

    return {
        "estimated": True,
        "currency": "USD",
        "input_cost": round(input_cost, 8),
        "cached_input_cost": round(cached_input_cost, 8),
        "output_cost": round(output_cost, 8),
        "total_cost": round(total, 8),
        "input_cost_per_million": input_cost_per_million,
        "cached_input_cost_per_million": cached_price,
        "output_cost_per_million": output_cost_per_million,
    }
