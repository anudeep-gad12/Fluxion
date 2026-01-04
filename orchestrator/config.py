"""Configuration for the chat orchestrator.

This module is the single source of truth for all chat settings.
Configuration is loaded from chat_config.yaml with environment variable support.

Environment variable syntax:
    ${VAR}              - Required, errors if not set
    ${VAR:-default}     - Optional with default value
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator


# =============================================================================
# Base Paths
# =============================================================================

BASE_DIR = Path(__file__).parent.parent
VAR_DIR = BASE_DIR / "var"
DB_PATH = VAR_DIR / "traces.sqlite"
CHAT_CONFIG_PATH = Path(__file__).parent / "chat_config.yaml"

# Ensure directories exist
VAR_DIR.mkdir(exist_ok=True)


# =============================================================================
# Environment Variable Resolution
# =============================================================================


def resolve_env_vars(value: Any) -> Any:
    """Resolve ${VAR} and ${VAR:-default} patterns recursively.

    This runs BEFORE Pydantic validation.
    Unresolved ${VAR} without default raises error.

    Args:
        value: The value to resolve (can be str, dict, list, or primitive).

    Returns:
        The value with all environment variables resolved.

    Raises:
        ValueError: If an environment variable is not set and has no default.
    """
    if isinstance(value, str):
        pattern = r"\$\{([^}:-]+)(?::-([^}]*))?\}"

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)  # None if no default specified
            env_value = os.environ.get(var_name)

            if env_value is not None:
                return env_value
            if default is not None:
                return default

            # No env var and no default - raise error
            raise ValueError(
                f"Environment variable {var_name} not set and no default provided"
            )

        return re.sub(pattern, replacer, value)

    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [resolve_env_vars(v) for v in value]

    return value


# =============================================================================
# Provider Configuration
# =============================================================================


class ProviderConfig(BaseModel):
    """LLM provider configuration.

    All providers are OpenAI-compatible - no type branching needed.
    Just configure base_url, api_key, and endpoint selection.
    """

    # Connection
    base_url: str = "http://127.0.0.1:1234"
    api_key: Optional[str] = None

    # Endpoint selection
    endpoint: Literal["responses", "chat_completions", "auto"] = "responses"
    fallback_on_404: bool = True

    # Tool fallback policy
    # If True (default), raises ToolFallbackError when tools are requested but
    # /v1/responses is unavailable. gpt-oss models ALWAYS require /v1/responses
    # for tools regardless of this setting.
    fail_on_tool_fallback: bool = True

    # Stateful mode for conversation chaining
    # - "stateless" (default): Always send full message history
    # - "stateful_opt_in": Use previous_response_id when available for efficiency
    state_mode: Literal["stateless", "stateful_opt_in"] = "stateless"

    # Reliability - exponential backoff with jitter
    timeout: float = 120.0
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    retryable_statuses: List[int] = [429, 500, 502, 503, 504]

    # Extra headers (e.g., api-version for Azure)
    extra_headers: Dict[str, str] = {}

    @field_validator("api_key", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Optional[str]:
        """Convert empty string to None for api_key."""
        if v == "" or v is None:
            return None
        return v


# =============================================================================
# Provider Chain Configuration
# =============================================================================


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for provider resilience.

    The circuit breaker prevents cascading failures by fast-failing
    requests to unhealthy providers.
    """

    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout_seconds: float = 30.0  # Seconds before trying half-open
    success_threshold: int = 2  # Successes in half-open before closing


class ChainedProviderConfig(BaseModel):
    """Configuration for a single provider in a chain.

    Attributes:
        name: Identifier for logging (e.g., "deepinfra", "together_ai")
        provider: The provider configuration
        priority: Lower number = higher priority (tried first)
        circuit_breaker: Optional circuit breaker config (uses default if None)
    """

    name: str
    provider: ProviderConfig
    priority: int = 0
    circuit_breaker: Optional[CircuitBreakerConfig] = None


class ProviderChainConfig(BaseModel):
    """Configuration for provider chain with failover.

    When enabled, requests are routed through multiple providers
    with automatic failover on failure.

    Example:
        provider_chain:
          enabled: true
          providers:
            - name: deepinfra
              priority: 0
              provider:
                base_url: "https://api.deepinfra.com/v1/openai"
                api_key: ${DEEPINFRA_API_KEY:-}
            - name: together_ai
              priority: 1
              provider:
                base_url: "https://api.together.xyz/v1"
                api_key: ${TOGETHER_API_KEY:-}
    """

    enabled: bool = False  # If False, use single provider mode
    providers: List[ChainedProviderConfig] = []
    default_circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()


# =============================================================================
# Chat Configuration Classes
# =============================================================================


class ChatModelConfig(BaseModel):
    """Model generation parameters."""

    name: str = "openai/gpt-oss-20b"
    temperature: float = 0.7
    max_tokens: int = 4096
    seed: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    # Native reasoning effort for gpt-oss models (low, medium, high)
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = None


class ChatContextConfig(BaseModel):
    """Context window management settings."""

    max_messages: int = 50
    max_tokens: int = 6000
    reserve_for_response: int = 2048
    truncation_strategy: Literal["sliding_window", "oldest_first"] = "sliding_window"


class ChatTracingConfig(BaseModel):
    """Tracing settings."""

    enabled: bool = True
    log_level: Literal["debug", "info", "warn"] = "info"
    log_model_calls: bool = True


# =============================================================================
# Thinking Configuration Classes
# =============================================================================


class ThinkingTracingConfig(BaseModel):
    """Thinking tracing settings."""

    save_internal: bool = True
    save_user_summary: bool = True


class ThinkingUIConfig(BaseModel):
    """Thinking UI display settings."""

    show_thinking: bool = False
    collapsible: bool = True


class ThinkingConfig(BaseModel):
    """Complete thinking/reasoning configuration."""

    mode_mapping: Dict[str, str] = {"default": "direct", "thinking": "direct"}
    tracing: ThinkingTracingConfig = ThinkingTracingConfig()
    ui: ThinkingUIConfig = ThinkingUIConfig()


# =============================================================================
# Main Chat Configuration
# =============================================================================


class ChatConfig(BaseModel):
    """Complete chat configuration loaded from chat_config.yaml.

    This is the single source of truth for all chat runtime settings.
    """

    provider: ProviderConfig = ProviderConfig()
    provider_chain: Optional[ProviderChainConfig] = None  # Optional chain with failover
    model: ChatModelConfig = ChatModelConfig()
    context: ChatContextConfig = ChatContextConfig()
    system_prompt: str = "You are a helpful AI assistant. Answer directly and clearly."
    tracing: ChatTracingConfig = ChatTracingConfig()
    thinking: ThinkingConfig = ThinkingConfig()

    # Backward compatibility alias
    @property
    def endpoint(self) -> str:
        """Backward compatibility alias for provider.base_url."""
        return self.provider.base_url

    def get_snapshot(self) -> dict:
        """Get a snapshot of config for tracing/reproducibility."""
        import hashlib

        prompt_hash = hashlib.md5(self.system_prompt.encode()).hexdigest()[:8]
        snapshot = {
            "provider": self.provider.model_dump(),
            "model": self.model.model_dump(),
            "context": self.context.model_dump(),
            "system_prompt_hash": prompt_hash,
            "tracing": self.tracing.model_dump(),
            "thinking": self.thinking.model_dump(),
        }
        if self.provider_chain:
            snapshot["provider_chain"] = self.provider_chain.model_dump()
        return snapshot


# =============================================================================
# Config Loading
# =============================================================================

_chat_config: Optional[ChatConfig] = None


def get_chat_config(reload: bool = False) -> ChatConfig:
    """Load chat config from YAML file with environment variable resolution.

    Args:
        reload: If True, reload from file even if cached.

    Returns:
        ChatConfig instance.
    """
    global _chat_config

    if _chat_config is not None and not reload:
        return _chat_config

    if CHAT_CONFIG_PATH.exists():
        import yaml

        with open(CHAT_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}

        # Resolve environment variables BEFORE Pydantic validation
        data = resolve_env_vars(data)

        _chat_config = ChatConfig(**data)
    else:
        # Use defaults if file doesn't exist
        _chat_config = ChatConfig()

    return _chat_config
