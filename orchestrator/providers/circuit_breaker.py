"""Circuit breaker pattern for provider resilience.

The circuit breaker prevents cascading failures by fast-failing requests
to unhealthy providers, allowing them time to recover.

States:
- CLOSED: Normal operation, requests flow through
- OPEN: Provider is unhealthy, requests are rejected immediately
- HALF_OPEN: Testing recovery, allow limited requests through
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests flow through
    OPEN = "open"  # Failing, requests rejected immediately
    HALF_OPEN = "half_open"  # Testing recovery, allow one request


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: float = 30.0  # Seconds before trying half-open
    success_threshold: int = 2  # Successes in half-open before closing


@dataclass
class CircuitBreaker:
    """Circuit breaker for a single provider.

    Thread-safe via asyncio.Lock for concurrent requests.

    Example:
        cb = CircuitBreaker(name="deepinfra")

        if await cb.can_execute():
            try:
                result = await provider.complete(...)
                await cb.record_success()
                return result
            except Exception:
                await cb.record_failure()
                raise
        else:
            # Skip this provider, try next in chain
            pass
    """

    name: str  # Provider name for logging
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # Internal state (initialized after __init__)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Current failure count."""
        return self._failure_count

    @property
    def is_available(self) -> bool:
        """Check if circuit allows requests (sync check, no state transition).

        Use can_execute() for async state transitions.
        """
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN:
            return True
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                return elapsed >= self.config.recovery_timeout
        return False

    async def can_execute(self) -> bool:
        """Check if request can proceed, transitioning to half-open if needed.

        This is the main entry point for checking circuit state.
        It handles state transitions from OPEN -> HALF_OPEN when recovery
        timeout has elapsed.

        Returns:
            True if request should proceed, False to skip this provider.
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.HALF_OPEN:
                # Already in half-open, allow the test request
                return True

            # State is OPEN - check recovery timeout
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.config.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(
                        "Circuit breaker transitioning to half-open",
                        extra={"provider": self.name, "elapsed_seconds": round(elapsed, 2)},
                    )
                    return True

            logger.debug(
                "Circuit breaker is open, skipping provider",
                extra={"provider": self.name},
            )
            return False

    async def record_success(self) -> None:
        """Record a successful request.

        In HALF_OPEN state, success counts toward closing the circuit.
        In CLOSED state, resets the failure counter.
        """
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        "Circuit breaker closed after recovery",
                        extra={"provider": self.name},
                    )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self) -> None:
        """Record a failed request.

        In CLOSED state, increments failure count and may open circuit.
        In HALF_OPEN state, immediately reopens the circuit.
        """
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failed during recovery test, go back to open
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker reopened after half-open failure",
                    extra={"provider": self.name},
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit breaker opened",
                        extra={
                            "provider": self.name,
                            "failure_count": self._failure_count,
                        },
                    )

    def reset(self) -> None:
        """Reset circuit breaker to initial state.

        Primarily for testing purposes.
        """
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
