"""Tests for configuration loading and validation."""

import os
import pytest
from unittest.mock import patch
from orchestrator.config import (
    resolve_env_vars,
    get_chat_config,
    ChatConfig,
    ProviderConfig,
    ChatModelConfig,
    ChatContextConfig,
    ThinkingConfig,
)


class TestResolveEnvVars:
    """Tests for environment variable resolution."""

    def test_resolve_required_env_var_present(self):
        """Required env var resolves when set."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = resolve_env_vars("${TEST_VAR}")
            assert result == "test_value"

    def test_resolve_required_env_var_missing_raises(self):
        """Required env var without default raises error."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the var is not set
            os.environ.pop("MISSING_VAR", None)
            with pytest.raises(ValueError, match="Environment variable MISSING_VAR not set"):
                resolve_env_vars("${MISSING_VAR}")

    def test_resolve_optional_env_var_with_default(self):
        """Optional env var uses default when not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPTIONAL_VAR", None)
            result = resolve_env_vars("${OPTIONAL_VAR:-default_value}")
            assert result == "default_value"

    def test_resolve_optional_env_var_overrides_default(self):
        """Set env var overrides default."""
        with patch.dict(os.environ, {"OPTIONAL_VAR": "actual_value"}):
            result = resolve_env_vars("${OPTIONAL_VAR:-default_value}")
            assert result == "actual_value"

    def test_resolve_empty_default(self):
        """Empty default is valid."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("EMPTY_DEFAULT", None)
            result = resolve_env_vars("${EMPTY_DEFAULT:-}")
            assert result == ""

    def test_resolve_nested_dict(self):
        """Resolves env vars in nested dicts."""
        with patch.dict(os.environ, {"DB_HOST": "localhost"}):
            data = {"database": {"host": "${DB_HOST}"}}
            result = resolve_env_vars(data)
            assert result == {"database": {"host": "localhost"}}

    def test_resolve_list(self):
        """Resolves env vars in lists."""
        with patch.dict(os.environ, {"ITEM": "value"}):
            data = ["${ITEM}", "static"]
            result = resolve_env_vars(data)
            assert result == ["value", "static"]

    def test_resolve_non_string_passthrough(self):
        """Non-string values pass through unchanged."""
        assert resolve_env_vars(42) == 42
        assert resolve_env_vars(3.14) == 3.14
        assert resolve_env_vars(True) is True
        assert resolve_env_vars(None) is None


class TestProviderConfig:
    """Tests for ProviderConfig validation."""

    def test_default_values(self):
        """ProviderConfig has sensible defaults."""
        config = ProviderConfig()
        assert config.base_url == "http://127.0.0.1:1234"
        assert config.api_key is None
        assert config.endpoint == "responses"
        assert config.fallback_on_404 is True
        assert config.timeout == 120.0
        assert config.max_retries == 3

    def test_empty_api_key_becomes_none(self):
        """Empty string api_key converts to None."""
        config = ProviderConfig(api_key="")
        assert config.api_key is None

    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "fw-key"}, clear=True)
    def test_fireworks_api_key_falls_back_to_provider_env(self):
        """Fireworks config uses FIREWORKS_API_KEY when api_key is omitted."""
        config = ProviderConfig(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key="",
        )
        assert config.api_key == "fw-key"

    @patch.dict(os.environ, {"DEEPINFRA_API_KEY": "di-key"}, clear=True)
    def test_deepinfra_api_key_falls_back_to_provider_env(self):
        """DeepInfra config uses DEEPINFRA_API_KEY when api_key is omitted."""
        config = ProviderConfig(
            base_url="https://api.deepinfra.com/v1/openai",
            api_key="",
        )
        assert config.api_key == "di-key"

    def test_valid_endpoint_values(self):
        """Valid endpoint values are accepted."""
        for endpoint in ["responses", "chat_completions", "auto"]:
            config = ProviderConfig(endpoint=endpoint)
            assert config.endpoint == endpoint

    def test_retryable_statuses(self):
        """Retryable statuses are configurable."""
        config = ProviderConfig(retryable_statuses=[500, 503])
        assert config.retryable_statuses == [500, 503]


class TestChatModelConfig:
    """Tests for ChatModelConfig validation."""

    def test_default_values(self):
        """ChatModelConfig has sensible defaults."""
        config = ChatModelConfig()
        assert config.name == "accounts/fireworks/models/kimi-k2p6"
        assert config.temperature == 0.7
        assert config.max_tokens == 32768
        assert config.reasoning_effort is None

    def test_reasoning_effort_values(self):
        """Valid reasoning effort values are accepted."""
        for effort in ["low", "medium", "high"]:
            config = ChatModelConfig(reasoning_effort=effort)
            assert config.reasoning_effort == effort


class TestChatContextConfig:
    """Tests for ChatContextConfig validation."""

    def test_default_values(self):
        """ChatContextConfig has sensible defaults."""
        config = ChatContextConfig()
        assert config.max_messages == 50
        assert config.max_tokens == 6000
        assert config.truncation_strategy == "sliding_window"


class TestThinkingConfig:
    """Tests for ThinkingConfig validation."""

    def test_default_mode_mapping(self):
        """Default mode mapping uses direct for all modes."""
        config = ThinkingConfig()
        assert config.mode_mapping["default"] == "direct"
        assert config.mode_mapping["thinking"] == "direct"

    def test_tracing_defaults(self):
        """Thinking tracing has sensible defaults."""
        config = ThinkingConfig()
        assert config.tracing.save_internal is True
        assert config.tracing.save_user_summary is True


class TestChatConfig:
    """Tests for complete ChatConfig."""

    def test_endpoint_alias(self):
        """endpoint property returns provider.base_url."""
        config = ChatConfig(provider=ProviderConfig(base_url="http://custom:8080"))
        assert config.endpoint == "http://custom:8080"

    def test_get_snapshot(self):
        """get_snapshot returns config summary."""
        config = ChatConfig()
        snapshot = config.get_snapshot()

        assert "provider" in snapshot
        assert "model" in snapshot
        assert "context" in snapshot
        assert "system_prompt_hash" in snapshot
        assert "thinking" in snapshot

    def test_nested_config_loading(self):
        """Nested configs load correctly."""
        config = ChatConfig(
            provider=ProviderConfig(base_url="http://test:1234"),
            model=ChatModelConfig(temperature=0.5),
        )
        assert config.provider.base_url == "http://test:1234"
        assert config.model.temperature == 0.5


class TestGetChatConfig:
    """Tests for get_chat_config function."""

    def test_returns_cached_config(self):
        """Subsequent calls return cached config."""
        config1 = get_chat_config()
        config2 = get_chat_config()
        # Same object (cached)
        assert config1 is config2

    def test_reload_returns_fresh_config(self):
        """reload=True returns fresh config."""
        config1 = get_chat_config()
        config2 = get_chat_config(reload=True)
        # Different object (reloaded)
        assert config1 is not config2
