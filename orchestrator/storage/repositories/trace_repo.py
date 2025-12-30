"""Repository for runs and model calls."""

import json
from datetime import datetime, timezone
from typing import Any, Optional, List
from orchestrator.storage.db import Database

class TraceRepo:
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
    ) -> dict[str, Any]:
        """Start a new run."""
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
                status, usage_stats
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, conversation_id, now,
                user_message, system_prompt,
                profile_name, mode, config_snapshot,
                "running", usage_stats
            ),
        )
        await self.db.conn.commit()
        return {"run_id": run_id, "status": "running"}

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

    async def list_runs(
        self, 
        conversation_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[dict[str, Any]]:
        """List runs, optionally filtering by conversation."""
        query = "SELECT * FROM runs"
        params = []
        
        if conversation_id:
            query += " WHERE conversation_id = ?"
            params.append(conversation_id)
            
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

    # Alias for backward compatibility
    async def list_traces(self, *args, **kwargs):
        return await self.list_runs(*args, **kwargs)

    # --- Model Calls (formerly reasoning_traces) ---

    async def add_model_call(
        self,
        run_id: str,
        seq: int,
        step_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Add a model call record."""
        now = datetime.now(timezone.utc).isoformat()
        import uuid
        id = str(uuid.uuid4())
        
        # Ensure metadata is valid JSON
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        
        await self.db.conn.execute(
            """
            INSERT INTO model_calls (id, run_id, seq, created_at, step_type, content, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, run_id, seq, now, step_type, content, meta_json),
        )
        await self.db.conn.commit()

    # Alias for backward compatibility
    async def add_reasoning_step(self, *args, **kwargs):
        return await self.add_model_call(*args, **kwargs)

    async def get_model_calls(self, run_id: str) -> List[dict[str, Any]]:
        """Get all model calls for a run."""
        async with self.db.conn.execute(
            "SELECT * FROM model_calls WHERE run_id = ? ORDER BY seq ASC",
            (run_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            calls = []
            for row in rows:
                call = dict(row)
                call["metadata"] = json.loads(call.pop("metadata_json", "{}"))
                calls.append(call)
            return calls

    # Alias for backward compatibility
    async def get_reasoning_traces(self, run_id: str):
        return await self.get_model_calls(run_id)

    # --- Thinking Traces (dual-layer) ---

    async def add_thinking_step(
        self,
        run_id: str,
        step: "ThinkingStep",
    ) -> None:
        """Store both internal and UI trace for a thinking step.

        Args:
            run_id: The run ID to associate with.
            step: ThinkingStep with both internal and UI data.
        """
        from orchestrator.thinking.base import ThinkingStep

        now = datetime.now(timezone.utc).isoformat()
        import uuid
        id = str(uuid.uuid4())

        # Build metadata with both internal and UI sections
        metadata = {
            "internal": step.to_internal_dict(),
            "ui": step.to_ui_dict(),
        }
        meta_json = json.dumps(metadata, ensure_ascii=False)

        await self.db.conn.execute(
            """
            INSERT INTO model_calls (id, run_id, seq, created_at, step_type, content, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, run_id, step.seq, now, step.step_type, step.ui_summary, meta_json),
        )
        await self.db.conn.commit()

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

        # Get all model calls (thinking steps)
        calls = await self.get_model_calls(run_id)

        # Filter to thinking-related steps
        thinking_steps = []
        for call in calls:
            meta = call.get("metadata", {})
            step_type = call.get("step_type", "")

            if detail == "user":
                # Return only UI-friendly data
                ui_data = meta.get("ui", {})
                thinking_steps.append({
                    "seq": call.get("seq"),
                    "step_type": step_type,
                    "summary": ui_data.get("summary", call.get("content", "")),
                    "status": ui_data.get("status", "done"),
                })
            elif detail == "internal":
                # Return full internal trace
                internal_data = meta.get("internal", {})
                thinking_steps.append({
                    "seq": call.get("seq"),
                    "step_type": step_type,
                    "raw_content": internal_data.get("raw_content", call.get("content", "")),
                    "messages_sent": internal_data.get("messages_sent", []),
                    "tokens": internal_data.get("tokens", {}),
                    "timing_ms": internal_data.get("timing_ms", 0),
                })
            else:  # full
                # Return everything
                thinking_steps.append({
                    "seq": call.get("seq"),
                    "step_type": step_type,
                    "internal": meta.get("internal", {}),
                    "ui": meta.get("ui", {}),
                })

        return {
            "run_id": run_id,
            "thinking_summary": run.get("thinking_summary", ""),
            "strategy": run.get("model_config", {}).get("thinking", {}).get("default_strategy", "unknown"),
            "steps": thinking_steps,
            "detail_level": detail,
        }
