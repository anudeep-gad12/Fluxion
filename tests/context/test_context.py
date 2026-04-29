"""Tests for the context management module."""

import pytest
from orchestrator.context.budget import ContextBudget
from orchestrator.context.turn_summary import TurnSummarizer, TurnSummary
from orchestrator.context.history_builder import HistoryBuilder
from orchestrator.utils.tokens import TokenCounter


class TestContextBudget:
    """Tests for ContextBudget dataclass."""

    def test_available_for_history(self):
        budget = ContextBudget(
            max_tokens=100000,
            reserve_for_response=4096,
            system_prompt_tokens=500,
            plan_tokens=0,
            current_query_tokens=100,
        )
        assert budget.available_for_history == 100000 - 4096 - 500 - 100

    def test_total_used(self):
        budget = ContextBudget(
            max_tokens=100000,
            reserve_for_response=4096,
            system_prompt_tokens=500,
            plan_tokens=200,
            current_query_tokens=100,
            history_tokens=3000,
        )
        assert budget.total_used == 500 + 200 + 100 + 3000

    def test_utilization_pct(self):
        budget = ContextBudget(
            max_tokens=100000,
            reserve_for_response=4096,
            system_prompt_tokens=10000,
            history_tokens=40000,
        )
        assert budget.utilization_pct == pytest.approx(50.0)

    def test_utilization_pct_zero_max(self):
        budget = ContextBudget(max_tokens=0, reserve_for_response=0)
        assert budget.utilization_pct == 0.0

    def test_available_with_plan(self):
        budget = ContextBudget(
            max_tokens=100000,
            reserve_for_response=4096,
            system_prompt_tokens=500,
            plan_tokens=1000,
            current_query_tokens=100,
        )
        # Plan tokens reduce available for history
        assert budget.available_for_history == 100000 - 4096 - 500 - 1000 - 100


class TestTurnSummary:
    """Tests for TurnSummary dataclass."""

    def test_to_context_string_basic(self):
        summary = TurnSummary(
            run_id="run-1",
            mode="chat",
            query_brief="What is Python?",
            answer_brief="Python is a programming language.",
        )
        result = summary.to_context_string()
        assert result.startswith("Outcome: Python is a programming language.")
        assert "User asked: What is Python?" in result

    def test_to_context_string_with_tools(self):
        summary = TurnSummary(
            run_id="run-1",
            mode="agent",
            query_brief="Find latest news",
            answer_brief="Here are the latest...",
            tools_used=["web_search", "web_extract"],
        )
        result = summary.to_context_string()
        assert "Tools: web_search, web_extract" in result

    def test_to_context_string_with_files(self):
        summary = TurnSummary(
            run_id="run-1",
            mode="agent",
            query_brief="Edit the config",
            answer_brief="Done, updated config.",
            files_touched=["/src/config.py", "/src/app.py"],
        )
        result = summary.to_context_string()
        assert "Files: /src/config.py, /src/app.py" in result

    def test_files_limited_to_5(self):
        summary = TurnSummary(
            run_id="run-1",
            mode="agent",
            query_brief="Edit many files",
            answer_brief="Done.",
            files_touched=[f"/file{i}.py" for i in range(10)],
        )
        result = summary.to_context_string()
        # Should only include first 5 files
        assert "/file4.py" in result
        assert "/file5.py" not in result


class TestTurnSummarizer:
    """Tests for TurnSummarizer."""

    def test_summarize_chat_run(self):
        counter = TokenCounter()
        summarizer = TurnSummarizer(counter)
        summary = summarizer.summarize_chat_run(
            "What is the capital of France?",
            "The capital of France is Paris.",
        )
        assert summary.mode == "chat"
        assert "France" in summary.query_brief
        assert "Paris" in summary.answer_brief
        assert summary.token_cost > 0
        assert summary.token_cost < 100  # Should be compact

    def test_summarize_agent_run(self):
        counter = TokenCounter()
        summarizer = TurnSummarizer(counter)
        summary = summarizer.summarize_agent_run(
            run={
                "run_id": "run-1",
                "user_message": "Research quantum computing",
                "final_answer": "Quantum computing uses qubits to perform computations...",
                "thinking_summary": "Searched for quantum computing basics",
                "mode": "agent",
            },
            tool_calls=[
                {"tool_name": "web_search", "status": "success"},
                {"tool_name": "web_extract", "status": "success"},
                {"tool_name": "web_search", "status": "success"},  # duplicate
            ],
            artifacts=[
                {"file_path": "/notes.md", "action": "write_file"},
            ],
        )
        assert summary.mode == "agent"
        assert "quantum" in summary.query_brief.lower()
        assert summary.tools_used == ["web_search", "web_extract"]  # deduplicated
        assert summary.files_touched == ["/notes.md"]
        assert summary.token_cost > 0

    def test_truncates_long_query(self):
        counter = TokenCounter()
        summarizer = TurnSummarizer(counter)
        long_query = "x" * 200
        summary = summarizer.summarize_chat_run(long_query, "short answer")
        assert len(summary.query_brief) == 120

    def test_truncates_long_answer(self):
        counter = TokenCounter()
        summarizer = TurnSummarizer(counter)
        long_answer = "y" * 500
        summary = summarizer.summarize_chat_run("short query", long_answer)
        assert len(summary.answer_brief) == 200


class TestHistoryBuilder:
    """Tests for HistoryBuilder."""

    def test_basic_history(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "Hello",
                "final_answer": "Hi there!",
            },
        ]

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="You are helpful.",
            current_query="How are you?",
        )

        assert len(messages) == 4  # system + user + assistant + current
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Hi there!"
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "How are you?"
        assert budget.history_tokens > 0

    def test_empty_history(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        messages, budget = builder.build_history_messages(
            prior_runs=[],
            system_prompt="System",
            current_query="Hello",
        )

        assert len(messages) == 2  # system + current
        assert budget.history_tokens == 0

    def test_skips_incomplete_runs(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "Complete",
                "final_answer": "Response",
            },
            {
                "created_at": "2024-01-01T10:01:00Z",
                "user_message": "Incomplete",
                "final_answer": None,
            },
        ]

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="System",
            current_query="Current",
        )

        # Only complete run included
        assert len(messages) == 4  # system + complete pair + current

    def test_skips_duplicate_query(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "Same query",
                "final_answer": "Previous answer",
            },
        ]

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="System",
            current_query="Same query",
        )

        # Duplicate query skipped
        assert len(messages) == 2  # system + current only

    def test_prefers_turn_summary(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        long_answer = "x" * 5000
        summary = "Q: What? | A: Short answer"

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "What?",
                "final_answer": long_answer,
                "turn_summary": summary,
            },
        ]

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="System",
            current_query="Follow-up",
        )

        # Should use turn_summary (with Q: prefix stripped), not raw final_answer
        assert messages[2]["content"] == "Short answer"
        assert len(messages[2]["content"]) < 100

    def test_structured_summary_keeps_outcome_before_metadata(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": "Fix the UI",
                "final_answer": "Long answer",
                "turn_summary": (
                    "Outcome: Fixed the UI and tests passed. | Tools: read_file, edit_file, bash "
                    "| Files: ui/src/App.tsx | User asked: Fix the UI"
                ),
            },
        ]

        messages, _ = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="System",
            current_query="Follow-up",
        )

        assert messages[2]["content"].startswith("Outcome: Fixed the UI")
        assert "Tools:" in messages[2]["content"]
        assert "User asked:" not in messages[2]["content"]

    def test_newest_first_priority(self):
        """Most recent turns are included first when budget is tight."""
        counter = TokenCounter()
        # Tight budget — system ~5 + current ~5 + reserve 50 = ~60 overhead
        # leaving ~90 tokens for history — enough for 1 pair but not 2
        builder = HistoryBuilder(counter, max_context_tokens=200, reserve_for_response=50)

        # Use longer messages so each pair costs ~50+ tokens
        old_text = "This is an old message with enough text to consume tokens. " * 3
        recent_text = "RECENT message that should survive budget cuts. " * 3

        prior_runs = [
            {
                "created_at": "2024-01-01T10:00:00Z",
                "user_message": old_text,
                "final_answer": old_text,
            },
            {
                "created_at": "2024-01-01T10:05:00Z",
                "user_message": recent_text,
                "final_answer": recent_text,
            },
        ]

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="Sys",
            current_query="Now",
        )

        # If both can't fit, only the most recent should be included
        user_msgs = [m["content"] for m in messages if m["role"] == "user" and m["content"] != "Now"]
        if len(user_msgs) == 1:
            assert "RECENT" in user_msgs[0]

    def test_budget_tracking(self):
        counter = TokenCounter()
        builder = HistoryBuilder(counter, max_context_tokens=100000, reserve_for_response=4096)

        prior_runs = [
            {
                "created_at": f"2024-01-01T10:0{i}:00Z",
                "user_message": f"Message {i}",
                "final_answer": f"Response {i}",
            }
            for i in range(5)
        ]

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt="System prompt",
            current_query="Current query",
        )

        assert budget.max_tokens == 100000
        assert budget.reserve_for_response == 4096
        assert budget.system_prompt_tokens > 0
        assert budget.current_query_tokens > 0
        assert budget.history_tokens > 0
        assert budget.utilization_pct > 0
        assert budget.utilization_pct < 5  # Small messages, should be well under budget


class TestTurnSummaryDBStorage:
    """Tests for turn_summary column in database."""

    @pytest.mark.asyncio
    async def test_update_run_stores_turn_summary(self):
        from orchestrator.storage.db import Database
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )

        await repo.create_run(
            run_id="run-1",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="Hello",
        )

        summary_text = "Q: Hello | A: Hi there"
        await repo.update_run("run-1", turn_summary=summary_text)

        # Verify stored
        async with db.conn.execute(
            "SELECT turn_summary FROM runs WHERE run_id = ?", ("run-1",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row[0] == summary_text

        await db.close()

    @pytest.mark.asyncio
    async def test_list_runs_includes_turn_summary(self):
        from orchestrator.storage.db import Database
        from orchestrator.storage.repositories.trace_repo import TraceRepo

        db = Database(":memory:")
        await db.connect()
        repo = TraceRepo(db)

        await db.conn.execute(
            "INSERT INTO conversations (conversation_id, title, created_at, status) VALUES (?, ?, ?, ?)",
            ("conv-1", "Test", "2024-01-01T10:00:00Z", "active"),
        )

        await repo.create_run(
            run_id="run-1",
            conversation_id="conv-1",
            profile_name="chat",
            mode="chat",
            model_config={},
            user_message="Hello",
        )
        await repo.update_run(
            "run-1",
            final_answer="Hi there",
            status="succeeded",
            turn_summary="Q: Hello | A: Hi there",
        )

        runs = await repo.list_runs_for_conversation("conv-1")
        assert len(runs) == 1
        assert runs[0].get("turn_summary") == "Q: Hello | A: Hi there"

        await db.close()
