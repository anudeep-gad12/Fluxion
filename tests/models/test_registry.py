"""Tests for the model registry.

Unit tests for ModelRegistry.resolve() and list_models().
No real API calls — API keys mocked via environment variables.
"""

import asyncio
import os
from unittest.mock import patch

import pytest

from orchestrator.models.registry import (
    MODEL_PRESETS,
    PROVIDERS,
    ModelRegistry,
    ResolvedModel,
)
from orchestrator.providers.factory import create_provider_for_model


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

    @patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"})
    def test_resolve_openai_provider_prefix(self):
        """'openai:model' forces the OpenAI API provider."""
        resolved = ModelRegistry.resolve("openai:gpt-5.2-codex")
        assert resolved.provider_name == "openai"
        assert resolved.model_id == "gpt-5.2-codex"
        assert resolved.endpoint == "responses"
        assert resolved.api_key == "openai-key"
        assert resolved.supports_tools is True
        assert resolved.reasoning_request_param == "reasoning"

    def test_resolve_chatgpt_subscription_models(self):
        """ChatGPT subscription uses current GPT model IDs, not stale Codex IDs."""
        resolved = ModelRegistry.resolve("chatgpt:gpt-5.5")
        assert resolved.provider_name == "chatgpt"
        assert resolved.model_id == "gpt-5.5"
        assert resolved.api_key is None

        alias = ModelRegistry.resolve("chatgpt:chatgpt-latest")
        assert alias.model_id == "gpt-5.5"

    def test_reject_unknown_chatgpt_model(self):
        """Unknown ChatGPT subscription model IDs should fail at selection time."""
        with pytest.raises(ValueError, match="Unsupported ChatGPT/Codex model"):
            ModelRegistry.resolve("chatgpt:gpt-5.3-codex")

    @patch.dict(os.environ, {"XAI_API_KEY": "xai-key"})
    def test_resolve_xai_provider_prefix(self):
        """'xai:model' forces the xAI provider."""
        resolved = ModelRegistry.resolve("xai:grok-4.3")
        assert resolved.provider_name == "xai"
        assert resolved.model_id == "grok-4.3"
        assert resolved.endpoint == "responses"
        assert resolved.api_key == "xai-key"
        assert resolved.reasoning_effort == "medium"

    @patch.dict(os.environ, {"XAI_API_KEY": "xai-key"})
    def test_xai_grok_build_does_not_send_reasoning_effort(self):
        """Grok Build on xAI rejects reasoningEffort, so metadata disables it."""
        resolved = ModelRegistry.resolve("xai:grok-build-0.1")
        assert resolved.provider_name == "xai"
        assert resolved.model_id == "grok-build-0.1"
        assert resolved.reasoning_effort is None
        assert resolved.reasoning_request_param is None

    def test_resolve_grok_oauth_provider_prefix(self, tmp_path, monkeypatch):
        """'grok:model' uses local Grok CLI OAuth credentials, not XAI_API_KEY."""
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            """
            {
              "https://auth.x.ai::client": {
                "key": "grok-token",
                "auth_mode": "oidc",
                "email": "user@example.com",
                "expires_at": "2999-01-01T00:00:00Z",
                "oidc_issuer": "https://auth.x.ai"
              }
            }
            """
        )
        monkeypatch.setenv("GROK_AUTH_FILE", str(auth_file))

        resolved = ModelRegistry.resolve("grok:grok-build")
        assert resolved.provider_name == "grok"
        assert resolved.model_id == "grok-build"
        assert resolved.base_url == "https://cli-chat-proxy.grok.com/v1"
        assert resolved.endpoint == "responses"
        assert resolved.api_key == "grok-token"
        assert resolved.reasoning_effort is None

        composer = ModelRegistry.resolve("grok:grok-composer-2.5-fast")
        assert composer.provider_name == "grok"
        assert composer.model_id == "grok-composer-2.5-fast"
        assert composer.display_name == "Composer 2.5"
        assert composer.api_key == "grok-token"

        composer_alias = ModelRegistry.resolve("grok:composer-2.5-fast")
        assert composer_alias.model_id == "grok-composer-2.5-fast"

    def test_resolve_grok_oauth_without_token_raises(self, tmp_path, monkeypatch):
        """Grok OAuth provider requires a valid local Grok CLI token."""
        monkeypatch.setenv("GROK_AUTH_FILE", str(tmp_path / "missing-auth.json"))
        with pytest.raises(ValueError, match="Connect Grok OAuth"):
            ModelRegistry.resolve("grok:grok-build")

    def test_grok_provider_uses_cli_proxy_headers(self, tmp_path, monkeypatch):
        """Grok OAuth provider sends the CLI-token auth headers required by the proxy."""
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            """
            {
              "https://auth.x.ai::client": {
                "key": "grok-token",
                "auth_mode": "oidc",
                "expires_at": "2999-01-01T00:00:00Z",
                "oidc_issuer": "https://auth.x.ai"
              }
            }
            """
        )
        monkeypatch.setenv("GROK_AUTH_FILE", str(auth_file))

        provider, resolved = create_provider_for_model("grok:grok-build")
        assert resolved.provider_name == "grok"
        assert provider._client.headers["authorization"] == "Bearer grok-token"  # noqa: SLF001
        assert provider._client.headers["x-xai-token-auth"] == "xai-grok-cli"  # noqa: SLF001
        assert provider._client.headers["x-grok-model-override"] == "grok-build"  # noqa: SLF001
        assert provider._client.headers["x-grok-client-version"]  # noqa: SLF001
        assert provider._client.headers["x-grok-client-identifier"] == "fluxion"  # noqa: SLF001
        asyncio.run(provider.close())

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
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="No API key"):
                ModelRegistry.resolve("deepinfra:some-model")


class TestProviderDetection:
    """Tests for auto-provider detection based on API keys."""

    def test_detect_provider_openrouter_key_only(self):
        """When only OPENROUTER_API_KEY set, auto-selects OpenRouter."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY")}
        env["OPENROUTER_API_KEY"] = "or-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "openrouter"

    def test_detect_provider_deepinfra_key_only(self):
        """When only DEEPINFRA_API_KEY set, auto-selects DeepInfra."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY")}
        env["DEEPINFRA_API_KEY"] = "di-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "deepinfra"

    def test_detect_provider_both_keys_prefers_openrouter(self):
        """Both keys set -> defaults to OpenRouter (larger catalog)."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY")}
        env["OPENROUTER_API_KEY"] = "or-key"
        env["DEEPINFRA_API_KEY"] = "di-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "openrouter"


    def test_explicit_provider_without_key_does_not_fallback(self, monkeypatch):
        """Explicit provider:model selections must not silently route elsewhere."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("FIREWORKS_API_KEY", "fireworks-key")

        with pytest.raises(ValueError, match="No API key found for openrouter"):
            ModelRegistry.resolve("openrouter:qwen/qwen3-72b")

    def test_detect_provider_fireworks_key_only(self):
        """When only FIREWORKS_API_KEY is set, auto-selects Fireworks."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY")}
        env["FIREWORKS_API_KEY"] = "fw-key"
        with patch.dict(os.environ, env, clear=True):
            resolved = ModelRegistry.resolve("some-unknown-model")
            assert resolved.provider_name == "fireworks"


class TestProviderHint:
    """Tests for models with provider_hint."""

    @patch.dict(os.environ, {"DEEPINFRA_API_KEY": "di-key"})
    def test_gpt_oss_routes_to_deepinfra(self):
        """gpt-oss models always route to DeepInfra (provider_hint)."""
        resolved = ModelRegistry.resolve("gpt-oss-120b")
        assert resolved.provider_name == "deepinfra"
        assert "gpt-oss" in resolved.model_id

    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "fw-key"})
    def test_kimi_routes_to_fireworks_with_pricing(self):
        """Kimi K2.6 resolves to Fireworks with pricing metadata."""
        resolved = ModelRegistry.resolve("kimi-2.6")
        assert resolved.provider_name == "fireworks"
        assert resolved.model_id == "accounts/fireworks/models/kimi-k2p6"
        assert resolved.base_url == "https://api.fireworks.ai/inference/v1"
        assert resolved.input_cost_per_million == 0.95
        assert resolved.cached_input_cost_per_million == 0.16
        assert resolved.output_cost_per_million == 4.00
        assert resolved.reasoning_request_param is None

    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "fw-key"})
    def test_glm5_fireworks_routes_with_pricing(self):
        """Fireworks GLM-5 alias resolves to the current GLM-5.1 model card metadata."""
        resolved = ModelRegistry.resolve("fireworks-glm-5")
        assert resolved.provider_name == "fireworks"
        assert resolved.model_id == "accounts/fireworks/models/glm-5p1"
        assert resolved.base_url == "https://api.fireworks.ai/inference/v1"
        assert resolved.context_window == 202752
        assert resolved.input_cost_per_million == 1.40
        assert resolved.cached_input_cost_per_million == 0.26
        assert resolved.output_cost_per_million == 4.40
        assert resolved.reasoning_request_param is None

    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "fw-key"})
    def test_qwen36plus_fireworks_routes_with_vision_and_pricing(self):
        """Fireworks Qwen3.6 Plus resolves with model-card vision and pricing metadata."""
        resolved = ModelRegistry.resolve("qwen3.6plus")
        assert resolved.provider_name == "fireworks"
        assert resolved.model_id == "accounts/fireworks/models/qwen3p6-plus"
        assert resolved.base_url == "https://api.fireworks.ai/inference/v1"
        assert resolved.context_window == 131072
        assert resolved.max_output_tokens == 16384
        assert resolved.supports_tools is True
        assert resolved.supports_vision is True
        assert resolved.input_cost_per_million == 0.50
        assert resolved.cached_input_cost_per_million == 0.10
        assert resolved.output_cost_per_million == 3.00

    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "fw-key"})
    def test_minimax_m27_fireworks_routes_with_vision_and_pricing(self):
        """Fireworks MiniMax M2.7 resolves with model-card vision and pricing metadata."""
        resolved = ModelRegistry.resolve("minimax-m2.7")
        assert resolved.provider_name == "fireworks"
        assert resolved.model_id == "accounts/fireworks/models/minimax-m2p7"
        assert resolved.base_url == "https://api.fireworks.ai/inference/v1"
        assert resolved.context_window == 196608
        assert resolved.max_output_tokens == 16384
        assert resolved.supports_tools is True
        assert resolved.supports_vision is True
        assert resolved.input_cost_per_million == 0.30
        assert resolved.cached_input_cost_per_million == 0.06
        assert resolved.output_cost_per_million == 1.20

    @patch.dict(os.environ, {"DEEPINFRA_API_KEY": "di-key"})
    def test_non_fireworks_reasoning_models_send_reasoning_param(self):
        """Existing non-Fireworks reasoning models keep their reasoning request field."""
        resolved = ModelRegistry.resolve("gpt-oss-120b")
        assert resolved.reasoning_request_param == "reasoning"


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
               if k not in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY")}
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
        assert "fireworks" in result
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

    @patch.dict(os.environ, {"FIREWORKS_API_KEY": "fw-key"})
    def test_list_models_has_fireworks_pricing(self):
        """Fireworks presets include pricing metadata for cost display."""
        result = ModelRegistry.list_models()
        kimi = next(
            model
            for model in result["fireworks"]["models"]
            if model["model_id"] == "accounts/fireworks/models/kimi-k2p6"
        )
        assert kimi["input_cost_per_million"] == 0.95
        assert kimi["output_cost_per_million"] == 4.00

        glm5 = next(
            model
            for model in result["fireworks"]["models"]
            if model["model_id"] == "accounts/fireworks/models/glm-5p1"
        )
        assert glm5["input_cost_per_million"] == 1.40
        assert glm5["cached_input_cost_per_million"] == 0.26
        assert glm5["output_cost_per_million"] == 4.40

        qwen36 = next(
            model
            for model in result["fireworks"]["models"]
            if model["model_id"] == "accounts/fireworks/models/qwen3p6-plus"
        )
        assert qwen36["supports_vision"] is True
        assert qwen36["input_cost_per_million"] == 0.50
        assert qwen36["cached_input_cost_per_million"] == 0.10
        assert qwen36["output_cost_per_million"] == 3.00

        minimax = next(
            model
            for model in result["fireworks"]["models"]
            if model["model_id"] == "accounts/fireworks/models/minimax-m2p7"
        )
        assert minimax["supports_vision"] is True
        assert minimax["input_cost_per_million"] == 0.30
        assert minimax["cached_input_cost_per_million"] == 0.06
        assert minimax["output_cost_per_million"] == 1.20


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
        assert isinstance(resolved.supports_vision, bool)

    @patch.dict(os.environ, {"DEEPINFRA_API_KEY": "test-key"})
    def test_vision_model_marks_supports_vision(self):
        """Vision presets advertise image input support."""
        resolved = ModelRegistry.resolve("qwen2.5-vl-32b")

        assert resolved.supports_vision is True
        assert resolved.provider_name == "deepinfra"
