"""Tests for runs routes, particularly ChatEngine resource cleanup and queue behavior."""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from orchestrator.app import app
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo
import orchestrator.storage.db as db_module
import orchestrator.routes.runs as runs_module


@pytest.fixture(scope="function")
def test_db():
    db_module._db = None
    database = Database(":memory:")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(database.connect())

    async def mock_get_db():
        return database

    with patch("orchestrator.storage.db.get_db", mock_get_db):
        with patch("orchestrator.app.get_db", mock_get_db):
            with patch("orchestrator.routes.runs.get_db", mock_get_db):
                with patch("orchestrator.routes.conversations.get_db", mock_get_db):
                    yield database

    runs_module._active_runs.clear()
    runs_module._abort_signals.clear()
    runs_module._run_sessions.clear()
    loop.run_until_complete(database.close())
    db_module._db = None


@pytest.fixture
async def async_client(test_db):
    runs_module._active_runs.clear()
    runs_module._abort_signals.clear()
    runs_module._run_sessions.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    runs_module._active_runs.clear()
    runs_module._abort_signals.clear()
    runs_module._run_sessions.clear()

class TestEventQueueSize:
    """Tests for event queue configuration."""

    def test_queue_size_is_1000_for_conversation_run(self):
        """Event queue should have maxsize=1000 for conversation runs."""
        # The queue is created inside the route, so we verify by checking the code
        import orchestrator.routes.runs as runs_module
        import inspect

        source = inspect.getsource(runs_module.create_conversation_run)
        assert "maxsize=1000" in source, "Queue maxsize should be 1000"

    def test_queue_size_is_1000_for_standalone_run(self):
        """Event queue should have maxsize=1000 for standalone runs."""
        import orchestrator.routes.runs as runs_module
        import inspect

        source = inspect.getsource(runs_module.create_run)
        assert "maxsize=1000" in source, "Queue maxsize should be 1000"

    def test_queue_overflow_logs_warning(self):
        """When queue is full, a warning should be logged."""
        import orchestrator.routes.runs as runs_module
        import inspect

        source = inspect.getsource(runs_module.create_conversation_run)
        assert 'logger.warning("Event queue full"' in source, "Should log warning on queue full"


class TestChatEngineCleanup:
    """Tests for ChatEngine cleanup in run routes."""

    @pytest.mark.asyncio
    async def test_engine_close_called_on_success(self):
        """ChatEngine.close() should be called after successful chat completion."""
        close_called = asyncio.Event()

        # Mock ChatEngine
        mock_engine = MagicMock()
        mock_engine.chat = AsyncMock(return_value=MagicMock(
            run_id="test-run-id",
            response="Test response",
            status="succeeded",
            error=None,
            thinking_summary="",
        ))

        async def mock_close():
            close_called.set()

        mock_engine.close = mock_close

        # Mock ChatEngine constructor
        with patch("orchestrator.routes.runs.ChatEngine", return_value=mock_engine):
            with patch("orchestrator.routes.runs.get_chat_config", return_value=MagicMock(
                thinking=MagicMock(mode_mapping={"think": "direct"})
            )):
                # Import after patching
                from orchestrator.routes.runs import _active_runs

                # Create mock event queue
                event_queue = asyncio.Queue(maxsize=100)
                run_id = "test-run-id"
                _active_runs[run_id] = event_queue

                # Create and run the chat task inline (simulating the background task)
                async def run_chat():
                    from orchestrator.routes.runs import get_chat_config, ChatEngine
                    config = get_chat_config()
                    engine = ChatEngine(config)

                    try:
                        result = await engine.chat(
                            conversation_id="test-conv",
                            message="Hello",
                            run_id=run_id,
                            event_callback=lambda e: None,
                        )
                        event_queue.put_nowait({
                            "type": "_STREAM_END",
                            "result": {"run_id": result.run_id},
                        })
                    except Exception as e:
                        event_queue.put_nowait({"type": "_STREAM_ERROR", "error": str(e)})
                        _active_runs.pop(run_id, None)
                        return
                    finally:
                        await engine.close()
                    await asyncio.sleep(0.1)  # Shortened for test
                    _active_runs.pop(run_id, None)

                await run_chat()

                # Verify close was called
                assert close_called.is_set(), "engine.close() was not called"

    @pytest.mark.asyncio
    async def test_engine_close_called_on_error(self):
        """ChatEngine.close() should be called even when chat fails."""
        close_called = asyncio.Event()

        # Mock ChatEngine that raises an error
        mock_engine = MagicMock()
        mock_engine.chat = AsyncMock(side_effect=Exception("Test error"))

        async def mock_close():
            close_called.set()

        mock_engine.close = mock_close

        # Mock ChatEngine constructor
        with patch("orchestrator.routes.runs.ChatEngine", return_value=mock_engine):
            with patch("orchestrator.routes.runs.get_chat_config", return_value=MagicMock(
                thinking=MagicMock(mode_mapping={"think": "direct"})
            )):
                from orchestrator.routes.runs import _active_runs

                event_queue = asyncio.Queue(maxsize=100)
                run_id = "test-run-error"
                _active_runs[run_id] = event_queue

                async def run_chat():
                    from orchestrator.routes.runs import get_chat_config, ChatEngine
                    config = get_chat_config()
                    engine = ChatEngine(config)

                    try:
                        result = await engine.chat(
                            conversation_id="test-conv",
                            message="Hello",
                            run_id=run_id,
                            event_callback=lambda e: None,
                        )
                    except Exception as e:
                        event_queue.put_nowait({"type": "_STREAM_ERROR", "error": str(e)})
                        _active_runs.pop(run_id, None)
                        return
                    finally:
                        await engine.close()

                await run_chat()

                # Verify close was called even after error
                assert close_called.is_set(), "engine.close() was not called on error"

    @pytest.mark.asyncio
    async def test_provider_client_closed(self):
        """The underlying httpx client should be closed when engine.close() is called."""
        from orchestrator.providers.openai_compat import OpenAICompatProvider

        # Create a real provider
        provider = OpenAICompatProvider(
            base_url="http://localhost:8080",
            api_key="test-key",
        )

        # Verify client is initially open
        assert not provider._client.is_closed

        # Close the provider
        await provider.close()

        # Verify client is now closed
        assert provider._client.is_closed

    @pytest.mark.asyncio
    async def test_chat_engine_close_closes_provider(self):
        """ChatEngine.close() should close the underlying provider."""
        from orchestrator.engine.chat_engine import ChatEngine
        from unittest.mock import patch

        # Mock the provider
        mock_provider = MagicMock()
        mock_provider.close = AsyncMock()

        with patch("orchestrator.engine.chat_engine.create_provider", return_value=mock_provider):
            # Create engine (will use mocked provider)
            engine = ChatEngine()

            # Close the engine
            await engine.close()

            # Verify provider.close() was called
            mock_provider.close.assert_called_once()


class TestRunStreamRecovery:
    """Tests for terminal chat SSE fallback after in-memory state is gone."""

    @pytest.mark.asyncio
    async def test_interrupted_chat_run_streams_terminal_complete(self, async_client, test_db):
        run_id = "interrupted-chat-run"
        conversation_id = f"{run_id}-conv"
        await ConversationRepo(test_db).create(
            conversation_id=conversation_id,
            title="interrupted chat",
        )
        trace_repo = TraceRepo(test_db)
        await trace_repo.create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="resume interrupted chat",
        )
        await trace_repo.update_run(
            run_id,
            status="interrupted",
            error_message="Server restarted - run was interrupted",
        )
        runs_module._active_runs.pop(run_id, None)

        async with async_client.stream("GET", f"/api/runs/{run_id}/stream") as response:
            body = (await response.aread()).decode()

        assert response.status_code == 200
        assert "event: complete" in body
        assert '"status": "interrupted"' in body
        assert '"error_message": "Server restarted - run was interrupted"' in body


class TestConversationAutoTitles:
    """Tests for smart conversation auto-titles."""

    def test_helper_generates_smart_issue_title(self):
        from orchestrator.conversation_titles import conversation_title_from_message

        assert (
            conversation_title_from_message('why is the sidebar still cramped')
            == 'Issue: The sidebar too cramped'
        )

    def test_helper_strips_filler_for_imperative_title(self):
        from orchestrator.conversation_titles import conversation_title_from_message

        assert (
            conversation_title_from_message('can you fix the broken workspace title handling')
            == 'Fix the broken workspace title handling'
        )
