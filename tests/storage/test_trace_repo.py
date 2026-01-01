"""Tests for TraceRepo."""

import asyncio
import uuid
import pytest
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.trace_repo import TraceRepo


class TestTraceEventsSeq:
    """Tests for trace_events sequential ordering."""

    @pytest.mark.asyncio
    async def test_trace_seq_monotonic_under_concurrency(self):
        """Test that seq values are strictly monotonic under concurrent writes.

        This verifies that BEGIN IMMEDIATE provides proper atomic allocation
        even when multiple coroutines attempt to insert simultaneously.
        """
        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        # Create a conversation and run
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await repo.create_run(
            run_id=run_id,
            conversation_id="conv-1",
            profile_name="test",
            mode="chat",
            model_config={},
        )

        # Concurrently add 50 trace events
        async def add_event(i: int) -> str:
            return await repo.add_trace_event(
                run_id=run_id,
                event_type="test",
                content={"index": i},
                actor="test",
                event_status="success",
            )

        # Run all adds concurrently
        event_ids = await asyncio.gather(*[add_event(i) for i in range(50)])

        # Verify all 50 events were created
        assert len(event_ids) == 50
        assert len(set(event_ids)) == 50  # All unique IDs

        # Get all events and verify seq ordering
        events = await repo.get_trace_events(run_id)

        # Extract seq values
        seqs = [e["seq"] for e in events]

        # Verify all seqs are unique
        assert len(seqs) == len(set(seqs)), "Seq values must be unique"

        # Verify seqs are monotonically increasing (1, 2, 3, ...)
        assert seqs == sorted(seqs), "Seqs must be monotonic"
        assert seqs == list(range(1, 51)), f"Seqs must be 1-50, got {seqs[:5]}...{seqs[-5:]}"

        await db.close()

    @pytest.mark.asyncio
    async def test_trace_seq_starts_at_one(self):
        """Verify first event gets seq=1."""
        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await repo.create_run(
            run_id=run_id,
            conversation_id="conv-1",
            profile_name="test",
            mode="chat",
            model_config={},
        )

        # Add first event
        await repo.add_trace_event(
            run_id=run_id,
            event_type="first",
            content={"test": True},
            actor="test",
            event_status="success",
        )

        events = await repo.get_trace_events(run_id)
        assert len(events) == 1
        assert events[0]["seq"] == 1

        await db.close()

    @pytest.mark.asyncio
    async def test_trace_seq_per_run_isolation(self):
        """Verify seq is independent per run_id."""
        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id_1 = str(uuid.uuid4())
        run_id_2 = str(uuid.uuid4())

        await repo.create_run(run_id_1, "conv-1", "test", "chat", {})
        await repo.create_run(run_id_2, "conv-1", "test", "chat", {})

        # Add events to both runs
        await repo.add_trace_event(run_id_1, "test", {"run": 1}, "test", "success")
        await repo.add_trace_event(run_id_1, "test", {"run": 1}, "test", "success")
        await repo.add_trace_event(run_id_2, "test", {"run": 2}, "test", "success")
        await repo.add_trace_event(run_id_1, "test", {"run": 1}, "test", "success")

        events_1 = await repo.get_trace_events(run_id_1)
        events_2 = await repo.get_trace_events(run_id_2)

        # Run 1 should have seq 1, 2, 3
        assert [e["seq"] for e in events_1] == [1, 2, 3]

        # Run 2 should have seq 1 (independent)
        assert [e["seq"] for e in events_2] == [1]

        await db.close()
