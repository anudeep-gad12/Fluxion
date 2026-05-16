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
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


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
        with patch("orchestrator.app.get_db", mock_get_db):
            with patch("orchestrator.routes.conversations.get_db", mock_get_db):
                with patch("orchestrator.routes.runs.get_db", mock_get_db):
                    with patch("orchestrator.routes.agent_runs.get_db", mock_get_db):
                        with patch("orchestrator.engine.chat_engine.get_db", mock_get_db):
                            with patch("orchestrator.agent.factory.get_db", mock_get_db):
                                with patch("orchestrator.services.reasoning_settings.get_db", mock_get_db):
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
    agent_runs_module._run_sessions.clear()
    agent_runs_module._approval_queues.clear()

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
    agent_runs_module._run_sessions.clear()
    agent_runs_module._approval_queues.clear()


@pytest.fixture
async def async_client(test_db, mock_agent_engine):
    """Create an async test client for SSE streaming tests."""
    # Clear module state before each test
    agent_runs_module._active_runs.clear()
    agent_runs_module._abort_signals.clear()
    agent_runs_module._event_history.clear()
    agent_runs_module._run_tokens.clear()
    agent_runs_module._run_sessions.clear()
    agent_runs_module._approval_queues.clear()

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
    agent_runs_module._run_sessions.clear()
    agent_runs_module._approval_queues.clear()


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

    def test_existing_new_conversation_is_retitled_from_first_agent_message(
        self,
        client,
        test_db,
    ):
        """Existing placeholder-titled conversations should auto-title on first agent run."""
        conv_resp = client.post(
            "/api/conversations",
            json={"title": "New conversation"},
        )
        assert conv_resp.status_code == 200
        conversation_id = conv_resp.json()["conversation_id"]

        response = client.post(
            "/api/agent/runs",
            json={
                "query": "   fix    the   broken workspace title handling   ",
                "conversation_id": conversation_id,
            },
        )

        async def fetch_conversation_title() -> str | None:
            repo = ConversationRepo(test_db)
            conversation = await repo.get(conversation_id)
            return conversation.get("title") if conversation else None

        loop = asyncio.get_event_loop()
        updated_title = loop.run_until_complete(fetch_conversation_title())

        assert response.status_code == 200
        assert updated_title == "Fix the broken workspace title handling"

    def test_standalone_agent_run_uses_normalized_conversation_title(self, client, test_db):
        """Ephemeral agent conversations should use the normalized first query as title."""
        response = client.post(
            "/api/agent/runs",
            json={
                "query": "   explain    why   the   workspace   cards look cramped   ",
            },
        )
        assert response.status_code == 200

        run_id = response.json()["run_id"]

        async def fetch_title() -> str | None:
            async with test_db.conn.execute(
                "SELECT conversation_id FROM runs WHERE run_id = ?",
                (run_id,),
            ) as cursor:
                row = await cursor.fetchone()
            conversation_id = row["conversation_id"] if row else None
            if not conversation_id:
                return None
            repo = ConversationRepo(test_db)
            conversation = await repo.get(conversation_id)
            return conversation.get("title") if conversation else None

        loop = asyncio.get_event_loop()
        title = loop.run_until_complete(fetch_title())
        assert title == "Issue: The workspace cards too cramped"

    def test_existing_conversation_workspace_overrides_request_workspace(self, test_db, tmp_path):
        """Workspace-bound conversations ignore mismatched request workspace paths."""
        mock_engine = MagicMock()
        mock_engine._context_profile_dict.return_value = {
            "provider_name": "test",
            "model_id": "test-model",
            "display_name": "Test Model",
            "context_window": 1000,
            "max_output_tokens": 100,
            "effective_input_budget": 900,
            "supports_tools": True,
            "supports_reasoning": False,
            "pricing": {},
            "source": "test",
        }

        async def mock_run(run_id, query, event_callback=None, conversation_id=None):
            return AgentResult(
                run_id=run_id,
                success=True,
                final_answer="done",
                citations=[],
                total_steps=1,
                error_message=None,
                timing_ms=10,
            )

        mock_engine.run = mock_run

        captured_kwargs = {}

        async def mock_create_engine(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_engine

        with patch("orchestrator.agent.factory.create_agent_engine", mock_create_engine):
            with TestClient(app, raise_server_exceptions=False) as client:
                conv_resp = client.post(
                    "/api/conversations",
                    json={"title": "Workspace", "workspace_path": str(tmp_path)},
                )
                conv_id = conv_resp.json()["conversation_id"]

                response = client.post(
                    "/api/agent/runs",
                    json={
                        "query": "Test query",
                        "conversation_id": conv_id,
                        "workspace_path": "/var",
                        "filesystem_enabled": True,
                    },
                )

        import time
        time.sleep(0.05)

        assert response.status_code == 200
        assert captured_kwargs["working_dir"] == str(tmp_path.resolve())


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
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)

        # Create a run with a slow engine to ensure it's still active
        with patch(
            "orchestrator.routes.agent_runs._run_agent_task",
            new=AsyncMock(side_effect=slow_run),
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


class TestRunAgentTaskFailureHandling:
    """Tests for background run failure persistence."""

    async def _seed_run(self, test_db: Database, run_id: str) -> None:
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        conversation_id = f"{run_id}-conv"
        await ConversationRepo(test_db).create(
            conversation_id=conversation_id,
            title="failure handling",
        )
        await TraceRepo(test_db).create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            profile_name="agent",
            mode="agent",
            model_config={},
            user_message="failure handling",
        )

    def _mock_engine(self, run_impl):
        engine = MagicMock()
        engine._context_profile_dict.return_value = {
            "provider_name": "test",
            "model_id": "test-model",
            "display_name": "Test Model",
            "context_window": 1000,
            "max_output_tokens": 100,
            "effective_input_budget": 900,
            "supports_tools": True,
            "supports_reasoning": False,
            "pricing": {},
            "source": "test",
        }
        engine.run = run_impl
        return engine

    @pytest.mark.asyncio
    async def test_cancelled_error_marks_running_run_failed(self, test_db):
        """Background task CancelledError is persisted instead of orphaning the run."""
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        run_id = "cancelled-background-run"
        await self._seed_run(test_db, run_id)

        async def cancelled_run(*args, **kwargs):
            raise asyncio.CancelledError()

        async def create_engine(**kwargs):
            return self._mock_engine(cancelled_run)

        async def cleanup_now(*args, **kwargs):
            return None

        agent_runs_module._active_runs[run_id] = True
        agent_runs_module._abort_signals[run_id] = asyncio.Event()
        agent_runs_module._event_history[run_id] = []
        agent_runs_module._event_notify[run_id] = asyncio.Event()

        with patch("orchestrator.agent.factory.create_agent_engine", create_engine):
            with patch("orchestrator.routes.agent_runs._cleanup_run", cleanup_now):
                await agent_runs_module._run_agent_task(
                    run_id=run_id,
                    query="trigger cancellation",
                    conversation_id=f"{run_id}-conv",
                    max_steps=10,
                )

        run = await TraceRepo(test_db).get_run(run_id)
        assert run is not None
        assert run["status"] == "failed"
        assert "CancelledError" in run["error_message"]
        assert agent_runs_module._event_history[run_id][-1]["type"] == "_STREAM_ERROR"
        assert "CancelledError" in agent_runs_module._event_history[run_id][-1]["error"]

    @pytest.mark.asyncio
    async def test_failed_agent_result_streams_error_message(self, test_db):
        """A failure result includes its error in the terminal stream event."""
        run_id = "failed-result-run"
        await self._seed_run(test_db, run_id)

        async def failed_run(*args, **kwargs):
            return AgentResult(
                run_id=run_id,
                success=False,
                final_answer=None,
                citations=[],
                total_steps=1,
                error_message="provider exploded",
                timing_ms=10,
            )

        async def create_engine(**kwargs):
            return self._mock_engine(failed_run)

        async def cleanup_now(*args, **kwargs):
            return None

        agent_runs_module._active_runs[run_id] = True
        agent_runs_module._abort_signals[run_id] = asyncio.Event()
        agent_runs_module._event_history[run_id] = []
        agent_runs_module._event_notify[run_id] = asyncio.Event()

        with patch("orchestrator.agent.factory.create_agent_engine", create_engine):
            with patch("orchestrator.routes.agent_runs._cleanup_run", cleanup_now):
                await agent_runs_module._run_agent_task(
                    run_id=run_id,
                    query="trigger failure result",
                    conversation_id=f"{run_id}-conv",
                    max_steps=10,
                )

        end_event = agent_runs_module._event_history[run_id][-1]
        assert end_event["type"] == "_STREAM_END"
        assert end_event["result"]["success"] is False
        assert end_event["result"]["error_message"] == "provider exploded"


# =============================================================================
# Tool Approval Tests
# =============================================================================


class TestToolApprovals:
    """Tests for approve/deny endpoints."""

    SESSION_HEADERS = {"x-cli-session": "approval-session"}

    def test_approve_pending_future(self, client):
        """A pending approval future is resolved."""
        run_id = "approval-run"
        tool_call_id = "approval-tool"
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        agent_runs_module._approval_queues[run_id] = {tool_call_id: future}

        response = client.post(f"/api/agent/runs/{run_id}/approve/{tool_call_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "approved"
        assert future.done()
        assert future.result() is True

    def test_deny_pending_future(self, client):
        """A pending denial future is resolved."""
        run_id = "approval-run"
        tool_call_id = "approval-tool"
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        agent_runs_module._approval_queues[run_id] = {tool_call_id: future}

        response = client.post(f"/api/agent/runs/{run_id}/deny/{tool_call_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "denied"
        assert future.done()
        assert future.result() is False

    def test_duplicate_approve_returns_existing_decision(self, client, test_db):
        """A repeated approve after persistence is idempotent."""
        loop = asyncio.get_event_loop()
        run_id = "approval-run"
        tool_call_id = loop.run_until_complete(
            self._seed_tool_call(test_db, run_id, "approved", "running", "approval-session")
        )

        response = client.post(
            f"/api/agent/runs/{run_id}/approve/{tool_call_id}",
            headers=self.SESSION_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    def test_duplicate_deny_returns_existing_decision(self, client, test_db):
        """A repeated deny after persistence is idempotent."""
        loop = asyncio.get_event_loop()
        run_id = "approval-run"
        tool_call_id = loop.run_until_complete(
            self._seed_tool_call(test_db, run_id, "denied", "running", "approval-session")
        )

        response = client.post(
            f"/api/agent/runs/{run_id}/deny/{tool_call_id}",
            headers=self.SESSION_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "denied"

    def test_stale_approval_on_failed_run_returns_conflict(self, client, test_db):
        """A stale approval after run failure returns explicit conflict."""
        loop = asyncio.get_event_loop()
        run_id = "approval-run"
        tool_call_id = loop.run_until_complete(
            self._seed_tool_call(test_db, run_id, None, "failed", "approval-session")
        )

        response = client.post(
            f"/api/agent/runs/{run_id}/approve/{tool_call_id}",
            headers=self.SESSION_HEADERS,
        )

        assert response.status_code == 409, response.json()
        assert "already failed" in response.json()["detail"]

    async def _seed_tool_call(
        self,
        db: Database,
        run_id: str,
        approval_decision: str | None,
        run_status: str,
        session_id: str,
    ) -> str:
        from orchestrator.storage.repositories.agent_repo import AgentRepo
        from orchestrator.storage.repositories.conversation_repo import ConversationRepo
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        conversation_id = f"{run_id}-conv"
        await ConversationRepo(db).create(conversation_id=conversation_id, title="approval")
        await TraceRepo(db).create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            profile_name="agent",
            mode="agent",
            model_config={},
            user_message="approval",
            session_id=session_id,
        )
        await TraceRepo(db).update_run(run_id, status=run_status)
        agent_repo = AgentRepo(db)
        step = await agent_repo.create_step(run_id, 1, "tool_calling")
        tool_call = await agent_repo.create_tool_call(
            run_id=run_id,
            step_id=step["id"],
            tool_name="bash",
            arguments={"command": "echo hi"},
            idempotency_key=f"{run_id}-tool",
        )
        if approval_decision is not None:
            await agent_repo.update_tool_call(
                tool_call["id"],
                approval_decision=approval_decision,
                approval_policy="strict",
            )
        return tool_call["id"]


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

    def test_trace_maps_edit_result_detail_to_result_data(self, client, test_db):
        """Historical trace payloads expose edit_file diffs for the browser UI."""
        loop = asyncio.get_event_loop()
        diff = "--- a/app.py\n+++ b/app.py\n-old\n+new\n"

        async def seed_run() -> str:
            run_id = "trace-edit-diff-run"
            await ConversationRepo(test_db).create("trace-edit-diff-conv", title="trace")
            await TraceRepo(test_db).create_run(
                run_id=run_id,
                conversation_id="trace-edit-diff-conv",
                profile_name="agent",
                mode="agent",
                model_config={},
                user_message="edit file",
                session_id="trace-session",
            )
            agent_repo = AgentRepo(test_db)
            step = await agent_repo.create_step(run_id, 1, "tool_calling")
            tool_call = await agent_repo.create_tool_call(
                run_id=run_id,
                step_id=step["id"],
                tool_name="edit_file",
                arguments={"file_path": "app.py"},
                idempotency_key="trace-edit-diff-tool",
            )
            await agent_repo.update_tool_call(
                tool_call["id"],
                status="success",
                result_summary="Edited app.py",
                result_detail=json.dumps({"file_path": "app.py", "diff": diff}),
            )
            return run_id

        run_id = loop.run_until_complete(seed_run())

        response = client.get(
            f"/api/agent/runs/{run_id}/trace",
            headers={"x-cli-session": "trace-session"},
        )

        assert response.status_code == 200
        tool_call = response.json()["tool_calls"][0]
        assert tool_call["tool_name"] == "edit_file"
        assert tool_call["result_data"] == diff


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
            with patch(
                "orchestrator.agent.factory.create_browser_agent_tool_registry",
                return_value=mock_registry,
            ):
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
            with patch(
                "orchestrator.agent.factory.create_browser_agent_tool_registry",
                return_value=mock_registry,
            ):
                engine = await create_agent_engine()

                assert engine is not None
                assert engine._max_steps == 1000

    @pytest.mark.asyncio
    async def test_factory_prefers_provider_override_model_name(self, test_db):
        """Factory should use the active override model identity instead of stale config names."""
        from orchestrator.agent import create_agent_engine

        mock_provider = MagicMock()
        mock_provider._context_profile_model_id = "Qwen3.6-35B-A3B-Q4_K_M"
        mock_provider._default_model = None
        mock_registry = MagicMock()
        mock_registry.tool_names = []

        with patch("orchestrator.agent.factory.create_provider", return_value=MagicMock()):
            with patch(
                "orchestrator.agent.factory.create_browser_agent_tool_registry",
                return_value=mock_registry,
            ):
                engine = await create_agent_engine(provider_override=mock_provider, filesystem_enabled=True)

                assert engine is not None
                assert engine._model_name == "Qwen3.6-35B-A3B-Q4_K_M"

    async def test_factory_uses_coding_profile_max_steps(self, test_db):
        """Factory uses coding profile max_steps when filesystem mode is enabled."""
        from orchestrator.agent import create_agent_engine

        mock_provider = MagicMock()
        mock_registry = MagicMock()
        mock_registry.tool_names = []

        with patch("orchestrator.agent.factory.create_provider", return_value=mock_provider):
            with patch(
                "orchestrator.agent.factory.create_browser_agent_tool_registry",
                return_value=mock_registry,
            ):
                engine = await create_agent_engine(filesystem_enabled=True)

                assert engine is not None
                assert engine._max_steps == 1000
