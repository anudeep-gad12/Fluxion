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
    display_name: str = ""
    auth_type: str = "api_key"


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
    supports_vision: bool = False
    reasoning_request_param: Optional[str] = None
    reasoning_effort: Optional[str] = None
    provider_hint: Optional[str] = None  # Force specific provider
    input_cost_per_million: Optional[float] = None
    cached_input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    recommended: bool = False
    category: str = "general"


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
    supports_vision: bool = False
    reasoning_request_param: Optional[str] = None
    input_cost_per_million: Optional[float] = None
    cached_input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    recommended: bool = False
    category: str = "general"


# =============================================================================
# Provider Registry
# =============================================================================

PROVIDERS: dict[str, ProviderDef] = {
    "openai": ProviderDef(
        name="openai",
        display_name="OpenAI API",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        endpoint="responses",
    ),
    "chatgpt": ProviderDef(
        name="chatgpt",
        display_name="ChatGPT / Codex",
        base_url="https://chatgpt.com/backend-api",
        api_key_env="",
        endpoint="responses",
        auth_type="oauth",
    ),
    "grok": ProviderDef(
        name="grok",
        display_name="Grok",
        base_url="https://cli-chat-proxy.grok.com/v1",
        api_key_env="",
        endpoint="responses",
        auth_type="oauth",
    ),
    "xai": ProviderDef(
        name="xai",
        display_name="xAI",
        base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        endpoint="responses",
    ),
    "openrouter": ProviderDef(
        name="openrouter",
        display_name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        endpoint="chat_completions",
    ),
    "deepinfra": ProviderDef(
        name="deepinfra",
        display_name="DeepInfra",
        base_url="https://api.deepinfra.com/v1/openai",
        api_key_env="DEEPINFRA_API_KEY",
        endpoint="chat_completions",
    ),
    "fireworks": ProviderDef(
        name="fireworks",
        display_name="Fireworks",
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY",
        endpoint="chat_completions",
    ),
    "local": ProviderDef(
        name="local",
        display_name="Local",
        base_url="http://localhost:8080/v1",
        api_key_env="",  # No key needed
        endpoint="chat_completions",
    ),
}


# =============================================================================
# Model Presets
# =============================================================================

MODEL_PRESETS: list[ModelPreset] = [
    # --- OpenAI API ---
    ModelPreset(
        model_id="gpt-5.5",
        display_name="GPT-5.5",
        provider="openai",
        aliases=["openai-gpt-5.5", "gpt-5.5-api"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=5.00,
        cached_input_cost_per_million=0.50,
        output_cost_per_million=30.00,
        recommended=True,
        category="frontier",
    ),
    ModelPreset(
        model_id="gpt-5.4",
        display_name="GPT-5.4",
        provider="openai",
        aliases=["openai-gpt-5.4", "gpt-5.4-api"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=2.50,
        cached_input_cost_per_million=0.25,
        output_cost_per_million=15.00,
        recommended=True,
        category="reasoning",
    ),
    ModelPreset(
        model_id="gpt-5.4-mini",
        display_name="GPT-5.4 mini",
        provider="openai",
        aliases=["openai-gpt-5.4-mini", "gpt-5.4-mini-api"],
        context_window=270000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=0.75,
        cached_input_cost_per_million=0.075,
        output_cost_per_million=4.50,
        recommended=True,
        category="fast",
    ),
    ModelPreset(
        model_id="gpt-5.2-codex",
        display_name="GPT-5.2 Codex",
        provider="openai",
        aliases=["openai-gpt-5.2-codex", "gpt-5.2-codex-api"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=2.50,
        cached_input_cost_per_million=0.25,
        output_cost_per_million=15.00,
        recommended=True,
        category="coding",
    ),
    ModelPreset(
        model_id="gpt-5.2",
        display_name="GPT-5.2",
        provider="openai",
        aliases=["openai-gpt-5.2", "gpt-5.2-api"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=1.25,
        cached_input_cost_per_million=0.125,
        output_cost_per_million=10.00,
        recommended=True,
        category="reasoning",
    ),
    ModelPreset(
        model_id="gpt-5.1-codex",
        display_name="GPT-5.1 Codex",
        provider="openai",
        aliases=["openai-gpt-5.1-codex", "gpt-5.1-codex-api"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=1.25,
        cached_input_cost_per_million=0.125,
        output_cost_per_million=10.00,
        category="coding",
    ),
    ModelPreset(
        model_id="o4-mini",
        display_name="o4-mini",
        provider="openai",
        aliases=["openai-o4-mini", "o4-mini-api"],
        context_window=200000,
        max_output_tokens=100000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        category="fast",
    ),
    # --- ChatGPT OAuth / subscription ---
    ModelPreset(
        model_id="gpt-5.5",
        display_name="GPT-5.5 (ChatGPT)",
        provider="chatgpt",
        aliases=["chatgpt-gpt-5.5", "chatgpt-latest", "gpt-5.5-chatgpt"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=0.0,
        cached_input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        recommended=True,
        category="frontier",
    ),
    ModelPreset(
        model_id="gpt-5.4",
        display_name="GPT-5.4 (ChatGPT)",
        provider="chatgpt",
        aliases=["chatgpt-gpt-5.4", "gpt-5.4-chatgpt"],
        context_window=400000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=0.0,
        cached_input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        recommended=True,
        category="reasoning",
    ),
    ModelPreset(
        model_id="gpt-5.4-mini",
        display_name="GPT-5.4 mini (ChatGPT)",
        provider="chatgpt",
        aliases=["chatgpt-gpt-5.4-mini", "gpt-5.4-mini-chatgpt"],
        context_window=270000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=0.0,
        cached_input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        recommended=True,
        category="fast",
    ),
    # --- xAI ---
    ModelPreset(
        model_id="grok-4.3",
        display_name="Grok 4.3",
        provider="xai",
        aliases=["xai-grok-4.3", "grok4.3", "grok-4"],
        context_window=1000000,
        max_output_tokens=32768,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_request_param="reasoning",
        reasoning_effort="medium",
        input_cost_per_million=1.25,
        cached_input_cost_per_million=0.20,
        output_cost_per_million=2.50,
        recommended=True,
        category="reasoning",
    ),
    ModelPreset(
        model_id="grok-build-0.1",
        display_name="Grok Build 0.1",
        provider="xai",
        aliases=["xai-grok-build", "grok-build"],
        context_window=256000,
        max_output_tokens=32768,
        supports_reasoning=False,
        input_cost_per_million=1.00,
        cached_input_cost_per_million=0.20,
        output_cost_per_million=2.00,
        recommended=True,
        category="coding",
    ),
    # --- Grok OAuth / subscription ---
    ModelPreset(
        model_id="grok-build",
        display_name="Grok Build",
        provider="grok",
        aliases=["grok-oauth-build", "grok-build-oauth"],
        context_window=256000,
        max_output_tokens=32768,
        supports_reasoning=False,
        input_cost_per_million=0.0,
        cached_input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        recommended=True,
        category="coding",
    ),
    ModelPreset(
        model_id="grok-composer-2.5-fast",
        display_name="Composer 2.5",
        provider="grok",
        aliases=["composer-2.5", "composer-2.5-fast", "grok-composer-2.5"],
        context_window=256000,
        max_output_tokens=32768,
        supports_reasoning=False,
        input_cost_per_million=0.0,
        cached_input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        recommended=True,
        category="coding",
    ),
    # --- OpenRouter current popular / cheap ---
    ModelPreset(
        model_id="openrouter/owl-alpha",
        display_name="Owl Alpha (free)",
        provider="openrouter",
        aliases=["owl-alpha", "openrouter-free"],
        context_window=1048756,
        max_output_tokens=262144,
        supports_reasoning=False,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        recommended=True,
        category="free",
    ),
    ModelPreset(
        model_id="qwen/qwen3.7-max",
        display_name="Qwen3.7 Max",
        provider="openrouter",
        aliases=["qwen3.7-max", "qwen-max"],
        context_window=1000000,
        max_output_tokens=65536,
        supports_reasoning=True,
        input_cost_per_million=1.25,
        cached_input_cost_per_million=0.25,
        output_cost_per_million=3.75,
        recommended=True,
        category="coding",
    ),
    ModelPreset(
        model_id="google/gemini-3.5-flash",
        display_name="Gemini 3.5 Flash",
        provider="openrouter",
        aliases=["gemini-3.5-flash", "gemini35-flash"],
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=1.50,
        cached_input_cost_per_million=0.15,
        output_cost_per_million=9.00,
        recommended=True,
        category="balanced",
    ),
    ModelPreset(
        model_id="google/gemini-3.1-flash-lite",
        display_name="Gemini 3.1 Flash Lite",
        provider="openrouter",
        aliases=["gemini-3.1-flash-lite", "gemini-lite"],
        context_window=1048576,
        max_output_tokens=65536,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=0.25,
        cached_input_cost_per_million=0.025,
        output_cost_per_million=1.50,
        recommended=True,
        category="cheap",
    ),
    ModelPreset(
        model_id="x-ai/grok-4.3",
        display_name="Grok 4.3",
        provider="openrouter",
        aliases=["openrouter-grok-4.3", "or-grok-4.3"],
        context_window=1000000,
        max_output_tokens=32768,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=1.25,
        cached_input_cost_per_million=0.20,
        output_cost_per_million=2.50,
        recommended=True,
        category="reasoning",
    ),
    ModelPreset(
        model_id="x-ai/grok-build-0.1",
        display_name="Grok Build 0.1",
        provider="openrouter",
        aliases=["openrouter-grok-build", "or-grok-build"],
        context_window=256000,
        max_output_tokens=32768,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=1.00,
        cached_input_cost_per_million=0.20,
        output_cost_per_million=2.00,
        recommended=True,
        category="coding",
    ),
    ModelPreset(
        model_id="inclusionai/ring-2.6-1t",
        display_name="Ring 2.6 1T",
        provider="openrouter",
        aliases=["ring-2.6", "ring-1t"],
        context_window=262144,
        max_output_tokens=65536,
        supports_reasoning=True,
        input_cost_per_million=0.075,
        cached_input_cost_per_million=0.015,
        output_cost_per_million=0.625,
        recommended=True,
        category="cheap",
    ),
    ModelPreset(
        model_id="stepfun/step-3.7-flash",
        display_name="Step 3.7 Flash",
        provider="openrouter",
        aliases=["step-3.7-flash", "stepfun-flash"],
        context_window=256000,
        max_output_tokens=256000,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=0.20,
        cached_input_cost_per_million=0.04,
        output_cost_per_million=1.15,
        category="cheap",
    ),
    ModelPreset(
        model_id="mistralai/mistral-medium-3-5",
        display_name="Mistral Medium 3.5",
        provider="openrouter",
        aliases=["mistral-medium-3.5", "mistral-medium"],
        context_window=262144,
        max_output_tokens=32768,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=1.50,
        output_cost_per_million=7.50,
        category="balanced",
    ),
    ModelPreset(
        model_id="anthropic/claude-opus-4.8",
        display_name="Claude Opus 4.8",
        provider="openrouter",
        aliases=["claude-opus-4.8", "opus-4.8"],
        context_window=1000000,
        max_output_tokens=128000,
        supports_reasoning=True,
        supports_vision=True,
        input_cost_per_million=5.00,
        cached_input_cost_per_million=0.50,
        output_cost_per_million=25.00,
        category="frontier",
    ),
    # --- Qwen ---
    ModelPreset(
        model_id="qwen/qwen3-72b",
        display_name="Qwen 3 72B",
        provider="openrouter",
        aliases=["qwen3-72b", "qwen3"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_request_param=None,
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
        reasoning_request_param=None,
        reasoning_effort="medium",
        input_cost_per_million=0.18,
        output_cost_per_million=0.60,
    ),
    ModelPreset(
        model_id="qwen/qwen3-32b",
        display_name="Qwen 3 32B",
        provider="openrouter",
        aliases=["qwen3-32b"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_request_param="reasoning",
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
        reasoning_request_param="reasoning",
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
        input_cost_per_million=0.55,
        cached_input_cost_per_million=0.14,
        output_cost_per_million=2.19,
    ),
    ModelPreset(
        model_id="deepseek/deepseek-v3-0324",
        display_name="DeepSeek V3",
        provider="openrouter",
        aliases=["deepseek-v3", "v3"],
        context_window=131072,
        max_output_tokens=16384,
        input_cost_per_million=0.27,
        cached_input_cost_per_million=0.07,
        output_cost_per_million=1.10,
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
        input_cost_per_million=0.55,
        cached_input_cost_per_million=0.14,
        output_cost_per_million=2.19,
    ),
    # --- Llama ---
    ModelPreset(
        model_id="meta-llama/llama-4-maverick",
        display_name="Llama 4 Maverick",
        provider="openrouter",
        aliases=["llama4-maverick", "maverick"],
        context_window=1048576,
        max_output_tokens=16384,
        supports_vision=True,
    ),
    ModelPreset(
        model_id="meta-llama/llama-4-scout",
        display_name="Llama 4 Scout",
        provider="openrouter",
        aliases=["llama4-scout", "scout"],
        context_window=524288,
        max_output_tokens=16384,
        supports_vision=True,
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
        supports_vision=True,
        reasoning_request_param=None,
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
        supports_vision=True,
        reasoning_effort="low",
    ),
    # --- DeepInfra vision/OCR ---
    ModelPreset(
        model_id="Qwen/Qwen2.5-VL-32B-Instruct",
        display_name="Qwen 2.5 VL 32B (DeepInfra)",
        provider="deepinfra",
        aliases=["deepinfra-qwen2.5-vl-32b", "qwen2.5-vl-32b", "qwen-vl-32b"],
        context_window=131072,
        max_output_tokens=8192,
        supports_vision=True,
        provider_hint="deepinfra",
    ),
    ModelPreset(
        model_id="Qwen/Qwen2.5-VL-7B-Instruct",
        display_name="Qwen 2.5 VL 7B (DeepInfra)",
        provider="deepinfra",
        aliases=["deepinfra-qwen2.5-vl-7b", "qwen2.5-vl-7b", "qwen-vl-7b"],
        context_window=32768,
        max_output_tokens=8192,
        supports_vision=True,
        provider_hint="deepinfra",
    ),
    # --- DeepInfra-specific ---
    ModelPreset(
        model_id="zai-org/GLM-5.1",
        display_name="GLM-5.1",
        provider="deepinfra",
        aliases=["glm-5.1", "glm5.1", "deepinfra-glm-5.1"],
        context_window=202752,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_request_param=None,
        reasoning_effort="medium",
        provider_hint="deepinfra",
        input_cost_per_million=1.05,
        cached_input_cost_per_million=0.205,
        output_cost_per_million=3.50,
        recommended=True,
        category="coding",
    ),
    ModelPreset(
        model_id="Qwen/Qwen3.6-35B-A3B",
        display_name="Qwen3.6 35B A3B",
        provider="deepinfra",
        aliases=["deepinfra-qwen3.6-35b", "qwen3.6-35b"],
        context_window=256000,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="deepinfra",
        input_cost_per_million=0.15,
        output_cost_per_million=0.95,
        recommended=True,
        category="cheap",
    ),
    ModelPreset(
        model_id="stepfun-ai/Step-3.5-Flash",
        display_name="Step 3.5 Flash",
        provider="deepinfra",
        aliases=["deepinfra-step-3.5-flash", "step-3.5-flash"],
        context_window=256000,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="deepinfra",
        input_cost_per_million=0.09,
        cached_input_cost_per_million=0.02,
        output_cost_per_million=0.30,
        category="cheap",
    ),
    ModelPreset(
        model_id="deepseek-ai/DeepSeek-V3.1-Terminus",
        display_name="DeepSeek V3.1 Terminus",
        provider="deepinfra",
        aliases=["deepinfra-deepseek-v3.1-terminus", "deepseek-v3.1-terminus"],
        context_window=163840,
        max_output_tokens=16384,
        provider_hint="deepinfra",
        input_cost_per_million=0.27,
        output_cost_per_million=0.85,
        category="cheap",
    ),
    ModelPreset(
        model_id="zai-org/GLM-5",
        display_name="GLM-5",
        provider="deepinfra",
        aliases=["glm-5", "glm5"],
        context_window=202752,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_request_param=None,
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
        input_cost_per_million=0.09,
        output_cost_per_million=0.45,
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
        input_cost_per_million=0.55,
        output_cost_per_million=2.19,
    ),
    # --- Fireworks-specific ---
    ModelPreset(
        model_id="accounts/fireworks/models/deepseek-v4-pro",
        display_name="DeepSeek V4 Pro (Fireworks)",
        provider="fireworks",
        aliases=["fireworks-deepseek-v4-pro", "fw-deepseek-v4-pro", "deepseek-v4-pro"],
        context_window=163840,
        max_output_tokens=32768,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=1.74,
        cached_input_cost_per_million=0.145,
        output_cost_per_million=3.48,
        recommended=True,
        category="reasoning",
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/deepseek-v4-flash",
        display_name="DeepSeek V4 Flash (Fireworks)",
        provider="fireworks",
        aliases=["fireworks-deepseek-v4-flash", "fw-deepseek-v4-flash", "deepseek-v4-flash"],
        context_window=163840,
        max_output_tokens=32768,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.14,
        cached_input_cost_per_million=0.028,
        output_cost_per_million=0.28,
        recommended=True,
        category="cheap",
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/kimi-k2p6",
        display_name="Kimi K2.6 (Fireworks)",
        provider="fireworks",
        aliases=[
            "kimi-k2.6",
            "kimi-2.6",
            "kimi-k2p6",
            "fireworks-kimi-k2p6",
            "fw-kimi-k2p6",
        ],
        context_window=262144,
        max_output_tokens=32768,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.95,
        cached_input_cost_per_million=0.16,
        output_cost_per_million=4.00,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/kimi-k2p5",
        display_name="Kimi K2.5 (Fireworks)",
        provider="fireworks",
        aliases=[
            "kimi-k2.5",
            "kimi-2.5",
            "kimi-k2p5",
            "fireworks-kimi-k2p5",
            "fw-kimi-k2p5",
        ],
        context_window=262144,
        max_output_tokens=32768,
        supports_reasoning=True,
        supports_vision=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.60,
        cached_input_cost_per_million=0.10,
        output_cost_per_million=3.00,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/qwen3p6-plus",
        display_name="Qwen3.6 Plus (Fireworks)",
        provider="fireworks",
        aliases=[
            "qwen3.6plus",
            "qwen3.6-plus",
            "qwen3p6-plus",
            "fireworks-qwen3p6-plus",
            "fw-qwen3p6-plus",
        ],
        context_window=131072,
        max_output_tokens=16384,
        supports_vision=True,
        provider_hint="fireworks",
        input_cost_per_million=0.50,
        cached_input_cost_per_million=0.10,
        output_cost_per_million=3.00,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/minimax-m2p7",
        display_name="MiniMax M2.7 (Fireworks)",
        provider="fireworks",
        aliases=[
            "minimax-m2.7",
            "minimax-m2p7",
            "minimax-2.7",
            "fireworks-minimax-m2p7",
            "fw-minimax-m2p7",
        ],
        context_window=196608,
        max_output_tokens=16384,
        supports_vision=True,
        provider_hint="fireworks",
        input_cost_per_million=0.30,
        cached_input_cost_per_million=0.06,
        output_cost_per_million=1.20,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/gpt-oss-120b",
        display_name="GPT-OSS 120B (Fireworks)",
        provider="fireworks",
        aliases=["fireworks-gpt-oss-120b", "fw-gpt-oss-120b"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.15,
        cached_input_cost_per_million=0.01,
        output_cost_per_million=0.60,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/gpt-oss-20b",
        display_name="GPT-OSS 20B (Fireworks)",
        provider="fireworks",
        aliases=["fireworks-gpt-oss-20b", "fw-gpt-oss-20b"],
        context_window=131072,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.07,
        cached_input_cost_per_million=0.04,
        output_cost_per_million=0.30,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/deepseek-v3p1",
        display_name="DeepSeek V3.1 (Fireworks)",
        provider="fireworks",
        aliases=["fireworks-deepseek-v3p1", "fw-deepseek-v3p1"],
        context_window=163840,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.56,
        cached_input_cost_per_million=0.28,
        output_cost_per_million=1.68,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/qwen3-8b",
        display_name="Qwen3 8B (Fireworks)",
        provider="fireworks",
        aliases=["fireworks-qwen3-8b", "fw-qwen3-8b"],
        context_window=41000,
        max_output_tokens=8192,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=0.20,
        cached_input_cost_per_million=0.10,
        output_cost_per_million=0.20,
    ),
    ModelPreset(
        model_id="accounts/fireworks/models/glm-5p1",
        display_name="GLM-5.1 (Fireworks)",
        provider="fireworks",
        aliases=[
            "fireworks-glm-5.1",
            "fw-glm-5.1",
            "glm-5.1-fireworks",
            "fireworks-glm-5",
            "fw-glm-5",
            "glm-5-fireworks",
        ],
        context_window=202752,
        max_output_tokens=16384,
        supports_reasoning=True,
        reasoning_effort="medium",
        provider_hint="fireworks",
        input_cost_per_million=1.40,
        cached_input_cost_per_million=0.26,
        output_cost_per_million=4.40,
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
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
    ),
]

# Build alias index (case-insensitive)
_ALIAS_INDEX: dict[str, ModelPreset] = {}
_MODEL_ID_INDEX: dict[str, ModelPreset] = {}

for _preset in MODEL_PRESETS:
    if (
        _preset.supports_reasoning
        and _preset.provider != "fireworks"
        and _preset.reasoning_request_param is None
    ):
        _preset.reasoning_request_param = "reasoning"
    _MODEL_ID_INDEX.setdefault(_preset.model_id.lower(), _preset)
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

        lookup_key = model_string.lower()
        if explicit_provider:
            preset = next(
                (
                    candidate
                    for candidate in MODEL_PRESETS
                    if candidate.provider == explicit_provider
                    and (
                        candidate.model_id.lower() == lookup_key
                        or lookup_key in {alias.lower() for alias in candidate.aliases}
                    )
                ),
                None,
            )
        else:
            # Try alias lookup (case-insensitive)
            preset = _ALIAS_INDEX.get(lookup_key)

            # Try full model ID lookup
            if not preset:
                preset = _MODEL_ID_INDEX.get(lookup_key)

        if preset:
            # Use explicit provider if specified, otherwise preset's provider
            provider_name = explicit_provider or preset.provider_hint or preset.provider
            provider_def = PROVIDERS[provider_name]

            # Check API key
            api_key = ModelRegistry._get_api_key(provider_def)
            if provider_name == "grok":
                from orchestrator.services.grok_auth import get_grok_access_token_sync

                api_key = get_grok_access_token_sync()
            if not api_key and provider_name not in {"local", "chatgpt"}:
                if provider_name == "grok":
                    raise ValueError("Connect Grok OAuth before selecting this model.")
                if explicit_provider or preset.provider_hint:
                    raise ValueError(
                        f"No API key found for {provider_name}. "
                        f"Set {provider_def.api_key_env} environment variable."
                    )
                # Legacy alias fallback for unqualified model names only. Explicit
                # UI/provider selections must never silently route to another
                # provider because it makes the selected model label lie.
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
                reasoning_request_param=preset.reasoning_request_param,
                supports_tools=preset.supports_tools,
                supports_vision=preset.supports_vision,
                input_cost_per_million=preset.input_cost_per_million,
                cached_input_cost_per_million=preset.cached_input_cost_per_million,
                output_cost_per_million=preset.output_cost_per_million,
                recommended=preset.recommended,
                category=preset.category,
            )

        # Unknown model — use as raw model ID with conservative defaults
        if explicit_provider:
            provider_name = explicit_provider
            if provider_name == "chatgpt":
                raise ValueError(
                    f"Unsupported ChatGPT/Codex model '{model_string}'. "
                    "Use one of the ChatGPT models listed in the picker."
                )
            provider_def = PROVIDERS[provider_name]
            api_key = ModelRegistry._get_api_key(provider_def)
            if provider_name == "grok":
                from orchestrator.services.grok_auth import get_grok_access_token_sync

                api_key = get_grok_access_token_sync()
            if not api_key and provider_name not in {"local", "chatgpt"}:
                if provider_name == "grok":
                    raise ValueError("Connect Grok OAuth before selecting this model.")
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
            reasoning_request_param=None,
            supports_tools=True,
            supports_vision=False,
            input_cost_per_million=0.0 if provider_name == "local" else None,
            output_cost_per_million=0.0 if provider_name == "local" else None,
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
                    "supports_vision": p.supports_vision,
                    "reasoning_request_param": p.reasoning_request_param,
                    "input_cost_per_million": p.input_cost_per_million,
                    "cached_input_cost_per_million": p.cached_input_cost_per_million,
                    "output_cost_per_million": p.output_cost_per_million,
                    "recommended": p.recommended,
                    "category": p.category,
                    "source": "curated",
                }
                for p in MODEL_PRESETS
                if p.provider == provider_name
            ]

            result[provider_name] = {
                "models": presets,
                "available": has_key,
                "api_key_env": provider_def.api_key_env,
                "display_name": provider_def.display_name or provider_def.name,
                "auth_type": provider_def.auth_type,
                "base_url": provider_def.base_url,
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

        # Preserve legacy raw-model fallback order; explicit provider:model is
        # the intended path for OpenAI/xAI because their catalogs are stricter.
        for name in ("openrouter", "deepinfra", "fireworks"):
            pdef = PROVIDERS[name]
            key = ModelRegistry._get_api_key(pdef)
            if key:
                return key, name, pdef

        # Try local as last resort
        local_def = PROVIDERS["local"]
        return None, "local", local_def
