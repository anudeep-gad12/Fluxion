"""Tests for runtime reasoning settings defaults."""

from orchestrator.config import ChatConfig
from orchestrator.reasoning_controls import ReasoningSettings
from orchestrator.services.reasoning_settings import (
    _should_migrate_legacy_max_output_default,
    default_reasoning_settings,
)


def test_default_reasoning_settings_uses_model_max_output_auto():
    settings = default_reasoning_settings(ChatConfig())

    assert settings.max_output_tokens is None


def test_legacy_static_max_output_default_migrates_to_auto():
    cfg = ChatConfig()
    settings = default_reasoning_settings(cfg).model_copy(update={"max_output_tokens": 2048})

    assert _should_migrate_legacy_max_output_default(settings, cfg) is True


def test_non_legacy_custom_max_output_token_cap_is_preserved():
    cfg = ChatConfig()
    settings = ReasoningSettings(max_output_tokens=4096, reasoning_effort="low")

    assert _should_migrate_legacy_max_output_default(settings, cfg) is False
