"""Factory for creating LLM providers from configuration."""

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Union

from .base import LLMProvider
from .chain import ChainedProvider, ProviderChain
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .openai_compat import OpenAICompatProvider

if TYPE_CHECKING:
    from orchestrator.config import ChatGPTConfig, ProviderChainConfig, ProviderConfig
    from orchestrator.models.registry import ResolvedModel

# Runtime provider override — set by /api/models/local/start, cleared by /stop
_provider_override: Optional[LLMProvider] = None


def get_provider_override() -> Optional[LLMProvider]:
    """Get the current runtime provider override (if any)."""
    return _provider_override


def set_provider_override(provider: Optional[LLMProvider]) -> None:
    """Set or clear the runtime provider override."""
    global _provider_override
    _provider_override = provider


def create_chatgpt_provider(
    tokens: Dict[str, Any],
    chatgpt_config: Optional["ChatGPTConfig"] = None,
    model: Optional[str] = None,
) -> "LLMProvider":
    """Create a ChatGPT backend provider from stored tokens.

    Args:
        tokens: Dict with access_token, account_id, refresh_token, expires_at.
        chatgpt_config: Optional ChatGPT configuration override.
        model: Optional model name override (e.g., "o4-mini").

    Returns:
        ChatGPTProvider instance.
    """
    from .chatgpt import ChatGPTProvider

    if chatgpt_config is None:
        from orchestrator.config import get_chat_config

        config = get_chat_config()
        chatgpt_config = config.chatgpt

    default_model = model or (chatgpt_config.default_model if chatgpt_config else "gpt-5.2-codex")

    provider = ChatGPTProvider(
        access_token=tokens["access_token"],
        account_id=tokens["account_id"],
        backend_url=chatgpt_config.backend_url
        if chatgpt_config
        else "https://chatgpt.com/backend-api",
        default_model=default_model,
        reasoning_effort=chatgpt_config.reasoning_effort if chatgpt_config else "medium",
    )
    provider._reasoning_provider_family = "chatgpt"
    provider._supports_reasoning = True
    return provider


def create_provider_for_model(model_string: str) -> Tuple[LLMProvider, "ResolvedModel"]:
    """Create an LLM provider from a model registry string.

    Resolves the model string via ModelRegistry, then creates an
    OpenAICompatProvider with the resolved parameters.

    Args:
        model_string: Model name, alias, or "provider:model" string.

    Returns:
        Tuple of (provider, resolved_model).
    """
    from orchestrator.models.registry import ModelRegistry

    resolved = ModelRegistry.resolve(model_string)
    provider = OpenAICompatProvider(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
    )
    provider._reasoning_provider_family = resolved.provider_name
    provider._reasoning_request_param = resolved.reasoning_request_param
    provider._supports_reasoning = resolved.reasoning_effort is not None
    provider._supports_vision = resolved.supports_vision
    provider._max_output_tokens = resolved.max_output_tokens
    provider._context_window = resolved.context_window
    provider._context_profile_provider_name = resolved.provider_name
    provider._context_profile_model_id = resolved.model_id
    provider._context_profile_display_name = resolved.display_name
    return provider, resolved


def create_provider(
    config: "ProviderConfig",
    chain_config: Optional["ProviderChainConfig"] = None,
) -> LLMProvider:
    """Create an LLM provider from configuration.

    If a runtime override is set (via local model start), returns that.
    If chain_config is provided and enabled, creates a ProviderChain with
    failover support. Otherwise, creates a single OpenAICompatProvider.

    Args:
        config: Single provider configuration (used if chain disabled).
        chain_config: Optional chain configuration for failover.

    Returns:
        LLMProvider instance (either OpenAICompatProvider or ProviderChain).
    """
    # Check runtime override first (local model)
    if _provider_override is not None:
        return _provider_override

    # Check if chain mode is enabled
    if chain_config and chain_config.enabled and chain_config.providers:
        return _create_provider_chain(chain_config)

    # Single provider mode (backward compatible)
    return _create_single_provider(config)


def _create_single_provider(config: "ProviderConfig") -> OpenAICompatProvider:
    """Create a single OpenAI-compatible provider."""
    return OpenAICompatProvider(
        base_url=config.base_url,
        api_key=config.api_key,
        endpoint=config.endpoint,
        fallback_on_404=config.fallback_on_404,
        fail_on_tool_fallback=config.fail_on_tool_fallback,
        timeout=config.timeout,
        max_retries=config.max_retries,
        base_delay=config.base_delay,
        max_delay=config.max_delay,
        retryable_statuses=config.retryable_statuses,
        extra_headers=config.extra_headers,
    )


def _create_provider_chain(chain_config: "ProviderChainConfig") -> ProviderChain:
    """Create a provider chain with circuit breakers.

    Args:
        chain_config: Chain configuration with providers and circuit breaker settings.

    Returns:
        ProviderChain with all providers configured.
    """
    chained_providers = []

    for provider_cfg in chain_config.providers:
        # Create the underlying provider
        provider = _create_single_provider(provider_cfg.provider)

        # Create circuit breaker config
        if provider_cfg.circuit_breaker:
            cb_config = CircuitBreakerConfig(
                failure_threshold=provider_cfg.circuit_breaker.failure_threshold,
                recovery_timeout=provider_cfg.circuit_breaker.recovery_timeout_seconds,
                success_threshold=provider_cfg.circuit_breaker.success_threshold,
            )
        else:
            # Use default from chain config
            cb_config = CircuitBreakerConfig(
                failure_threshold=chain_config.default_circuit_breaker.failure_threshold,
                recovery_timeout=chain_config.default_circuit_breaker.recovery_timeout_seconds,
                success_threshold=chain_config.default_circuit_breaker.success_threshold,
            )

        # Create circuit breaker
        circuit_breaker = CircuitBreaker(
            name=provider_cfg.name,
            config=cb_config,
        )

        # Create chained provider
        chained = ChainedProvider(
            name=provider_cfg.name,
            provider=provider,
            circuit_breaker=circuit_breaker,
            priority=provider_cfg.priority,
        )
        chained_providers.append(chained)

    return ProviderChain(providers=chained_providers)
