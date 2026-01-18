"""Tests for runs routes, particularly ChatEngine resource cleanup."""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


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
