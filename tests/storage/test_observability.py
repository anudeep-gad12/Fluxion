"""Tests for observability gap fixes: approval audit, result_detail, run_events, run_artifacts."""

import uuid
import pytest
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


async def _setup_db():
    """Create an in-memory DB with schema + migrations."""
    db = Database(":memory:")
    await db.connect()
    return db


async def _setup_run(db):
    """Create prerequisite conversation + run, return (repo, trace_repo, run_id, step, tool_call)."""
    repo = AgentRepo(db)
    trace_repo = TraceRepo(db)

    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    await db.conn.execute(
        "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
        (conv_id, "Test", "2024-01-01T10:00:00Z", "active"),
    )
    await db.conn.commit()

    run_id = str(uuid.uuid4())
    await trace_repo.create_run(run_id, conv_id, "test", "agent", {})

    step = await repo.create_step(run_id, 1, "tool_calling")
    tool_call = await repo.create_tool_call(
        run_id, step["id"], "write_file", {"file_path": "/tmp/test.py"}, "key-1"
    )
    return repo, trace_repo, run_id, step, tool_call


class TestApprovalDecision:
    """Tests for approval_decision column on agent_tool_calls."""

    @pytest.mark.asyncio
    async def test_approval_decision_column_exists(self):
        """Test that migration adds approval columns."""
        db = await _setup_db()
        cursor = await db.conn.execute("PRAGMA table_info(agent_tool_calls)")
        columns = await cursor.fetchall()
        col_names = [col["name"] for col in columns]

        assert "approval_decision" in col_names
        assert "approval_policy" in col_names
        assert "approval_decided_at" in col_names
        await db.close()

    @pytest.mark.asyncio
    async def test_write_and_read_approval_decision(self):
        """Test storing and retrieving approval decision."""
        db = await _setup_db()
        repo, _, _, _, tool_call = await _setup_run(db)

        await repo.update_tool_call(
            tool_call["id"],
            approval_decision="approved",
            approval_policy="strict",
            approval_decided_at="2024-01-01T10:00:01Z",
        )

        updated = await repo.get_tool_call(tool_call["id"])
        assert updated["approval_decision"] == "approved"
        assert updated["approval_policy"] == "strict"
        assert updated["approval_decided_at"] == "2024-01-01T10:00:01Z"
        await db.close()

    @pytest.mark.asyncio
    async def test_denied_approval(self):
        """Test storing denied approval."""
        db = await _setup_db()
        repo, _, _, _, tool_call = await _setup_run(db)

        await repo.update_tool_call(
            tool_call["id"],
            approval_decision="denied",
            approval_policy="relaxed",
            approval_decided_at="2024-01-01T10:00:02Z",
        )

        updated = await repo.get_tool_call(tool_call["id"])
        assert updated["approval_decision"] == "denied"
        assert updated["approval_policy"] == "relaxed"
        await db.close()

    @pytest.mark.asyncio
    async def test_auto_approval(self):
        """Test storing auto-approved decision."""
        db = await _setup_db()
        repo, _, _, _, tool_call = await _setup_run(db)

        await repo.update_tool_call(
            tool_call["id"],
            approval_decision="auto",
            approval_policy="yolo",
            approval_decided_at="2024-01-01T10:00:03Z",
        )

        updated = await repo.get_tool_call(tool_call["id"])
        assert updated["approval_decision"] == "auto"
        assert updated["approval_policy"] == "yolo"
        await db.close()


class TestResultDetail:
    """Tests for result_detail column on agent_tool_calls."""

    @pytest.mark.asyncio
    async def test_result_detail_column_exists(self):
        """Test that migration adds result_detail column."""
        db = await _setup_db()
        cursor = await db.conn.execute("PRAGMA table_info(agent_tool_calls)")
        columns = await cursor.fetchall()
        col_names = [col["name"] for col in columns]

        assert "result_detail" in col_names
        await db.close()

    @pytest.mark.asyncio
    async def test_store_and_retrieve_result_detail(self):
        """Test storing full result detail."""
        db = await _setup_db()
        repo, _, _, _, tool_call = await _setup_run(db)

        detail = '{"content": "file contents here", "bytes_written": 1234}'
        await repo.update_tool_call(
            tool_call["id"],
            status="success",
            result_summary="Wrote 1234 bytes",
            result_detail=detail,
        )

        updated = await repo.get_tool_call(tool_call["id"])
        assert updated["result_detail"] == detail
        assert updated["result_summary"] == "Wrote 1234 bytes"
        await db.close()

    @pytest.mark.asyncio
    async def test_result_detail_null_by_default(self):
        """Test that result_detail is null for read-only tools."""
        db = await _setup_db()
        repo, _, run_id, step, _ = await _setup_run(db)

        tc = await repo.create_tool_call(
            run_id, step["id"], "web_search", {"query": "test"}, "key-read"
        )
        await repo.update_tool_call(tc["id"], status="success", result_summary="Found 5 results")

        updated = await repo.get_tool_call(tc["id"])
        assert updated["result_detail"] is None
        await db.close()


class TestRunEvents:
    """Tests for run_events table CRUD."""

    @pytest.mark.asyncio
    async def test_run_events_table_exists(self):
        """Test that run_events table is created."""
        db = await _setup_db()
        cursor = await db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_events'"
        )
        row = await cursor.fetchone()
        assert row is not None
        await db.close()

    @pytest.mark.asyncio
    async def test_create_and_get_run_events(self):
        """Test creating and retrieving run events."""
        db = await _setup_db()
        repo, _, run_id, _, _ = await _setup_run(db)

        # Create events
        e1 = await repo.create_run_event(run_id, 1, "agent_started", {"query": "test"})
        e2 = await repo.create_run_event(run_id, 2, "thinking", {"text": "analyzing..."})
        e3 = await repo.create_run_event(run_id, 3, "tool_start", {"tool": "web_search"})

        assert e1["id"] is not None
        assert e1["seq"] == 1
        assert e1["event_type"] == "agent_started"

        # Get all events
        events = await repo.get_run_events(run_id)
        assert len(events) == 3
        assert events[0]["seq"] == 1
        assert events[1]["seq"] == 2
        assert events[2]["seq"] == 3
        assert events[0]["event_data"]["query"] == "test"
        assert events[1]["event_data"]["text"] == "analyzing..."
        await db.close()

    @pytest.mark.asyncio
    async def test_run_events_empty_for_new_run(self):
        """Test that new run has no events."""
        db = await _setup_db()
        repo, _, run_id, _, _ = await _setup_run(db)

        events = await repo.get_run_events(run_id)
        assert events == []
        await db.close()

    @pytest.mark.asyncio
    async def test_run_events_isolation(self):
        """Test that events are scoped to their run."""
        db = await _setup_db()
        repo, trace_repo, run_id, _, _ = await _setup_run(db)

        # Create second run (reuse existing conversation)
        conv_cursor = await db.conn.execute("SELECT conversation_id FROM conversations LIMIT 1")
        conv_row = await conv_cursor.fetchone()
        conv_id = conv_row["conversation_id"]
        run_id_2 = str(uuid.uuid4())
        await trace_repo.create_run(run_id_2, conv_id, "test", "agent", {})

        await repo.create_run_event(run_id, 1, "agent_started", {})
        await repo.create_run_event(run_id_2, 1, "agent_started", {})
        await repo.create_run_event(run_id, 2, "thinking", {})

        events_1 = await repo.get_run_events(run_id)
        events_2 = await repo.get_run_events(run_id_2)
        assert len(events_1) == 2
        assert len(events_2) == 1
        await db.close()


class TestRunArtifacts:
    """Tests for run_artifacts table CRUD."""

    @pytest.mark.asyncio
    async def test_run_artifacts_table_exists(self):
        """Test that run_artifacts table is created."""
        db = await _setup_db()
        cursor = await db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_artifacts'"
        )
        row = await cursor.fetchone()
        assert row is not None
        await db.close()

    @pytest.mark.asyncio
    async def test_create_and_get_run_artifacts(self):
        """Test creating and retrieving run artifacts."""
        db = await _setup_db()
        repo, _, run_id, _, tool_call = await _setup_run(db)

        # Create artifacts
        a1 = await repo.create_run_artifact(
            run_id=run_id,
            artifact_type="file_write",
            file_path="/tmp/test.py",
            action="write_file",
            detail="Wrote 500 bytes",
            tool_call_id=tool_call["id"],
        )
        a2 = await repo.create_run_artifact(
            run_id=run_id,
            artifact_type="file_edit",
            file_path="/tmp/other.py",
            action="edit_file",
            detail="Replaced 3 lines",
            tool_call_id=tool_call["id"],
        )

        assert a1["id"] is not None
        assert a1["artifact_type"] == "file_write"
        assert a1["file_path"] == "/tmp/test.py"

        # Get all artifacts
        artifacts = await repo.get_run_artifacts(run_id)
        assert len(artifacts) == 2
        assert artifacts[0]["artifact_type"] == "file_write"
        assert artifacts[1]["artifact_type"] == "file_edit"
        await db.close()

    @pytest.mark.asyncio
    async def test_artifact_without_tool_call_id(self):
        """Test creating artifact without tool_call_id."""
        db = await _setup_db()
        repo, _, run_id, _, _ = await _setup_run(db)

        a = await repo.create_run_artifact(
            run_id=run_id,
            artifact_type="command_run",
            file_path="ls -la",
            action="bash_tool",
        )

        assert a["tool_call_id"] is None
        assert a["detail"] is None

        artifacts = await repo.get_run_artifacts(run_id)
        assert len(artifacts) == 1
        await db.close()

    @pytest.mark.asyncio
    async def test_artifacts_empty_for_new_run(self):
        """Test that new run has no artifacts."""
        db = await _setup_db()
        repo, _, run_id, _, _ = await _setup_run(db)

        artifacts = await repo.get_run_artifacts(run_id)
        assert artifacts == []
        await db.close()


class TestUpdatedAtTimestamps:
    """Tests for updated_at columns on conversations and agent_steps."""

    @pytest.mark.asyncio
    async def test_conversations_updated_at_column_exists(self):
        """Test that conversations table has updated_at column."""
        db = await _setup_db()
        cursor = await db.conn.execute("PRAGMA table_info(conversations)")
        columns = await cursor.fetchall()
        col_names = [col["name"] for col in columns]

        assert "updated_at" in col_names
        await db.close()

    @pytest.mark.asyncio
    async def test_agent_steps_updated_at_column_exists(self):
        """Test that agent_steps table has updated_at column."""
        db = await _setup_db()
        cursor = await db.conn.execute("PRAGMA table_info(agent_steps)")
        columns = await cursor.fetchall()
        col_names = [col["name"] for col in columns]

        assert "updated_at" in col_names
        await db.close()
