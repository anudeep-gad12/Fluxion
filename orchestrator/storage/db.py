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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        
        # Apply strict schema
        if SCHEMA_PATH.exists():
            schema_sql = SCHEMA_PATH.read_text()
            await self._connection.executescript(schema_sql)
        
        await self._connection.commit()

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
