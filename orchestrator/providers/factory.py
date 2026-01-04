"""Factory for creating LLM providers from configuration."""

from typing import TYPE_CHECKING, Optional, Union

from .base import LLMProvider
from .chain import ChainedProvider, ProviderChain
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .openai_compat import OpenAICompatProvider

if TYPE_CHECKING:
    from orchestrator.config import ProviderChainConfig, ProviderConfig


def create_provider(
    config: "ProviderConfig",
    chain_config: Optional["ProviderChainConfig"] = None,
) -> LLMProvider:
    """Create an LLM provider from configuration.

    If chain_config is provided and enabled, creates a ProviderChain with
    failover support. Otherwise, creates a single OpenAICompatProvider.

    Args:
        config: Single provider configuration (used if chain disabled).
        chain_config: Optional chain configuration for failover.

    Returns:
        LLMProvider instance (either OpenAICompatProvider or ProviderChain).
    """
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
