"""Tests for model-aware context parameter resolution."""

import pytest
from unittest.mock import patch, MagicMock

from orchestrator.context.budget import context_params_for_model


class TestContextParamsForModel:
    """Test context_params_for_model() resolution."""

    def test_returns_config_defaults_when_model_is_none(self):
        max_ctx, reserve = context_params_for_model(
            model_name=None,
            config_max_tokens=100000,
            config_reserve=16384,
        )
        assert max_ctx == 100000
        assert reserve == 16384

    def test_floor_when_config_is_small(self):
        """Config values below 32768 should be floored."""
        max_ctx, reserve = context_params_for_model(
            model_name=None,
            config_max_tokens=6000,
            config_reserve=4096,
        )
        assert max_ctx == 32768
        assert reserve == 4096

    @patch("orchestrator.models.registry.ModelRegistry.resolve")
    def test_uses_model_registry_when_model_found(self, mock_resolve):
        resolved = MagicMock()
        resolved.context_window = 131072
        resolved.max_output_tokens = 16384
        mock_resolve.return_value = resolved

        max_ctx, reserve = context_params_for_model(
            model_name="qwen3-72b",
            config_max_tokens=100000,
            config_reserve=4096,
        )
        assert max_ctx == 131072
        assert reserve == 16384
        mock_resolve.assert_called_once_with("qwen3-72b")

    @patch("orchestrator.models.registry.ModelRegistry.resolve")
    def test_falls_back_on_registry_error(self, mock_resolve):
        mock_resolve.side_effect = ValueError("No API key")

        max_ctx, reserve = context_params_for_model(
            model_name="unknown-model",
            config_max_tokens=100000,
            config_reserve=16384,
        )
        assert max_ctx == 100000
        assert reserve == 16384

    @patch("orchestrator.models.registry.ModelRegistry.resolve")
    def test_large_context_model(self, mock_resolve):
        resolved = MagicMock()
        resolved.context_window = 1048576  # 1M context
        resolved.max_output_tokens = 32768
        mock_resolve.return_value = resolved

        max_ctx, reserve = context_params_for_model(
            model_name="llama4-maverick",
            config_max_tokens=100000,
            config_reserve=4096,
        )
        assert max_ctx == 1048576
        assert reserve == 32768
