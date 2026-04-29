"""Integration tests for AgentEngine.

These tests verify the agent can answer real-world questions using mocked tools.
The exit criteria for Phase 5 is: "Agent answers 'What is the population of Tokyo?'"
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.agent.agent_engine import AgentEngine, AgentResult
from orchestrator.agent.tools.base import ToolResult
from orchestrator.agent.state_machine import RecoveryContext
from orchestrator.providers.base import LLMResponse
from orchestrator.schemas import AgentStepState


class TestAgentIntegrationTokyoPopulation:
    """Exit criteria test: Agent answers 'What is the population of Tokyo?'"""

    @pytest.mark.asyncio
    async def test_tokyo_population_with_search(self):
        """Agent searches the web and synthesizes an answer about Tokyo's population.

        This is the EXIT CRITERIA for Phase 5.
        """
        # Track LLM call count for multi-step behavior
        call_count = 0

        async def mock_llm_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: Agent decides to search
                return LLMResponse(
                    text="<think>I need to search for Tokyo's population.</think>",
                    tool_calls=[
                        {
                            "id": "tc-search-1",
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "Tokyo population 2024"}',
                            },
                        }
                    ],
                )
            else:
                # Second call: Agent synthesizes answer
                return LLMResponse(
                    text=(
                        "Based on my research, Tokyo's population is approximately "
                        "14 million in the metropolitan area, making it one of the "
                        "most populous cities in the world. The greater Tokyo area "
                        "has around 37-38 million people. [1]"
                    ),
                    tool_calls=None,
                )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_llm_streaming)

        # Mock web_search tool
        mock_search = MagicMock()
        mock_search.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Found 5 results for 'Tokyo population 2024'",
                result_data={
                    "query": "Tokyo population 2024",
                    "results": [
                        {
                            "url": "https://example.com/tokyo-stats",
                            "title": "Tokyo Population Statistics 2024",
                            "snippet": (
                                "Tokyo has a population of approximately 14 million "
                                "in the city proper and 37.4 million in the greater "
                                "metropolitan area as of 2024."
                            ),
                        },
                        {
                            "url": "https://example.com/japan-cities",
                            "title": "Japan's Largest Cities",
                            "snippet": (
                                "Tokyo remains Japan's largest city with over 14 million "
                                "residents in the central 23 wards."
                            ),
                        },
                    ],
                },
                duration_ms=250,
            )
        )

        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ]
        registry.get.return_value = mock_search
        registry.is_idempotent.return_value = True

        # Mock repo
        repo = MagicMock()
        repo.create_citation = AsyncMock()
        repo.get_citations_for_run = AsyncMock(
            return_value=[
                {
                    "id": "cit-1",
                    "source_url": "https://example.com/tokyo-stats",
                    "title": "Tokyo Population Statistics 2024",
                    "snippet": "Tokyo has a population of approximately 14 million...",
                },
            ]
        )
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        # Mock state machine
        step_count = 0

        def can_continue():
            return step_count < 2

        def start_step():
            nonlocal step_count
            step_count += 1
            return {"step_number": step_count, "id": f"step-{step_count}"}

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )
        )
        mock_sm.can_continue.side_effect = lambda: can_continue()
        mock_sm.start_step = AsyncMock(side_effect=start_step)
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-search-1"})
        mock_sm.start_tool_execution = AsyncMock()
        mock_sm.complete_tool_call = AsyncMock()
        mock_sm.record_approval = AsyncMock()
        mock_sm.current_step = 1
        mock_sm.steps_remaining = 9

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
                max_steps=10,
            )

            events = []
            result = await engine.run(
                run_id="test-tokyo-population",
                query="What is the population of Tokyo?",
                event_callback=lambda e: events.append(e),
            )

        # ========== ASSERTIONS (EXIT CRITERIA) ==========

        # 1. Agent succeeded
        assert result.success is True, f"Agent failed: {result.error_message}"

        # 2. Answer contains population information
        assert result.final_answer is not None
        assert "14 million" in result.final_answer.lower() or "14" in result.final_answer

        # 3. Agent used the search tool
        mock_search.execute.assert_called_once()
        call_args = mock_search.execute.call_args
        assert "Tokyo" in str(call_args) or "population" in str(call_args).lower()

        # 4. Correct events were emitted
        event_types = [e["type"] for e in events]
        assert "agent_started" in event_types
        assert "step_started" in event_types
        assert "tool_start" in event_types
        assert "tool_result" in event_types
        assert "synthesizing" in event_types
        assert "agent_complete" in event_types

        # 5. Tool result was successful
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is True

        # 6. Agent completed in expected number of steps
        assert result.total_steps == 2  # Search + Synthesize

    @pytest.mark.asyncio
    async def test_tokyo_population_direct_answer(self):
        """Agent can answer directly if it already knows (no tools needed)."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(
                text=(
                    "Tokyo's population is approximately 14 million people "
                    "in the city proper, making it one of the world's largest "
                    "metropolitan areas. The greater Tokyo area has around "
                    "37-38 million residents."
                ),
                tool_calls=None,
            )
        )

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )
        )
        mock_sm.can_continue.side_effect = [True, False]
        mock_sm.start_step = AsyncMock(return_value={"step_number": 1, "id": "step-1"})
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.current_step = 1
        mock_sm.steps_remaining = 9

        repo = MagicMock()
        repo.get_citations_for_run = AsyncMock(return_value=[])
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        registry = MagicMock()
        registry.get_openai_schemas.return_value = []

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
            )

            result = await engine.run(
                run_id="test-tokyo-direct",
                query="What is the population of Tokyo?",
            )

        assert result.success is True
        assert "14 million" in result.final_answer.lower()
        assert result.total_steps == 1


class TestAgentIntegrationMultiStep:
    """Tests for multi-step agent behavior."""

    @pytest.mark.asyncio
    async def test_search_then_extract(self):
        """Agent searches, then extracts content from a URL."""
        call_count = 0

        async def mock_llm_streaming(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First: search
                return LLMResponse(
                    text="I'll search for this information.",
                    tool_calls=[
                        {
                            "id": "tc-1",
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "test query"}',
                            },
                        }
                    ],
                )
            elif call_count == 2:
                # Second: extract
                return LLMResponse(
                    text="Let me get more details.",
                    tool_calls=[
                        {
                            "id": "tc-2",
                            "function": {
                                "name": "web_extract",
                                "arguments": '{"urls": ["https://example.com/page"]}',
                            },
                        }
                    ],
                )
            else:
                # Third: synthesize
                return LLMResponse(
                    text="Based on my research, here is the answer.",
                    tool_calls=None,
                )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_llm_streaming)

        # Mock search tool
        mock_search = MagicMock()
        mock_search.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Found results",
                result_data={"results": [{"url": "https://example.com/page"}]},
                duration_ms=100,
            )
        )

        # Mock extract tool
        mock_extract = MagicMock()
        mock_extract.execute = AsyncMock(
            return_value=ToolResult(
                success=True,
                result_summary="Extracted content",
                result_data={"url": "https://example.com/page", "content": "..."},
                duration_ms=200,
            )
        )

        def get_tool(name):
            if name == "web_search":
                return mock_search
            elif name == "web_extract":
                return mock_extract
            return None

        registry = MagicMock()
        registry.get_openai_schemas.return_value = []
        registry.get.side_effect = get_tool
        registry.is_idempotent.return_value = True

        repo = MagicMock()
        repo.create_citation = AsyncMock()
        repo.get_citations_for_run = AsyncMock(return_value=[])
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        # Mock state machine for 3 steps
        step_count = 0
        tool_call_count = 0

        def can_continue():
            return step_count < 3

        def start_step():
            nonlocal step_count
            step_count += 1
            return {"step_number": step_count, "id": f"step-{step_count}"}

        def record_tool(**kwargs):
            nonlocal tool_call_count
            tool_call_count += 1
            # Return same ID as tool_call_id to indicate new call
            return {"id": kwargs.get("tool_call_id", f"tc-{tool_call_count}")}

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )
        )
        mock_sm.can_continue.side_effect = lambda: can_continue()
        mock_sm.start_step = AsyncMock(side_effect=start_step)
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.record_tool_call = AsyncMock(side_effect=record_tool)
        mock_sm.start_tool_execution = AsyncMock()
        mock_sm.complete_tool_call = AsyncMock()
        mock_sm.record_approval = AsyncMock()
        mock_sm.current_step = 1
        mock_sm.steps_remaining = 9

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
                run_id="test-multi-step",
                query="Multi-step query",
                event_callback=lambda e: events.append(e),
            )

        assert result.success is True
        assert result.total_steps == 3

        # Both tools were called
        mock_search.execute.assert_called_once()
        mock_extract.execute.assert_called_once()

        # Two tool_result events
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 2


class TestAgentIntegrationRecovery:
    """Tests for crash recovery scenarios."""

    @pytest.mark.asyncio
    async def test_recovers_with_hint_injection(self):
        """Agent recovers from crash with hint injection."""
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(
                text="I'll regenerate the code based on the hint.",
                tool_calls=None,
            )
        )

        # Recovery context with hints
        recovery_hint = {
            "role": "system",
            "content": "IMPORTANT: The previous python_execute was interrupted.",
            "_recovery_hint": True,
        }

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=True,
                interrupted_tool_calls=[{"id": "tc-1", "tool_name": "python_execute"}],
                hints=[recovery_hint],
                last_completed_step=1,
            )
        )
        mock_sm.can_continue.side_effect = [True, False]
        mock_sm.start_step = AsyncMock(return_value={"step_number": 2, "id": "step-2"})
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.current_step = 2
        mock_sm.steps_remaining = 8

        repo = MagicMock()
        repo.get_citations_for_run = AsyncMock(return_value=[])
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        registry = MagicMock()
        registry.get_openai_schemas.return_value = []

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
            )

            result = await engine.run(
                run_id="test-recovery",
                query="Continue from where we left off",
            )

        assert result.success is True

        # Verify LLM was called with recovery hint injected
        call_args = provider.complete_streaming.call_args
        messages = call_args[1]["messages"]

        # Find the recovery hint in messages
        hint_found = any(
            msg.get("_recovery_hint") is True or "interrupted" in msg.get("content", "")
            for msg in messages
        )
        assert hint_found, "Recovery hint was not injected into messages"


class TestAgentIntegrationErrors:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_handles_all_tools_failing(self):
        """Agent handles gracefully when all tool calls fail."""
        call_count = 0

        async def mock_llm_streaming(*args, **kwargs):
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
                                "arguments": "{}",
                            },
                        }
                    ],
                )
            else:
                return LLMResponse(
                    text="I couldn't find information, but here's what I know.",
                    tool_calls=None,
                )

        provider = MagicMock()
        provider.complete_streaming = AsyncMock(side_effect=mock_llm_streaming)

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value=ToolResult(
                success=False,
                result_summary="API error",
                error_message="Rate limited",
                duration_ms=50,
            )
        )

        registry = MagicMock()
        registry.get_openai_schemas.return_value = []
        registry.get.return_value = mock_tool
        registry.is_idempotent.return_value = True

        repo = MagicMock()
        repo.create_citation = AsyncMock()
        repo.get_citations_for_run = AsyncMock(return_value=[])
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        step_count = 0

        def start_step():
            nonlocal step_count
            step_count += 1
            return {"step_number": step_count, "id": f"step-{step_count}"}

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )
        )
        mock_sm.can_continue.side_effect = lambda: step_count < 2
        mock_sm.start_step = AsyncMock(side_effect=start_step)
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-1"})
        mock_sm.start_tool_execution = AsyncMock()
        mock_sm.complete_tool_call = AsyncMock()
        mock_sm.record_approval = AsyncMock()
        mock_sm.current_step = 1
        mock_sm.steps_remaining = 9

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
                run_id="test-tool-fail",
                query="Test query",
                event_callback=lambda e: events.append(e),
            )

        # Agent should still succeed - it handles the tool failure gracefully
        assert result.success is True

        # Tool result shows failure
        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["success"] is False


class TestAgentIntegrationCodingContinuation:
    """Integration regressions for coding continuation behavior."""

    @pytest.mark.asyncio
    async def test_praise_followup_answers_directly_without_forced_write_tool(self):
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
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            return_value=LLMResponse(text="Glad you like the changes.")
        )

        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {"type": "function", "function": {"name": "write_file"}}
        ]
        registry.get.return_value = None
        registry.is_idempotent.return_value = True

        repo = MagicMock()
        repo.create_citation = AsyncMock()
        repo.get_citations_for_run = AsyncMock(return_value=[])
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        trace_repo = MagicMock()
        trace_repo.list_runs_for_conversation = AsyncMock(return_value=prior_runs)
        trace_repo.update_run = AsyncMock()

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )
        )
        mock_sm.can_continue.side_effect = [True, False]
        mock_sm.start_step = AsyncMock(return_value={"step_number": 1, "id": "step-1"})
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.current_step = 1
        mock_sm.steps_remaining = 9

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            from orchestrator.agent.profile import get_profile

            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
                trace_repo=trace_repo,
                profile=get_profile("coding"),
                planning_enabled=False,
            )
            result = await engine.run(
                run_id="test-praise-followup",
                query="woah love these changes cool stuff",
                conversation_id="conv-praise",
            )

        assert result.success is True
        assert "Glad you like the changes." == result.final_answer
        call_kwargs = provider.complete_streaming.call_args.kwargs
        assert call_kwargs["tool_choice"] is None
        assert call_kwargs["tools"] is not None

    @pytest.mark.asyncio
    async def test_invalid_tool_call_does_not_corrupt_next_request(self):
        provider = MagicMock()
        provider.complete_streaming = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="Let me inspect the UI files first.",
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
                LLMResponse(
                    text="I spotted a few improvement ideas, but I need a valid edit request to change files.",
                    tool_calls=None,
                ),
            ]
        )

        edit_tool = MagicMock()
        edit_tool.schema.parameters = {
            "required": ["file_path", "old_string", "new_string"]
        }

        registry = MagicMock()
        registry.get_openai_schemas.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
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
        registry.get.side_effect = lambda name: edit_tool if name == "edit_file" else None
        registry.is_idempotent.return_value = True

        repo = MagicMock()
        repo.create_citation = AsyncMock()
        repo.get_citations_for_run = AsyncMock(return_value=[])
        repo.mark_citations_used = AsyncMock()
        repo.create_run_artifact = AsyncMock()

        step_count = 0

        def start_step():
            nonlocal step_count
            step_count += 1
            return {"step_number": step_count, "id": f"step-{step_count}"}

        mock_sm = MagicMock()
        mock_sm.initialize = AsyncMock(
            return_value=RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )
        )
        mock_sm.can_continue.side_effect = lambda: step_count < 2
        mock_sm.start_step = AsyncMock(side_effect=start_step)
        mock_sm.transition_to = AsyncMock()
        mock_sm.complete_step = AsyncMock()
        mock_sm.complete_run = AsyncMock()
        mock_sm.record_tool_call = AsyncMock(return_value={"id": "tc-bad"})
        mock_sm.start_tool_execution = AsyncMock()
        mock_sm.complete_tool_call = AsyncMock()
        mock_sm.record_approval = AsyncMock()
        mock_sm.current_step = 1
        mock_sm.steps_remaining = 9

        with patch(
            "orchestrator.agent.agent_engine.AgentStateMachine",
            return_value=mock_sm,
        ):
            from orchestrator.agent.profile import get_profile

            engine = AgentEngine(
                provider=provider,
                repo=repo,
                registry=registry,
                profile=get_profile("coding"),
                planning_enabled=False,
            )
            result = await engine.run(
                run_id="test-invalid-tool-replay",
                query="is there any part of UI you'd improve to make it cleaner?",
            )

        assert result.success is True
        second_messages = provider.complete_streaming.call_args_list[1].kwargs["messages"]
        assert not any(
            msg.get("role") == "assistant" and msg.get("tool_calls")
            for msg in second_messages
        )
        assert any(
            msg.get("role") == "system"
            and "Previous tool call was invalid and failed." in str(msg.get("content"))
            for msg in second_messages
        )
