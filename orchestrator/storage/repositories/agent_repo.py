"""Repository for agent steps, tool calls, and citations."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, List
from orchestrator.storage.db import Database


class AgentRepo:
    """Repository for web research agent data.

    Provides CRUD operations for agent_steps, agent_tool_calls, and agent_citations.
    Designed for crash recovery with idempotency keys and status tracking.
    """

    def __init__(self, db: Database):
        self.db = db

    # --- Agent Steps ---

    async def create_step(
        self,
        run_id: str,
        step_number: int,
        state: str,
        thinking_text: Optional[str] = None,
        decision: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new agent step.

        Args:
            run_id: The run ID this step belongs to.
            step_number: Sequential step number (1, 2, 3...).
            state: Step state (planning, tool_calling, synthesizing, complete, error).
            thinking_text: Model's reasoning/thinking for this step.
            decision: Decision made (call_tool, synthesize, error).

        Returns:
            Dict with step_id and created data.
        """
        step_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await self.db.conn.execute(
            """
            INSERT INTO agent_steps (
                id, run_id, step_number, created_at,
                state, thinking_text, decision
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (step_id, run_id, step_number, now, state, thinking_text, decision),
        )
        await self.db.conn.commit()

        return {
            "id": step_id,
            "run_id": run_id,
            "step_number": step_number,
            "state": state,
            "created_at": now,
        }

    async def update_step(
        self,
        step_id: str,
        state: Optional[str] = None,
        thinking_text: Optional[str] = None,
        decision: Optional[str] = None,
        completed_at: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update an existing agent step.

        Args:
            step_id: The step ID to update.
            state: New state.
            thinking_text: Updated thinking text.
            decision: Updated decision.
            completed_at: Completion timestamp (ISO format).
            error_message: Error message if state is error.
        """
        updates = []
        values = []

        if state is not None:
            updates.append("state = ?")
            values.append(state)
        if thinking_text is not None:
            updates.append("thinking_text = ?")
            values.append(thinking_text)
        if decision is not None:
            updates.append("decision = ?")
            values.append(decision)
        if completed_at is not None:
            updates.append("completed_at = ?")
            values.append(completed_at)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)

        if updates:
            updates.append("updated_at = ?")
            values.append(datetime.now(timezone.utc).isoformat())
            values.append(step_id)
            await self.db.conn.execute(
                f"UPDATE agent_steps SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            await self.db.conn.commit()

    async def get_step(self, step_id: str) -> Optional[dict[str, Any]]:
        """Get a step by ID.

        Args:
            step_id: The step ID.

        Returns:
            Step dict or None if not found.
        """
        async with self.db.conn.execute(
            "SELECT * FROM agent_steps WHERE id = ?", (step_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_step_by_number(
        self, run_id: str, step_number: int
    ) -> Optional[dict[str, Any]]:
        """Get a step by run_id and step_number.

        Args:
            run_id: The run ID.
            step_number: The step number.

        Returns:
            Step dict or None if not found.
        """
        async with self.db.conn.execute(
            "SELECT * FROM agent_steps WHERE run_id = ? AND step_number = ?",
            (run_id, step_number),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_steps_for_run(self, run_id: str) -> List[dict[str, Any]]:
        """Get all steps for a run in order.

        Args:
            run_id: The run ID.

        Returns:
            List of step dicts ordered by step_number.
        """
        async with self.db.conn.execute(
            "SELECT * FROM agent_steps WHERE run_id = ? ORDER BY step_number ASC",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_latest_step(self, run_id: str) -> Optional[dict[str, Any]]:
        """Get the most recent step for a run.

        Args:
            run_id: The run ID.

        Returns:
            Step dict or None if no steps exist.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_steps
            WHERE run_id = ?
            ORDER BY step_number DESC
            LIMIT 1
            """,
            (run_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    # --- Agent Tool Calls ---

    async def create_tool_call(
        self,
        run_id: str,
        step_id: str,
        tool_name: str,
        arguments: dict,
        idempotency_key: str,
        status: str = "pending",
    ) -> dict[str, Any]:
        """Create a new tool call.

        Args:
            run_id: The run ID.
            step_id: The step ID this tool call belongs to.
            tool_name: Name of the tool (web_search, web_extract, exec_command, etc.).
            arguments: Tool arguments as dict.
            idempotency_key: Unique key for retry detection.
            status: Initial status (default: pending).

        Returns:
            Dict with tool_call_id and created data.
        """
        tool_call_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        arguments_json = json.dumps(arguments, ensure_ascii=False)

        await self.db.conn.execute(
            """
            INSERT INTO agent_tool_calls (
                id, run_id, step_id, created_at,
                tool_name, arguments, status, idempotency_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_call_id,
                run_id,
                step_id,
                now,
                tool_name,
                arguments_json,
                status,
                idempotency_key,
            ),
        )
        await self.db.conn.commit()

        return {
            "id": tool_call_id,
            "run_id": run_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "status": status,
            "created_at": now,
            "idempotency_key": idempotency_key,
        }

    async def update_tool_call(
        self,
        tool_call_id: str,
        status: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        duration_ms: Optional[int] = None,
        execution_attempt: Optional[int] = None,
        result_summary: Optional[str] = None,
        error_message: Optional[str] = None,
        approval_decision: Optional[str] = None,
        approval_policy: Optional[str] = None,
        approval_decided_at: Optional[str] = None,
        result_detail: Optional[str] = None,
    ) -> None:
        """Update an existing tool call.

        Args:
            tool_call_id: The tool call ID to update.
            status: New status.
            started_at: When execution started.
            completed_at: When execution completed.
            duration_ms: Execution duration in milliseconds.
            execution_attempt: Attempt number (for retries).
            result_summary: One-line summary of result (not full output).
            error_message: Error message if status is error/timeout.
            approval_decision: Approval decision (approved/denied/auto/timeout).
            approval_policy: Permission policy (strict/relaxed/yolo).
            approval_decided_at: ISO timestamp of approval decision.
            result_detail: Full tool result text (up to 10k chars).
        """
        updates = []
        values = []

        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if started_at is not None:
            updates.append("started_at = ?")
            values.append(started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            values.append(completed_at)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            values.append(duration_ms)
        if execution_attempt is not None:
            updates.append("execution_attempt = ?")
            values.append(execution_attempt)
        if result_summary is not None:
            updates.append("result_summary = ?")
            values.append(result_summary)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)
        if approval_decision is not None:
            updates.append("approval_decision = ?")
            values.append(approval_decision)
        if approval_policy is not None:
            updates.append("approval_policy = ?")
            values.append(approval_policy)
        if approval_decided_at is not None:
            updates.append("approval_decided_at = ?")
            values.append(approval_decided_at)
        if result_detail is not None:
            updates.append("result_detail = ?")
            values.append(result_detail)

        if updates:
            values.append(tool_call_id)
            await self.db.conn.execute(
                f"UPDATE agent_tool_calls SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            await self.db.conn.commit()

    async def get_tool_call(self, tool_call_id: str) -> Optional[dict[str, Any]]:
        """Get a tool call by ID.

        Args:
            tool_call_id: The tool call ID.

        Returns:
            Tool call dict with parsed arguments, or None if not found.
        """
        async with self.db.conn.execute(
            "SELECT * FROM agent_tool_calls WHERE id = ?", (tool_call_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                tool_call = dict(row)
                tool_call["arguments"] = json.loads(tool_call["arguments"])
                return tool_call
        return None

    async def get_tool_call_by_idempotency_key(
        self, run_id: str, idempotency_key: str
    ) -> Optional[dict[str, Any]]:
        """Get a tool call by idempotency key.

        Used for crash recovery to check if a tool call was already created.

        Args:
            run_id: The run ID.
            idempotency_key: The idempotency key.

        Returns:
            Tool call dict or None if not found.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_tool_calls
            WHERE run_id = ? AND idempotency_key = ?
            """,
            (run_id, idempotency_key),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                tool_call = dict(row)
                tool_call["arguments"] = json.loads(tool_call["arguments"])
                return tool_call
        return None

    async def get_tool_calls_for_step(self, step_id: str) -> List[dict[str, Any]]:
        """Get all tool calls for a step.

        Args:
            step_id: The step ID.

        Returns:
            List of tool call dicts ordered by created_at.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_tool_calls
            WHERE step_id = ?
            ORDER BY created_at ASC
            """,
            (step_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            tool_calls = []
            for row in rows:
                tc = dict(row)
                tc["arguments"] = json.loads(tc["arguments"])
                tool_calls.append(tc)
            return tool_calls

    async def get_tool_calls_for_run(self, run_id: str) -> List[dict[str, Any]]:
        """Get all tool calls for a run.

        Args:
            run_id: The run ID.

        Returns:
            List of tool call dicts ordered by created_at.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_tool_calls
            WHERE run_id = ?
            ORDER BY created_at ASC
            """,
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            tool_calls = []
            for row in rows:
                tc = dict(row)
                tc["arguments"] = json.loads(tc["arguments"])
                tool_calls.append(tc)
            return tool_calls

    async def get_pending_tool_calls(self, run_id: str) -> List[dict[str, Any]]:
        """Get tool calls in pending or running state for crash recovery.

        Args:
            run_id: The run ID.

        Returns:
            List of tool call dicts that need to be resumed or retried.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_tool_calls
            WHERE run_id = ? AND status IN ('pending', 'running')
            ORDER BY created_at ASC
            """,
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            tool_calls = []
            for row in rows:
                tc = dict(row)
                tc["arguments"] = json.loads(tc["arguments"])
                tool_calls.append(tc)
            return tool_calls

    # --- Agent Citations ---

    async def create_citation(
        self,
        run_id: str,
        tool_call_id: str,
        source_url: str,
        snippet: str,
        title: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new citation.

        Args:
            run_id: The run ID.
            tool_call_id: The tool call that produced this citation.
            source_url: URL of the source.
            snippet: Relevant text snippet from the source.
            title: Optional title of the source.

        Returns:
            Dict with citation_id and created data.
        """
        citation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await self.db.conn.execute(
            """
            INSERT INTO agent_citations (
                id, run_id, tool_call_id, created_at,
                source_url, title, snippet, used_in_answer
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (citation_id, run_id, tool_call_id, now, source_url, title, snippet, False),
        )
        await self.db.conn.commit()

        return {
            "id": citation_id,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
            "source_url": source_url,
            "title": title,
            "snippet": snippet,
            "used_in_answer": False,
            "created_at": now,
        }

    async def get_citation(self, citation_id: str) -> Optional[dict[str, Any]]:
        """Get a citation by ID.

        Args:
            citation_id: The citation ID.

        Returns:
            Citation dict or None if not found.
        """
        async with self.db.conn.execute(
            "SELECT * FROM agent_citations WHERE id = ?", (citation_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
        return None

    async def get_citations_for_run(self, run_id: str) -> List[dict[str, Any]]:
        """Get all citations for a run.

        Args:
            run_id: The run ID.

        Returns:
            List of citation dicts ordered by created_at.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_citations
            WHERE run_id = ?
            ORDER BY created_at ASC
            """,
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_citations_for_tool_call(
        self, tool_call_id: str
    ) -> List[dict[str, Any]]:
        """Get all citations from a specific tool call.

        Args:
            tool_call_id: The tool call ID.

        Returns:
            List of citation dicts.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM agent_citations
            WHERE tool_call_id = ?
            ORDER BY created_at ASC
            """,
            (tool_call_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_citation_used(self, citation_id: str) -> None:
        """Mark a citation as used in the final answer.

        Args:
            citation_id: The citation ID.
        """
        await self.db.conn.execute(
            "UPDATE agent_citations SET used_in_answer = ? WHERE id = ?",
            (True, citation_id),
        )
        await self.db.conn.commit()

    async def mark_citations_used(self, citation_ids: List[str]) -> None:
        """Mark multiple citations as used in the final answer.

        Args:
            citation_ids: List of citation IDs.
        """
        if not citation_ids:
            return

        placeholders = ",".join("?" * len(citation_ids))
        await self.db.conn.execute(
            f"UPDATE agent_citations SET used_in_answer = ? WHERE id IN ({placeholders})",
            [True] + citation_ids,
        )
        await self.db.conn.commit()

    # --- Run Events ---

    async def create_run_event(
        self,
        run_id: str,
        seq: int,
        event_type: str,
        event_data: dict,
    ) -> dict[str, Any]:
        """Persist an SSE event for durable replay.

        Args:
            run_id: The run ID.
            seq: Sequence number within the run.
            event_type: Event type string.
            event_data: Full event payload dict.

        Returns:
            Dict with event id and created data.
        """
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        event_data_json = json.dumps(event_data, ensure_ascii=False)

        await self.db.conn.execute(
            """
            INSERT INTO run_events (id, run_id, seq, event_type, event_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, run_id, seq, event_type, event_data_json, now),
        )
        await self.db.conn.commit()

        return {
            "id": event_id,
            "run_id": run_id,
            "seq": seq,
            "event_type": event_type,
            "created_at": now,
        }

    async def get_run_events(self, run_id: str) -> List[dict[str, Any]]:
        """Get all persisted events for a run in order.

        Args:
            run_id: The run ID.

        Returns:
            List of event dicts ordered by seq.
        """
        async with self.db.conn.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY seq ASC",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            events = []
            for row in rows:
                e = dict(row)
                if e.get("event_data"):
                    e["event_data"] = json.loads(e["event_data"])
                events.append(e)
            return events

    # --- Run Artifacts ---

    async def create_run_artifact(
        self,
        run_id: str,
        artifact_type: str,
        file_path: str,
        action: str,
        detail: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        artifact_path: Optional[str] = None,
        byte_count: Optional[int] = None,
        sha256: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record a file change or command execution artifact.

        Args:
            run_id: The run ID.
            artifact_type: Type of artifact (file_write, file_edit, command_run).
            file_path: Path to affected file or command string.
            action: Tool name that produced this artifact.
            detail: Result summary or additional detail.
            tool_call_id: Optional link to the tool call record.

        Returns:
            Dict with artifact id and created data.
        """
        artifact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await self.db.conn.execute(
            """
            INSERT INTO run_artifacts (
                id, run_id, artifact_type, file_path, action,
                detail, tool_call_id, artifact_path, byte_count,
                sha256, content_type, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                run_id,
                artifact_type,
                file_path,
                action,
                detail,
                tool_call_id,
                artifact_path,
                byte_count,
                sha256,
                content_type,
                json.dumps(metadata or {}, ensure_ascii=False) if metadata is not None else None,
                now,
            ),
        )
        await self.db.conn.commit()

        return {
            "id": artifact_id,
            "run_id": run_id,
            "artifact_type": artifact_type,
            "file_path": file_path,
            "action": action,
            "detail": detail,
            "tool_call_id": tool_call_id,
            "artifact_path": artifact_path,
            "byte_count": byte_count,
            "sha256": sha256,
            "content_type": content_type,
            "metadata": metadata,
            "created_at": now,
        }

    async def get_run_artifacts(self, run_id: str) -> List[dict[str, Any]]:
        """Get all artifacts for a run.

        Args:
            run_id: The run ID.

        Returns:
            List of artifact dicts ordered by created_at.
        """
        async with self.db.conn.execute(
            "SELECT * FROM run_artifacts WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            artifacts: list[dict[str, Any]] = []
            for row in rows:
                artifact = dict(row)
                if artifact.get("metadata"):
                    try:
                        artifact["metadata"] = json.loads(artifact["metadata"])
                    except (TypeError, json.JSONDecodeError):
                        artifact["metadata"] = {}
                artifacts.append(artifact)
            return artifacts

    # --- Persistent Coding Session State ---

    async def get_coding_session_state(
        self,
        conversation_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get persisted coding-session state for a conversation."""
        async with self.db.conn.execute(
            "SELECT * FROM coding_sessions WHERE conversation_id = ?",
            (conversation_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            record = dict(row)
            record["state"] = json.loads(record.pop("state_json"))
            return record

    async def upsert_coding_session_state(
        self,
        conversation_id: str,
        state: dict[str, Any],
        *,
        last_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create or replace persisted coding-session state."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.conn.execute(
            """
            INSERT INTO coding_sessions (
                conversation_id, state_json, last_run_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                state_json = excluded.state_json,
                last_run_id = excluded.last_run_id,
                updated_at = excluded.updated_at
            """,
            (
                conversation_id,
                json.dumps(state, ensure_ascii=False),
                last_run_id,
                now,
                now,
            ),
        )
        await self.db.conn.commit()
        return {
            "conversation_id": conversation_id,
            "state": state,
            "last_run_id": last_run_id,
            "created_at": now,
            "updated_at": now,
        }

    async def append_coding_session_entries(
        self,
        conversation_id: str,
        entries: List[dict[str, Any]],
    ) -> List[dict[str, Any]]:
        """Append coding-session entries using globally unique per-conversation seq values."""
        if not entries:
            return []

        now = datetime.now(timezone.utc).isoformat()
        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            async with self.db.conn.execute(
                """
                SELECT COALESCE(MAX(seq), 0) AS max_seq
                FROM coding_session_entries
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ) as cursor:
                row = await cursor.fetchone()
                next_seq = int(row["max_seq"] or 0) + 1 if row else 1

            stored: List[dict[str, Any]] = []
            for entry in entries:
                entry_id = str(uuid.uuid4())
                seq = next_seq
                next_seq += 1
                content_json = json.dumps(
                    entry.get("content_json") or {},
                    ensure_ascii=False,
                )
                await self.db.conn.execute(
                    """
                    INSERT INTO coding_session_entries (
                        id, conversation_id, seq, run_id, step_number,
                        entry_type, role, content_json, token_estimate,
                        created_at, compacted_at, rewound_at, rewind_group_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        conversation_id,
                        seq,
                        entry.get("run_id"),
                        entry.get("step_number"),
                        entry.get("entry_type"),
                        entry.get("role"),
                        content_json,
                        int(entry.get("token_estimate") or 0),
                        now,
                        entry.get("compacted_at"),
                        entry.get("rewound_at"),
                        entry.get("rewind_group_id"),
                    ),
                )
                stored.append(
                    {
                        "id": entry_id,
                        "conversation_id": conversation_id,
                        "seq": seq,
                        "run_id": entry.get("run_id"),
                        "step_number": entry.get("step_number"),
                        "entry_type": entry.get("entry_type"),
                        "role": entry.get("role"),
                        "content_json": entry.get("content_json") or {},
                        "token_estimate": int(entry.get("token_estimate") or 0),
                        "created_at": now,
                        "compacted_at": entry.get("compacted_at"),
                        "rewound_at": entry.get("rewound_at"),
                        "rewind_group_id": entry.get("rewind_group_id"),
                    }
                )

            await self.db.conn.commit()
            return stored
        except Exception:
            await self.db.conn.rollback()
            raise

    async def insert_coding_session_entry(
        self,
        conversation_id: str,
        *,
        before_seq: int,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        """Insert a coding-session entry before an existing seq, preserving global seq uniqueness."""
        now = datetime.now(timezone.utc).isoformat()
        entry_id = str(uuid.uuid4())
        content_json = json.dumps(entry.get("content_json") or {}, ensure_ascii=False)

        await self.db.conn.execute("BEGIN IMMEDIATE")
        try:
            async with self.db.conn.execute(
                """
                SELECT COALESCE(MAX(seq), 0) AS max_seq
                FROM coding_session_entries
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ) as cursor:
                row = await cursor.fetchone()
                max_seq = int(row["max_seq"] or 0) if row else 0

            shift_offset = max_seq + 1
            await self.db.conn.execute(
                """
                UPDATE coding_session_entries
                SET seq = seq + ?
                WHERE conversation_id = ? AND seq >= ?
                """,
                (shift_offset, conversation_id, before_seq),
            )
            await self.db.conn.execute(
                """
                INSERT INTO coding_session_entries (
                    id, conversation_id, seq, run_id, step_number,
                    entry_type, role, content_json, token_estimate,
                    created_at, compacted_at, rewound_at, rewind_group_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    conversation_id,
                    before_seq,
                    entry.get("run_id"),
                    entry.get("step_number"),
                    entry.get("entry_type"),
                    entry.get("role"),
                    content_json,
                    int(entry.get("token_estimate") or 0),
                    now,
                    entry.get("compacted_at"),
                    entry.get("rewound_at"),
                    entry.get("rewind_group_id"),
                ),
            )
            await self.db.conn.execute(
                """
                UPDATE coding_session_entries
                SET seq = seq - ?
                WHERE conversation_id = ? AND seq >= ?
                """,
                (shift_offset - 1, conversation_id, before_seq + shift_offset),
            )
            await self.db.conn.commit()
        except Exception:
            await self.db.conn.rollback()
            raise

        return {
            "id": entry_id,
            "conversation_id": conversation_id,
            "seq": before_seq,
            "run_id": entry.get("run_id"),
            "step_number": entry.get("step_number"),
            "entry_type": entry.get("entry_type"),
            "role": entry.get("role"),
            "content_json": entry.get("content_json") or {},
            "token_estimate": int(entry.get("token_estimate") or 0),
            "created_at": now,
            "compacted_at": entry.get("compacted_at"),
            "rewound_at": entry.get("rewound_at"),
            "rewind_group_id": entry.get("rewind_group_id"),
        }

    async def list_coding_session_entries(
        self,
        conversation_id: str,
        *,
        start_seq: Optional[int] = None,
        end_seq: Optional[int] = None,
        include_compacted: bool = True,
        include_rewound: bool = False,
    ) -> List[dict[str, Any]]:
        """List coding-session entries in seq order."""
        query = """
            SELECT *
            FROM coding_session_entries
            WHERE conversation_id = ?
        """
        params: List[Any] = [conversation_id]
        if start_seq is not None:
            query += " AND seq >= ?"
            params.append(start_seq)
        if end_seq is not None:
            query += " AND seq <= ?"
            params.append(end_seq)
        if not include_compacted:
            query += " AND compacted_at IS NULL"
        if not include_rewound:
            query += " AND rewound_at IS NULL"
        query += " ORDER BY seq ASC"

        async with self.db.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            entries: List[dict[str, Any]] = []
            for row in rows:
                record = dict(row)
                record["content_json"] = json.loads(record["content_json"])
                entries.append(record)
            return entries

    async def get_latest_coding_session_entry_seq(
        self,
        conversation_id: str,
        *,
        include_rewound: bool = False,
    ) -> int:
        """Return the latest seq stored for a conversation."""
        query = """
            SELECT COALESCE(MAX(seq), 0) AS max_seq
            FROM coding_session_entries
            WHERE conversation_id = ?
        """
        params: List[Any] = [conversation_id]
        if not include_rewound:
            query += " AND rewound_at IS NULL"
        async with self.db.conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if not row:
                return 0
            return int(row["max_seq"] or 0)

    async def mark_coding_session_entries_compacted(
        self,
        conversation_id: str,
        *,
        through_seq: int,
        compacted_at: Optional[str] = None,
    ) -> None:
        """Mark coding-session entries through seq as compacted."""
        timestamp = compacted_at or datetime.now(timezone.utc).isoformat()
        await self.db.conn.execute(
            """
            UPDATE coding_session_entries
            SET compacted_at = COALESCE(compacted_at, ?)
            WHERE conversation_id = ? AND seq <= ?
            """,
            (timestamp, conversation_id, through_seq),
        )
        await self.db.conn.commit()

    async def mark_coding_session_entries_rewound(
        self,
        conversation_id: str,
        *,
        after_seq: int,
        rewound_at: str,
        rewind_group_id: str,
    ) -> None:
        """Soft-hide active coding-session entries after a checkpoint boundary."""
        await self.db.conn.execute(
            """
            UPDATE coding_session_entries
            SET rewound_at = ?, rewind_group_id = ?
            WHERE conversation_id = ? AND seq > ? AND rewound_at IS NULL
            """,
            (rewound_at, rewind_group_id, conversation_id, after_seq),
        )
        await self.db.conn.commit()

    # --- Run Agent State (updates to runs table) ---

    async def update_run_agent_state(
        self,
        run_id: str,
        agent_state: Optional[str] = None,
        current_step: Optional[int] = None,
        max_steps: Optional[int] = None,
        status: Optional[str] = None,
        final_answer: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update agent-related columns on the runs table.

        Args:
            run_id: The run ID.
            agent_state: Current agent state.
            current_step: Current step number.
            max_steps: Maximum allowed steps.
            status: Run status (running, succeeded, failed).
            final_answer: Final answer text.
            error_message: Error message if failed.
        """
        updates = ["updated_at = ?"]
        values = [datetime.now(timezone.utc).isoformat()]

        if agent_state is not None:
            updates.append("agent_state = ?")
            values.append(agent_state)
        if current_step is not None:
            updates.append("current_step = ?")
            values.append(current_step)
        if max_steps is not None:
            updates.append("max_steps = ?")
            values.append(max_steps)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if final_answer is not None:
            updates.append("final_answer = ?")
            values.append(final_answer)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)

        values.append(run_id)
        await self.db.conn.execute(
            f"UPDATE runs SET {', '.join(updates)} WHERE run_id = ?",
            values,
        )
        await self.db.conn.commit()

    async def get_interrupted_runs(self) -> List[dict[str, Any]]:
        """Get runs that were interrupted (for startup recovery).

        Returns runs where:
        - mode = 'agent' (agent runs only)
        - status = 'running' (was in progress when interrupted)

        Returns:
            List of run dicts that need recovery.
        """
        async with self.db.conn.execute(
            """
            SELECT * FROM runs
            WHERE mode = 'agent' AND status = 'running'
            ORDER BY created_at ASC
            """,
        ) as cursor:
            rows = await cursor.fetchall()
            runs = []
            for row in rows:
                r = dict(row)
                if r.get("model_config_snapshot"):
                    r["model_config"] = json.loads(r.pop("model_config_snapshot"))
                if r.get("usage_stats"):
                    r["usage"] = json.loads(r.pop("usage_stats"))
                runs.append(r)
            return runs

    # --- Cascade Delete ---

    async def delete_agent_data_for_run(self, run_id: str) -> None:
        """Delete all agent data for a run.

        Deletes agent_steps, agent_tool_calls, and agent_citations.
        Uses cascade delete via foreign keys, but explicitly deletes for safety.

        Args:
            run_id: The run ID.
        """
        try:
            await self.db.conn.execute("PRAGMA foreign_keys = OFF")

            # Delete in reverse dependency order
            await self.db.conn.execute(
                "DELETE FROM agent_citations WHERE run_id = ?", (run_id,)
            )
            await self.db.conn.execute(
                "DELETE FROM agent_tool_calls WHERE run_id = ?", (run_id,)
            )
            await self.db.conn.execute(
                "DELETE FROM agent_steps WHERE run_id = ?", (run_id,)
            )

            await self.db.conn.commit()
        finally:
            await self.db.conn.execute("PRAGMA foreign_keys = ON")
