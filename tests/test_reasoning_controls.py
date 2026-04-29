"""Tests for provider-specific reasoning controls."""

from orchestrator.reasoning_controls import (
    ReasoningSettings,
    apply_reasoning_settings,
    resolve_reasoning_capabilities,
)


def test_fireworks_effort_sends_top_level_reasoning_effort_only():
    """Fireworks effort mode uses reasoning_effort, not thinking budget."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        reasoning_effort="high",
        fireworks_reasoning_mode="effort",
        fireworks_thinking_budget_tokens=4096,
    )

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="fireworks",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "reasoning_effort": "high",
    }


def test_fireworks_thinking_sends_budget_only():
    """Fireworks budget mode uses thinking.budget_tokens, not reasoning_effort."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        reasoning_effort="high",
        fireworks_reasoning_mode="thinking",
        fireworks_thinking_budget_tokens=4096,
    )

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="fireworks",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "thinking": {"type": "enabled", "budget_tokens": 4096},
    }


def test_fireworks_thinking_defaults_missing_budget():
    """Fireworks budget mode should save and send a sane default when UI budget is blank."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        reasoning_effort="high",
        fireworks_reasoning_mode="thinking",
        fireworks_thinking_budget_tokens=None,
    )

    assert settings.fireworks_thinking_budget_tokens == 1024

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="fireworks",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }


def test_fireworks_thinking_clamps_too_small_budget():
    """Fireworks rejects budgets below 1024, so settings normalize instead of failing to save."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        fireworks_reasoning_mode="thinking",
        fireworks_thinking_budget_tokens=500,
    )

    assert settings.fireworks_thinking_budget_tokens == 1024

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="fireworks",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }


def test_openrouter_sends_reasoning_object_with_max_tokens():
    """OpenRouter max reasoning tokens replaces effort because docs make them alternatives."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        reasoning_effort="medium",
        reasoning_max_tokens=512,
    )

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="openrouter",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "reasoning": {"max_tokens": 512},
    }
    assert "reasoning_effort" not in kwargs


def test_openrouter_sends_reasoning_effort_without_max_tokens():
    """OpenRouter effort is sent when no explicit reasoning token cap is set."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        reasoning_effort="medium",
    )

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="openrouter",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "reasoning": {"effort": "medium"},
    }


def test_deepinfra_sends_reasoning_effort_without_max_tokens_cap():
    """DeepInfra exposes effort/on-off, not a separate reasoning max token cap."""
    settings = ReasoningSettings(
        max_output_tokens=2048,
        reasoning_effort="medium",
        reasoning_max_tokens=512,
    )

    kwargs = apply_reasoning_settings(
        settings,
        provider_family="deepinfra",
        supports_reasoning=True,
    )

    assert kwargs == {
        "max_tokens": 2048,
        "reasoning_effort": "medium",
        "reasoning": {"effort": "medium"},
    }


def test_capabilities_are_provider_specific():
    """Provider capability metadata should not advertise generic fake options."""
    fireworks = resolve_reasoning_capabilities("fireworks", supports_reasoning=True)
    openrouter = resolve_reasoning_capabilities("openrouter", supports_reasoning=True)
    deepinfra = resolve_reasoning_capabilities("deepinfra", supports_reasoning=True)

    assert fireworks.reasoning_effort.options == ["low", "medium", "high"]
    assert fireworks.fireworks_thinking_budget_tokens.supported is True
    assert "minimal" not in fireworks.reasoning_effort.options
    assert "xhigh" not in fireworks.reasoning_effort.options

    assert openrouter.reasoning_effort.options == [
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert openrouter.reasoning_max_tokens.supported is True

    assert deepinfra.reasoning_effort.options == ["none", "low", "medium", "high"]
    assert deepinfra.reasoning_max_tokens.supported is False
