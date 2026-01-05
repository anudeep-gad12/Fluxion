"""Agent engine for web research execution.

This module provides:
- AgentEngine: Main orchestration class for running agent queries
- Streaming SSE event emission
- Tool call parsing and execution
- Crash recovery support
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
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

if TYPE_CHECKING:
    from orchestrator.providers.base import LLMProvider, LLMResponse
    from orchestrator.storage.repositories.agent_repo import AgentRepo
    from orchestrator.agent.tools.registry import ToolRegistry
    from orchestrator.agent.tools.base import ToolResult

logger = get_logger(__name__)


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

    # Default system prompt for agent
    DEFAULT_SYSTEM_PROMPT = """You are a research assistant that MUST use tools to search the web and analyze information.

Available tools:
- web_search: Search the web for information (ALWAYS use this first for questions about current events, data, or facts)
- web_extract: Extract detailed content from URLs
- python_execute: Run Python code for calculations

IMPORTANT INSTRUCTIONS:
1. You MUST call web_search for questions requiring current information, data, or facts
2. Never assume you can't access information - always try searching first
3. If search results are empty or unhelpful, try different search terms
4. Only provide a final answer AFTER using tools to gather information
5. Always cite your sources with [1], [2], etc.

To provide your final answer, respond WITHOUT calling any tools.
Include citations in your response."""

    def __init__(
        self,
        provider: "LLMProvider",
        repo: "AgentRepo",
        registry: "ToolRegistry",
        model_name: str = "qwen3-32b",
        max_steps: int = 10,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        keep_full_steps: int = 2,
    ) -> None:
        """Initialize agent engine.

        Args:
            provider: LLM provider (can be ProviderChain for failover).
            repo: AgentRepo for persistence.
            registry: ToolRegistry with registered tools.
            model_name: Model to use for LLM calls.
            max_steps: Maximum steps before forcing synthesis.
            max_tokens: Max tokens for LLM response.
            temperature: Sampling temperature.
            system_prompt: Custom system prompt (or use default).
            keep_full_steps: Number of recent steps to keep detailed.
        """
        self._provider = provider
        self._repo = repo
        self._registry = registry
        self._model_name = model_name
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self._pruner = ContextPruner(keep_full_steps=keep_full_steps)

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

        # Initialize state machine
        state_machine = AgentStateMachine(
            run_id=run_id,
            repo=self._repo,
            tool_registry=self._registry,
            max_steps=self._max_steps,
        )

        try:
            recovery_context = await state_machine.initialize()

            # Build initial messages
            messages = self._build_initial_messages(query)

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

                # Prune context before LLM call
                pruned_messages = self._pruner.prune(
                    messages,
                    current_step=step_number,
                    step_metadata=step_metadata,
                )

                # Call LLM with tools
                try:
                    llm_response = await self._call_llm_with_tools(
                        messages=pruned_messages,
                        event_callback=event_callback,
                        run_id=run_id,
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

                # Extract thinking if present (Harmony format)
                thinking_text = self._extract_thinking(llm_response.text)

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
                    else:
                        logger.debug("No tool calls found in text", extra={"text": llm_response.text[:300] if llm_response.text else ""})

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
                    messages.append(
                        {
                            "role": "assistant",
                            "content": llm_response.text or None,
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

                    final_answer = self._clean_answer(llm_response.text)

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

                    self._emit(
                        event_callback,
                        "agent_complete",
                        run_id=run_id,
                        final_answer=final_answer,
                        citations=citations,
                        total_steps=step_number,
                    )

                    return AgentResult(
                        run_id=run_id,
                        success=True,
                        final_answer=final_answer,
                        citations=citations,
                        total_steps=step_number,
                        timing_ms=int((time.perf_counter() - start_time) * 1000),
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

            self._emit(
                event_callback,
                "agent_complete",
                run_id=run_id,
                final_answer=final_answer,
                citations=citations,
                total_steps=state_machine.current_step,
            )

            return AgentResult(
                run_id=run_id,
                success=True,
                final_answer=final_answer,
                citations=citations,
                total_steps=state_machine.current_step,
                timing_ms=int((time.perf_counter() - start_time) * 1000),
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

            return AgentResult(
                run_id=run_id,
                success=False,
                error_message=str(e),
                total_steps=state_machine.current_step,
                timing_ms=int((time.perf_counter() - start_time) * 1000),
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

    def _build_initial_messages(self, query: str) -> List[Dict[str, Any]]:
        """Build initial message list with system prompt and query.

        Args:
            query: User's research query.

        Returns:
            Message list with system and user messages.
        """
        return [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": query},
        ]

    async def _call_llm_with_tools(
        self,
        messages: List[Dict[str, Any]],
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
    ) -> "LLMResponse":
        """Call LLM with tool schemas via streaming.

        Args:
            messages: Message list.
            event_callback: SSE callback.
            run_id: Run ID for events.

        Returns:
            LLMResponse with text and tool_calls.
        """
        tool_schemas = self._registry.get_openai_schemas()

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
            """Handle content tokens - sanitize before emitting."""
            cleaned = sanitize_token(token)
            if cleaned and cleaned.strip():
                self._emit(event_callback, "thinking", run_id=run_id, content=cleaned)

        def on_reasoning(reasoning: str) -> None:
            """Handle native reasoning tokens - sanitize before emitting."""
            cleaned = sanitize_token(reasoning)
            if cleaned and cleaned.strip():
                self._emit(event_callback, "thinking", run_id=run_id, content=cleaned)

        response = await self._provider.complete_streaming(
            messages=messages,
            model=self._model_name,
            on_token=on_token,
            on_reasoning=on_reasoning,
            tools=tool_schemas if tool_schemas else None,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        return response

    def _parse_text_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse tool calls from text using Harmony format.

        Handles models that output tool calls in text format rather than
        using the OpenAI tool_calls API. Handles various format variants:
        - <|channel|>commentary to=TOOL_NAME <|constrain|>json<|message|>{args}
        - <|channel|>commentary to=TOOL_NAME code<|message|>{args}
        - <|channel|>commentary to=TOOL_NAME json{args}

        Args:
            text: Response text that may contain embedded tool calls.

        Returns:
            List of tool call dicts in OpenAI format, or None if no tool calls found.
        """
        import uuid

        # Pattern: commentary to=TOOL_NAME followed by optional markers then JSON
        # Handles various format variants from gpt-oss models
        pattern = r'(?:<\|channel\|>)?commentary\s+to=(\w+)\s*(?:<\|constrain\|>)?(?:json|code)?(?:<\|message\|>)?(\{[^}]+\})'

        matches = re.findall(pattern, text, re.IGNORECASE)

        if not matches:
            return None

        tool_calls = []
        for tool_name, args_json in matches:
            try:
                # Validate JSON
                json.loads(args_json)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": args_json,
                    },
                })
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse tool call JSON from text",
                    extra={"tool_name": tool_name, "args": args_json},
                )
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

            results.append((tool_call, result))

        return results

    def _format_tool_result(self, result: "ToolResult") -> str:
        """Format tool result for message content.

        Args:
            result: ToolResult from execution.

        Returns:
            JSON string for tool message content.
        """
        if result.success:
            # Use full result_data if available, otherwise summary
            if result.result_data:
                return json.dumps(result.result_data, ensure_ascii=False)
            return result.result_summary
        else:
            return json.dumps(
                {
                    "error": result.error_message or "Unknown error",
                    "summary": result.result_summary,
                }
            )

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
        """Remove thinking tags from answer.

        Args:
            text: Raw LLM response.

        Returns:
            Cleaned answer text.
        """
        if not text:
            return ""

        # Remove <think>...</think> blocks
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return cleaned.strip()

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
                "based on the information gathered so far. Include citations."
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
            self._emit(
                event_callback,
                "answer_token",
                run_id=run_id,
                content=token,
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
