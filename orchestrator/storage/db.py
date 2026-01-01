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
