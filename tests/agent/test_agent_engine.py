"""Tests for AgentEngine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from orchestrator.agent.agent_engine import (
    AgentEngine,
    AgentResult,
    ParsedToolCall,
)
from orchestrator.agent.tools.bash_tool import BashTool
from orchestrator.agent.tools.base import ToolResult
from orchestrator.agent.state_machine import RecoveryContext
from orchestrator.providers.base import LLMResponse
from orchestrator.schemas import AgentStepState


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
    return repo


def create_mock_registry():
    """Create a mock ToolRegistry."""
    registry = MagicMock()
    registry.get_openai_schemas.return_value = []
    registry.get.return_value = None
    registry.is_idempotent.return_value = True
    return registry


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
        assert parsed[0].arguments == {}  # Falls back to empty dict

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


# =============================================================================
# AgentEngine Run Tests
# =============================================================================


class TestAgentEngineRun:
    """Tests for AgentEngine.run() method."""

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
        citations = await engine._extract_and_store_citations("run-1", answer)

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
        citations = await engine._extract_and_store_citations("run-1", answer)

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

        result = await engine._force_synthesis(
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

        result = await engine._force_synthesis(
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
            {"tool_name": "web_search", "arguments": {"query": "Tokyo population"}, "success": True, "step_number": 1},
        ]

        calls = [ParsedToolCall(id="tc-2", name="web_search", arguments={"query": "Tokyo population"}, raw_arguments='{"query": "Tokyo population"}')]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert "Duplicate" in redundant[0][1]

    def test_allows_different_arguments(self):
        """Does not flag calls with different arguments."""
        engine = self._make_engine()
        engine._tool_call_log = [
            {"tool_name": "web_search", "arguments": {"query": "Tokyo population"}, "success": True, "step_number": 1},
        ]

        calls = [ParsedToolCall(id="tc-2", name="web_search", arguments={"query": "Paris population"}, raw_arguments='{"query": "Paris population"}')]
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
            {"tool_name": "list_directory", "arguments": {"path": "."}, "success": True, "step_number": 1},
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
            {"tool_name": "web_search", "arguments": {"query": "test"}, "success": True, "step_number": 1},
        ]

        calls = [
            ParsedToolCall(id="tc-a", name="web_search", arguments={"query": "test"}, raw_arguments='{"query": "test"}'),
            ParsedToolCall(id="tc-b", name="web_search", arguments={"query": "new query"}, raw_arguments='{"query": "new query"}'),
        ]
        redundant = engine._detect_redundant_calls(calls)

        assert len(redundant) == 1
        assert redundant[0][0].id == "tc-a"


# =============================================================================
# Synthesis Nudging Tests
# =============================================================================


# =============================================================================
# Parallel Tool Execution Tests
# =============================================================================


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

    def test_mutating_tools_not_parallel(self):
        """Mutating tools are not in PARALLEL_TOOLS."""
        assert "write_file" not in AgentEngine.PARALLEL_TOOLS
        assert "edit_file" not in AgentEngine.PARALLEL_TOOLS
        assert "bash_tool" not in AgentEngine.PARALLEL_TOOLS
        assert "python_execute" not in AgentEngine.PARALLEL_TOOLS


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
