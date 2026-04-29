"""Repository for browser terminal session metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator.storage.db import Database


class TerminalSessionRepo:
    """CRUD helper for persisted browser terminal session metadata."""

    def __init__(self, db: Database):
        self.db = db

    async def get_by_conversation(self, conversation_id: str) -> Optional[dict[str, Any]]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM terminal_sessions WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_by_session_id(self, session_id: str) -> Optional[dict[str, Any]]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM terminal_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def upsert(
        self,
        *,
        session_id: str,
        conversation_id: str,
        workspace_path: str | None,
        shell: str,
        status: str,
        cols: int,
        rows: int,
        session_owner: str | None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.conn.execute(
            """
            INSERT INTO terminal_sessions (
                session_id, conversation_id, workspace_path, shell, status,
                cols, rows, session_owner, created_at, updated_at, last_activity_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                session_id = excluded.session_id,
                workspace_path = excluded.workspace_path,
                shell = excluded.shell,
                status = excluded.status,
                cols = excluded.cols,
                rows = excluded.rows,
                session_owner = excluded.session_owner,
                updated_at = excluded.updated_at,
                last_activity_at = excluded.last_activity_at
            """,
            (
                session_id,
                conversation_id,
                workspace_path,
                shell,
                status,
                cols,
                rows,
                session_owner,
                now,
                now,
                now,
            ),
        )
        await self.db.conn.commit()
        return {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "workspace_path": workspace_path,
            "shell": shell,
            "status": status,
            "cols": cols,
            "rows": rows,
            "session_owner": session_owner,
            "created_at": now,
            "updated_at": now,
            "last_activity_at": now,
        }

    async def mark_status(
        self,
        conversation_id: str,
        *,
        status: str,
        cols: int | None = None,
        rows: int | None = None,
        workspace_path: str | None = None,
    ) -> None:
        updates = ["status = ?", "updated_at = ?", "last_activity_at = ?"]
        values: list[Any] = [status, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()]
        if cols is not None:
            updates.append("cols = ?")
            values.append(cols)
        if rows is not None:
            updates.append("rows = ?")
            values.append(rows)
        if workspace_path is not None:
            updates.append("workspace_path = ?")
            values.append(workspace_path)
        values.append(conversation_id)
        await self.db.conn.execute(
            f"UPDATE terminal_sessions SET {', '.join(updates)} WHERE conversation_id = ?",
            values,
        )
        await self.db.conn.commit()

    async def touch(
        self,
        conversation_id: str,
        *,
        cols: int | None = None,
        rows: int | None = None,
    ) -> None:
        updates = ["updated_at = ?", "last_activity_at = ?"]
        now = datetime.now(timezone.utc).isoformat()
        values: list[Any] = [now, now]
        if cols is not None:
            updates.append("cols = ?")
            values.append(cols)
        if rows is not None:
            updates.append("rows = ?")
            values.append(rows)
        values.append(conversation_id)
        await self.db.conn.execute(
            f"UPDATE terminal_sessions SET {', '.join(updates)} WHERE conversation_id = ?",
            values,
        )
        await self.db.conn.commit()

    async def delete(self, conversation_id: str) -> None:
        await self.db.conn.execute(
            "DELETE FROM terminal_sessions WHERE conversation_id = ?",
            (conversation_id,),
        )
        await self.db.conn.commit()
