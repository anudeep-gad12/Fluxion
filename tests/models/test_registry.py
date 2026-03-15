"""Tests for the model registry.

Unit tests for ModelRegistry.resolve() and list_models().
No real API calls — API keys mocked via environment variables.
"""

import os
from unittest.mock import patch

import pytest

from orchestrator.models.registry import (
    MODEL_PRESETS,
    PROVIDERS,
    ModelRegistry,
    ResolvedModel,
)


class TestResolveByAlias:
    """Tests for alias-based model resolution."""

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_resolve_by_alias(self):
        """'qwen3-72b' resolves to full model preset."""
        resolved = ModelRegistry.resolve("qwen3-72b")
        assert resolved.model_id == "qwen/qwen3-72b"
        assert resolved.display_name == "Qwen 3 72B"
        assert resolved.provider_name == "openrouter"
        assert resolved.api_key == "test-key"

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_resolve_by_full_id(self):
        """'qwen/qwen3-72b' resolves directly."""
        resolved = ModelRegistry.resolve("qwen/qwen3-72b")
        assert resolved.model_id == "qwen/qwen3-72b"
        assert resolved.provider_name == "openrouter"

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-key"})
    def test_case_insensitive_aliases(self):
        """'QWEN3-72B' and 'Qwen3-72b' both resolve."""
        r1 = ModelRegistry.resolve("QWEN3-72B")
        r2 = ModelRegistry.resolve("Qwen3-72b")
        r3 = ModelRegistry.resolve("qwen3-72b")
        assert r1.model_id == r2.model_id == r3.model_id

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-key"})
    def test_resolved_model_has_correct_context_window(self):
        """Each preset returns its specific context window."""
        r1 = ModelRegistry.resolve("qwen3-72b")
        r2 = ModelRegistry.resolve("deepseek-r1")
        assert r1.context_window == 131072
        assert r2.context_window == 163840


class TestExplicitProviderPrefix:
    """Tests for explicit provider:model syntax."""

    @patch.dict(os.environ, {"DEEPINFRA_API_KEY": "di-key"})
    def test_resolve_explicit_provider_prefix(self):
        """'deepinfra:meta-llama/...' forces DeepInfra provider."""
        resolved = ModelRegistry.resolve("deepinfra:some-unknown-model")
        assert resolved.provider_name == "deepinfra"
        assert resolved.model_id == "some-unknown-model"
        assert resolved.api_key == "di-key"

    @patch.dict(os.environ, {}, clear=True)
    def test_explicit_provider_no_key_raises(self):
        """Explicit provider without API key raises ValueError."""
        # Clear all provider keys
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="No API key"):
                ModelRegistry.resolve("deepinfra:some-model")


class TestProviderDetection:
    """Tests for auto-provider detection based on API keys."""

    def test_detect_provider_openrouter_key_only(self):
        """When only OPENROUTER_API_KEY set, auto-selects OpenRouter."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY")}
        env["OPENROUTER_API_KEY"] = "or-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "openrouter"

    def test_detect_provider_deepinfra_key_only(self):
        """When only DEEPINFRA_API_KEY set, auto-selects DeepInfra."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY")}
        env["DEEPINFRA_API_KEY"] = "di-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "deepinfra"

    def test_detect_provider_both_keys_prefers_openrouter(self):
        """Both keys set -> defaults to OpenRouter (larger catalog)."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY")}
        env["OPENROUTER_API_KEY"] = "or-key"
        env["DEEPINFRA_API_KEY"] = "di-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "openrouter"


class TestProviderHint:
    """Tests for models with provider_hint."""

    @patch.dict(os.environ, {"DEEPINFRA_API_KEY": "di-key"})
    def test_gpt_oss_routes_to_deepinfra(self):
        """gpt-oss models always route to DeepInfra (provider_hint)."""
        resolved = ModelRegistry.resolve("gpt-oss-120b")
        assert resolved.provider_name == "deepinfra"
        assert "gpt-oss" in resolved.model_id


class TestUnknownModelFallback:
    """Tests for unknown model handling."""

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-key"})
    def test_resolve_unknown_model_fallback(self):
        """Unknown model gets conservative defaults, routes to available provider."""
        resolved = ModelRegistry.resolve("totally-unknown-model-v99")
        assert resolved.model_id == "totally-unknown-model-v99"
        assert resolved.context_window == 32768
        assert resolved.temperature == 0.7
        assert resolved.provider_name in ("openrouter", "deepinfra", "local")

    def test_missing_api_key_falls_back_to_local(self):
        """No cloud keys set falls back to local provider."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-model")
            assert resolved.provider_name == "local"


class TestLocalProvider:
    """Tests for local provider resolution."""

    def test_local_provider_no_api_key_required(self):
        """Local provider resolves without any API key."""
        resolved = ModelRegistry.resolve("local")
        assert resolved.provider_name == "local"
        assert resolved.base_url == "http://localhost:8080/v1"
        assert resolved.api_key is None


class TestListModels:
    """Tests for list_models()."""

    def test_list_models_groups_by_provider(self):
        """list_models() returns presets grouped by provider with availability."""
        result = ModelRegistry.list_models()
        assert "openrouter" in result
        assert "deepinfra" in result
        assert "local" in result
        assert "models" in result["openrouter"]
        assert "available" in result["openrouter"]
        assert "api_key_env" in result["openrouter"]

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_list_models_availability_with_key(self):
        """Provider with API key shows as available."""
        result = ModelRegistry.list_models()
        assert result["openrouter"]["available"] is True

    def test_list_models_local_always_available(self):
        """Local provider always shows as available."""
        result = ModelRegistry.list_models()
        assert result["local"]["available"] is True

    def test_list_models_has_presets(self):
        """Each provider group contains model presets."""
        result = ModelRegistry.list_models()
        openrouter_models = result["openrouter"]["models"]
        assert len(openrouter_models) > 0
        assert "model_id" in openrouter_models[0]
        assert "display_name" in openrouter_models[0]


class TestResolvedModelShape:
    """Tests for ResolvedModel dataclass completeness."""

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_resolved_model_has_all_fields(self):
        """ResolvedModel has all required fields."""
        resolved = ModelRegistry.resolve("qwen3-72b")
        assert isinstance(resolved, ResolvedModel)
        assert resolved.model_id
        assert resolved.display_name
        assert resolved.provider_name
        assert resolved.base_url
        assert resolved.endpoint
        assert resolved.context_window > 0
        assert resolved.max_output_tokens > 0
        assert isinstance(resolved.supports_tools, bool)
