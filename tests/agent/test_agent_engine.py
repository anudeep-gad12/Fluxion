"""Tests for AgentEngine."""

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.agent.agent_engine import (
    AgentEngine,
    AgentResult,
    ParsedToolCall,
    WorkingMemory,
)
from orchestrator.agent.coding_session import (
    CodingFileSpan,
    CodingFileState,
    CodingSessionEntry,
    CodingSessionState,
)
from orchestrator.agent.plan_mode import PlanDecision
from orchestrator.agent.state_machine import RecoveryContext
from orchestrator.agent.tools.base import ToolResult, ToolSchema
from orchestrator.agent.tools.bash_tool import BashTool
from orchestrator.agent.tools.command_session import (
    CommandSessionManager,
    ExecCommandTool,
    WriteStdinTool,
)
from orchestrator.agent.tools.read_file import ReadFileTool
from orchestrator.agent.tools.registry import ToolRegistry
from orchestrator.providers.base import LLMResponse

# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_provider(response_text="Test answer", tool_calls=None):
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.complete_streaming = AsyncMock(
        return_value=LLMResponse(
            text=response_text,
            tool_calls=tool_calls,
        )
    )
    return provider


def create_mock_repo():
    """Create a mock AgentRepo."""
    repo = MagicMock()
    repo.get_citations_for_run = AsyncMock(return_value=[])
    repo.mark_citations_used = AsyncMock()
    repo.create_citation = AsyncMock()
    repo.create_run_artifact = AsyncMock()
    repo.get_coding_session_state = AsyncMock(return_value=None)
    repo.upsert_coding_session_state = AsyncMock()
    repo.append_coding_session_entries = AsyncMock(return_value=[])
    repo.insert_coding_session_entry = AsyncMock(return_value={})
    repo.list_coding_session_entries = AsyncMock(return_value=[])
    repo.get_latest_coding_session_entry_seq = AsyncMock(return_value=0)
    repo.mark_coding_session_entries_compacted = AsyncMock()
    return repo


def create_mock_registry():
    """Create a mock ToolRegistry."""
    registry = MagicMock()
    registry.get_openai_schemas.return_value = []
    registry.get.return_value = None
    registry.is_idempotent.return_value = True
    return registry


def create_mock_trace_repo(prior_runs=None):
    """Create a mock TraceRepo."""
    repo = MagicMock()
    repo.list_runs_for_conversation = AsyncMock(return_value=prior_runs or [])
    repo.update_run = AsyncMock()
    return repo


def create_mock_state_machine(
    can_continue_sequence=None,
    step_sequence=None,
):
    """Create a mock AgentStateMachine.

    Args:
        can_continue_sequence: List of boolean values for can_continue() calls
        step_sequence: List of step dicts for start_step() calls
    """
    if can_continue_sequence is None:
        can_continue_sequence = [True, False]
    if step_sequence is None:
        step_sequence = [{"step_number": 1, "id": "step-1"}]

    mock_sm = MagicMock()
    mock_sm.initialize = AsyncMock(
        return_value=RecoveryContext(
            needs_recovery=False,
            interrupted_tool_calls=[],
            hints=[],
            last_completed_step=0,
        )
    )
    mock_sm.can_continue.side_effect = can_continue_sequence
    mock_sm.start_step = AsyncMock(side_effect=step_sequence)
    mock_sm.transition_to = AsyncMock()
    mock_sm.complete_step = AsyncMock()
    mock_sm.complete_run = AsyncMock()
    mock_sm.error_step = AsyncMock()
    mock_sm.error_run = AsyncMock()
    mock_sm.record_tool_call = AsyncMock()
    mock_sm.start_tool_execution = AsyncMock()
    mock_sm.complete_tool_call = AsyncMock()
    mock_sm.record_approval = AsyncMock()
    mock_sm.current_step = 1
    mock_sm.steps_remaining = 9
    return mock_sm


# =============================================================================
# AgentResult Tests
# =============================================================================


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_create_successful_result(self):
        """Can create a successful result."""
        result = AgentResult(
            run_id="run-1",
            success=True,
            final_answer="The answer is 42.",
            citations=[{"id": "c-1", "source_url": "https://example.com"}],
            total_steps=2,
            timing_ms=1500,
        )

        assert result.success is True
        assert result.final_answer == "The answer is 42."
        assert len(result.citations) == 1
        assert result.error_message is None

    def test_create_failed_result(self):
        """Can create a failed result."""
        result = AgentResult(
            run_id="run-1",
            success=False,
            error_message="LLM call failed",
            total_steps=1,
            timing_ms=500,
        )

        assert result.success is False
        assert result.error_message == "LLM call failed"
        assert result.final_answer is None

    def test_default_values(self):
        """Default values are set correctly."""
        result = AgentResult(run_id="run-1", success=True)

        assert result.citations == []
        assert result.total_steps == 0
        assert result.timing_ms == 0


# =============================================================================
# ParsedToolCall Tests
# =============================================================================


class TestParsedToolCall:
    """Tests for ParsedToolCall dataclass."""

    def test_create_parsed_tool_call(self):
        """Can create a parsed tool call."""
        tc = ParsedToolCall(
            id="tc-1",
            name="web_search",
            arguments={"query": "Tokyo population"},
            raw_arguments='{"query": "Tokyo population"}',
        )

        assert tc.id == "tc-1"
        assert tc.name == "web_search"
        assert tc.arguments == {"query": "Tokyo population"}


# =============================================================================
# AgentEngine Basic Tests
# =============================================================================


class TestAgentEngineInit:
    """Tests for AgentEngine initialization."""

    def test_init_with_defaults(self):
        """Initialize with default settings."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        assert engine._model_name == "accounts/fireworks/models/kimi-k2p6"
        assert engine._max_steps == 1000
        assert engine._max_tokens == 32768
        assert engine._temperature == 0.7

    def test_init_with_custom_settings(self):
        """Initialize with custom settings."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
            model_name="gpt-4",
            max_steps=5,
            max_tokens=2048,
            temperature=0.5,
            system_prompt="Custom prompt",
        )

        assert engine._model_name == "gpt-4"
        assert engine._max_steps == 5
        assert engine._system_prompt == "Custom prompt"


class TestAgentEngineHelpers:
    """Tests for AgentEngine helper methods."""

    def test_emit_with_callback(self):
        """Emit calls callback with event dict."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        events = []
        engine._emit(lambda e: events.append(e), "test_event", foo="bar", num=42)

        assert len(events) == 1
        assert events[0]["type"] == "test_event"
        assert events[0]["foo"] == "bar"
        assert events[0]["num"] == 42

    def test_emit_without_callback(self):
        """Emit does nothing when callback is None."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        # Should not raise
        engine._emit(None, "test_event", foo="bar")

    @pytest.mark.asyncio
    async def test_empty_content_without_tool_calls_continues(self):
        """Empty content/no tools should prompt continuation, not force synthesis."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="",
                    reasoning="I have enough context. Let me search next.",
                    tool_calls=[],
                    finish_reason="stop",
                ),
                LLMResponse(
                    text="Complete answer.",
                    reasoning=None,
                    tool_calls=[],
                    finish_reason="stop",
                ),
            ]
        )
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=create_mock_registry(),
            )
            result = await engine.run(run_id="run-empty-retry", query="Research VO2 max")

        assert result.final_answer == "Complete answer."
        assert provider.complete_streaming.await_count == 2
        decisions = [call.kwargs.get("decision") for call in mock_sm.complete_step.await_args_list]
        assert "empty_response_retry" in decisions
        assert "synthesize" in decisions

    @pytest.mark.asyncio
    async def test_finalize_edit_file_emits_raw_diff_result_data(self):
        """edit_file tool_result events expose raw unified diff text to the UI."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )
        state_machine = create_mock_state_machine()
        diff = "--- a/app.py\n+++ b/app.py\n-old\n+new\n"
        events = []

        await engine._finalize_tool_call(
            tool_call=ParsedToolCall(
                id="provider-tool-id",
                name="edit_file",
                arguments={"file_path": "app.py"},
                raw_arguments='{"file_path":"app.py"}',
            ),
            result=ToolResult(
                success=True,
                result_summary="Edited app.py",
                result_data={"file_path": "app.py", "diff": diff, "matched_by": "exact"},
                duration_ms=12,
            ),
            tc_record={"id": "db-tool-id"},
            tool_call_event_id=None,
            state_machine=state_machine,
            step_number=1,
            event_callback=lambda event: events.append(event),
            run_id="run-1",
        )

        tool_result = next(event for event in events if event["type"] == "tool_result")
        assert tool_result["result_data"] == diff
        state_machine.complete_tool_call.assert_awaited_once()

    async def test_build_initial_messages(self):
        """Build initial messages with system and user."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
            system_prompt="You are helpful.",
        )

        messages, budget = await engine._build_initial_messages("What is 2+2?")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What is 2+2?"
        assert budget.max_tokens == 100000
        assert budget.history_tokens == 0

    async def test_build_initial_messages_uses_turn_summary_not_prior_agent_state(self):
        """Cross-turn context should come from summaries, not prior serialized transcript."""
        trace_repo = create_mock_trace_repo(
            prior_runs=[
                {
                    "created_at": "2026-04-27T10:00:00Z",
                    "status": "succeeded",
                    "user_message": "Inspect the chart issue",
                    "final_answer": "Fixed it",
                    "turn_summary": "Q: Inspect the chart issue | A: Investigated chart ordering and fixed descending sort.",
                    "agent_state": json.dumps(
                        [
                            {"role": "system", "content": "old system"},
                            {"role": "tool", "name": "read_file", "content": "huge raw file dump"},
                        ]
                    ),
                }
            ]
        )
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
            trace_repo=trace_repo,
            system_prompt="You are helpful.",
        )

        messages, _ = await engine._build_initial_messages(
            "What should I change next?",
            conversation_id="conv-1",
        )

        assert [message["role"] for message in messages] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert messages[2]["content"] == "Investigated chart ordering and fixed descending sort."
        assert all(message["role"] != "tool" for message in messages)

    def test_build_prompt_messages_includes_working_memory_and_run_transcript(self):
        """Prompt assembly injects working memory without dropping run transcript."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )
        scaffold = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Fix the chart ordering."},
            {"role": "assistant", "content": "Inspecting chart code."},
        ]
        memory = WorkingMemory(
            objective="Fix the chart ordering.",
            files_inspected={"src/chart.ts": "Sorts dates descending."},
        )
        run_messages = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "tc-1"}]},
            {"role": "tool", "name": "read_file", "content": "raw file excerpt"},
        ]

        prompt = engine._build_prompt_messages(scaffold + run_messages, memory)

        assert prompt[0]["role"] == "system"
        assert prompt[1]["role"] == "system"
        assert "WORKING MEMORY" in prompt[1]["content"]
        assert "durable state for the current agent conversation" in prompt[1]["content"]
        assert "do not restate the plan" in prompt[1]["content"]
        assert "answer directly when no tool is needed" in prompt[1]["content"]
        assert prompt[-1]["role"] == "tool"
        assert prompt[-1]["content"] == "raw file excerpt"

    def test_extract_thinking_with_tags(self):
        """Extract thinking from Harmony format."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        text = "<think>I should search for this</think>The answer is 42."
        thinking = engine._extract_thinking(text)

        assert thinking == "I should search for this"

    def test_extract_thinking_multiline(self):
        """Extract multiline thinking."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        text = "<think>Line 1\nLine 2\nLine 3</think>Answer"
        thinking = engine._extract_thinking(text)

        assert "Line 1" in thinking
        assert "Line 2" in thinking
        assert "Line 3" in thinking

    def test_extract_thinking_none_when_missing(self):
        """Return None when no thinking tags."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        thinking = engine._extract_thinking("Just a plain answer.")
        assert thinking is None

    def test_extract_thinking_empty_text(self):
        """Handle empty text."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        assert engine._extract_thinking("") is None
        assert engine._extract_thinking(None) is None

    def test_clean_answer_removes_thinking(self):
        """Clean answer removes thinking tags."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        text = "<think>reasoning here</think>The actual answer."
        cleaned = engine._clean_answer(text)

        assert cleaned == "The actual answer."
        assert "<think>" not in cleaned
        assert "reasoning" not in cleaned

    def test_clean_answer_handles_empty(self):
        """Clean answer handles empty text."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        assert engine._clean_answer("") == ""
        assert engine._clean_answer(None) == ""


def test_apply_patch_failure_recovery_message_prefers_retry_patch():
    engine = AgentEngine(
        provider=create_mock_provider(),
        repo=create_mock_repo(),
        registry=create_mock_registry(),
    )
    failures = [{"error": "Unexpected patch line: Update File: src/index.css"}]

    messages = engine._build_apply_patch_failure_recovery_messages(failures)

    assert messages
    content = messages[0]["content"]
    assert "Do not switch to edit_file" in content
    assert "*** Update File: path/to/file" in content
    assert "--- a/path/to/file" in content
    assert "Never send placeholder-only patches" in content


def test_apply_patch_hunk_mismatch_recovery_requires_reread_then_patch():
    engine = AgentEngine(
        provider=create_mock_provider(),
        repo=create_mock_repo(),
        registry=create_mock_registry(),
    )
    tool_call = ParsedToolCall(
        id="tc-patch",
        name="apply_patch",
        arguments={
            "patch": (
                "*** Begin Patch\n"
                "--- a/src/index.css\n"
                "+++ b/src/index.css\n"
                "@@ -1,1 +1,1 @@\n"
                "-old\n"
                "+new\n"
                "*** End Patch\n"
            )
        },
        raw_arguments="{}",
    )
    result = ToolResult(
        success=False,
        result_summary="Patch failed: Patch hunk did not match current contents of src/index.css",
        error_message="Patch hunk did not match current contents of src/index.css",
    )

    failures = engine._apply_patch_failure_contexts([(tool_call, result)])
    messages = engine._build_apply_patch_failure_recovery_messages(failures)

    assert failures[0]["failure_type"] == "hunk_mismatch"
    assert failures[0]["paths"] == ["src/index.css"]
    content = messages[0]["content"]
    assert "reread the exact affected file region" in content
    assert "retry a smaller apply_patch" in content
    assert "Do not switch to edit_file" in content


def test_apply_patch_failure_hides_legacy_write_schemas_for_coding_profile():
    registry = create_mock_registry()
    registry.get_openai_schemas.return_value = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "apply_patch"}},
        {"type": "function", "function": {"name": "edit_file"}},
        {"type": "function", "function": {"name": "write_file"}},
    ]
    profile = MagicMock()
    profile.name = "coding"
    engine = AgentEngine(
        provider=create_mock_provider(),
        repo=create_mock_repo(),
        registry=registry,
        profile=profile,
    )
    engine._apply_patch_failures = {
        "src/App.tsx": {"failure_type": "hunk_mismatch"}
    }

    names = {
        schema["function"]["name"] for schema in engine._available_tool_schemas()
    }

    assert {"read_file", "apply_patch"} <= names
    assert "edit_file" not in names
    assert "write_file" not in names


class TestAgentEngineToolParsing:
    """Tests for tool call parsing."""

    def test_parse_tool_calls_valid(self):
        """Parse valid tool calls."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        tool_calls = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "Tokyo population"}',
                },
            }
        ]

        parsed = engine._parse_tool_calls(tool_calls)

        assert len(parsed) == 1
        assert parsed[0].id == "tc-1"
        assert parsed[0].name == "web_search"
        assert parsed[0].arguments == {"query": "Tokyo population"}
        assert parsed[0].raw_arguments == '{"query": "Tokyo population"}'

    def test_parse_tool_calls_invalid_json(self):
        """Parse tool calls with invalid JSON arguments."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        tool_calls = [
            {
                "id": "tc-1",
                "function": {
                    "name": "web_search",
                    "arguments": "not valid json",
                },
            }
        ]

        parsed = engine._parse_tool_calls(tool_calls)

        assert len(parsed) == 1
        assert parsed[0].arguments == {}
        assert parsed[0].parse_error is not None
        assert "valid JSON" in parsed[0].parse_error

    def test_parse_tool_calls_missing_id(self):
        """Parse tool calls with missing ID generates UUID."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        tool_calls = [
            {
                "function": {
                    "name": "web_search",
                    "arguments": "{}",
                },
            }
        ]

        parsed = engine._parse_tool_calls(tool_calls)

        assert len(parsed) == 1
        assert parsed[0].id is not None  # Generated UUID

    def test_parse_tool_calls_empty_list(self):
        """Parse empty tool calls list."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        parsed = engine._parse_tool_calls([])
        assert parsed == []

    def test_parse_tool_calls_multiple(self):
        """Parse multiple tool calls."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        tool_calls = [
            {
                "id": "tc-1",
                "function": {"name": "web_search", "arguments": '{"query": "q1"}'},
            },
            {
                "id": "tc-2",
                "function": {"name": "web_extract", "arguments": '{"urls": []}'},
            },
        ]

        parsed = engine._parse_tool_calls(tool_calls)

        assert len(parsed) == 2
        assert parsed[0].name == "web_search"
        assert parsed[1].name == "web_extract"

    def test_parse_tool_calls_canonicalizes_tool_name_case_and_separator(self):
        """Normalize model-emitted tool names against advertised schemas."""
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "grep"}},
            {"type": "function", "function": {"name": "glob"}},
            {"type": "function", "function": {"name": "read_file"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        tool_calls = [
            {
                "id": "tc-1",
                "function": {
                    "name": "Grep",
                    "arguments": '{"pattern": "resume", "path": "Career"}',
                },
            },
            {
                "id": "tc-2",
                "function": {
                    "name": "Glob",
                    "arguments": '{"pattern": "Career/**/*"}',
                },
            },
            {
                "id": "tc-3",
                "function": {
                    "name": "Read-File",
                    "arguments": '{"file_path": "README.md"}',
                },
            },
        ]

        parsed = engine._parse_tool_calls(tool_calls)

        assert [tool_call.name for tool_call in parsed] == [
            "grep",
            "glob",
            "read_file",
        ]

    def test_parse_tool_calls_leaves_unknown_tool_name_unchanged(self):
        """Unknown names still surface as unknown-tool errors later."""
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "grep"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        parsed = engine._parse_tool_calls(
            [
                {
                    "id": "tc-1",
                    "function": {"name": "Nope", "arguments": "{}"},
                }
            ]
        )

        assert parsed[0].name == "Nope"

    def test_parse_tool_calls_non_object_json_marks_parse_error(self):
        """Parse tool calls with JSON that is not an object."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        tool_calls = [
            {
                "id": "tc-1",
                "function": {
                    "name": "write_file",
                    "arguments": '["not", "an", "object"]',
                },
            }
        ]

        parsed = engine._parse_tool_calls(tool_calls)

        assert len(parsed) == 1
        assert parsed[0].arguments == {}
        assert parsed[0].parse_error is not None
        assert "JSON object" in parsed[0].parse_error


class TestAgentEngineFormatResult:
    """Tests for tool result formatting."""

    def test_format_success_with_data(self):
        """Format successful result with data."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        result = ToolResult(
            success=True,
            result_summary="Found 5 results",
            result_data={"results": [{"url": "http://example.com"}]},
        )

        formatted = engine._format_tool_result(result)
        parsed = json.loads(formatted)

        assert "results" in parsed

    def test_format_success_without_data(self):
        """Format successful result without data uses summary."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        result = ToolResult(
            success=True,
            result_summary="Found 5 results",
        )

        formatted = engine._format_tool_result(result)
        assert formatted == "Found 5 results"

    def test_format_error_result(self):
        """Format error result."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        result = ToolResult(
            success=False,
            result_summary="Failed",
            error_message="API error",
        )

        formatted = engine._format_tool_result(result)
        parsed = json.loads(formatted)

        assert parsed["error"] == "API error"
        assert parsed["summary"] == "Failed"


class TestAgentWorkingMemory:
    """Tests for structured agent working memory."""

    def test_update_working_memory_from_tools(self):
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )
        memory = WorkingMemory(objective="Fix issue")

        tool_results = [
            (
                ParsedToolCall(
                    id="tc-read",
                    name="read_file",
                    arguments={"file_path": "src/chart.ts"},
                    raw_arguments='{"file_path":"src/chart.ts"}',
                ),
                ToolResult(
                    success=True,
                    result_summary="Read 20 lines from src/chart.ts",
                    result_data="1\tconst data = sortDesc(items)\n2\treturn data\n",
                ),
            ),
            (
                ParsedToolCall(
                    id="tc-edit",
                    name="edit_file",
                    arguments={"file_path": "src/chart.ts"},
                    raw_arguments='{"file_path":"src/chart.ts"}',
                ),
                ToolResult(
                    success=True,
                    result_summary="Edited src/chart.ts",
                    result_data="--- a/src/chart.ts\n+++ b/src/chart.ts\n-sortDesc(items)\n+sortAsc(items)\n",
                ),
            ),
            (
                ParsedToolCall(
                    id="tc-bash",
                    name="bash",
                    arguments={"command": "npm run build"},
                    raw_arguments='{"command":"npm run build"}',
                ),
                ToolResult(
                    success=False,
                    result_summary="Command failed (exit 2): npm run build",
                    result_data={
                        "exit_code": 2,
                        "stdout": "",
                        "stderr": "src/chart.ts:44 error TS2322: bad type",
                        "timed_out": False,
                    },
                ),
            ),
            (
                ParsedToolCall(
                    id="tc-grep",
                    name="grep",
                    arguments={"pattern": "sort", "path": "src"},
                    raw_arguments='{"pattern":"sort","path":"src"}',
                ),
                ToolResult(
                    success=True,
                    result_summary="Found 3 matches in src",
                    result_data="src/chart.ts:12: sortDesc(items)",
                ),
            ),
        ]

        engine._update_working_memory_from_tools(memory, tool_results)

        assert "src/chart.ts" in memory.files_inspected
        assert "src/chart.ts" in memory.files_changed
        assert any(
            item == "Command failed (exit 2): npm run build"
            for item in memory.validation_results
        )
        assert any("TS2322" in item for item in memory.validation_results)
        assert any("grep 'sort'" in item for item in memory.recent_raw_evidence)


class TestCodingSessionPersistence:
    """Tests for persistent coding-session continuity."""

    @pytest.mark.asyncio
    async def test_restore_coding_session_reuses_fresh_file_evidence(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        chart_file = src_dir / "chart.ts"
        chart_file.write_text("const data = sortDesc(items)\nreturn data\n", encoding="utf-8")

        registry = create_mock_registry()
        read_tool = ReadFileTool(str(tmp_path))
        registry.get.side_effect = lambda name: read_tool if name == "read_file" else None

        repo = create_mock_repo()
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=registry,
        )
        memory = WorkingMemory(objective="Do all of it")
        session_state = CodingSessionState(
            objective="Review the chart sorting",
            read_files=["src/chart.ts"],
            file_evidence={
                "src/chart.ts": CodingFileState(
                    path="src/chart.ts",
                    summary="Read 2 lines from src/chart.ts",
                    spans=[
                        CodingFileSpan(
                            line_start=1,
                            line_end=2,
                            excerpt="const data = sortDesc(items) | return data",
                            reason="read",
                        )
                    ],
                    content_hash=hashlib.sha256(
                        chart_file.read_text(encoding="utf-8").encode("utf-8")
                    ).hexdigest(),
                )
            },
        )

        await engine._hydrate_working_memory_from_coding_session(
            conversation_id="conv-1",
            session_state=session_state,
            working_memory=memory,
            run_id="run-restore",
            updated_at="2026-04-29T12:00:00Z",
        )

        assert memory.restored_session is True
        assert "src/chart.ts" in memory.files_inspected
        assert "[stored, fresh]" in memory.files_inspected["src/chart.ts"]
        assert "Stored excerpt" in memory.files_inspected["src/chart.ts"]
        assert memory.stale_file_summaries == {}

    @pytest.mark.asyncio
    async def test_restore_coding_session_marks_changed_files_stale(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        chart_file = src_dir / "chart.ts"
        chart_file.write_text("const data = sortDesc(items)\nreturn data\n", encoding="utf-8")
        original_hash = hashlib.sha256(
            chart_file.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        chart_file.write_text("const data = sortAsc(items)\nreturn data\n", encoding="utf-8")

        registry = create_mock_registry()
        read_tool = ReadFileTool(str(tmp_path))
        registry.get.side_effect = lambda name: read_tool if name == "read_file" else None

        repo = create_mock_repo()
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=registry,
        )
        memory = WorkingMemory(objective="Do all of it")
        session_state = CodingSessionState(
            objective="Review the chart sorting",
            read_files=["src/chart.ts"],
            file_evidence={
                "src/chart.ts": CodingFileState(
                    path="src/chart.ts",
                    summary="Read 2 lines from src/chart.ts",
                    spans=[
                        CodingFileSpan(
                            line_start=1,
                            line_end=2,
                            excerpt="const data = sortDesc(items) | return data",
                            reason="read",
                        )
                    ],
                    content_hash=original_hash,
                )
            },
        )

        await engine._hydrate_working_memory_from_coding_session(
            conversation_id="conv-1",
            session_state=session_state,
            working_memory=memory,
            run_id="run-restore",
            updated_at="2026-04-29T12:00:00Z",
        )

        assert "src/chart.ts" not in memory.files_inspected
        assert "src/chart.ts" in memory.stale_file_summaries
        assert "changed" in memory.stale_file_summaries["src/chart.ts"]

    @pytest.mark.asyncio
    async def test_persist_coding_session_captures_multiple_file_spans(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        chart_file = src_dir / "chart.ts"
        chart_file.write_text(
            "const data = sortDesc(items)\nreturn data\nconst more = 1\n",
            encoding="utf-8",
        )

        registry = create_mock_registry()
        read_tool = ReadFileTool(str(tmp_path))
        registry.get.side_effect = lambda name: read_tool if name == "read_file" else None
        repo = create_mock_repo()
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=registry,
        )
        memory = WorkingMemory(objective="Implement the sort fix")
        first_tool_results = [
            (
                ParsedToolCall(
                    id="tc-read",
                    name="read_file",
                    arguments={"file_path": "src/chart.ts", "offset": 1, "limit": 2},
                    raw_arguments='{"file_path":"src/chart.ts","offset":1,"limit":20}',
                ),
                ToolResult(
                    success=True,
                    result_summary="Read 2 lines from src/chart.ts",
                    result_data="     1\tconst data = sortDesc(items)\n     2\treturn data",
                    metadata={"lines_read": 2},
                ),
            ),
        ]
        second_tool_results = [
            (
                ParsedToolCall(
                    id="tc-read-2",
                    name="read_file",
                    arguments={"file_path": "src/chart.ts", "offset": 3, "limit": 1},
                    raw_arguments='{"file_path":"src/chart.ts","offset":3,"limit":1}',
                ),
                ToolResult(
                    success=True,
                    result_summary="Read 1 line from src/chart.ts",
                    result_data="     3\tconst more = 1",
                    metadata={"lines_read": 1},
                ),
            ),
        ]

        engine._update_working_memory_from_tools(memory, first_tool_results)
        session_state = CodingSessionState(objective="Implement the sort fix")
        await engine._persist_coding_session_state(
            conversation_id="conv-1",
            run_id="run-1",
            working_memory=memory,
            session_state=session_state,
            tool_results=first_tool_results,
            reason="tool_progress",
            step_number=1,
        )
        engine._update_working_memory_from_tools(memory, second_tool_results)
        await engine._persist_coding_session_state(
            conversation_id="conv-1",
            run_id="run-1",
            working_memory=memory,
            session_state=session_state,
            tool_results=second_tool_results,
            reason="tool_progress",
            step_number=2,
        )

        persisted_state = repo.upsert_coding_session_state.await_args.args[1]
        stored_file = persisted_state["file_evidence"]["src/chart.ts"]
        assert persisted_state["read_files"] == ["src/chart.ts"]
        assert len(stored_file["spans"]) == 2
        assert stored_file["spans"][0]["line_start"] == 1
        assert stored_file["spans"][0]["line_end"] == 2
        assert stored_file["spans"][1]["line_start"] == 3
        assert stored_file["spans"][1]["line_end"] == 3
        assert stored_file["content_hash"]

    def test_classify_reread_reason_detects_span_gaps_and_explicit_rereads(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        chart_file = src_dir / "chart.ts"
        chart_file.write_text("a\nb\nc\nd\n", encoding="utf-8")
        file_hash = hashlib.sha256(
            chart_file.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()

        registry = create_mock_registry()
        read_tool = ReadFileTool(str(tmp_path))
        registry.get.side_effect = lambda name: read_tool if name == "read_file" else None
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )
        engine._active_coding_session_state = CodingSessionState(
            objective="Inspect chart",
            read_files=["src/chart.ts"],
            file_evidence={
                "src/chart.ts": CodingFileState(
                    path="src/chart.ts",
                    summary="Read first two lines",
                    spans=[
                        CodingFileSpan(
                            line_start=1,
                            line_end=2,
                            excerpt="a | b",
                            reason="read",
                        )
                    ],
                    content_hash=file_hash,
                )
            },
        )

        span_gap_reason = engine._classify_coding_file_read_reason(
            ParsedToolCall(
                id="tc-read-gap",
                name="read_file",
                arguments={"file_path": "src/chart.ts", "offset": 4, "limit": 1},
                raw_arguments='{"file_path":"src/chart.ts","offset":4,"limit":1}',
            )
        )
        explicit_reason = engine._classify_coding_file_read_reason(
            ParsedToolCall(
                id="tc-read-repeat",
                name="read_file",
                arguments={"file_path": "src/chart.ts", "offset": 1, "limit": 2},
                raw_arguments='{"file_path":"src/chart.ts","offset":1,"limit":2}',
            )
        )

        assert span_gap_reason["reason"] == "span_insufficient"
        assert explicit_reason["reason"] == "explicit_model_request"

    @pytest.mark.asyncio
    async def test_compaction_keeps_last_two_turns_raw_and_preserves_tool_pairs(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=1,
                run_id="run-0",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "Turn 1"},
                token_estimate=900,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=2,
                run_id="run-0",
                step_number=1,
                entry_type="assistant_tool_calls",
                role="assistant",
                content_json={"content": "", "tool_calls": [{"id": "tc-1"}]},
                token_estimate=500,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=3,
                run_id="run-0",
                step_number=1,
                entry_type="tool_result",
                role="tool",
                content_json={"tool_call_id": "tc-1", "name": "read_file", "content": "Read file"},
                token_estimate=400,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=4,
                run_id="run-0",
                step_number=2,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Done turn 1"},
                token_estimate=400,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=5,
                run_id="run-1",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "Turn 2"},
                token_estimate=500,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=6,
                run_id="run-1",
                step_number=1,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Done turn 2"},
                token_estimate=300,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=7,
                run_id="run-2",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "Turn 3"},
                token_estimate=500,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=8,
                run_id="run-2",
                step_number=1,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Done turn 3"},
                token_estimate=300,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )
        session_state = CodingSessionState(objective="Continue coding")

        with patch.object(engine, "_coding_tail_target_tokens", return_value=2000):
            compacted = await engine._compact_coding_session_history(
                conversation_id="conv-1",
                run_id="run-current",
                step_number=3,
                session_state=session_state,
            )

        assert compacted is True
        repo.mark_coding_session_entries_compacted.assert_awaited_once()
        assert repo.mark_coding_session_entries_compacted.await_args.kwargs["through_seq"] == 3
        repo.insert_coding_session_entry.assert_awaited_once()
        inserted = repo.insert_coding_session_entry.await_args.kwargs["entry"]
        assert inserted["entry_type"] == "compaction_summary"
        assert inserted["role"] == "user"
        summary_content = inserted["content_json"]["content"]
        assert "## Goal" in summary_content
        assert "## Progress" in summary_content
        assert "### Done" in summary_content
        assert "## Key Decisions" in summary_content
        assert "<read-files>" in summary_content
        assert inserted["content_json"]["covered_through_seq"] == 3
        assert repo.list_coding_session_entries.await_args.kwargs["include_compacted"] is False

    @pytest.mark.asyncio
    async def test_persist_step_entries_skips_malformed_tool_call_replay(self):
        repo = create_mock_repo()
        edit_tool = MagicMock()
        edit_tool.schema.parameters = {"required": ["file_path", "old_string", "new_string"]}
        registry = create_mock_registry()
        registry.get.side_effect = lambda name: edit_tool if name == "edit_file" else None
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=registry,
        )

        tool_results = [
            (
                ParsedToolCall(
                    id="tc-edit",
                    name="edit_file",
                    arguments={},
                    raw_arguments='{"file_path":"src/chart.ts"}',
                ),
                ToolResult(
                    success=False,
                    result_summary="Missing required args: 'old_string', 'new_string'",
                    error_message="Missing required argument(s).",
                ),
            ),
        ]

        await engine._persist_coding_session_step_entries(
            conversation_id="conv-1",
            run_id="run-1",
            step_number=2,
            assistant_content="Trying the edit.",
            tool_results=tool_results,
        )

        persisted_entries = repo.append_coding_session_entries.await_args.args[1]
        assert [entry["entry_type"] for entry in persisted_entries] == ["assistant", "tool_result"]
        assert persisted_entries[0]["content_json"]["replay_eligible"] is False
        assert "recovery_note" in persisted_entries[1]["content_json"]

    @pytest.mark.asyncio
    async def test_compaction_summary_is_iterative_across_repeated_compactions(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=4,
                run_id="run-old",
                step_number=2,
                entry_type="compaction_summary",
                role="user",
                content_json={
                    "content": "prior checkpoint",
                    "summary_state": {
                        "goal": "Fix the app",
                        "done": ["Read src/app.ts"],
                        "read_files": ["src/app.ts"],
                        "modified_files": [],
                    },
                },
                token_estimate=30,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=5,
                run_id="run-2",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "now patch src/app.ts"},
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=6,
                run_id="run-2",
                step_number=1,
                entry_type="assistant_tool_calls",
                role="assistant",
                content_json={
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": '{"file_path":"src/app.ts"}',
                            },
                        }
                    ]
                },
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=7,
                run_id="run-2",
                step_number=1,
                entry_type="tool_result",
                role="tool",
                content_json={
                    "tool_call_id": "tc-1",
                    "name": "edit_file",
                    "content": "Updated src/app.ts",
                },
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=8,
                run_id="run-3",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "verify it"},
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=9,
                run_id="run-3",
                step_number=1,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Verifying now."},
                token_estimate=20,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )
        session_state = CodingSessionState(
            objective="Fix the app",
            read_files=["src/app.ts"],
            modified_files=["src/app.ts"],
        )

        with patch.object(engine, "_coding_tail_target_tokens", return_value=60):
            compacted = await engine._compact_coding_session_history(
                conversation_id="conv-1",
                run_id="run-current",
                step_number=4,
                session_state=session_state,
            )

        assert compacted is True
        inserted = repo.insert_coding_session_entry.await_args.kwargs["entry"]
        summary_state = inserted["content_json"]["summary_state"]
        assert summary_state["goal"] == "Fix the app"
        assert "Read src/app.ts" in summary_state["done"]
        assert any("Modified file" in item for item in summary_state["done"])

    @pytest.mark.asyncio
    async def test_load_coding_session_messages_ignores_state_narrative_fields(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=1,
                run_id="run-1",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "please fix it"},
                token_estimate=10,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )
        session_state = CodingSessionState.from_dict(
            {
                "objective": "Fix it",
                "prior_outcomes": ["Assistant claimed it was fixed."],
                "checkpoint_summary": "CODING SESSION CHECKPOINT\n- Progress so far: fixed",
                "open_tasks": ["Double-check the cache path"],
                "modified_files": ["src/App.tsx"],
            }
        )
        memory = WorkingMemory(objective="Fix it")

        messages, _ = await engine._load_coding_session_messages(
            conversation_id="conv-1",
            system_prompt="System prompt",
            query="it still looks the same",
            run_id="run-2",
            session_state=session_state,
            working_memory=memory,
            use_session_entries=True,
        )

        flattened = "\n".join(str(message.get("content", "")) for message in messages)
        assert "Assistant claimed it was fixed." not in flattened
        assert "Progress so far: fixed" not in flattened
        assert "Double-check the cache path" not in flattened
        assert [message["role"] for message in messages] == ["system", "system", "user"]
        assert "CODING SESSION CURRENT STATE" in messages[1]["content"]
        assert repo.list_coding_session_entries.await_args.kwargs["include_compacted"] is False
        assert engine._last_stored_context is not None
        assert engine._last_stored_context["stored_tokens"] > 0

    @pytest.mark.asyncio
    async def test_load_coding_session_messages_replays_checkpoint_restores_files_and_preserves_tail(
        self,
        tmp_path: Path,
    ):
        repo = create_mock_repo()
        app_file = tmp_path / "src" / "app.ts"
        app_file.parent.mkdir(parents=True)
        app_file.write_text("const app = true;\nconsole.log(app);\n", encoding="utf-8")

        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=4,
                run_id="run-1",
                step_number=3,
                entry_type="compaction_summary",
                role="user",
                content_json={
                    "content": "The earlier part of this coding conversation was compacted...\n\n<summary>\n## Goal\n- Fix app\n</summary>",
                    "summary_state": {
                        "goal": "Fix app",
                        "read_files": ["src/app.ts"],
                        "modified_files": ["src/app.ts"],
                    },
                    "covered_through_seq": 3,
                    "tail_start_seq": 5,
                },
                token_estimate=50,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=5,
                run_id="run-2",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "still broken in src/app.ts"},
                token_estimate=10,
            ).to_dict(),
        ]
        from orchestrator.agent.tools.read_file import ReadFileTool

        registry = create_mock_registry()
        registry.get.side_effect = lambda name: ReadFileTool(str(tmp_path)) if name == "read_file" else None
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=registry,
        )
        session_state = CodingSessionState(
            objective="Fix app",
            read_files=["src/app.ts"],
            modified_files=["src/app.ts"],
            file_evidence={
                "src/app.ts": CodingFileState(
                    path="src/app.ts",
                    summary="Read app.ts",
                    spans=[
                        CodingFileSpan(
                            line_start=1,
                            line_end=2,
                            excerpt="const app = true;",
                            reason="read",
                        )
                    ],
                )
            },
        )

        messages, _ = await engine._load_coding_session_messages(
            conversation_id="conv-1",
            system_prompt="System prompt",
            query="still broken in src/app.ts",
            run_id="run-2",
            session_state=session_state,
            working_memory=WorkingMemory(objective="Fix app"),
            use_session_entries=True,
        )

        assert [message["role"] for message in messages[:6]] == [
            "system",
            "user",
            "system",
            "assistant",
            "tool",
            "user",
        ]
        assert "The earlier part of this coding conversation was compacted" in messages[1]["content"]
        assert messages[4]["name"] == "read_file"
        assert "const app = true;" in messages[4]["content"]

    @pytest.mark.asyncio
    async def test_persist_final_answer_can_mark_terminal_fallback_as_non_replayable(self):
        repo = create_mock_repo()
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )

        await engine._persist_coding_session_final_answer(
            conversation_id="conv-1",
            run_id="run-1",
            step_number=4,
            final_answer="Here is the patch to apply manually.",
            replay_eligible=False,
        )

        persisted_entries = repo.append_coding_session_entries.await_args.args[1]
        assert persisted_entries[0]["content_json"]["replay_eligible"] is False

    @pytest.mark.asyncio
    async def test_refresh_coding_stored_context_excludes_compacted_and_nonreplayable_entries(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=1,
                run_id="run-1",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "first"},
                token_estimate=10,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=2,
                run_id="run-1",
                step_number=1,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "manual fallback", "replay_eligible": False},
                token_estimate=10,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )

        payload = await engine._refresh_coding_stored_context(
            conversation_id="conv-1",
            session_state=CodingSessionState(objective="Fix it"),
            working_memory=WorkingMemory(objective="Fix it"),
        )

        assert payload is not None
        assert payload["replayable_entry_count"] == 1
        assert repo.list_coding_session_entries.await_args.kwargs["include_compacted"] is False

    @pytest.mark.asyncio
    async def test_prepare_coding_prompt_messages_keeps_full_raw_replay_below_pressure(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=1,
                run_id="run-1",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "Earliest exact user request"},
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=2,
                run_id="run-1",
                step_number=1,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Acknowledged and investigating."},
                token_estimate=20,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )
        engine._add_trace_event = AsyncMock()
        session_state = CodingSessionState(objective="Earliest exact user request")

        with (
            patch.object(engine, "_is_coding_profile", return_value=True),
            patch.object(engine._pruner, "estimate_tokens", return_value=100),
        ):
            messages, _, usage_payload = await engine._prepare_coding_prompt_messages(
                conversation_id="conv-1",
                run_id="run-2",
                query="follow-up",
                step_number=2,
                system_prompt="System prompt",
                session_state=session_state,
                working_memory=WorkingMemory(objective="Earliest exact user request"),
            )

        assert any(
            message.get("role") == "user"
            and message.get("content") == "Earliest exact user request"
            for message in messages
        )
        assert usage_payload["reduction_stage"] == "stage0_full_raw_replay"
        assert usage_payload["checkpoint_fallback_activated"] is False
        repo.insert_coding_session_entry.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_prepare_coding_prompt_messages_reduces_tool_payloads_before_dialogue(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=1,
                run_id="run-1",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "Preserve this exact user request"},
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=2,
                run_id="run-1",
                step_number=1,
                entry_type="tool_result",
                role="tool",
                content_json={
                    "tool_call_id": "tc-1",
                    "name": "read_file",
                    "content": "\n".join(f"{i}\t{'x' * 100}" for i in range(1, 140)),
                },
                token_estimate=4000,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=3,
                run_id="run-1",
                step_number=2,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Found the relevant section."},
                token_estimate=20,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )
        engine._add_trace_event = AsyncMock()
        session_state = CodingSessionState(objective="Preserve this exact user request")

        def estimate_tokens(messages):
            return sum(len(str(message.get("content") or "")) for message in messages) // 20

        with (
            patch.object(engine, "_is_coding_profile", return_value=True),
            patch.object(engine, "_coding_pressure_threshold_tokens", return_value=500),
            patch.object(engine._pruner, "estimate_tokens", side_effect=estimate_tokens),
        ):
            messages, _, usage_payload = await engine._prepare_coding_prompt_messages(
                conversation_id="conv-1",
                run_id="run-2",
                query="follow-up",
                step_number=2,
                system_prompt="System prompt",
                session_state=session_state,
                working_memory=WorkingMemory(objective="Preserve this exact user request"),
            )

        tool_messages = [message for message in messages if message.get("role") == "tool"]
        assert tool_messages
        assert "... [middle omitted under prompt pressure] ..." in tool_messages[0]["content"]
        assert any(
            message.get("role") == "user"
            and message.get("content") == "Preserve this exact user request"
            for message in messages
        )
        assert usage_payload["reduction_stage"] == "stage1_tool_payload_reduced"
        assert usage_payload["checkpoint_fallback_activated"] is False

    @pytest.mark.asyncio
    async def test_prepare_coding_prompt_messages_activates_checkpoint_fallback_only_after_staged_reduction(self):
        repo = create_mock_repo()
        repo.list_coding_session_entries.return_value = [
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=1,
                run_id="run-1",
                step_number=0,
                entry_type="user",
                role="user",
                content_json={"content": "Original user goal"},
                token_estimate=20,
            ).to_dict(),
            CodingSessionEntry(
                conversation_id="conv-1",
                seq=2,
                run_id="run-1",
                step_number=1,
                entry_type="assistant",
                role="assistant",
                content_json={"content": "Earlier assistant context " * 30},
                token_estimate=1000,
            ).to_dict(),
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )
        engine._add_trace_event = AsyncMock()
        session_state = CodingSessionState(objective="Original user goal")

        compact_mock = AsyncMock(return_value=True)
        rebuilt_context = (
            [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "Checkpoint summary"},
                {"role": "user", "content": "Recent raw tail"},
            ],
            MagicMock(),
            [
                CodingSessionEntry(
                    conversation_id="conv-1",
                    seq=3,
                    run_id="run-2",
                    step_number=0,
                    entry_type="compaction_summary",
                    role="user",
                    content_json={"content": "Checkpoint summary"},
                    token_estimate=20,
                ),
            ],
            {"stored_tokens": 10, "replayable_entry_count": 2, "context_window": 100000, "utilization_pct": 0.0},
            {
                "conversation_id": "conv-1",
                "transcript_source": "coding_session_entries",
                "used_session_entries": True,
                "metadata_included": False,
                "replayed_entry_count": 2,
                "message_count": 3,
                "prompt_tokens": 80,
                "stored_context_tokens": 10,
                "checkpoint_present": True,
                "preserved_tail_count": 1,
                "restored_file_count": 0,
                "replay_source_ranges": {},
            },
        )

        with (
            patch.object(engine, "_is_coding_profile", return_value=True),
            patch.object(engine, "_coding_pressure_threshold_tokens", return_value=100),
            patch.object(
                engine._pruner,
                "estimate_tokens",
                side_effect=[200, 180, 160, 80],
            ),
            patch.object(engine, "_compact_coding_session_history", compact_mock),
            patch.object(
                engine,
                "_build_coding_session_context_from_entries",
                side_effect=[
                    await engine._build_coding_session_context_from_entries(
                        conversation_id="conv-1",
                        system_prompt="System prompt",
                        query="follow-up",
                        session_state=session_state,
                        working_memory=WorkingMemory(objective="Original user goal"),
                    ),
                    rebuilt_context,
                ],
            ),
        ):
            messages, _, usage_payload = await engine._prepare_coding_prompt_messages(
                conversation_id="conv-1",
                run_id="run-2",
                query="follow-up",
                step_number=2,
                system_prompt="System prompt",
                session_state=session_state,
                working_memory=WorkingMemory(objective="Original user goal"),
            )

        assert messages[1]["content"] == "Checkpoint summary"
        assert usage_payload["reduction_stage"] == "stage4_checkpoint_fallback"
        assert usage_payload["checkpoint_fallback_activated"] is True
        compact_mock.assert_awaited_once()
        assert compact_mock.await_args.kwargs["prompt_tokens_before_reduction"] == 200


# =============================================================================
# AgentEngine Run Tests
# =============================================================================


class TestAgentEngineRun:
    """Tests for AgentEngine.run() method."""

    def test_view_image_schema_hidden_for_text_only_models(self):
        """Text-only models must not see view_image because follow-up image payloads fail."""
        provider = create_mock_provider()
        provider._supports_vision = False
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "view_image"}},
        ]
        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=registry,
        )

        schemas = engine._available_tool_schemas()

        assert [schema["function"]["name"] for schema in schemas] == ["read_file"]

    def test_view_image_instruction_hidden_for_text_only_models(self):
        """Text-only prompts should not ask the model to use a hidden image tool."""
        provider = create_mock_provider()
        provider._supports_vision = False
        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        prompt = engine._effective_system_prompt(
            "- Prefer `grep` and `read_file` over broad exploration.\n"
            "- Use `view_image` for workspace screenshots/images/charts/forms/diagrams when the user asks you to inspect images or visual content. Do not rely on OCR first unless exact text extraction is specifically needed.\n"
            "- Use `bash` for verification.\n"
        )

        assert "view_image" not in prompt
        assert "Use `bash`" in prompt

    def test_normalize_system_messages_merges_into_leading_system(self):
        """Strict providers reject system messages after the beginning."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        messages = engine._normalize_system_messages(
            [
                {"role": "system", "content": "Base prompt"},
                {"role": "user", "content": "Question"},
                {"role": "system", "content": "WORKING MEMORY\nObjective: answer"},
                {"role": "assistant", "content": "Thinking"},
            ]
        )

        assert messages[0] == {
            "role": "system",
            "content": "Base prompt\n\nWORKING MEMORY\nObjective: answer",
        }
        assert [message["role"] for message in messages] == [
            "system",
            "user",
            "assistant",
        ]

    @pytest.mark.asyncio
    async def test_call_llm_filters_view_image_for_text_only_models(self):
        """The actual provider call should receive the same filtered schema list."""
        provider = create_mock_provider()
        provider._supports_vision = False
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "view_image"}},
        ]
        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=registry,
        )

        await engine._call_llm_with_tools(
            messages=[{"role": "user", "content": "inspect images"}],
            event_callback=None,
            run_id="run-vision-filter",
        )

        call_kwargs = provider.complete_streaming.call_args.kwargs
        assert [schema["function"]["name"] for schema in call_kwargs["tools"]] == ["read_file"]

    @pytest.mark.asyncio
    async def test_call_llm_merges_multiple_system_messages_for_provider(self):
        """Provider calls should never contain non-leading system messages."""
        provider = create_mock_provider()
        registry = create_mock_registry()
        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=registry,
        )

        await engine._call_llm_with_tools(
            messages=[
                {"role": "system", "content": "Base prompt"},
                {"role": "user", "content": "Question"},
                {"role": "system", "content": "WORKING MEMORY\nObjective: answer"},
            ],
            event_callback=None,
            run_id="run-system-normalize",
        )

        sent_messages = provider.complete_streaming.call_args.kwargs["messages"]
        assert [message["role"] for message in sent_messages] == ["system", "user"]
        assert sent_messages[0]["content"] == "Base prompt\n\nWORKING MEMORY\nObjective: answer"

    @pytest.mark.asyncio
    async def test_simple_query_no_tools(self):
        """Agent synthesizes directly without tools."""
        provider = create_mock_provider(
            response_text="The population of Tokyo is about 14 million."
        )
        repo = create_mock_repo()
        registry = create_mock_registry()

        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
            )

            events = []
            result = await engine.run(
                run_id="test-run",
                query="What is Tokyo's population?",
                event_callback=lambda e: events.append(e),
            )

        assert result.success is True
        assert "14 million" in result.final_answer
        assert any(e["type"] == "agent_started" for e in events)
        assert any(e["type"] == "agent_complete" for e in events)

    @pytest.mark.asyncio
    async def test_plan_mode_does_not_persist_coding_session_context(self, tmp_path: Path):
        """Plan exploration reads must not replay as implementation file evidence."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "App.tsx").write_text(
            "export function App() { return <div>Hello</div>; }\n",
            encoding="utf-8",
        )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="I'll inspect first.",
                    tool_calls=[
                        {
                            "id": "tc-read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"file_path": "src/App.tsx"}',
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text=(
                        "Ready.\n"
                        "<proposed_plan>\n"
                        "Update src/App.tsx after re-reading it in Default Mode.\n"
                        "</proposed_plan>"
                    )
                ),
            ]
        )

        registry = create_mock_registry()
        read_tool = ReadFileTool(str(tmp_path))
        registry.get.side_effect = (
            lambda name: read_tool if name == "read_file" else None
        )
        registry.get_openai_schemas.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        repo = create_mock_repo()
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )
        mock_sm.record_tool_call.return_value = {"id": "tc-read", "status": "pending"}

        async def approve_plan(
            _run_id: str, _plan_id: str, _markdown: str
        ) -> PlanDecision:
            return PlanDecision(decision="approved", implementation_run_id="impl-run")

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            profile = MagicMock()
            profile.name = "coding"
            profile.max_steps = 5
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
                profile=profile,
                planning_enabled=False,
                collaboration_mode="plan",
                plan_approval_callback=approve_plan,
            )
            result = await engine.run(
                run_id="plan-run",
                query="Plan the App update",
                conversation_id="conv-plan",
            )

        assert result.success is True
        assert (
            result.approved_plan
            == "Update src/App.tsx after re-reading it in Default Mode."
        )
        repo.get_coding_session_state.assert_not_awaited()
        repo.get_latest_coding_session_entry_seq.assert_not_awaited()
        repo.append_coding_session_entries.assert_not_awaited()
        repo.upsert_coding_session_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raw_tool_results_persist_for_full_run(self):
        """Exact tool results stay available across later steps in the same run."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="I'll inspect the file.",
                    tool_calls=[
                        {
                            "id": "tc-read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"file_path": "src/chart.ts"}',
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text="Now validate with a build.",
                    tool_calls=[
                        {
                            "id": "tc-bash",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command": "npm run build"}',
                            },
                        }
                    ],
                ),
                LLMResponse(text="Done."),
            ]
        )
        repo = create_mock_repo()
        registry = create_mock_registry()
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
            ],
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
            )
            with patch.object(
                engine,
                "_execute_tool_calls",
                AsyncMock(
                    side_effect=[
                        [
                            (
                                ParsedToolCall(
                                    id="tc-read",
                                    name="read_file",
                                    arguments={"file_path": "src/chart.ts"},
                                    raw_arguments='{"file_path": "src/chart.ts"}',
                                ),
                                ToolResult(
                                    success=True,
                                    result_summary="Read 20 lines from src/chart.ts",
                                    result_data="1\tconst points = data.sort(desc)\n2\texport default points\n",
                                ),
                            )
                        ],
                        [
                            (
                                ParsedToolCall(
                                    id="tc-bash",
                                    name="bash",
                                    arguments={"command": "npm run build"},
                                    raw_arguments='{"command": "npm run build"}',
                                ),
                                ToolResult(
                                    success=True,
                                    result_summary="Command succeeded (exit 0): npm run build",
                                    result_data={
                                        "exit_code": 0,
                                        "stdout": "build ok",
                                        "stderr": "",
                                        "timed_out": False,
                                    },
                                ),
                            )
                        ],
                    ],
                ),
            ):
                result = await engine.run(
                    run_id="test-run",
                    query="Fix the chart ordering",
                )

        assert result.success is True
        first_call_messages = provider.complete_streaming.call_args_list[0].kwargs["messages"]
        second_call_messages = provider.complete_streaming.call_args_list[1].kwargs["messages"]
        third_call_messages = provider.complete_streaming.call_args_list[2].kwargs["messages"]

        assert not any(msg.get("role") == "tool" for msg in first_call_messages)
        assert any(
            msg.get("role") == "tool" and msg.get("name") == "read_file"
            for msg in second_call_messages
        )
        assert any(
            msg.get("role") == "tool" and msg.get("name") == "read_file"
            for msg in third_call_messages
        )
        assert any(
            msg.get("role") == "tool" and msg.get("name") == "bash"
            for msg in third_call_messages
        )

    @pytest.mark.asyncio
    async def test_emits_step_started_event(self):
        """Step started event is emitted."""
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=create_mock_provider(),
                repo=create_mock_repo(),
                registry=create_mock_registry(),
            )

            events = []
            await engine.run(
                run_id="test-run",
                query="Test query",
                event_callback=lambda e: events.append(e),
            )

        step_events = [e for e in events if e["type"] == "step_started"]
        assert len(step_events) == 1
        assert step_events[0]["step_number"] == 1

    @pytest.mark.asyncio
    async def test_emits_synthesizing_event(self):
        """Synthesizing event is emitted."""
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=create_mock_provider(),
                repo=create_mock_repo(),
                registry=create_mock_registry(),
            )

            events = []
            await engine.run(
                run_id="test-run",
                query="Test query",
                event_callback=lambda e: events.append(e),
            )

        synth_events = [e for e in events if e["type"] == "synthesizing"]
        assert len(synth_events) == 1

    @pytest.mark.asyncio
    async def test_handles_llm_error(self):
        """Handles LLM call errors gracefully."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=Exception("LLM connection failed")
        )

        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=create_mock_registry(),
            )

            result = await engine.run(run_id="test-run", query="Test query")

        assert result.success is False
        assert "LLM connection failed" in result.error_message
        mock_sm.error_step.assert_called_once()
        mock_sm.error_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_blank_llm_error_is_persisted_with_type_and_error_trace(self):
        """Blank timeout-like LLM errors keep type info and close the trace span."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=TimeoutError())
        trace_repo = MagicMock()
        trace_repo.add_trace_event = AsyncMock(
            side_effect=[
                "agent-start-event",
                "step-start-event",
                "llm-request-event",
                "llm-error-event",
            ]
        )

        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=create_mock_registry(),
                trace_repo=trace_repo,
            )

            result = await engine.run(run_id="test-run", query="Test query")

        assert result.success is False
        assert result.error_message
        assert "TimeoutError" in result.error_message
        mock_sm.error_step.assert_called_once_with(result.error_message)
        mock_sm.error_run.assert_called_once_with(result.error_message)

        trace_calls = trace_repo.add_trace_event.await_args_list
        llm_request_call = next(
            call for call in trace_calls if call.kwargs["event_type"] == "llm_request"
        )
        llm_error_call = next(
            call
            for call in trace_calls
            if call.kwargs["event_type"] == "llm_response"
            and call.kwargs["event_status"] == "error"
        )
        assert llm_request_call.kwargs["event_status"] == "pending"
        assert llm_error_call.kwargs["parent_event_id"] == "llm-request-event"
        assert llm_error_call.kwargs["content"]["error_message"] == result.error_message

    @pytest.mark.asyncio
    async def test_handles_recovery_context(self):
        """Handles crash recovery context."""
        hint = {"role": "system", "content": "Recovery hint"}
        recovery_ctx = RecoveryContext(
            needs_recovery=True,
            interrupted_tool_calls=[],
            hints=[hint],
            last_completed_step=1,
        )

        mock_sm = create_mock_state_machine()
        mock_sm.initialize = AsyncMock(return_value=recovery_ctx)

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=create_mock_provider(),
                repo=create_mock_repo(),
                registry=create_mock_registry(),
            )

            result = await engine.run(run_id="test-run", query="Test query")

        assert result.success is True
        # Recovery messages should have been injected


class TestAgentEngineToolExecution:
    """Tests for tool execution in AgentEngine."""

    @pytest.mark.asyncio
    async def test_executes_tool_call(self):
        """Executes tool calls from LLM response."""
        # First call returns tool call, second returns answer
        call_count = 0

        async def mock_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    text="I'll search for this.",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "test"}',
                            },
                        }
                    ],
                )
            else:
                return LLMResponse(
                    text="Based on my search, the answer is X.",
                    tool_calls=None,
                )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_streaming)

        # Mock tool
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Found 5 results",
                result_data={"results": []},
                duration_ms=150,
            )
        )

        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}}
        ]
        registry.get.return_value = mock_tool
        registry.is_idempotent.return_value = True

        # Create mock state machine that allows 2 steps
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )
        # Return same ID as tool_call to indicate this is a new call (not cached)
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-1"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=registry,
            )

            events = []
            result = await engine.run(
                run_id="test-run",
                query="Test query",
                event_callback=lambda e: events.append(e),
            )

        assert result.success is True
        mock_tool.execute.assert_called_once_with(query="test")

        # Check tool events
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_starts) == 1
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is True


    @pytest.mark.asyncio
    async def test_model_can_edit_two_files_with_exec_python_script(self, tmp_path):
        (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("two\n", encoding="utf-8")
        cmd = (
            "python3 -c \"from pathlib import Path; "
            "a=Path('a.txt'); b=Path('b.txt'); "
            "assert a.read_text(encoding='utf-8') == 'one\\\\n'; "
            "assert b.read_text(encoding='utf-8') == 'two\\\\n'; "
            "a.write_text('ONE\\\\n', encoding='utf-8'); "
            "b.write_text('TWO\\\\n', encoding='utf-8')\""
        )
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="Editing both files with a checked Python script.",
                    tool_calls=[
                        {
                            "id": "tc-exec-edit",
                            "function": {
                                "name": "exec_command",
                                "arguments": json.dumps({"cmd": cmd}),
                            },
                        }
                    ],
                ),
                LLMResponse(text="Done.", tool_calls=None),
            ]
        )
        registry = ToolRegistry()
        registry.register(ExecCommandTool(CommandSessionManager(str(tmp_path))))
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[{"step_number": 1, "id": "step-1"}, {"step_number": 2, "id": "step-2"}],
        )
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-exec-edit"})

        with patch("orchestrator.agent.agent_engine.AgentStateMachine", return_value=mock_sm):
            engine = AgentEngine(provider=provider, repo=create_mock_repo(), registry=registry)
            events = []
            result = await engine.run(
                "run-patch",
                "edit files",
                event_callback=lambda e: events.append(e),
            )

        assert result.success is True
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "ONE\n"
        assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "TWO\n"
        tool_result = next(e for e in events if e["type"] == "tool_result")
        assert tool_result["tool_name"] == "exec_command"
        assert tool_result["success"] is True

    @pytest.mark.asyncio
    async def test_model_can_run_and_poll_exec_command(self, tmp_path):
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="Running focused check.",
                    tool_calls=[
                        {
                            "id": "tc-exec",
                            "function": {
                                "name": "exec_command",
                                "arguments": json.dumps(
                                    {
                                        "cmd": (
                                            "python3 -c 'import time; "
                                            "print(\"start\", flush=True); "
                                            "time.sleep(.3); "
                                            "print(\"done\", flush=True)'"
                                        ),
                                        "yield_time_ms": 50,
                                    }
                                ),
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text="Polling.",
                    tool_calls=[
                        {
                            "id": "tc-poll",
                            "function": {
                                "name": "write_stdin",
                                "arguments": '{"session_id":1,"yield_time_ms":1000}',
                            },
                        }
                    ],
                ),
                LLMResponse(text="Done.", tool_calls=None),
            ]
        )
        manager = CommandSessionManager(str(tmp_path))
        registry = ToolRegistry()
        registry.register(ExecCommandTool(manager))
        registry.register(WriteStdinTool(manager))
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(
            side_effect=lambda *args, **kwargs: {"id": kwargs["tool_call_id"]}
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(provider=provider, repo=create_mock_repo(), registry=registry)
            events = []
            result = await engine.run(
                "run-exec",
                "run tests",
                event_callback=lambda e: events.append(e),
            )

        assert result.success is True
        command_events = [e for e in events if e["type"] == "tool_result"]
        assert command_events[0]["tool_name"] == "exec_command"
        assert command_events[0]["bash_output"]["exit_code"] is None
        assert command_events[1]["tool_name"] == "write_stdin"
        assert command_events[1]["bash_output"]["exit_code"] == 0
        assert "done" in command_events[1]["bash_output"]["stdout"]

    @pytest.mark.asyncio
    async def test_handles_unknown_tool(self):
        """Handles unknown tool gracefully."""
        # First call returns tool call, second returns answer
        call_count = 0

        async def mock_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    text="Let me use a tool.",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "function": {
                                "name": "unknown_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                )
            else:
                return LLMResponse(
                    text="The tool was not found.",
                    tool_calls=None,
                )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_streaming)

        registry = MagicMock()
        registry.get_openai_schemas.return_value = []
        registry.get.return_value = None  # Tool not found

        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )
        # Return same ID as tool_call to indicate this is a new call (not cached)
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-1"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=registry,
            )

            events = []
            # This will fail because unknown tool, but should handle gracefully
            await engine.run(
                run_id="test-run",
                query="Test",
                event_callback=lambda e: events.append(e),
            )

        # Should have emitted tool_result with error
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is False

    @pytest.mark.asyncio
    async def test_handles_tool_execution_error(self):
        """Handles tool execution errors."""
        # First call returns tool call, second returns answer
        call_count = 0

        async def mock_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    text="Let me search.",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "test"}',
                            },
                        }
                    ],
                )
            else:
                return LLMResponse(
                    text="Search failed but here's my answer.",
                    tool_calls=None,
                )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_streaming)

        # Mock tool that throws
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(side_effect=Exception("API rate limited"))

        registry = MagicMock()
        registry.get_openai_schemas.return_value = []
        registry.get.return_value = mock_tool

        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )
        # Return same ID as tool_call to indicate this is a new call (not cached)
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-1"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=registry,
            )

            events = []
            await engine.run(
                run_id="test-run",
                query="Test",
                event_callback=lambda e: events.append(e),
            )

        # Should have recorded the error
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is False

    @pytest.mark.asyncio
    async def test_stalls_after_repeated_filtered_duplicate_tool_calls(self):
        """Repeated duplicate tool calls should fail clearly instead of force synthesis."""
        call_count = 0
        captured_messages = []

        async def mock_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            captured_messages.append(kwargs["messages"])
            if call_count == 1:
                return LLMResponse(
                    text="Let me inspect git status.",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command": "git status"}',
                            },
                        }
                    ],
                )
            if call_count in (2, 3):
                return LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": f"tc-{call_count}",
                            "function": {
                                "name": "bash",
                                "arguments": '{"command": "git status"}',
                            },
                        }
                    ],
                )
            return LLMResponse(
                text="I already checked git status. The revert is complete.",
                tool_calls=None,
            )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_streaming)

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Command succeeded (exit 0): git status",
                result_data={
                    "command": "git status",
                    "exit_code": 0,
                    "stdout": "clean",
                    "stderr": "",
                    "truncated": False,
                },
                duration_ms=50,
            )
        )

        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "bash"}}
        ]
        registry.get.return_value = mock_tool
        registry.is_idempotent.return_value = True

        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-1"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=registry,
            )

            result = await engine.run(
                run_id="test-run",
                query="Revert the previous change",
            )

        assert result.success is False
        assert "repeated filtered tool calls" in (result.error_message or "")
        assert mock_tool.execute.call_count == 1
        assert provider.complete_streaming.call_count == 3

        decisions = [
            call.kwargs.get("decision")
            for call in mock_sm.complete_step.await_args_list
        ]
        assert decisions == ["call_tool", "filtered", "filtered"]
        assert any(
            "Engine notice: the previous tool call was filtered as redundant"
            in message["content"]
            for batch in captured_messages[2:]
            for message in batch
            if message["role"] == "system"
        )
        assert any(
            "Do not attribute that constraint to the user."
            in message["content"]
            for batch in captured_messages[2:]
            for message in batch
            if message["role"] == "user"
        )


class TestAgentEngineCitations:
    """Tests for citation handling."""

    @pytest.mark.asyncio
    async def test_stores_citations_from_search(self):
        """Stores citations from web_search results."""
        repo = create_mock_repo()

        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )

        result_data = {
            "results": [
                {"url": "http://example.com/1", "title": "Result 1", "snippet": "..."},
                {"url": "http://example.com/2", "title": "Result 2", "snippet": "..."},
            ]
        }

        await engine._store_citations_from_tool(
            run_id="run-1",
            tool_call_id="tc-1",
            tool_name="web_search",
            result_data=result_data,
        )

        assert repo.create_citation.call_count == 2

    @pytest.mark.asyncio
    async def test_stores_citations_from_extract(self):
        """Stores citations from web_extract results."""
        repo = create_mock_repo()

        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )

        result_data = {
            "url": "http://example.com",
            "title": "Page Title",
            "content": "Extracted content here...",
        }

        await engine._store_citations_from_tool(
            run_id="run-1",
            tool_call_id="tc-1",
            tool_name="web_extract",
            result_data=result_data,
        )

        repo.create_citation.assert_called_once()

    @pytest.mark.asyncio
    async def test_marks_citations_used_by_reference(self):
        """Marks citations used when referenced by [1], [2] etc."""
        repo = create_mock_repo()
        repo.get_citations_for_run = AsyncMock(
            return_value=[
                {"id": "c-1", "source_url": "http://example1.com"},
                {"id": "c-2", "source_url": "http://example2.com"},
            ]
        )

        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )

        answer = "According to [1], the answer is X. See also [2]."
        _ = await engine._extract_and_store_citations("run-1", answer)

        repo.mark_citations_used.assert_called_once()
        # Both citations should be marked
        call_args = repo.mark_citations_used.call_args[0][0]
        assert "c-1" in call_args
        assert "c-2" in call_args

    @pytest.mark.asyncio
    async def test_marks_citations_used_by_url(self):
        """Marks citations used when URL appears in answer."""
        repo = create_mock_repo()
        repo.get_citations_for_run = AsyncMock(
            return_value=[
                {"id": "c-1", "source_url": "http://example.com/page"},
            ]
        )

        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=repo,
            registry=create_mock_registry(),
        )

        answer = "According to http://example.com/page, the answer is X."
        _ = await engine._extract_and_store_citations("run-1", answer)

        repo.mark_citations_used.assert_called_once()
        call_args = repo.mark_citations_used.call_args[0][0]
        assert "c-1" in call_args


class TestAgentEngineForceSynthesis:
    """Tests for forced synthesis."""

    @pytest.mark.asyncio
    async def test_force_synthesis_adds_message(self):
        """Force synthesis adds instruction message."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(text="Forced answer", tool_calls=None)
        )

        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        events = []
        result = await engine._force_synthesis(
            messages=[{"role": "system", "content": "System"}],
            event_callback=lambda e: events.append(e),
            run_id="run-1",
        )

        assert result == "Forced answer"
        # Check that tools=None was passed
        call_kwargs = provider.complete_streaming.call_args[1]
        assert call_kwargs["tools"] is None

        # Check synthesizing event
        synth_events = [e for e in events if e["type"] == "synthesizing"]
        assert len(synth_events) == 1
        assert synth_events[0].get("forced") is True


class TestAgentEngineFindingsAccumulator:
    """Tests for findings accumulator feature."""

    def test_findings_initialized_empty(self):
        """Findings list is initialized empty."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )
        assert engine._findings == []
        assert engine._current_query is None

    def test_extract_finding_from_web_search(self):
        """Extracts finding from web_search result."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        finding = engine._extract_finding_from_result(
            tool_name="web_search",
            arguments={"query": "capital of France"},
            result_summary="Found 5 results about Paris being the capital of France.",
            step_number=1,
        )

        assert finding is not None
        assert finding["step"] == 1
        assert finding["tool"] == "web_search"
        assert finding["query"] == "capital of France"
        assert "Search for 'capital of France'" in finding["content"]

    def test_extract_finding_from_web_extract(self):
        """Extracts finding from web_extract result."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        finding = engine._extract_finding_from_result(
            tool_name="web_extract",
            arguments={"urls": ["http://example.com/page"]},
            result_summary="The article discusses the history of the Eiffel Tower...",
            step_number=2,
        )

        assert finding is not None
        assert finding["step"] == 2
        assert finding["tool"] == "web_extract"
        assert "example.com" in finding["url"]
        assert "Extracted from" in finding["content"]

    def test_extract_finding_from_python_success(self):
        """Extracts finding from successful python_execute result."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        finding = engine._extract_finding_from_result(
            tool_name="python_execute",
            arguments={"code": "print(2 + 2)"},
            result_summary="The calculation result is 42.",
            step_number=3,
        )

        assert finding is not None
        assert finding["step"] == 3
        assert finding["tool"] == "python_execute"
        assert "Python result:" in finding["content"]

    def test_extract_finding_skips_python_error(self):
        """Skips extraction for python_execute with error."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        finding = engine._extract_finding_from_result(
            tool_name="python_execute",
            arguments={"code": "invalid code"},
            result_summary="Error: SyntaxError: invalid syntax",
            step_number=3,
        )

        assert finding is None

    def test_extract_finding_skips_short_content(self):
        """Skips extraction for very short content."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        finding = engine._extract_finding_from_result(
            tool_name="web_search",
            arguments={"query": "test"},
            result_summary="No results",  # Too short
            step_number=1,
        )

        assert finding is None

    def test_extract_finding_truncates_long_content(self):
        """Truncates long content in finding."""
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        long_summary = "A" * 500  # Longer than 300 char limit for web_search
        finding = engine._extract_finding_from_result(
            tool_name="web_search",
            arguments={"query": "test"},
            result_summary=long_summary,
            step_number=1,
        )

        assert finding is not None
        assert finding["content"].endswith("...")
        assert len(finding["content"]) < len(long_summary) + 50  # Some overhead for prefix

    @pytest.mark.asyncio
    async def test_force_synthesis_includes_findings(self):
        """Force synthesis prompt includes accumulated findings."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(text="Synthesized answer", tool_calls=None)
        )

        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        # Set up findings
        engine._current_query = "What is the capital of France?"
        engine._findings = [
            {"step": 1, "tool": "web_search", "content": "Search for 'capital of France': Paris is the capital."},
            {"step": 2, "tool": "web_extract", "content": "Extracted from wikipedia.org: Paris has been the capital since..."},
        ]

        _ = await engine._force_synthesis(
            messages=[{"role": "system", "content": "System"}],
            event_callback=lambda e: None,
            run_id="run-1",
        )

        # Check that the prompt includes findings
        call_args = provider.complete_streaming.call_args
        messages = call_args[1]["messages"]
        last_message = messages[-1]["content"]

        assert "KEY FINDINGS" in last_message
        assert "2 items" in last_message
        assert "capital of France" in last_message
        assert "Paris is the capital" in last_message

    @pytest.mark.asyncio
    async def test_force_synthesis_without_findings(self):
        """Force synthesis works without findings (fallback prompt)."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(text="Synthesized answer", tool_calls=None)
        )

        engine = AgentEngine(
            provider=provider,
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        # No findings set
        engine._findings = []

        _ = await engine._force_synthesis(
            messages=[{"role": "system", "content": "System"}],
            event_callback=lambda e: None,
            run_id="run-1",
        )

        # Check that fallback prompt is used
        call_args = provider.complete_streaming.call_args
        messages = call_args[1]["messages"]
        last_message = messages[-1]["content"]

        assert "KEY FINDINGS" not in last_message
        assert "MAXIMUM STEPS REACHED" in last_message


# =============================================================================
# Redundancy Detection Tests
# =============================================================================


class TestRedundancyDetection:
    """Tests for _detect_redundant_calls method."""

    def _make_engine(self):
        return AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

    def test_detects_exact_duplicate(self):
        """Flags tool calls that match a previous call exactly."""
        engine = self._make_engine()
        engine._tool_call_log = [
            {
                "tool_name": "web_search",
                "arguments": {"query": "Tokyo population"},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
        ]

        calls = [ParsedToolCall(id="tc-2", name="web_search", arguments={"query": "Tokyo population"}, raw_arguments='{"query": "Tokyo population"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert "Duplicate" in redundant[0][1]

    def test_allows_different_arguments(self):
        """Does not flag calls with different arguments."""
        engine = self._make_engine()
        engine._tool_call_log = [
            {
                "tool_name": "web_search",
                "arguments": {"query": "Tokyo population"},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
        ]

        calls = [ParsedToolCall(id="tc-2", name="web_search", arguments={"query": "Paris population"}, raw_arguments='{"query": "Paris population"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0

    def test_allows_read_file_rereads(self):
        """Same-run read_file calls are allowed so exact context can be reacquired."""
        engine = self._make_engine()
        engine._tool_call_log = [
            {
                "tool_name": "read_file",
                "arguments": {"file_path": "src/chart.ts"},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
        ]

        calls = [ParsedToolCall(id="tc-2", name="read_file", arguments={"file_path": "src/chart.ts"}, raw_arguments='{"file_path": "src/chart.ts"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0

    def test_detects_broad_glob_star_py(self):
        """Flags overly broad glob **/*.py."""
        engine = self._make_engine()
        calls = [ParsedToolCall(id="tc-1", name="glob", arguments={"pattern": "**/*.py"}, raw_arguments='{"pattern": "**/*.py"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert "Too broad" in redundant[0][1]

    def test_detects_broad_glob_star_md(self):
        """Flags overly broad glob **/*.md."""
        engine = self._make_engine()
        calls = [ParsedToolCall(id="tc-1", name="glob", arguments={"pattern": "**/*.md"}, raw_arguments='{"pattern": "**/*.md"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert "Too broad" in redundant[0][1]

    def test_allows_targeted_glob(self):
        """Does not flag targeted glob patterns."""
        engine = self._make_engine()
        calls = [ParsedToolCall(id="tc-1", name="glob", arguments={"pattern": "src/**/*.py"}, raw_arguments='{"pattern": "src/**/*.py"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0

    def test_detects_repeated_list_directory(self):
        """Flags repeated list_directory on root."""
        engine = self._make_engine()
        engine._tool_call_log = [
            {
                "tool_name": "list_directory",
                "arguments": {"path": "."},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
        ]

        calls = [ParsedToolCall(id="tc-2", name="list_directory", arguments={"path": "."}, raw_arguments='{"path": "."}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert "Duplicate" in redundant[0][1]

    def test_allows_first_list_directory(self):
        """Does not flag the first list_directory call."""
        engine = self._make_engine()
        # No previous list_directory in log
        calls = [ParsedToolCall(id="tc-1", name="list_directory", arguments={"path": "."}, raw_arguments='{"path": "."}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0

    def test_empty_tool_call_log(self):
        """No redundancy when log is empty."""
        engine = self._make_engine()
        calls = [ParsedToolCall(id="tc-1", name="web_search", arguments={"query": "test"}, raw_arguments='{"query": "test"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0

    def test_multiple_calls_mixed_redundancy(self):
        """Correctly identifies subset of redundant calls."""
        engine = self._make_engine()
        engine._tool_call_log = [
            {
                "tool_name": "web_search",
                "arguments": {"query": "test"},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
        ]

        calls = [
            ParsedToolCall(id="tc-a", name="web_search", arguments={"query": "test"}, raw_arguments='{"query": "test"}'),
            ParsedToolCall(id="tc-b", name="web_search", arguments={"query": "new query"}, raw_arguments='{"query": "new query"}'),
        ]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert redundant[0][0].id == "tc-a"

    def test_allows_duplicate_bash_after_edit_changes_state(self):
        """Allows repeating verification commands after an edit changed state."""
        engine = self._make_engine()
        engine._tool_state_version = 1
        engine._tool_call_log = [
            {
                "tool_name": "bash",
                "arguments": {"command": "npm run build"},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
            {
                "tool_name": "edit_file",
                "arguments": {"file_path": "src/App.tsx"},
                "success": True,
                "step_number": 2,
                "state_version_after": 1,
            },
        ]

        calls = [ParsedToolCall(id="tc-3", name="bash", arguments={"command": "npm run build"}, raw_arguments='{"command": "npm run build"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0

    def test_blocks_duplicate_edit_without_state_change(self):
        """Still blocks identical edits when nothing changed since the last one."""
        engine = self._make_engine()
        engine._tool_state_version = 2
        engine._tool_call_log = [
            {
                "tool_name": "edit_file",
                "arguments": {"file_path": "src/App.tsx", "old_string": "a", "new_string": "b"},
                "success": True,
                "step_number": 3,
                "state_version_after": 2,
            },
        ]

        calls = [ParsedToolCall(id="tc-4", name="edit_file", arguments={"file_path": "src/App.tsx", "old_string": "a", "new_string": "b"}, raw_arguments='{"file_path": "src/App.tsx", "old_string": "a", "new_string": "b"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1

    def test_blocks_same_failed_edit_without_reread(self):
        """Exact failed edit retries require rereading first."""
        engine = self._make_engine()
        engine._tool_state_version = 3
        engine._tool_call_log = [
            {
                "tool_name": "edit_file",
                "arguments": {
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                "success": False,
                "step_number": 4,
                "state_version_after": 3,
                "result_metadata": {"match_failure_type": "not_found"},
            },
        ]
        engine._edit_failures = {
            "src/App.tsx": {
                "arguments": {
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                "failure_type": "not_found",
                "file_read_sequence_at_failure": 1,
            }
        }
        engine._file_last_read_sequences = {"src/App.tsx": 1}

        calls = [
            ParsedToolCall(
                id="tc-edit",
                name="edit_file",
                arguments={
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                raw_arguments='{"file_path": "src/App.tsx", "old_string": "const a = 1;", "new_string": "const a = 2;"}',
            )
        ]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert "rereading the file first" in redundant[0][1]

    def test_allows_same_failed_edit_after_reread(self):
        """A reread clears the redundant-filter block for the same edit."""
        engine = self._make_engine()
        engine._tool_state_version = 3
        engine._tool_call_log = [
            {
                "tool_name": "edit_file",
                "arguments": {
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                "success": False,
                "step_number": 4,
                "state_version_after": 3,
                "result_metadata": {"match_failure_type": "not_found"},
            },
        ]
        engine._edit_failures = {
            "src/App.tsx": {
                "arguments": {
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                "failure_type": "not_found",
                "file_read_sequence_at_failure": 1,
            }
        }
        engine._file_last_read_sequences = {"src/App.tsx": 2}

        calls = [
            ParsedToolCall(
                id="tc-edit",
                name="edit_file",
                arguments={
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                raw_arguments='{"file_path": "src/App.tsx", "old_string": "const a = 1;", "new_string": "const a = 2;"}',
            )
        ]
        redundant = engine._detect_redundant_calls(calls)

        assert redundant == []

    def test_allows_materially_changed_edit_args_after_failure(self):
        """Updated edit args are allowed even after a stale-match failure."""
        engine = self._make_engine()
        engine._tool_state_version = 3
        engine._tool_call_log = [
            {
                "tool_name": "edit_file",
                "arguments": {
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 1;",
                    "new_string": "const a = 2;",
                },
                "success": False,
                "step_number": 4,
                "state_version_after": 3,
                "result_metadata": {"match_failure_type": "not_found"},
            },
        ]

        calls = [
            ParsedToolCall(
                id="tc-edit",
                name="edit_file",
                arguments={
                    "file_path": "src/App.tsx",
                    "old_string": "const a = 2;",
                    "new_string": "const a = 3;",
                },
                raw_arguments='{"file_path": "src/App.tsx", "old_string": "const a = 2;", "new_string": "const a = 3;"}',
            )
        ]
        redundant = engine._detect_redundant_calls(calls)

        assert redundant == []

    def test_apply_patch_success_updates_file_freshness(self):
        """Successful apply_patch increments versions for every changed file."""
        engine = self._make_engine()
        engine._apply_patch_failures = {
            "src/App.tsx": {"file_read_sequence_at_failure": 1}
        }
        tool_call = ParsedToolCall(
            id="tc-patch",
            name="apply_patch",
            arguments={"patch": "*** Begin Patch\n*** Update File: src/App.tsx\n@@\n-old\n+new\n*** End Patch"},
            raw_arguments="{}",
        )
        result = ToolResult(
            success=True,
            result_summary="Applied patch",
            result_data={"changed_files": ["src/App.tsx"], "diff": ""},
            metadata={"changed_files": ["src/App.tsx"]},
        )

        payload = engine._track_file_freshness(tool_call, result)

        assert engine._file_state_versions["src/App.tsx"] == 1
        assert "src/App.tsx" not in engine._apply_patch_failures
        assert payload["changed_files"] == ["src/App.tsx"]

    def test_blocks_edit_fallback_after_apply_patch_failure_until_patch_succeeds(self):
        """A failed patch blocks edit/write fallback even after reread until patch succeeds."""
        engine = self._make_engine()
        failed_patch = ParsedToolCall(
            id="tc-patch",
            name="apply_patch",
            arguments={
                "patch": (
                    "*** Begin Patch\n"
                    "*** Update File: src/App.tsx\n"
                    "@@\n"
                    "-old\n"
                    "+new\n"
                    "*** End Patch"
                )
            },
            raw_arguments="{}",
        )
        engine._track_file_freshness(
            failed_patch,
            ToolResult(
                success=False,
                result_summary="Patch failed: Patch hunk did not match current contents of src/App.tsx",
                error_message="Patch hunk did not match current contents of src/App.tsx",
            ),
        )

        edit_call = ParsedToolCall(
            id="tc-edit",
            name="edit_file",
            arguments={
                "file_path": "src/App.tsx",
                "old_string": "old",
                "new_string": "new",
            },
            raw_arguments="{}",
        )
        redundant = engine._detect_redundant_calls([edit_call])

        assert len(redundant) == 1
        assert "retry apply_patch" in redundant[0][1]
        assert engine._last_redundant_filter_codes["tc-edit"] == (
            "apply_patch_recovery_required"
        )

        engine._file_read_sequence = 1
        engine._file_last_read_sequences["src/App.tsx"] = 1
        assert len(engine._detect_redundant_calls([edit_call])) == 1

        engine._track_file_freshness(
            ParsedToolCall(
                id="tc-patch-2",
                name="apply_patch",
                arguments={
                    "patch": (
                        "*** Begin Patch\n"
                        "*** Update File: src/App.tsx\n"
                        "@@\n"
                        "-old\n"
                        "+new\n"
                        "*** End Patch"
                    )
                },
                raw_arguments="{}",
            ),
            ToolResult(
                success=True,
                result_summary="Applied patch",
                result_data={"changed_files": ["src/App.tsx"], "diff": ""},
                metadata={"changed_files": ["src/App.tsx"]},
            ),
        )
        assert engine._detect_redundant_calls([edit_call]) == []

    def test_successful_command_changes_state_for_verification_retry(self):
        """A successful command/poll allows repeating earlier verification commands."""
        engine = self._make_engine()
        engine._tool_state_version = 1
        engine._tool_call_log = [
            {
                "tool_name": "exec_command",
                "arguments": {"cmd": "npm run build 2>&1", "timeout": 120},
                "success": False,
                "step_number": 1,
                "state_version_after": 1,
            },
        ]
        assert engine._did_tool_call_change_state(
            "write_stdin", ToolResult(success=True, result_summary="done")
        )
        engine._tool_state_version = 2
        engine._tool_call_log.append(
            {
                "tool_name": "write_stdin",
                "arguments": {"session_id": 2},
                "success": True,
                "step_number": 2,
                "state_version_after": 2,
            }
        )

        calls = [
            ParsedToolCall(
                id="tc-build",
                name="exec_command",
                arguments={"cmd": "npm run build 2>&1", "timeout": 120},
                raw_arguments="{}",
            )
        ]

        assert engine._detect_redundant_calls(calls) == []

    def test_allows_duplicate_web_search_after_state_change(self):
        """Allows repeating a search after new evidence changed the working state."""
        engine = self._make_engine()
        engine._tool_state_version = 1
        engine._tool_call_log = [
            {
                "tool_name": "web_search",
                "arguments": {"query": "base-ui select collision padding"},
                "success": True,
                "step_number": 1,
                "state_version_after": 0,
            },
            {
                "tool_name": "web_extract",
                "arguments": {"urls": ["https://example.com"]},
                "success": True,
                "step_number": 2,
                "state_version_after": 1,
            },
        ]

        calls = [ParsedToolCall(id="tc-5", name="web_search", arguments={"query": "base-ui select collision padding"}, raw_arguments='{"query": "base-ui select collision padding"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 0


# =============================================================================
# Synthesis Nudging Tests
# =============================================================================


# =============================================================================
# Parallel Tool Execution Tests
# =============================================================================


class TestEditRecoveryFlow:
    """Regression coverage for edit-failure recovery behavior."""

    def _coding_profile(self):
        profile = MagicMock()
        profile.name = "coding"
        profile.max_steps = 20
        return profile

    def _registry_with_file_tools(self, root: Path):
        registry = create_mock_registry()
        read_tool = ReadFileTool(str(root))
        from orchestrator.agent.tools.edit_file import EditFileTool

        edit_tool = EditFileTool(str(root))
        registry.get.side_effect = (
            lambda name: read_tool
            if name == "read_file"
            else edit_tool
            if name == "edit_file"
            else None
        )
        return registry

    @pytest.mark.asyncio
    async def test_failed_edit_injects_reread_oriented_recovery_messages(self, tmp_path: Path):
        app_file = tmp_path / "App.tsx"
        app_file.write_text("const value = 1;\nconst label = value;\n", encoding="utf-8")

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-edit-1",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": json.dumps(
                                    {
                                        "file_path": "App.tsx",
                                        "old_string": "const value = 1;",
                                        "new_string": "const value = 2;",
                                    }
                                ),
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-edit-2",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": json.dumps(
                                    {
                                        "file_path": "App.tsx",
                                        "old_string": "const value = 1;\nconst label = value;",
                                        "new_string": "const value = 2;\nconst label = String(value);",
                                    }
                                ),
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"file_path": "App.tsx"}),
                            },
                        }
                    ],
                ),
                LLMResponse(text="Done."),
            ]
        )

        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
                {"step_number": 4, "id": "step-4"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(
            side_effect=lambda *args, **kwargs: {"id": kwargs["tool_call_id"]}
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_file_tools(tmp_path),
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            result = await engine.run(run_id="run-edit-recovery", query="Fix App.tsx")

        assert result.success is True
        assert provider.complete_streaming.call_count == 4
        third_messages = provider.complete_streaming.call_args_list[2].kwargs["messages"]
        assert any(
            msg.get("role") == "system"
            and "Reread the relevant file region before retrying edit_file" in str(
                msg.get("content")
            )
            for msg in third_messages
        )
        assert any(
            msg.get("role") == "system" and "App.tsx" in str(msg.get("content"))
            for msg in third_messages
        )

    @pytest.mark.asyncio
    async def test_repeated_filtered_edit_retry_without_reread_does_not_force_synthesis(
        self, tmp_path: Path
    ):
        app_file = tmp_path / "App.tsx"
        app_file.write_text("const value = 2;\n", encoding="utf-8")

        failed_args = {
            "file_path": "App.tsx",
            "old_string": "const value = 1;",
            "new_string": "const value = 3;",
        }

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-edit-1",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": json.dumps(failed_args),
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-edit-2",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": json.dumps(failed_args),
                            },
                        }
                    ],
                ),
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-edit-3",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": json.dumps(failed_args),
                            },
                        }
                    ],
                ),
                LLMResponse(text="Done without forcing synthesis."),
            ]
        )

        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
                {"step_number": 4, "id": "step-4"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(
            side_effect=lambda *args, **kwargs: {"id": kwargs["tool_call_id"]}
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_file_tools(tmp_path),
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            result = await engine.run(run_id="run-edit-filter", query="Fix App.tsx")

        assert result.success is True
        assert result.final_answer == "Done without forcing synthesis."
        assert provider.complete_streaming.call_count == 4
        third_messages = provider.complete_streaming.call_args_list[2].kwargs["messages"]
        assert any(
            msg.get("role") == "user"
            and "Do not resend identical stale edit arguments" in str(msg.get("content"))
            for msg in third_messages
        )


class TestParallelToolExecution:
    """Tests for parallel read-only tool execution."""

    def test_parallel_tools_constant(self):
        """PARALLEL_TOOLS contains expected read-only tools."""
        assert "read_file" in AgentEngine.PARALLEL_TOOLS
        assert "grep" in AgentEngine.PARALLEL_TOOLS
        assert "glob" in AgentEngine.PARALLEL_TOOLS
        assert "list_directory" in AgentEngine.PARALLEL_TOOLS
        assert "web_search" in AgentEngine.PARALLEL_TOOLS
        assert "web_extract" in AgentEngine.PARALLEL_TOOLS
        assert "list_run_artifacts" in AgentEngine.PARALLEL_TOOLS
        assert "read_artifact" in AgentEngine.PARALLEL_TOOLS

    def test_mutating_tools_not_parallel(self):
        """Mutating tools are not in PARALLEL_TOOLS."""
        assert "write_file" not in AgentEngine.PARALLEL_TOOLS
        assert "edit_file" not in AgentEngine.PARALLEL_TOOLS
        assert "bash_tool" not in AgentEngine.PARALLEL_TOOLS
        assert "python_execute" not in AgentEngine.PARALLEL_TOOLS

    @pytest.mark.asyncio
    async def test_fast_parallel_tool_finalizes_before_slow_serial_tool(self):
        """Fast read-only calls should not look running behind a slow command."""

        class FakeTool:
            def __init__(self, name: str, delay: float, markers: list[str]) -> None:
                self.name = name
                self._delay = delay
                self._markers = markers
                self.schema = ToolSchema(
                    name=name,
                    description=f"Fake {name}",
                    parameters={"type": "object", "properties": {}},
                    permission_level="auto",
                )

            async def execute(self, **kwargs):
                del kwargs
                self._markers.append(f"{self.name}:execute_start")
                await asyncio.sleep(self._delay)
                self._markers.append(f"{self.name}:execute_done")
                return ToolResult(
                    success=True,
                    result_summary=f"{self.name} done",
                    result_data={"ok": True},
                )

        markers: list[str] = []
        tools = {
            "read_file": FakeTool("read_file", 0.01, markers),
            "exec_command": FakeTool("exec_command", 0.05, markers),
        }
        registry = create_mock_registry()
        registry.get.side_effect = lambda name: tools.get(name)
        state_machine = create_mock_state_machine()

        async def record_tool_call(**kwargs):
            return {"id": kwargs["tool_call_id"]}

        state_machine.record_tool_call = AsyncMock(side_effect=record_tool_call)
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )
        engine._add_trace_event = AsyncMock(return_value="trace-event")

        def on_event(event):
            if event.get("type") == "tool_result":
                markers.append(f"event:{event.get('tool_name')}")

        await engine._execute_tool_calls(
            tool_calls=[
                {
                    "id": "read-1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"file_path":"src/app.py"}',
                    },
                },
                {
                    "id": "exec-1",
                    "function": {
                        "name": "exec_command",
                        "arguments": '{"cmd":"pytest"}',
                    },
                },
            ],
            state_machine=state_machine,
            step_number=1,
            event_callback=on_event,
            run_id="run-1",
            step_metadata={},
        )

        assert markers.index("event:read_file") < markers.index("exec_command:execute_start")
        assert markers.index("event:exec_command") > markers.index("exec_command:execute_done")


class TestPermissionPolicies:
    """Tests for tool approval policy handling."""

    @pytest.mark.asyncio
    async def test_relaxed_bash_read_only_command_auto_approves(self, tmp_path):
        registry = create_mock_registry()
        registry.get.side_effect = lambda name: BashTool(str(tmp_path)) if name == "bash" else None

        approval_callback = AsyncMock(return_value=True)
        state_machine = create_mock_state_machine()
        state_machine.record_tool_call = AsyncMock(return_value={"id": "tc-1"})
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
            approval_callback=approval_callback,
            permission_policy="relaxed",
        )

        events = []
        prep = await engine._prepare_tool_call(
            ParsedToolCall(
                id="tc-1",
                name="bash",
                arguments={"command": "git status && rg permission_policy orchestrator"},
                raw_arguments='{"command":"git status && rg permission_policy orchestrator"}',
            ),
            state_machine=state_machine,
            step_number=1,
            event_callback=lambda event: events.append(event),
            run_id="run-1",
        )

        assert prep["tool"] is not None
        approval_callback.assert_not_called()
        assert not any(event["type"] == "tool_approval_required" for event in events)
        state_machine.record_approval.assert_awaited_with(
            tool_call_id="tc-1",
            decision="auto",
            policy="relaxed",
        )

    @pytest.mark.asyncio
    async def test_relaxed_bash_mutating_command_requires_approval(self, tmp_path):
        registry = create_mock_registry()
        registry.get.side_effect = lambda name: BashTool(str(tmp_path)) if name == "bash" else None

        approval_callback = AsyncMock(return_value=True)
        state_machine = create_mock_state_machine()
        state_machine.record_tool_call = AsyncMock(return_value={"id": "tc-2"})
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
            approval_callback=approval_callback,
            permission_policy="relaxed",
        )

        events = []
        await engine._prepare_tool_call(
            ParsedToolCall(
                id="tc-2",
                name="bash",
                arguments={"command": "mkdir -p src && touch src/new.py"},
                raw_arguments='{"command":"mkdir -p src && touch src/new.py"}',
            ),
            state_machine=state_machine,
            step_number=1,
            event_callback=lambda event: events.append(event),
            run_id="run-1",
        )

        approval_callback.assert_awaited_once()
        approval_events = [event for event in events if event["type"] == "tool_approval_required"]
        assert len(approval_events) == 1
        assert approval_events[0]["permission_level"] == "dangerous"


class TestAgentFactoryPermissionPolicy:
    """Tests that the factory forwards permission policy into the engine."""

    @pytest.mark.asyncio
    async def test_factory_passes_permission_policy(self, tmp_path):
        from orchestrator.agent.factory import create_agent_engine

        with patch("orchestrator.agent.factory.get_chat_config") as mock_config, patch(
            "orchestrator.agent.factory.get_profile"
        ) as mock_profile, patch(
            "orchestrator.agent.factory.get_context_strategy"
        ) as mock_strategy, patch(
            "orchestrator.agent.factory.get_db", AsyncMock(return_value=MagicMock())
        ), patch(
            "orchestrator.agent.factory.AgentRepo"
        ), patch(
            "orchestrator.agent.factory.TraceRepo"
        ), patch(
            "orchestrator.agent.factory.create_provider", return_value=MagicMock()
        ):
            mock_config.return_value = MagicMock(
                model=MagicMock(
                    name="accounts/fireworks/models/kimi-k2p6",
                    temperature=0.7,
                    max_tokens=32768,
                    reasoning_effort=None,
                ),
                context=MagicMock(max_tokens=100000),
                provider=MagicMock(slow_response_threshold=15.0),
                provider_chain=None,
                agent_planning=None,
                query_classification=MagicMock(enabled=False),
            )
            mock_profile.return_value = MagicMock(
                name="coding",
                context_strategy="coding",
                system_prompt_template="{date_context}\n{project_context}",
                max_plan_steps=5,
            )
            mock_strategy.return_value = MagicMock(gather=AsyncMock(return_value="project context"))

            engine = await create_agent_engine(
                filesystem_enabled=True,
                working_dir=str(tmp_path),
                permission_policy="relaxed",
            )

        assert engine._permission_policy == "relaxed"


# =============================================================================
# Force Prune Filesystem Tools Tests
# =============================================================================


class TestForcePruneFilesystemTools:
    """Tests for _force_prune_largest with filesystem tools."""

    def _make_engine(self):
        return AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

    def test_force_prune_read_file(self):
        """Force prune keeps head+tail for read_file."""
        engine = self._make_engine()
        content = "import os\n" + "X" * 2000
        messages = [
            {"role": "tool", "content": content, "name": "read_file", "_step": 1},
        ]
        result = engine._force_prune_largest(messages, {})
        assert "import os" in result[0]["content"]
        assert result[0]["_force_pruned"] is True

    def test_force_prune_grep(self):
        """Force prune keeps first matches for grep."""
        engine = self._make_engine()
        content = "match_line_1\nmatch_line_2\n" + "X" * 2000
        messages = [
            {"role": "tool", "content": content, "name": "grep", "_step": 1},
        ]
        result = engine._force_prune_largest(messages, {})
        assert "match_line_1" in result[0]["content"]
        assert result[0]["_force_pruned"] is True

    def test_force_prune_glob(self):
        """Force prune keeps first portion for glob."""
        engine = self._make_engine()
        content = "src/main.py\nsrc/util.py\n" + "X" * 2000
        messages = [
            {"role": "tool", "content": content, "name": "glob", "_step": 1},
        ]
        result = engine._force_prune_largest(messages, {})
        assert "src/main.py" in result[0]["content"]
        assert result[0]["_force_pruned"] is True

    def test_format_read_file_result_applies_budget(self):
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        long_line = "x" * 600
        content = "\n".join(f"{i}\t{long_line}" for i in range(500))
        result = ToolResult(success=True, result_summary="read ok", result_data=content)

        formatted = engine._format_tool_result(result, "read_file")

        assert len(formatted.splitlines()) <= 400
        assert formatted.splitlines()[0] == "[read ok]"
        assert all(len(line) <= 303 for line in formatted.splitlines() if line)

    def test_format_web_search_result_caps_results(self):
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        result = ToolResult(
            success=True,
            result_summary="search ok",
            result_data={
                "query": "test",
                "results": [
                    {"title": f"Title {i}", "url": f"https://example.com/{i}", "snippet": "s" * 500}
                    for i in range(20)
                ],
            },
        )

        formatted = json.loads(engine._format_tool_result(result, "web_search"))

        assert len(formatted["results"]) == 8
        assert all(len(item["snippet"]) <= 300 for item in formatted["results"])

    def test_format_command_result_includes_artifact_refs(self):
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )

        result = ToolResult(
            success=True,
            result_summary="command ok",
            result_data={
                "cmd": "pytest",
                "stdout": "passed",
                "artifacts": [
                    {
                        "artifact_type": "command_stdout",
                        "artifact_path": ".fluxion/runs/run-1/tool-calls/tc/stdout.txt",
                        "byte_count": 6,
                        "detail": "stdout for exec_command",
                    }
                ],
            },
        )

        formatted = json.loads(engine._format_tool_result(result, "exec_command"))

        assert formatted["artifacts"][0]["artifact_path"].endswith("stdout.txt")

    def test_compaction_replaces_old_history_with_summary_and_tail_user(self):
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=create_mock_registry(),
        )
        engine._tool_call_log = [
            {"tool_name": "read_file", "arguments": {"file_path": "orchestrator/app.py"}, "result_summary": "Read app.py", "step_number": 1}
        ]
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Please inspect the backend"},
            {"role": "assistant", "content": "Inspecting now"},
            {"role": "user", "content": "Continue with the current task"},
        ]

        compacted = engine._compact_conversation(messages, step_number=2)

        assert compacted[0]["role"] == "system"
        assert compacted[1]["role"] == "system"
        assert compacted[1]["content"].startswith(engine.COMPACTION_PREFIX)
        assert "Read app.py" in compacted[1]["content"]
        assert compacted[-1]["content"] == "Continue with the current task"
        assert engine._compaction_count == 1
        assert engine._last_compacted_at_step == 2


class TestCodingContinuationBehavior:
    """Tests for coding-profile continuation behavior without intent routing."""

    def _coding_profile(self):
        from orchestrator.agent.profile import get_profile

        return get_profile("coding")

    def _registry_with_tools(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        return registry

    @pytest.mark.asyncio
    async def test_praise_in_coding_workspace_does_not_force_tools(self):
        provider = create_mock_provider(response_text="Glad you like it.")
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_tools(),
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            result = await engine.run(
                run_id="run-praise",
                query="woah love these changes cool stuff",
            )

        assert result.success is True
        call_kwargs = provider.complete_streaming.call_args.kwargs
        assert call_kwargs["tool_choice"] is None
        assert call_kwargs["tools"] is not None
        system_content = call_kwargs["messages"][0]["content"]
        assert "Latest user intent" not in system_content
        assert "Tool guidance" not in system_content

    @pytest.mark.asyncio
    async def test_coding_run_first_step_does_not_force_tool_choice(self):
        provider = create_mock_provider(response_text="Hi — ready when you are.")
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_tools(),
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            await engine.run(run_id="run-chat", query="say hi")

        assert provider.complete_streaming.call_args.kwargs["tool_choice"] is None

    @pytest.mark.asyncio
    async def test_repeated_length_only_reasoning_fails_without_forced_synthesis(self):
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(text="", reasoning="thinking only", finish_reason="length"),
                LLMResponse(text="", reasoning="still thinking", finish_reason="length"),
            ]
        )
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_tools(),
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            result = await engine.run(run_id="run-length", query="fix the UI")

        assert result.success is False
        assert "length-truncated reasoning" in (result.error_message or "")
        assert provider.complete_streaming.call_count == 2

    @pytest.mark.asyncio
    async def test_regression_praise_after_changes_stays_conversational(self):
        prior_runs = [
            {
                "created_at": "2026-04-29T13:53:22Z",
                "user_message": "is there any part of UI you'd improve today?",
                "final_answer": "I found a few UI improvements worth making.",
                "turn_summary": (
                    "Outcome: I identified UI spacing and component polish opportunities. "
                    "| Tools: read_file, grep | Files: ui/src/App.tsx "
                    "| User asked: is there any part of UI you'd improve today?"
                ),
            },
            {
                "created_at": "2026-04-29T13:55:03Z",
                "user_message": "Right use shadcn component in that case",
                "final_answer": "Implemented the UI polish and verified the build.",
                "turn_summary": (
                    "Outcome: Implemented the UI polish and verified the build. "
                    "| Tools: read_file, edit_file, bash | Files: ui/src/App.tsx "
                    "| User asked: Right use shadcn component in that case"
                ),
            },
        ]
        provider = create_mock_provider(response_text="Glad you like the changes.")
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            repo = create_mock_repo()
            repo.get_coding_session_state.return_value = {
                "conversation_id": "conv-1",
                "state": CodingSessionState(
                    objective="Use shadcn components",
                    modified_files=["ui/src/App.tsx"],
                    file_evidence={
                        "ui/src/App.tsx": CodingFileState(
                            path="ui/src/App.tsx",
                            summary="Updated spacing and button components.",
                        )
                    },
                ).to_dict(),
                "updated_at": "2026-04-29T13:55:03Z",
            }
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=self._registry_with_tools(),
                trace_repo=create_mock_trace_repo(prior_runs=prior_runs),
                profile=self._coding_profile(),
                planning_enabled=True,
            )
            with patch.object(engine, "_execute_tool_calls", AsyncMock()) as execute_tools:
                result = await engine.run(
                    run_id="run-regression",
                    query="woah love these changes cool stuff",
                    conversation_id="conv-1",
                )

        assert result.success is True
        assert "Glad" in result.final_answer
        assert execute_tools.await_count == 0
        assert provider.complete_streaming.call_count == 1
        assert provider.complete_streaming.call_args.kwargs["tool_choice"] is None
        repo.upsert_coding_session_state.assert_awaited()

    @pytest.mark.asyncio
    async def test_coding_agent_handles_ambiguous_follow_up_without_planner(self):
        provider = create_mock_provider(response_text="Can you clarify what you want changed?")
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_tools(),
                profile=self._coding_profile(),
                planning_enabled=True,
            )
            result = await engine.run(run_id="run-ambiguous", query="that part feels weird")

        assert result.success is True
        assert result.final_answer == "Can you clarify what you want changed?"

    def test_canonical_replay_tool_calls_serializes_parsed_args(self):
        registry = create_mock_registry()
        list_directory_tool = MagicMock()
        list_directory_tool.schema.parameters = {"required": []}
        registry.get.return_value = list_directory_tool
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        replay, recovery_notes = engine._canonical_replay_tool_calls(
            [
                (
                    ParsedToolCall(
                        id="tc-1",
                        name="list_directory",
                        arguments={"path": "src", "recursive": False},
                        raw_arguments='{"recursive":false,"path":"src"}',
                    ),
                    ToolResult(success=True, result_summary="ok"),
                )
            ]
        )

        assert recovery_notes == []
        assert replay == [
            {
                "id": "tc-1",
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "arguments": '{"path":"src","recursive":false}',
                },
            }
        ]

    def test_malformed_tool_call_replay_is_dropped_and_recovery_noted(self):
        registry = create_mock_registry()
        edit_tool = MagicMock()
        edit_tool.schema.parameters = {
            "required": ["file_path", "old_string", "new_string"]
        }
        registry.get.return_value = edit_tool
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )
        memory = WorkingMemory(objective="Fix UI")

        replay, recovery_notes = engine._canonical_replay_tool_calls(
            [
                (
                    ParsedToolCall(
                        id="tc-bad",
                        name="edit_file",
                        arguments={},
                        raw_arguments='{"file_path"',
                    ),
                    ToolResult(
                        success=False,
                        result_summary="Missing required args: 'file_path', 'old_string', 'new_string'",
                    ),
                )
            ]
        )
        engine._record_tool_call_recovery(memory, recovery_notes)

        assert replay == []
        assert len(recovery_notes) == 1
        assert "invalid" in recovery_notes[0]
        assert any("edit_file" in item for item in memory.unresolved_tasks)

    @pytest.mark.asyncio
    async def test_invalid_edit_file_call_does_not_poison_next_provider_payload(self):
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="Applying the change.",
                    tool_calls=[
                        {
                            "id": "tc-bad",
                            "type": "function",
                            "function": {
                                "name": "edit_file",
                                "arguments": '{"file_path"',
                            },
                        }
                    ],
                ),
                LLMResponse(text="I need valid edit arguments before changing that file."),
                LLMResponse(text="I need valid edit arguments before changing that file."),
            ]
        )
        repo = create_mock_repo()
        registry = create_mock_registry()
        edit_tool = MagicMock()
        edit_tool.schema.parameters = {
            "required": ["file_path", "old_string", "new_string"]
        }
        registry.get.side_effect = lambda name: edit_tool if name == "edit_file" else None
        registry.get_openai_schemas.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Edit a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"},
                        },
                        "required": ["file_path", "old_string", "new_string"],
                    },
                },
            }
        ]
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-bad"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            result = await engine.run(run_id="run-invalid", query="fix the broken UI")

        assert result.success is False
        assert "repeated text-only updates" in (result.error_message or "")
        second_messages = provider.complete_streaming.call_args_list[1].kwargs["messages"]
        assistant_with_tool_calls = [
            msg
            for msg in second_messages
            if msg.get("role") == "assistant" and msg.get("tool_calls")
        ]
        assert assistant_with_tool_calls == []
        assert any(
            msg.get("role") == "system"
            and "malformed" in str(msg.get("content"))
            for msg in second_messages
        )
        assert any(
            msg.get("role") == "user"
            and "Retry the intended tool call now." in str(msg.get("content"))
            for msg in second_messages
        )

    @pytest.mark.asyncio
    async def test_malformed_tool_call_retries_instead_of_executing_empty_args(self):
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-bad",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": '{"file_path"',
                            },
                        }
                    ],
                    finish_reason="length",
                ),
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-good",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps(
                                    {
                                        "file_path": "src/WeeklyHistory.tsx",
                                        "content": "export const x = 1;\n",
                                    }
                                ),
                            },
                        }
                    ],
                    finish_reason="tool_calls",
                ),
                LLMResponse(text="Done.", finish_reason="stop"),
            ]
        )
        repo = create_mock_repo()
        registry = create_mock_registry()
        write_tool = MagicMock()
        write_tool.schema.parameters = {"required": ["file_path", "content"]}
        write_tool.schema.permission_level = "auto"
        write_tool.execute = AsyncMock(
            return_value=ToolResult(success=True, result_summary="Wrote file")
        )
        registry.get.side_effect = lambda name: write_tool if name == "write_file" else None
        registry.get_openai_schemas.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["file_path", "content"],
                    },
                },
            }
        ]
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(
            side_effect=[
                {"id": "tc-good"},
            ]
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            result = await engine.run(run_id="run-retry", query="make the edits")

        assert result.success is True
        write_tool.execute.assert_awaited_once_with(
            file_path="src/WeeklyHistory.tsx",
            content="export const x = 1;\n",
        )
        first_retry_messages = provider.complete_streaming.call_args_list[1].kwargs["messages"]
        assert any(
            msg.get("role") == "user"
            and "Retry the intended tool call now." in str(msg.get("content"))
            for msg in first_retry_messages
        )

    @pytest.mark.asyncio
    async def test_regression_followup_has_no_intent_bucket_in_working_memory(self):
        prior_runs = [
            {
                "created_at": "2026-04-29T13:55:03Z",
                "user_message": "Right use shadcn component in that case",
                "final_answer": "Implemented the UI polish and verified the build.",
                "turn_summary": (
                    "Outcome: Implemented the UI polish and verified the build. "
                    "| Tools: read_file, edit_file, bash | Files: ui/src/App.tsx "
                    "| User asked: Right use shadcn component in that case"
                ),
            },
        ]
        provider = create_mock_provider(response_text="Glad you like the changes.")
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=create_mock_repo(),
                registry=self._registry_with_tools(),
                trace_repo=create_mock_trace_repo(prior_runs=prior_runs),
                profile=self._coding_profile(),
                planning_enabled=False,
            )
            await engine.run(
                run_id="run-regression-memory",
                query="woah love these changes cool stuff",
                conversation_id="01a36ca9-390e-4c0e-a0da-0d6c470dde47",
            )

        system_content = provider.complete_streaming.call_args.kwargs["messages"][0]["content"]
        assert "Latest user intent" not in system_content
        assert "Tool guidance" not in system_content

    @pytest.mark.asyncio
    async def test_text_with_api_tool_call_emits_assistant_update(self):
        """Assistant text accompanying API tool calls is shown as progress, not final."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="I'll search for this.",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "test"}',
                            },
                        }
                    ],
                ),
                LLMResponse(text="Final answer.", tool_calls=None),
            ]
        )
        web_tool = MagicMock()
        web_tool.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Found 5 results",
                result_data={"results": []},
                duration_ms=1,
            )
        )
        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}}
        ]
        registry.get.return_value = web_tool
        registry.is_idempotent.return_value = True
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-1"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(provider=provider, repo=create_mock_repo(), registry=registry)
            events = []
            result = await engine.run(
                run_id="run-assistant-update",
                query="Test query",
                event_callback=lambda event: events.append(event),
            )

        assert result.success is True
        web_tool.execute.assert_awaited_once_with(query="test")
        updates = [event for event in events if event["type"] == "assistant_update"]
        answers = [event for event in events if event["type"] == "answer_token"]
        assert updates == [
            {
                "type": "assistant_update",
                "run_id": "run-assistant-update",
                "step_number": 1,
                "content": "I'll search for this.",
            }
        ]
        assert "I'll search for this." not in "".join(event["content"] for event in answers)

    @pytest.mark.asyncio
    async def test_progress_update_continues_without_forcing_web_search(self):
        """Progress-only response is shown as update, then agent continues normally."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="Cross-checking evidence on what speeds VO2max gains.",
                    tool_calls=None,
                    reasoning="I should use web_search before answering.",
                ),
                LLMResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "tc-web",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "VO2max training evidence"}',
                            },
                        }
                    ],
                ),
                LLMResponse(text="Final evidence-backed answer.", tool_calls=None),
            ]
        )
        web_tool = MagicMock()
        web_tool.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Found 10 results",
                result_data={"results": []},
                duration_ms=1,
            )
        )
        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}}
        ]
        registry.get.return_value = web_tool
        registry.is_idempotent.return_value = True
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
                {"step_number": 3, "id": "step-3"},
            ],
        )
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-web"})

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(provider=provider, repo=create_mock_repo(), registry=registry)
            events = []
            result = await engine.run(
                run_id="run-forced-web",
                query="research on how to improve VO2max faster",
                event_callback=lambda event: events.append(event),
            )

        assert result.success is True
        assert provider.complete_streaming.await_args_list[0].kwargs["tool_choice"] is None
        assert provider.complete_streaming.await_args_list[1].kwargs["tool_choice"] is None
        second_call_messages = provider.complete_streaming.await_args_list[1].kwargs["messages"]
        second_call_text = "\n".join(str(message.get("content", "")) for message in second_call_messages)
        assert "Cross-checking evidence on what speeds VO2max gains." in second_call_text
        assert "Continue the run" not in second_call_text
        assert "required evidence is still missing" not in second_call_text
        web_tool.execute.assert_awaited_once_with(query="VO2max training evidence")
        decisions = [call.kwargs.get("decision") for call in mock_sm.complete_step.await_args_list]
        assert "completion_gate_continue" in decisions
        assert "call_tool" in decisions
        updates = [event for event in events if event["type"] == "assistant_update"]
        assert len(updates) == 1
        assert updates[0]["content"] == "Cross-checking evidence on what speeds VO2max gains."

    @pytest.mark.asyncio
    async def test_repeated_progress_updates_stall_without_web_nudge(self):
        """Repeated progress-only responses fail clearly without web-specific nudging."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="I'll search the evidence.",
                    tool_calls=None,
                    reasoning="I should use web_search.",
                ),
                LLMResponse(
                    text="I'll search the evidence.",
                    tool_calls=None,
                    reasoning="I should use web_search.",
                ),
            ]
        )
        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}}
        ]
        registry.get.return_value = None
        registry.is_idempotent.return_value = True
        mock_sm = create_mock_state_machine(
            can_continue_sequence=[True, True, False],
            step_sequence=[
                {"step_number": 1, "id": "step-1"},
                {"step_number": 2, "id": "step-2"},
            ],
        )

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(provider=provider, repo=create_mock_repo(), registry=registry)
            result = await engine.run(
                run_id="run-forced-web-fail",
                query="research current VO2max evidence",
        )

        assert result.success is False
        assert "repeated text-only updates" in (result.error_message or "")
        assert provider.complete_streaming.await_count == 2
        decisions = [call.kwargs.get("decision") for call in mock_sm.complete_step.await_args_list]
        assert decisions.count("completion_gate_continue") == 1
        assert "completion_gate_stalled" in decisions

    @pytest.mark.asyncio
    async def test_today_logging_task_does_not_trigger_web_recovery(self):
        """Words like today do not force web-search recovery for no-tool final text."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(
                text="Logged today's sleep and HRV.",
                tool_calls=None,
            )
        )
        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}}
        ]
        registry.get.return_value = None
        registry.is_idempotent.return_value = True
        mock_sm = create_mock_state_machine()

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(provider=provider, repo=create_mock_repo(), registry=registry)
            result = await engine.run(
                run_id="run-today-log",
                query="today’s log 23:10 - 5:50 - 6h",
            )

        assert result.success is True
        assert result.final_answer == "Logged today's sleep and HRV."
        assert provider.complete_streaming.await_count == 1
        assert provider.complete_streaming.await_args.kwargs["tool_choice"] is None
        decisions = [call.kwargs.get("decision") for call in mock_sm.complete_step.await_args_list]
        assert "synthesize" in decisions

    def test_completion_gate_blocks_coding_final_before_mutation_evidence(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "edit_file"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
            profile=self._coding_profile(),
        )

        gate = engine._evaluate_completion_gate(
            query="fix the broken button",
            llm_response=LLMResponse(text="I found the issue and will fix it."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=WorkingMemory(objective="fix the broken button"),
        )

        assert gate.action == "show_update_and_continue"
        assert gate.evidence_missing == [
            "workspace_inspection",
            "workspace_mutation",
        ]

    def test_completion_gate_accepts_coding_final_after_mutation_evidence(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "edit_file"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
            profile=self._coding_profile(),
        )
        memory = WorkingMemory(objective="fix the broken button")
        memory.files_inspected["ui/Button.tsx"] = "Read button component."
        memory.files_changed["ui/Button.tsx"] = "Updated click handler."
        engine._tool_call_log = [
            {"tool_name": "edit_file", "success": True, "arguments": {}},
        ]

        gate = engine._evaluate_completion_gate(
            query="fix the broken button",
            llm_response=LLMResponse(text="Fixed the button."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=memory,
        )

        assert gate.action == "accept_final"
        assert gate.evidence_missing == []

    def test_completion_gate_blocks_research_final_before_web_evidence(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        gate = engine._evaluate_completion_gate(
            query="research what speeds VO2max gains",
            llm_response=LLMResponse(text="VO2max improves with intervals."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=WorkingMemory(objective="research VO2max"),
        )

        assert gate.action == "show_update_and_continue"
        assert gate.evidence_missing == ["web_evidence"]

    def test_completion_gate_does_not_treat_word_slash_word_as_workspace_path(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "grep"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
            profile=self._coding_profile(),
        )

        gate = engine._evaluate_completion_gate(
            query="Bangalore/Bengaluru? which is right",
            llm_response=LLMResponse(text="Use Bengaluru for formal India resumes."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=WorkingMemory(objective="location naming"),
        )

        assert gate.action == "accept_final"
        assert gate.evidence_missing == []

    def test_completion_gate_still_detects_real_workspace_path_references(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "grep"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
            profile=self._coding_profile(),
        )

        gate = engine._evaluate_completion_gate(
            query="explain Health/Phase-7.5-Plan.md",
            llm_response=LLMResponse(text="That file describes the current training phase."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=WorkingMemory(objective="explain plan file"),
        )

        assert gate.action == "show_update_and_continue"
        assert gate.evidence_missing == ["workspace_inspection"]

    def test_completion_gate_does_not_treat_negated_test_it_as_command(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "exec_command"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        gate = engine._evaluate_completion_gate(
            query='might i have this? "DEC2 (BHLHE41 gene)" just curious tho, didn’t test it but is it possible?',
            llm_response=LLMResponse(text="It is possible, but you would need a genotype to know."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=WorkingMemory(objective="answer genetics question"),
        )

        assert gate.action == "accept_final"
        assert gate.evidence_missing == []

    def test_completion_gate_still_treats_test_it_as_command(self):
        registry = create_mock_registry()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "exec_command"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        gate = engine._evaluate_completion_gate(
            query="the fix is ready, test it",
            llm_response=LLMResponse(text="I'll test it now."),
            tool_calls=None,
            tool_schemas=registry.get_openai_schemas.return_value,
            working_memory=WorkingMemory(objective="test fix"),
        )

        assert gate.action == "show_update_and_continue"
        assert gate.evidence_missing == ["command_execution"]

    def test_available_tool_schemas_do_not_add_final_answer_tool(self):
        """The agent does not advertise a synthetic final_answer finish tool."""
        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "web_search"}},
        ]
        engine = AgentEngine(
            provider=create_mock_provider(),
            repo=create_mock_repo(),
            registry=registry,
        )

        tool_names = {
            schema.get("function", {}).get("name")
            for schema in engine._available_tool_schemas()
        }
        assert "final_answer" not in tool_names
