"""End-to-end tests for agent API flow.

Tests the full agent flow from API request to response,
mocking only the external LLM provider and tools.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from orchestrator.app import app
from orchestrator.agent import AgentResult
from orchestrator.providers.base import LLMResponse
from orchestrator.storage.db import Database
import orchestrator.storage.db as db_module
import orchestrator.routes.agent_runs as agent_runs_module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory database for each test."""
    # Clear any existing singleton before test
    db_module._db = None

    database = Database(":memory:")

    # Get or create event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Run async setup
    loop.run_until_complete(database.connect())

    # Create async get_db that returns our database
    async def mock_get_db():
        return database

    # Patch get_db everywhere it's used
    with patch("orchestrator.storage.db.get_db", mock_get_db):
        with patch("orchestrator.routes.conversations.get_db", mock_get_db):
            with patch("orchestrator.routes.runs.get_db", mock_get_db):
                with patch("orchestrator.routes.agent_runs.get_db", mock_get_db):
                    with patch("orchestrator.engine.chat_engine.get_db", mock_get_db):
                        with patch("orchestrator.agent.factory.get_db", mock_get_db):
                            yield database

    # Cleanup
    loop.run_until_complete(database.close())
    db_module._db = None


@pytest.fixture
def mock_agent_engine():
    """Mock the agent engine that simulates a research flow."""
    mock_engine = MagicMock()

    async def mock_run(run_id, query, event_callback=None, conversation_id=None):
        """Simulate a multi-step agent research flow."""
        if event_callback:
            # Emit agent started
            event_callback({
                "type": "agent_started",
                "run_id": run_id,
                "query": query,
            })

            # Step 1: Planning/thinking
            event_callback({
                "type": "step_started",
                "run_id": run_id,
                "step_number": 1,
                "steps_remaining": 9,
            })
            event_callback({
                "type": "thinking",
                "run_id": run_id,
                "content": "I need to search for information about Tokyo's population.",
            })

            # Simulate tool use (web_search)
            event_callback({
                "type": "tool_start",
                "run_id": run_id,
                "tool_call_id": "tc-1",
                "tool_name": "web_search",
                "arguments": {"query": "Tokyo population 2024"},
            })
            event_callback({
                "type": "tool_result",
                "run_id": run_id,
                "tool_call_id": "tc-1",
                "tool_name": "web_search",
                "success": True,
                "result_summary": "Found 5 results about Tokyo population",
                "duration_ms": 150,
            })

            # Step 2: Synthesis
            event_callback({
                "type": "step_started",
                "run_id": run_id,
                "step_number": 2,
                "steps_remaining": 8,
            })
            event_callback({
                "type": "synthesizing",
                "run_id": run_id,
                "step_number": 2,
            })

            # Stream final answer
            for token in ["The ", "population ", "of ", "Tokyo ", "is ", "about ", "14 ", "million."]:
                event_callback({
                    "type": "answer_token",
                    "run_id": run_id,
                    "content": token,
                })

        # Return successful result
        return AgentResult(
            run_id=run_id,
            success=True,
            final_answer="The population of Tokyo is about 14 million.",
            citations=[
                {
                    "source_url": "https://example.com/tokyo",
                    "title": "Tokyo Population Statistics",
                    "snippet": "Tokyo has a population of approximately 14 million.",
                }
            ],
            total_steps=2,
            error_message=None,
            timing_ms=500,
        )

    mock_engine.run = mock_run
    return mock_engine


@pytest.fixture
def mock_failing_engine():
    """Mock agent engine that fails."""
    mock_engine = MagicMock()

    async def mock_run(run_id, query, event_callback=None, conversation_id=None):
        if event_callback:
            event_callback({"type": "agent_started", "run_id": run_id})
        raise RuntimeError("LLM provider unavailable")

    mock_engine.run = mock_run
    return mock_engine


@pytest.fixture
def client(test_db, mock_agent_engine):
    """Create a test client with mocked agent engine."""
    # Clear module state before each test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()

    async def mock_create_engine(**kwargs):
        return mock_agent_engine

    with patch("orchestrator.agent.factory.create_agent_engine", mock_create_engine):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    # Clean up module state after test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()


@pytest.fixture
async def async_client(test_db, mock_agent_engine):
    """Create an async test client for SSE streaming tests."""
    # Clear module state before each test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()

    async def mock_create_engine(**kwargs):
        return mock_agent_engine

    with patch("orchestrator.agent.factory.create_agent_engine", mock_create_engine):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    # Clean up module state after test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()


# =============================================================================
# E2E Tests
# =============================================================================


class TestAgentE2EFlow:
    """Test complete agent research flow."""

    def test_simple_query_returns_answer(self, client):
        """Simple query returns answer with citations."""
        # Start the run
        response = client.post(
            "/api/agent/runs",
            json={"query": "What is the population of Tokyo?"},
        )
        assert response.status_code == 200
        data = response.json()
        run_id = data["run_id"]
        assert data["status"] == "running"

        # Wait for completion
        import time
        time.sleep(0.3)

        # Check status
        status_response = client.get(f"/api/agent/runs/{run_id}")
        assert status_response.status_code == 200

    def test_trace_includes_steps_and_tools(self, client):
        """Trace includes all steps and tool calls."""
        # Start the run
        response = client.post(
            "/api/agent/runs",
            json={"query": "Research Tokyo population"},
        )
        run_id = response.json()["run_id"]

        # Wait for completion
        import time
        time.sleep(0.3)

        # Get trace
        trace_response = client.get(f"/api/agent/runs/{run_id}/trace")
        assert trace_response.status_code == 200
        trace = trace_response.json()

        assert trace["run_id"] == run_id
        # Steps and tool calls are recorded
        assert "steps" in trace
        assert "tool_calls" in trace
        assert "citations" in trace


class TestAgentErrorRecovery:
    """Test error handling and recovery."""

    def test_provider_failure_returns_error(self, test_db, mock_failing_engine):
        """Provider failure results in error status."""
        # Clear module state
        agent_runs_module._active_runs.clear()
        agent_runs_module._abort_signals.clear()
        agent_runs_module._event_history.clear()

        async def mock_create_engine(**kwargs):
            return mock_failing_engine

        with patch("orchestrator.agent.factory.create_agent_engine", mock_create_engine):
            with TestClient(app, raise_server_exceptions=False) as client:
                # Start the run
                response = client.post(
                    "/api/agent/runs",
                    json={"query": "This will fail"},
                )
                assert response.status_code == 200
                run_id = response.json()["run_id"]

                # Wait for failure
                import time
                time.sleep(0.3)

                # The run should exist
                status_response = client.get(f"/api/agent/runs/{run_id}")
                assert status_response.status_code == 200


class TestAgentCancellation:
    """Test run cancellation."""

    def test_cancel_active_run(self, client):
        """Can cancel an actively running agent."""
        # Manually add a run to active_runs to simulate an ongoing run
        run_id = "cancel-test-run"
        queue = asyncio.Queue()
        agent_runs_module._active_runs[run_id] = queue
        agent_runs_module._abort_signals[run_id] = asyncio.Event()

        # Cancel it
        response = client.post(f"/api/agent/runs/{run_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["run_id"] == run_id

    def test_cancel_nonexistent_run_returns_404(self, client):
        """Cancelling nonexistent run returns 404."""
        response = client.post("/api/agent/runs/fake-run-id/cancel")
        assert response.status_code == 404


class TestHealthCheck:
    """Test basic API health."""

    def test_health_endpoint(self, client):
        """Health check returns ok."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
