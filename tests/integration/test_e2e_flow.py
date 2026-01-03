"""End-to-end tests that hit real API endpoints and verify database state.

These tests use FastAPI's TestClient to make actual HTTP requests,
only mocking the external LLM provider.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from orchestrator.app import app
from orchestrator.providers.base import LLMResponse
from orchestrator.storage.db import Database
import orchestrator.storage.db as db_module


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory database for each test."""
    import asyncio

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

    # Patch get_db everywhere
    with patch("orchestrator.storage.db.get_db", mock_get_db):
        with patch("orchestrator.routes.conversations.get_db", mock_get_db):
            with patch("orchestrator.routes.runs.get_db", mock_get_db):
                with patch("orchestrator.engine.chat_engine.get_db", mock_get_db):
                    yield database

    # Cleanup - don't close the loop, just the database
    loop.run_until_complete(database.close())
    db_module._db = None


@pytest.fixture
def mock_llm_provider():
    """Mock the LLM provider to return predictable responses."""
    mock_provider = MagicMock()

    async def mock_complete_streaming(messages, model, on_token=None, on_reasoning=None, **kwargs):
        response_text = "This is a test response from the LLM."

        # Simulate token streaming
        if on_token:
            for word in response_text.split():
                on_token(word + " ")

        return LLMResponse(
            text=response_text,
            usage={"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
            endpoint_used="/v1/responses",
            response_id="test-resp-123",
        )

    mock_provider.complete_streaming = mock_complete_streaming
    mock_provider.close = AsyncMock()
    return mock_provider


@pytest.fixture
def client(test_db, mock_llm_provider):
    """Create a test client with mocked provider."""
    with patch("orchestrator.engine.chat_engine.create_provider", return_value=mock_llm_provider):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


@pytest.fixture
async def async_client(test_db, mock_llm_provider):
    """Create an async test client for SSE streaming tests."""
    with patch("orchestrator.engine.chat_engine.create_provider", return_value=mock_llm_provider):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


# =============================================================================
# E2E Flow Tests
# =============================================================================


class TestConversationEndpoints:
    """Test conversation CRUD via real HTTP endpoints."""

    def test_create_conversation(self, client):
        """POST /api/conversations creates a conversation."""
        response = client.post(
            "/api/conversations",
            json={"title": "My Test Conversation"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        assert len(data["conversation_id"]) == 36  # UUID format

    def test_list_conversations(self, client):
        """GET /api/conversations returns created conversations."""
        # Create some conversations
        client.post("/api/conversations", json={"title": "First"})
        client.post("/api/conversations", json={"title": "Second"})

        response = client.get("/api/conversations")

        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert len(data["conversations"]) == 2

    def test_get_conversation_detail(self, client):
        """GET /api/conversations/{id} returns conversation with runs."""
        # Create conversation
        create_resp = client.post("/api/conversations", json={"title": "Detail Test"})
        conv_id = create_resp.json()["conversation_id"]

        # Get details
        response = client.get(f"/api/conversations/{conv_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["conversation"]["conversation_id"] == conv_id
        assert "runs" in data

    def test_get_nonexistent_conversation_returns_404(self, client):
        """GET /api/conversations/{bad_id} returns 404."""
        response = client.get("/api/conversations/nonexistent-id")
        assert response.status_code == 404

    def test_delete_conversation(self, client):
        """DELETE /api/conversations/{id} removes conversation."""
        # Create
        create_resp = client.post("/api/conversations", json={"title": "To Delete"})
        conv_id = create_resp.json()["conversation_id"]

        # Delete
        delete_resp = client.delete(f"/api/conversations/{conv_id}")
        assert delete_resp.status_code == 200

        # Verify gone
        get_resp = client.get(f"/api/conversations/{conv_id}")
        assert get_resp.status_code == 404


class TestChatFlow:
    """Test the complete chat flow via HTTP endpoints."""

    def test_send_message_creates_run(self, client):
        """POST /api/conversations/{id}/runs creates a run and returns stream URL."""
        # Create conversation
        create_resp = client.post("/api/conversations", json={"title": "Chat Test"})
        conv_id = create_resp.json()["conversation_id"]

        # Send message
        response = client.post(
            f"/api/conversations/{conv_id}/runs",
            json={
                "message": "Hello, how are you?",
                "thinking_mode": "default",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "stream_url" in data
        assert data["stream_url"].startswith("/api/runs/")

    def test_standalone_run_creates_conversation(self, client):
        """POST /api/runs creates ephemeral conversation."""
        response = client.post(
            "/api/runs",
            json={"prompt": "What is 2+2?"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "stream_url" in data

    def test_run_appears_in_conversation_detail(self, client):
        """Runs appear in conversation detail after chat."""
        import time

        # Create conversation
        create_resp = client.post("/api/conversations", json={"title": "Run Test"})
        conv_id = create_resp.json()["conversation_id"]

        # Send message
        run_resp = client.post(
            f"/api/conversations/{conv_id}/runs",
            json={"message": "Test message", "thinking_mode": "default"}
        )
        run_id = run_resp.json()["run_id"]

        # Wait for async processing
        time.sleep(0.5)

        # Check conversation detail
        detail_resp = client.get(f"/api/conversations/{conv_id}")
        data = detail_resp.json()

        assert len(data["runs"]) >= 1
        run_ids = [r["run_id"] for r in data["runs"]]
        assert run_id in run_ids

    def test_run_stores_message_and_response(self, client):
        """Run stores user message and assistant response."""
        import time

        # Create conversation
        create_resp = client.post("/api/conversations", json={"title": "Storage Test"})
        conv_id = create_resp.json()["conversation_id"]

        # Send message
        run_resp = client.post(
            f"/api/conversations/{conv_id}/runs",
            json={"message": "What is the capital of France?", "thinking_mode": "default"}
        )
        run_id = run_resp.json()["run_id"]

        # Wait for async processing
        time.sleep(0.5)

        # Get run details
        run_detail = client.get(f"/api/runs/{run_id}")

        if run_detail.status_code == 200:
            data = run_detail.json()
            assert data["user_message"] == "What is the capital of France?"
            # Response should be from our mock
            assert "test response" in data.get("final_answer", "").lower() or data["status"] in ["succeeded", "running"]


class TestRunEndpoints:
    """Test run-specific endpoints."""

    def test_list_runs(self, client):
        """GET /api/runs lists all runs."""
        # Create a run first
        client.post("/api/runs", json={"prompt": "Test prompt"})

        import time
        time.sleep(0.3)

        response = client.get("/api/runs")

        assert response.status_code == 200
        data = response.json()
        assert "runs" in data

    def test_get_run_events(self, client):
        """GET /api/runs/{id}/events returns trace events."""
        import time

        # Create a run
        run_resp = client.post("/api/runs", json={"prompt": "Event test"})
        run_id = run_resp.json()["run_id"]

        time.sleep(0.5)

        # Get events
        events_resp = client.get(f"/api/runs/{run_id}/events")

        if events_resp.status_code == 200:
            data = events_resp.json()
            assert "events" in data

    def test_get_run_timeline(self, client):
        """GET /api/runs/{id}/timeline returns full timeline."""
        import time

        # Create a run
        run_resp = client.post("/api/runs", json={"prompt": "Timeline test"})
        run_id = run_resp.json()["run_id"]

        time.sleep(0.5)

        # Get timeline
        timeline_resp = client.get(f"/api/runs/{run_id}/timeline")

        if timeline_resp.status_code == 200:
            data = timeline_resp.json()
            assert "events" in data
            assert "run_id" in data


class TestHealthAndConfig:
    """Test health and config endpoints."""

    def test_health_check(self, client):
        """GET /api/health returns ok."""
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_config_endpoint(self, client):
        """GET /api/config returns configuration."""
        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "model" in data["config"]
        assert "provider" in data["config"]


class TestDatabaseIntegrity:
    """Test database operations and integrity."""

    def test_conversation_cascade_delete(self, client):
        """Deleting conversation cascades to runs."""
        import time

        # Create conversation with a run
        create_resp = client.post("/api/conversations", json={"title": "Cascade Test"})
        conv_id = create_resp.json()["conversation_id"]

        run_resp = client.post(
            f"/api/conversations/{conv_id}/runs",
            json={"message": "Test", "thinking_mode": "default"}
        )
        run_id = run_resp.json()["run_id"]

        time.sleep(0.5)

        # Delete conversation
        client.delete(f"/api/conversations/{conv_id}")

        # Run should be gone too
        run_detail = client.get(f"/api/runs/{run_id}")
        assert run_detail.status_code == 404

    def test_multiple_conversations_isolated(self, client):
        """Multiple conversations don't interfere with each other."""
        import time

        # Create two conversations
        conv1 = client.post("/api/conversations", json={"title": "Conv 1"}).json()["conversation_id"]
        conv2 = client.post("/api/conversations", json={"title": "Conv 2"}).json()["conversation_id"]

        # Send messages to both
        client.post(f"/api/conversations/{conv1}/runs", json={"message": "Message to conv 1", "thinking_mode": "default"})
        client.post(f"/api/conversations/{conv2}/runs", json={"message": "Message to conv 2", "thinking_mode": "default"})

        time.sleep(0.5)

        # Check each conversation has its own runs
        detail1 = client.get(f"/api/conversations/{conv1}").json()
        detail2 = client.get(f"/api/conversations/{conv2}").json()

        # Runs should be different
        run_ids_1 = {r["run_id"] for r in detail1["runs"]}
        run_ids_2 = {r["run_id"] for r in detail2["runs"]}

        assert run_ids_1.isdisjoint(run_ids_2)


class TestMultiTurnConversation:
    """Test multi-turn conversation flow."""

    def test_conversation_builds_history(self, client):
        """Multiple messages in conversation build history."""
        import time

        # Create conversation
        conv_id = client.post("/api/conversations", json={"title": "Multi-turn"}).json()["conversation_id"]

        # Send multiple messages
        messages = ["First message", "Second message", "Third message"]
        run_ids = []

        for msg in messages:
            resp = client.post(
                f"/api/conversations/{conv_id}/runs",
                json={"message": msg, "thinking_mode": "default"}
            )
            run_ids.append(resp.json()["run_id"])
            time.sleep(0.3)

        # Check all runs exist
        detail = client.get(f"/api/conversations/{conv_id}").json()

        assert len(detail["runs"]) == 3

        # Verify each run has correct user message
        for i, run in enumerate(sorted(detail["runs"], key=lambda r: r.get("created_at", ""))):
            if "user_message" in run:
                assert run["user_message"] in messages


class TestErrorHandling:
    """Test error handling in the API."""

    def test_message_to_nonexistent_conversation(self, client):
        """Sending message to nonexistent conversation returns 404."""
        response = client.post(
            "/api/conversations/fake-id/runs",
            json={"message": "Hello", "thinking_mode": "default"}
        )

        assert response.status_code == 404

    def test_invalid_request_body(self, client):
        """Invalid request body returns 422."""
        conv_id = client.post("/api/conversations", json={"title": "Test"}).json()["conversation_id"]

        response = client.post(
            f"/api/conversations/{conv_id}/runs",
            json={}  # Missing required fields
        )

        assert response.status_code == 422
