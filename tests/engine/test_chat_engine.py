"""Tests for ChatEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.engine.chat_engine import ChatEngine


class TestBuildMessages:
    """Tests for _build_messages method."""

    def test_conversation_history_included_in_provider_request(self):
        """Verify prior conversation turns are included in next provider request.

        This test ensures that:
        1. Messages are built from runs table (user_message + final_answer pairs)
        2. Prior turns are included in order
        3. System message comes first, then history, then current message
        """
        # Create engine with mock config
        with patch("orchestrator.engine.chat_engine.get_chat_config") as mock_config:
            mock_config.return_value = MagicMock(
                system_prompt="You are a helpful assistant.",
                context=MagicMock(max_messages=50),
                provider=MagicMock(
                    base_url="http://localhost:1234",
                    api_key=None,
                    endpoint="responses",
                    fallback_on_404=True,
                    timeout=120.0,
                ),
                model=MagicMock(
                    name="test-model",
                    temperature=0.7,
                    max_tokens=4096,
                ),
                thinking=MagicMock(cot=MagicMock(thinking_budget=512, answer_budget=256)),
                tracing=MagicMock(log_level="info"),
                endpoint="responses",
            )
            with patch("orchestrator.engine.chat_engine.create_provider"):
                engine = ChatEngine()

        # Simulate prior runs from database (runs table format)
        prior_runs = [
            {
                "run_id": "run-1",
                "conversation_id": "conv-1",
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "Hello!",
                "final_answer": "Hi there! How can I help you today?",
                "status": "succeeded",
            },
            {
                "run_id": "run-2",
                "conversation_id": "conv-1",
                "created_at": "2024-01-01T10:01:00Z",
                "user_message": "What is 2+2?",
                "final_answer": "2+2 equals 4.",
                "status": "succeeded",
            },
        ]

        current_message = "Thanks! Now what is 3+3?"

        # Build messages
        messages = engine._build_messages(prior_runs, current_message)

        # Verify message structure
        assert len(messages) == 6  # system + 2 user + 2 assistant + current

        # Check order: system, user1, assistant1, user2, assistant2, current
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert messages[1] == {"role": "user", "content": "Hello!"}
        assert messages[2] == {"role": "assistant", "content": "Hi there! How can I help you today?"}
        assert messages[3] == {"role": "user", "content": "What is 2+2?"}
        assert messages[4] == {"role": "assistant", "content": "2+2 equals 4."}
        assert messages[5] == {"role": "user", "content": "Thanks! Now what is 3+3?"}

    def test_empty_history_only_has_system_and_current(self):
        """Verify first message in conversation has system + current only."""
        with patch("orchestrator.engine.chat_engine.get_chat_config") as mock_config:
            mock_config.return_value = MagicMock(
                system_prompt="System prompt here.",
                context=MagicMock(max_messages=50),
                provider=MagicMock(
                    base_url="http://localhost:1234",
                    api_key=None,
                    endpoint="responses",
                    fallback_on_404=True,
                    timeout=120.0,
                ),
                model=MagicMock(),
                thinking=MagicMock(cot=MagicMock()),
                tracing=MagicMock(log_level="info"),
                endpoint="responses",
            )
            with patch("orchestrator.engine.chat_engine.create_provider"):
                engine = ChatEngine()

        prior_runs = []  # No history
        current_message = "First message"

        messages = engine._build_messages(prior_runs, current_message)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "First message"}

    def test_sliding_window_respects_max_messages(self):
        """Verify sliding window truncates old messages."""
        with patch("orchestrator.engine.chat_engine.get_chat_config") as mock_config:
            mock_config.return_value = MagicMock(
                system_prompt="System",
                context=MagicMock(max_messages=2),  # Only keep 2 recent turns
                provider=MagicMock(
                    base_url="http://localhost:1234",
                    api_key=None,
                    endpoint="responses",
                    fallback_on_404=True,
                    timeout=120.0,
                ),
                model=MagicMock(),
                thinking=MagicMock(cot=MagicMock()),
                tracing=MagicMock(log_level="info"),
                endpoint="responses",
            )
            with patch("orchestrator.engine.chat_engine.create_provider"):
                engine = ChatEngine()

        # Create 5 prior runs
        prior_runs = [
            {"created_at": f"2024-01-01T10:0{i}:00Z", "user_message": f"msg{i}", "final_answer": f"resp{i}"}
            for i in range(5)
        ]

        messages = engine._build_messages(prior_runs, "current")

        # Should have: system + 2 turns (4 messages) + current = 6
        # But with max_messages=2, we keep only last 2 runs
        assert len(messages) == 6  # system + 2*2 + current
        # Verify we have the LAST 2 runs (msg3, msg4)
        assert messages[1]["content"] == "msg3"
        assert messages[3]["content"] == "msg4"

    def test_skips_runs_without_final_answer(self):
        """Verify incomplete runs (no final_answer) are handled gracefully."""
        with patch("orchestrator.engine.chat_engine.get_chat_config") as mock_config:
            mock_config.return_value = MagicMock(
                system_prompt="System",
                context=MagicMock(max_messages=50),
                provider=MagicMock(
                    base_url="http://localhost:1234",
                    api_key=None,
                    endpoint="responses",
                    fallback_on_404=True,
                    timeout=120.0,
                ),
                model=MagicMock(),
                thinking=MagicMock(cot=MagicMock()),
                tracing=MagicMock(log_level="info"),
                endpoint="responses",
            )
            with patch("orchestrator.engine.chat_engine.create_provider"):
                engine = ChatEngine()

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "Complete message",
                "final_answer": "Complete response",
            },
            {
                "created_at": "2024-01-01T10:01:00Z",
                "user_message": "Failed message",
                "final_answer": None,  # No response (failed run)
            },
        ]

        messages = engine._build_messages(prior_runs, "current")

        # Should have: system + complete pair + incomplete user only + current
        # The None final_answer should be skipped
        assert len(messages) == 5
        assert messages[1]["content"] == "Complete message"
        assert messages[2]["content"] == "Complete response"
        assert messages[3]["content"] == "Failed message"
        assert messages[4]["content"] == "current"


class TestStatefulMode:
    """Tests for stateful conversation chaining via previous_response_id."""

    @pytest.mark.asyncio
    async def test_get_latest_response_id_filters_succeeded_only(self):
        """Verify only succeeded runs are considered for chaining."""
        from orchestrator.storage.db import Database
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        # Create a conversation
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )

        # Create runs with different statuses
        # Run 1: succeeded with response_id
        await repo.create_run(
            run_id="run-1",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="First",
        )
        await repo.update_run("run-1", status="succeeded", last_response_id="resp-1")

        # Run 2: failed (no response_id)
        await repo.create_run(
            run_id="run-2",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="Second",
        )
        await repo.update_run("run-2", status="failed")

        # Run 3: running (no response_id)
        await repo.create_run(
            run_id="run-3",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="Third",
        )
        # Don't update - stays as "running"

        # Get latest response_id - should be from run-1 (only succeeded)
        latest = await repo.get_latest_response_id("conv-1")
        assert latest == "resp-1"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_latest_response_id_returns_most_recent(self):
        """Verify the most recent succeeded run's response_id is returned."""
        from orchestrator.storage.db import Database
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )

        # Create multiple succeeded runs
        await repo.create_run(
            run_id="run-1",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="First",
        )
        await repo.update_run("run-1", status="succeeded", last_response_id="resp-1")

        await repo.create_run(
            run_id="run-2",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="Second",
        )
        await repo.update_run("run-2", status="succeeded", last_response_id="resp-2")

        # Should return resp-2 (most recent)
        latest = await repo.get_latest_response_id("conv-1")
        assert latest == "resp-2"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_latest_response_id_returns_none_when_no_succeeded(self):
        """Verify None is returned when no succeeded runs exist."""
        from orchestrator.storage.db import Database
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )

        # Create only failed runs
        await repo.create_run(
            run_id="run-1",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
        )
        await repo.update_run("run-1", status="failed")

        latest = await repo.get_latest_response_id("conv-1")
        assert latest is None

        await db.close()

    @pytest.mark.asyncio
    async def test_update_run_stores_last_response_id(self):
        """Verify last_response_id is stored correctly."""
        from orchestrator.storage.db import Database
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )

        await repo.create_run(
            run_id="run-1",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
        )

        # Update with last_response_id
        await repo.update_run(
            "run-1",
            status="succeeded",
            final_answer="Test answer",
            last_response_id="resp-abc-123",
        )

        # Verify it's stored
        async with db.conn.execute(
            "SELECT last_response_id FROM runs WHERE run_id = ?", ("run-1",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row[0] == "resp-abc-123"

        await db.close()
