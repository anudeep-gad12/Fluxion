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
CHAT_CONFIG_PATH = Path(__file__).parent / "chat_config.yaml"

# Database path - configurable for Railway volumes or other persistent storage
# Default: var/traces.sqlite (relative to project root)
DB_PATH_STR = os.environ.get("DATABASE_PATH", str(BASE_DIR / "var" / "traces.sqlite"))
DB_PATH = Path(DB_PATH_STR)

# Ensure database directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# VAR_DIR for backward compatibility (local dev)
VAR_DIR = BASE_DIR / "var"
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
    slow_response_threshold: float = 15.0  # Seconds before showing "taking longer" message
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
# Tool Configuration
# =============================================================================


class ParallelSearchConfig(BaseModel):
    """Parallel.ai search settings."""

    max_results: int = 10
    timeout_ms: int = 15000


class ParallelExtractConfig(BaseModel):
    """Parallel.ai extract settings."""

    timeout_ms: int = 30000
    max_urls_per_request: int = 5


class ParallelConfig(BaseModel):
    """Parallel.ai API configuration for web search and extraction."""

    base_url: str = "https://api.parallel.ai/v1beta"
    api_key: Optional[str] = None
    search: ParallelSearchConfig = ParallelSearchConfig()
    extract: ParallelExtractConfig = ParallelExtractConfig()

    @field_validator("api_key", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Optional[str]:
        """Convert empty string to None for api_key."""
        if v == "" or v is None:
            return None
        return v


class E2BConfig(BaseModel):
    """E2B sandbox settings for Python code execution."""

    api_key: Optional[str] = None
    template: str = "code-interpreter"  # Must use code-interpreter for port 49999
    timeout_seconds: int = 30
    cleanup_on_startup: bool = True
    stale_session_minutes: int = 10
    metadata: Dict[str, str] = {"app": "reasoner"}

    @field_validator("api_key", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Optional[str]:
        """Convert empty string to None for api_key."""
        if v == "" or v is None:
            return None
        return v


class SandboxConfig(BaseModel):
    """Sandbox configuration."""

    provider: Literal["e2b"] = "e2b"
    e2b: E2BConfig = E2BConfig()


# =============================================================================
# Chat Configuration Classes
# =============================================================================


class ChatGPTConfig(BaseModel):
    """ChatGPT OAuth integration configuration.

    Allows users with ChatGPT Plus/Pro subscriptions to use OpenAI models
    through the Codex backend API at no extra API cost.
    """

    enabled: bool = True
    client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    auth_url: str = "https://auth.openai.com/oauth/authorize"
    token_url: str = "https://auth.openai.com/oauth/token"
    backend_url: str = "https://chatgpt.com/backend-api"
    callback_path: str = "/auth/callback"
    default_model: str = "gpt-5.2-codex"
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    available_models: List[Dict[str, str]] = [
        {"id": "gpt-5.2-codex", "label": "GPT-5.2 Codex"},
        {"id": "o4-mini", "label": "o4-mini"},
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "o3", "label": "o3"},
    ]


class ChatModelConfig(BaseModel):
    """Model generation parameters."""

    name: str = "openai/gpt-oss-120b"
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


class QueryClassificationConfig(BaseModel):
    """Query classification settings for tool selection."""

    enabled: bool = True  # If False, skip classification and let model decide
    min_confidence_for_enforcement: int = 2


class PythonConfig(BaseModel):
    """Python execution settings."""

    timeout_seconds: int = 30


# =============================================================================
# Demo Mode Configuration
# =============================================================================


class RateLimitConfig(BaseModel):
    """Rate limiting settings for demo mode."""

    max_agent_runs_per_hour: int = 10
    max_chat_runs_per_hour: int = 30
    window_seconds: int = 3600


class DemoConfig(BaseModel):
    """Demo mode configuration for showcase deployments.

    When enabled, adds rate limiting and sidebar restrictions.
    Owner can unlock full access via secret URL parameter.
    """

    enabled: bool = False
    owner_secret: str = ""
    rate_limit: RateLimitConfig = RateLimitConfig()
    whitelist_ips: List[str] = ["127.0.0.1", "::1"]

    @field_validator("owner_secret", mode="before")
    @classmethod
    def empty_string_to_empty(cls, v: Any) -> str:
        """Convert None to empty string for owner_secret."""
        if v is None:
            return ""
        return v


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

    # Tool configurations
    parallel: Optional[ParallelConfig] = None  # Parallel.ai for web search/extract
    sandbox: Optional[SandboxConfig] = None  # E2B for Python execution

    # Query classification (disabled by default - let model decide when to use tools)
    query_classification: Optional[QueryClassificationConfig] = None
    python: Optional[PythonConfig] = None

    # ChatGPT OAuth integration
    chatgpt: Optional[ChatGPTConfig] = None

    # Demo mode (rate limiting, sidebar lock)
    demo: Optional[DemoConfig] = None

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
        if self.parallel:
            snapshot["parallel"] = self.parallel.model_dump()
        if self.sandbox:
            snapshot["sandbox"] = self.sandbox.model_dump()
        if self.query_classification:
            snapshot["query_classification"] = self.query_classification.model_dump()
        if self.python:
            snapshot["python"] = self.python.model_dump()
        if self.chatgpt:
            snapshot["chatgpt"] = self.chatgpt.model_dump()
        if self.demo:
            # Don't expose owner_secret in snapshot
            demo_snapshot = self.demo.model_dump()
            demo_snapshot.pop("owner_secret", None)
            snapshot["demo"] = demo_snapshot
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
