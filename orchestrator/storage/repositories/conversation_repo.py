"""Repository for conversations."""

import json
import uuid
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
        workspace_path: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new conversation.

        Args:
            conversation_id: Unique identifier for the conversation.
            title: Optional title for the conversation.
            status: Conversation status (default: "active").
            metadata: Optional metadata dict.
            session_id: Session ID for demo mode isolation.

        Returns:
            Created conversation dict.
        """
        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

        await self.db.conn.execute(
            """
            INSERT INTO conversations (
                conversation_id, created_at, updated_at, title, status, workspace_path,
                metadata_json, session_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, now, now, title, status, workspace_path, metadata_json, session_id),
        )
        await self.db.conn.commit()
        return {
            "conversation_id": conversation_id,
            "created_at": now,
            "updated_at": now,
            "title": title,
            "status": status,
            "workspace_path": workspace_path,
            "metadata": metadata or {},
            "session_id": session_id,
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

    async def get_with_session_check(
        self,
        conversation_id: str,
        session_id: Optional[str] = None,
        is_owner: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Get a conversation with session ownership verification.

        Returns None if:
        - Conversation doesn't exist
        - User is not owner AND session_id doesn't match
        - Conversation has NULL session_id (legacy/owner-only data) AND user is not owner

        Args:
            conversation_id: ID of the conversation to get.
            session_id: Session ID of the requesting user.
            is_owner: If True, bypass session check.

        Returns:
            Conversation dict if found and accessible, None otherwise.
        """
        conversation = await self.get(conversation_id)
        if not conversation:
            return None

        # Owner bypasses all checks
        if is_owner:
            return conversation

        # Check session ownership
        conv_session = conversation.get("session_id")

        # NULL session_id = owner-only (legacy data)
        if conv_session is None:
            return None

        # Must match session
        if conv_session != session_id:
            return None

        return conversation

    async def list(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        session_id: Optional[str] = None,
        is_owner: bool = False,
    ) -> List[dict[str, Any]]:
        """List conversations with optional session scoping.

        Args:
            status: Filter by conversation status.
            limit: Maximum number of results.
            offset: Offset for pagination.
            session_id: Session ID for filtering (demo mode).
            is_owner: If True, bypass session filtering and show all.

        Returns:
            List of conversation dicts.
        """
        query = "SELECT * FROM conversations"
        params: List[Any] = []
        conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)

        # Session scoping: only show user's conversations (unless owner)
        if not is_owner and session_id:
            # Show conversations owned by this session
            conditions.append("session_id = ?")
            params.append(session_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY COALESCE(updated_at, created_at) DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            conversations = []
            for row in rows:
                convo = dict(row)
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
            updates.append("updated_at = ?")
            values.append(datetime.now(timezone.utc).isoformat())
            values.append(conversation_id)
            await self.db.conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE conversation_id = ?",
                values,
            )
            await self.db.conn.commit()

    async def delete(self, conversation_id: str) -> None:
        """Delete conversation and ALL associated data.

        Temporarily disables foreign key checks to handle complex
        cross-references between tables.
        """
        try:
            # Disable FK checks for clean deletion
            await self.db.conn.execute("PRAGMA foreign_keys = OFF")

            # 1. Get all run_ids for this conversation
            async with self.db.conn.execute(
                "SELECT run_id FROM runs WHERE conversation_id = ?",
                (conversation_id,)
            ) as cursor:
                run_rows = await cursor.fetchall()
                run_ids = [dict(row)["run_id"] for row in run_rows]

            if run_ids:
                placeholders = ",".join(["?" for _ in run_ids])

                # 2. Delete trace_events for these runs
                await self.db.conn.execute(
                    f"DELETE FROM trace_events WHERE run_id IN ({placeholders})",
                    tuple(run_ids)
                )

                # 3. Delete eval_samples that reference these runs
                await self.db.conn.execute(
                    f"DELETE FROM eval_samples WHERE run_id IN ({placeholders})",
                    tuple(run_ids)
                )

            # 4. Delete runs
            await self.db.conn.execute(
                "DELETE FROM runs WHERE conversation_id = ?",
                (conversation_id,)
            )

            # 5. Delete conversation
            await self.db.conn.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,)
            )

            await self.db.conn.commit()
        except Exception as e:
            await self.db.conn.rollback()
            raise e
        finally:
            # Re-enable FK checks
            await self.db.conn.execute("PRAGMA foreign_keys = ON")

    async def create_rewind_checkpoint(
        self,
        *,
        conversation_id: str,
        run_id: str,
        user_message: str,
        entry_seq_before: int,
        state_before: dict[str, Any],
    ) -> dict[str, Any]:
        """Create or replace a rewind checkpoint for a conversation run."""
        checkpoint_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self.db.conn.execute(
            """
            INSERT INTO conversation_rewind_checkpoints (
                id, conversation_id, run_id, user_message,
                entry_seq_before, state_before_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                conversation_id = excluded.conversation_id,
                user_message = excluded.user_message,
                entry_seq_before = excluded.entry_seq_before,
                state_before_json = excluded.state_before_json,
                created_at = excluded.created_at
            """,
            (
                checkpoint_id,
                conversation_id,
                run_id,
                user_message,
                int(entry_seq_before),
                json.dumps(state_before, ensure_ascii=False),
                now,
            ),
        )
        await self.db.conn.commit()
        return {
            "id": checkpoint_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "user_message": user_message,
            "entry_seq_before": int(entry_seq_before),
            "state_before": state_before,
            "created_at": now,
        }

    async def get_rewind_checkpoint(
        self,
        *,
        conversation_id: str,
        run_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get a rewind checkpoint by run_id."""
        async with self.db.conn.execute(
            """
            SELECT *
            FROM conversation_rewind_checkpoints
            WHERE conversation_id = ? AND run_id = ?
            """,
            (conversation_id, run_id),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            record = dict(row)
            record["state_before"] = json.loads(record.pop("state_before_json") or "{}")
            return record

    async def list_rewind_checkpoints(
        self,
        conversation_id: str,
    ) -> List[dict[str, Any]]:
        """List rewind checkpoints for currently visible runs, newest first."""
        async with self.db.conn.execute(
            """
            SELECT c.*
            FROM conversation_rewind_checkpoints c
            INNER JOIN runs r ON r.run_id = c.run_id
            WHERE c.conversation_id = ? AND r.rewound_at IS NULL
            ORDER BY r.created_at DESC
            """,
            (conversation_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            checkpoints: List[dict[str, Any]] = []
            for row in rows:
                record = dict(row)
                record["state_before"] = json.loads(record.pop("state_before_json") or "{}")
                checkpoints.append(record)
            return checkpoints
