"""Integration tests for the complete chat flow.

These tests exercise the full path from API request through chat engine,
provider, storage, and back - mocking only the external LLM API.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.config import ChatConfig, ProviderConfig, ChatModelConfig
from orchestrator.engine.chat_engine import ChatEngine
from orchestrator.providers.base import LLMResponse
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_db():
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return ChatConfig(
        provider=ProviderConfig(
            base_url="http://test:1234",
            api_key="test-key",
            endpoint="responses",
            timeout=10.0,
        ),
        model=ChatModelConfig(
            name="test-model",
            temperature=0.7,
            max_tokens=1000,
        ),
        system_prompt="You are a test assistant.",
    )


def create_mock_provider(response_text="Hello! How can I help?", reasoning=None):
    """Create a mock provider that returns specified response."""
    mock_provider = MagicMock()

    async def mock_complete_streaming(
        messages, model, on_token=None, on_reasoning=None, **kwargs
    ):
        # Simulate streaming tokens
        if on_token:
            for word in response_text.split():
                on_token(word + " ")

        # Simulate reasoning if provided
        if reasoning and on_reasoning:
            on_reasoning(reasoning)

        return LLMResponse(
            text=response_text,
            reasoning=reasoning,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            endpoint_used="/v1/responses",
            response_id="resp-123",
        )

    mock_provider.complete_streaming = mock_complete_streaming
    mock_provider.close = AsyncMock()
    return mock_provider


# =============================================================================
# Full Flow Tests
# =============================================================================


class TestChatFlow:
    """Tests for the complete chat flow."""

    @pytest.mark.asyncio
    async def test_complete_chat_flow(self, test_db, test_config):
        """Test complete flow: create conversation -> send message -> get response -> verify traces."""
        # Setup repos
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)

        # 1. Create conversation
        conv = await conv_repo.create(
            conversation_id="test-conv-1",
            title="Test Conversation",
        )
        assert conv["conversation_id"] == "test-conv-1"

        # 2. Mock the provider and create engine
        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Hello! How can I help?")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)

                # 3. Collect streaming events
                events = []

                def event_callback(event):
                    events.append(event)

                # 4. Send message
                result = await engine.chat(
                    conversation_id="test-conv-1",
                    message="Hi there!",
                    event_callback=event_callback,
                )

        # 5. Verify result
        assert result.status == "succeeded"
        assert result.conversation_id == "test-conv-1"
        assert result.message == "Hi there!"
        assert "Hello" in result.response

        # 6. Verify events were emitted
        event_types = [e["type"] for e in events]
        assert "CHAT_STARTED" in event_types
        assert "CHAT_COMPLETED" in event_types

        # 7. Verify traces were stored
        runs = await trace_repo.list_runs_for_conversation("test-conv-1")
        assert len(runs) >= 1
        assert runs[0]["conversation_id"] == "test-conv-1"
        assert runs[0]["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_conversation_not_found(self, test_db, test_config):
        """Test chat fails gracefully when conversation doesn't exist."""
        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider()

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)

                result = await engine.chat(
                    conversation_id="nonexistent",
                    message="Hello",
                )

        assert result.status == "failed"
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, test_db, test_config):
        """Test multiple messages in a conversation."""
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)

        # Create conversation
        await conv_repo.create(conversation_id="multi-turn")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Response")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)

                # First message
                result1 = await engine.chat(
                    conversation_id="multi-turn",
                    message="First message",
                )
                assert result1.status == "succeeded"

                # Second message
                result2 = await engine.chat(
                    conversation_id="multi-turn",
                    message="Second message",
                )
                assert result2.status == "succeeded"

        # Verify both runs are stored
        runs = await trace_repo.list_runs_for_conversation("multi-turn")
        assert len(runs) == 2


class TestEventEmission:
    """Tests for event emission during chat."""

    @pytest.mark.asyncio
    async def test_chat_started_event(self, test_db, test_config):
        """Verify CHAT_STARTED event is emitted."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="event-test")

        events = []

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Hi")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                await engine.chat(
                    conversation_id="event-test",
                    message="Test",
                    event_callback=lambda e: events.append(e),
                )

        # First event should be CHAT_STARTED
        assert events[0]["type"] == "CHAT_STARTED"
        assert "run_id" in events[0]
        assert events[0]["conversation_id"] == "event-test"

    @pytest.mark.asyncio
    async def test_token_events_streamed(self, test_db, test_config):
        """Verify TOKEN events are streamed during response."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="token-test")

        events = []

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Token1 Token2 Token3")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                await engine.chat(
                    conversation_id="token-test",
                    message="Test",
                    event_callback=lambda e: events.append(e),
                )

        # Should have TOKEN events (tokens go to TOKEN after StreamParser processes)
        token_events = [e for e in events if e["type"] == "TOKEN"]
        assert len(token_events) > 0

    @pytest.mark.asyncio
    async def test_thinking_token_events(self, test_db, test_config):
        """Verify THINKING_TOKEN events for native reasoning."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="thinking-test")

        events = []

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider(
                "Answer here", reasoning="Let me think about this..."
            )

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                await engine.chat(
                    conversation_id="thinking-test",
                    message="Complex problem",
                    event_callback=lambda e: events.append(e),
                    reasoning_effort="medium",
                )

        # Should have THINKING_TOKEN events from native reasoning callback
        thinking_events = [e for e in events if e["type"] == "THINKING_TOKEN"]
        assert len(thinking_events) > 0

    @pytest.mark.asyncio
    async def test_chat_completed_event(self, test_db, test_config):
        """Verify CHAT_COMPLETED event is emitted at end."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="complete-test")

        events = []

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Done")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                await engine.chat(
                    conversation_id="complete-test",
                    message="Test",
                    event_callback=lambda e: events.append(e),
                )

        # Last meaningful event should be CHAT_COMPLETED
        assert any(e["type"] == "CHAT_COMPLETED" for e in events)
        completed = [e for e in events if e["type"] == "CHAT_COMPLETED"][0]
        assert "response" in completed
        assert completed["response"] == "Done"


class TestTraceStorage:
    """Tests for trace storage during chat."""

    @pytest.mark.asyncio
    async def test_run_created_with_status(self, test_db, test_config):
        """Verify run is created with proper status."""
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)
        await conv_repo.create(conversation_id="trace-test")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Response")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="trace-test",
                    message="Test message",
                )

        # Verify run status
        run = await trace_repo.get_run(result.run_id)
        assert run is not None
        assert run["status"] == "succeeded"
        assert run["conversation_id"] == "trace-test"

    @pytest.mark.asyncio
    async def test_trace_events_logged(self, test_db, test_config):
        """Verify trace events are logged during chat."""
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)
        await conv_repo.create(conversation_id="event-log-test")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Hi")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="event-log-test",
                    message="Hello",
                )

        # Verify trace events exist
        events = await trace_repo.get_trace_events(result.run_id)
        assert len(events) > 0

        # Should have llm_request event
        event_types = [e["event_type"] for e in events]
        assert "llm_request" in event_types

    @pytest.mark.asyncio
    async def test_run_stores_user_message(self, test_db, test_config):
        """Verify user message is stored in run."""
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)
        await conv_repo.create(conversation_id="msg-test")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("Reply")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="msg-test",
                    message="My original message",
                )

        run = await trace_repo.get_run(result.run_id)
        assert run["user_message"] == "My original message"
        assert run["final_answer"] == "Reply"


class TestConfigIntegration:
    """Tests for config integration with chat engine."""

    @pytest.mark.asyncio
    async def test_system_prompt_from_config(self, test_db, test_config):
        """Verify system prompt from config is used."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="prompt-test")

        messages_received = []

        def capture_provider(response_text):
            mock = MagicMock()

            async def mock_complete(messages, model, **kwargs):
                messages_received.extend(messages)
                return LLMResponse(
                    text=response_text,
                    usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
                    endpoint_used="/v1/responses",
                )

            mock.complete_streaming = mock_complete
            mock.close = AsyncMock()
            return mock

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = capture_provider("OK")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                await engine.chat(
                    conversation_id="prompt-test",
                    message="Test",
                )

        # System prompt should be in messages
        assert any(m["role"] == "system" for m in messages_received)
        system_msg = [m for m in messages_received if m["role"] == "system"][0]
        assert system_msg["content"] == "You are a test assistant."


class TestThinkingOrchestrator:
    """Tests for thinking orchestrator integration."""

    @pytest.mark.asyncio
    async def test_direct_strategy_used_by_default(self, test_db, test_config):
        """Verify DirectStrategy is used by default."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="strategy-test")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("OK")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)

                # Default strategy should be "direct"
                assert engine.thinking_orchestrator.default_strategy == "direct"

                result = await engine.chat(
                    conversation_id="strategy-test",
                    message="Test",
                )

        assert result.status == "succeeded"


class TestConversationManagement:
    """Tests for conversation CRUD through the flow."""

    @pytest.mark.asyncio
    async def test_conversation_history_loaded(self, test_db, test_config):
        """Verify conversation history is loaded for context."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="history-test")

        messages_from_second_call = []

        def capture_provider():
            mock = MagicMock()
            call_count = [0]

            async def mock_complete(messages, model, on_token=None, **kwargs):
                call_count[0] += 1
                if call_count[0] == 2:
                    messages_from_second_call.extend(messages)

                if on_token:
                    on_token("Response ")

                return LLMResponse(
                    text="Response",
                    usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
                    endpoint_used="/v1/responses",
                )

            mock.complete_streaming = mock_complete
            mock.close = AsyncMock()
            return mock

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = capture_provider()

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)

                # First message
                await engine.chat(
                    conversation_id="history-test",
                    message="First message",
                )

                # Second message should include history
                await engine.chat(
                    conversation_id="history-test",
                    message="Second message",
                )

        # Second call should have prior history
        assert len(messages_from_second_call) >= 3  # system + first exchange + second user
        roles = [m["role"] for m in messages_from_second_call]
        assert "system" in roles
        assert roles.count("user") >= 2  # At least first + second message

    @pytest.mark.asyncio
    async def test_cascade_delete_cleans_traces(self, test_db, test_config):
        """Verify deleting conversation cascades to runs."""
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)
        await conv_repo.create(conversation_id="cascade-test")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("OK")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="cascade-test",
                    message="Test",
                )

        run_id = result.run_id

        # Verify run exists
        run = await trace_repo.get_run(run_id)
        assert run is not None

        # Delete conversation
        await conv_repo.delete("cascade-test")

        # Run should be gone (cascade delete)
        run = await trace_repo.get_run(run_id)
        assert run is None


class TestErrorHandling:
    """Tests for error handling in the chat flow."""

    @pytest.mark.asyncio
    async def test_provider_error_handled(self, test_db, test_config):
        """Verify provider errors are handled gracefully."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="error-test")

        mock_provider = MagicMock()

        async def raise_error(*args, **kwargs):
            raise Exception("Provider connection failed")

        mock_provider.complete_streaming = raise_error
        mock_provider.close = AsyncMock()

        events = []

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = mock_provider

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="error-test",
                    message="Test",
                    event_callback=lambda e: events.append(e),
                )

        # Should fail gracefully
        assert result.status == "failed"
        assert "Provider connection failed" in result.error

        # Should emit CHAT_FAILED event
        assert any(e["type"] == "CHAT_FAILED" for e in events)

    @pytest.mark.asyncio
    async def test_failed_run_stored_in_trace(self, test_db, test_config):
        """Verify failed runs are stored in trace."""
        conv_repo = ConversationRepo(test_db)
        trace_repo = TraceRepo(test_db)
        await conv_repo.create(conversation_id="fail-trace-test")

        mock_provider = MagicMock()

        async def raise_error(*args, **kwargs):
            raise Exception("API Error")

        mock_provider.complete_streaming = raise_error
        mock_provider.close = AsyncMock()

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = mock_provider

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="fail-trace-test",
                    message="Test",
                )

        # Run should be stored with failed status
        run = await trace_repo.get_run(result.run_id)
        assert run is not None
        assert run["status"] == "failed"


class TestUsageTracking:
    """Tests for token usage tracking."""

    @pytest.mark.asyncio
    async def test_usage_returned_in_result(self, test_db, test_config):
        """Verify token usage is returned in chat result."""
        conv_repo = ConversationRepo(test_db)
        await conv_repo.create(conversation_id="usage-test")

        with patch("orchestrator.engine.chat_engine.create_provider") as mock_create:
            mock_create.return_value = create_mock_provider("OK")

            with patch("orchestrator.engine.chat_engine.get_db", return_value=test_db):
                engine = ChatEngine(test_config)
                result = await engine.chat(
                    conversation_id="usage-test",
                    message="Test",
                )

        assert result.status == "succeeded"
        assert result.token_usage is not None
        assert "total_tokens" in result.token_usage
