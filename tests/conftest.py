"""Pytest fixtures for orchestrator tests."""

import asyncio
import sys
from pathlib import Path

import pytest

# Add orchestrator to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="function")
def event_loop():
    """Create event loop for async tests.

    Using function scope to ensure each test gets a fresh event loop,
    which prevents issues with asyncio.Lock objects being bound to
    different event loops.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_trace_repo_lock():
    """Reset the TraceRepo class-level lock between tests.

    The TraceRepo._seq_lock is a class-level asyncio.Lock that gets bound
    to a specific event loop. When tests create new event loops, the lock
    becomes invalid. This fixture resets the lock for proper isolation.
    """
    from orchestrator.storage.repositories.trace_repo import TraceRepo

    # Reset the lock before each test
    TraceRepo._seq_lock = asyncio.Lock()
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset process-global rate limiter state between tests."""
    from orchestrator.middleware.rate_limit import _rate_limiter

    _rate_limiter.reset()
    yield
    _rate_limiter.reset()
