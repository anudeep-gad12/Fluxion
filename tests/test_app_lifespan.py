"""Tests for app lifespan behavior, particularly orphaned run cleanup."""

import pytest
from unittest.mock import patch
from datetime import datetime, timezone

from orchestrator.app import RESTART_INTERRUPTED_MESSAGE, cleanup_orphaned_runs_on_startup
from orchestrator.storage.db import Database
import orchestrator.storage.db as db_module


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

    yield database

    # Cleanup
    loop.run_until_complete(database.close())
    db_module._db = None


@pytest.fixture
def mock_get_db(test_db):
    """Mock get_db to return test database."""
    async def _get_db():
        return test_db

    with patch("orchestrator.storage.db.get_db", _get_db):
        with patch("orchestrator.app.get_db", _get_db):
            yield test_db


class TestOrphanedRunCleanup:
    """Tests for orphaned run cleanup on server startup."""

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_runs_on_startup(self, test_db):
        """Orphaned runs (status='running') should be marked as interrupted on startup."""
        # Create some orphaned runs
        now = datetime.now(timezone.utc).isoformat()
        await test_db.conn.execute(
            """
            INSERT INTO runs (run_id, created_at, profile_name, mode, model_config_snapshot, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("orphan-1", now, "test", "agent", "{}", "running"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO runs (run_id, created_at, profile_name, mode, model_config_snapshot, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("orphan-2", now, "test", "agent", "{}", "running"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO runs (run_id, created_at, profile_name, mode, model_config_snapshot, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("completed-1", now, "test", "chat", "{}", "succeeded"),
        )
        await test_db.conn.commit()

        # Verify we have 2 running, 1 succeeded
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        assert row[0] == 2

        counts = await cleanup_orphaned_runs_on_startup(test_db)
        assert counts["orphaned_runs"] == 2
        assert counts["terminal_events"] == 2

        # Verify orphaned runs are now interrupted
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        assert row[0] == 0

        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'interrupted'"
        )
        row = await cursor.fetchone()
        assert row[0] == 2

        # Verify succeeded run is unchanged
        cursor = await test_db.conn.execute(
            "SELECT status FROM runs WHERE run_id = 'completed-1'"
        )
        row = await cursor.fetchone()
        assert row[0] == "succeeded"

        # Verify error message is set
        cursor = await test_db.conn.execute(
            "SELECT error_message FROM runs WHERE run_id = 'orphan-1'"
        )
        row = await cursor.fetchone()
        assert row[0] == RESTART_INTERRUPTED_MESSAGE

        cursor = await test_db.conn.execute(
            "SELECT event_type, event_data FROM run_events WHERE run_id = 'orphan-1'"
        )
        row = await cursor.fetchone()
        assert row[0] == "_STREAM_END"
        assert '"status": "interrupted"' in row[1]

    @pytest.mark.asyncio
    async def test_no_orphaned_runs_no_error(self, test_db):
        """When there are no orphaned runs, cleanup should do nothing."""
        # Create only completed runs
        now = datetime.now(timezone.utc).isoformat()
        await test_db.conn.execute(
            """
            INSERT INTO runs (run_id, created_at, profile_name, mode, model_config_snapshot, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("completed-1", now, "test", "chat", "{}", "succeeded"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO runs (run_id, created_at, profile_name, mode, model_config_snapshot, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("failed-1", now, "test", "chat", "{}", "failed"),
        )
        await test_db.conn.commit()

        counts = await cleanup_orphaned_runs_on_startup(test_db)
        assert counts["orphaned_runs"] == 0
        assert counts["terminal_events"] == 0

        # Verify no changes to existing runs
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'succeeded'"
        )
        row = await cursor.fetchone()
        assert row[0] == 1

        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'failed'"
        )
        row = await cursor.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_empty_database_no_error(self, test_db):
        """Cleanup should work fine on empty database."""
        counts = await cleanup_orphaned_runs_on_startup(test_db)
        assert counts["orphaned_runs"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_tool_calls_and_steps(self, test_db):
        """Orphaned tool calls and steps should also be cleaned up."""
        now = datetime.now(timezone.utc).isoformat()

        # Create an orphaned run
        await test_db.conn.execute(
            """
            INSERT INTO runs (run_id, created_at, profile_name, mode, model_config_snapshot, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("orphan-run", now, "test", "agent", "{}", "running"),
        )

        # Create orphaned agent_steps
        await test_db.conn.execute(
            """
            INSERT INTO agent_steps (id, run_id, step_number, created_at, state)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("step-1", "orphan-run", 1, now, "tool_calling"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO agent_steps (id, run_id, step_number, created_at, state)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("step-2", "orphan-run", 2, now, "planning"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO agent_steps (id, run_id, step_number, created_at, state)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("step-3", "orphan-run", 3, now, "complete"),
        )

        # Create orphaned agent_tool_calls
        await test_db.conn.execute(
            """
            INSERT INTO agent_tool_calls (id, run_id, step_id, created_at, tool_name, arguments, status, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("tc-1", "orphan-run", "step-1", now, "web_search", "{}", "running", "key-1"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO agent_tool_calls (id, run_id, step_id, created_at, tool_name, arguments, status, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("tc-2", "orphan-run", "step-1", now, "python_execute", "{}", "pending", "key-2"),
        )
        await test_db.conn.execute(
            """
            INSERT INTO agent_tool_calls (id, run_id, step_id, created_at, tool_name, arguments, status, idempotency_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("tc-3", "orphan-run", "step-3", now, "web_extract", "{}", "success", "key-3"),
        )
        await test_db.conn.commit()

        counts = await cleanup_orphaned_runs_on_startup(test_db)
        assert counts["orphaned_runs"] == 1
        assert counts["orphaned_tool_calls"] == 2
        assert counts["orphaned_steps"] == 2
        assert counts["terminal_events"] == 1

        # Verify run is interrupted
        cursor = await test_db.conn.execute(
            "SELECT status FROM runs WHERE run_id = 'orphan-run'"
        )
        row = await cursor.fetchone()
        assert row[0] == "interrupted"

        # Verify tool calls are interrupted (running/pending) or unchanged (success)
        cursor = await test_db.conn.execute(
            "SELECT status FROM agent_tool_calls WHERE id = 'tc-1'"
        )
        row = await cursor.fetchone()
        assert row[0] == "interrupted"

        cursor = await test_db.conn.execute(
            "SELECT status FROM agent_tool_calls WHERE id = 'tc-2'"
        )
        row = await cursor.fetchone()
        assert row[0] == "interrupted"

        cursor = await test_db.conn.execute(
            "SELECT status FROM agent_tool_calls WHERE id = 'tc-3'"
        )
        row = await cursor.fetchone()
        assert row[0] == "success"  # Should be unchanged

        # Verify steps are error (tool_calling/planning) or unchanged (complete)
        cursor = await test_db.conn.execute(
            "SELECT state FROM agent_steps WHERE id = 'step-1'"
        )
        row = await cursor.fetchone()
        assert row[0] == "error"

        cursor = await test_db.conn.execute(
            "SELECT state FROM agent_steps WHERE id = 'step-2'"
        )
        row = await cursor.fetchone()
        assert row[0] == "error"

        cursor = await test_db.conn.execute(
            "SELECT state FROM agent_steps WHERE id = 'step-3'"
        )
        row = await cursor.fetchone()
        assert row[0] == "complete"  # Should be unchanged
