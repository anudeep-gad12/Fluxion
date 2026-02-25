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
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from orchestrator.agent.context_pruner import ContextPruner
from orchestrator.agent.recovery import (
    build_recovery_messages,
    create_idempotency_key,
)
from orchestrator.agent.state_machine import (
    AgentStateMachine,
    MaxStepsExceededError,
    RecoveryContext,
)
from orchestrator.logging_config import get_logger
from orchestrator.schemas import AgentStepState
from orchestrator.utils.sanitize import sanitize_harmony_tokens

if TYPE_CHECKING:
    from orchestrator.agent.planner import ResearchPlan
    from orchestrator.agent.profile import AgentProfile
    from orchestrator.agent.tools.base import ToolResult
    from orchestrator.agent.tools.registry import ToolRegistry
    from orchestrator.providers.base import LLMProvider, LLMResponse
    from orchestrator.storage.repositories.agent_repo import AgentRepo
    from orchestrator.storage.repositories.trace_repo import TraceRepo

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
        total_tokens: Total tokens used across all LLM calls.
    """

    run_id: str
    success: bool
    final_answer: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    error_message: Optional[str] = None
    timing_ms: int = 0
    total_tokens: int = 0


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
    DEFAULT_SYSTEM_PROMPT = """You are a research assistant that helps users find and analyze information. You have access to tools for web searching, extracting content from URLs, and running Python code for calculations.

{date_context}

You have ONLY three tools available (no others exist):
- web_search: Find URLs for information online
- web_extract: Get full page content from URLs
- python_execute: Run calculations and data analysis

IMPORTANT: After using web_extract, you have the COMPLETE page content. Read through it directly to find what you need - do not try to call any "search within page" or "find" tools, they don't exist.

=== RESEARCH GUIDELINES ===

1. GOOD SOURCES: Wikipedia, official sites (.gov, .edu), established news. Avoid forums, blogs, paywalled sites.

2. EFFICIENCY: One good source with clear facts is enough. Only search again if information is unclear or conflicting.

3. EXTRACT WHEN NEEDED: Use web_extract to get full content when search snippets aren't sufficient.

=== MANDATORY PYTHON PROTOCOL ===

For ANY calculation, you MUST use python_execute:
- Math operations (addition, multiplication, percentages)
- Date calculations (days between dates, years)
- Unit conversions (miles to km, F to C)
- Counting or aggregating data

CRITICAL: Always use print() to output results. The tool only captures stdout.
Code without print() returns nothing and wastes a step.
WRONG: x = 5 * 3          → returns "(no output)"
RIGHT: x = 5 * 3; print(x) → returns "15"

Don't use python_execute to verify values already stated in the content.

NEVER compute mentally or in text.

=== RESPONSE FORMAT ===

Do NOT include inline citation numbers like [1], [2] in your answer text. The UI automatically displays a Sources section at the bottom with all the web pages you consulted during research.

Be warm and engaging. Show genuine interest in helping and enthusiasm for findings.

When ready to give your final answer, respond without calling any tools."""

    # DEPRECATED: Query classification is disabled. DEFAULT_SYSTEM_PROMPT now includes
    # calculation guidelines. Kept for backwards compatibility.
    # Calculation-focused system prompt for physics/math queries
    CALCULATION_SYSTEM_PROMPT = """You are a research assistant specializing in physics and mathematical calculations.

{date_context}

You have ONLY three tools (no others exist):
- python_execute: Run Python code for calculations (USE THIS for any physics/math computation)
- web_search: Search the web for reference data or constants
- web_extract: Extract detailed content from URLs (then READ it directly, don't try to search within it)

CRITICAL INSTRUCTIONS FOR CALCULATIONS:
1. For ANY physics or mathematical calculation, you MUST use python_execute
2. NEVER compute physics formulas mentally or in text - always use Python code
3. Even "simple" physics calculations (like kinetic energy, velocity, etc.) MUST use python_execute
4. Use Python for: unit conversions, formula evaluation, numerical computation
5. Only answer directly for trivial arithmetic like "2+2" or "5*3"
6. ALWAYS use print() to output results - the tool only captures stdout.
   Code without print() returns nothing and wastes a step.

CALCULATION WORKFLOW:
1. Identify the physics/math problem and relevant formula
2. Use python_execute to compute the result with proper units
3. If you need reference data (constants, material properties), use web_search first
4. Present the final answer with the computation result

WEB EXTRACT: Use when you need reference data. Wikipedia and official sources are fine.

NEVER answer with mental math like "KE = 0.5 * 5 * 100 = 250 J" - always use python_execute.

RESPONSE FORMAT:
- Do NOT include inline citation numbers like [1], [2] in your answer
- The UI automatically displays a Sources section with all consulted pages

To provide your final answer, respond WITHOUT calling any tools."""

    # Maximum characters for tool result content (prevents context blowout)
    MAX_TOOL_RESULT_CHARS: int = 50000

    def __init__(
        self,
        provider: "LLMProvider",
        repo: "AgentRepo",
        registry: "ToolRegistry",
        trace_repo: Optional["TraceRepo"] = None,
        model_name: str = "openai/gpt-oss-120b",
        max_steps: int = 10,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        keep_full_steps: int = 10,
        tool_choice: Optional[str] = None,
        max_context_tokens: int = 100000,
        slow_response_threshold: float = 15.0,
        planning_enabled: bool = True,
        max_plan_steps: int = 5,
        approval_callback: Optional[Callable] = None,
        permission_policy: str = "strict",
        profile: Optional["AgentProfile"] = None,
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
            planning_enabled: Whether to create research plans before execution.
            max_plan_steps: Maximum steps the planner can create (default 5).
            profile: Agent profile for behavior customization.
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

        # Agent profile
        self._profile = profile

        # Findings accumulator for improved synthesis
        self._findings: List[Dict[str, Any]] = []
        self._current_query: Optional[str] = None

        # Token accumulator for run stats
        self._total_tokens: int = 0

        # Planning configuration
        self._planning_enabled = planning_enabled
        self._max_plan_steps = max_plan_steps
        self._current_plan: Optional["ResearchPlan"] = None

        # Permission system
        self._approval_callback = approval_callback
        self._permission_policy = permission_policy

        # Run metrics accumulator
        self._tool_call_log: List[Dict[str, Any]] = []

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

        # Initialize findings for this run
        self._findings = []
        self._current_query = query
        self._total_tokens = 0
        self._tool_call_log = []

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

        # Enable LLM-based smart summarization for context pruning
        self._pruner.set_llm(self._provider, self._model_name, query)

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

            # Planning step - create plan before execution loop
            self._current_plan = None
            if self._planning_enabled:
                plan = await self._create_plan(run_id, query, event_callback)
                if plan:
                    self._current_plan = plan
                    messages_before = len(messages)
                    messages = self._inject_plan_into_messages(messages, plan)

                    # Trace: plan_injected - verify plan is in messages
                    await self._add_trace_event(
                        run_id=run_id,
                        event_type="plan_injected",
                        content={
                            "plan_id": plan.id,
                            "messages_before": messages_before,
                            "messages_after": len(messages),
                            "plan_text_preview": plan.to_injection_text()[:500],
                        },
                        actor="system",
                    )

                    logger.info(
                        "Plan injected into messages",
                        extra={
                            "run_id": run_id,
                            "plan_id": plan.id,
                            "messages_before": messages_before,
                            "messages_after": len(messages),
                            "plan_step_count": len(plan.steps),
                        },
                    )

            # Step metadata for context pruning (maps tool_call_id -> step_number)
            step_metadata: Dict[str, int] = {}
            tool_steps_completed = 0

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

                # Prune context before LLM call (uses LLM for smart summarization)
                pruned_messages = await self._pruner.prune_async(
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
                    # Coding/full profiles: force tool use until model has explored
                    if (
                        self._profile
                        and self._profile.name in ("coding", "full")
                        and tool_steps_completed == 0
                    ):
                        step_tool_choice = "required"
                    elif step_number == 1 and self._tool_choice:
                        step_tool_choice = self._tool_choice
                    else:
                        step_tool_choice = None
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
                        total_tokens=self._total_tokens,
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
                    token_count=llm_response.usage.get("total_tokens"),
                )

                # Accumulate tokens for run stats
                if llm_response.usage.get("total_tokens"):
                    self._total_tokens += llm_response.usage["total_tokens"]

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

                    # Update plan progress based on executed tools
                    if self._current_plan:
                        parsed_calls = []
                        for tc in tool_calls:
                            args = tc["function"].get("arguments", {})
                            if isinstance(args, str):
                                raw_args = args
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    args = {}
                            else:
                                raw_args = json.dumps(args)
                            parsed_calls.append(ParsedToolCall(
                                id=tc["id"],
                                name=tc["function"]["name"],
                                arguments=args,
                                raw_arguments=raw_args,
                            ))
                        self._update_plan_progress(parsed_calls, step_number)

                    tool_steps_completed += 1

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

                    # Compute and store run metrics
                    await self._store_run_metrics(run_id, total_timing_ms)

                    return AgentResult(
                        run_id=run_id,
                        success=True,
                        final_answer=final_answer,
                        citations=citations,
                        total_steps=step_number,
                        timing_ms=total_timing_ms,
                        total_tokens=self._total_tokens,
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

            # Compute and store run metrics
            await self._store_run_metrics(run_id, total_timing_ms)

            return AgentResult(
                run_id=run_id,
                success=True,
                final_answer=final_answer,
                citations=citations,
                total_steps=state_machine.current_step,
                timing_ms=total_timing_ms,
                total_tokens=self._total_tokens,
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
                total_tokens=self._total_tokens,
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
                total_tokens=self._total_tokens,
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
        token_count: Optional[int] = None,
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
            token_count: Number of tokens used (from API response).

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
                token_count=token_count,
            )
        except Exception as e:
            logger.warning("Failed to write trace event", extra={"error": str(e)})
            return None

    # =========================================================================
    # Planning Methods
    # =========================================================================

    async def _create_plan(
        self,
        run_id: str,
        query: str,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> Optional["ResearchPlan"]:
        """Create a research plan for the query.

        The planner LLM naturally scales plan complexity:
        - Simple queries get 1-step plans
        - Complex queries get 3-5 step plans

        Args:
            run_id: Current run ID.
            query: User's query.
            event_callback: SSE callback.

        Returns:
            ResearchPlan if created successfully, None otherwise.
        """
        from orchestrator.agent.planner import Planner

        planning_start = time.perf_counter()

        # Trace: planning_start
        await self._add_trace_event(
            run_id=run_id,
            event_type="planning_start",
            content={"query": query[:200]},
            actor="system",
        )

        # Use profile-specific planning prompt and step types if available
        planning_kwargs: Dict[str, Any] = {
            "provider": self._provider,
            "model_name": self._model_name,
            "max_plan_steps": self._max_plan_steps,
        }
        if self._profile:
            if self._profile.planning_prompt_template:
                planning_kwargs["planning_prompt"] = self._profile.planning_prompt_template
            if self._profile.plan_step_types:
                planning_kwargs["valid_step_types"] = self._profile.plan_step_types

        planner = Planner(**planning_kwargs)

        plan = await planner.create_plan(query, self._registry.tool_names)

        planning_duration_ms = int((time.perf_counter() - planning_start) * 1000)

        if plan:
            # Trace: plan_created
            await self._add_trace_event(
                run_id=run_id,
                event_type="plan_created",
                content=plan.to_dict(),
                actor="model",
                duration_ms=planning_duration_ms,
            )

            logger.info(
                "Research plan created",
                extra={
                    "run_id": run_id,
                    "plan_id": plan.id,
                    "steps": len(plan.steps),
                    "complexity": plan.estimated_complexity,
                    "duration_ms": planning_duration_ms,
                },
            )
        else:
            # Trace: planning_failed
            await self._add_trace_event(
                run_id=run_id,
                event_type="planning_failed",
                content={"reason": "Planning LLM call failed or returned invalid plan"},
                actor="system",
                event_status="error",
                duration_ms=planning_duration_ms,
            )

            logger.warning(
                "Planning failed, agent will proceed without plan",
                extra={"run_id": run_id, "duration_ms": planning_duration_ms},
            )

        return plan

    def _inject_plan_into_messages(
        self,
        messages: List[Dict[str, Any]],
        plan: "ResearchPlan",
    ) -> List[Dict[str, Any]]:
        """Inject research plan into message list.

        Appends the plan to the existing system message to maintain proper
        message alternation (required by some models like Mistral).

        Args:
            messages: Current message list.
            plan: Research plan to inject.

        Returns:
            New message list with plan appended to system prompt.
        """
        plan_text = plan.to_injection_text()
        plan_content = f"""

=== RESEARCH PLAN FOR THIS QUERY ===

{plan_text}

Follow this plan as a guide. Adapt as needed based on what you discover.
When you complete each step, proceed to the next."""

        # Find and modify the system message (should be first)
        new_messages = []
        plan_injected = False
        for msg in messages:
            if msg.get("role") == "system" and not plan_injected:
                # Append plan to system message
                new_msg = msg.copy()
                new_msg["content"] = msg["content"] + plan_content
                new_msg["_plan"] = True  # Marker for context pruning
                new_messages.append(new_msg)
                plan_injected = True
            else:
                new_messages.append(msg)

        return new_messages

    def _update_plan_progress(
        self,
        tool_calls: List[Dict[str, Any]],
        step_number: int,
    ) -> None:
        """Update plan progress based on executed tools.

        Maps executed tools to plan steps and marks them complete.

        Args:
            tool_calls: List of tool calls that were executed.
            step_number: Current agent step number.
        """
        if not self._current_plan:
            return

        from orchestrator.agent.planner import PlanStepStatus

        # Get tool names from executed calls
        executed_tools = set()
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("function", {}).get("name", "")
            else:
                # ParsedToolCall object
                name = getattr(tc, "name", "")
            if name:
                executed_tools.add(name)

        # Find and mark matching plan steps
        for plan_step in self._current_plan.steps:
            if plan_step.status == PlanStepStatus.PENDING:
                if plan_step.expected_tool in executed_tools:
                    plan_step.status = PlanStepStatus.COMPLETED
                    logger.debug(
                        "Plan step completed",
                        extra={
                            "plan_step": plan_step.step_number,
                            "tool": plan_step.expected_tool,
                            "agent_step": step_number,
                        },
                    )
                    break  # Only mark one step per iteration

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
        # Build system prompt: if profile is set, the factory already formatted
        # the prompt with date_context and project_context. Otherwise, inject
        # date context for backward compatibility.
        if self._profile:
            system_prompt = self._system_prompt
        else:
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
                # Skip incomplete runs (no assistant response) to maintain
                # strict user/assistant alternation required by some models
                if not assistant_msg:
                    continue
                # Skip if this is the same query we're about to add
                if user_msg == query:
                    continue
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
            """Handle native reasoning tokens - emit to thinking panel.

            Pass tokens through raw (no sanitization, no whitespace stripping)
            to match chat mode behavior. Any cleanup happens on the frontend
            or when final thinking_text is persisted to the database.
            """
            first_token_received.set()
            if reasoning:
                self._emit(event_callback, "thinking", run_id=run_id, content=reasoning)

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
                available_tools = list(self._registry._tools.keys())
                result = ToolResult(
                    success=False,
                    result_summary=f"Unknown tool: {tool_call.name}",
                    error_message=(
                        f"Tool '{tool_call.name}' does not exist. "
                        f"Available tools: {', '.join(available_tools)}. "
                        f"Use web_search to find URLs, web_extract to get page content, "
                        f"or python_execute to process/search text."
                    ),
                    duration_ms=0,
                )
            else:
                # Validate required arguments before execution
                required_args = tool.schema.parameters.get("required", [])
                missing_args = [arg for arg in required_args if arg not in tool_call.arguments]
                if missing_args:
                    arg_list = ", ".join(f"'{a}'" for a in missing_args)
                    result = ToolResult(
                        success=False,
                        result_summary=f"Missing required args: {arg_list}",
                        error_message=(
                            f"Missing required argument(s): {arg_list}. "
                            f"The {tool_call.name} tool requires these parameters."
                        ),
                        duration_ms=0,
                    )
                else:
                    # Permission gate: check if tool needs approval
                    permission_level = getattr(tool.schema, "permission_level", "auto")
                    needs_approval = (
                        self._permission_policy != "yolo"
                        and permission_level != "auto"
                        and self._approval_callback is not None
                    )

                    if needs_approval:
                        # Emit approval request event
                        self._emit(
                            event_callback,
                            "tool_approval_required",
                            run_id=run_id,
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                            permission_level=permission_level,
                        )
                        # Wait for approval
                        try:
                            approved = await self._approval_callback(
                                run_id, tool_call.id, tool_call.name, tool_call.arguments
                            )
                        except Exception as e:
                            logger.error(
                                "Approval callback error",
                                extra={"tool": tool_call.name, "error": str(e)},
                            )
                            approved = False

                        # Record approval decision
                        await state_machine.record_approval(
                            tool_call_id=tc_record["id"],
                            decision="approved" if approved else "denied",
                            policy=self._permission_policy,
                        )

                        if not approved:
                            result = ToolResult(
                                success=False,
                                result_summary=f"User denied {tool_call.name}",
                                error_message="Tool execution denied by user.",
                                duration_ms=0,
                            )
                            # Skip to recording completion
                            await state_machine.complete_tool_call(
                                tool_call_id=tc_record["id"],
                                success=False,
                                result_summary=result.result_summary,
                                duration_ms=0,
                                error_message=result.error_message,
                            )
                            self._emit(
                                event_callback,
                                "tool_result",
                                run_id=run_id,
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                                success=False,
                                result_summary=result.result_summary,
                            )
                            results.append({
                                "tool_call_id": tool_call.id,
                                "content": result.error_message or "Denied",
                            })
                            continue
                    else:
                        # Auto-approved tool (no approval needed)
                        await state_machine.record_approval(
                            tool_call_id=tc_record["id"],
                            decision="auto",
                            policy=self._permission_policy,
                        )

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

            # Capture full result_detail for write tools
            result_detail = None
            if tool_call.name in ("write_file", "edit_file", "bash_tool") and result.result_data:
                result_detail = json.dumps(result.result_data, ensure_ascii=False)[:10000]

            # Record completion
            await state_machine.complete_tool_call(
                tool_call_id=tc_record["id"],
                success=result.success,
                result_summary=result.result_summary,
                duration_ms=result.duration_ms or 0,
                error_message=result.error_message,
                result_detail=result_detail,
            )

            # Record file change artifact for write tools
            if result.success and tool_call.name in ("write_file", "edit_file", "bash_tool"):
                artifact_type = {
                    "write_file": "file_write",
                    "edit_file": "file_edit",
                    "bash_tool": "command_run",
                }.get(tool_call.name, tool_call.name)
                file_path = tool_call.arguments.get(
                    "file_path", tool_call.arguments.get("command", "")
                )
                try:
                    await self._repo.create_run_artifact(
                        run_id=run_id,
                        artifact_type=artifact_type,
                        file_path=file_path,
                        action=tool_call.name,
                        detail=result.result_summary,
                        tool_call_id=tc_record["id"],
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to record artifact",
                        extra={"run_id": run_id, "tool": tool_call.name, "error": str(e)},
                    )

            # Extract citations from search/extract results
            if result.success and tool_call.name in ("web_search", "web_extract"):
                await self._store_citations_from_tool(
                    run_id=run_id,
                    tool_call_id=tc_record["id"],
                    tool_name=tool_call.name,
                    result_data=result.result_data,
                )

            # Extract key finding from successful tool calls
            if result.success:
                finding = self._extract_finding_from_result(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                    result_summary=result.result_summary,
                    step_number=step_number,
                )
                if finding:
                    self._findings.append(finding)
                    logger.debug(
                        "Extracted finding from tool result",
                        extra={"step": step_number, "tool": tool_call.name},
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

            # Log tool call for run metrics
            self._tool_call_log.append({
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "success": result.success,
                "step_number": step_number,
            })

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

    def _clean_reasoning_for_answer(self, reasoning: str) -> str:
        """Clean reasoning content to use as answer fallback.

        Removes JSON tool call patterns and other artifacts that appear
        in reasoning content but shouldn't be in the final answer.

        Args:
            reasoning: Raw reasoning content from the model.

        Returns:
            Cleaned reasoning suitable for display as answer.
        """
        import re

        # Remove JSON objects that look like tool calls (e.g., {"urls": [...], "query": ...})
        # Pattern matches { ... } where content looks like a tool call
        cleaned = re.sub(r'\{["\']?(urls|query|num_results)["\']?\s*:\s*[^}]+\}', '', reasoning)

        # Remove standalone JSON arrays
        cleaned = re.sub(r'\[\s*"https?://[^]]+\]', '', cleaned)

        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Remove trailing punctuation fragments
        cleaned = re.sub(r'[,.:;]+\s*$', '', cleaned).strip()

        return cleaned

    def _extract_finding_from_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result_summary: str,
        step_number: int,
    ) -> Optional[Dict[str, Any]]:
        """Extract a key finding from a tool result.

        Uses profile.findings_tools to determine which tools produce findings.

        Args:
            tool_name: Name of the tool.
            arguments: Tool arguments.
            result_summary: Summary of the result.
            step_number: Current step number.

        Returns:
            Finding dict or None if no finding to extract.
        """
        if not result_summary or len(result_summary) < 20:
            return None

        # Check if this tool produces findings (profile-aware)
        if self._profile and self._profile.findings_tools:
            if tool_name not in self._profile.findings_tools:
                return None

        # For web_search, extract the query and summarize results
        if tool_name == "web_search":
            query = arguments.get("query", "")
            summary = result_summary[:300]
            if len(result_summary) > 300:
                summary += "..."
            return {
                "step": step_number,
                "tool": tool_name,
                "query": query,
                "content": f"Search for '{query}': {summary}",
            }

        # For web_extract, note what URL was extracted
        if tool_name == "web_extract":
            urls = arguments.get("urls", [])
            url_str = urls[0] if urls else "unknown"
            summary = result_summary[:400]
            if len(result_summary) > 400:
                summary += "..."
            return {
                "step": step_number,
                "tool": tool_name,
                "url": url_str,
                "content": f"Extracted from {url_str}: {summary}",
            }

        # For python_execute, note the calculation result
        if tool_name == "python_execute":
            if "Error" not in result_summary and len(result_summary) < 500:
                return {
                    "step": step_number,
                    "tool": tool_name,
                    "content": f"Python result: {result_summary[:200]}",
                }

        # For filesystem tools (coding profile), extract findings
        if tool_name in ("read_file", "grep", "glob"):
            summary = result_summary[:400]
            if len(result_summary) > 400:
                summary += "..."

            if tool_name == "read_file":
                file_path = arguments.get("file_path", "unknown")
                return {
                    "step": step_number,
                    "tool": tool_name,
                    "file_path": file_path,
                    "content": f"Read {file_path}: {summary}",
                }
            elif tool_name == "grep":
                pattern = arguments.get("pattern", "")
                return {
                    "step": step_number,
                    "tool": tool_name,
                    "pattern": pattern,
                    "content": f"Grep for '{pattern}': {summary}",
                }
            elif tool_name == "glob":
                pattern = arguments.get("pattern", "")
                return {
                    "step": step_number,
                    "tool": tool_name,
                    "pattern": pattern,
                    "content": f"Glob '{pattern}': {summary}",
                }

        return None

    def _compute_run_metrics(self) -> Dict[str, Any]:
        """Compute run metrics from tool call log.

        Returns:
            Dict with navigation_overhead, total_tool_calls, distinct_files_read,
            distinct_files_modified, retries, profile name.
        """
        read_tools = {"read_file", "glob", "grep", "list_directory"}
        write_tools = {"write_file", "edit_file"}

        total_tool_calls = len(self._tool_call_log)
        files_read: set = set()
        files_modified: set = set()

        # Count navigation overhead: read/glob/grep/list calls before first write/edit
        navigation_overhead = 0
        first_write_seen = False

        # Track retries: same tool + same primary argument
        call_signatures: Dict[str, int] = {}
        retries = 0

        for entry in self._tool_call_log:
            tool_name = entry["tool_name"]
            arguments = entry["arguments"]

            # Track files read
            if tool_name == "read_file":
                fp = arguments.get("file_path", "")
                if fp:
                    files_read.add(fp)
            elif tool_name in ("grep", "glob"):
                pattern = arguments.get("pattern", "")
                if pattern:
                    files_read.add(f"<{tool_name}:{pattern}>")

            # Track files modified
            if tool_name in write_tools:
                fp = arguments.get("file_path", "")
                if fp:
                    files_modified.add(fp)
                if not first_write_seen:
                    first_write_seen = True

            # Navigation overhead
            if not first_write_seen and tool_name in read_tools:
                navigation_overhead += 1

            # Retries: same tool + same primary arg
            primary_arg = ""
            if tool_name in ("read_file", "write_file", "edit_file"):
                primary_arg = arguments.get("file_path", "")
            elif tool_name == "grep":
                primary_arg = arguments.get("pattern", "")
            elif tool_name == "glob":
                primary_arg = arguments.get("pattern", "")
            elif tool_name == "web_search":
                primary_arg = arguments.get("query", "")

            sig = f"{tool_name}:{primary_arg}"
            call_signatures[sig] = call_signatures.get(sig, 0) + 1
            if call_signatures[sig] > 1:
                retries += 1

        return {
            "navigation_overhead": navigation_overhead,
            "total_tool_calls": total_tool_calls,
            "distinct_files_read": len(files_read),
            "distinct_files_modified": len(files_modified),
            "retries": retries,
            "context_tokens": len(self._system_prompt) // 4,  # Approximate
            "profile": self._profile.name if self._profile else "unknown",
        }

    async def _store_run_metrics(self, run_id: str, timing_ms: int) -> None:
        """Compute and store run metrics in the database.

        Args:
            run_id: Run ID.
            timing_ms: Total run timing in milliseconds.
        """
        try:
            metrics = self._compute_run_metrics()
            metrics["timing_ms"] = timing_ms
            metrics["total_tokens"] = self._total_tokens

            # Store via trace_repo usage_stats (accepts dict, serializes to JSON)
            if self._trace_repo:
                await self._trace_repo.update_run(
                    run_id,
                    usage_stats=metrics,
                )
                logger.info(
                    "Run metrics stored",
                    extra={
                        "run_id": run_id,
                        "profile": metrics.get("profile"),
                        "navigation_overhead": metrics.get("navigation_overhead"),
                        "total_tool_calls": metrics.get("total_tool_calls"),
                        "retries": metrics.get("retries"),
                    },
                )
        except Exception as e:
            logger.warning(
                "Failed to store run metrics",
                extra={"run_id": run_id, "error": str(e)},
            )

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
            logger.debug(
                "No result_data for citations",
                extra={"run_id": run_id, "tool_name": tool_name},
            )
            return

        if tool_name == "web_search":
            results = result_data.get("results", [])
            citation_count = 0
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
                    citation_count += 1
            logger.debug(
                "Stored citations from web_search",
                extra={"run_id": run_id, "citation_count": citation_count},
            )
        elif tool_name == "web_extract":
            # Handle both single extraction and batch extraction
            extractions = result_data.get("extractions", [result_data])
            citation_count = 0
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
                    citation_count += 1
            logger.debug(
                "Stored citations from web_extract",
                extra={"run_id": run_id, "citation_count": citation_count},
            )

    async def _extract_and_store_citations(
        self,
        run_id: str,
        answer: str,
    ) -> List[Dict[str, Any]]:
        """Get all citations for the run to show as sources.

        All sources gathered during research are returned so users can
        see what was consulted. The UI displays these at the end of
        the answer.

        Args:
            run_id: Run ID.
            answer: Final answer text.

        Returns:
            List of all citation dicts for the run.
        """
        # Get all citations for run - return all sources, not just "used" ones
        all_citations = await self._repo.get_citations_for_run(run_id)

        # Mark citations that are explicitly referenced in the answer
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

        # Return ALL citations so Sources section always shows what was consulted
        logger.info(
            "Returning citations for run",
            extra={
                "run_id": run_id,
                "total_citations": len(all_citations),
                "used_citations": len(used_ids),
            },
        )
        return all_citations

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
        # Build synthesis prompt with accumulated findings
        if self._findings:
            findings_text = "\n".join(
                f"- {f['content']}" for f in self._findings
            )
            synthesis_content = (
                f"IMPORTANT: You have reached the maximum number of research steps and NO MORE TOOLS ARE AVAILABLE.\n"
                f"Do NOT attempt to use any tools or output JSON.\n\n"
                f"ORIGINAL QUERY: {self._current_query}\n\n"
                f"KEY FINDINGS FROM YOUR RESEARCH ({len(self._findings)} items):\n"
                f"{findings_text}\n\n"
                f"Based on these findings, provide your FINAL ANSWER directly as plain text.\n"
                f"Address the original query directly and comprehensively.\n"
                f"Do NOT include inline citation numbers like [1], [2] - the UI will show sources automatically."
            )
        else:
            synthesis_content = (
                "IMPORTANT: You have reached the maximum number of research steps and NO MORE TOOLS ARE AVAILABLE. "
                "Do NOT attempt to use any tools or output JSON. "
                "Based on the information you have gathered so far, provide your FINAL ANSWER directly as plain text. "
                "Summarize the key findings and insights from your research. "
                "Do NOT include inline citation numbers like [1], [2] - the UI will show sources automatically."
            )

        force_msg = {
            "role": "user",
            "content": synthesis_content,
        }
        messages = messages + [force_msg]

        self._emit(
            event_callback,
            "synthesizing",
            run_id=run_id,
            forced=True,
        )

        # Trace: forced synthesis LLM request
        await self._add_trace_event(
            run_id=run_id,
            event_type="llm_request",
            content={
                "model": self._model_name,
                "messages_count": len(messages),
                "tools_count": 0,
                "forced_synthesis": True,
                "findings_count": len(self._findings),
            },
        )

        # Call LLM without tools to force text response
        # Use higher token limit for reasoning models that need extra tokens for chain-of-thought
        synthesis_max_tokens = max(self._max_tokens, 8192)
        answer_tokens: List[str] = []
        reasoning_tokens: List[str] = []

        def on_token(token: str) -> None:
            answer_tokens.append(token)
            # Pass through without sanitization to preserve word order;
            # full sanitization happens on accumulated text after streaming
            if token:
                self._emit(
                    event_callback,
                    "answer_token",
                    run_id=run_id,
                    content=token,
                )

        def on_reasoning(token: str) -> None:
            reasoning_tokens.append(token)

        response = await self._provider.complete_streaming(
            messages=messages,
            model=self._model_name,
            on_token=on_token,
            on_reasoning=on_reasoning,
            tools=None,  # No tools - force text response
            max_tokens=synthesis_max_tokens,
            temperature=self._temperature,
        )

        # Log synthesis results for debugging
        logger.info(
            "Forced synthesis completed",
            extra={
                "run_id": run_id,
                "text_length": len(response.text) if response.text else 0,
                "reasoning_length": len(response.reasoning) if response.reasoning else 0,
                "finish_reason": response.finish_reason,
            },
        )

        # Trace: forced synthesis LLM response
        await self._add_trace_event(
            run_id=run_id,
            event_type="llm_response",
            content={
                "text_length": len(response.text) if response.text else 0,
                "reasoning_length": len(response.reasoning) if response.reasoning else 0,
                "finish_reason": response.finish_reason,
                "forced_synthesis": True,
            },
            token_count=response.usage.get("total_tokens"),
        )

        # Accumulate tokens from forced synthesis
        if response.usage.get("total_tokens"):
            self._total_tokens += response.usage["total_tokens"]

        # If text is empty but we got reasoning, use reasoning as the answer
        # This can happen with reasoning models where the "thinking" IS the answer
        if not response.text and response.reasoning:
            logger.warning(
                "Forced synthesis produced reasoning but no content, using reasoning as answer",
                extra={
                    "run_id": run_id,
                    "reasoning_length": len(response.reasoning),
                    "finish_reason": response.finish_reason,
                },
            )
            # Clean reasoning content - remove JSON tool call attempts
            cleaned_reasoning = self._clean_reasoning_for_answer(response.reasoning)
            return self._clean_answer(cleaned_reasoning)

        # If both are empty, return a fallback message
        if not response.text:
            logger.error(
                "Forced synthesis produced no content at all",
                extra={
                    "run_id": run_id,
                    "finish_reason": response.finish_reason,
                },
            )
            return "I was unable to synthesize a complete answer based on the research gathered. Please try again with a more specific question."

        return self._clean_answer(response.text)
