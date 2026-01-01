"""Repository for conversations."""

import json
from datetime import datetime, timezone
from typing import Any, Optional, List
from orchestrator.storage.db import Database

class ConversationRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        status: str = "active",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create a new conversation."""
        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        
        await self.db.conn.execute(
            """
            INSERT INTO conversations (conversation_id, created_at, title, status, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, now, title, status, metadata_json),
        )
        await self.db.conn.commit()
        return {
            "conversation_id": conversation_id,
            "created_at": now,
            "title": title,
            "status": status,
            "metadata": metadata or {},
        }

    async def get(self, conversation_id: str) -> Optional[dict[str, Any]]:
        """Get a conversation by ID."""
        async with self.db.conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                convo = dict(row)
                # convo["conversation_id"] is already present from DB
                convo["metadata"] = json.loads(convo.pop("metadata_json", "{}") or "{}")
                return convo
        return None

    async def list(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict[str, Any]]:
        """List conversations."""
        query = "SELECT * FROM conversations"
        params = []
        
        if status:
            query += " WHERE status = ?"
            params.append(status)
            
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            conversations = []
            for row in rows:
                convo = dict(row)
                # convo["conversation_id"] present
                convo["metadata"] = json.loads(convo.pop("metadata_json", "{}") or "{}")
                conversations.append(convo)
            return conversations

    async def update(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Update conversation."""
        updates = []
        values: List[Any] = []

        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if summary is not None:
            updates.append("summary = ?")
            values.append(summary)
        if metadata is not None:
            updates.append("metadata_json = ?")
            values.append(json.dumps(metadata, ensure_ascii=False))

        if updates:
            values.append(conversation_id)
            await self.db.conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE conversation_id = ?",
                values,
            )
            await self.db.conn.commit()

    async def delete(self, conversation_id: str) -> None:
        """Delete conversation and ALL associated runs.

        Note: trace_events are automatically deleted via ON DELETE CASCADE
        when runs are deleted.
        """
        try:
            # 1. Get all run_ids for this conversation
            async with self.db.conn.execute(
                "SELECT run_id FROM runs WHERE conversation_id = ?",
                (conversation_id,)
            ) as cursor:
                run_rows = await cursor.fetchall()
                run_ids = [dict(row)["run_id"] for row in run_rows]

            # 2. Delete eval_samples that reference these runs (if any)
            if run_ids:
                placeholders = ",".join(["?" for _ in run_ids])
                await self.db.conn.execute(
                    f"DELETE FROM eval_samples WHERE run_id IN ({placeholders})",
                    tuple(run_ids)
                )

            # 3. Delete runs (trace_events cascade automatically)
            await self.db.conn.execute(
                "DELETE FROM runs WHERE conversation_id = ?",
                (conversation_id,)
            )

            # 4. Delete conversation
            await self.db.conn.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,)
            )
            await self.db.conn.commit()
        except Exception as e:
            await self.db.conn.rollback()
            raise e
