"""Tests for ProviderChain."""

import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.providers.base import LLMResponse, ProviderError, RetryExhaustedError
from orchestrator.providers.chain import (
    AllProvidersFailedError,
    ChainedProvider,
    ProviderChain,
)
from orchestrator.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


def create_mock_provider(name: str, response_text: str = "test response"):
    """Helper to create a mock provider."""
    provider = AsyncMock()
    provider.complete.return_value = LLMResponse(
        text=response_text,
        endpoint_used="/v1/chat/completions",
    )
    provider.complete_streaming.return_value = LLMResponse(
        text=response_text,
        endpoint_used="/v1/chat/completions",
    )
    provider.health_check.return_value = True
    provider.close.return_value = None
    return provider


def create_chained_provider(
    name: str,
    provider=None,
    priority: int = 0,
    failure_threshold: int = 2,
):
    """Helper to create a chained provider with circuit breaker."""
    if provider is None:
        provider = create_mock_provider(name)

    return ChainedProvider(
        name=name,
        provider=provider,
        circuit_breaker=CircuitBreaker(
            name=name,
            config=CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                recovery_timeout=0.1,
            ),
        ),
        priority=priority,
    )


class TestProviderChainBasics:
    """Basic functionality tests."""

    @pytest.mark.asyncio
    async def test_requires_at_least_one_provider(self):
        """ProviderChain requires at least one provider."""
        with pytest.raises(ValueError, match="at least one provider"):
            ProviderChain(providers=[])

    @pytest.mark.asyncio
    async def test_uses_primary_provider_when_healthy(self):
        """Primary provider is used when available."""
        primary = create_chained_provider("primary", priority=0)
        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        response = await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        assert primary.provider.complete.called
        assert not fallback.provider.complete.called
        await chain.close()

    @pytest.mark.asyncio
    async def test_providers_sorted_by_priority(self):
        """Providers are tried in priority order."""
        # Create out of order
        fallback = create_chained_provider("fallback", priority=1)
        primary = create_chained_provider("primary", priority=0)

        chain = ProviderChain(providers=[fallback, primary])

        # Primary should be first despite being added second
        assert chain.providers[0].name == "primary"
        assert chain.providers[1].name == "fallback"
        await chain.close()

    @pytest.mark.asyncio
    async def test_fails_over_to_fallback_on_primary_failure(self):
        """Fallback is used when primary fails."""
        primary_provider = create_mock_provider("primary")
        primary_provider.complete.side_effect = RetryExhaustedError("Primary failed")
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback_provider = create_mock_provider("fallback", "fallback response")
        fallback = create_chained_provider(
            "fallback", provider=fallback_provider, priority=1
        )

        chain = ProviderChain(providers=[primary, fallback])

        response = await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        assert primary.provider.complete.called
        assert fallback.provider.complete.called
        assert response.text == "fallback response"
        await chain.close()

    @pytest.mark.asyncio
    async def test_raises_all_providers_failed_when_all_fail(self):
        """AllProvidersFailedError raised when all providers fail."""
        primary_provider = create_mock_provider("primary")
        primary_provider.complete.side_effect = RetryExhaustedError("Primary failed")
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback_provider = create_mock_provider("fallback")
        fallback_provider.complete.side_effect = RetryExhaustedError("Fallback failed")
        fallback = create_chained_provider(
            "fallback", provider=fallback_provider, priority=1
        )

        chain = ProviderChain(providers=[primary, fallback])

        with pytest.raises(AllProvidersFailedError) as exc_info:
            await chain.complete(
                messages=[{"role": "user", "content": "test"}],
                model="test-model",
            )

        assert len(exc_info.value.errors) == 2
        assert "primary" in str(exc_info.value)
        assert "fallback" in str(exc_info.value)
        await chain.close()

    @pytest.mark.asyncio
    async def test_handles_unexpected_exceptions(self):
        """Unexpected exceptions are caught and recorded."""
        primary_provider = create_mock_provider("primary")
        primary_provider.complete.side_effect = RuntimeError("Unexpected!")
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        response = await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        # Should failover to fallback
        assert response.text == "test response"
        await chain.close()


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration with chain."""

    @pytest.mark.asyncio
    async def test_skips_provider_with_open_circuit(self):
        """Providers with open circuits are skipped."""
        primary = create_chained_provider("primary", priority=0)
        fallback = create_chained_provider("fallback", priority=1)

        # Manually open primary's circuit
        primary.circuit_breaker._state = CircuitState.OPEN
        primary.circuit_breaker._last_failure_time = time.time()

        chain = ProviderChain(providers=[primary, fallback])

        response = await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        # Primary should be skipped
        assert not primary.provider.complete.called
        assert fallback.provider.complete.called
        await chain.close()

    @pytest.mark.asyncio
    async def test_circuit_opens_after_repeated_failures(self):
        """Circuit breaker opens after failure threshold."""
        primary_provider = create_mock_provider("primary")
        primary_provider.complete.side_effect = RetryExhaustedError("Failed")
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0, failure_threshold=2
        )

        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        # Trigger failures to open circuit (threshold is 2)
        await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )
        await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        # Circuit should now be open
        assert primary.circuit_breaker.state == CircuitState.OPEN

        # Third request should skip primary entirely
        primary.provider.complete.reset_mock()
        await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        assert not primary.provider.complete.called  # Skipped
        await chain.close()

    @pytest.mark.asyncio
    async def test_success_records_to_circuit_breaker(self):
        """Successful requests are recorded in circuit breaker."""
        primary = create_chained_provider("primary", priority=0)
        chain = ProviderChain(providers=[primary])

        # Add a failure first
        await primary.circuit_breaker.record_failure()
        assert primary.circuit_breaker.failure_count == 1

        # Success should reset
        await chain.complete(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
        )

        assert primary.circuit_breaker.failure_count == 0
        await chain.close()


class TestStreamingFailover:
    """Tests for streaming with failover."""

    @pytest.mark.asyncio
    async def test_streaming_uses_primary_when_healthy(self):
        """Streaming uses primary provider when available."""
        primary = create_chained_provider("primary", priority=0)
        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        on_token = MagicMock()
        response = await chain.complete_streaming(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            on_token=on_token,
        )

        assert primary.provider.complete_streaming.called
        assert not fallback.provider.complete_streaming.called
        await chain.close()

    @pytest.mark.asyncio
    async def test_streaming_failover_on_connection_error(self):
        """Streaming fails over on connection error before streaming starts."""
        primary_provider = create_mock_provider("primary")
        primary_provider.complete_streaming.side_effect = RetryExhaustedError(
            "Connection failed"
        )
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        on_token = MagicMock()
        response = await chain.complete_streaming(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            on_token=on_token,
        )

        assert fallback.provider.complete_streaming.called
        await chain.close()

    @pytest.mark.asyncio
    async def test_streaming_skips_open_circuit(self):
        """Streaming skips providers with open circuits."""
        primary = create_chained_provider("primary", priority=0)
        fallback = create_chained_provider("fallback", priority=1)

        # Open primary's circuit
        primary.circuit_breaker._state = CircuitState.OPEN
        primary.circuit_breaker._last_failure_time = time.time()

        chain = ProviderChain(providers=[primary, fallback])

        on_token = MagicMock()
        await chain.complete_streaming(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            on_token=on_token,
        )

        assert not primary.provider.complete_streaming.called
        assert fallback.provider.complete_streaming.called
        await chain.close()


class TestHealthCheck:
    """Tests for health check across chain."""

    @pytest.mark.asyncio
    async def test_healthy_if_any_provider_healthy(self):
        """Chain is healthy if at least one provider is healthy."""
        primary_provider = create_mock_provider("primary")
        primary_provider.health_check.return_value = False
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        assert await chain.health_check() is True
        await chain.close()

    @pytest.mark.asyncio
    async def test_unhealthy_if_all_providers_unhealthy(self):
        """Chain is unhealthy if all providers are unhealthy."""
        primary_provider = create_mock_provider("primary")
        primary_provider.health_check.return_value = False
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback_provider = create_mock_provider("fallback")
        fallback_provider.health_check.return_value = False
        fallback = create_chained_provider(
            "fallback", provider=fallback_provider, priority=1
        )

        chain = ProviderChain(providers=[primary, fallback])

        assert await chain.health_check() is False
        await chain.close()

    @pytest.mark.asyncio
    async def test_health_check_handles_exceptions(self):
        """Health check catches provider exceptions."""
        primary_provider = create_mock_provider("primary")
        primary_provider.health_check.side_effect = Exception("Connection error")
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        # Should still return True because fallback is healthy
        assert await chain.health_check() is True
        await chain.close()


class TestClose:
    """Tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_closes_all_providers(self):
        """Close method closes all providers."""
        primary = create_chained_provider("primary", priority=0)
        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])
        await chain.close()

        assert primary.provider.close.called
        assert fallback.provider.close.called

    @pytest.mark.asyncio
    async def test_close_handles_provider_errors(self):
        """Close handles errors from individual providers."""
        primary_provider = create_mock_provider("primary")
        primary_provider.close.side_effect = Exception("Close failed")
        primary = create_chained_provider(
            "primary", provider=primary_provider, priority=0
        )

        fallback = create_chained_provider("fallback", priority=1)

        chain = ProviderChain(providers=[primary, fallback])

        # Should not raise
        await chain.close()

        # Fallback should still be closed
        assert fallback.provider.close.called


class TestAllProvidersFailedError:
    """Tests for AllProvidersFailedError."""

    def test_error_message_includes_all_providers(self):
        """Error message includes all provider errors."""
        errors = [
            ("primary", Exception("Primary failed")),
            ("fallback", Exception("Fallback failed")),
        ]

        error = AllProvidersFailedError(errors)

        assert "primary" in str(error)
        assert "fallback" in str(error)
        assert "All providers failed" in str(error)

    def test_errors_list_accessible(self):
        """Errors list is accessible on exception."""
        errors = [
            ("primary", Exception("Primary failed")),
        ]

        error = AllProvidersFailedError(errors)

        assert len(error.errors) == 1
        assert error.errors[0][0] == "primary"
