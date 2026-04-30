"""Tests for AgentRepo."""

import uuid
import pytest
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


class TestAgentSteps:
    """Tests for agent_steps CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_step(self):
        """Test creating an agent step."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Create prerequisite data
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(
            run_id=run_id,
            conversation_id="conv-1",
            profile_name="test",
            mode="agent",
            model_config={},
        )

        # Create step
        step = await repo.create_step(
            run_id=run_id,
            step_number=1,
            state="planning",
            thinking_text="Let me search for information...",
            decision="call_tool",
        )

        assert step["id"] is not None
        assert step["run_id"] == run_id
        assert step["step_number"] == 1
        assert step["state"] == "planning"
        assert step["created_at"] is not None

        await db.close()

    @pytest.mark.asyncio
    async def test_update_step(self):
        """Test updating an agent step."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        step = await repo.create_step(run_id, 1, "planning")

        # Update step
        await repo.update_step(
            step["id"],
            state="complete",
            completed_at="2024-01-01T10:01:00Z",
            decision="synthesize",
        )

        # Verify update
        updated = await repo.get_step(step["id"])
        assert updated["state"] == "complete"
        assert updated["completed_at"] == "2024-01-01T10:01:00Z"
        assert updated["decision"] == "synthesize"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_steps_for_run(self):
        """Test getting all steps for a run in order."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        # Create multiple steps
        await repo.create_step(run_id, 1, "planning")
        await repo.create_step(run_id, 2, "tool_calling")
        await repo.create_step(run_id, 3, "synthesizing")

        # Get all steps
        steps = await repo.get_steps_for_run(run_id)
        assert len(steps) == 3
        assert steps[0]["step_number"] == 1
        assert steps[1]["step_number"] == 2
        assert steps[2]["step_number"] == 3

        await db.close()

    @pytest.mark.asyncio
    async def test_get_step_by_number(self):
        """Test getting a step by run_id and step_number."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        await repo.create_step(run_id, 1, "planning")
        await repo.create_step(run_id, 2, "tool_calling")

        # Get specific step
        step = await repo.get_step_by_number(run_id, 2)
        assert step is not None
        assert step["step_number"] == 2
        assert step["state"] == "tool_calling"

        # Non-existent step
        step = await repo.get_step_by_number(run_id, 5)
        assert step is None

        await db.close()

    @pytest.mark.asyncio
    async def test_get_latest_step(self):
        """Test getting the most recent step for a run."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        await repo.create_step(run_id, 1, "planning")
        await repo.create_step(run_id, 2, "tool_calling")
        await repo.create_step(run_id, 3, "synthesizing")

        # Get latest
        latest = await repo.get_latest_step(run_id)
        assert latest is not None
        assert latest["step_number"] == 3
        assert latest["state"] == "synthesizing"

        await db.close()


class TestAgentToolCalls:
    """Tests for agent_tool_calls CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_tool_call(self):
        """Test creating a tool call."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")

        # Create tool call
        tool_call = await repo.create_tool_call(
            run_id=run_id,
            step_id=step["id"],
            tool_name="web_search",
            arguments={"query": "population of Tokyo"},
            idempotency_key="search-tokyo-1",
        )

        assert tool_call["id"] is not None
        assert tool_call["tool_name"] == "web_search"
        assert tool_call["arguments"] == {"query": "population of Tokyo"}
        assert tool_call["status"] == "pending"
        assert tool_call["idempotency_key"] == "search-tokyo-1"

        await db.close()

    @pytest.mark.asyncio
    async def test_update_tool_call(self):
        """Test updating a tool call."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")

        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {"query": "test"}, "key-1"
        )

        # Update tool call
        await repo.update_tool_call(
            tool_call["id"],
            status="success",
            started_at="2024-01-01T10:00:00Z",
            completed_at="2024-01-01T10:00:05Z",
            duration_ms=5000,
            result_summary="Found 10 results",
        )

        # Verify update
        updated = await repo.get_tool_call(tool_call["id"])
        assert updated["status"] == "success"
        assert updated["duration_ms"] == 5000
        assert updated["result_summary"] == "Found 10 results"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_tool_call_by_idempotency_key(self):
        """Test finding a tool call by idempotency key for crash recovery."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")

        await repo.create_tool_call(
            run_id, step["id"], "web_search", {"query": "test"}, "unique-key-123"
        )

        # Find by idempotency key
        found = await repo.get_tool_call_by_idempotency_key(run_id, "unique-key-123")
        assert found is not None
        assert found["tool_name"] == "web_search"

        # Non-existent key
        not_found = await repo.get_tool_call_by_idempotency_key(run_id, "other-key")
        assert not_found is None

        await db.close()

    @pytest.mark.asyncio
    async def test_get_pending_tool_calls(self):
        """Test getting pending/running tool calls for crash recovery."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")

        # Create tool calls with various statuses
        tc1 = await repo.create_tool_call(
            run_id, step["id"], "web_search", {"query": "test1"}, "key-1"
        )
        tc2 = await repo.create_tool_call(
            run_id, step["id"], "web_search", {"query": "test2"}, "key-2"
        )
        tc3 = await repo.create_tool_call(
            run_id, step["id"], "web_search", {"query": "test3"}, "key-3"
        )

        # Update statuses
        await repo.update_tool_call(tc1["id"], status="success")
        await repo.update_tool_call(tc2["id"], status="running")
        # tc3 remains pending

        # Get pending/running
        pending = await repo.get_pending_tool_calls(run_id)
        assert len(pending) == 2
        tool_call_ids = [tc["id"] for tc in pending]
        assert tc2["id"] in tool_call_ids  # running
        assert tc3["id"] in tool_call_ids  # pending
        assert tc1["id"] not in tool_call_ids  # success

        await db.close()

    @pytest.mark.asyncio
    async def test_get_tool_calls_for_step(self):
        """Test getting all tool calls for a step."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step1 = await repo.create_step(run_id, 1, "tool_calling")
        step2 = await repo.create_step(run_id, 2, "tool_calling")

        # Create tool calls for different steps
        await repo.create_tool_call(run_id, step1["id"], "web_search", {}, "key-1")
        await repo.create_tool_call(run_id, step1["id"], "web_extract", {}, "key-2")
        await repo.create_tool_call(run_id, step2["id"], "python_execute", {}, "key-3")

        # Get tool calls for step 1
        calls = await repo.get_tool_calls_for_step(step1["id"])
        assert len(calls) == 2
        tool_names = [tc["tool_name"] for tc in calls]
        assert "web_search" in tool_names
        assert "web_extract" in tool_names

        await db.close()


class TestAgentCitations:
    """Tests for agent_citations CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_citation(self):
        """Test creating a citation."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")
        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {}, "key-1"
        )

        # Create citation
        citation = await repo.create_citation(
            run_id=run_id,
            tool_call_id=tool_call["id"],
            source_url="https://example.com/article",
            snippet="Tokyo has a population of 14 million.",
            title="Tokyo Demographics",
        )

        assert citation["id"] is not None
        assert citation["source_url"] == "https://example.com/article"
        assert citation["snippet"] == "Tokyo has a population of 14 million."
        assert citation["title"] == "Tokyo Demographics"
        assert citation["used_in_answer"] is False

        await db.close()

    @pytest.mark.asyncio
    async def test_mark_citation_used(self):
        """Test marking a citation as used in the answer."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")
        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {}, "key-1"
        )
        citation = await repo.create_citation(
            run_id, tool_call["id"], "https://example.com", "test snippet"
        )

        # Mark as used
        await repo.mark_citation_used(citation["id"])

        # Verify (SQLite returns 1 for True)
        updated = await repo.get_citation(citation["id"])
        assert updated["used_in_answer"] == True  # noqa: E712

        await db.close()

    @pytest.mark.asyncio
    async def test_mark_citations_used_batch(self):
        """Test marking multiple citations as used."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")
        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {}, "key-1"
        )

        # Create multiple citations
        c1 = await repo.create_citation(
            run_id, tool_call["id"], "https://example1.com", "snippet 1"
        )
        c2 = await repo.create_citation(
            run_id, tool_call["id"], "https://example2.com", "snippet 2"
        )
        c3 = await repo.create_citation(
            run_id, tool_call["id"], "https://example3.com", "snippet 3"
        )

        # Mark c1 and c3 as used
        await repo.mark_citations_used([c1["id"], c3["id"]])

        # Verify (SQLite returns 1/0 for True/False)
        citations = await repo.get_citations_for_run(run_id)
        used_map = {c["id"]: c["used_in_answer"] for c in citations}
        assert used_map[c1["id"]] == True  # noqa: E712
        assert used_map[c2["id"]] == False  # noqa: E712
        assert used_map[c3["id"]] == True  # noqa: E712

        await db.close()

    @pytest.mark.asyncio
    async def test_get_citations_for_run(self):
        """Test getting all citations for a run."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")
        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {}, "key-1"
        )

        # Create citations
        await repo.create_citation(run_id, tool_call["id"], "https://a.com", "A")
        await repo.create_citation(run_id, tool_call["id"], "https://b.com", "B")
        await repo.create_citation(run_id, tool_call["id"], "https://c.com", "C")

        # Get all citations
        citations = await repo.get_citations_for_run(run_id)
        assert len(citations) == 3
        urls = [c["source_url"] for c in citations]
        assert "https://a.com" in urls
        assert "https://b.com" in urls
        assert "https://c.com" in urls

        await db.close()


class TestRunAgentState:
    """Tests for run agent state operations."""

    @pytest.mark.asyncio
    async def test_update_run_agent_state(self):
        """Test updating agent state on runs table."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        # Update agent state
        await repo.update_run_agent_state(
            run_id,
            agent_state="tool_calling",
            current_step=2,
            max_steps=10,
        )

        # Verify
        run = await trace_repo.get_run(run_id)
        assert run["agent_state"] == "tool_calling"
        assert run["current_step"] == 2
        assert run["max_steps"] == 10
        assert run["updated_at"] is not None

        await db.close()

    @pytest.mark.asyncio
    async def test_get_interrupted_runs(self):
        """Test getting interrupted runs for startup recovery."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id_1 = str(uuid.uuid4())
        run_id_2 = str(uuid.uuid4())
        run_id_3 = str(uuid.uuid4())

        # Create runs with different modes and statuses
        await trace_repo.create_run(run_id_1, "conv-1", "test", "agent", {})
        await trace_repo.create_run(run_id_2, "conv-1", "test", "agent", {})
        await trace_repo.create_run(run_id_3, "conv-1", "test", "chat", {})

        # Update statuses
        await trace_repo.update_run(run_id_1, status="running")  # Should be returned
        await trace_repo.update_run(run_id_2, status="succeeded")  # Should not be returned
        await trace_repo.update_run(run_id_3, status="running")  # mode=chat, should not be returned

        # Get interrupted runs
        interrupted = await repo.get_interrupted_runs()
        assert len(interrupted) == 1
        assert interrupted[0]["run_id"] == run_id_1

        await db.close()


class TestCascadeDelete:
    """Tests for cascade deletion."""

    @pytest.mark.asyncio
    async def test_delete_agent_data_for_run(self):
        """Test deleting all agent data for a run."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        # Create agent data
        step = await repo.create_step(run_id, 1, "tool_calling")
        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {}, "key-1"
        )
        await repo.create_citation(
            run_id, tool_call["id"], "https://example.com", "test"
        )

        # Verify data exists
        steps = await repo.get_steps_for_run(run_id)
        assert len(steps) == 1
        tool_calls = await repo.get_tool_calls_for_run(run_id)
        assert len(tool_calls) == 1
        citations = await repo.get_citations_for_run(run_id)
        assert len(citations) == 1

        # Delete agent data
        await repo.delete_agent_data_for_run(run_id)

        # Verify all deleted
        steps = await repo.get_steps_for_run(run_id)
        assert len(steps) == 0
        tool_calls = await repo.get_tool_calls_for_run(run_id)
        assert len(tool_calls) == 0
        citations = await repo.get_citations_for_run(run_id)
        assert len(citations) == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_cascade_delete_with_fk_enabled(self):
        """Test that agent data is deleted when run is deleted with FK enabled.

        Note: trace_repo.delete_run() disables FK, so cascade doesn't work there.
        This test verifies cascade works with direct DELETE and FK enabled.
        """
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})

        # Create agent data
        step = await repo.create_step(run_id, 1, "tool_calling")
        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_search", {}, "key-1"
        )
        await repo.create_citation(
            run_id, tool_call["id"], "https://example.com", "test"
        )

        # Delete run directly with FK enabled (cascade should work)
        # First delete agent data (required due to FK order), then delete run
        await repo.delete_agent_data_for_run(run_id)
        await db.conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        await db.conn.commit()

        # Verify run deleted
        run = await trace_repo.get_run(run_id)
        assert run is None

        # Verify all agent data deleted
        steps = await repo.get_steps_for_run(run_id)
        assert len(steps) == 0
        tool_calls = await repo.get_tool_calls_for_run(run_id)
        assert len(tool_calls) == 0
        citations = await repo.get_citations_for_run(run_id)
        assert len(citations) == 0

        await db.close()


class TestJSONArguments:
    """Tests for JSON serialization of tool arguments."""

    @pytest.mark.asyncio
    async def test_complex_json_arguments(self):
        """Test that complex JSON arguments are properly serialized and deserialized."""
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        # Setup
        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "test", "agent", {})
        step = await repo.create_step(run_id, 1, "tool_calling")

        # Complex arguments
        complex_args = {
            "urls": ["https://a.com", "https://b.com", "https://c.com"],
            "options": {
                "max_depth": 2,
                "include_images": True,
                "filters": ["news", "articles"],
            },
            "unicode_test": "こんにちは世界",
        }

        tool_call = await repo.create_tool_call(
            run_id, step["id"], "web_extract", complex_args, "key-1"
        )

        # Retrieve and verify
        retrieved = await repo.get_tool_call(tool_call["id"])
        assert retrieved["arguments"] == complex_args
        assert retrieved["arguments"]["urls"] == ["https://a.com", "https://b.com", "https://c.com"]
        assert retrieved["arguments"]["unicode_test"] == "こんにちは世界"

        await db.close()


class TestCodingSessionStateRepo:
    """Tests for persisted coding-session state storage."""

    @pytest.mark.asyncio
    async def test_upsert_and_get_coding_session_state(self):
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)
        trace_repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        run_id = str(uuid.uuid4())
        await trace_repo.create_run(run_id, "conv-1", "coding", "agent", {})

        state = {
            "objective": "Implement the UI cleanup",
            "prior_outcomes": ["Reviewed the component tree."],
            "files_inspected": {"ui/src/App.tsx": "Read 80 lines from ui/src/App.tsx"},
            "file_evidence": {
                "ui/src/App.tsx": {
                    "path": "ui/src/App.tsx",
                    "summary": "Read 80 lines from ui/src/App.tsx",
                    "excerpt": "return <AppShell /> | className='space-y-6'",
                    "line_start": 1,
                    "line_end": 80,
                    "content_hash": "abc123",
                }
            },
        }

        await repo.upsert_coding_session_state("conv-1", state, last_run_id=run_id)
        stored = await repo.get_coding_session_state("conv-1")

        assert stored is not None
        assert stored["conversation_id"] == "conv-1"
        assert stored["last_run_id"] == run_id
        assert stored["state"]["objective"] == "Implement the UI cleanup"
        assert (
            stored["state"]["file_evidence"]["ui/src/App.tsx"]["excerpt"]
            == "return <AppShell /> | className='space-y-6'"
        )

        await db.close()

    @pytest.mark.asyncio
    async def test_coding_session_state_cascades_on_conversation_delete(self):
        db = Database(":memory:")
        await db.connect()
        repo = AgentRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )
        await db.conn.commit()

        await repo.upsert_coding_session_state(
            "conv-1",
            {"objective": "Implement follow-up", "prior_outcomes": ["Reviewed UI"]},
        )

        await db.conn.execute(
            "DELETE FROM conversations WHERE conversation_id = ?",
            ("conv-1",),
        )
        await db.conn.commit()

        stored = await repo.get_coding_session_state("conv-1")
        assert stored is None

        await db.close()
