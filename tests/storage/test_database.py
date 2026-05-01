"""Tests for database connection and schema management."""

import sqlite3
import pytest
from pathlib import Path
from orchestrator.storage.db import Database


@pytest.fixture
async def in_memory_db():
    """Create an in-memory database for testing."""
    db = Database(":memory:")
    await db.connect()
    yield db
    await db.close()


class TestDatabase:
    """Tests for Database class."""

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, in_memory_db):
        """Connect creates required tables from schema."""
        db = in_memory_db

        # Check conversations table exists
        cursor = await db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
        )
        row = await cursor.fetchone()
        assert row is not None

        # Check runs table exists
        cursor = await db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
        )
        row = await cursor.fetchone()
        assert row is not None

        # Check trace_events table exists
        cursor = await db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trace_events'"
        )
        row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_foreign_keys_enabled(self, in_memory_db):
        """Foreign keys are enabled."""
        db = in_memory_db
        cursor = await db.conn.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
        assert row[0] == 1

    @pytest.mark.asyncio
    async def test_migrations_add_columns(self, in_memory_db):
        """Migrations add required columns."""
        db = in_memory_db

        # Check thinking_summary column exists
        cursor = await db.conn.execute("PRAGMA table_info(runs)")
        columns = await cursor.fetchall()
        column_names = [col["name"] for col in columns]

        assert "thinking_summary" in column_names
        assert "last_response_id" in column_names

    @pytest.mark.asyncio
    async def test_conn_property_raises_when_not_connected(self):
        """conn property raises when not connected."""
        db = Database(":memory:")  # Don't connect

        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = db.conn

    @pytest.mark.asyncio
    async def test_close_clears_connection(self, in_memory_db):
        """Close clears the connection."""
        db = in_memory_db
        await db.close()

        with pytest.raises(RuntimeError, match="Database not connected"):
            _ = db.conn

    @pytest.mark.asyncio
    async def test_row_factory_returns_dict_like(self, in_memory_db):
        """Row factory returns dict-accessible rows."""
        db = in_memory_db

        # Insert test data
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, created_at, status) VALUES (?, ?, ?)",
            ("test-id", "2024-01-01T00:00:00Z", "active"),
        )
        await db.conn.commit()

        # Query and access by name
        cursor = await db.conn.execute(
            "SELECT conversation_id, status FROM conversations WHERE conversation_id = ?",
            ("test-id",),
        )
        row = await cursor.fetchone()

        assert row["conversation_id"] == "test-id"
        assert row["status"] == "active"

    @pytest.mark.asyncio
    async def test_connect_migrates_workspace_path_on_existing_database(self, tmp_path: Path):
        """Connect migrates legacy databases before creating workspace index."""
        db_path = tmp_path / "legacy.sqlite"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE conversations (
                conversation_id TEXT PRIMARY KEY,
                title TEXT,
                summary TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT
            );
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                conversation_id TEXT,
                created_at TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                mode TEXT NOT NULL,
                model_config_snapshot TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
            );
            CREATE INDEX idx_conversations_created_at ON conversations(created_at);
            """
        )
        conn.commit()
        conn.close()

        db = Database(db_path)
        await db.connect()

        cursor = await db.conn.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        column_names = [col["name"] for col in columns]
        assert "workspace_path" in column_names

        cursor = await db.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index' AND name = 'idx_conversations_workspace_path'
            """
        )
        row = await cursor.fetchone()
        assert row is not None

        await db.close()
