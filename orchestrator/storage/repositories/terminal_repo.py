"""Repository for browser terminal session metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator.storage.db import Database


class TerminalSessionRepo:
    """CRUD helper for persisted browser terminal session metadata."""

    def __init__(self, db: Database):
        self.db = db

    async def get_by_session_id(self, session_id: str) -> Optional[dict[str, Any]]:
        cursor = await self.db.conn.execute(
            "SELECT * FROM terminal_sessions WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_by_conversation(
        self,
        conversation_id: str,
        *,
        status: str | None = "running",
    ) -> list[dict[str, Any]]:
        if status is None:
            cursor = await self.db.conn.execute(
                """
                SELECT * FROM terminal_sessions
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            )
        else:
            cursor = await self.db.conn.execute(
                """
                SELECT * FROM terminal_sessions
                WHERE conversation_id = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (conversation_id, status),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def count_running(self, conversation_id: str) -> int:
        cursor = await self.db.conn.execute(
            """
            SELECT COUNT(*) AS count FROM terminal_sessions
            WHERE conversation_id = ? AND status = 'running'
            """,
            (conversation_id,),
        )
        row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def get_first_running(self, conversation_id: str) -> Optional[dict[str, Any]]:
        rows = await self.list_by_conversation(conversation_id, status="running")
        return rows[0] if rows else None

    async def insert(
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
        title: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        await self.db.conn.execute(
            """
            INSERT INTO terminal_sessions (
                session_id, conversation_id, workspace_path, shell, status,
                cols, rows, session_owner, title, created_at, updated_at, last_activity_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                title,
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
            "title": title,
            "created_at": now,
            "updated_at": now,
            "last_activity_at": now,
        }

    async def mark_status(
        self,
        session_id: str,
        *,
        status: str,
        cols: int | None = None,
        rows: int | None = None,
        workspace_path: str | None = None,
    ) -> None:
        updates = ["status = ?", "updated_at = ?", "last_activity_at = ?"]
        now = datetime.now(timezone.utc).isoformat()
        values: list[Any] = [status, now, now]
        if cols is not None:
            updates.append("cols = ?")
            values.append(cols)
        if rows is not None:
            updates.append("rows = ?")
            values.append(rows)
        if workspace_path is not None:
            updates.append("workspace_path = ?")
            values.append(workspace_path)
        values.append(session_id)
        await self.db.conn.execute(
            f"UPDATE terminal_sessions SET {', '.join(updates)} WHERE session_id = ?",
            values,
        )
        await self.db.conn.commit()

    async def touch(
        self,
        session_id: str,
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
        values.append(session_id)
        await self.db.conn.execute(
            f"UPDATE terminal_sessions SET {', '.join(updates)} WHERE session_id = ?",
            values,
        )
        await self.db.conn.commit()

    async def delete(self, session_id: str) -> None:
        await self.db.conn.execute(
            "DELETE FROM terminal_sessions WHERE session_id = ?",
            (session_id,),
        )
        await self.db.conn.commit()

    async def delete_all_for_conversation(self, conversation_id: str) -> None:
        await self.db.conn.execute(
            "DELETE FROM terminal_sessions WHERE conversation_id = ?",
            (conversation_id,),
        )
        await self.db.conn.commit()
