"""Tests for CircuitBreaker."""

import asyncio
import time

import pytest

from orchestrator.providers.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self):
        """Circuit breaker starts in closed state."""
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert await cb.can_execute() is True

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        """Circuit opens after reaching failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(name="test", config=config)

        # Record failures
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        await cb.record_failure()  # 3rd failure
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_blocks_execution(self):
        """Open circuit prevents execution."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60.0)
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert await cb.can_execute() is False

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        """Circuit transitions to half-open after recovery timeout."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1)
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Calling can_execute triggers transition
        assert await cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_after_success_in_half_open(self):
        """Circuit closes after success threshold in half-open."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
            success_threshold=2,
        )
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        await asyncio.sleep(0.15)
        await cb.can_execute()  # Triggers half-open

        await cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # Still half-open

        await cb.record_success()  # 2nd success
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reopens_on_failure_in_half_open(self):
        """Circuit reopens if failure occurs in half-open state."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1)
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        await asyncio.sleep(0.15)
        await cb.can_execute()  # Triggers half-open
        assert cb.state == CircuitState.HALF_OPEN

        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        """Success in closed state resets failure count."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        await cb.record_failure()  # 2 failures
        await cb.record_success()  # Reset

        await cb.record_failure()
        await cb.record_failure()  # 2 failures again, not 4
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_is_available_sync_check(self):
        """is_available property provides sync state check."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60.0)
        cb = CircuitBreaker(name="test", config=config)

        assert cb.is_available is True

        await cb.record_failure()
        assert cb.is_available is False

    @pytest.mark.asyncio
    async def test_reset_clears_all_state(self):
        """reset() returns circuit to initial state."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 1

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


class TestCircuitBreakerConcurrency:
    """Tests for thread-safety under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_failures_tracked_correctly(self):
        """Concurrent failure recordings are thread-safe."""
        config = CircuitBreakerConfig(failure_threshold=10)
        cb = CircuitBreaker(name="test", config=config)

        # Record 10 failures concurrently
        await asyncio.gather(*[cb.record_failure() for _ in range(10)])

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_successes_tracked_correctly(self):
        """Concurrent success recordings are thread-safe."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.05,
            success_threshold=5,
        )
        cb = CircuitBreaker(name="test", config=config)

        # Open the circuit
        await cb.record_failure()
        await asyncio.sleep(0.1)
        await cb.can_execute()  # Transition to half-open

        # Record 5 successes concurrently
        await asyncio.gather(*[cb.record_success() for _ in range(5)])

        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_concurrent_can_execute_calls(self):
        """Concurrent can_execute calls don't cause race conditions."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.05)
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        await asyncio.sleep(0.1)

        # Call can_execute concurrently - all should return True
        results = await asyncio.gather(*[cb.can_execute() for _ in range(10)])

        assert all(results)
        assert cb.state == CircuitState.HALF_OPEN


class TestCircuitBreakerConfig:
    """Tests for configuration options."""

    @pytest.mark.asyncio
    async def test_default_config_values(self):
        """Default config has expected values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 30.0
        assert config.success_threshold == 2

    @pytest.mark.asyncio
    async def test_custom_failure_threshold(self):
        """Custom failure threshold is respected."""
        config = CircuitBreakerConfig(failure_threshold=10)
        cb = CircuitBreaker(name="test", config=config)

        # 9 failures - still closed
        for _ in range(9):
            await cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        # 10th failure - opens
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_custom_success_threshold(self):
        """Custom success threshold is respected."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.05,
            success_threshold=3,
        )
        cb = CircuitBreaker(name="test", config=config)

        await cb.record_failure()
        await asyncio.sleep(0.1)
        await cb.can_execute()

        # 2 successes - still half-open
        await cb.record_success()
        await cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN

        # 3rd success - closes
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_has_name(self):
        """Circuit breaker stores name for logging."""
        cb = CircuitBreaker(name="deepinfra")
        assert cb.name == "deepinfra"
