"""Database connection management."""

from pathlib import Path
from typing import Optional
import aiosqlite
from orchestrator.config import DB_PATH

# Read schema from file
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Initialize database connection and create schema."""
        # Handle in-memory database (for tests) vs file-based
        if isinstance(self.db_path, str) and self.db_path == ":memory:":
            self._connection = await aiosqlite.connect(":memory:")
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")

        # Apply strict schema
        if SCHEMA_PATH.exists():
            schema_sql = SCHEMA_PATH.read_text()
            await self._connection.executescript(schema_sql)

        # Run migrations for schema changes
        await self._run_migrations()

        await self._connection.commit()

    async def _run_migrations(self) -> None:
        """Run schema migrations for existing databases."""
        # Migration 1: Add thinking_summary column to runs table
        await self._add_column_if_not_exists("runs", "thinking_summary", "TEXT")
        # Migration 2: Add last_response_id for stateful mode
        await self._add_column_if_not_exists("runs", "last_response_id", "TEXT")
        # Migration 3: Agent columns on runs table
        await self._add_column_if_not_exists("runs", "agent_state", "TEXT")
        await self._add_column_if_not_exists("runs", "current_step", "INTEGER DEFAULT 0")
        await self._add_column_if_not_exists("runs", "max_steps", "INTEGER DEFAULT 10")
        await self._add_column_if_not_exists("runs", "updated_at", "TEXT")
        # Migration 4: Session scoping for demo mode user isolation
        await self._add_column_if_not_exists("conversations", "session_id", "TEXT")
        await self._add_column_if_not_exists("runs", "session_id", "TEXT")
        # Migration 5: ChatGPT OAuth token storage
        await self._create_table_if_not_exists(
            "chatgpt_tokens",
            """
            CREATE TABLE IF NOT EXISTS chatgpt_tokens (
                session_id TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                account_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """,
        )
        # Migration 6: Observability — approval audit trail + full tool results
        await self._add_column_if_not_exists("agent_tool_calls", "approval_decision", "TEXT")
        await self._add_column_if_not_exists("agent_tool_calls", "approval_policy", "TEXT")
        await self._add_column_if_not_exists("agent_tool_calls", "approval_decided_at", "TEXT")
        await self._add_column_if_not_exists("agent_tool_calls", "result_detail", "TEXT")
        # Migration 7: Observability — updated_at timestamps
        await self._add_column_if_not_exists("conversations", "updated_at", "TEXT")
        await self._add_column_if_not_exists("agent_steps", "updated_at", "TEXT")
        # Migration 8: Observability — SSE event persistence
        await self._create_table_if_not_exists(
            "run_events",
            """
            CREATE TABLE IF NOT EXISTS run_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """,
        )
        # Migration 9: Observability — file change tracking
        await self._create_table_if_not_exists(
            "run_artifacts",
            """
            CREATE TABLE IF NOT EXISTS run_artifacts (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                file_path TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                tool_call_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
                FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE
            )
            """,
        )

    async def _create_table_if_not_exists(
        self, table: str, create_sql: str
    ) -> None:
        """Create a table if it doesn't already exist.

        Args:
            table: Table name (for logging).
            create_sql: Full CREATE TABLE IF NOT EXISTS statement.
        """
        await self._connection.execute(create_sql)

    async def _add_column_if_not_exists(
        self, table: str, column: str, column_type: str
    ) -> None:
        """Add a column to a table if it doesn't already exist."""
        cursor = await self._connection.execute(f"PRAGMA table_info({table})")
        columns = await cursor.fetchall()
        column_names = [col["name"] for col in columns]

        if column not in column_names:
            await self._connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
            )

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

# Singleton instance
_db: Optional[Database] = None

async def get_db() -> Database:
    """Get the database singleton."""
    global _db
    if _db is None:
        _db = Database()
        await _db.connect()
    return _db
