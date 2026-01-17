"""Provider chain with failover and circuit breaker support.

The ProviderChain implements the LLMProvider protocol, allowing it to be
used transparently in place of a single provider. It manages multiple
providers with automatic failover when the primary provider fails.

Failover Strategy:
1. Try primary provider (lowest priority number)
2. If circuit breaker is open OR request fails, try next provider
3. If all providers fail, raise AllProvidersFailedError

Note: Failover only occurs before streaming starts. Once tokens begin
flowing, the stream is committed to that provider.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from orchestrator.logging_config import get_logger

from .base import (
    LLMProvider,
    LLMResponse,
    ProviderError,
    RetryExhaustedError,
)
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = get_logger(__name__)


class AllProvidersFailedError(ProviderError):
    """Raised when all providers in the chain have failed."""

    def __init__(self, errors: List[tuple]):
        self.errors = errors
        error_summary = "; ".join(f"{name}: {err}" for name, err in errors)
        super().__init__(f"All providers failed: {error_summary}")


@dataclass
class ChainedProvider:
    """A provider with its circuit breaker.

    Attributes:
        name: Identifier for logging (e.g., "deepinfra", "together_ai")
        provider: The underlying LLMProvider implementation
        circuit_breaker: Circuit breaker for this provider
        priority: Lower number = higher priority (tried first)
    """

    name: str
    provider: LLMProvider
    circuit_breaker: CircuitBreaker
    priority: int = 0


class ProviderChain:
    """Chain of LLM providers with failover support.

    Implements LLMProvider protocol for transparent integration.

    Example:
        chain = ProviderChain(providers=[
            ChainedProvider(
                name="deepinfra",
                provider=create_provider(deepinfra_config),
                circuit_breaker=CircuitBreaker(name="deepinfra"),
                priority=0,  # Primary
            ),
            ChainedProvider(
                name="together_ai",
                provider=create_provider(together_config),
                circuit_breaker=CircuitBreaker(name="together_ai"),
                priority=1,  # Fallback
            ),
        ])

        # Use like any LLMProvider
        response = await chain.complete(messages=..., model=...)
    """

    def __init__(
        self,
        providers: List[ChainedProvider],
        default_circuit_config: Optional[CircuitBreakerConfig] = None,
    ):
        """Initialize the provider chain.

        Args:
            providers: List of providers with their circuit breakers.
            default_circuit_config: Default circuit breaker config if not specified.

        Raises:
            ValueError: If no providers are given.
        """
        if not providers:
            raise ValueError("ProviderChain requires at least one provider")

        # Sort by priority (lower = tried first)
        self._providers = sorted(providers, key=lambda p: p.priority)
        self._default_circuit_config = default_circuit_config or CircuitBreakerConfig()

        logger.info(
            "ProviderChain initialized",
            extra={
                "provider_count": len(self._providers),
                "providers": [p.name for p in self._providers],
            },
        )

    @property
    def providers(self) -> List[ChainedProvider]:
        """Get ordered list of providers."""
        return self._providers

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        previous_response_id: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete with failover across providers.

        Tries each provider in priority order until one succeeds.
        Circuit breaker state determines if provider is attempted.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name/ID.
            instructions: System prompt.
            tools: Tool definitions for function calling.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            reasoning_effort: Native reasoning effort.
            stream: Whether to stream (ignored, use complete_streaming).
            previous_response_id: For stateful mode.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse from the first successful provider.

        Raises:
            AllProvidersFailedError: If all providers fail.
        """
        errors: List[tuple] = []

        for chained in self._providers:
            # Check circuit breaker
            if not await chained.circuit_breaker.can_execute():
                logger.debug(
                    "Skipping provider due to open circuit",
                    extra={"provider": chained.name},
                )
                continue

            try:
                logger.debug(
                    "Attempting provider",
                    extra={"provider": chained.name},
                )

                response = await chained.provider.complete(
                    messages=messages,
                    model=model,
                    instructions=instructions,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                    stream=stream,
                    previous_response_id=previous_response_id,
                    **kwargs,
                )

                # Success - record and return
                await chained.circuit_breaker.record_success()
                logger.info(
                    "Provider completed successfully",
                    extra={"provider": chained.name},
                )
                return response

            except (RetryExhaustedError, ProviderError) as e:
                # Provider-level failure (after retries) - record and try next
                await chained.circuit_breaker.record_failure()
                errors.append((chained.name, e))
                logger.warning(
                    "Provider failed, trying next",
                    extra={"provider": chained.name, "error": str(e)},
                )
                continue
            except Exception as e:
                # Unexpected error - still record failure
                await chained.circuit_breaker.record_failure()
                errors.append((chained.name, e))
                logger.error(
                    "Unexpected provider error",
                    extra={"provider": chained.name, "error": str(e)},
                )
                continue

        # All providers failed
        raise AllProvidersFailedError(errors)

    async def complete_streaming(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        on_token: Callable[[str], None],
        on_reasoning: Optional[Callable[[str], None]] = None,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        previous_response_id: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Stream completion with failover across providers.

        Note: Failover only occurs before streaming starts.
        Once tokens begin flowing, the stream is committed.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            on_token: Callback for each content token.
            on_reasoning: Callback for reasoning tokens.
            instructions: System prompt.
            tools: Tool definitions.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            reasoning_effort: Native reasoning effort.
            previous_response_id: For stateful mode.
            **kwargs: Additional parameters.

        Returns:
            Final LLMResponse after streaming completes.

        Raises:
            AllProvidersFailedError: If all providers fail.
        """
        errors: List[tuple] = []

        for chained in self._providers:
            # Check circuit breaker
            if not await chained.circuit_breaker.can_execute():
                logger.debug(
                    "Skipping provider for streaming due to open circuit",
                    extra={"provider": chained.name},
                )
                continue

            try:
                logger.debug(
                    "Attempting streaming with provider",
                    extra={"provider": chained.name},
                )

                response = await chained.provider.complete_streaming(
                    messages=messages,
                    model=model,
                    on_token=on_token,
                    on_reasoning=on_reasoning,
                    instructions=instructions,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                    previous_response_id=previous_response_id,
                    **kwargs,
                )

                # Success - record and return
                await chained.circuit_breaker.record_success()
                logger.info(
                    "Streaming completed successfully",
                    extra={"provider": chained.name},
                )
                return response

            except (RetryExhaustedError, ProviderError) as e:
                # Provider-level failure - record and try next
                await chained.circuit_breaker.record_failure()
                errors.append((chained.name, e))
                logger.warning(
                    "Streaming provider failed, trying next",
                    extra={"provider": chained.name, "error": str(e)},
                )
                continue
            except Exception as e:
                # Unexpected error
                await chained.circuit_breaker.record_failure()
                errors.append((chained.name, e))
                logger.error(
                    "Unexpected streaming error",
                    extra={"provider": chained.name, "error": str(e)},
                )
                continue

        # All providers failed
        raise AllProvidersFailedError(errors)

    async def health_check(self) -> bool:
        """Check if at least one provider is healthy.

        Returns:
            True if any provider is healthy, False if all are down.
        """
        for chained in self._providers:
            try:
                if await chained.provider.health_check():
                    return True
            except Exception:
                continue
        return False

    async def close(self) -> None:
        """Close all providers and release resources."""
        for chained in self._providers:
            try:
                await chained.provider.close()
            except Exception as e:
                logger.warning(
                    "Error closing provider",
                    extra={"provider": chained.name, "error": str(e)},
                )
