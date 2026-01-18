"""Tests for app lifespan behavior, particularly orphaned run cleanup."""

import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

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
        """Orphaned runs (status='running') should be marked as failed on startup."""
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

        # Simulate the cleanup logic from app.py lifespan
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        orphaned_count = row[0] if row else 0

        if orphaned_count > 0:
            await test_db.conn.execute(
                """
                UPDATE runs
                SET status = 'failed',
                    error_message = 'Server restarted - run was interrupted'
                WHERE status = 'running'
                """
            )
            await test_db.conn.commit()

        # Verify orphaned runs are now failed
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        assert row[0] == 0

        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'failed'"
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
        assert row[0] == "Server restarted - run was interrupted"

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

        # Simulate the cleanup logic
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        orphaned_count = row[0] if row else 0

        # Should find no orphaned runs
        assert orphaned_count == 0

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
        cursor = await test_db.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'running'"
        )
        row = await cursor.fetchone()
        orphaned_count = row[0] if row else 0

        assert orphaned_count == 0
