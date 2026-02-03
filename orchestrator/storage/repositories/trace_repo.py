"""Repository for runs and trace events."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, List
from orchestrator.storage.db import Database


class TraceRepo:
    """Repository for runs and trace events.

    Provides atomic operations for trace events with proper concurrency handling.
    """

    # Class-level lock for atomic seq allocation
    # This ensures only one add_trace_event transaction runs at a time
    _seq_lock = asyncio.Lock()

    def __init__(self, db: Database):
        self.db = db

    # --- Runs (formerly conversation_traces) ---

    async def create_run(
        self,
        run_id: str,
        conversation_id: str,
        profile_name: str,
        mode: str,
        model_config: dict,
        user_message: Optional[str] = None,
        system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Start a new run.

        Args:
            run_id: Unique identifier for the run.
            conversation_id: Associated conversation ID.
            profile_name: Chat profile name.
            mode: Run mode (chat, eval, agent).
            model_config: Model configuration dict.
            user_message: User's input message.
            system_prompt: System prompt used.
            session_id: Session ID for demo mode isolation.

        Returns:
            Created run dict.
        """
        now = datetime.now(timezone.utc).isoformat()
        config_snapshot = json.dumps(model_config, ensure_ascii=False)

        # Initial empty usage stats
        usage_stats = json.dumps({"input_tokens": 0, "output_tokens": 0, "latency_ms": 0})

        await self.db.conn.execute(
            """
            INSERT INTO runs (
                run_id, conversation_id, created_at,
                user_message, system_prompt_snapshot,
                profile_name, mode, model_config_snapshot,
                status, usage_stats, session_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, conversation_id, now,
                user_message, system_prompt,
                profile_name, mode, config_snapshot,
                "running", usage_stats, session_id
            ),
        )
        await self.db.conn.commit()
        return {"run_id": run_id, "status": "running", "session_id": session_id}

    # Alias for backward compatibility
    async def create_conversation_trace(self, *args, **kwargs):
        return await self.create_run(*args, **kwargs)

    async def update_run(
        self,
        run_id: str,
        final_answer: Optional[str] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        usage_stats: Optional[dict] = None,
        last_response_id: Optional[str] = None,
    ) -> None:
        """Update run with results."""
        updates = []
        values = []

        if final_answer is not None:
            updates.append("final_answer = ?")
            values.append(final_answer)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)
        if usage_stats is not None:
            updates.append("usage_stats = ?")
            values.append(json.dumps(usage_stats))
        if last_response_id is not None:
            updates.append("last_response_id = ?")
            values.append(last_response_id)

        if updates:
            values.append(run_id)
            await self.db.conn.execute(
                f"UPDATE runs SET {', '.join(updates)} WHERE run_id = ?",
                values,
            )
            await self.db.conn.commit()

    # Alias for backward compatibility
    async def update_conversation_trace(self, *args, **kwargs):
        return await self.update_run(*args, **kwargs)

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        async with self.db.conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                run = dict(row)
                run["model_config"] = json.loads(run.pop("model_config_snapshot"))
                run["usage"] = json.loads(run.pop("usage_stats"))
                return run
        return None

    # Alias for backward compatibility
    async def get_conversation_trace(self, run_id: str):
        return await self.get_run(run_id)

    async def get_run_with_session_check(
        self,
        run_id: str,
        session_id: Optional[str] = None,
        is_owner: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Get a run with session ownership verification.

        Returns None if:
        - Run doesn't exist
        - User is not owner AND session_id doesn't match
        - Run has NULL session_id (legacy/owner-only data) AND user is not owner

        Args:
            run_id: ID of the run to get.
            session_id: Session ID of the requesting user.
            is_owner: If True, bypass session check.

        Returns:
            Run dict if found and accessible, None otherwise.
        """
        run = await self.get_run(run_id)
        if not run:
            return None

        # Owner bypasses all checks
        if is_owner:
            return run

        # Check session ownership
        run_session = run.get("session_id")

        # NULL session_id = owner-only (legacy data)
        if run_session is None:
            return None

        # Must match session
        if run_session != session_id:
            return None

        return run

    async def list_runs(
        self,
        conversation_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        session_id: Optional[str] = None,
        is_owner: bool = False,
    ) -> List[dict[str, Any]]:
        """List runs with optional session scoping.

        Args:
            conversation_id: Filter by conversation.
            limit: Maximum number of results.
            offset: Offset for pagination.
            session_id: Session ID for filtering (demo mode).
            is_owner: If True, bypass session filtering and show all.

        Returns:
            List of run dicts.
        """
        query = "SELECT * FROM runs"
        params: List[Any] = []
        conditions = []

        if conversation_id:
            conditions.append("conversation_id = ?")
            params.append(conversation_id)

        # Session scoping: only show user's runs (unless owner)
        if not is_owner and session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            runs = []
            for row in rows:
                r = dict(row)
                r["model_config"] = json.loads(r.pop("model_config_snapshot", "{}"))
                r["usage"] = json.loads(r.pop("usage_stats", "{}"))
                runs.append(r)
            return runs

    async def list_runs_for_conversation(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict[str, Any]]:
        """List runs for a conversation in chronological order.

        This is the canonical method for loading conversation history.
        Uses ASC ordering so messages display oldest-first (top to bottom).
        Use list_runs() for paginated listings where newest-first is desired.
        """
        query = """
            SELECT * FROM runs
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
        """
        params = [conversation_id, limit, offset]

        async with self.db.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            runs = []
            for row in rows:
                r = dict(row)
                r["model_config"] = json.loads(r.pop("model_config_snapshot", "{}"))
                r["usage"] = json.loads(r.pop("usage_stats", "{}"))
                runs.append(r)
            return runs

    async def get_latest_response_id(
        self,
        conversation_id: str,
    ) -> Optional[str]:
        """Get the last_response_id from the most recent succeeded run.

        Used for stateful mode to chain conversations via previous_response_id.
        Only considers runs with status='succeeded' to avoid chaining onto failed/partial runs.

        Args:
            conversation_id: The conversation to query.

        Returns:
            The last_response_id from the most recent succeeded run, or None.
        """
        async with self.db.conn.execute(
            """
            SELECT last_response_id FROM runs
            WHERE conversation_id = ? AND status = 'succeeded' AND last_response_id IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        return None

    # --- Thinking Traces (via trace_events) ---

    async def add_thinking_step(
        self,
        run_id: str,
        step: "ThinkingStep",
    ) -> str:
        """Store both internal and UI trace for a thinking step.

        Uses trace_events table with event_type="thinking".

        Args:
            run_id: The run ID to associate with.
            step: ThinkingStep with both internal and UI data.

        Returns:
            The created event ID.
        """
        # Build content with both internal and UI sections
        content = {
            "step_type": step.step_type,
            "summary": step.ui_summary,
            "internal": step.to_internal_dict(),
            "ui": step.to_ui_dict(),
        }

        return await self.add_trace_event(
            run_id=run_id,
            event_type="thinking",
            content=content,
            actor="model",
            event_status="success",
            step_number=step.seq,
            token_count=step.to_internal_dict().get("tokens", {}).get("total"),
            duration_ms=step.to_internal_dict().get("timing_ms"),
        )

    async def update_thinking_summary(
        self,
        run_id: str,
        thinking_summary: str,
    ) -> None:
        """Update the thinking_summary for a run."""
        await self.db.conn.execute(
            "UPDATE runs SET thinking_summary = ? WHERE run_id = ?",
            (thinking_summary, run_id),
        )
        await self.db.conn.commit()

    async def get_thinking(
        self,
        run_id: str,
        detail: str = "user",
    ) -> dict[str, Any]:
        """Get thinking trace for a run.

        Queries trace_events with event_type="thinking".

        Args:
            run_id: The run ID.
            detail: Level of detail - "user", "internal", or "full".

        Returns:
            Dict with thinking data based on detail level.
        """
        # Get run for thinking_summary
        run = await self.get_run(run_id)
        if not run:
            return {"error": "Run not found"}

        # Get thinking events from trace_events
        events = await self.get_trace_events(run_id, event_type="thinking")

        # Build thinking steps from events
        thinking_steps = []
        for event in events:
            content = event.get("content", {})
            step_type = content.get("step_type", "")

            if detail == "user":
                # Return only UI-friendly data
                ui_data = content.get("ui", {})
                thinking_steps.append({
                    "seq": event.get("step_number") or event.get("seq"),
                    "step_type": step_type,
                    "summary": ui_data.get("summary", content.get("summary", "")),
                    "status": ui_data.get("status", "done"),
                })
            elif detail == "internal":
                # Return full internal trace
                internal_data = content.get("internal", {})
                thinking_steps.append({
                    "seq": event.get("step_number") or event.get("seq"),
                    "step_type": step_type,
                    "raw_content": internal_data.get("raw_content", ""),
                    "messages_sent": internal_data.get("messages_sent", []),
                    "tokens": internal_data.get("tokens", {}),
                    "timing_ms": event.get("duration_ms") or internal_data.get("timing_ms", 0),
                })
            else:  # full
                # Return everything
                thinking_steps.append({
                    "seq": event.get("step_number") or event.get("seq"),
                    "step_type": step_type,
                    "internal": content.get("internal", {}),
                    "ui": content.get("ui", {}),
                })

        return {
            "run_id": run_id,
            "thinking_summary": run.get("thinking_summary", ""),
            "strategy": run.get("model_config", {}).get("thinking", {}).get("default_strategy", "unknown"),
            "steps": thinking_steps,
            "detail_level": detail,
        }

    # --- Trace Events (granular timeline for multi-step agent flows) ---

    async def add_trace_event(
        self,
        run_id: str,
        event_type: str,
        content: dict,
        actor: str = "system",
        event_status: str = "success",
        endpoint: Optional[str] = None,
        attempt: int = 1,
        parent_event_id: Optional[str] = None,
        step_number: Optional[int] = None,
        duration_ms: Optional[int] = None,
        token_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Add trace event with atomic seq allocation.

        Uses BEGIN IMMEDIATE to ensure sequential ordering even under concurrent access.

        Args:
            run_id: The run ID to associate with.
            event_type: Type of event (llm_request, llm_response, reasoning, tool_call, tool_response, error, retry).
            content: Event payload as dict (will be JSON serialized).
            actor: Who created the event (model, system, tool:<name>).
            event_status: Status (pending, success, error, skipped).
            endpoint: API endpoint used (/v1/responses or /v1/chat/completions).
            attempt: Retry attempt number.
            parent_event_id: Parent event ID for linking (e.g., tool_response -> tool_call).
            step_number: Agent step number (1, 2, 3...).
            duration_ms: Duration of the operation.
            token_count: Number of tokens used.
            error_message: Error message if event_status is "error".

        Returns:
            The created event ID.
        """
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        content_json = json.dumps(content, ensure_ascii=False)

        # Use lock + BEGIN IMMEDIATE for atomic seq allocation
        # The lock ensures single-threaded access within this process
        # BEGIN IMMEDIATE handles cross-process coordination in production
        async with self._seq_lock:
            await self.db.conn.execute("BEGIN IMMEDIATE")
            try:
                # Get next seq atomically
                async with self.db.conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM trace_events WHERE run_id = ?",
                    (run_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    seq = row[0]

                # Insert with allocated seq
                await self.db.conn.execute(
                    """
                    INSERT INTO trace_events (
                        id, run_id, seq, created_at,
                        event_type, event_status, actor,
                        endpoint, attempt, content_json,
                        parent_event_id, step_number,
                        duration_ms, token_count, error_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, run_id, seq, now,
                        event_type, event_status, actor,
                        endpoint, attempt, content_json,
                        parent_event_id, step_number,
                        duration_ms, token_count, error_message
                    ),
                )

                await self.db.conn.execute("COMMIT")
            except Exception:
                await self.db.conn.execute("ROLLBACK")
                raise

        return event_id

    async def update_trace_event(
        self,
        event_id: str,
        event_status: Optional[str] = None,
        duration_ms: Optional[int] = None,
        token_count: Optional[int] = None,
        error_message: Optional[str] = None,
        content: Optional[dict] = None,
    ) -> None:
        """Update an existing trace event.

        Useful for updating pending events when operation completes.
        """
        updates = []
        values = []

        if event_status is not None:
            updates.append("event_status = ?")
            values.append(event_status)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            values.append(duration_ms)
        if token_count is not None:
            updates.append("token_count = ?")
            values.append(token_count)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)
        if content is not None:
            updates.append("content_json = ?")
            values.append(json.dumps(content, ensure_ascii=False))

        if updates:
            values.append(event_id)
            await self.db.conn.execute(
                f"UPDATE trace_events SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            await self.db.conn.commit()

    async def get_trace_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        step_number: Optional[int] = None,
    ) -> List[dict[str, Any]]:
        """Get trace events for a run in sequential order.

        Args:
            run_id: The run ID.
            event_type: Optional filter by event type.
            step_number: Optional filter by step number.

        Returns:
            List of trace events in seq order.
        """
        query = "SELECT * FROM trace_events WHERE run_id = ?"
        params: List[Any] = [run_id]

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if step_number is not None:
            query += " AND step_number = ?"
            params.append(step_number)

        query += " ORDER BY seq ASC"

        async with self.db.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            events = []
            for row in rows:
                event = dict(row)
                event["content"] = json.loads(event.pop("content_json", "{}"))
                events.append(event)
            return events

    async def get_trace_events_for_conversation(
        self,
        conversation_id: str,
    ) -> List[dict[str, Any]]:
        """Get all trace events for all runs in a conversation.

        Joins trace_events with runs to include user_message for context.
        Events are ordered chronologically across all runs.

        Args:
            conversation_id: The conversation ID.

        Returns:
            List of trace events with run context.
        """
        query = """
            SELECT te.*, r.user_message
            FROM trace_events te
            JOIN runs r ON te.run_id = r.run_id
            WHERE r.conversation_id = ?
            ORDER BY te.created_at ASC, te.seq ASC
        """

        async with self.db.conn.execute(query, [conversation_id]) as cursor:
            rows = await cursor.fetchall()
            events = []
            for row in rows:
                event = dict(row)
                event["content"] = json.loads(event.pop("content_json", "{}"))
                events.append(event)
            return events

    async def get_run_timeline(
        self,
        run_id: str,
    ) -> dict[str, Any]:
        """Get complete timeline for a run with all events.

        Returns structured data suitable for UI display or debugging.
        """
        run = await self.get_run(run_id)
        if not run:
            return {"error": "Run not found"}

        events = await self.get_trace_events(run_id)

        # Group events by step_number if available
        steps: dict[int, List[dict]] = {}
        for event in events:
            step = event.get("step_number") or 0
            if step not in steps:
                steps[step] = []
            steps[step].append(event)

        return {
            "run_id": run_id,
            "status": run.get("status"),
            "created_at": run.get("created_at"),
            "events": events,
            "events_by_step": steps,
            "total_events": len(events),
        }

    async def delete_run(self, run_id: str) -> None:
        """Delete a run and all associated trace events (void).

        Used when a run is aborted before completion - no partial data saved.
        Temporarily disables foreign key checks to handle cross-references.

        Args:
            run_id: The run ID to delete.
        """
        try:
            await self.db.conn.execute("PRAGMA foreign_keys = OFF")

            # Delete trace_events for this run
            await self.db.conn.execute(
                "DELETE FROM trace_events WHERE run_id = ?",
                (run_id,)
            )

            # Delete the run itself
            await self.db.conn.execute(
                "DELETE FROM runs WHERE run_id = ?",
                (run_id,)
            )

            await self.db.conn.commit()
        finally:
            await self.db.conn.execute("PRAGMA foreign_keys = ON")

