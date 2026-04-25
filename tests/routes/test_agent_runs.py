"""Tests for agent run routes.

Tests cover all 5 endpoints:
- POST /api/agent/runs - Start agent run
- GET /api/agent/runs/{id} - Get status
- GET /api/agent/runs/{id}/stream - SSE stream
- POST /api/agent/runs/{id}/cancel - Cancel run
- GET /api/agent/runs/{id}/trace - Full trace
"""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import orchestrator.routes.agent_runs as agent_runs_module
import orchestrator.storage.db as db_module
from orchestrator.app import app
from orchestrator.agent import AgentResult
from orchestrator.storage.db import Database


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
    """Mock the agent engine factory."""
    mock_engine = MagicMock()

    async def mock_run(run_id, query, event_callback=None, conversation_id=None):
        # Simulate events
        if event_callback:
            event_callback({"type": "agent_started", "run_id": run_id, "query": query})
            event_callback({"type": "step_started", "run_id": run_id, "step_number": 1})
            event_callback({"type": "thinking", "run_id": run_id, "content": "Analyzing..."})
            event_callback({"type": "synthesizing", "run_id": run_id, "step_number": 1})
            event_callback({"type": "answer_token", "run_id": run_id, "content": "The answer is 42."})

        return AgentResult(
            run_id=run_id,
            success=True,
            final_answer="The answer is 42.",
            citations=[],
            total_steps=1,
            error_message=None,
            timing_ms=100,
        )

    mock_engine.run = mock_run
    return mock_engine


@pytest.fixture
def client(test_db, mock_agent_engine):
    """Create a test client with mocked agent engine."""
    # Clear module state before each test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()
    agent_runs_module._run_tokens.clear()

    async def mock_create_engine(**kwargs):
        return mock_agent_engine

    # Patch at the source module where the import actually happens
    with patch("orchestrator.agent.factory.create_agent_engine", mock_create_engine):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    # Clean up module state after test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()
    agent_runs_module._run_tokens.clear()


@pytest.fixture
async def async_client(test_db, mock_agent_engine):
    """Create an async test client for SSE streaming tests."""
    # Clear module state before each test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()
    agent_runs_module._run_tokens.clear()

    async def mock_create_engine(**kwargs):
        return mock_agent_engine

    # Patch at the source module where the import actually happens
    with patch("orchestrator.agent.factory.create_agent_engine", mock_create_engine):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    # Clean up module state after test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()
    agent_runs_module._run_tokens.clear()


# =============================================================================
# POST /api/agent/runs Tests
# =============================================================================


class TestCreateAgentRun:
    """Tests for POST /api/agent/runs."""

    def test_returns_run_id_and_stream_url(self, client):
        """Successful creation returns run_id and stream_url."""
        response = client.post(
            "/api/agent/runs",
            json={"query": "What is the population of Tokyo?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "running"
        assert data["stream_url"].startswith(f"/api/agent/runs/{data['run_id']}/stream?token=")
        assert "stream_token" in data
        assert len(data["stream_token"]) > 0

    def test_validates_required_query_field(self, client):
        """Missing query field returns 422."""
        response = client.post("/api/agent/runs", json={})
        assert response.status_code == 422

    def test_accepts_optional_conversation_id(self, client):
        """Can specify conversation_id."""
        # Create a conversation via the API (uses TestClient's event loop)
        conv_resp = client.post("/api/conversations", json={"title": "Test conv"})
        assert conv_resp.status_code == 200
        conv_id = conv_resp.json()["conversation_id"]

        response = client.post(
            "/api/agent/runs",
            json={
                "query": "Test query",
                "conversation_id": conv_id,
            },
        )
        assert response.status_code == 200

    def test_accepts_custom_max_steps(self, client):
        """Can override max_steps."""
        response = client.post(
            "/api/agent/runs",
            json={
                "query": "Test query",
                "max_steps": 5,
            },
        )
        assert response.status_code == 200


# =============================================================================
# GET /api/agent/runs/{id} Tests
# =============================================================================


class TestGetAgentRunStatus:
    """Tests for GET /api/agent/runs/{id}."""

    def test_returns_status_for_created_run(self, client):
        """Created run shows status."""
        # Create a run
        create_resp = client.post(
            "/api/agent/runs",
            json={"query": "Test query"},
        )
        run_id = create_resp.json()["run_id"]

        # Give it a moment to start
        import time
        time.sleep(0.1)

        # Get status
        response = client.get(f"/api/agent/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["status"] in ("running", "succeeded")

    def test_returns_404_for_nonexistent_run(self, client):
        """Unknown run_id returns 404."""
        response = client.get("/api/agent/runs/nonexistent-run-id")
        assert response.status_code == 404


# =============================================================================
# POST /api/agent/runs/{id}/cancel Tests
# =============================================================================


class TestCancelAgentRun:
    """Tests for POST /api/agent/runs/{id}/cancel."""

    def test_returns_404_for_nonexistent_run(self, client):
        """Cannot cancel nonexistent run."""
        response = client.post("/api/agent/runs/nonexistent-run-id/cancel")
        assert response.status_code == 404

    def test_cancels_active_run(self, client):
        """Can cancel an active run."""
        # Create a run with a slow engine to ensure it's still active
        with patch(
            "orchestrator.routes.agent_runs._run_agent_task",
            new=AsyncMock(side_effect=asyncio.sleep(10)),
        ):
            # Manually add to active runs
            run_id = "test-cancel-run"
            queue = asyncio.Queue()
            agent_runs_module._active_runs[run_id] = queue
            agent_runs_module._abort_signals[run_id] = asyncio.Event()

            response = client.post(f"/api/agent/runs/{run_id}/cancel")
            assert response.status_code == 200
            data = response.json()
            assert data["run_id"] == run_id
            assert data["status"] == "cancelled"


# =============================================================================
# GET /api/agent/runs/{id}/trace Tests
# =============================================================================


class TestGetAgentRunTrace:
    """Tests for GET /api/agent/runs/{id}/trace."""

    def test_returns_404_for_nonexistent_run(self, client):
        """Unknown run_id returns 404."""
        response = client.get("/api/agent/runs/nonexistent-run-id/trace")
        assert response.status_code == 404

    def test_returns_trace_for_created_run(self, client):
        """Created run has trace data."""
        # Create a run
        create_resp = client.post(
            "/api/agent/runs",
            json={"query": "Test query"},
        )
        run_id = create_resp.json()["run_id"]

        # Give it time to complete
        import time
        time.sleep(0.3)

        # Get trace
        response = client.get(f"/api/agent/runs/{run_id}/trace")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert "steps" in data
        assert "tool_calls" in data
        assert "citations" in data


# =============================================================================
# SSE Event Translation Tests
# =============================================================================


class TestSSEEventTranslation:
    """Tests for SSE event translation."""

    def test_translate_event_adds_seq_and_timestamp(self):
        """Translation adds sequence number and timestamp."""
        from orchestrator.routes.agent_runs import _translate_event

        event = {"type": "thinking", "content": "Testing..."}
        result = _translate_event(event, seq=5)

        assert result["event"] == "thinking"
        data = json.loads(result["data"])
        assert data["seq"] == 5
        assert "timestamp" in data
        assert data["content"] == "Testing..."

    def test_translate_event_maps_types(self):
        """Event types are mapped correctly."""
        from orchestrator.routes.agent_runs import _translate_event

        test_cases = [
            ("agent_started", "agent_state"),
            ("step_started", "step_start"),
            ("thinking", "thinking"),
            ("tool_start", "tool_start"),
            ("tool_result", "tool_result"),
            ("synthesizing", "agent_state"),
            ("answer_token", "answer"),
            ("agent_complete", "complete"),
            ("agent_error", "error"),
        ]

        for engine_type, expected_sse_type in test_cases:
            event = {"type": engine_type}
            result = _translate_event(event, seq=1)
            assert result["event"] == expected_sse_type


# =============================================================================
# Module State Tests
# =============================================================================


class TestModuleState:
    """Tests for module-level state management."""

    def test_cleanup_removes_run_state(self):
        """Cleanup removes run from active_runs."""
        import asyncio

        run_id = "cleanup-test-run"
        agent_runs_module._active_runs[run_id] = asyncio.Queue()
        agent_runs_module._abort_signals[run_id] = asyncio.Event()

        # Run cleanup with no delay
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(agent_runs_module._cleanup_run(run_id, delay_seconds=0))
        loop.close()

        assert run_id not in agent_runs_module._active_runs
        assert run_id not in agent_runs_module._abort_signals

    @pytest.mark.asyncio
    async def test_restore_event_history_from_db(self, test_db):
        """Persisted run events can be restored after memory cleanup."""
        from orchestrator.storage.repositories.agent_repo import AgentRepo
        from orchestrator.storage.repositories.conversation_repo import ConversationRepo
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        run_id = "restore-events-run"
        await ConversationRepo(test_db).create("restore-events-conv", title="restore")
        await TraceRepo(test_db).create_run(
            run_id=run_id,
            conversation_id="restore-events-conv",
            profile_name="agent",
            mode="agent",
            model_config={},
            user_message="restore",
        )
        repo = AgentRepo(test_db)
        await repo.create_run_event(
            run_id=run_id,
            seq=1,
            event_type="thinking",
            event_data={"type": "thinking", "content": "hello"},
        )

        agent_runs_module._event_history.pop(run_id, None)
        restored = await agent_runs_module._restore_event_history_from_db(run_id)

        assert restored == 1
        assert agent_runs_module._event_history[run_id][0]["seq"] == 1
        assert agent_runs_module._event_history[run_id][0]["content"] == "hello"


# =============================================================================
# Factory Tests
# =============================================================================


class TestAgentFactory:
    """Tests for create_agent_engine factory."""

    @pytest.mark.asyncio
    async def test_factory_creates_engine(self, test_db):
        """Factory creates an AgentEngine instance."""
        from orchestrator.agent import create_agent_engine

        # Mock the dependencies
        mock_provider = MagicMock()
        mock_registry = MagicMock()
        mock_registry.tool_names = ["web_search"]

        with patch("orchestrator.agent.factory.create_provider", return_value=mock_provider):
            with patch("orchestrator.agent.factory.create_tool_registry", return_value=mock_registry):
                engine = await create_agent_engine(max_steps=5)

                assert engine is not None
                assert engine._max_steps == 5

    @pytest.mark.asyncio
    async def test_factory_uses_config_defaults(self, test_db):
        """Factory uses config values when no overrides provided."""
        from orchestrator.agent import create_agent_engine

        mock_provider = MagicMock()
        mock_registry = MagicMock()
        mock_registry.tool_names = []

        with patch("orchestrator.agent.factory.create_provider", return_value=mock_provider):
            with patch("orchestrator.agent.factory.create_tool_registry", return_value=mock_registry):
                engine = await create_agent_engine()

                assert engine is not None
                # Default max_steps is 10
                assert engine._max_steps == 10
