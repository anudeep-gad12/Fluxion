"""Agent engine for web research execution.

This module provides:
- AgentEngine: Main orchestration class for running agent queries
- Streaming SSE event emission
- Tool call parsing and execution
- Crash recovery support
"""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from orchestrator.logging_config import get_logger
from orchestrator.schemas import AgentStepState
from orchestrator.agent.state_machine import (
    AgentStateMachine,
    MaxStepsExceededError,
    RecoveryContext,
)
from orchestrator.agent.context_pruner import ContextPruner
from orchestrator.agent.recovery import (
    build_recovery_messages,
    create_idempotency_key,
)
from orchestrator.utils.sanitize import sanitize_harmony_tokens

if TYPE_CHECKING:
    from orchestrator.providers.base import LLMProvider, LLMResponse
    from orchestrator.storage.repositories.agent_repo import AgentRepo
    from orchestrator.storage.repositories.trace_repo import TraceRepo
    from orchestrator.agent.tools.registry import ToolRegistry
    from orchestrator.agent.tools.base import ToolResult

logger = get_logger(__name__)


# =============================================================================
# System Prompt Helpers
# =============================================================================


def get_system_prompt_for_query_type(query_type: "QueryType") -> str:
    """Get appropriate system prompt based on query classification.

    Args:
        query_type: Classification result from QueryClassifier.

    Returns:
        System prompt string for the given query type.
    """
    from orchestrator.agent.query_classifier import QueryType

    if query_type == QueryType.CALCULATION:
        return AgentEngine.CALCULATION_SYSTEM_PROMPT
    return AgentEngine.DEFAULT_SYSTEM_PROMPT


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class AgentResult:
    """Final result from agent execution.

    Attributes:
        run_id: The run ID.
        success: Whether execution succeeded.
        final_answer: The synthesized answer (if successful).
        citations: List of citations used in the answer.
        total_steps: Number of steps taken.
        error_message: Error message if failed.
        timing_ms: Total execution time in milliseconds.
    """

    run_id: str
    success: bool
    final_answer: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    error_message: Optional[str] = None
    timing_ms: int = 0


@dataclass
class ParsedToolCall:
    """Parsed tool call from LLM response.

    Attributes:
        id: Tool call ID from LLM.
        name: Tool name.
        arguments: Parsed arguments dict.
        raw_arguments: Original JSON string (for hashing).
    """

    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str


# =============================================================================
# SSE Event Types
# =============================================================================

# Event types for UI streaming:
# - "agent_started": Agent run initiated
# - "step_started": New step begun
# - "thinking": Model reasoning content (streamed)
# - "tool_start": Tool execution starting
# - "tool_result": Tool execution completed
# - "synthesizing": Synthesis phase started
# - "answer_token": Final answer token (streamed)
# - "agent_complete": Agent run finished
# - "agent_error": Error occurred


# =============================================================================
# Agent Engine
# =============================================================================


class AgentEngine:
    """Orchestrates agent execution with tool calling.

    The engine:
    1. Initializes state machine (handles recovery)
    2. Runs the agent loop:
       a. Prune context to manage token limits
       b. Call LLM with tool schemas
       c. Parse response for tool calls or synthesis
       d. Execute tools and record results
       e. Loop until synthesis or max steps
    3. Returns final answer with citations

    Example:
        engine = AgentEngine(
            provider=provider_chain,
            repo=agent_repo,
            registry=tool_registry,
        )

        result = await engine.run(
            run_id="run-123",
            query="What is the population of Tokyo?",
            event_callback=emit_sse,
        )
    """

    # Default system prompt for agent (date context added dynamically in _build_messages)
    DEFAULT_SYSTEM_PROMPT = """You are a research assistant that uses tools to search the web and analyze information.

{date_context}

Available tools:
- web_search: Search the web for information
- web_extract: Extract detailed content from URLs
- python_execute: Run Python code for calculations and data analysis

TOOL SELECTION:
- For calculations/math/physics: Use python_execute (not web_search)
- For current events, facts, or data after your knowledge cutoff: Use web_search
- For questions within your knowledge cutoff that don't need fresh data: Answer directly
- For detailed content from specific URLs: Use web_extract after web_search

WEB SEARCH GUIDELINES:
- Use web_search when you need information after June 2024 or real-time data
- If search results are unhelpful, try different search terms
- Include the current year in searches for recent information

WEB EXTRACT GUIDELINES:
- Extract 2-3 most relevant URLs from search results (not more unless necessary)
- Prefer: academic sources, official data, authoritative sites
- Avoid extracting if the search snippet already answers the question
- Skip: Wikipedia overviews, forums, paywalled content

CITATION FORMAT:
- Use [1], [2], etc. INLINE within your answer text where you reference information
- Do NOT add a separate "Citations" or "Sources" section at the end
- The UI will automatically display a formatted sources list

To provide your final answer, respond WITHOUT calling any tools."""

    # Calculation-focused system prompt for physics/math queries
    CALCULATION_SYSTEM_PROMPT = """You are a research assistant specializing in physics and mathematical calculations.

{date_context}

Available tools:
- python_execute: Run Python code for calculations (USE THIS for any physics/math computation)
- web_search: Search the web for reference data or constants
- web_extract: Extract detailed content from URLs

CRITICAL INSTRUCTIONS FOR CALCULATIONS:
1. For ANY physics or mathematical calculation, you MUST use python_execute
2. NEVER compute physics formulas mentally or in text - always use Python code
3. Even "simple" physics calculations (like kinetic energy, velocity, etc.) MUST use python_execute
4. Use Python for: unit conversions, formula evaluation, numerical computation
5. Only answer directly for trivial arithmetic like "2+2" or "5*3"

CALCULATION WORKFLOW:
1. Identify the physics/math problem and relevant formula
2. Use python_execute to compute the result with proper units
3. If you need reference data (constants, material properties), use web_search first
4. Present the final answer with the computation result

WEB EXTRACT GUIDELINES (if needed):
- Extract 2-3 most relevant URLs (not more unless necessary)
- Prefer: academic sources, official data, authoritative sites
- Skip: Wikipedia overviews, forums, paywalled content

NEVER answer with mental math like "KE = 0.5 * 5 * 100 = 250 J" - always use python_execute.

CITATION FORMAT (if referencing sources):
- Use [1], [2], etc. INLINE within your answer text
- Do NOT add a separate "Citations" or "Sources" section at the end
- The UI will automatically display a formatted sources list

To provide your final answer, respond WITHOUT calling any tools."""

    # Maximum characters for tool result content (prevents context blowout)
    MAX_TOOL_RESULT_CHARS: int = 50000

    def __init__(
        self,
        provider: "LLMProvider",
        repo: "AgentRepo",
        registry: "ToolRegistry",
        trace_repo: Optional["TraceRepo"] = None,
        model_name: str = "qwen3-32b",
        max_steps: int = 10,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        keep_full_steps: int = 2,
        tool_choice: Optional[str] = None,
        max_context_tokens: int = 100000,
        slow_response_threshold: float = 15.0,
    ) -> None:
        """Initialize agent engine.

        Args:
            provider: LLM provider (can be ProviderChain for failover).
            repo: AgentRepo for persistence.
            registry: ToolRegistry with registered tools.
            trace_repo: Optional TraceRepo for trace events (Debug Trace panel).
            model_name: Model to use for LLM calls.
            max_steps: Maximum steps before forcing synthesis.
            max_tokens: Max tokens for LLM response.
            temperature: Sampling temperature.
            system_prompt: Custom system prompt (or use default).
            keep_full_steps: Number of recent steps to keep detailed.
            tool_choice: Override tool selection behavior on first step.
                - None: Use default "auto"
                - "python_execute": Force python_execute on first step
                - "required": Force model to use some tool
            max_context_tokens: Maximum tokens for input context (default 100k).
                Used to enforce context budget before LLM calls.
            slow_response_threshold: Seconds before emitting slow_response warning.
        """
        self._provider = provider
        self._repo = repo
        self._registry = registry
        self._trace_repo = trace_repo
        self._model_name = model_name
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self._pruner = ContextPruner(keep_full_steps=keep_full_steps)
        self._tool_choice = tool_choice
        self._max_context_tokens = max_context_tokens
        self._slow_response_threshold = slow_response_threshold

    async def run(
        self,
        run_id: str,
        query: str,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        conversation_id: Optional[str] = None,
    ) -> AgentResult:
        """Execute agent loop for a query.

        Args:
            run_id: Unique run ID.
            query: User's research query.
            event_callback: Callback for SSE events.
            conversation_id: Optional conversation context.

        Returns:
            AgentResult with answer and citations.
        """
        start_time = time.perf_counter()

        # Emit start event
        self._emit(event_callback, "agent_started", run_id=run_id, query=query)

        # Trace: agent_start
        await self._add_trace_event(
            run_id=run_id,
            event_type="agent_start",
            content={"query": query[:500], "max_steps": self._max_steps},
            actor="system",
        )

        # Initialize state machine
        state_machine = AgentStateMachine(
            run_id=run_id,
            repo=self._repo,
            tool_registry=self._registry,
            max_steps=self._max_steps,
        )

        try:
            recovery_context = await state_machine.initialize()

            # Build initial messages (includes conversation history if available)
            messages = await self._build_initial_messages(query, conversation_id)

            # Handle recovery if needed
            if recovery_context.needs_recovery:
                messages = build_recovery_messages(recovery_context, messages)
                logger.info(
                    "Agent recovering from crash",
                    extra={
                        "run_id": run_id,
                        "last_step": recovery_context.last_completed_step,
                        "hints": len(recovery_context.hints),
                    },
                )

            # Step metadata for context pruning (maps tool_call_id -> step_number)
            step_metadata: Dict[str, int] = {}

            # Main agent loop
            while state_machine.can_continue():
                step = await state_machine.start_step()
                step_number = step["step_number"]

                self._emit(
                    event_callback,
                    "step_started",
                    run_id=run_id,
                    step_number=step_number,
                    steps_remaining=state_machine.steps_remaining,
                )

                # Trace: step_start
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="step_start",
                    content={
                        "step_number": step_number,
                        "steps_remaining": state_machine.steps_remaining,
                    },
                    step_number=step_number,
                )

                # Prune context before LLM call
                pruned_messages = self._pruner.prune(
                    messages,
                    current_step=step_number,
                    step_metadata=step_metadata,
                )

                # Enforce context budget - force prune if still over limit
                estimated_tokens = self._pruner.estimate_tokens(pruned_messages)
                prune_iterations = 0
                max_prune_iterations = 20  # Safety limit to prevent infinite loop

                while estimated_tokens > self._max_context_tokens and prune_iterations < max_prune_iterations:
                    prune_iterations += 1
                    logger.warning(
                        "Context exceeds budget, force pruning",
                        extra={
                            "estimated_tokens": estimated_tokens,
                            "max_context_tokens": self._max_context_tokens,
                            "iteration": prune_iterations,
                            "step": step_number,
                        },
                    )
                    pruned_messages = self._force_prune_largest(pruned_messages, step_metadata)
                    estimated_tokens = self._pruner.estimate_tokens(pruned_messages)

                if prune_iterations > 0:
                    logger.info(
                        "Context budget enforced",
                        extra={
                            "prune_iterations": prune_iterations,
                            "final_estimated_tokens": estimated_tokens,
                            "messages_count": len(pruned_messages),
                        },
                    )

                # Call LLM with tools
                tool_schemas = self._registry.get_openai_schemas()

                # Trace: llm_request
                llm_request_event_id = await self._add_trace_event(
                    run_id=run_id,
                    event_type="llm_request",
                    content={
                        "model": self._model_name,
                        "messages_count": len(pruned_messages),
                        "tools_count": len(tool_schemas) if tool_schemas else 0,
                    },
                    event_status="pending",
                    step_number=step_number,
                )

                llm_start_time = time.perf_counter()
                try:
                    # Use tool_choice only on first step (if configured)
                    step_tool_choice = self._tool_choice if step_number == 1 else None
                    llm_response = await self._call_llm_with_tools(
                        messages=pruned_messages,
                        event_callback=event_callback,
                        run_id=run_id,
                        tool_choice=step_tool_choice,
                    )
                except Exception as e:
                    logger.error("LLM call failed", extra={"error": str(e)})
                    await state_machine.error_step(str(e))
                    await state_machine.error_run(str(e))
                    return AgentResult(
                        run_id=run_id,
                        success=False,
                        error_message=str(e),
                        total_steps=step_number,
                        timing_ms=int((time.perf_counter() - start_time) * 1000),
                    )

                # Extract thinking: Harmony format <think> tags OR native reasoning
                thinking_text = self._extract_thinking(llm_response.text)
                if not thinking_text and llm_response.reasoning:
                    # Use native reasoning content if no <think> tags found
                    thinking_text = llm_response.reasoning

                # Check for tool calls - try API response first, then text fallback
                tool_calls = llm_response.tool_calls
                logger.debug(
                    "LLM response received",
                    extra={
                        "api_tool_calls": len(tool_calls) if tool_calls else 0,
                        "text_length": len(llm_response.text) if llm_response.text else 0,
                        "text_preview": (llm_response.text[:200] if llm_response.text else "")[:200],
                    },
                )
                if not tool_calls:
                    # Fallback: parse tool calls from text (Harmony format)
                    text_tool_calls = self._parse_text_tool_calls(llm_response.text)
                    if text_tool_calls:
                        tool_calls = text_tool_calls
                        logger.info(
                            "Parsed tool calls from text",
                            extra={"count": len(text_tool_calls), "tools": [tc["function"]["name"] for tc in text_tool_calls]},
                        )
                    # Also try parsing from reasoning if text is empty
                    # (Some models output tool calls in reasoning_content field)
                    elif not llm_response.text and llm_response.reasoning:
                        reasoning_tool_calls = self._parse_json_tool_calls(llm_response.reasoning)
                        if reasoning_tool_calls:
                            tool_calls = reasoning_tool_calls
                            logger.info(
                                "Parsed tool calls from reasoning",
                                extra={"count": len(reasoning_tool_calls), "tools": [tc["function"]["name"] for tc in reasoning_tool_calls]},
                            )
                        else:
                            logger.debug("No tool calls found in reasoning", extra={"reasoning_preview": llm_response.reasoning[:300] if llm_response.reasoning else ""})
                    else:
                        logger.debug("No tool calls found in text", extra={"text": llm_response.text[:300] if llm_response.text else ""})

                # Trace: llm_response (with thinking)
                llm_duration_ms = int((time.perf_counter() - llm_start_time) * 1000)
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="llm_response",
                    content={
                        "text_length": len(llm_response.text) if llm_response.text else 0,
                        "has_tool_calls": bool(tool_calls),
                        "tool_calls_count": len(tool_calls) if tool_calls else 0,
                        "thinking_text": thinking_text,
                    },
                    actor="model",
                    step_number=step_number,
                    duration_ms=llm_duration_ms,
                    parent_event_id=llm_request_event_id,
                )

                if tool_calls:
                    # Tool calling step
                    await state_machine.transition_to(AgentStepState.TOOL_CALLING)

                    # Parse and execute tools
                    tool_results = await self._execute_tool_calls(
                        tool_calls=tool_calls,
                        state_machine=state_machine,
                        step_number=step_number,
                        event_callback=event_callback,
                        run_id=run_id,
                        step_metadata=step_metadata,
                    )

                    # Add assistant message with tool calls
                    # Include truncated reasoning for context so model doesn't re-analyze
                    # each step. Limit to ~500 chars to avoid 400 errors with some providers.
                    assistant_content = llm_response.text
                    if not assistant_content and llm_response.reasoning:
                        # Use last portion of reasoning (most relevant to decision)
                        reasoning = llm_response.reasoning.strip()
                        if len(reasoning) > 500:
                            # Take last 500 chars to preserve the conclusion/decision
                            assistant_content = "..." + reasoning[-500:]
                        else:
                            assistant_content = reasoning
                    messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_content or None,
                            "tool_calls": tool_calls,
                        }
                    )

                    # Add tool results as tool messages
                    for tool_call, result in tool_results:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.name,
                                "content": self._format_tool_result(result),
                                "_step": step_number,
                            }
                        )
                        step_metadata[tool_call.id] = step_number

                    await state_machine.complete_step(
                        decision="call_tool",
                        thinking_text=thinking_text,
                    )

                else:
                    # Synthesis step - no tool calls means final answer
                    await state_machine.transition_to(AgentStepState.SYNTHESIZING)

                    self._emit(
                        event_callback,
                        "synthesizing",
                        run_id=run_id,
                        step_number=step_number,
                    )

                    # Trace: synthesis
                    await self._add_trace_event(
                        run_id=run_id,
                        event_type="synthesis",
                        content={"step_number": step_number},
                        step_number=step_number,
                    )

                    final_answer = self._clean_answer(llm_response.text)

                    # Fallback: If text is empty but reasoning exists, extract answer from it
                    # (Some models put the answer in reasoning_content instead of content)
                    if not final_answer and llm_response.reasoning:
                        # Strip any incomplete JSON fragments from reasoning
                        reasoning_text = llm_response.reasoning
                        # Remove trailing JSON fragments (incomplete tool calls)
                        reasoning_text = re.sub(r'\{[^{}]*$', '', reasoning_text)  # Trailing unclosed {
                        reasoning_text = re.sub(r'\{"[^"]*":\s*"[^}]*$', '', reasoning_text)  # Partial JSON
                        reasoning_text = reasoning_text.strip()
                        if reasoning_text:
                            final_answer = self._clean_answer(reasoning_text)
                            logger.info(
                                "Used reasoning as fallback answer",
                                extra={"answer_length": len(final_answer)},
                            )

                    # Emit answer as answer_token so UI displays it in answer panel
                    # (streaming sent it to thinking, now send cleaned version to answer)
                    if final_answer:
                        self._emit(
                            event_callback,
                            "answer_token",
                            run_id=run_id,
                            content=final_answer,
                        )

                    # Extract and store citations
                    citations = await self._extract_and_store_citations(
                        run_id=run_id,
                        answer=final_answer,
                    )

                    await state_machine.complete_step(
                        decision="synthesize",
                        thinking_text=thinking_text,
                    )
                    await state_machine.complete_run(final_answer)

                    # Trace: agent_complete
                    total_timing_ms = int((time.perf_counter() - start_time) * 1000)

                    self._emit(
                        event_callback,
                        "agent_complete",
                        run_id=run_id,
                        success=True,
                        final_answer=final_answer,
                        citations=citations,
                        total_steps=step_number,
                        timing_ms=total_timing_ms,
                    )
                    await self._add_trace_event(
                        run_id=run_id,
                        event_type="agent_complete",
                        content={
                            "success": True,
                            "total_steps": step_number,
                            "answer_length": len(final_answer) if final_answer else 0,
                            "citations_count": len(citations),
                        },
                        duration_ms=total_timing_ms,
                    )

                    return AgentResult(
                        run_id=run_id,
                        success=True,
                        final_answer=final_answer,
                        citations=citations,
                        total_steps=step_number,
                        timing_ms=total_timing_ms,
                    )

            # Max steps reached - force synthesis
            final_answer = await self._force_synthesis(
                messages=messages,
                event_callback=event_callback,
                run_id=run_id,
            )

            citations = await self._extract_and_store_citations(
                run_id=run_id,
                answer=final_answer,
            )

            await state_machine.complete_run(final_answer)

            # Trace: agent_complete (max steps)
            total_timing_ms = int((time.perf_counter() - start_time) * 1000)

            self._emit(
                event_callback,
                "agent_complete",
                run_id=run_id,
                success=True,
                final_answer=final_answer,
                citations=citations,
                total_steps=state_machine.current_step,
                timing_ms=total_timing_ms,
            )
            await self._add_trace_event(
                run_id=run_id,
                event_type="agent_complete",
                content={
                    "success": True,
                    "total_steps": state_machine.current_step,
                    "answer_length": len(final_answer) if final_answer else 0,
                    "citations_count": len(citations),
                    "forced_synthesis": True,
                },
                duration_ms=total_timing_ms,
            )

            return AgentResult(
                run_id=run_id,
                success=True,
                final_answer=final_answer,
                citations=citations,
                total_steps=state_machine.current_step,
                timing_ms=total_timing_ms,
            )

        except MaxStepsExceededError:
            # Should not happen due to can_continue() check, but handle anyway
            await state_machine.error_run("Max steps exceeded")
            return AgentResult(
                run_id=run_id,
                success=False,
                error_message="Max steps exceeded",
                total_steps=state_machine.current_step,
                timing_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            logger.error(
                "Agent run failed",
                extra={"run_id": run_id, "error": str(e)},
                exc_info=True,
            )
            try:
                await state_machine.error_run(str(e))
            except Exception:
                pass

            self._emit(
                event_callback,
                "agent_error",
                run_id=run_id,
                error=str(e),
            )

            # Trace: agent_error
            total_timing_ms = int((time.perf_counter() - start_time) * 1000)
            await self._add_trace_event(
                run_id=run_id,
                event_type="agent_error",
                content={
                    "error_message": str(e),
                    "total_steps": state_machine.current_step,
                },
                event_status="error",
                duration_ms=total_timing_ms,
            )

            return AgentResult(
                run_id=run_id,
                success=False,
                error_message=str(e),
                total_steps=state_machine.current_step,
                timing_ms=total_timing_ms,
            )

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _emit(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]],
        event_type: str,
        **kwargs: Any,
    ) -> None:
        """Emit SSE event via callback.

        Args:
            callback: Event callback function.
            event_type: Event type string.
            **kwargs: Event payload.
        """
        if callback:
            callback({"type": event_type, **kwargs})

    async def _add_trace_event(
        self,
        run_id: str,
        event_type: str,
        content: dict,
        actor: str = "system",
        event_status: str = "success",
        step_number: Optional[int] = None,
        duration_ms: Optional[int] = None,
        parent_event_id: Optional[str] = None,
    ) -> Optional[str]:
        """Write trace event if trace_repo is configured.

        Args:
            run_id: Run ID to associate with.
            event_type: Type of event (agent_start, step_start, llm_request, etc).
            content: Event payload dict.
            actor: Who created event (system, model, tool:<name>).
            event_status: Status (pending, success, error).
            step_number: Agent step number.
            duration_ms: Operation duration.
            parent_event_id: Parent event for linking.

        Returns:
            Event ID if written, None if trace_repo not configured.
        """
        if not self._trace_repo:
            return None
        try:
            return await self._trace_repo.add_trace_event(
                run_id=run_id,
                event_type=event_type,
                content=content,
                actor=actor,
                event_status=event_status,
                step_number=step_number,
                duration_ms=duration_ms,
                parent_event_id=parent_event_id,
            )
        except Exception as e:
            logger.warning("Failed to write trace event", extra={"error": str(e)})
            return None

    async def _build_initial_messages(
        self,
        query: str,
        conversation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build initial message list with system prompt, history, and query.

        Args:
            query: User's research query.
            conversation_id: Optional conversation ID to load history from.

        Returns:
            Message list with system, history, and user messages.
        """
        # Inject date context into system prompt
        today = date.today()
        date_context = (
            f"Current date: {today.strftime('%B %d, %Y')}\n"
            f"Your knowledge cutoff: June 2024. For information after this date, use web_search."
        )
        system_prompt = self._system_prompt.format(date_context=date_context)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Load conversation history if conversation_id provided
        if conversation_id and self._trace_repo:
            prior_runs = await self._trace_repo.list_runs_for_conversation(
                conversation_id
            )
            # Sort by created_at ascending (oldest first)
            sorted_runs = sorted(prior_runs, key=lambda r: r.get("created_at", ""))

            # Limit to last N runs to prevent context overflow
            max_history = 10
            if len(sorted_runs) > max_history:
                sorted_runs = sorted_runs[-max_history:]

            for run in sorted_runs:
                user_msg = run.get("user_message")
                assistant_msg = run.get("final_answer")
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if assistant_msg:
                    messages.append({"role": "assistant", "content": assistant_msg})

        # Add current query
        messages.append({"role": "user", "content": query})
        return messages

    async def _call_llm_with_tools(
        self,
        messages: List[Dict[str, Any]],
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
        tool_choice: Optional[str] = None,
    ) -> "LLMResponse":
        """Call LLM with tool schemas via streaming.

        Args:
            messages: Message list.
            event_callback: SSE callback.
            run_id: Run ID for events.
            tool_choice: Tool selection override (auto, required, or tool_name).

        Returns:
            LLMResponse with text and tool_calls.
        """
        tool_schemas = self._registry.get_openai_schemas()
        first_token_received = asyncio.Event()
        llm_complete = asyncio.Event()

        def sanitize_token(token: str) -> str:
            """Strip protocol tokens from thinking content.

            Removes Harmony format tokens and tool-call protocol markers that
            should not be displayed to users.
            """
            # Remove <|...|> style tokens (opening Harmony format)
            cleaned = re.sub(r'<\|[^|]*\|>', '', token)
            # Remove </...|> style tokens (closing variants)
            cleaned = re.sub(r'</[^|]*\|>', '', cleaned)
            # Remove channel/constraint annotations like "commentary to=web_search"
            cleaned = re.sub(r'\b(commentary|analysis|final)\s+to=\w+', '', cleaned, flags=re.IGNORECASE)
            # Remove standalone channel identifiers
            cleaned = re.sub(r'\b(commentary|analysis|final)\b', '', cleaned, flags=re.IGNORECASE)
            # Remove constraint markers before JSON (e.g., "json{" -> "{")
            cleaned = re.sub(r'\b(json|xml)\b(?=\s*[\{\[])', '', cleaned, flags=re.IGNORECASE)
            # Remove raw JSON tool calls that leak through
            cleaned = re.sub(r'\{"query":[^}]+\}', '', cleaned)
            return cleaned

        def on_token(token: str) -> None:
            """Handle content tokens.

            For gpt-oss models with native reasoning, content tokens are the
            actual answer (not thinking). Don't emit to thinking - the answer
            will be emitted as answer_token at synthesis.

            This keeps thinking panel clean for actual reasoning content only.
            """
            # Signal that we've received a token (response is flowing)
            first_token_received.set()
            # Don't emit content tokens to thinking - they're the answer
            # The full answer will be emitted as answer_token at synthesis
            pass

        def on_reasoning(reasoning: str) -> None:
            """Handle native reasoning tokens - emit to thinking panel."""
            # Signal that we've received a token (response is flowing)
            first_token_received.set()
            cleaned = sanitize_token(reasoning)
            if cleaned and cleaned.strip():
                self._emit(event_callback, "thinking", run_id=run_id, content=cleaned)

        async def slow_response_monitor() -> None:
            """Monitor LLM call and emit slow_response events if taking too long."""
            start_time = time.perf_counter()
            threshold = self._slow_response_threshold
            warning_emitted = False

            while not llm_complete.is_set():
                elapsed = time.perf_counter() - start_time
                # Only emit warning if we haven't received any tokens yet
                if elapsed >= threshold and not first_token_received.is_set() and not warning_emitted:
                    self._emit(
                        event_callback,
                        "slow_response",
                        run_id=run_id,
                        message="Taking longer than usual...",
                        elapsed_seconds=round(elapsed, 1),
                    )
                    warning_emitted = True
                    logger.info(
                        "Slow LLM response detected",
                        extra={
                            "run_id": run_id,
                            "elapsed_seconds": round(elapsed, 1),
                            "threshold": threshold,
                        },
                    )
                # Check every second
                try:
                    await asyncio.wait_for(llm_complete.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

        # Start the slow response monitor
        monitor_task = asyncio.create_task(slow_response_monitor())

        try:
            response = await self._provider.complete_streaming(
                messages=messages,
                model=self._model_name,
                on_token=on_token,
                on_reasoning=on_reasoning,
                tools=tool_schemas if tool_schemas else None,
                tool_choice=tool_choice,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        finally:
            # Signal completion and clean up monitor
            llm_complete.set()
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

        return response

    def _parse_text_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse tool calls from text using official Harmony parser.

        Uses the openai-harmony library to properly parse gpt-oss Harmony format
        output instead of fragile regex patterns.

        Args:
            text: Response text that may contain Harmony format tool calls.

        Returns:
            List of tool call dicts in OpenAI format, or None if no tool calls found.
        """
        from orchestrator.utils.harmony_parser import parse_harmony_tool_calls

        return parse_harmony_tool_calls(text)

    def _parse_json_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse raw JSON tool calls from text (fallback for malformed output).

        Some models output tool calls as raw JSON in reasoning_content instead
        of as structured tool_calls. This extracts them as a fallback.

        Supported formats:
        - {"query": "..."} -> web_search
        - {"code": "..."} -> python_execute
        - {"url": "..."} or {"urls": [...]} -> web_extract

        Args:
            text: Text that may contain JSON tool call objects.

        Returns:
            List of tool call dicts in OpenAI format, or None if no tool calls found.
        """
        import json
        import re
        import uuid

        if not text:
            return None

        tool_calls = []

        # Find JSON objects in the text
        # Look for patterns like {"query": "...", "max_results": 10}
        json_pattern = r'\{[^{}]*"(?:query|code|url|urls)"[^{}]*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)

        for match in matches:
            try:
                obj = json.loads(match)
                tool_name = None
                arguments = {}

                if "query" in obj:
                    tool_name = "web_search"
                    arguments = {"query": obj["query"]}
                    if "max_results" in obj:
                        arguments["max_results"] = obj["max_results"]
                elif "code" in obj:
                    tool_name = "python_execute"
                    arguments = {"code": obj["code"]}
                elif "urls" in obj:
                    tool_name = "web_extract"
                    arguments = {"urls": obj["urls"]}
                elif "url" in obj:
                    tool_name = "web_extract"
                    arguments = {"urls": [obj["url"]]}

                if tool_name:
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(arguments),
                        },
                    })
                    logger.debug(
                        "Extracted JSON tool call from reasoning",
                        extra={"tool_name": tool_name, "match": match[:100]},
                    )
            except json.JSONDecodeError:
                continue

        return tool_calls if tool_calls else None

    def _parse_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> List[ParsedToolCall]:
        """Parse tool calls from LLM response.

        Args:
            tool_calls: Raw tool calls from LLM response.

        Returns:
            List of ParsedToolCall objects.
        """
        import uuid

        parsed = []
        for tc in tool_calls:
            try:
                tc_id = tc.get("id", str(uuid.uuid4()))
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")

                # Parse JSON arguments
                try:
                    arguments = json.loads(args_str)
                except json.JSONDecodeError:
                    arguments = {}

                parsed.append(
                    ParsedToolCall(
                        id=tc_id,
                        name=name,
                        arguments=arguments,
                        raw_arguments=args_str,
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse tool call", extra={"error": str(e)})
                continue

        return parsed

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        state_machine: AgentStateMachine,
        step_number: int,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
        step_metadata: Dict[str, int],
    ) -> List[tuple["ParsedToolCall", "ToolResult"]]:
        """Execute tool calls.

        Args:
            tool_calls: List of tool call dicts in OpenAI format.
            state_machine: State machine for recording.
            step_number: Current step number.
            event_callback: SSE callback.
            run_id: Run ID.
            step_metadata: Metadata dict to update.

        Returns:
            List of (ParsedToolCall, ToolResult) tuples.
        """
        from orchestrator.agent.tools.base import ToolResult

        results: List[tuple[ParsedToolCall, ToolResult]] = []

        parsed_calls = self._parse_tool_calls(tool_calls)

        for tool_call in parsed_calls:
            # Create idempotency key
            args_hash = hashlib.md5(tool_call.raw_arguments.encode()).hexdigest()[:8]
            idempotency_key = create_idempotency_key(
                run_id, step_number, tool_call.name, args_hash
            )

            # Record tool call in state machine
            tc_record = await state_machine.record_tool_call(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                idempotency_key=idempotency_key,
            )

            # Check if this was a duplicate (idempotent retry)
            if tc_record.get("id") != tool_call.id:
                # Only use cached result if it was successful
                # Don't cache failures - re-execute to get fresh result
                if tc_record.get("status") == "success":
                    logger.debug(
                        "Using cached tool result", extra={"key": idempotency_key}
                    )
                    cached_result = ToolResult(
                        success=True,
                        result_summary=tc_record.get("result_summary", ""),
                        error_message=None,
                    )
                    results.append((tool_call, cached_result))
                    continue
                else:
                    logger.debug(
                        "Ignoring cached failure, re-executing tool",
                        extra={"key": idempotency_key, "status": tc_record.get("status")},
                    )
                    # Fall through to execute tool below

            # Emit tool start event
            self._emit(
                event_callback,
                "tool_start",
                run_id=run_id,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
            )

            # Trace: tool_call
            tool_call_event_id = await self._add_trace_event(
                run_id=run_id,
                event_type="tool_call",
                content={
                    "tool_name": tool_call.name,
                    "arguments": tool_call.arguments,
                    "tool_call_id": tool_call.id,
                },
                actor=f"tool:{tool_call.name}",
                event_status="pending",
                step_number=step_number,
            )

            # Mark as running
            await state_machine.start_tool_execution(tc_record["id"])

            # Get and execute tool
            tool = self._registry.get(tool_call.name)
            if tool is None:
                result = ToolResult(
                    success=False,
                    result_summary=f"Unknown tool: {tool_call.name}",
                    error_message=f"Tool '{tool_call.name}' not found",
                    duration_ms=0,
                )
            else:
                try:
                    result = await tool.execute(**tool_call.arguments)
                except Exception as e:
                    logger.error(
                        "Tool execution failed",
                        extra={
                            "tool": tool_call.name,
                            "error": str(e),
                        },
                    )
                    result = ToolResult(
                        success=False,
                        result_summary=f"Tool error: {str(e)[:100]}",
                        error_message=str(e),
                        duration_ms=0,
                    )

            # Record completion
            await state_machine.complete_tool_call(
                tool_call_id=tc_record["id"],
                success=result.success,
                result_summary=result.result_summary,
                duration_ms=result.duration_ms or 0,
                error_message=result.error_message,
            )

            # Extract citations from search/extract results
            if result.success and tool_call.name in ("web_search", "web_extract"):
                await self._store_citations_from_tool(
                    run_id=run_id,
                    tool_call_id=tc_record["id"],
                    tool_name=tool_call.name,
                    result_data=result.result_data,
                )

            # Emit tool result event
            self._emit(
                event_callback,
                "tool_result",
                run_id=run_id,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                success=result.success,
                result_summary=result.result_summary,
                duration_ms=result.duration_ms,
            )

            # Trace: tool_result
            await self._add_trace_event(
                run_id=run_id,
                event_type="tool_result",
                content={
                    "tool_name": tool_call.name,
                    "success": result.success,
                    "result_summary": result.result_summary,
                    "error_message": result.error_message,
                },
                actor=f"tool:{tool_call.name}",
                event_status="success" if result.success else "error",
                step_number=step_number,
                duration_ms=result.duration_ms or 0,
                parent_event_id=tool_call_event_id,
            )

            results.append((tool_call, result))

        return results

    def _format_tool_result(self, result: "ToolResult") -> str:
        """Format tool result for message content.

        Args:
            result: ToolResult from execution.

        Returns:
            JSON string for tool message content, truncated if too large.
        """
        if result.success:
            # Use full result_data if available, otherwise summary
            if result.result_data:
                content = json.dumps(result.result_data, ensure_ascii=False)
            else:
                content = result.result_summary
        else:
            content = json.dumps(
                {
                    "error": result.error_message or "Unknown error",
                    "summary": result.result_summary,
                }
            )

        # Truncate if too large to prevent context blowout
        if len(content) > self.MAX_TOOL_RESULT_CHARS:
            truncated = content[: self.MAX_TOOL_RESULT_CHARS - 100]
            content = truncated + f"\n\n[... truncated {len(content) - len(truncated)} chars ...]"
            logger.warning(
                "Truncated large tool result",
                extra={
                    "original_chars": len(content),
                    "truncated_to": self.MAX_TOOL_RESULT_CHARS,
                },
            )

        return content

    def _force_prune_largest(
        self, messages: List[Dict[str, Any]], step_metadata: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """Force prune the largest tool result to reduce context size.

        Finds the tool message with the largest content and summarizes it,
        preserving key information while dramatically reducing token count.
        Prioritizes older messages over recent ones to preserve recent context.

        Args:
            messages: List of message dicts.
            step_metadata: Mapping of tool_call_id to step number.

        Returns:
            New list with the largest tool result summarized.
        """
        # Find tool messages sorted by size (largest first), preferring older steps
        tool_messages = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool" and not msg.get("_force_pruned"):
                content = msg.get("content", "")
                step = msg.get("_step") or step_metadata.get(msg.get("tool_call_id"), 999)
                tool_messages.append((i, len(content), step, msg))

        if not tool_messages:
            # No tool messages to prune - truncate the largest message regardless of type
            logger.warning("No tool messages to prune, truncating largest message")
            largest_idx = -1
            largest_size = 0
            for i, msg in enumerate(messages):
                content_len = len(str(msg.get("content", "")))
                if content_len > largest_size and msg.get("role") != "system":
                    largest_size = content_len
                    largest_idx = i

            if largest_idx >= 0 and largest_size > 1000:
                new_messages = messages.copy()
                msg = new_messages[largest_idx]
                content = str(msg.get("content", ""))
                # Keep first and last portions
                summary = content[:500] + "\n\n[... content truncated for context limit ...]\n\n" + content[-500:]
                new_messages[largest_idx] = {**msg, "content": summary, "_force_pruned": True}
                return new_messages
            return messages

        # Sort by: older steps first (lower step number), then by size (larger first)
        # This ensures we prune older large results before recent ones
        tool_messages.sort(key=lambda x: (x[2], -x[1]))

        # Take the first candidate (oldest step with large content)
        target_idx, content_len, step, target_msg = tool_messages[0]

        # Create summary based on tool type
        tool_name = target_msg.get("name", "unknown")
        content = target_msg.get("content", "")

        if tool_name == "web_search":
            # For web search, keep query and result count
            try:
                data = json.loads(content)
                query = data.get("query", "unknown query")
                results = data.get("results", [])
                # Keep just URLs and titles for reference
                brief_results = [
                    {"title": r.get("title", "")[:60], "url": r.get("url", "")}
                    for r in results[:5]  # Keep top 5 only
                ]
                summary = json.dumps({
                    "query": query,
                    "result_count": len(results),
                    "top_results": brief_results,
                    "_summarized": True,
                })
            except (json.JSONDecodeError, TypeError):
                summary = f"[Web search results - {content_len} chars, summarized for context limit]"

        elif tool_name == "web_extract":
            # For web extract, keep URL and brief excerpt
            try:
                data = json.loads(content)
                url = data.get("url", "unknown")
                title = data.get("title", "")[:100]
                # Keep first 500 chars of content as excerpt
                full_content = data.get("full_content", "")
                excerpt = full_content[:500] + "..." if len(full_content) > 500 else full_content
                summary = json.dumps({
                    "url": url,
                    "title": title,
                    "excerpt": excerpt,
                    "_summarized": True,
                })
            except (json.JSONDecodeError, TypeError):
                summary = f"[Web extract results - {content_len} chars, summarized for context limit]"

        elif tool_name == "python_execute":
            # For python, keep code and truncated output
            try:
                data = json.loads(content)
                code = data.get("code", "")[:300]
                output = data.get("output", "")
                output_summary = output[:200] + "..." if len(output) > 200 else output
                summary = json.dumps({
                    "code": code + ("..." if len(data.get("code", "")) > 300 else ""),
                    "output": output_summary,
                    "success": data.get("success", True),
                    "_summarized": True,
                })
            except (json.JSONDecodeError, TypeError):
                summary = f"[Python execution results - {content_len} chars, summarized for context limit]"

        else:
            # Generic summarization
            summary = f"[Tool '{tool_name}' results - {content_len} chars, summarized for context limit]"

        # Create new messages list with summarized content
        new_messages = messages.copy()
        new_messages[target_idx] = {
            **target_msg,
            "content": summary,
            "_force_pruned": True,
        }

        logger.info(
            "Force pruned large tool result",
            extra={
                "tool_name": tool_name,
                "step": step,
                "original_chars": content_len,
                "summary_chars": len(summary),
            },
        )

        return new_messages

    def _extract_thinking(self, text: str) -> Optional[str]:
        """Extract thinking from Harmony format <think>...</think>.

        Args:
            text: LLM response text.

        Returns:
            Thinking content or None.
        """
        if not text:
            return None

        match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _clean_answer(self, text: str) -> str:
        """Remove thinking tags and Harmony format tokens from answer.

        Uses shared sanitization utility to handle all gpt-oss Harmony
        format control tokens that should not be displayed to users.

        Args:
            text: Raw LLM response.

        Returns:
            Cleaned answer text.
        """
        return sanitize_harmony_tokens(text)

    async def _store_citations_from_tool(
        self,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        result_data: Any,
    ) -> None:
        """Store citations from search/extract results.

        Args:
            run_id: Run ID.
            tool_call_id: Tool call ID.
            tool_name: Tool name.
            result_data: Result data from tool.
        """
        if not result_data:
            return

        if tool_name == "web_search":
            results = result_data.get("results", [])
            for r in results:
                url = r.get("url", "")
                if url:
                    await self._repo.create_citation(
                        run_id=run_id,
                        tool_call_id=tool_call_id,
                        source_url=url,
                        title=r.get("title"),
                        snippet=r.get("snippet", "")[:500],
                    )
        elif tool_name == "web_extract":
            # Handle both single extraction and batch extraction
            extractions = result_data.get("extractions", [result_data])
            for extraction in extractions:
                url = extraction.get("url", "")
                if url:
                    title = extraction.get("title")
                    content = extraction.get("content", "")
                    await self._repo.create_citation(
                        run_id=run_id,
                        tool_call_id=tool_call_id,
                        source_url=url,
                        title=title,
                        snippet=content[:500] if content else "",
                    )

    async def _extract_and_store_citations(
        self,
        run_id: str,
        answer: str,
    ) -> List[Dict[str, Any]]:
        """Mark citations used in final answer.

        Args:
            run_id: Run ID.
            answer: Final answer text.

        Returns:
            List of used citation dicts.
        """
        # Get all citations for run
        all_citations = await self._repo.get_citations_for_run(run_id)

        # Simple heuristic: mark citations whose URL appears in answer
        used_ids = []
        for citation in all_citations:
            url = citation.get("source_url", "")
            if url and url in answer:
                used_ids.append(citation["id"])

        # Also check for [1], [2] style references
        ref_matches = re.findall(r"\[(\d+)\]", answer)
        for i, citation in enumerate(all_citations):
            if str(i + 1) in ref_matches:
                if citation["id"] not in used_ids:
                    used_ids.append(citation["id"])

        if used_ids:
            await self._repo.mark_citations_used(used_ids)

        return [c for c in all_citations if c["id"] in used_ids]

    async def _force_synthesis(
        self,
        messages: List[Dict[str, Any]],
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
    ) -> str:
        """Force synthesis when max steps reached.

        Args:
            messages: Current message list.
            event_callback: SSE callback.
            run_id: Run ID.

        Returns:
            Synthesized answer.
        """
        # Add instruction to synthesize
        force_msg = {
            "role": "user",
            "content": (
                "You have reached the maximum number of research steps. "
                "Please synthesize your findings and provide your best answer "
                "based on the information gathered so far. "
                "Use inline [1], [2] citations but do NOT add a separate Citations section."
            ),
        }
        messages = messages + [force_msg]

        self._emit(
            event_callback,
            "synthesizing",
            run_id=run_id,
            forced=True,
        )

        # Call LLM without tools to force text response
        answer_tokens: List[str] = []

        def on_token(token: str) -> None:
            answer_tokens.append(token)
            # Sanitize token before emitting to UI
            cleaned = sanitize_harmony_tokens(token)
            if cleaned:
                self._emit(
                    event_callback,
                    "answer_token",
                    run_id=run_id,
                    content=cleaned,
                )

        response = await self._provider.complete_streaming(
            messages=messages,
            model=self._model_name,
            on_token=on_token,
            tools=None,  # No tools - force text response
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        return self._clean_answer(response.text)
