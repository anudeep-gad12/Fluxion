"""Model registry for resolving model strings to provider configurations.

Supports:
- Alias-based lookup (e.g., "qwen3-72b" -> full model preset)
- Explicit provider prefix (e.g., "deepinfra:meta-llama/...")
- Unknown model fallback with auto-provider detection
- API key availability checking
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderDef:
    """Definition of an LLM provider endpoint."""

    name: str  # "openrouter", "deepinfra", "local"
    base_url: str  # "https://openrouter.ai/api/v1"
    api_key_env: str  # "OPENROUTER_API_KEY" (empty for local)
    endpoint: str = "chat_completions"


@dataclass
class ModelPreset:
    """A known model with its configuration and provider."""

    model_id: str  # "qwen/qwen3-72b" (sent to API)
    display_name: str  # "Qwen 3 72B" (shown in picker)
    provider: str  # "openrouter" | "deepinfra" | "local"
    aliases: list[str] = field(default_factory=list)
    context_window: int = 32768
    max_output_tokens: int = 16384
    default_temperature: float = 0.7
    supports_tools: bool = True
    supports_reasoning: bool = False
    reasoning_effort: Optional[str] = None
    provider_hint: Optional[str] = None  # Force specific provider


@dataclass
class ResolvedModel:
    """Fully resolved model configuration ready for provider creation."""

    model_id: str
    display_name: str
    provider_name: str
    base_url: str
    api_key: Optional[str]
    endpoint: str
    context_window: int
    max_output_tokens: int
    temperature: float
    reasoning_effort: Optional[str]
    supports_tools: bool


# =============================================================================
# Provider Registry
# =============================================================================

PROVIDERS: dict[str, ProviderDef] = {
    "openrouter": ProviderDef(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        endpoint="chat_completions",
    ),
    "deepinfra": ProviderDef(
        name="deepinfra",
        base_url="https://api.deepinfra.com/v1/openai",
        api_key_env="DEEPINFRA_API_KEY",
        endpoint="chat_completions",
    ),
    "local": ProviderDef(
        name="local",
        base_url="http://localhost:8080/v1",
        api_key_env="",  # No key needed
        endpoint="chat_completions",
    ),
}


# =============================================================================
# Model Presets
# =============================================================================

MODEL_PRESETS: list[ModelPreset] = [
    # --- Qwen ---
    ModelPreset(
        model_id="qwen/qwen3-72b",
        display_name="Qwen 3 72B",
        provider="openrouter",
        aliases=["qwen3-72b", "qwen3"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
    ),
    ModelPreset(
        model_id="qwen/qwen3-235b-a22b",
        display_name="Qwen 3 235B (MoE)",
        provider="openrouter",
        aliases=["qwen3-235b", "qwen3-moe"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
    ),
    ModelPreset(
        model_id="qwen/qwen3-32b",
        display_name="Qwen 3 32B",
        provider="openrouter",
        aliases=["qwen3-32b"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
    ),
    ModelPreset(
        model_id="qwen/qwen3-30b-a3b",
        display_name="Qwen 3 30B (MoE)",
        provider="openrouter",
        aliases=["qwen3-30b"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
    ),
    ModelPreset(
        model_id="qwen/qwen2.5-72b-instruct",
        display_name="Qwen 2.5 72B",
        provider="openrouter",
        aliases=["qwen2.5-72b"],
        context_window=131072,
        max_output_tokens=8192,
    ),
    # --- DeepSeek ---
    ModelPreset(
        model_id="deepseek/deepseek-r1",
        display_name="DeepSeek R1",
        provider="openrouter",
        aliases=["deepseek-r1", "r1"],
        context_window=163840,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="high",
    ),
    ModelPreset(
        model_id="deepseek/deepseek-v3-0324",
        display_name="DeepSeek V3",
        provider="openrouter",
        aliases=["deepseek-v3", "v3"],
        context_window=131072,
        max_output_tokens=16384,
    ),
    ModelPreset(
        model_id="deepseek/deepseek-r1-0528",
        display_name="DeepSeek R1 0528",
        provider="openrouter",
        aliases=["deepseek-r1-0528", "r1-0528"],
        context_window=163840,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="high",
    ),
    # --- Llama ---
    ModelPreset(
        model_id="meta-llama/llama-4-maverick",
        display_name="Llama 4 Maverick",
        provider="openrouter",
        aliases=["llama4-maverick", "maverick"],
        context_window=1048576,
        max_output_tokens=16384,
    ),
    ModelPreset(
        model_id="meta-llama/llama-4-scout",
        display_name="Llama 4 Scout",
        provider="openrouter",
        aliases=["llama4-scout", "scout"],
        context_window=524288,
        max_output_tokens=16384,
    ),
    ModelPreset(
        model_id="meta-llama/llama-3.3-70b-instruct",
        display_name="Llama 3.3 70B",
        provider="openrouter",
        aliases=["llama3.3-70b", "llama-3.3"],
        context_window=131072,
        max_output_tokens=8192,
    ),
    ModelPreset(
        model_id="meta-llama/llama-3.1-70b-instruct",
        display_name="Llama 3.1 70B",
        provider="openrouter",
        aliases=["llama3.1-70b"],
        context_window=131072,
        max_output_tokens=8192,
    ),
    ModelPreset(
        model_id="meta-llama/llama-3.1-8b-instruct",
        display_name="Llama 3.1 8B",
        provider="openrouter",
        aliases=["llama3.1-8b"],
        context_window=131072,
        max_output_tokens=8192,
    ),
    # --- Mistral ---
    ModelPreset(
        model_id="mistralai/mistral-large-2411",
        display_name="Mistral Large",
        provider="openrouter",
        aliases=["mistral-large"],
        context_window=131072,
        max_output_tokens=8192,
    ),
    ModelPreset(
        model_id="mistralai/codestral-2501",
        display_name="Codestral",
        provider="openrouter",
        aliases=["codestral"],
        context_window=262144,
        max_output_tokens=16384,
    ),
    # --- Google ---
    ModelPreset(
        model_id="google/gemini-2.5-pro-preview",
        display_name="Gemini 2.5 Pro",
        provider="openrouter",
        aliases=["gemini-2.5-pro", "gemini-pro"],
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=True,
        reasoning_effort="medium",
    ),
    ModelPreset(
        model_id="google/gemini-2.5-flash-preview",
        display_name="Gemini 2.5 Flash",
        provider="openrouter",
        aliases=["gemini-2.5-flash", "gemini-flash"],
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=True,
        reasoning_effort="low",
    ),
    # --- DeepInfra-specific ---
    ModelPreset(
        model_id="zai-org/GLM-5",
        display_name="GLM-5",
        provider="deepinfra",
        aliases=["glm-5", "glm5"],
        context_window=202752,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="deepinfra",
    ),
    ModelPreset(
        model_id="openai/gpt-oss-120b",
        display_name="GPT-OSS 120B",
        provider="deepinfra",
        aliases=["gpt-oss-120b", "gpt-oss"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="deepinfra",
    ),
    ModelPreset(
        model_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
        display_name="Llama 3.1 70B (DeepInfra)",
        provider="deepinfra",
        aliases=["deepinfra-llama3.1-70b"],
        context_window=131072,
        max_output_tokens=8192,
        provider_hint="deepinfra",
    ),
    ModelPreset(
        model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
        display_name="Llama 3.1 8B (DeepInfra)",
        provider="deepinfra",
        aliases=["deepinfra-llama3.1-8b"],
        context_window=131072,
        max_output_tokens=8192,
        provider_hint="deepinfra",
    ),
    ModelPreset(
        model_id="Qwen/Qwen2.5-72B-Instruct",
        display_name="Qwen 2.5 72B (DeepInfra)",
        provider="deepinfra",
        aliases=["deepinfra-qwen2.5-72b"],
        context_window=131072,
        max_output_tokens=8192,
        provider_hint="deepinfra",
    ),
    ModelPreset(
        model_id="deepseek-ai/DeepSeek-R1",
        display_name="DeepSeek R1 (DeepInfra)",
        provider="deepinfra",
        aliases=["deepinfra-deepseek-r1"],
        context_window=163840,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="high",
        provider_hint="deepinfra",
    ),
    # --- Local models (common GGUF patterns) ---
    ModelPreset(
        model_id="local-model",
        display_name="Local Model",
        provider="local",
        aliases=["local"],
        context_window=32768,
        max_output_tokens=4096,
        default_temperature=0.7,
        supports_tools=True,
    ),
]

# Build alias index (case-insensitive)
_ALIAS_INDEX: dict[str, ModelPreset] = {}
_MODEL_ID_INDEX: dict[str, ModelPreset] = {}

for _preset in MODEL_PRESETS:
    _MODEL_ID_INDEX[_preset.model_id.lower()] = _preset
    for _alias in _preset.aliases:
        _ALIAS_INDEX[_alias.lower()] = _preset


# =============================================================================
# Model Registry
# =============================================================================


class ModelRegistry:
    """Registry for resolving model strings to fully configured providers."""

    @staticmethod
    def resolve(model_string: str) -> ResolvedModel:
        """Resolve a model string to a full provider configuration.

        Supports:
        - Aliases: "qwen3-72b" -> Qwen 3 72B on OpenRouter
        - Full model IDs: "qwen/qwen3-72b" -> direct lookup
        - Provider prefix: "deepinfra:meta-llama/..." -> force provider
        - Unknown models: conservative defaults, auto-detect provider

        Args:
            model_string: Model name, alias, or "provider:model" string.

        Returns:
            ResolvedModel with everything needed to create a provider.

        Raises:
            ValueError: If no API key is available for the target provider.
        """
        model_string = model_string.strip()

        # Check for explicit provider prefix: "deepinfra:model-id"
        explicit_provider = None
        if ":" in model_string and not model_string.startswith("http"):
            parts = model_string.split(":", 1)
            if parts[0].lower() in PROVIDERS:
                explicit_provider = parts[0].lower()
                model_string = parts[1]

        # Try alias lookup (case-insensitive)
        preset = _ALIAS_INDEX.get(model_string.lower())

        # Try full model ID lookup
        if not preset:
            preset = _MODEL_ID_INDEX.get(model_string.lower())

        if preset:
            # Use explicit provider if specified, otherwise preset's provider
            provider_name = explicit_provider or preset.provider_hint or preset.provider
            provider_def = PROVIDERS[provider_name]

            # Check API key
            api_key = ModelRegistry._get_api_key(provider_def)
            if not api_key and provider_name != "local":
                # Try to fall back to another provider that has a key
                api_key, provider_name, provider_def = ModelRegistry._find_available_provider(
                    prefer=provider_name
                )

            return ResolvedModel(
                model_id=preset.model_id,
                display_name=preset.display_name,
                provider_name=provider_name,
                base_url=provider_def.base_url,
                api_key=api_key,
                endpoint=provider_def.endpoint,
                context_window=preset.context_window,
                max_output_tokens=preset.max_output_tokens,
                temperature=preset.default_temperature,
                reasoning_effort=preset.reasoning_effort,
                supports_tools=preset.supports_tools,
            )

        # Unknown model — use as raw model ID with conservative defaults
        if explicit_provider:
            provider_name = explicit_provider
            provider_def = PROVIDERS[provider_name]
            api_key = ModelRegistry._get_api_key(provider_def)
            if not api_key and provider_name != "local":
                raise ValueError(
                    f"No API key found for {provider_name}. "
                    f"Set {provider_def.api_key_env} environment variable."
                )
        else:
            # Auto-detect: find a provider with an available API key
            api_key, provider_name, provider_def = ModelRegistry._find_available_provider()

        return ResolvedModel(
            model_id=model_string,
            display_name=model_string,
            provider_name=provider_name,
            base_url=provider_def.base_url,
            api_key=api_key,
            endpoint=provider_def.endpoint,
            context_window=32768,
            max_output_tokens=8192,
            temperature=0.7,
            reasoning_effort=None,
            supports_tools=True,
        )

    @staticmethod
    def list_models() -> dict[str, list[dict]]:
        """List all model presets grouped by provider with availability info.

        Returns:
            Dict with provider names as keys, each containing:
            - "models": list of model preset dicts
            - "available": bool (API key present)
            - "api_key_env": env var name for the API key
        """
        result: dict[str, list[dict]] = {}

        for provider_name, provider_def in PROVIDERS.items():
            has_key = bool(ModelRegistry._get_api_key(provider_def)) or provider_name == "local"
            presets = [
                {
                    "model_id": p.model_id,
                    "display_name": p.display_name,
                    "aliases": p.aliases,
                    "context_window": p.context_window,
                    "max_output_tokens": p.max_output_tokens,
                    "supports_tools": p.supports_tools,
                    "supports_reasoning": p.supports_reasoning,
                }
                for p in MODEL_PRESETS
                if p.provider == provider_name
            ]

            result[provider_name] = {
                "models": presets,
                "available": has_key,
                "api_key_env": provider_def.api_key_env,
            }

        return result

    @staticmethod
    def _get_api_key(provider_def: ProviderDef) -> Optional[str]:
        """Get API key from environment for a provider."""
        if not provider_def.api_key_env:
            return None
        return os.environ.get(provider_def.api_key_env)

    @staticmethod
    def _find_available_provider(
        prefer: Optional[str] = None,
    ) -> tuple[Optional[str], str, ProviderDef]:
        """Find a provider with an available API key.

        Args:
            prefer: Preferred provider name (tried first).

        Returns:
            Tuple of (api_key, provider_name, provider_def).

        Raises:
            ValueError: If no provider has an API key set.
        """
        # Try preferred provider first
        if prefer and prefer in PROVIDERS:
            pdef = PROVIDERS[prefer]
            key = ModelRegistry._get_api_key(pdef)
            if key:
                return key, prefer, pdef

        # Try OpenRouter first (larger catalog), then DeepInfra
        for name in ("openrouter", "deepinfra"):
            pdef = PROVIDERS[name]
            key = ModelRegistry._get_api_key(pdef)
            if key:
                return key, name, pdef

        # Try local as last resort
        local_def = PROVIDERS["local"]
        return None, "local", local_def
