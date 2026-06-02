"""Agent engine for web research execution.

This module provides:
- AgentEngine: Main orchestration class for running agent queries
- Streaming SSE event emission
- Tool call parsing and execution
- Crash recovery support
"""

import asyncio
import hashlib
import inspect
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from orchestrator.agent.coding_context_builder import CodingSessionContextBuilder
from orchestrator.agent.coding_session import (
    CodingFileState,
    CodingSessionEntry,
    CodingSessionState,
)
from orchestrator.agent.context_pruner import ContextPruner
from orchestrator.agent.permissions import classify_tool_call
from orchestrator.agent.plan_mode import (
    PLAN_MODE_MUTATING_TOOLS,
    PlanDecision,
    extract_proposed_plan,
    normalize_collaboration_mode,
)
from orchestrator.agent.recovery import (
    build_recovery_messages,
    create_idempotency_key,
)
from orchestrator.agent.state_machine import (
    AgentStateMachine,
    MaxStepsExceededError,
)
from orchestrator.agent.tool_result_payloads import (
    bash_output_from_result_data,
    display_result_data,
)
from orchestrator.context.budget import ContextBudget
from orchestrator.context.context_profile import ModelContextProfile
from orchestrator.context.history_builder import HistoryBuilder
from orchestrator.logging_config import get_logger
from orchestrator.providers.usage import add_usage, estimate_cost, normalize_usage
from orchestrator.reasoning_controls import ReasoningSettings, apply_reasoning_settings
from orchestrator.schemas import AgentStepState
from orchestrator.utils.sanitize import sanitize_harmony_tokens
from orchestrator.vision import build_multimodal_user_content, validate_image_attachments

if TYPE_CHECKING:
    from orchestrator.agent.profile import AgentProfile
    from orchestrator.agent.tools.base import ToolResult
    from orchestrator.agent.tools.registry import ToolRegistry
    from orchestrator.providers.base import LLMProvider, LLMResponse
    from orchestrator.storage.repositories.agent_repo import AgentRepo
    from orchestrator.storage.repositories.trace_repo import TraceRepo

logger = get_logger(__name__)


def _format_exception_for_user(error: BaseException) -> str:
    """Format exceptions without losing type information for blank messages."""
    error_type = f"{error.__class__.__module__}.{error.__class__.__name__}"
    message = str(error).strip()
    if message:
        return f"{error_type}: {message}"
    return f"{error_type}: {repr(error)}"


# =============================================================================
# System Prompt Helpers
# =============================================================================


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
    context_usage: Optional[Dict[str, Any]] = None
    stored_context: Optional[Dict[str, Any]] = None
    context_profile: Optional[Dict[str, Any]] = None
    compaction_count: int = 0
    last_compacted_at_step: Optional[int] = None
    usage: Optional[Dict[str, int]] = None
    cost: Optional[Dict[str, Any]] = None
    approved_plan: Optional[str] = None
    implementation_run_id: Optional[str] = None
    implementation_stream_token: Optional[str] = None


@dataclass
class ParsedToolCall:
    """Parsed tool call from LLM response.

    Attributes:
        id: Tool call ID from LLM.
        name: Tool name.
        arguments: Parsed arguments dict.
        raw_arguments: Original JSON string (for hashing).
        parse_error: Validation error when arguments are malformed.
    """

    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str
    parse_error: Optional[str] = None


@dataclass
class WorkingMemory:
    """Compact agent working memory used for prompt reconstruction."""

    objective: str
    restored_session: bool = False
    restored_session_updated_at: Optional[str] = None
    prior_outcomes: List[str] = field(default_factory=list)
    files_inspected: Dict[str, str] = field(default_factory=dict)
    files_changed: Dict[str, str] = field(default_factory=dict)
    stale_file_summaries: Dict[str, str] = field(default_factory=dict)
    validation_results: List[str] = field(default_factory=list)
    recent_commands: List[str] = field(default_factory=list)
    current_hypothesis: Optional[str] = None
    unresolved_tasks: List[str] = field(default_factory=list)
    recent_raw_evidence: List[str] = field(default_factory=list)

    def render(self) -> str:
        """Render compact working memory for model context."""
        sections = [
            "This is durable state for the current agent conversation. Continue from it instead of restarting from scratch.",
            f"Current user request: {self.objective}",
        ]
        if self.restored_session:
            restored = "Persisted coding session state from earlier turns was restored for this conversation."
            if self.restored_session_updated_at:
                restored += f" Last updated: {self.restored_session_updated_at}."
            sections.append(restored)
        if self.prior_outcomes:
            sections.append(
                "Prior outcomes:\n"
                + "\n".join(f"- {item}" for item in self.prior_outcomes[-6:])
            )

        if self.files_inspected:
            inspected = "\n".join(
                f"- {path}: {summary}"
                for path, summary in list(self.files_inspected.items())[-8:]
            )
            sections.append(f"Files inspected:\n{inspected}")

        if self.files_changed:
            changed = "\n".join(
                f"- {path}: {summary}"
                for path, summary in list(self.files_changed.items())[-8:]
            )
            sections.append(f"Files changed:\n{changed}")

        if self.stale_file_summaries:
            stale = "\n".join(
                f"- {path}: {reason}"
                for path, reason in list(self.stale_file_summaries.items())[-8:]
            )
            sections.append(f"Stale stored file evidence:\n{stale}")

        if self.validation_results:
            sections.append(
                "Validation:\n"
                + "\n".join(f"- {item}" for item in self.validation_results[-6:])
            )
        if self.recent_commands:
            sections.append(
                "Recent commands:\n"
                + "\n".join(f"- {item}" for item in self.recent_commands[-6:])
            )

        if self.current_hypothesis:
            sections.append(f"Current hypothesis: {self.current_hypothesis}")

        if self.unresolved_tasks:
            sections.append(
                "Open tasks:\n"
                + "\n".join(f"- {item}" for item in self.unresolved_tasks[-6:])
            )
        if self.recent_raw_evidence:
            sections.append(
                "Recent raw evidence:\n"
                + "\n".join(f"- {item}" for item in self.recent_raw_evidence[-6:])
            )

        sections.append(
            "Use this working memory as the durable state. Raw tool outputs that follow "
            "are only from the most recent tool step. Continue from the current state, "
            "do not restate the plan, and answer directly when no tool is needed. "
            "If stored file evidence is present, reuse it before rereading files. "
            "Only reread when the stored evidence is stale, insufficient, or you need exact new context."
        )
        return "\n\n".join(sections)

    def render_coding_metadata(self) -> Optional[str]:
        """Render concise current coding state where the model reliably sees it."""
        lines: List[str] = [f"- current_request: {self.objective}"]
        if self.files_changed:
            lines.append(
                "- changed_files: "
                + ", ".join(list(self.files_changed.keys())[-8:])
            )
            diff_summary = " | ".join(
                f"{path}: {summary}"
                for path, summary in list(self.files_changed.items())[-6:]
            )
            lines.append(f"- compact_diff_summary: {diff_summary}")
        if self.files_inspected:
            lines.append(
                "- referenced_files: "
                + ", ".join(list(self.files_inspected.keys())[-8:])
            )
        if self.recent_commands:
            lines.append(
                "- recent_commands: "
                + " | ".join(self.recent_commands[-4:])
            )
        if self.validation_results:
            lines.append(
                "- recent_command_outcomes: "
                + " | ".join(self.validation_results[-4:])
            )
            failing = [
                item
                for item in self.validation_results[-8:]
                if any(
                    marker in item.lower()
                    for marker in ("failed", "error", "exit 1", "timed out")
                )
            ]
            if failing:
                lines.append("- failing_test_summary: " + " | ".join(failing[-3:]))
        if self.stale_file_summaries:
            stale = " | ".join(
                f"{path}: {reason}"
                for path, reason in list(self.stale_file_summaries.items())[-6:]
            )
            lines.append(f"- stale_files: {stale}")
        return "CODING SESSION CURRENT STATE\n" + "\n".join(lines)


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

    # Final emergency character floor after token-budget formatting.
    MAX_TOOL_RESULT_CHARS: int = 50000
    COMPACTION_THRESHOLD_PCT: int = 90
    COMPACTION_PREFIX: str = "Conversation compacted to preserve context window"

    def __init__(
        self,
        provider: "LLMProvider",
        repo: "AgentRepo",
        registry: "ToolRegistry",
        trace_repo: Optional["TraceRepo"] = None,
        model_name: str = "accounts/fireworks/models/kimi-k2p6",
        max_steps: int = 1000,
        max_tokens: int = 32768,
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
        reasoning_effort: Optional[str] = None,
        reasoning_request_param: Optional[str] = None,
        reasoning_provider_family: str = "generic",
        reasoning_settings: Optional[ReasoningSettings] = None,
        input_cost_per_million: Optional[float] = None,
        cached_input_cost_per_million: Optional[float] = None,
        output_cost_per_million: Optional[float] = None,
        context_profile: Optional[ModelContextProfile] = None,
        collaboration_mode: str = "default",
        plan_approval_callback: Optional[Callable[[str, str, str], Any]] = None,
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
            reasoning_effort: Reasoning effort level for providers that support it
                (e.g., OpenRouter: "low", "medium", "high"). Passed as
                {"effort": value} in the request payload.
        """
        self._provider = provider
        self._repo = repo
        self._registry = registry
        self._trace_repo = trace_repo
        # Use provider's default model if set (e.g. local MLX server).
        # MagicMock creates attributes on demand, so only accept real strings.
        provider_default_model = getattr(provider, "_default_model", None)
        self._model_name = (
            provider_default_model
            if isinstance(provider_default_model, str) and provider_default_model
            else model_name
        )
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self._pruner = ContextPruner(keep_full_steps=keep_full_steps)
        self._tool_choice = tool_choice
        self._max_context_tokens = max_context_tokens
        self._slow_response_threshold = slow_response_threshold
        self._context_profile = context_profile or ModelContextProfile(
            provider_name="unknown",
            model_id=self._model_name,
            display_name=self._model_name,
            context_window=max_context_tokens,
            max_output_tokens=max_tokens,
            supports_tools=True,
            supports_reasoning=bool(reasoning_effort),
            supports_vision=bool(getattr(provider, "_supports_vision", False)),
            pricing={
                "input_cost_per_million": input_cost_per_million,
                "cached_input_cost_per_million": cached_input_cost_per_million,
                "output_cost_per_million": output_cost_per_million,
            },
            source="config_fallback",
        )
        self._compaction_count = 0
        self._last_compacted_at_step: Optional[int] = None

        # Agent profile
        self._profile = profile

        # Findings accumulator for improved synthesis
        self._findings: List[Dict[str, Any]] = []
        self._current_query: Optional[str] = None

        # Token accumulator for run stats
        self._total_tokens: int = 0
        self._usage_totals: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        }
        self._input_cost_per_million = input_cost_per_million
        self._cached_input_cost_per_million = cached_input_cost_per_million
        self._output_cost_per_million = output_cost_per_million
        self._collaboration_mode = normalize_collaboration_mode(collaboration_mode)
        self._plan_approval_callback = plan_approval_callback
        self._approved_plan: Optional[str] = None
        self._implementation_run_id: Optional[str] = None
        self._implementation_stream_token: Optional[str] = None


        # Permission system
        self._approval_callback = approval_callback
        self._permission_policy = permission_policy

        # Reasoning config for providers like OpenRouter
        self._reasoning_effort = reasoning_effort
        self._reasoning_request_param = reasoning_request_param
        self._reasoning_provider_family = reasoning_provider_family
        self._reasoning_settings = reasoning_settings or ReasoningSettings(
            max_output_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )

        # Context budget tracking
        self._context_budget: Optional[ContextBudget] = None

        # Run metrics accumulator
        self._tool_call_log: List[Dict[str, Any]] = []
        self._tool_state_version = 0
        self._file_state_versions: Dict[str, int] = {}
        self._file_last_read_state_versions: Dict[str, int] = {}
        self._file_last_read_sequences: Dict[str, int] = {}
        self._file_read_sequence = 0
        self._edit_failures: Dict[str, Dict[str, Any]] = {}
        self._apply_patch_failures: Dict[str, Dict[str, Any]] = {}
        self._last_redundant_filter_codes: Dict[str, str] = {}
        self._coding_last_step_structural_failure = False
        self._last_context_usage: Optional[Dict[str, Any]] = None
        self._last_stored_context: Optional[Dict[str, Any]] = None
        self._active_conversation_id: Optional[str] = None
        self._active_coding_session_state: Optional[CodingSessionState] = None

    def _reasoning_provider_kwargs(self) -> tuple[int, Dict[str, Any]]:
        """Resolve provider-specific reasoning kwargs for the active model."""
        kwargs = apply_reasoning_settings(
            self._reasoning_settings,
            provider_family=self._reasoning_provider_family,
            supports_reasoning=bool(self._context_profile.supports_reasoning),
        )
        max_tokens = int(kwargs.pop("max_tokens", self._max_tokens))
        return max_tokens, kwargs

    def _build_prompt_messages(
        self,
        scaffold_messages: List[Dict[str, Any]],
        working_memory: WorkingMemory,
    ) -> List[Dict[str, Any]]:
        """Assemble the actual prompt from run transcript and working memory."""
        prompt_messages: List[Dict[str, Any]] = []
        working_memory_message = (
            {
                "role": "system",
                "content": "WORKING MEMORY\n" + working_memory.render(),
                "_working_memory": True,
            }
            if not self._is_coding_profile()
            else None
        )
        if scaffold_messages:
            prompt_messages.append(scaffold_messages[0])
            if working_memory_message is not None:
                prompt_messages.append(working_memory_message)
            prompt_messages.extend(scaffold_messages[1:])
        elif working_memory_message is not None:
            prompt_messages.append(working_memory_message)

        return prompt_messages

    def _summarize_assistant_content(self, content: Optional[str]) -> Optional[str]:
        """Keep concise assistant decision text in long-lived scaffold."""
        if not content:
            return None
        stripped = re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()
        if not stripped:
            return None
        if len(stripped) > 400:
            stripped = stripped[:397].rstrip() + "..."
        return stripped

    def _trim_scaffold_messages(
        self,
        scaffold_messages: List[Dict[str, Any]],
        max_assistant_messages: int = 8,
    ) -> List[Dict[str, Any]]:
        """Keep system + user turns and only the most recent short assistant decisions."""
        assistant_indices = [
            idx
            for idx, msg in enumerate(scaffold_messages)
            if idx > 0 and msg.get("role") == "assistant"
        ]
        if len(assistant_indices) <= max_assistant_messages:
            return scaffold_messages

        keep_assistant = set(assistant_indices[-max_assistant_messages:])
        trimmed: List[Dict[str, Any]] = []
        for idx, msg in enumerate(scaffold_messages):
            if idx == 0 or msg.get("role") != "assistant" or idx in keep_assistant:
                trimmed.append(msg)
        return trimmed

    def _prior_outcomes_from_scaffold(
        self,
        scaffold_messages: List[Dict[str, Any]],
    ) -> List[str]:
        """Extract compact prior outcomes from cross-turn scaffold messages."""
        outcomes: List[str] = []
        for msg in scaffold_messages[1:-1]:
            if msg.get("role") != "assistant":
                continue
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            first_line = content.splitlines()[0].strip()
            if first_line.startswith("Outcome:"):
                first_line = first_line.removeprefix("Outcome:").strip()
            outcomes.append(first_line[:500])
        return outcomes[-6:]

    def _resolved_system_prompt(self) -> str:
        """Build the effective system prompt for the current run/model."""
        if self._profile:
            system_prompt = self._system_prompt
        else:
            today = date.today()
            date_context = (
                f"Current date: {today.strftime('%B %d, %Y')}\n"
                f"Your knowledge cutoff: June 2024. For information after this date, use web_search."
            )
            system_prompt = self._system_prompt.format(date_context=date_context)
        return self._effective_system_prompt(system_prompt)

    def _update_working_memory_from_tools(
        self,
        memory: WorkingMemory,
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
    ) -> None:
        """Fold tool results into compact structured memory."""
        for tool_call, result in tool_results:
            summary = result.result_summary.strip()
            evidence = f"{tool_call.name}: {summary}"[:500]
            memory.recent_raw_evidence.append(evidence)
            memory.recent_raw_evidence = memory.recent_raw_evidence[-8:]
            if tool_call.name == "read_file":
                file_path = self._canonical_workspace_path(
                    str(tool_call.arguments.get("file_path", "unknown"))
                )
                excerpt = self._extract_read_file_excerpt(result.result_data)
                memory.files_inspected[file_path] = (
                    f"{summary}. Key excerpt: {excerpt}" if excerpt else summary
                )[:500]
                memory.current_hypothesis = f"Latest inspected file: {file_path}"
            elif tool_call.name in ("edit_file", "write_file"):
                file_path = self._canonical_workspace_path(
                    str(tool_call.arguments.get("file_path", "unknown"))
                )
                if result.success:
                    diff_summary = self._summarize_diff(result.result_data) or summary
                    memory.files_changed[file_path] = diff_summary[:500]
                    memory.current_hypothesis = f"Changed {file_path}"
            elif tool_call.name == "apply_patch":
                if result.success:
                    changed_files = []
                    if isinstance(result.result_data, dict):
                        changed_files = list(result.result_data.get("changed_files") or [])
                    diff_summary = self._summarize_diff(result.result_data) or summary
                    for file_path in changed_files:
                        canonical = self._canonical_workspace_path(str(file_path))
                        memory.files_changed[canonical] = diff_summary[:500]
                    if changed_files:
                        changed_preview = ", ".join(map(str, changed_files[:3]))
                        memory.current_hypothesis = f"Changed {changed_preview}"
            elif tool_call.name in {"bash", "exec_command", "write_stdin"}:
                memory.validation_results.append(summary[:500])
                diagnostics = self._extract_bash_diagnostics(result.result_data, summary)
                memory.validation_results.extend(item[:500] for item in diagnostics)
                command = str(
                    tool_call.arguments.get("command")
                    or tool_call.arguments.get("cmd")
                    or f"write_stdin session {tool_call.arguments.get('session_id', '')}"
                ).strip()
                if command:
                    memory.recent_commands.append(command[:500])
            else:
                discovery = self._summarize_discovery(tool_call, result)
                if discovery:
                    memory.recent_raw_evidence.append(discovery[:500])
        memory.validation_results = memory.validation_results[-8:]
        memory.recent_commands = memory.recent_commands[-8:]
        memory.recent_raw_evidence = memory.recent_raw_evidence[-8:]

    def _record_tool_call_recovery(
        self,
        memory: WorkingMemory,
        recovery_notes: List[str],
    ) -> None:
        """Persist malformed tool-call recovery state in durable memory."""
        if not recovery_notes:
            return
        memory.unresolved_tasks.extend(note[:500] for note in recovery_notes)
        memory.unresolved_tasks = memory.unresolved_tasks[-6:]
        memory.recent_raw_evidence.extend(note[:500] for note in recovery_notes)
        memory.recent_raw_evidence = memory.recent_raw_evidence[-8:]


    def _apply_patch_failure_contexts(
        self,
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
    ) -> List[Dict[str, Any]]:
        """Extract apply_patch failures that need patch-first recovery."""
        failures: List[Dict[str, Any]] = []
        for tool_call, result in tool_results:
            if tool_call.name != "apply_patch" or result.success:
                continue
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            error = str(result.error_message or result.result_summary or "")
            failure_type = self._apply_patch_failure_type(result)
            recoverable = metadata.get("failure_type") == "malformed_patch" or any(
                marker in error
                for marker in (
                    "Unexpected patch line",
                    "Malformed",
                    "has no hunks",
                    "Patch must",
                    "Patch hunk did not match",
                )
            )
            if recoverable:
                failures.append(
                    {
                        "error": error[:500],
                        "failure_type": failure_type,
                        "paths": [
                            self._canonical_workspace_path(path)
                            for path in self._extract_apply_patch_paths(
                                str(tool_call.arguments.get("patch", ""))
                            )
                        ],
                    }
                )
        return failures

    def _build_apply_patch_failure_recovery_messages(
        self,
        failures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build targeted recovery guidance after malformed apply_patch calls."""
        if not failures:
            return []
        errors = " | ".join(
            str(item.get("error") or "")[:180] for item in failures[:2]
        )
        has_hunk_mismatch = any(
            item.get("failure_type") == "hunk_mismatch" for item in failures
        )
        paths = sorted(
            {
                str(path)
                for item in failures[:3]
                for path in (item.get("paths") or [])
                if path
            }
        )
        reread_hint = (
            " First reread the exact affected file region"
            + (f" ({', '.join(paths[:3])})" if paths else "")
            + ", then retry a smaller apply_patch built from the fresh text."
            if has_hunk_mismatch
            else ""
        )
        return [
            {
                "role": "system",
                "content": (
                    "apply_patch recovery required. The previous patch failed "
                    f"before changing files: {errors}. Do not switch to edit_file or "
                    "write_file just because the patch did not apply. Retry with one "
                    "complete apply_patch call containing actual hunks."
                    f"{reread_hint} Valid examples:\n\n"
                    "*** Begin Patch\n"
                    "*** Update File: path/to/file\n"
                    "@@\n"
                    " old context line\n"
                    "-old line\n"
                    "+new line\n"
                    "*** End Patch\n\n"
                    "or:\n\n"
                    "*** Begin Patch\n"
                    "--- a/path/to/file\n"
                    "+++ b/path/to/file\n"
                    "@@ -1,2 +1,2 @@\n"
                    " old context line\n"
                    "-old line\n"
                    "+new line\n"
                    "*** End Patch\n\n"
                    "Never send placeholder-only patches such as `Update File: path` "
                    "with no hunks."
                ),
            }
        ]

    def _record_apply_patch_failure_recovery(
        self,
        memory: WorkingMemory,
        failures: List[Dict[str, Any]],
    ) -> None:
        """Persist apply_patch format recovery hints into working memory."""
        if not failures:
            return
        has_hunk_mismatch = any(
            failure.get("failure_type") == "hunk_mismatch" for failure in failures
        )
        memory.unresolved_tasks.append(
            (
                "Reread affected file region, then retry apply_patch with a smaller fresh hunk."
                if has_hunk_mismatch
                else "Retry apply_patch with a complete patch; previous patch was malformed."
            )
        )
        memory.recent_raw_evidence.append(
            (
                "apply_patch failed because a hunk did not match current file contents."
                if has_hunk_mismatch
                else "apply_patch failed due to malformed/placeholder patch syntax."
            )
        )
        memory.unresolved_tasks = memory.unresolved_tasks[-6:]
        memory.recent_raw_evidence = memory.recent_raw_evidence[-8:]

    def _edit_failure_contexts(
        self,
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
    ) -> List[Dict[str, Any]]:
        """Extract structured edit-match failures that need explicit recovery."""
        failures: List[Dict[str, Any]] = []
        for tool_call, result in tool_results:
            if tool_call.name != "edit_file" or result.success:
                continue
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            failure_type = metadata.get("match_failure_type")
            if failure_type not in {"not_found", "ambiguous"}:
                continue
            file_path = self._canonical_workspace_path(
                str(tool_call.arguments.get("file_path", "unknown"))
            )
            failures.append(
                {
                    "file_path": file_path,
                    "failure_type": failure_type,
                    "candidate_snippets": list(metadata.get("candidate_snippets") or [])[:3],
                }
            )
        return failures

    def _build_edit_failure_recovery_messages(
        self,
        failures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build targeted recovery guidance after edit matching failures."""
        if not failures:
            return []

        lines = []
        for failure in failures[:2]:
            reason = (
                "the target text was not found"
                if failure["failure_type"] == "not_found"
                else "the target text matched multiple locations"
            )
            snippet_hint = ""
            candidate_snippets = failure.get("candidate_snippets") or []
            if candidate_snippets:
                snippet_hint = " Candidate snippets: " + " || ".join(
                    snippet.replace("\n", " ")[:180] for snippet in candidate_snippets[:2]
                )
            lines.append(f"- {failure['file_path']}: {reason}.{snippet_hint}")

        return [
            {
                "role": "system",
                "content": (
                    "Edit recovery required. The file may have changed since the last read. "
                    "Reread the relevant file region before retrying edit_file, and do not repeat "
                    "the same edit arguments unchanged.\n"
                    + "\n".join(lines)
                ),
            }
        ]

    def _record_edit_failure_recovery(
        self,
        memory: WorkingMemory,
        failures: List[Dict[str, Any]],
    ) -> None:
        """Persist edit recovery hints into working memory."""
        if not failures:
            return
        for failure in failures:
            reason = (
                "reread before retrying edit_file; previous target was not found"
                if failure["failure_type"] == "not_found"
                else "reread before retrying edit_file; previous target was ambiguous"
            )
            memory.stale_file_summaries[failure["file_path"]] = reason
            memory.unresolved_tasks.append(
                f"edit_file recovery for {failure['file_path']}: {reason}"
            )
        memory.stale_file_summaries = self._merge_string_maps(
            {}, memory.stale_file_summaries, limit=8
        )
        memory.unresolved_tasks = memory.unresolved_tasks[-6:]

    def _tool_call_recovery_note(self, tool_call: ParsedToolCall) -> Optional[str]:
        """Return a recovery note when a tool call should not be replayed."""
        tool = self._registry.get(tool_call.name)
        if tool is None:
            return f"Previous tool call '{tool_call.name}' failed because the tool does not exist."

        if tool_call.parse_error:
            return (
                f"Previous tool call '{tool_call.name}' was invalid because {tool_call.parse_error}"
            )

        required_args = tool.schema.parameters.get("required", [])
        missing_args = [arg for arg in required_args if arg not in tool_call.arguments]
        if missing_args:
            missing = ", ".join(sorted(missing_args))
            return (
                f"Previous tool call '{tool_call.name}' was invalid because it was missing "
                f"required arguments: {missing}."
            )

        return None

    def _should_suppress_assistant_transcript_entry(
        self,
        *,
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
        recovery_notes: List[str],
    ) -> bool:
        """Return whether assistant prose for a tool step is structurally unsafe to replay."""
        if recovery_notes:
            return True
        return bool(tool_results) and all(not result.success for _, result in tool_results)

    def _canonical_replay_tool_calls(
        self,
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """Build safe assistant tool-call replay from parsed calls only."""
        replay_tool_calls: List[Dict[str, Any]] = []
        recovery_notes: List[str] = []
        for tool_call, _ in tool_results:
            recovery_note = self._tool_call_recovery_note(tool_call)
            if recovery_note:
                recovery_notes.append(recovery_note)
                continue
            replay_tool_calls.append(
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(
                            tool_call.arguments,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    },
                }
            )
        return replay_tool_calls, recovery_notes

    def _image_parts_from_tool_result(self, result: "ToolResult") -> List[Dict[str, Any]]:
        """Convert view_image result data into multimodal message parts."""
        data = result.result_data if isinstance(result.result_data, dict) else {}
        parts: List[Dict[str, Any]] = []
        for image in (data.get("images") or [])[:8]:
            data_url = image.get("data_url")
            if not data_url:
                continue
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                }
            )
        return parts

    def _available_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas valid for the active model/provider."""
        tool_schemas = self._registry.get_openai_schemas()
        if self._is_coding_profile() and self._apply_patch_failures:
            tool_schemas = [
                schema
                for schema in tool_schemas
                if schema.get("function", {}).get("name")
                not in {"edit_file", "write_file"}
            ]
        if bool(getattr(self._provider, "_supports_vision", False)):
            return tool_schemas
        return [
            schema
            for schema in tool_schemas
            if schema.get("function", {}).get("name") != "view_image"
        ]

    def _effective_system_prompt(self, system_prompt: str) -> str:
        """Remove capability-specific instructions that the active model cannot use."""
        if bool(getattr(self._provider, "_supports_vision", False)):
            return system_prompt
        return system_prompt.replace(
            "- Use `view_image` for workspace screenshots/images/charts/forms/diagrams when the user asks you to inspect images or visual content. Do not rely on OCR first unless exact text extraction is specifically needed.\n",
            "",
        )

    def _normalize_system_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge all system messages into one leading system message for strict providers."""
        system_parts: List[str] = []
        non_system_messages: List[Dict[str, Any]] = []
        for message in messages:
            if message.get("role") == "system":
                content = message.get("content")
                if content:
                    system_parts.append(str(content))
            else:
                non_system_messages.append(message)

        if not system_parts:
            return list(messages)

        return [
            {
                "role": "system",
                "content": "\n\n".join(system_parts),
            },
            *non_system_messages,
        ]

    def _extract_read_file_excerpt(self, result_data: Any) -> Optional[str]:
        """Extract a tiny code/text excerpt from read_file output."""
        if not isinstance(result_data, str):
            return None
        cleaned_lines = []
        for line in result_data.splitlines():
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                line = line.split("\t", 1)[1].strip()
            cleaned_lines.append(line)
            if len(cleaned_lines) >= 3:
                break
        if not cleaned_lines:
            return None
        excerpt = " | ".join(cleaned_lines)
        return excerpt[:240]

    def _summarize_diff(self, result_data: Any) -> Optional[str]:
        """Compress a diff into a short description."""
        if isinstance(result_data, dict):
            result_data = result_data.get("diff") or result_data.get("preview") or ""
        if not isinstance(result_data, str):
            return None
        additions = 0
        removals = 0
        preview: List[str] = []
        for line in result_data.splitlines():
            if line.startswith("+++ ") or line.startswith("--- ") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                additions += 1
                if len(preview) < 3:
                    preview.append(line[1:].strip())
            elif line.startswith("-"):
                removals += 1
        summary = f"{additions} additions, {removals} removals"
        if preview:
            summary += "; examples: " + " | ".join(item[:120] for item in preview)
        return summary

    def _extract_bash_diagnostics(self, result_data: Any, fallback: str) -> List[str]:
        """Keep only actionable bash diagnostics."""
        if not isinstance(result_data, dict):
            return [fallback]
        diagnostics: List[str] = []
        exit_code = result_data.get("exit_code")
        if exit_code is not None:
            diagnostics.append(f"exit_code={exit_code}")
        if result_data.get("timed_out"):
            diagnostics.append("command timed out")
        combined = "\n".join(
            part for part in [result_data.get("stderr"), result_data.get("stdout")] if part
        )
        for line in combined.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if (
                "error" in lowered
                or "warning" in lowered
                or "failed" in lowered
                or re.search(r":[0-9]+(?::[0-9]+)?", stripped)
            ):
                diagnostics.append(stripped[:240])
            if len(diagnostics) >= 6:
                break
        if not diagnostics:
            diagnostics.append(fallback)
        return diagnostics[:6]

    def _summarize_discovery(
        self,
        tool_call: ParsedToolCall,
        result: "ToolResult",
    ) -> Optional[str]:
        """Summarize grep/glob/listing results into a compact fact."""
        if tool_call.name == "grep":
            pattern = tool_call.arguments.get("pattern", "")
            path = tool_call.arguments.get("path", "")
            return f"grep '{pattern}' in {path or '.'}: {result.result_summary}"[:400]
        if tool_call.name == "glob":
            pattern = tool_call.arguments.get("pattern", "")
            return f"glob '{pattern}': {result.result_summary}"[:400]
        if tool_call.name == "list_directory":
            path = tool_call.arguments.get("path", "")
            return f"listed {path or '.'}: {result.result_summary}"[:400]
        return None

    def _is_coding_profile(self) -> bool:
        """Return whether the current agent profile is the coding profile."""
        return bool(self._profile and self._profile.name == "coding")

    async def _call_repo_async_method(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Call an optional async repo method when available."""
        method = getattr(self._repo, method_name, None)
        if method is None or not inspect.iscoroutinefunction(method):
            return None
        return await method(*args, **kwargs)

    def _dedupe_tail(self, items: List[str], limit: int) -> List[str]:
        """Keep only the most recent unique items."""
        seen: set[str] = set()
        deduped: List[str] = []
        for item in reversed([str(item).strip() for item in items if str(item).strip()]):
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item[:500])
        deduped.reverse()
        return deduped[-limit:]

    def _merge_string_maps(
        self,
        base: Dict[str, str],
        incoming: Dict[str, str],
        limit: Optional[int] = 32,
    ) -> Dict[str, str]:
        """Merge ordered string maps and keep the newest entries."""
        merged = dict(base)
        for key, value in incoming.items():
            clean_key = str(key).strip()
            clean_value = str(value).strip()
            if not clean_key or not clean_value:
                continue
            if clean_key in merged:
                merged.pop(clean_key)
            merged[clean_key] = clean_value[:500]
        if limit is None or len(merged) <= limit:
            return merged
        return dict(list(merged.items())[-limit:])

    def _strip_session_render_markers(self, summary: str) -> str:
        """Remove restore-only prefixes before persisting summaries again."""
        for prefix in ("[stored, fresh] ", "[stored summary] "):
            if summary.startswith(prefix):
                return summary[len(prefix) :]
        return summary

    def _canonical_workspace_path(self, file_path: str) -> str:
        """Normalize a workspace file path to a stable relative path when possible."""
        resolved = self._resolve_workspace_file(file_path)
        workspace_path = self._get_workspace_path()
        if resolved is None or workspace_path is None:
            return str(file_path)
        try:
            return str(resolved.relative_to(Path(workspace_path).resolve()))
        except ValueError:
            return str(file_path)

    def _extract_apply_patch_paths(self, patch: str) -> List[str]:
        """Best-effort target path extraction from model-supplied patch text."""
        paths: List[str] = []
        previous_unified_old: Optional[str] = None

        def add_path(raw_path: str) -> None:
            clean = raw_path.strip()
            if not clean or clean == "/dev/null":
                return
            if "\t" in clean:
                clean = clean.split("\t", 1)[0].strip()
            if clean.startswith(("a/", "b/")):
                clean = clean[2:]
            if clean and clean not in paths:
                paths.append(clean)

        for raw_line in str(patch or "").splitlines():
            line = raw_line.strip()
            stripped = line.lstrip("*").strip()

            for prefix in ("Update File:", "Add File:", "Delete File:"):
                if stripped.startswith(prefix):
                    add_path(stripped[len(prefix) :])
                    previous_unified_old = None
                    break
            else:
                if stripped.startswith("Move to:"):
                    add_path(stripped[len("Move to:") :])
                    previous_unified_old = None
                elif line.startswith("--- "):
                    old_path = line[4:].strip()
                    previous_unified_old = old_path
                    add_path(old_path)
                elif line.startswith("+++ "):
                    new_path = line[4:].strip()
                    if new_path != "/dev/null":
                        add_path(new_path)
                    elif previous_unified_old:
                        add_path(previous_unified_old)
                    previous_unified_old = None

        return paths

    def _apply_patch_failure_type(self, result: "ToolResult") -> str:
        """Classify apply_patch failure so recovery can steer the next action."""
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        if metadata.get("failure_type") == "malformed_patch":
            return "malformed_patch"
        error = str(result.error_message or result.result_summary or "")
        lowered = error.lower()
        if "hunk did not match" in lowered or "current contents" in lowered:
            return "hunk_mismatch"
        if "outside working directory" in lowered or "path" in lowered and "outside" in lowered:
            return "path_rejected"
        return "patch_failed"

    def _track_file_freshness(
        self,
        tool_call: ParsedToolCall,
        result: "ToolResult",
    ) -> Dict[str, Any]:
        """Update per-file freshness state for edit recovery."""
        if tool_call.name not in {"read_file", "edit_file", "write_file", "apply_patch"}:
            return {}

        if tool_call.name == "apply_patch":
            payload: Dict[str, Any] = {}
            changed_files: List[str] = []
            if result.success:
                if isinstance(result.result_data, dict):
                    changed_files = [
                        self._canonical_workspace_path(str(path))
                        for path in result.result_data.get("changed_files") or []
                    ]
                if not changed_files:
                    metadata = result.metadata if isinstance(result.metadata, dict) else {}
                    changed_files = [
                        self._canonical_workspace_path(str(path))
                        for path in metadata.get("changed_files") or []
                    ]
                for changed_file in changed_files:
                    self._file_state_versions[changed_file] = (
                        self._file_state_versions.get(changed_file, 0) + 1
                    )
                    self._apply_patch_failures.pop(changed_file, None)
                if changed_files:
                    self._apply_patch_failures.pop("__global__", None)
                    payload["changed_files"] = changed_files
                    payload["file_state_versions_after"] = {
                        path: self._file_state_versions.get(path, 0)
                        for path in changed_files
                    }
                return payload

            patch_paths = [
                self._canonical_workspace_path(path)
                for path in self._extract_apply_patch_paths(
                    str(tool_call.arguments.get("patch", ""))
                )
            ]
            if not patch_paths:
                patch_paths = ["__global__"]
            failure_type = self._apply_patch_failure_type(result)
            for patch_path in patch_paths:
                self._apply_patch_failures[patch_path] = {
                    "arguments": dict(tool_call.arguments),
                    "failure_type": failure_type,
                    "error": str(result.error_message or result.result_summary or "")[:500],
                    "file_read_sequence_at_failure": self._file_last_read_sequences.get(
                        patch_path, 0
                    ),
                    "file_state_version_at_failure": self._file_state_versions.get(
                        patch_path, 0
                    ),
                }
            payload["file_paths"] = patch_paths
            payload["failure_type"] = failure_type
            return payload

        file_path = str(tool_call.arguments.get("file_path", "")).strip()
        if not file_path:
            return {}

        canonical_path = self._canonical_workspace_path(file_path)
        payload: Dict[str, Any] = {"file_path": canonical_path}

        if tool_call.name == "read_file" and result.success:
            self._file_read_sequence += 1
            file_state_version = self._file_state_versions.get(canonical_path, 0)
            self._file_last_read_state_versions[canonical_path] = file_state_version
            self._file_last_read_sequences[canonical_path] = self._file_read_sequence
            payload["file_state_version_after"] = file_state_version
            payload["file_read_sequence_after"] = self._file_read_sequence
            return payload

        payload["file_state_version_before"] = self._file_state_versions.get(canonical_path, 0)
        payload["file_read_sequence_before"] = self._file_last_read_sequences.get(canonical_path, 0)

        if tool_call.name in {"edit_file", "write_file"} and result.success:
            self._file_state_versions[canonical_path] = (
                self._file_state_versions.get(canonical_path, 0) + 1
            )

        payload["file_state_version_after"] = self._file_state_versions.get(canonical_path, 0)

        if tool_call.name == "edit_file":
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            failure_type = metadata.get("match_failure_type")
            if result.success:
                self._edit_failures.pop(canonical_path, None)
            elif failure_type in {"not_found", "ambiguous"}:
                self._edit_failures[canonical_path] = {
                    "arguments": dict(tool_call.arguments),
                    "failure_type": failure_type,
                    "candidate_snippets": list(metadata.get("candidate_snippets") or [])[:3],
                    "file_read_sequence_at_failure": self._file_last_read_sequences.get(
                        canonical_path, 0
                    ),
                    "file_state_version_at_failure": self._file_state_versions.get(
                        canonical_path, 0
                    ),
                }

        return payload

    def _has_reread_since_edit_failure(self, file_path: str) -> bool:
        """Return whether the file was reread after the latest tracked edit failure."""
        failure = self._edit_failures.get(file_path)
        if not failure:
            return False
        return self._file_last_read_sequences.get(file_path, 0) > int(
            failure.get("file_read_sequence_at_failure", 0)
        )

    def _apply_patch_failure_for_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Return unresolved apply_patch failure for a file, falling back to global."""
        return self._apply_patch_failures.get(file_path) or self._apply_patch_failures.get(
            "__global__"
        )

    def _resolve_workspace_file(self, file_path: str) -> Optional[Path]:
        """Resolve a workspace file using tool resolvers when available."""
        for tool_name in ("read_file", "write_file", "edit_file", "apply_patch", "view_image"):
            tool = self._registry.get(tool_name)
            resolver = getattr(tool, "_resolve_path", None)
            if callable(resolver):
                try:
                    resolved = resolver(file_path)
                except Exception:
                    continue
                if resolved is not None:
                    return Path(resolved)
        workspace_path = self._get_workspace_path()
        if not workspace_path:
            return None
        try:
            base = Path(workspace_path).resolve()
            path = Path(file_path)
            if not path.is_absolute():
                path = base / path
            resolved = path.resolve()
            if resolved.is_relative_to(base):
                return resolved
        except Exception:
            return None
        return None

    def _hash_file_contents(self, path: Path) -> Optional[str]:
        """Compute a stable hash for a workspace file."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

    def _excerpt_from_file(
        self,
        path: Path,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
    ) -> Optional[str]:
        """Extract a compact excerpt from a file on disk."""
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        if line_start and line_end and line_start > 0:
            selected = lines[line_start - 1 : line_end]
        else:
            selected = lines
        cleaned: List[str] = []
        for line in selected:
            stripped = line.strip()
            if not stripped:
                continue
            cleaned.append(stripped)
            if len(cleaned) >= 3:
                break
        if not cleaned:
            return None
        return " | ".join(cleaned)[:240]

    def _read_file_line_span(
        self,
        tool_call: ParsedToolCall,
        result: "ToolResult",
    ) -> tuple[Optional[int], Optional[int]]:
        """Derive the stored line span for a read_file result."""
        if isinstance(result.metadata, dict):
            metadata_start = result.metadata.get("line_start")
            metadata_end = result.metadata.get("line_end")
            if isinstance(metadata_start, int):
                return metadata_start, metadata_end if isinstance(metadata_end, int) else None

        offset = tool_call.arguments.get("offset", 1)
        try:
            line_start = max(1, int(offset))
        except (TypeError, ValueError):
            line_start = 1
        lines_read = result.metadata.get("lines_read") if isinstance(result.metadata, dict) else None
        if isinstance(lines_read, int) and lines_read > 0:
            return line_start, line_start + lines_read - 1
        return line_start, None

    def _build_file_state_from_read(
        self,
        tool_call: ParsedToolCall,
        result: "ToolResult",
        run_id: str,
    ) -> Optional[CodingFileState]:
        """Create persisted file evidence from a successful read_file call."""
        if not result.success:
            return None
        file_path = self._canonical_workspace_path(
            str(tool_call.arguments.get("file_path", "unknown"))
        )
        line_start, line_end = self._read_file_line_span(tool_call, result)
        resolved = self._resolve_workspace_file(file_path)
        excerpt = self._extract_read_file_excerpt(result.result_data)
        if excerpt is None and resolved is not None:
            excerpt = self._excerpt_from_file(resolved, line_start, line_end)
        file_state = CodingFileState(
            path=file_path,
            summary=result.result_summary[:1500],
            content_hash=self._hash_file_contents(resolved) if resolved else None,
            source="read_file",
            captured_at=datetime.now(timezone.utc).isoformat(),
            last_read_run_id=run_id,
        )
        file_state.add_span(
            line_start=line_start,
            line_end=line_end,
            excerpt=excerpt,
            reason="read",
        )
        return file_state

    def _build_file_state_from_write(
        self,
        tool_call: ParsedToolCall,
        result: "ToolResult",
        run_id: str,
    ) -> Optional[CodingFileState]:
        """Create persisted file evidence from a successful edit/write call."""
        if not result.success:
            return None
        file_path = self._canonical_workspace_path(
            str(tool_call.arguments.get("file_path", "unknown"))
        )
        resolved = self._resolve_workspace_file(file_path)
        excerpt = self._excerpt_from_file(resolved) if resolved else None
        summary = self._summarize_diff(result.result_data) or result.result_summary
        file_state = CodingFileState(
            path=file_path,
            summary=summary[:1500],
            content_hash=self._hash_file_contents(resolved) if resolved else None,
            source=tool_call.name,
            captured_at=datetime.now(timezone.utc).isoformat(),
            last_modified_run_id=run_id,
        )
        file_state.add_span(
            line_start=None,
            line_end=None,
            excerpt=excerpt,
            reason="edit-context",
        )
        return file_state

    def _merge_working_memory_into_coding_session(
        self,
        session_state: CodingSessionState,
        working_memory: WorkingMemory,
    ) -> None:
        """Fold neutral coding metadata into durable coding-session state."""
        if working_memory.objective:
            session_state.objective = working_memory.objective
        session_state.recent_commands = list(
            dict.fromkeys(session_state.recent_commands + working_memory.recent_commands)
        )
        session_state.normalize()

    def _merge_tool_results_into_coding_session(
        self,
        session_state: CodingSessionState,
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
        run_id: str,
    ) -> None:
        """Persist concrete file evidence from the current tool step."""
        for tool_call, result in tool_results:
            file_state: Optional[CodingFileState] = None
            if tool_call.name == "read_file":
                session_state.note_read_file(
                    self._canonical_workspace_path(
                        str(tool_call.arguments.get("file_path", "unknown"))
                    )
                )
                file_state = self._build_file_state_from_read(tool_call, result, run_id)
            elif tool_call.name in ("edit_file", "write_file"):
                file_path = self._canonical_workspace_path(
                    str(tool_call.arguments.get("file_path", "unknown"))
                )
                session_state.note_modified_file(file_path)
                file_state = self._build_file_state_from_write(tool_call, result, run_id)
            elif tool_call.name == "apply_patch":
                changed_files = []
                if result.success and isinstance(result.result_data, dict):
                    changed_files = list(result.result_data.get("changed_files") or [])
                for changed_file in changed_files:
                    file_path = self._canonical_workspace_path(str(changed_file))
                    session_state.note_modified_file(file_path)
                    resolved = self._resolve_workspace_file(file_path)
                    if resolved and resolved.exists() and resolved.is_file():
                        patch_state = CodingFileState(
                            path=file_path,
                            summary=(
                                self._summarize_diff(result.result_data)
                                or result.result_summary
                            )[:1500],
                            content_hash=self._hash_file_contents(resolved),
                            source=tool_call.name,
                            captured_at=datetime.now(timezone.utc).isoformat(),
                            last_modified_run_id=run_id,
                        )
                        patch_state.add_span(
                            line_start=None,
                            line_end=None,
                            excerpt=self._excerpt_from_file(resolved),
                            reason="patch-context",
                        )
                        existing = session_state.file_evidence.get(file_path)
                        if existing is not None:
                            existing.summary = patch_state.summary or existing.summary
                            existing.content_hash = patch_state.content_hash or existing.content_hash
                            existing.source = patch_state.source or existing.source
                            existing.captured_at = patch_state.captured_at or existing.captured_at
                            existing.last_modified_run_id = patch_state.last_modified_run_id
                            for span in patch_state.spans:
                                existing.add_span(
                                    line_start=span.line_start,
                                    line_end=span.line_end,
                                    excerpt=span.excerpt,
                                    reason=span.reason,
                                )
                        else:
                            session_state.file_evidence[file_path] = patch_state
            elif tool_call.name in {"bash", "exec_command", "write_stdin"}:
                command = str(
                    tool_call.arguments.get("command")
                    or tool_call.arguments.get("cmd")
                    or f"write_stdin session {tool_call.arguments.get('session_id', '')}"
                ).strip()
                if command:
                    session_state.recent_commands.append(command[:500])
            if file_state is None:
                continue
            existing = session_state.file_evidence.get(file_state.path)
            if existing is not None:
                existing.summary = file_state.summary or existing.summary
                existing.content_hash = file_state.content_hash or existing.content_hash
                existing.source = file_state.source or existing.source
                existing.captured_at = file_state.captured_at or existing.captured_at
                existing.last_read_run_id = (
                    file_state.last_read_run_id or existing.last_read_run_id
                )
                existing.last_modified_run_id = (
                    file_state.last_modified_run_id or existing.last_modified_run_id
                )
                for span in file_state.spans:
                    existing.add_span(
                        line_start=span.line_start,
                        line_end=span.line_end,
                        excerpt=span.excerpt,
                        reason=span.reason,
                    )
            else:
                session_state.file_evidence[file_state.path] = file_state
        session_state.normalize()

    def _stored_file_summary(
        self,
        file_state: CodingFileState,
    ) -> str:
        """Format stored file evidence for working-memory rendering."""
        parts = [file_state.summary]
        latest_span = file_state.spans[-1] if file_state.spans else None
        if latest_span and latest_span.line_start and latest_span.line_end:
            parts.append(f"lines {latest_span.line_start}-{latest_span.line_end}")
        excerpt = file_state.latest_excerpt()
        if excerpt:
            parts.append(f"Stored excerpt: {excerpt}")
        return ". ".join(part for part in parts if part)[:500]

    def _assess_file_freshness(
        self,
        file_state: CodingFileState,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check whether persisted file evidence can be reused as-is."""
        resolved = self._resolve_workspace_file(file_state.path)
        if resolved is None:
            return True, None, "freshness not revalidated; workspace file resolver unavailable"
        if not resolved.exists():
            return False, "missing_evidence", "file is missing from the workspace"
        if file_state.content_hash is None:
            return True, None, "freshness not revalidated; no stored file hash"
        current_hash = self._hash_file_contents(resolved)
        if current_hash != file_state.content_hash:
            return (
                False,
                "stale_hash",
                "file content changed since the stored evidence was captured",
            )
        return True, None, None

    async def _load_coding_session_state_record(
        self,
        conversation_id: str,
    ) -> tuple[Optional[dict[str, Any]], Optional[CodingSessionState]]:
        """Load persisted coding-session state for a conversation."""
        record = await self._call_repo_async_method(
            "get_coding_session_state", conversation_id
        )
        if not isinstance(record, dict):
            return None, None
        return record, CodingSessionState.from_dict(record.get("state") or {})

    async def _hydrate_working_memory_from_coding_session(
        self,
        *,
        conversation_id: str,
        session_state: CodingSessionState,
        working_memory: WorkingMemory,
        run_id: str,
        updated_at: Optional[str] = None,
    ) -> None:
        """Restore persisted coding-session state into working memory."""
        working_memory.restored_session = True
        if updated_at:
            working_memory.restored_session_updated_at = str(updated_at)
        working_memory.recent_commands = self._dedupe_tail(
            session_state.recent_commands + working_memory.recent_commands,
            12,
        )

        reused_files: List[str] = []
        stale_files: Dict[str, str] = {}
        for path in session_state.read_files:
            file_state = session_state.file_evidence.get(path)
            if file_state is None:
                stale_files[path] = "Stored read history exists but no concrete evidence spans remain."
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reread",
                    content={
                        "conversation_id": conversation_id,
                        "path": path,
                        "reason": "missing_evidence",
                        "detail": stale_files[path],
                    },
                    actor="system",
                )
                continue
            is_fresh, reason_code, detail = self._assess_file_freshness(file_state)
            if is_fresh:
                working_memory.files_inspected[path] = (
                    f"[stored, fresh] {self._stored_file_summary(file_state)}"
                )[:500]
                reused_files.append(path)
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reuse",
                    content={
                        "conversation_id": conversation_id,
                        "path": path,
                        "source": file_state.source,
                        "line_spans": [
                            {
                                "line_start": span.line_start,
                                "line_end": span.line_end,
                                "reason": span.reason,
                            }
                            for span in file_state.spans
                        ],
                    },
                    actor="system",
                )
            else:
                stale_files[path] = detail or "Stored evidence is stale."
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reread",
                    content={
                        "conversation_id": conversation_id,
                        "path": path,
                        "reason": reason_code or "missing_evidence",
                        "detail": detail,
                    },
                    actor="system",
                )

        for path in session_state.modified_files:
            file_state = session_state.file_evidence.get(path)
            if file_state is None:
                stale_files[path] = "Stored edit history exists but no concrete evidence spans remain."
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reread",
                    content={
                        "conversation_id": conversation_id,
                        "path": path,
                        "reason": "missing_evidence",
                        "detail": stale_files[path],
                    },
                    actor="system",
                )
                continue
            is_fresh, reason_code, detail = self._assess_file_freshness(file_state)
            if is_fresh:
                working_memory.files_changed[path] = (
                    f"[stored, fresh] {self._stored_file_summary(file_state)}"
                )[:500]
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reuse",
                    content={
                        "conversation_id": conversation_id,
                        "path": path,
                        "source": file_state.source,
                        "line_spans": [
                            {
                                "line_start": span.line_start,
                                "line_end": span.line_end,
                                "reason": span.reason,
                            }
                            for span in file_state.spans
                        ],
                    },
                    actor="system",
                )
            else:
                stale_files[path] = detail or "Stored evidence is stale."
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reread",
                    content={
                        "conversation_id": conversation_id,
                        "path": path,
                        "reason": reason_code or "missing_evidence",
                        "detail": detail,
                    },
                    actor="system",
                )

        working_memory.stale_file_summaries = self._merge_string_maps(
            working_memory.stale_file_summaries,
            stale_files,
            limit=64,
        )

    def _coding_context_builder(self) -> CodingSessionContextBuilder:
        """Return the coding-session prompt builder."""
        from orchestrator.utils.tokens import get_token_counter

        return CodingSessionContextBuilder(
            token_counter=get_token_counter(),
            max_context_tokens=self._max_context_tokens,
            reserve_for_response=self._max_tokens,
        )

    def _has_coding_session_state(self, session_state: Optional[CodingSessionState]) -> bool:
        """Return whether a session state contains meaningful durable data."""
        if session_state is None:
            return False
        return bool(
            session_state.objective
            or session_state.read_files
            or session_state.modified_files
            or session_state.file_evidence
            or session_state.recent_commands
        )

    def _message_token_estimate(
        self,
        role: str,
        content_json: dict[str, Any],
    ) -> int:
        """Estimate token cost for a persisted replay entry."""
        from orchestrator.utils.tokens import get_token_counter

        text = json.dumps({"role": role, **content_json}, ensure_ascii=False)
        return get_token_counter().count_tokens(text) + 4

    async def _append_coding_session_entries(
        self,
        *,
        conversation_id: str,
        run_id: str,
        entries: List[dict[str, Any]],
        step_number: Optional[int] = None,
    ) -> List[CodingSessionEntry]:
        """Append normalized coding-session entries and trace the append."""
        stored = await self._call_repo_async_method(
            "append_coding_session_entries",
            conversation_id,
            entries,
        )
        if not isinstance(stored, list):
            return []
        appended = [CodingSessionEntry.from_dict(entry) for entry in stored]
        if appended:
            await self._add_trace_event(
                run_id=run_id,
                event_type="coding_session_entry_append",
                content={
                    "conversation_id": conversation_id,
                    "count": len(appended),
                    "seq_start": appended[0].seq,
                    "seq_end": appended[-1].seq,
                    "entry_types": [entry.entry_type for entry in appended],
                },
                actor="system",
                step_number=step_number,
            )
        return appended

    async def _persist_coding_session_user_message(
        self,
        *,
        conversation_id: str,
        run_id: str,
        session_state: CodingSessionState,
        user_content: Any,
    ) -> None:
        """Persist the current user turn as a replayable session entry."""
        entry = {
            "run_id": run_id,
            "step_number": 0,
            "entry_type": "user",
            "role": "user",
            "content_json": {"content": user_content},
            "token_estimate": self._message_token_estimate(
                "user",
                {"content": user_content},
            ),
        }
        await self._append_coding_session_entries(
            conversation_id=conversation_id,
            run_id=run_id,
            entries=[entry],
            step_number=0,
        )
        session_state.normalize()

    async def _persist_coding_session_step_entries(
        self,
        *,
        conversation_id: str,
        run_id: str,
        step_number: int,
        assistant_content: Optional[str],
        tool_results: List[tuple[ParsedToolCall, "ToolResult"]],
    ) -> None:
        """Persist normalized assistant/tool history for a coding step."""
        entries: List[dict[str, Any]] = []
        clean_content = assistant_content.strip() if assistant_content else ""
        replay_tool_calls, recovery_notes = self._canonical_replay_tool_calls(tool_results)
        suppress_assistant_replay = self._should_suppress_assistant_transcript_entry(
            tool_results=tool_results,
            recovery_notes=recovery_notes,
        )
        self._coding_last_step_structural_failure = suppress_assistant_replay
        if clean_content:
            entries.append(
                {
                    "run_id": run_id,
                    "step_number": step_number,
                    "entry_type": "assistant",
                    "role": "assistant",
                    "content_json": {
                        "content": clean_content,
                        "replay_eligible": not suppress_assistant_replay,
                    },
                    "token_estimate": self._message_token_estimate(
                        "assistant",
                        {"content": clean_content},
                    ),
                }
            )

        if replay_tool_calls:
            content_json = {
                "content": clean_content,
                "tool_calls": replay_tool_calls,
                "replay_eligible": True,
            }
            entries.append(
                {
                    "run_id": run_id,
                    "step_number": step_number,
                    "entry_type": "assistant_tool_calls",
                    "role": "assistant",
                    "content_json": content_json,
                    "token_estimate": self._message_token_estimate("assistant", content_json),
                }
            )

        for tool_call, result in tool_results:
            recovery_note = self._tool_call_recovery_note(tool_call)
            content_json = {
                "tool_call_id": tool_call.id,
                "name": tool_call.name,
                "content": self._format_tool_result(result, tool_call.name),
                "success": result.success,
                "replay_eligible": True,
            }
            if recovery_note:
                content_json["recovery_note"] = (
                    "Previous tool call was invalid and failed. "
                    + recovery_note
                    + " Continue from the current state. Do not repeat malformed or incomplete tool arguments."
                )
            entries.append(
                {
                    "run_id": run_id,
                    "step_number": step_number,
                    "entry_type": "tool_result",
                    "role": "tool",
                    "content_json": content_json,
                    "token_estimate": self._message_token_estimate("tool", content_json),
                }
            )

        if entries:
            await self._append_coding_session_entries(
                conversation_id=conversation_id,
                run_id=run_id,
                entries=entries,
                step_number=step_number,
            )

    async def _persist_coding_session_final_answer(
        self,
        *,
        conversation_id: str,
        run_id: str,
        step_number: int,
        final_answer: str,
        replay_eligible: bool = True,
    ) -> None:
        """Persist the final assistant answer as a replayable session entry."""
        clean_answer = final_answer.strip()
        if not clean_answer:
            return
        await self._append_coding_session_entries(
            conversation_id=conversation_id,
            run_id=run_id,
            entries=[
                {
                    "run_id": run_id,
                    "step_number": step_number,
                    "entry_type": "assistant",
                    "role": "assistant",
                    "content_json": {
                        "content": clean_answer,
                        "replay_eligible": replay_eligible,
                    },
                    "token_estimate": self._message_token_estimate(
                        "assistant",
                        {"content": clean_answer},
                    ),
                }
            ],
            step_number=step_number,
        )

    async def _build_coding_session_context_from_entries(
        self,
        *,
        conversation_id: str,
        system_prompt: str,
        query: str,
        session_state: CodingSessionState,
        working_memory: Optional[WorkingMemory] = None,
        transcript_entries: Optional[List[CodingSessionEntry]] = None,
    ) -> tuple[
        List[Dict[str, Any]],
        ContextBudget,
        List[CodingSessionEntry],
        Dict[str, Any],
        Dict[str, Any],
    ]:
        """Build coding prompt context plus observability payloads from transcript entries."""
        if transcript_entries is None:
            entry_records = await self._call_repo_async_method(
                "list_coding_session_entries",
                conversation_id,
                include_compacted=False,
            )
            transcript_entries = [
                CodingSessionEntry.from_dict(entry)
                for entry in (entry_records or [])
            ]
        builder = self._coding_context_builder()
        metadata_message = (
            working_memory.render_coding_metadata()
            if working_memory is not None
            else None
        )
        restored_file_messages = self._build_restored_file_messages(
            session_state=session_state,
            transcript_entries=transcript_entries,
            current_query=query,
        )
        context = builder.build(
            system_prompt=system_prompt,
            session_state=session_state,
            transcript_entries=transcript_entries,
            current_query=query,
            metadata_message=metadata_message,
            restored_file_messages=restored_file_messages,
        )
        stored_context = builder.build_stored_context(
            session_state=session_state,
            transcript_entries=transcript_entries,
            metadata_message=metadata_message,
            restored_file_messages=restored_file_messages,
        )
        stored_payload = self._stored_context_usage_payload(
            stored_tokens=stored_context.token_count,
            replayable_entry_count=stored_context.replayable_entry_count,
        )
        self._last_stored_context = stored_payload
        context_payload = {
            "conversation_id": conversation_id,
            "transcript_source": "coding_session_entries",
            "used_session_entries": context.used_session_entries,
            "metadata_included": context.metadata_included,
            "replayed_entry_count": context.replayed_entry_count,
            "message_count": len(context.messages),
            "prompt_tokens": builder.estimate_tokens(context.messages),
            "stored_context_tokens": stored_context.token_count,
            "checkpoint_present": context.checkpoint_present,
            "preserved_tail_count": context.preserved_tail_count,
            "restored_file_count": context.restored_file_count,
            "replay_source_ranges": context.replay_source_ranges,
        }
        return (
            context.messages,
            context.budget,
            transcript_entries,
            stored_payload,
            context_payload,
        )

    async def _load_coding_session_messages(
        self,
        *,
        conversation_id: str,
        system_prompt: str,
        query: str,
        run_id: str,
        session_state: CodingSessionState,
        working_memory: Optional[WorkingMemory] = None,
        use_session_entries: bool = True,
    ) -> tuple[List[Dict[str, Any]], ContextBudget]:
        """Build coding prompt context from transcript entries plus neutral metadata."""
        transcript_entries: List[CodingSessionEntry] = []
        if use_session_entries:
            (
                messages,
                budget,
                transcript_entries,
                _,
                context_payload,
            ) = await self._build_coding_session_context_from_entries(
                conversation_id=conversation_id,
                system_prompt=system_prompt,
                query=query,
                session_state=session_state,
                working_memory=working_memory,
            )
        else:
            builder = self._coding_context_builder()
            context = builder.build(
                system_prompt=system_prompt,
                session_state=session_state,
                transcript_entries=[],
                current_query=query,
                metadata_message=working_memory.render_coding_metadata() if working_memory else None,
                restored_file_messages=[],
            )
            messages = context.messages
            budget = context.budget
            context_payload = {
                "conversation_id": conversation_id,
                "transcript_source": "coding_session_entries",
                "used_session_entries": False,
                "metadata_included": context.metadata_included,
                "replayed_entry_count": context.replayed_entry_count,
                "message_count": len(context.messages),
                "prompt_tokens": builder.estimate_tokens(context.messages),
                "stored_context_tokens": 0,
                "checkpoint_present": False,
                "preserved_tail_count": 0,
                "restored_file_count": 0,
                "replay_source_ranges": context.replay_source_ranges,
            }
        await self._add_trace_event(
            run_id=run_id,
            event_type="coding_session_context_load",
            content={
                **context_payload,
                **self._coding_prompt_pressure_metrics(context_payload["prompt_tokens"]),
                "context_phase": "raw_replay",
                "reduction_stage": "stage0_full_raw_replay",
                "checkpoint_fallback_activated": False,
                "raw_replay_counts": self._coding_replay_counts(
                    transcript_entries,
                    messages,
                ),
            },
            actor="system",
        )
        return messages, budget

    def _group_entries_by_turn(
        self,
        entries: List[CodingSessionEntry],
    ) -> List[Dict[str, Any]]:
        """Group replay entries into coding turns starting at user messages."""
        groups: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for entry in entries:
            if entry.entry_type == "user" or current is None:
                if current is not None:
                    groups.append(current)
                current = {
                    "start_seq": entry.seq,
                    "end_seq": entry.seq,
                    "entries": [entry],
                    "token_estimate": entry.token_estimate,
                }
            else:
                current["entries"].append(entry)
                current["end_seq"] = entry.seq
                current["token_estimate"] += entry.token_estimate
        if current is not None:
            groups.append(current)
        return groups

    def _is_coding_compaction_summary_entry(self, entry: CodingSessionEntry) -> bool:
        """Return whether an entry is a replayable coding compaction checkpoint."""
        return (
            entry.entry_type == "compaction_summary"
            and entry.content_json.get("replay_eligible", True) is not False
        )

    def _latest_coding_checkpoint_entry(
        self,
        entries: List[CodingSessionEntry],
    ) -> Optional[CodingSessionEntry]:
        """Return the latest replayable coding checkpoint entry if present."""
        for entry in reversed(entries):
            if self._is_coding_compaction_summary_entry(entry):
                return entry
        return None

    def _tail_entries_after_checkpoint(
        self,
        entries: List[CodingSessionEntry],
    ) -> List[CodingSessionEntry]:
        """Return uncompacted tail entries after the latest checkpoint."""
        checkpoint = self._latest_coding_checkpoint_entry(entries)
        if checkpoint is None:
            return [entry for entry in entries if not self._is_coding_compaction_summary_entry(entry)]
        return [
            entry
            for entry in entries
            if entry.seq > checkpoint.seq and not self._is_coding_compaction_summary_entry(entry)
        ]

    def _checkpoint_summary_state(
        self,
        entry: Optional[CodingSessionEntry],
    ) -> dict[str, Any]:
        """Return structured summary state from a stored checkpoint entry."""
        if entry is None:
            return {}
        state = entry.content_json.get("summary_state")
        return state if isinstance(state, dict) else {}

    def _entry_text_blob(self, entry: CodingSessionEntry) -> str:
        """Return normalized free-text content for an entry."""
        parts: List[str] = []
        content = entry.content_json.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content)
        tool_calls = entry.content_json.get("tool_calls") or []
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                if isinstance(function, dict):
                    name = function.get("name")
                    arguments = function.get("arguments")
                    if name:
                        parts.append(str(name))
                    if arguments:
                        parts.append(str(arguments))
        return "\n".join(parts)

    def _entry_file_paths(
        self,
        entry: CodingSessionEntry,
        known_paths: Optional[List[str]] = None,
    ) -> List[str]:
        """Extract workspace file paths referenced by a coding entry."""
        explicit: List[str] = []
        tool_calls = entry.content_json.get("tool_calls") or []
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                if not isinstance(function, dict):
                    continue
                arguments = function.get("arguments")
                parsed_arguments: Dict[str, Any] = {}
                if isinstance(arguments, str):
                    try:
                        candidate = json.loads(arguments)
                        if isinstance(candidate, dict):
                            parsed_arguments = candidate
                    except json.JSONDecodeError:
                        parsed_arguments = {}
                elif isinstance(arguments, dict):
                    parsed_arguments = arguments
                file_path = parsed_arguments.get("file_path")
                if file_path:
                    explicit.append(self._canonical_workspace_path(str(file_path)))
        if entry.entry_type == "tool_result":
            content = str(entry.content_json.get("content") or "")
            match = re.search(r"(?:from|to)\s+([^\s\(\[]+\.[A-Za-z0-9_./-]+)", content)
            if match:
                explicit.append(self._canonical_workspace_path(match.group(1)))

        explicit = list(dict.fromkeys(path for path in explicit if path))
        if explicit or not known_paths:
            return explicit

        blob = self._entry_text_blob(entry)
        return [path for path in known_paths if path and path in blob]

    def _coerce_string_list(self, value: Any) -> List[str]:
        """Normalize a stored summary list field."""
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _dedupe_summary_items(self, items: List[str], limit: int = 10) -> List[str]:
        """Keep recent unique summary bullets."""
        deduped: List[str] = []
        seen: set[str] = set()
        for item in items:
            clean = str(item).strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            deduped.append(clean[:500])
        if len(deduped) <= limit:
            return deduped
        return deduped[-limit:]

    def _extract_constraint_preferences(self, text: str) -> List[str]:
        """Extract explicit user constraints/preferences from a user message."""
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        constraints: List[str] = []
        for sentence in sentences:
            clean = sentence.strip(" -")
            lowered = clean.lower()
            if not clean:
                continue
            if any(
                marker in lowered
                for marker in (
                    "do not",
                    "don't",
                    "must",
                    "should",
                    "keep",
                    "preserve",
                    "use ",
                    "same branch",
                    "follow",
                )
            ):
                constraints.append(clean[:500])
        return constraints[:4]

    def _entry_summary_bullet(self, entry: CodingSessionEntry) -> Optional[str]:
        """Summarize one compacted entry into a grounded checkpoint bullet."""
        if entry.entry_type == "user":
            content = str(entry.content_json.get("content") or "").strip()
            if content:
                return f"User asked: {content[:400]}"
            return None
        if entry.entry_type == "assistant":
            content = str(entry.content_json.get("content") or "").strip()
            if content:
                return f"Assistant reported: {content[:400]}"
            return None
        if entry.entry_type == "assistant_tool_calls":
            paths = self._entry_file_paths(entry)
            if paths:
                return f"Started tool work touching: {', '.join(paths[:4])}"
            tool_calls = entry.content_json.get("tool_calls") or []
            if tool_calls:
                names = [
                    str((tool_call.get('function') or {}).get('name') or "")
                    for tool_call in tool_calls
                    if isinstance(tool_call, dict)
                ]
                names = [name for name in names if name]
                if names:
                    return f"Started tools: {', '.join(names[:4])}"
            return None
        if entry.entry_type == "tool_result":
            name = str(entry.content_json.get("name") or "").strip()
            content = str(entry.content_json.get("content") or "").strip()
            success = entry.content_json.get("success", True) is not False
            if not success:
                return f"Tool failed ({name}): {content[:300] or 'see transcript'}"
            paths = self._entry_file_paths(entry)
            path_text = f" {paths[0]}" if paths else ""
            if name == "read_file":
                return f"Read file{path_text}".strip()
            if name in {"edit_file", "write_file"}:
                return f"Modified file{path_text}".strip()
            if name == "bash":
                return f"Ran bash and captured output: {content[:220]}"
            if name:
                return f"Tool succeeded ({name}): {content[:260]}"
        return None

    def _build_coding_split_turn_context(
        self,
        compacted_entries: List[CodingSessionEntry],
        preserved_tail: List[CodingSessionEntry],
    ) -> List[str]:
        """Describe a turn boundary split so the preserved tail still makes sense."""
        if not compacted_entries or not preserved_tail:
            return []
        last_compacted = compacted_entries[-1]
        first_tail = preserved_tail[0]
        if last_compacted.entry_type == "assistant" and first_tail.entry_type == "assistant_tool_calls":
            content = str(last_compacted.content_json.get("content") or "").strip()
            if content:
                return [f"Assistant had already said: {content[:400]}"]
        if last_compacted.entry_type == "user" and first_tail.entry_type != "user":
            content = str(last_compacted.content_json.get("content") or "").strip()
            if content:
                return [f"Open user request at the cut point: {content[:400]}"]
        return []

    def _build_coding_checkpoint_payload(
        self,
        *,
        compacted_entries: List[CodingSessionEntry],
        preserved_tail: List[CodingSessionEntry],
        session_state: CodingSessionState,
        covered_through_seq: int,
        tail_start_seq: int,
    ) -> dict[str, Any]:
        """Build the persisted structured summary payload for a coding checkpoint."""
        prior_checkpoint = next(
            (
                entry
                for entry in reversed(compacted_entries)
                if self._is_coding_compaction_summary_entry(entry)
            ),
            None,
        )
        prior_state = self._checkpoint_summary_state(prior_checkpoint)
        transcript_entries = [
            entry for entry in compacted_entries if not self._is_coding_compaction_summary_entry(entry)
        ]

        goal = str(prior_state.get("goal") or "").strip()
        if not goal:
            goal = session_state.objective.strip()
        if not goal:
            for entry in transcript_entries:
                if entry.entry_type == "user":
                    goal = str(entry.content_json.get("content") or "").strip()
                    if goal:
                        break

        constraints = self._coerce_string_list(prior_state.get("constraints"))
        done = self._coerce_string_list(prior_state.get("done"))
        blocked = self._coerce_string_list(prior_state.get("blocked"))
        key_decisions = self._coerce_string_list(prior_state.get("key_decisions"))
        critical_context = self._coerce_string_list(prior_state.get("critical_context"))

        for entry in transcript_entries:
            if entry.entry_type == "user":
                constraints.extend(
                    self._extract_constraint_preferences(
                        str(entry.content_json.get("content") or "").strip()
                    )
                )
            bullet = self._entry_summary_bullet(entry)
            if not bullet:
                continue
            if entry.entry_type == "tool_result" and entry.content_json.get("success", True) is False:
                blocked.append(bullet)
            else:
                done.append(bullet)

        if session_state.modified_files:
            key_decisions.append(
                "Modified files carried forward: "
                + ", ".join(session_state.modified_files[-6:])
            )
        if session_state.read_files:
            critical_context.append(
                "Important read files: " + ", ".join(session_state.read_files[-8:])
            )
        if session_state.recent_commands:
            critical_context.append(
                "Recent commands: " + " | ".join(session_state.recent_commands[-4:])
            )

        split_turn_context = self._build_coding_split_turn_context(compacted_entries, preserved_tail)
        in_progress = split_turn_context or ["Continue from the preserved tail below; do not restart."]
        next_steps = split_turn_context or ["Resume from the preserved tail and finish the active task."]

        payload = {
            "goal": goal[:500],
            "constraints": self._dedupe_summary_items(constraints, limit=8),
            "done": self._dedupe_summary_items(done, limit=12),
            "in_progress": self._dedupe_summary_items(in_progress, limit=6),
            "blocked": self._dedupe_summary_items(blocked, limit=8),
            "key_decisions": self._dedupe_summary_items(key_decisions, limit=8),
            "next_steps": self._dedupe_summary_items(next_steps, limit=6),
            "critical_context": self._dedupe_summary_items(critical_context, limit=8),
            "split_turn_context": self._dedupe_summary_items(split_turn_context, limit=4),
            "read_files": session_state.read_files[-12:],
            "modified_files": session_state.modified_files[-12:],
            "covered_through_seq": covered_through_seq,
            "tail_start_seq": tail_start_seq,
        }
        payload["content"] = self._render_coding_checkpoint_summary(payload)
        return payload

    def _render_coding_checkpoint_summary(self, payload: Dict[str, Any]) -> str:
        """Render the replayable checkpoint message content."""
        def section_items(items: List[str], fallback: str) -> List[str]:
            return items if items else [fallback]

        lines = [
            "The earlier part of this coding conversation was compacted into the summary below. Continue from it naturally; do not restart the task.",
            "",
            "<summary>",
            "## Goal",
            f"- {str(payload.get('goal') or 'Continue the existing coding task.')[:500]}",
            "",
            "## Constraints & Preferences",
        ]
        lines.extend(f"- {item}" for item in section_items(payload.get("constraints") or [], "No explicit constraints were preserved."))
        lines.extend(
            [
                "",
                "## Progress",
                "### Done",
            ]
        )
        lines.extend(f"- {item}" for item in section_items(payload.get("done") or [], "No completed work was preserved."))
        lines.extend(["", "### In Progress"])
        lines.extend(f"- {item}" for item in section_items(payload.get("in_progress") or [], "Continue from the preserved tail."))
        lines.extend(["", "### Blocked"])
        lines.extend(f"- {item}" for item in section_items(payload.get("blocked") or [], "No explicit blockers were recorded."))
        lines.extend(["", "## Key Decisions"])
        lines.extend(f"- {item}" for item in section_items(payload.get("key_decisions") or [], "No durable implementation decisions were preserved."))
        lines.extend(["", "## Next Steps"])
        lines.extend(f"- {item}" for item in section_items(payload.get("next_steps") or [], "Continue from the preserved tail below."))
        lines.extend(["", "## Critical Context"])
        lines.extend(f"- {item}" for item in section_items(payload.get("critical_context") or [], "No additional critical context was preserved."))
        split_turn_context = payload.get("split_turn_context") or []
        if split_turn_context:
            lines.extend(["", "## Split Turn Context"])
            lines.extend(f"- {item}" for item in split_turn_context)
        lines.extend(["", "<read-files>"])
        lines.extend(payload.get("read_files") or [])
        lines.extend(["</read-files>", "<modified-files>"])
        lines.extend(payload.get("modified_files") or [])
        lines.extend(["</modified-files>", "</summary>"])
        return "\n".join(lines)

    def _file_restore_line_window(
        self,
        file_state: CodingFileState,
    ) -> tuple[int, int]:
        """Choose a bounded line window for restored file continuity."""
        spans_with_lines = [
            span
            for span in file_state.spans
            if span.line_start is not None and span.line_end is not None
        ]
        if spans_with_lines:
            span = spans_with_lines[-1]
            line_start = max(1, int(span.line_start or 1))
            line_end = max(line_start, int(span.line_end or line_start))
            if line_end - line_start + 1 > 160:
                line_end = line_start + 159
            return line_start, line_end
        return 1, 120

    def _format_restored_read_file_output(
        self,
        *,
        path: str,
        file_state: CodingFileState,
    ) -> Optional[str]:
        """Render current workspace file content as synthetic read_file output."""
        resolved = self._resolve_workspace_file(path)
        if resolved is None or not resolved.exists() or not resolved.is_file():
            return None
        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None

        line_start, line_end = self._file_restore_line_window(file_state)
        selected = lines[line_start - 1 : line_end]
        numbered_lines: List[str] = []
        for index, line in enumerate(selected, start=line_start):
            clean_line = line
            if len(clean_line) > 300:
                clean_line = clean_line[:300] + "..."
            numbered_lines.append(f"{index:>6}\t{clean_line}")
        if not numbered_lines:
            return None
        return self._truncate_text_to_tokens("\n".join(numbered_lines), 3000)

    def _build_restored_file_messages(
        self,
        *,
        session_state: CodingSessionState,
        transcript_entries: List[CodingSessionEntry],
        current_query: str,
    ) -> List[Dict[str, Any]]:
        """Restore bounded current file evidence after a coding checkpoint."""
        checkpoint = self._latest_coding_checkpoint_entry(transcript_entries)
        if checkpoint is None:
            return []

        checkpoint_state = self._checkpoint_summary_state(checkpoint)
        tail_entries = self._tail_entries_after_checkpoint(transcript_entries)
        known_paths = list(dict.fromkeys(
            session_state.modified_files
            + session_state.read_files
            + list(session_state.file_evidence.keys())
            + self._coerce_string_list(checkpoint_state.get("modified_files"))
            + self._coerce_string_list(checkpoint_state.get("read_files"))
        ))
        visible_paths: set[str] = set()
        mentioned_paths: set[str] = set()
        for entry in tail_entries:
            entry_paths = self._entry_file_paths(entry, known_paths=known_paths)
            if entry.entry_type in {"assistant_tool_calls", "tool_result"}:
                visible_paths.update(entry_paths)
            mentioned_paths.update(entry_paths)

        ranked: List[tuple[int, int, str]] = []
        for index, path in enumerate(known_paths):
            if not path or path in visible_paths:
                continue
            file_state = session_state.file_evidence.get(path)
            if file_state is None:
                continue
            score = 0
            if path in session_state.modified_files:
                score += 100
            if path in self._coerce_string_list(checkpoint_state.get("modified_files")):
                score += 80
            if path in mentioned_paths:
                score += 45
            if path in self._coerce_string_list(checkpoint_state.get("read_files")):
                score += 35
            if path in current_query:
                score += 30
            if file_state.last_modified_run_id:
                score += 20
            score += min(len(file_state.spans), 4) * 5
            ranked.append((score, index, path))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected_paths = [path for _, _, path in ranked[:3]]
        if not selected_paths:
            return []

        tool_calls: List[Dict[str, Any]] = []
        tool_messages: List[Dict[str, Any]] = []
        for idx, path in enumerate(selected_paths, start=1):
            file_state = session_state.file_evidence.get(path)
            if file_state is None:
                continue
            content = self._format_restored_read_file_output(path=path, file_state=file_state)
            if not content:
                continue
            tool_call_id = f"checkpoint-read-{checkpoint.seq}-{idx}"
            tool_calls.append(
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"file_path": path}, ensure_ascii=False),
                    },
                }
            )
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": "read_file",
                    "content": content,
                }
            )

        if not tool_calls:
            return []
        return [
            {
                "role": "assistant",
                "content": "Restoring important current file context from the workspace before continuing.",
                "tool_calls": tool_calls,
            },
            *tool_messages,
        ]

    def _coding_tail_target_tokens(self) -> int:
        """Return the retained raw-tail token target for coding compaction."""
        effective_budget = self._context_profile.effective_input_budget
        return min(60_000, max(8_000, int(effective_budget * 0.35)))

    async def _compact_coding_session_history(
        self,
        *,
        conversation_id: str,
        run_id: str,
        step_number: int,
        session_state: CodingSessionState,
        working_memory: Optional[WorkingMemory] = None,
        prompt_tokens_before_reduction: Optional[int] = None,
        raw_replay_counts: Optional[Dict[str, int]] = None,
        reduction_stages_applied: Optional[List[str]] = None,
    ) -> bool:
        """Compact coding-session history into a replayable checkpoint plus raw tail."""
        entry_records = await self._call_repo_async_method(
            "list_coding_session_entries",
            conversation_id,
            include_compacted=False,
        )
        active_entries = [
            CodingSessionEntry.from_dict(entry)
            for entry in (entry_records or [])
        ]
        if len(active_entries) < 2:
            return False

        total_raw_tokens = sum(entry.token_estimate for entry in active_entries)
        tail_target = self._coding_tail_target_tokens()
        if total_raw_tokens <= tail_target:
            return False

        tail_entries = self._tail_entries_after_checkpoint(active_entries)
        if len(tail_entries) < 2:
            return False

        turn_groups = self._group_entries_by_turn(tail_entries)
        if not turn_groups:
            return False
        keep_two_start = (
            turn_groups[-2]["start_seq"] if len(turn_groups) >= 2 else turn_groups[0]["start_seq"]
        )

        suffix_tokens: Dict[int, int] = {}
        running = 0
        for entry in reversed(tail_entries):
            running += entry.token_estimate
            suffix_tokens[entry.seq] = running

        safe_candidates = [entry.seq for entry in tail_entries if entry.entry_type != "tool_result"]
        preferred_candidates = [seq for seq in safe_candidates if seq <= keep_two_start]
        candidate_seq: Optional[int] = next(
            (seq for seq in preferred_candidates if suffix_tokens.get(seq, 0) <= tail_target),
            None,
        )
        if candidate_seq is None:
            split_candidates = [seq for seq in safe_candidates if seq >= keep_two_start]
            candidate_seq = next(
                (seq for seq in split_candidates if suffix_tokens.get(seq, 0) <= tail_target),
                None,
            )
            if candidate_seq is None and split_candidates:
                candidate_seq = split_candidates[-1]

        if candidate_seq is None:
            return False

        compacted_entries = [entry for entry in active_entries if entry.seq < candidate_seq]
        if not compacted_entries:
            return False

        preserved_tail = [entry for entry in active_entries if entry.seq >= candidate_seq]
        if not preserved_tail:
            return False

        _ = working_memory
        session_state.normalize()
        checkpoint_payload = self._build_coding_checkpoint_payload(
            compacted_entries=compacted_entries,
            preserved_tail=preserved_tail,
            session_state=session_state,
            covered_through_seq=compacted_entries[-1].seq,
            tail_start_seq=candidate_seq,
        )
        checkpoint_entry = {
            "run_id": run_id,
            "step_number": step_number,
            "entry_type": "compaction_summary",
            "role": "user",
            "content_json": {
                "content": checkpoint_payload["content"],
                "summary_state": {
                    key: value
                    for key, value in checkpoint_payload.items()
                    if key != "content"
                },
                "covered_through_seq": checkpoint_payload["covered_through_seq"],
                "tail_start_seq": checkpoint_payload["tail_start_seq"],
                "read_files": checkpoint_payload["read_files"],
                "modified_files": checkpoint_payload["modified_files"],
                "replay_eligible": True,
            },
            "token_estimate": self._message_token_estimate(
                "user",
                {"content": checkpoint_payload["content"]},
            ),
        }
        inserted_checkpoint = await self._call_repo_async_method(
            "insert_coding_session_entry",
            conversation_id,
            before_seq=candidate_seq,
            entry=checkpoint_entry,
        )
        await self._call_repo_async_method(
            "mark_coding_session_entries_compacted",
            conversation_id,
            through_seq=candidate_seq - 1,
        )
        await self._call_repo_async_method(
            "upsert_coding_session_state",
            conversation_id,
            session_state.to_dict(),
            last_run_id=run_id,
        )
        await self._add_trace_event(
            run_id=run_id,
            event_type="coding_session_compaction",
            content={
                "conversation_id": conversation_id,
                "step_number": step_number,
                "checkpoint_seq": inserted_checkpoint.get("seq") if isinstance(inserted_checkpoint, dict) else candidate_seq,
                "compacted_through_seq": candidate_seq - 1,
                "checkpoint_present": True,
                "preserved_tail_count": len(preserved_tail),
                "retained_raw_tokens": sum(entry.token_estimate for entry in preserved_tail),
                "tail_target_tokens": tail_target,
                "compacted_entry_count": len(compacted_entries),
                "kept_last_two_turns_raw": candidate_seq <= keep_two_start,
                "restorable_read_files": checkpoint_payload["read_files"],
                "restorable_modified_files": checkpoint_payload["modified_files"],
                "prompt_tokens_before_reduction": prompt_tokens_before_reduction,
                "raw_replay_counts": raw_replay_counts or {},
                "reduction_stages_applied": reduction_stages_applied or [],
                "fallback_stage": "stage4_checkpoint_fallback",
            },
            actor="system",
            step_number=step_number,
        )
        return True

    async def _persist_coding_session_state(
        self,
        *,
        conversation_id: str,
        run_id: str,
        working_memory: WorkingMemory,
        session_state: CodingSessionState,
        tool_results: Optional[List[tuple[ParsedToolCall, "ToolResult"]]] = None,
        final_answer: Optional[str] = None,
        reason: str,
        step_number: Optional[int] = None,
    ) -> None:
        """Persist durable coding-session state for the current conversation."""
        self._merge_working_memory_into_coding_session(session_state, working_memory)
        if tool_results:
            self._merge_tool_results_into_coding_session(session_state, tool_results, run_id)
        session_state.normalize()

        await self._call_repo_async_method(
            "upsert_coding_session_state",
            conversation_id,
            session_state.to_dict(),
            last_run_id=run_id,
        )

    async def _persist_coding_session_on_failure(
        self,
        *,
        conversation_id: Optional[str],
        run_id: str,
        working_memory: Optional[WorkingMemory],
        coding_session_state: Optional[CodingSessionState],
        coding_session_dirty: bool,
        error_message: str,
    ) -> None:
        """Persist coding session state when a run fails.

        Saves the working memory accumulated up to the point of failure so the
        next run in the conversation retains file/edit context and knows the
        prior run errored.
        """
        if not (coding_session_dirty and conversation_id
                and working_memory is not None
                and coding_session_state is not None):
            return
        try:
            await self._persist_coding_session_state(
                conversation_id=conversation_id,
                run_id=run_id,
                working_memory=working_memory,
                session_state=coding_session_state,
                reason="run_failed",
            )
        except Exception as persist_err:
            logger.warning(
                "Failed to persist coding session on run failure",
                extra={"run_id": run_id, "error": str(persist_err)},
            )

    async def run(
        self,
        run_id: str,
        query: str,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        conversation_id: Optional[str] = None,
        pause_signal: Optional[asyncio.Event] = None,
        resume_signal: Optional[asyncio.Event] = None,
        steer_queue: Optional[List[str]] = None,
        image_attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResult:
        """Execute agent loop for a query.

        Args:
            run_id: Unique run ID.
            query: User's research query.
            event_callback: Callback for SSE events.
            conversation_id: Optional conversation context.
            pause_signal: Event set when user requests pause (between steps).
            resume_signal: Event set when user requests resume after pause.
            steer_queue: Shared list for mid-run user steering messages.

        Returns:
            AgentResult with answer and citations.
        """
        start_time = time.perf_counter()
        coding_session_state: Optional[CodingSessionState] = None
        coding_session_dirty = False
        ephemeral_messages: List[Dict[str, Any]] = []
        # Plan Mode exploration must not become durable coding-session context.
        # The approved implementation run should start from the plan and re-read
        # files, not replay plan-time file evidence as if it were implementation
        # state.
        coding_session_persistence_enabled = (
            self._is_coding_profile() and self._collaboration_mode != "plan"
        )

        # Initialize findings for this run
        self._findings = []
        self._current_query = query
        self._total_tokens = 0
        self._usage_totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        }
        self._tool_call_log = []
        self._tool_state_version = 0
        self._file_state_versions = {}
        self._file_last_read_state_versions = {}
        self._file_last_read_sequences = {}
        self._file_read_sequence = 0
        self._edit_failures = {}
        self._apply_patch_failures = {}
        self._last_redundant_filter_codes = {}
        self._coding_last_step_structural_failure = False
        self._last_context_usage = None
        self._last_stored_context = None
        validated_images = validate_image_attachments(image_attachments)
        if validated_images and not bool(getattr(self._provider, "_supports_vision", False)):
            raise ValueError("Active model does not support image inputs. Select a vision model.")

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
            current_user_content: Any = (
                build_multimodal_user_content(query, validated_images)
                if validated_images
                else query
            )
            working_memory = WorkingMemory(objective=query)
            self._active_conversation_id = conversation_id
            self._active_coding_session_state = None
            coding_session_had_entries = False
            if coding_session_persistence_enabled and conversation_id:
                session_record, coding_session_state = await self._load_coding_session_state_record(
                    conversation_id
                )
                latest_entry_seq = await self._call_repo_async_method(
                    "get_latest_coding_session_entry_seq",
                    conversation_id,
                )
                coding_session_had_entries = bool(latest_entry_seq)
                if coding_session_state is None:
                    coding_session_state = CodingSessionState(objective=query)
                else:
                    await self._hydrate_working_memory_from_coding_session(
                        conversation_id=conversation_id,
                        session_state=coding_session_state,
                        working_memory=working_memory,
                        run_id=run_id,
                        updated_at=session_record.get("updated_at") if session_record else None,
                    )
                if not coding_session_state.objective:
                    coding_session_state.objective = query
                await self._persist_coding_session_user_message(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    session_state=coding_session_state,
                    user_content=current_user_content,
                )
                await self._persist_coding_session_state(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    working_memory=working_memory,
                    session_state=coding_session_state,
                    reason="user_turn_start",
                )
                coding_session_dirty = True
                self._active_coding_session_state = coding_session_state

            # Build initial scaffold from persisted session history or turn summaries.
            system_prompt = self._resolved_system_prompt()
            messages, self._context_budget = await self._build_initial_messages(
                query,
                conversation_id,
                run_id=run_id,
                coding_session_state=coding_session_state,
                working_memory=working_memory,
                coding_session_use_entries=coding_session_had_entries,
            )
            if not self._is_coding_profile():
                if validated_images and messages and messages[-1].get("role") == "user":
                    messages[-1]["content"] = current_user_content
                working_memory.prior_outcomes = self._prior_outcomes_from_scaffold(messages)

            # Handle recovery if needed
            if recovery_context.needs_recovery:
                ephemeral_messages.extend(recovery_context.hints)
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
            consecutive_filtered_steps = 0
            length_only_continuations = 0

            # Main agent loop
            while state_machine.can_continue():
                step = await state_machine.start_step()
                step_number = step["step_number"]
                image_parts_for_next_call: List[Dict[str, Any]] = []

                # Drain any pending steering messages before prompt assembly.
                if steer_queue:
                    while steer_queue:
                        steer_msg = steer_queue.pop(0)
                        if (
                            coding_session_persistence_enabled
                            and conversation_id
                            and coding_session_state is not None
                        ):
                            await self._persist_coding_session_user_message(
                                conversation_id=conversation_id,
                                run_id=run_id,
                                session_state=coding_session_state,
                                user_content=steer_msg,
                            )
                            coding_session_dirty = True
                        else:
                            messages.append({"role": "user", "content": steer_msg})
                        self._emit(
                            event_callback,
                            "steer_injected",
                            run_id=run_id,
                            content=steer_msg,
                            step_number=step_number,
                        )
                        logger.info(
                            "Steering message injected",
                            extra={"run_id": run_id, "step": step_number, "steer_content": steer_msg[:80]},
                        )

                compacted_now = False
                if (
                    coding_session_persistence_enabled
                    and conversation_id
                    and coding_session_state is not None
                ):
                    pruned_messages, self._context_budget, context_usage_payload = (
                        await self._prepare_coding_prompt_messages(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            query=query,
                            step_number=step_number,
                            system_prompt=system_prompt,
                            session_state=coding_session_state,
                            working_memory=working_memory,
                        )
                    )
                    if ephemeral_messages:
                        pruned_messages = [*pruned_messages, *ephemeral_messages]
                    compacted_now = bool(
                        context_usage_payload.get("checkpoint_fallback_activated")
                    )
                else:
                    prompt_messages = self._build_prompt_messages(
                        scaffold_messages=messages,
                        working_memory=working_memory,
                    )

                    pruned_messages, context_usage_payload, compacted_now = self._enforce_prompt_budget(
                        prompt_messages,
                        step_number,
                        enable_compaction=not self._is_coding_profile(),
                    )
                self._last_context_usage = context_usage_payload
                estimated_tokens = context_usage_payload["prompt_tokens_current_call"]
                context_remaining = context_usage_payload["remaining_tokens"]

                if self._context_budget:
                    fixed_tokens = (
                        self._context_budget.system_prompt_tokens
                        + self._context_budget.current_query_tokens
                        + self._context_budget.plan_tokens
                    )
                    self._context_budget.history_tokens = max(0, estimated_tokens - fixed_tokens)

                self._emit(
                    event_callback,
                    "step_started",
                    run_id=run_id,
                    step_number=step_number,
                    steps_remaining=state_machine.steps_remaining,
                    context_tokens=estimated_tokens,
                    context_max=self._context_profile.context_window,
                    context_remaining=context_remaining,
                    total_tokens_used=self._total_tokens,
                    context_usage=context_usage_payload,
                    stored_context=self._last_stored_context,
                    context_profile=self._context_profile_dict(),
                    compaction_count=self._compaction_count,
                    last_compacted_at_step=self._last_compacted_at_step,
                )

                await self._add_trace_event(
                    run_id=run_id,
                    event_type="step_start",
                    content={
                        "step_number": step_number,
                        "steps_remaining": state_machine.steps_remaining,
                        "context_tokens": estimated_tokens,
                        "context_max": self._context_profile.context_window,
                        "context_usage": context_usage_payload,
                        "stored_context": self._last_stored_context,
                        "context_profile": self._context_profile_dict(),
                    },
                    step_number=step_number,
                )

                if compacted_now:
                    context_usage_payload = self._current_context_usage_payload(
                        self._pruner.estimate_tokens(pruned_messages)
                    )
                    self._last_context_usage = context_usage_payload
                    self._emit(
                        event_callback,
                        "conversation_compacted",
                        run_id=run_id,
                        step_number=step_number,
                        message=self.COMPACTION_PREFIX,
                        context_usage=context_usage_payload,
                        stored_context=self._last_stored_context,
                        context_profile=self._context_profile_dict(),
                        compaction_count=self._compaction_count,
                    )
                    await self._add_trace_event(
                        run_id=run_id,
                        event_type="conversation_compacted",
                        content={
                            "step_number": step_number,
                            "message": self.COMPACTION_PREFIX,
                            "context_usage": context_usage_payload,
                            "stored_context": self._last_stored_context,
                            "context_profile": self._context_profile_dict(),
                            "compaction_count": self._compaction_count,
                        },
                        actor="system",
                        step_number=step_number,
                    )

                # Call LLM with tools
                tool_schemas = self._available_tool_schemas()

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
                    step_tool_choice = self._tool_choice if step_number == 1 else None
                    llm_response = await self._call_llm_with_tools(
                        messages=pruned_messages,
                        event_callback=event_callback,
                        run_id=run_id,
                        tool_choice=step_tool_choice,
                        tool_schemas=tool_schemas,
                    )
                except BaseException as e:
                    error_message = _format_exception_for_user(e)
                    llm_duration_ms = int((time.perf_counter() - llm_start_time) * 1000)
                    logger.error(
                        "LLM call failed",
                        extra={
                            "run_id": run_id,
                            "step_number": step_number,
                            "error": error_message,
                            "error_type": f"{e.__class__.__module__}.{e.__class__.__name__}",
                            "error_repr": repr(e),
                        },
                    )
                    try:
                        await self._add_trace_event(
                            run_id=run_id,
                            event_type="llm_response",
                            content={
                                "error_message": error_message,
                                "error_type": f"{e.__class__.__module__}.{e.__class__.__name__}",
                            },
                            actor="model",
                            event_status="error",
                            step_number=step_number,
                            duration_ms=llm_duration_ms,
                            parent_event_id=llm_request_event_id,
                        )
                        await state_machine.error_step(error_message)
                        await state_machine.error_run(error_message)
                    except Exception:
                        pass
                    if isinstance(e, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                        raise
                    return AgentResult(
                        run_id=run_id,
                        success=False,
                        error_message=error_message,
                        total_steps=step_number,
                        timing_ms=int((time.perf_counter() - start_time) * 1000),
                        total_tokens=self._total_tokens,
                        context_profile=self._context_profile_dict(),
                        compaction_count=self._compaction_count,
                        last_compacted_at_step=self._last_compacted_at_step,
                        usage=self._usage_totals.copy(),
                        cost=self._current_cost(),
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
                    # Try all text-based tool call formats on both text and reasoning
                    for source_name, source_text in [("text", llm_response.text), ("reasoning", llm_response.reasoning)]:
                        if not source_text:
                            continue
                        # 1. Harmony format (gpt-oss: <|channel|> tokens)
                        parsed = self._parse_text_tool_calls(source_text)
                        # 2. Qwen XML format (<tool_call><function=...>)
                        if not parsed:
                            parsed = self._parse_xml_tool_calls(source_text)
                        # 3. Raw JSON format ({"query": "..."})
                        if not parsed:
                            parsed = self._parse_json_tool_calls(source_text)
                        if parsed:
                            tool_calls = parsed
                            logger.info(
                                f"Parsed tool calls from {source_name}",
                                extra={"count": len(parsed), "tools": [tc["function"]["name"] for tc in parsed]},
                            )
                            break
                    else:
                        logger.debug("No tool calls found in text or reasoning")

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
                        "finish_reason": llm_response.finish_reason,
                    },
                    actor="model",
                    step_number=step_number,
                    duration_ms=llm_duration_ms,
                    parent_event_id=llm_request_event_id,
                    token_count=llm_response.usage.get("total_tokens"),
                )

                # Accumulate normalized token usage for run stats/cost display.
                normalized_usage = self._record_usage(
                    llm_response.usage,
                    prompt_messages=pruned_messages,
                    output_text=llm_response.text,
                    reasoning_text=llm_response.reasoning,
                )
                self._emit(
                    event_callback,
                    "usage_update",
                    run_id=run_id,
                    usage=self._usage_totals,
                    latest_usage=normalized_usage,
                    cost=self._current_cost(),
                    context_usage=self._current_context_usage_payload(
                        self._pruner.estimate_tokens(pruned_messages)
                    ),
                    stored_context=self._last_stored_context,
                    context_profile=self._context_profile_dict(),
                    compaction_count=self._compaction_count,
                    last_compacted_at_step=self._last_compacted_at_step,
                )

                # Model was truncated (hit max_tokens) — partial content
                # is not a final answer, the model may have been mid-tool-call
                if not tool_calls and llm_response.finish_reason == "length":
                    length_only = not (llm_response.text or "").strip() and bool(
                        llm_response.reasoning
                    )
                    if length_only and length_only_continuations >= 1:
                        logger.warning(
                            "Length-only reasoning repeated; forcing no-tools synthesis",
                            extra={
                                "run_id": run_id,
                                "step_number": step_number,
                                "reasoning_length": len(llm_response.reasoning or ""),
                            },
                        )
                        await state_machine.complete_step(
                            decision="length_only_force_synthesis",
                            thinking_text=thinking_text,
                        )
                        final_answer = await self._force_synthesis(
                            messages=self._build_prompt_messages(
                                scaffold_messages=messages,
                                working_memory=working_memory,
                            ),
                            event_callback=event_callback,
                            run_id=run_id,
                        )
                        return await self._finalize_successful_run(
                            final_answer=final_answer,
                            messages=messages,
                            state_machine=state_machine,
                            step_number=step_number,
                            start_time=start_time,
                            event_callback=event_callback,
                            run_id=run_id,
                            query=query,
                            conversation_id=conversation_id,
                            working_memory=working_memory,
                            coding_session_state=coding_session_state,
                            coding_session_dirty=coding_session_dirty,
                            forced_synthesis=True,
                        )
                    logger.warning(
                        "Model truncated (finish_reason=length), continuing",
                        extra={
                            "run_id": run_id,
                            "step_number": step_number,
                            "text_length": len(llm_response.text) if llm_response.text else 0,
                            "length_only": length_only,
                        },
                    )
                    if llm_response.text:
                        partial_message = {
                            "role": "assistant",
                            "content": self._summarize_assistant_content(llm_response.text),
                        }
                        messages.append(partial_message)
                        if self._is_coding_profile():
                            ephemeral_messages.append(partial_message)
                    if length_only:
                        length_only_continuations += 1
                    continuation_message = {
                        "role": "user",
                        "content": (
                            "Your last response hit the length limit before producing answer text. "
                            "Continue once from the compact working memory. "
                            "Prefer a concise final answer; call a tool only if essential."
                        ),
                    }
                    messages.append(continuation_message)
                    if self._is_coding_profile():
                        ephemeral_messages.append(continuation_message)
                    else:
                        messages = self._trim_scaffold_messages(messages)
                    await state_machine.complete_step(
                        decision="truncated",
                        thinking_text=thinking_text,
                    )
                    consecutive_filtered_steps = 0
                    continue

                if tool_calls:
                    # Check for redundant tool calls before execution
                    parsed_for_check = self._parse_tool_calls(tool_calls)
                    malformed_calls = [
                        tc for tc in parsed_for_check if tc.parse_error is not None
                    ]
                    if malformed_calls:
                        valid_ids = {
                            tc.id for tc in parsed_for_check if tc.parse_error is None
                        }
                        malformed_descriptions = "; ".join(
                            f"{tc.name}: {tc.parse_error}" for tc in malformed_calls
                        )
                        logger.warning(
                            "Filtered malformed tool calls",
                            extra={
                                "run_id": run_id,
                                "step_number": step_number,
                                "malformed_count": len(malformed_calls),
                                "valid_count": len(valid_ids),
                                "finish_reason": llm_response.finish_reason,
                            },
                        )
                        if valid_ids:
                            tool_calls = [
                                tc for tc in tool_calls if tc.get("id") in valid_ids
                            ]
                            parsed_for_check = [
                                tc for tc in parsed_for_check if tc.parse_error is None
                            ]
                            malformed_notice = {
                                "role": "system",
                                "content": (
                                    "[Malformed tool calls were dropped because their arguments "
                                    f"were incomplete or invalid JSON: {malformed_descriptions}]"
                                ),
                            }
                            messages.append(malformed_notice)
                            if self._is_coding_profile():
                                ephemeral_messages.append(malformed_notice)
                        else:
                            malformed_notice = {
                                "role": "system",
                                "content": (
                                    "[Your last tool call was malformed because its arguments "
                                    f"were incomplete or invalid JSON: {malformed_descriptions}]"
                                ),
                            }
                            retry_prompt = {
                                "role": "user",
                                "content": (
                                    "Retry the intended tool call now. "
                                    "Return only a valid tool call with complete JSON arguments "
                                    "for every required field. Do not explain the plan in prose."
                                ),
                            }
                            messages.append(malformed_notice)
                            messages.append(retry_prompt)
                            if self._is_coding_profile():
                                ephemeral_messages.append(malformed_notice)
                                ephemeral_messages.append(retry_prompt)
                            else:
                                messages = self._trim_scaffold_messages(messages)
                            await state_machine.complete_step(
                                decision="malformed_tool_call",
                                thinking_text=thinking_text,
                            )
                            consecutive_filtered_steps = 0
                            continue

                    redundant = self._detect_redundant_calls(parsed_for_check)
                    if redundant:
                        redundant_ids = {tc.id for tc, _ in redundant}
                        tool_calls = [tc for tc in tool_calls if tc["id"] not in redundant_ids]
                        reasons = "; ".join(r for _, r in redundant)
                        redundant_codes = {
                            self._last_redundant_filter_codes.get(tc.id, "duplicate")
                            for tc, _ in redundant
                        }
                        edit_reread_only = redundant_codes == {"edit_reread_required"}
                        apply_patch_recovery_only = redundant_codes == {
                            "apply_patch_recovery_required"
                        }
                        logger.info(
                            "Filtered redundant tool calls",
                            extra={"reasons": reasons, "filtered_count": len(redundant)},
                        )
                        filtered_notice = {
                            "role": "system",
                            "content": (
                                "[Engine notice: the previous tool call was filtered as redundant — "
                                f"{reasons}. This is an engine constraint, not a user instruction.]"
                            ),
                        }
                        messages.append(filtered_notice)
                        if self._is_coding_profile():
                            ephemeral_messages.append(filtered_notice)
                        if not tool_calls:
                            await state_machine.complete_step(
                                decision="filtered",
                                thinking_text=thinking_text,
                            )
                            if edit_reread_only:
                                consecutive_filtered_steps = 0
                            elif apply_patch_recovery_only:
                                consecutive_filtered_steps = 0
                            else:
                                consecutive_filtered_steps += 1
                            if consecutive_filtered_steps >= 2:
                                logger.warning(
                                    "Model repeated filtered tool calls; forcing synthesis",
                                    extra={
                                        "run_id": run_id,
                                        "step_number": step_number,
                                        "consecutive_filtered_steps": consecutive_filtered_steps,
                                        "reasons": reasons,
                                    },
                                )
                                final_answer = await self._force_synthesis(
                                    messages=self._build_prompt_messages(
                                        scaffold_messages=messages,
                                        working_memory=working_memory,
                                    ),
                                    event_callback=event_callback,
                                    run_id=run_id,
                                )
                                return await self._finalize_successful_run(
                                    final_answer=final_answer,
                                    messages=messages,
                                    state_machine=state_machine,
                                    step_number=step_number,
                                    start_time=start_time,
                                    event_callback=event_callback,
                                    run_id=run_id,
                                    query=query,
                                    conversation_id=conversation_id,
                                    working_memory=working_memory,
                                    coding_session_state=coding_session_state,
                                    coding_session_dirty=coding_session_dirty,
                                    forced_synthesis=True,
                                )

                        filtered_user_prompt = {
                            "role": "user",
                            "content": (
                                "A tool call was filtered by the engine as redundant. "
                                "Do not attribute that constraint to the user. "
                                + (
                                    "Reread the relevant file region before retrying the same edit_file call. "
                                    "Do not resend identical stale edit arguments without reacquiring current text."
                                    if edit_reread_only
                                    else "Retry a smaller apply_patch built from fresh file text. "
                                    "If you have not reread the affected region yet, reread it first. "
                                    "Do not switch to edit_file or write_file as a fallback for a failed patch."
                                    if apply_patch_recovery_only
                                    else "Either provide the final answer now or choose a genuinely different tool call. "
                                    "Only retry the same tool if something materially changed since the last identical call."
                                )
                            ),
                        }
                        messages.append(filtered_user_prompt)
                        if self._is_coding_profile():
                            ephemeral_messages.append(filtered_user_prompt)
                        continue

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

                    # Add assistant message with tool calls. Historical reasoning stays
                    # in DB/UI only and is never re-injected into future prompts.
                    assistant_content = self._summarize_assistant_content(llm_response.text)
                    replay_tool_calls, recovery_notes = self._canonical_replay_tool_calls(
                        tool_results
                    )
                    assistant_message: Dict[str, Any] = {
                        "role": "assistant",
                        "content": assistant_content,
                    }
                    if replay_tool_calls:
                        assistant_message["tool_calls"] = replay_tool_calls
                    messages.append(assistant_message)
                    self._update_working_memory_from_tools(working_memory, tool_results)
                    self._record_tool_call_recovery(working_memory, recovery_notes)
                    apply_patch_failures = self._apply_patch_failure_contexts(tool_results)
                    self._record_apply_patch_failure_recovery(
                        working_memory, apply_patch_failures
                    )
                    edit_failures = self._edit_failure_contexts(tool_results)
                    self._record_edit_failure_recovery(working_memory, edit_failures)
                    if (
                        coding_session_persistence_enabled
                        and coding_session_state is not None
                        and conversation_id
                    ):
                        coding_session_dirty = True
                        await self._persist_coding_session_step_entries(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            step_number=step_number,
                            assistant_content=assistant_content,
                            tool_results=tool_results,
                        )
                        await self._persist_coding_session_state(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            working_memory=working_memory,
                            session_state=coding_session_state,
                            tool_results=tool_results,
                            reason="tool_progress",
                            step_number=step_number,
                        )
                    for tool_call, result in tool_results:
                        if (
                            tool_call.name == "view_image"
                            and result.success
                            and bool(getattr(self._provider, "_supports_vision", False))
                        ):
                            image_parts_for_next_call.extend(
                                self._image_parts_from_tool_result(result)
                            )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.name,
                                "content": self._format_tool_result(result, tool_call.name),
                                "_step": step_number,
                        }
                        )
                        step_metadata[tool_call.id] = step_number

                    if apply_patch_failures:
                        for recovery_message in (
                            self._build_apply_patch_failure_recovery_messages(
                                apply_patch_failures
                            )
                        ):
                            messages.append(recovery_message)
                            if self._is_coding_profile():
                                ephemeral_messages.append(recovery_message)

                    if edit_failures:
                        for recovery_message in self._build_edit_failure_recovery_messages(
                            edit_failures
                        ):
                            messages.append(recovery_message)
                            if self._is_coding_profile():
                                ephemeral_messages.append(recovery_message)

                    if recovery_notes:
                        recovery_message = {
                            "role": "system",
                            "content": (
                                "Previous tool call was invalid and failed. "
                                + " ".join(recovery_notes)
                                + " Continue from the current state. "
                                "Do not repeat malformed or incomplete tool arguments. "
                                "If no tool is needed, answer directly."
                            ),
                        }
                        messages.append(recovery_message)
                        if self._is_coding_profile():
                            ephemeral_messages.append(recovery_message)

                    if image_parts_for_next_call:
                        vision_followup_message = {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Inspect the attached workspace image(s) visually and answer the user's request. "
                                        "Use the images directly; do not rely on OCR unless you need exact text extraction."
                                    ),
                                },
                                *image_parts_for_next_call,
                            ],
                            "_vision_from_tool": True,
                            "_step": step_number,
                        }
                        messages.append(vision_followup_message)
                        if self._is_coding_profile():
                            ephemeral_messages.append(vision_followup_message)

                    consecutive_filtered_steps = 0
                    length_only_continuations = 0

                    await state_machine.complete_step(
                        decision="call_tool",
                        thinking_text=thinking_text,
                    )

                    # Check if user requested pause between steps
                    if pause_signal and pause_signal.is_set():
                        await state_machine.pause_run()
                        self._emit(
                            event_callback,
                            "agent_paused",
                            run_id=run_id,
                            step_number=step_number,
                        )
                        # Block until resume signal fires
                        if resume_signal:
                            pause_signal.clear()
                            await resume_signal.wait()
                            resume_signal.clear()
                        await state_machine.resume_run()
                        self._emit(
                            event_callback,
                            "agent_resumed",
                            run_id=run_id,
                            step_number=step_number,
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

                    # Provider put everything in reasoning, content is empty.
                    # This happens when OpenRouter auto-separates thinking models
                    # (Qwen, etc.) and routes all output to reasoning_content.
                    if not final_answer and llm_response.reasoning:
                        final_answer = self._clean_answer(llm_response.reasoning)
                        logger.info(
                            "Used reasoning as answer (provider sent empty content)",
                            extra={"answer_length": len(final_answer)},
                        )

                    if self._collaboration_mode == "plan":
                        proposed_plan = extract_proposed_plan(final_answer)
                        if proposed_plan is not None and proposed_plan.markdown:
                            plan_id = str(uuid.uuid4())
                            await self._repo.create_run_artifact(
                                run_id=run_id,
                                artifact_type="proposed_plan",
                                file_path=None,
                                action="plan_mode",
                                detail=proposed_plan.markdown,
                            )
                            self._emit(
                                event_callback,
                                "plan_approval_required",
                                run_id=run_id,
                                plan_id=plan_id,
                                markdown=proposed_plan.markdown,
                                visible_answer=proposed_plan.visible_answer,
                                step_number=step_number,
                            )
                            decision = await self._await_plan_decision(
                                run_id=run_id,
                                plan_id=plan_id,
                                markdown=proposed_plan.markdown,
                            )
                            if decision.decision == "rejected":
                                await state_machine.complete_step(
                                    decision="plan_rejected",
                                    thinking_text=thinking_text,
                                )
                                rejection_message = {
                                    "role": "user",
                                    "content": (
                                        "The user rejected the proposed plan. "
                                        "Continue planning and revise it using this feedback:\n\n"
                                        f"{(decision.feedback or '').strip() or 'No specific feedback provided.'}"
                                    ),
                                }
                                messages.append(
                                    {
                                        "role": "assistant",
                                        "content": proposed_plan.markdown,
                                    }
                                )
                                messages.append(rejection_message)
                                if self._is_coding_profile():
                                    ephemeral_messages.append(rejection_message)
                                continue

                            self._approved_plan = proposed_plan.markdown
                            self._implementation_run_id = decision.implementation_run_id
                            self._implementation_stream_token = decision.implementation_stream_token
                            final_answer = proposed_plan.visible_answer or proposed_plan.markdown
                            self._emit(
                                event_callback,
                                "plan_approved",
                                run_id=run_id,
                                plan_id=plan_id,
                                implementation_run_id=decision.implementation_run_id,
                                implementation_stream_token=decision.implementation_stream_token,
                            )
                        else:
                            await state_machine.complete_step(
                                decision="plan_missing_block",
                                thinking_text=thinking_text,
                            )
                            if final_answer:
                                messages.append(
                                    {
                                        "role": "assistant",
                                        "content": final_answer,
                                    }
                                )
                            missing_plan_message = {
                                "role": "user",
                                "content": (
                                    "Plan Mode requires the final plan to be wrapped in "
                                    "<proposed_plan>...</proposed_plan>. Continue planning "
                                    "and produce the required plan block."
                                ),
                            }
                            messages.append(missing_plan_message)
                            if self._is_coding_profile():
                                ephemeral_messages.append(missing_plan_message)
                            continue

                    # Append assistant response to messages for cross-turn context.
                    # Keep only final answer text in long-lived scaffold.
                    if final_answer:
                        messages.append({
                            "role": "assistant",
                            "content": final_answer,
                        })
                    messages = self._trim_scaffold_messages(messages)

                    # Emit answer as answer_token so UI displays it in answer panel
                    # (streaming sent it to thinking, now send cleaned version to answer)
                    if final_answer:
                        self._emit(
                            event_callback,
                            "answer_token",
                            run_id=run_id,
                            content=final_answer,
                        )

                    await state_machine.complete_step(
                        decision="synthesize",
                        thinking_text=thinking_text,
                    )
                    return await self._finalize_successful_run(
                        final_answer=final_answer,
                        messages=messages,
                        state_machine=state_machine,
                        step_number=step_number,
                        start_time=start_time,
                        event_callback=event_callback,
                        run_id=run_id,
                        query=query,
                        conversation_id=conversation_id,
                        working_memory=working_memory,
                        coding_session_state=coding_session_state,
                        coding_session_dirty=coding_session_dirty,
                    )

            # Max steps reached - force synthesis
            final_answer = await self._force_synthesis(
                messages=self._build_prompt_messages(
                    scaffold_messages=messages,
                    working_memory=working_memory,
                ),
                event_callback=event_callback,
                run_id=run_id,
            )

            return await self._finalize_successful_run(
                final_answer=final_answer,
                messages=messages,
                state_machine=state_machine,
                step_number=state_machine.current_step,
                start_time=start_time,
                event_callback=event_callback,
                run_id=run_id,
                query=query,
                conversation_id=conversation_id,
                working_memory=working_memory,
                coding_session_state=coding_session_state,
                coding_session_dirty=coding_session_dirty,
                forced_synthesis=True,
            )

        except MaxStepsExceededError:
            # Should not happen due to can_continue() check, but handle anyway
            await state_machine.error_run("Max steps exceeded")
            await self._persist_coding_session_on_failure(
                conversation_id=conversation_id,
                run_id=run_id,
                working_memory=working_memory,
                coding_session_state=coding_session_state,
                coding_session_dirty=coding_session_dirty,
                error_message="Max steps exceeded",
            )
            return AgentResult(
                run_id=run_id,
                success=False,
                error_message="Max steps exceeded",
                total_steps=state_machine.current_step,
                timing_ms=int((time.perf_counter() - start_time) * 1000),
                total_tokens=self._total_tokens,
                usage=self._usage_totals.copy(),
                cost=self._current_cost(),
            )
        except BaseException as e:
            error_message = _format_exception_for_user(e)
            logger.error(
                "Agent run failed",
                extra={
                    "run_id": run_id,
                    "error": error_message,
                    "error_type": f"{e.__class__.__module__}.{e.__class__.__name__}",
                    "error_repr": repr(e),
                },
                exc_info=True,
            )
            try:
                await state_machine.error_run(error_message)
            except Exception:
                pass

            self._emit(
                event_callback,
                "agent_error",
                run_id=run_id,
                error=error_message,
            )

            # Trace: agent_error
            total_timing_ms = int((time.perf_counter() - start_time) * 1000)
            try:
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="agent_error",
                    content={
                        "error_message": error_message,
                        "total_steps": state_machine.current_step,
                    },
                    event_status="error",
                    duration_ms=total_timing_ms,
                )
            except Exception:
                pass

            await self._persist_coding_session_on_failure(
                conversation_id=conversation_id,
                run_id=run_id,
                working_memory=working_memory,
                coding_session_state=coding_session_state,
                coding_session_dirty=coding_session_dirty,
                error_message=error_message,
            )

            if isinstance(e, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise

            return AgentResult(
                run_id=run_id,
                success=False,
                error_message=error_message,
                total_steps=state_machine.current_step,
                timing_ms=total_timing_ms,
                total_tokens=self._total_tokens,
                usage=self._usage_totals.copy(),
                cost=self._current_cost(),
            )
        finally:
            close_all = getattr(self._registry, "close_all", None)
            if callable(close_all):
                maybe_close = close_all()
                if inspect.isawaitable(maybe_close):
                    await maybe_close
            self._active_conversation_id = None
            self._active_coding_session_state = None

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _await_plan_decision(
        self,
        *,
        run_id: str,
        plan_id: str,
        markdown: str,
    ) -> PlanDecision:
        """Wait for the browser HUD to approve or reject a proposed plan."""
        if self._plan_approval_callback is None:
            return PlanDecision(decision="approved")

        decision = await self._plan_approval_callback(run_id, plan_id, markdown)
        if isinstance(decision, PlanDecision):
            return decision
        if isinstance(decision, dict):
            return PlanDecision(
                decision="rejected" if decision.get("decision") == "rejected" else "approved",
                feedback=decision.get("feedback"),
                implementation_run_id=decision.get("implementation_run_id"),
                implementation_stream_token=decision.get("implementation_stream_token"),
            )
        return PlanDecision(decision="approved")

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

    def _context_profile_dict(self) -> Dict[str, Any]:
        return self._context_profile.to_dict()

    def _current_context_usage_payload(
        self,
        prompt_tokens_current_call: int,
        *,
        prompt_tokens_before_reduction: Optional[int] = None,
        reduction_stage: Optional[str] = None,
        checkpoint_fallback_activated: bool = False,
        raw_replay_counts: Optional[Dict[str, int]] = None,
        reduction_stages_applied: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        effective_budget = self._context_profile.effective_input_budget
        remaining = max(0, effective_budget - prompt_tokens_current_call)
        utilization_pct = (prompt_tokens_current_call / effective_budget * 100) if effective_budget else 0.0
        prompt_tokens_before = (
            prompt_tokens_current_call
            if prompt_tokens_before_reduction is None
            else prompt_tokens_before_reduction
        )
        pressure_threshold_tokens = self._coding_pressure_threshold_tokens()
        payload = {
            "context_window": self._context_profile.context_window,
            "reserved_output_tokens": self._context_profile.max_output_tokens,
            "effective_input_budget": effective_budget,
            "prompt_tokens_current_call": prompt_tokens_current_call,
            "prompt_tokens_before_reduction": prompt_tokens_before,
            "conversation_tokens_active_history": prompt_tokens_current_call,
            "utilization_pct_effective": round(utilization_pct, 1),
            "utilization_pct": round(utilization_pct, 1),
            "compaction_threshold_pct": self.COMPACTION_THRESHOLD_PCT,
            "pressure_threshold_tokens": pressure_threshold_tokens,
            "next_compaction_at_tokens": pressure_threshold_tokens,
            "remaining_tokens": remaining,
            "compactions_so_far": self._compaction_count,
            "compaction_count": self._compaction_count,
            "last_compacted_at_step": self._last_compacted_at_step,
            "pressure_ratio": round((prompt_tokens_current_call / effective_budget), 4)
            if effective_budget
            else 0.0,
            "pressure_ratio_before_reduction": round((prompt_tokens_before / effective_budget), 4)
            if effective_budget
            else 0.0,
            "reduction_stage": reduction_stage or "standard",
            "checkpoint_fallback_activated": checkpoint_fallback_activated,
            "reduction_stages_applied": reduction_stages_applied or [],
        }
        if raw_replay_counts is not None:
            payload["raw_replay_counts"] = raw_replay_counts
        return payload

    def _stored_context_usage_payload(
        self,
        *,
        stored_tokens: int,
        replayable_entry_count: int,
    ) -> Dict[str, Any]:
        """Build replayable stored-context usage payload."""
        context_window = self._context_profile.context_window
        utilization_pct = (stored_tokens / context_window * 100) if context_window else 0.0
        return {
            "context_window": context_window,
            "stored_tokens": stored_tokens,
            "utilization_pct": round(utilization_pct, 1),
            "replayable_entry_count": replayable_entry_count,
        }

    def _coding_pressure_threshold_tokens(self) -> int:
        """Return the prompt-token threshold that triggers coding pressure reduction."""
        effective_budget = self._context_profile.effective_input_budget
        return int(effective_budget * self.COMPACTION_THRESHOLD_PCT / 100)

    def _coding_prompt_pressure_metrics(self, prompt_tokens: int) -> Dict[str, Any]:
        """Return effective-budget pressure metrics for a coding prompt."""
        effective_budget = self._context_profile.effective_input_budget
        threshold_tokens = self._coding_pressure_threshold_tokens()
        return {
            "effective_input_budget": effective_budget,
            "pressure_threshold_tokens": threshold_tokens,
            "pressure_threshold_ratio": round(self.COMPACTION_THRESHOLD_PCT / 100, 3),
            "pressure_ratio": round((prompt_tokens / effective_budget), 4)
            if effective_budget
            else 0.0,
        }

    def _coding_replay_counts(
        self,
        transcript_entries: List[CodingSessionEntry],
        prompt_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        """Count replayed coding transcript/message categories for observability."""
        counts: Dict[str, int] = {
            "entries_total": len(transcript_entries),
            "user_entries": 0,
            "assistant_entries": 0,
            "assistant_tool_call_entries": 0,
            "tool_result_entries": 0,
            "checkpoint_entries": 0,
            "prompt_user_messages": 0,
            "prompt_assistant_messages": 0,
            "prompt_tool_messages": 0,
            "prompt_system_messages": 0,
        }
        for entry in transcript_entries:
            if entry.entry_type == "user":
                counts["user_entries"] += 1
            elif entry.entry_type == "assistant":
                counts["assistant_entries"] += 1
            elif entry.entry_type == "assistant_tool_calls":
                counts["assistant_tool_call_entries"] += 1
            elif entry.entry_type == "tool_result":
                counts["tool_result_entries"] += 1
            elif self._is_coding_compaction_summary_entry(entry):
                counts["checkpoint_entries"] += 1
        for message in prompt_messages or []:
            role = str(message.get("role") or "")
            if role == "user":
                counts["prompt_user_messages"] += 1
            elif role == "assistant":
                counts["prompt_assistant_messages"] += 1
            elif role == "tool":
                counts["prompt_tool_messages"] += 1
            elif role == "system":
                counts["prompt_system_messages"] += 1
        return counts

    def _clone_prompt_messages(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return a JSON-safe clone of prompt messages for transient reduction."""
        return json.loads(json.dumps(messages, ensure_ascii=False))

    async def _refresh_coding_stored_context(
        self,
        *,
        conversation_id: str,
        session_state: CodingSessionState,
        working_memory: Optional[WorkingMemory] = None,
    ) -> Optional[Dict[str, Any]]:
        """Refresh replayable stored-context metrics for the active coding conversation."""
        entry_records = await self._call_repo_async_method(
            "list_coding_session_entries",
            conversation_id,
            include_compacted=False,
        )
        transcript_entries = [
            CodingSessionEntry.from_dict(entry)
            for entry in (entry_records or [])
        ]
        builder = self._coding_context_builder()
        metadata_message = (
            working_memory.render_coding_metadata()
            if working_memory is not None
            else None
        )
        restored_file_messages = self._build_restored_file_messages(
            session_state=session_state,
            transcript_entries=transcript_entries,
            current_query=self._current_query or "",
        )
        stored_context = builder.build_stored_context(
            session_state=session_state,
            transcript_entries=transcript_entries,
            metadata_message=metadata_message,
            restored_file_messages=restored_file_messages,
        )
        payload = self._stored_context_usage_payload(
            stored_tokens=stored_context.token_count,
            replayable_entry_count=stored_context.replayable_entry_count,
        )
        self._last_stored_context = payload
        return payload

    def _shorten_with_head_tail(
        self,
        text: str,
        *,
        head_chars: int,
        tail_chars: int,
        marker: str = "\n... [truncated] ...\n",
    ) -> str:
        """Preserve head/tail evidence from long text."""
        if len(text) <= head_chars + tail_chars + len(marker):
            return text
        return text[:head_chars].rstrip() + marker + text[-tail_chars:].lstrip()

    def _reduce_coding_tool_content(
        self,
        *,
        tool_name: str,
        content: str,
        aggressive: bool = False,
    ) -> str:
        """Reduce bulky coding tool payloads while keeping grounded evidence."""
        if not content:
            return content
        budget_by_tool = {
            "read_file": 3200,
            "web_extract": 2200,
            "grep": 1800,
            "bash": 2200,
            "web_search": 1800,
        }
        target_chars = budget_by_tool.get(tool_name, 1600)
        if aggressive:
            target_chars = max(600, int(target_chars * 0.5))
        if len(content) <= target_chars:
            return content
        if tool_name in {"read_file", "grep"}:
            lines = content.splitlines()
            head_lines = 45 if not aggressive else 20
            tail_lines = 20 if not aggressive else 10
            if len(lines) <= head_lines + tail_lines + 4:
                return content[:target_chars]
            return "\n".join(
                [
                    *lines[:head_lines],
                    "... [middle omitted under prompt pressure] ...",
                    *lines[-tail_lines:],
                ]
            )
        return self._shorten_with_head_tail(
            content,
            head_chars=int(target_chars * 0.65),
            tail_chars=int(target_chars * 0.25),
            marker="\n... [reduced under prompt pressure] ...\n",
        )

    def _reduce_coding_tool_payloads(
        self,
        messages: List[Dict[str, Any]],
        *,
        aggressive: bool = False,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Stage 1: reduce large tool/file payloads before dialogue."""
        reduced = self._clone_prompt_messages(messages)
        changed = 0
        for message in reduced:
            if message.get("role") != "tool":
                continue
            tool_name = str(message.get("name") or "")
            content = str(message.get("content") or "")
            shrunk = self._reduce_coding_tool_content(
                tool_name=tool_name,
                content=content,
                aggressive=aggressive,
            )
            if shrunk != content:
                message["content"] = shrunk
                changed += 1
        return reduced, changed

    def _reduce_coding_tool_scaffolding(
        self,
        messages: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], int]:
        """Stage 2: reduce redundant assistant tool scaffolding before dialogue."""
        reduced = self._clone_prompt_messages(messages)
        changed = 0
        assistant_indices = [
            idx
            for idx, message in enumerate(reduced)
            if message.get("role") == "assistant" and message.get("tool_calls")
        ]
        protected = set(assistant_indices[-2:])
        for idx in assistant_indices:
            if idx in protected:
                continue
            message = reduced[idx]
            tool_calls = message.get("tool_calls") or []
            names = [
                str((tool_call.get("function") or {}).get("name") or "").strip()
                for tool_call in tool_calls
                if isinstance(tool_call, dict)
            ]
            names = [name for name in names if name]
            concise = (
                f"Called tool(s): {', '.join(names[:4])}"
                if names
                else "Called tool(s)."
            )
            if str(message.get("content") or "") != concise:
                message["content"] = concise
                changed += 1
        return reduced, changed

    def _reduce_coding_dialogue_context(
        self,
        messages: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], int]:
        """Stage 3: summarize older assistant/tool context while preserving user turns."""
        reduced = self._clone_prompt_messages(messages)
        changed = 0
        replay_indices = [
            idx
            for idx, message in enumerate(reduced)
            if message.get("role") in {"user", "assistant", "tool"}
        ]
        protected = set(replay_indices[-8:])
        for idx, message in enumerate(reduced):
            if idx in protected:
                continue
            role = message.get("role")
            if role == "user":
                continue
            if role == "assistant":
                content = str(message.get("content") or "").strip()
                tool_calls = message.get("tool_calls") or []
                if tool_calls:
                    names = [
                        str((tool_call.get("function") or {}).get("name") or "").strip()
                        for tool_call in tool_calls
                        if isinstance(tool_call, dict)
                    ]
                    concise = (
                        f"Earlier tool call: {', '.join(name for name in names[:4] if name)}"
                        if names
                        else "Earlier tool call."
                    )
                else:
                    concise = content if len(content) <= 220 else content[:217].rstrip() + "..."
                if concise != content:
                    message["content"] = concise
                    changed += 1
            elif role == "tool":
                tool_name = str(message.get("name") or "").strip()
                content = str(message.get("content") or "").strip()
                concise = self._reduce_coding_tool_content(
                    tool_name=tool_name,
                    content=content,
                    aggressive=True,
                )
                if concise != content:
                    message["content"] = concise
                    changed += 1
        return reduced, changed

    async def _prepare_coding_prompt_messages(
        self,
        *,
        conversation_id: str,
        run_id: str,
        query: str,
        step_number: int,
        system_prompt: str,
        session_state: CodingSessionState,
        working_memory: WorkingMemory,
    ) -> tuple[List[Dict[str, Any]], ContextBudget, Dict[str, Any]]:
        """Build coding prompt messages and reduce only under real prompt pressure."""
        (
            scaffold_messages,
            budget,
            transcript_entries,
            stored_payload,
            context_payload,
        ) = await self._build_coding_session_context_from_entries(
            conversation_id=conversation_id,
            system_prompt=system_prompt,
            query=query,
            session_state=session_state,
            working_memory=working_memory,
        )
        raw_prompt_messages = self._build_prompt_messages(
            scaffold_messages=scaffold_messages,
            working_memory=working_memory,
        )
        raw_prompt_tokens = self._pruner.estimate_tokens(raw_prompt_messages)
        effective_budget = self._context_profile.effective_input_budget
        threshold_tokens = self._coding_pressure_threshold_tokens()
        replay_counts = self._coding_replay_counts(transcript_entries, raw_prompt_messages)
        reduction_stages_applied: List[str] = []
        reduction_stage = "stage0_full_raw_replay"
        checkpoint_fallback_activated = False

        prompt_messages = raw_prompt_messages
        prompt_tokens = raw_prompt_tokens
        if prompt_tokens >= threshold_tokens:
            stage1_messages, stage1_changed = self._reduce_coding_tool_payloads(prompt_messages)
            if stage1_changed:
                prompt_messages = stage1_messages
                prompt_tokens = self._pruner.estimate_tokens(prompt_messages)
                reduction_stage = "stage1_tool_payload_reduced"
                reduction_stages_applied.append(reduction_stage)

            if prompt_tokens >= threshold_tokens:
                stage2_messages, stage2_changed = self._reduce_coding_tool_scaffolding(prompt_messages)
                if stage2_changed:
                    prompt_messages = stage2_messages
                    prompt_tokens = self._pruner.estimate_tokens(prompt_messages)
                    reduction_stage = "stage2_tool_scaffolding_reduced"
                    reduction_stages_applied.append(reduction_stage)

            if prompt_tokens >= threshold_tokens:
                stage3_messages, stage3_changed = self._reduce_coding_dialogue_context(prompt_messages)
                if stage3_changed:
                    prompt_messages = stage3_messages
                    prompt_tokens = self._pruner.estimate_tokens(prompt_messages)
                    reduction_stage = "stage3_context_summarized"
                    reduction_stages_applied.append(reduction_stage)

            if prompt_tokens >= threshold_tokens:
                checkpoint_fallback_activated = await self._compact_coding_session_history(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    step_number=step_number,
                    session_state=session_state,
                    working_memory=working_memory,
                    prompt_tokens_before_reduction=raw_prompt_tokens,
                    raw_replay_counts=replay_counts,
                    reduction_stages_applied=reduction_stages_applied,
                )
                if checkpoint_fallback_activated:
                    reduction_stage = "stage4_checkpoint_fallback"
                    reduction_stages_applied.append(reduction_stage)
                    (
                        scaffold_messages,
                        budget,
                        transcript_entries,
                        stored_payload,
                        context_payload,
                    ) = await self._build_coding_session_context_from_entries(
                        conversation_id=conversation_id,
                        system_prompt=system_prompt,
                        query=query,
                        session_state=session_state,
                        working_memory=working_memory,
                    )
                    prompt_messages = self._build_prompt_messages(
                        scaffold_messages=scaffold_messages,
                        working_memory=working_memory,
                    )
                    replay_counts = self._coding_replay_counts(
                        transcript_entries,
                        prompt_messages,
                    )
                    prompt_tokens = self._pruner.estimate_tokens(prompt_messages)
                    if prompt_tokens >= threshold_tokens:
                        prompt_messages, _ = self._reduce_coding_tool_payloads(
                            prompt_messages,
                            aggressive=True,
                        )
                        prompt_messages, _ = self._reduce_coding_tool_scaffolding(prompt_messages)
                        prompt_messages, _ = self._reduce_coding_dialogue_context(prompt_messages)
                        prompt_tokens = self._pruner.estimate_tokens(prompt_messages)

        if prompt_tokens > effective_budget:
            prune_iterations = 0
            while prompt_tokens > effective_budget and prune_iterations < 20:
                prune_iterations += 1
                prompt_messages = self._force_prune_largest(prompt_messages, {})
                prompt_tokens = self._pruner.estimate_tokens(prompt_messages)
            if prune_iterations:
                reduction_stage = "stage5_emergency_prune"
                reduction_stages_applied.append(reduction_stage)

        usage_payload = self._current_context_usage_payload(
            prompt_tokens,
            prompt_tokens_before_reduction=raw_prompt_tokens,
            reduction_stage=reduction_stage,
            checkpoint_fallback_activated=checkpoint_fallback_activated,
            raw_replay_counts=replay_counts,
            reduction_stages_applied=reduction_stages_applied,
        )
        usage_payload["final_pressure_ratio"] = round(
            (prompt_tokens / effective_budget), 4
        ) if effective_budget else 0.0

        await self._add_trace_event(
            run_id=run_id,
            event_type="coding_session_context_load",
            content={
                **context_payload,
                **self._coding_prompt_pressure_metrics(raw_prompt_tokens),
                "context_phase": "final_prompt",
                "prompt_tokens_before_reduction": raw_prompt_tokens,
                "prompt_tokens_final": prompt_tokens,
                "stored_context": stored_payload,
                "raw_replay_counts": replay_counts,
                "reduction_stage": reduction_stage,
                "reduction_stages_applied": reduction_stages_applied,
                "checkpoint_fallback_activated": checkpoint_fallback_activated,
            },
            actor="system",
            step_number=step_number,
        )
        return prompt_messages, budget, usage_payload

    def _is_compaction_message(self, message: Dict[str, Any]) -> bool:
        return message.get("role") == "system" and str(message.get("content") or "").startswith(self.COMPACTION_PREFIX)

    def _find_latest_compaction_index(self, messages: List[Dict[str, Any]]) -> Optional[int]:
        for idx in range(len(messages) - 1, -1, -1):
            if self._is_compaction_message(messages[idx]):
                return idx
        return None

    def _tool_log_entries_up_to_step(self, step_number: int) -> List[Dict[str, Any]]:
        return [entry for entry in self._tool_call_log if entry.get("step_number", 0) <= step_number]

    def _build_compaction_summary(
        self,
        messages_to_compact: List[Dict[str, Any]],
        step_number: int,
    ) -> str:
        user_messages = [
            str(m.get("content") or "").strip()
            for m in messages_to_compact
            if m.get("role") == "user" and str(m.get("content") or "").strip()
        ]
        assistant_messages = [
            str(m.get("content") or "").strip()
            for m in messages_to_compact
            if m.get("role") == "assistant" and str(m.get("content") or "").strip()
        ]
        working_memory_blocks = [
            str(m.get("content") or "").strip()
            for m in messages_to_compact
            if m.get("role") == "system"
            and str(m.get("content") or "").startswith("WORKING MEMORY")
        ]
        tool_entries = self._tool_log_entries_up_to_step(step_number)

        files_inspected: List[str] = []
        files_changed: List[str] = []
        command_outcomes: List[str] = []
        web_sources: List[str] = []
        findings: List[str] = []

        for entry in tool_entries:
            tool_name = entry.get("tool_name", "")
            arguments = entry.get("arguments", {}) or {}
            summary = str(entry.get("result_summary") or "").strip()
            if tool_name == "read_file" and arguments.get("file_path"):
                files_inspected.append(str(arguments.get("file_path")))
            elif tool_name == "grep" and arguments.get("path"):
                files_inspected.append(str(arguments.get("path")))
            elif tool_name in {"write_file", "edit_file"} and arguments.get("file_path"):
                files_changed.append(str(arguments.get("file_path")))
            elif tool_name == "apply_patch":
                changed = (entry.get("result_metadata") or {}).get("changed_files") or []
                files_changed.extend(str(item) for item in changed[:8])
            elif tool_name in {"bash", "exec_command", "write_stdin"} and summary:
                command_outcomes.append(summary)
            elif tool_name == "web_extract":
                for url in arguments.get("urls", [])[:2]:
                    web_sources.append(str(url))
            elif tool_name == "web_search" and summary:
                findings.append(summary)
            if summary and tool_name in {"read_file", "grep", "python_execute", "web_extract"}:
                findings.append(summary)

        def _uniq(items: List[str], limit: int) -> List[str]:
            seen = []
            for item in items:
                clean = item.strip()
                if clean and clean not in seen:
                    seen.append(clean)
                if len(seen) >= limit:
                    break
            return seen

        if self._profile and self._profile.name == "coding":
            sections = [
                self.COMPACTION_PREFIX,
                "",
                "Compacted coding context:",
                f"- Repo/workspace: {getattr(self._profile, 'name', 'coding')} profile active.",
            ]
            if user_messages:
                sections.append(f"- User goals and constraints: {' | '.join(_uniq(user_messages, 3))[:1200]}")
            if working_memory_blocks:
                durable_state = (
                    working_memory_blocks[-1].replace("WORKING MEMORY", "", 1).strip()
                )
                sections.append(f"- Durable working state preserved:\n{durable_state[:2200]}")
            if files_inspected:
                sections.append(f"- Files inspected: {', '.join(_uniq(files_inspected, 12))}")
            if files_changed:
                sections.append(f"- Files changed: {', '.join(_uniq(files_changed, 12))}")
            if command_outcomes:
                sections.append(f"- Command outcomes: {'; '.join(_uniq(command_outcomes, 6))[:1200]}")
            if findings:
                sections.append(f"- Important findings: {'; '.join(_uniq(findings, 6))[:1200]}")
            if web_sources:
                sections.append(f"- Sources consulted: {', '.join(_uniq(web_sources, 6))}")
            if assistant_messages:
                sections.append(f"- Unresolved implementation state: {assistant_messages[-1][:700]}")
            sections.append(f"- Runtime state: model={self._context_profile.display_name}, compactions={self._compaction_count + 1}.")
            return "\n".join(sections)

        sections = [
            self.COMPACTION_PREFIX,
            "",
            "Compacted conversation context:",
        ]
        if user_messages:
            sections.append(f"- User intent: {' | '.join(_uniq(user_messages, 3))[:1200]}")
        if working_memory_blocks:
            durable_state = (
                working_memory_blocks[-1].replace("WORKING MEMORY", "", 1).strip()
            )
            sections.append(f"- Durable working state preserved:\n{durable_state[:1600]}")
        if findings:
            sections.append(f"- Important facts: {'; '.join(_uniq(findings, 6))[:1200]}")
        if assistant_messages:
            sections.append(f"- Conclusions so far: {assistant_messages[-1][:900]}")
        sections.append("- Open questions: continue from the most recent raw messages after this compaction.")
        return "\n".join(sections)

    def _compact_conversation(
        self,
        messages: List[Dict[str, Any]],
        step_number: int,
    ) -> List[Dict[str, Any]]:
        if len(messages) <= 2:
            return messages
        base_system = messages[0]
        latest_compaction_idx = self._find_latest_compaction_index(messages)
        tail_messages: List[Dict[str, Any]] = []
        if messages and messages[-1].get("role") == "user":
            tail_messages = [messages[-1]]

        cutoff_end = len(messages) - len(tail_messages)
        start_idx = 1
        if latest_compaction_idx is not None:
            start_idx = latest_compaction_idx
        messages_to_compact = messages[start_idx:cutoff_end]
        if not messages_to_compact:
            return messages

        summary = self._build_compaction_summary(messages_to_compact, step_number)
        compacted = [base_system, {"role": "system", "content": summary}] + tail_messages
        self._compaction_count += 1
        self._last_compacted_at_step = step_number
        return compacted

    def _enforce_prompt_budget(
        self,
        messages: List[Dict[str, Any]],
        step_number: int,
        *,
        enable_compaction: bool = True,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
        effective_budget = self._context_profile.effective_input_budget
        threshold_tokens = int(effective_budget * self.COMPACTION_THRESHOLD_PCT / 100)
        prompt_tokens = self._pruner.estimate_tokens(messages)
        compacted_now = False

        if enable_compaction and prompt_tokens >= threshold_tokens:
            compacted_messages = self._compact_conversation(messages, step_number)
            if compacted_messages is not messages:
                messages = compacted_messages
                prompt_tokens = self._pruner.estimate_tokens(messages)
                compacted_now = True

        if prompt_tokens > effective_budget:
            prune_iterations = 0
            while prompt_tokens > effective_budget and prune_iterations < 20:
                prune_iterations += 1
                messages = self._force_prune_largest(messages, {})
                prompt_tokens = self._pruner.estimate_tokens(messages)
            if prune_iterations:
                logger.warning(
                    "Emergency prompt truncation applied after compaction",
                    extra={
                        "step_number": step_number,
                        "prune_iterations": prune_iterations,
                        "prompt_tokens": prompt_tokens,
                        "effective_budget": effective_budget,
                    },
                )

        usage_payload = self._current_context_usage_payload(prompt_tokens)
        return messages, usage_payload, compacted_now

    def _record_usage(
        self,
        raw_usage: dict[str, Any] | None,
        *,
        prompt_messages: Optional[List[Dict[str, Any]]] = None,
        output_text: Optional[str] = None,
        reasoning_text: Optional[str] = None,
    ) -> dict[str, int]:
        """Normalize and accumulate LLM token usage, with local fallback for providers that omit usage."""
        usage = normalize_usage(raw_usage)
        if usage.get("input_tokens", 0) == 0 and usage.get("output_tokens", 0) == 0 and prompt_messages is not None:
            from orchestrator.utils.tokens import get_token_counter

            token_counter = get_token_counter()
            input_tokens = self._pruner.estimate_tokens(prompt_messages)
            output_tokens = token_counter.count_tokens(output_text or "")
            reasoning_tokens = token_counter.count_tokens(reasoning_text or "")
            usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cached_tokens": 0,
                "total_tokens": input_tokens + output_tokens,
            }
        add_usage(self._usage_totals, usage)
        self._total_tokens = self._usage_totals.get("total_tokens", 0)
        return usage

    def _current_cost(self) -> Optional[dict[str, Any]]:
        """Return estimated cost for accumulated usage, if pricing is known."""
        return estimate_cost(
            self._usage_totals,
            self._input_cost_per_million,
            self._output_cost_per_million,
            self._cached_input_cost_per_million,
        )

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

    async def _build_initial_messages(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        run_id: Optional[str] = None,
        coding_session_state: Optional[CodingSessionState] = None,
        working_memory: Optional[WorkingMemory] = None,
        coding_session_use_entries: bool = True,
    ) -> tuple[List[Dict[str, Any]], ContextBudget]:
        """Build initial message list with system prompt, history, and query.

        Non-coding profiles use HistoryBuilder turn summaries. Coding-profile
        continuity rebuilds prompt context directly from persisted
        coding-session transcript entries keyed by conversation_id.

        Args:
            query: User's research query.
            conversation_id: Optional conversation ID to load history from.

        Returns:
            Tuple of (message list, ContextBudget accounting).
        """
        from orchestrator.utils.tokens import get_token_counter

        # Fallback: build from scratch (first message or no prior context)

        # Build system prompt: if profile is set, the factory already formatted
        # the prompt with date_context and project_context. Otherwise, inject
        # date context for backward compatibility.
        system_prompt = self._resolved_system_prompt()

        # Load conversation history
        prior_runs: list[dict] = []
        if conversation_id and self._trace_repo:
            prior_runs = await self._trace_repo.list_runs_for_conversation(
                conversation_id
            )

        if (
            self._is_coding_profile()
            and conversation_id
            and coding_session_state is not None
            and coding_session_use_entries
        ):
            messages, budget = await self._load_coding_session_messages(
                conversation_id=conversation_id,
                system_prompt=system_prompt,
                query=query,
                run_id=run_id or "coding-session-context",
                session_state=coding_session_state,
                working_memory=working_memory,
                use_session_entries=coding_session_use_entries,
            )
            return messages, budget

        builder = HistoryBuilder(
            token_counter=get_token_counter(),
            max_context_tokens=self._max_context_tokens,
            reserve_for_response=self._max_tokens,
        )

        messages, budget = builder.build_history_messages(
            prior_runs=prior_runs,
            system_prompt=system_prompt,
            current_query=query,
        )

        logger.info(
            "Context budget allocated",
            extra={
                "history_tokens": budget.history_tokens,
                "available_for_history": budget.available_for_history,
                "utilization_pct": round(budget.utilization_pct, 1),
                "history_pairs": (len(messages) - 2) // 2,  # exclude system + current query
            },
        )

        return messages, budget

    async def _call_llm_with_tools(
        self,
        messages: List[Dict[str, Any]],
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
        tool_choice: Optional[str] = None,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
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
        tool_schemas = tool_schemas if tool_schemas is not None else self._available_tool_schemas()
        messages = self._normalize_system_messages(messages)
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

            Pass tokens through raw — any cleanup (stripping tool_call XML,
            think tags, etc.) happens on the frontend in ThinkingPanel.
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
            effective_max_tokens, extra_kwargs = self._reasoning_provider_kwargs()

            response = await self._provider.complete_streaming(
                messages=messages,
                model=self._model_name,
                on_token=on_token,
                on_reasoning=on_reasoning,
                tools=tool_schemas if tool_schemas else None,
                tool_choice=tool_choice,
                max_tokens=effective_max_tokens,
                temperature=self._temperature,
                **extra_kwargs,
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

    def _parse_xml_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse Qwen-style XML tool calls from text.

        Qwen models output tool calls in this format:
            <tool_call>
            <function=web_extract>
            <parameter=urls>["http://example.com"]</parameter>
            </function>
            </tool_call>

        Also handles truncated/incomplete XML where closing tags are missing
        (e.g., model hit token limit mid-tool-call).

        Args:
            text: Text that may contain XML tool call blocks.

        Returns:
            List of tool call dicts in OpenAI format, or None if no tool calls found.
        """
        import re
        import uuid

        if not text or "<tool_call>" not in text:
            return None

        tool_calls = []

        # Match <tool_call> blocks — closing tag optional (handles truncation)
        for block in re.finditer(
            r"<tool_call>\s*(.*?)(?:</tool_call>|\Z)", text, re.DOTALL
        ):
            body = block.group(1)

            # Extract function name: <function=NAME>
            func_match = re.search(r"<function=(\w+)>", body)
            if not func_match:
                continue
            func_name = func_match.group(1)

            # Extract parameters — closing tag optional (handles truncation)
            params = {}
            for param in re.finditer(
                r"<parameter=(\w+)>\s*(.*?)(?:</parameter>|<(?:parameter|/function|/tool_call)|\Z)",
                body, re.DOTALL,
            ):
                key = param.group(1)
                value = param.group(2).strip()
                if not value:
                    continue
                # Try to parse as JSON (lists, dicts, numbers)
                try:
                    params[key] = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    params[key] = value

            if not params:
                continue

            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": json.dumps(params),
                },
            })

            logger.info(
                "Parsed XML tool call (Qwen format)",
                extra={
                    "tool_name": func_name,
                    "param_keys": list(params.keys()),
                },
            )

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
                raw_arguments_value = func.get("arguments", "{}")
                parse_error: Optional[str] = None

                if isinstance(raw_arguments_value, dict):
                    arguments = raw_arguments_value
                    args_str = json.dumps(raw_arguments_value, ensure_ascii=False)
                else:
                    args_str = str(raw_arguments_value)
                    try:
                        arguments = json.loads(args_str)
                    except json.JSONDecodeError as exc:
                        arguments = {}
                        parse_error = (
                            "its arguments did not parse into valid JSON "
                            f"({exc.msg})."
                        )

                if not parse_error and not isinstance(arguments, dict):
                    parse_error = (
                        "its arguments did not parse into a JSON object with named fields."
                    )
                    arguments = {}

                parsed.append(
                    ParsedToolCall(
                        id=tc_id,
                        name=name,
                        arguments=arguments,
                        raw_arguments=args_str,
                        parse_error=parse_error,
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse tool call", extra={"error": str(e)})
                continue

        return parsed

    # Tools safe to execute in parallel (read-only, no side effects)
    PARALLEL_TOOLS = frozenset({
        "read_file", "view_image", "grep", "glob", "list_directory",
        "web_search", "web_extract",
    })

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        state_machine: AgentStateMachine,
        step_number: int,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
        step_metadata: Dict[str, int],
    ) -> List[tuple["ParsedToolCall", "ToolResult"]]:
        """Execute tool calls, parallelizing read-only tool execution.

        Read-only tools (read_file, grep, glob, list_directory, web_search,
        web_extract) have their tool.execute() calls run concurrently via
        asyncio.gather. All DB bookkeeping (state machine, tracing) runs
        serially to avoid SQLite transaction contention.

        Args:
            tool_calls: List of tool call dicts in OpenAI format.
            state_machine: State machine for recording.
            step_number: Current step number.
            event_callback: SSE callback.
            run_id: Run ID.
            step_metadata: Metadata dict to update.

        Returns:
            List of (ParsedToolCall, ToolResult) tuples in original order.
        """
        from orchestrator.agent.tools.base import ToolResult

        results: List[tuple[ParsedToolCall, ToolResult]] = []

        parsed_calls = self._parse_tool_calls(tool_calls)

        # Phase 1: Pre-execution bookkeeping (serial — DB writes)
        # Collect (tool_call, tc_record, tool_call_event_id, tool_obj, execute_coro_or_result)
        prepared: List[Dict[str, Any]] = []

        for tool_call in parsed_calls:
            prep = await self._prepare_tool_call(
                tool_call, state_machine, step_number,
                event_callback, run_id,
            )
            prepared.append(prep)

            # Early return for cached/denied results
            if prep.get("early_result"):
                continue

        # Phase 2: Execute tools — parallel for read-only, serial for mutating
        parallel_indices: List[int] = []
        serial_indices: List[int] = []
        for i, prep in enumerate(prepared):
            if prep.get("early_result"):
                continue  # Already resolved
            if parsed_calls[i].name in self.PARALLEL_TOOLS:
                parallel_indices.append(i)
            else:
                serial_indices.append(i)

        # Run read-only tool.execute() calls in parallel
        if parallel_indices:
            async def _safe_execute(prep: Dict[str, Any]) -> ToolResult:
                tool = prep["tool"]
                tc = prep["tool_call"]
                try:
                    return await tool.execute(**tc.arguments)
                except Exception as e:
                    logger.error(
                        "Tool execution failed",
                        extra={"tool": tc.name, "error": str(e)},
                    )
                    return ToolResult(
                        success=False,
                        result_summary=f"Tool error: {str(e)[:100]}",
                        error_message=str(e),
                        duration_ms=0,
                    )

            parallel_results = await asyncio.gather(
                *[_safe_execute(prepared[i]) for i in parallel_indices]
            )
            for idx, result in zip(parallel_indices, parallel_results):
                prepared[idx]["result"] = result

        # Run mutating tools serially
        for idx in serial_indices:
            prep = prepared[idx]
            tool = prep["tool"]
            tc = prep["tool_call"]
            try:
                prep["result"] = await tool.execute(**tc.arguments)
            except Exception as e:
                logger.error(
                    "Tool execution failed",
                    extra={"tool": tc.name, "error": str(e)},
                )
                prep["result"] = ToolResult(
                    success=False,
                    result_summary=f"Tool error: {str(e)[:100]}",
                    error_message=str(e),
                    duration_ms=0,
                )

        # Phase 3: Post-execution bookkeeping (serial — DB writes)
        for prep in prepared:
            tool_call = prep["tool_call"]

            if prep.get("early_result"):
                result = prep["early_result"]

                # Finalize early results that went through bookkeeping
                # (skip cached results which don't have tool_call_event_id key)
                if "tool_call_event_id" in prep:
                    await self._finalize_tool_call(
                        tool_call, result, prep["tc_record"],
                        prep.get("tool_call_event_id"),
                        state_machine, step_number,
                        event_callback, run_id,
                    )
            else:
                result = prep["result"]

                # Post-execution recording
                await self._finalize_tool_call(
                    tool_call, result, prep["tc_record"],
                    prep.get("tool_call_event_id"),
                    state_machine, step_number,
                    event_callback, run_id,
                )

            results.append((tool_call, result))

            freshness_metadata = self._track_file_freshness(tool_call, result)
            state_changed = self._did_tool_call_change_state(tool_call.name, result)
            if state_changed:
                self._tool_state_version += 1

            # Log tool call for run metrics
            self._tool_call_log.append({
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "success": result.success,
                "result_summary": result.result_summary,
                "step_number": step_number,
                "state_version_after": self._tool_state_version,
                "result_metadata": dict(result.metadata) if isinstance(result.metadata, dict) else {},
                **freshness_metadata,
            })

        return results

    async def _prepare_tool_call(
        self,
        tool_call: "ParsedToolCall",
        state_machine: AgentStateMachine,
        step_number: int,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
    ) -> Dict[str, Any]:
        """Pre-execution bookkeeping for a tool call.

        Handles idempotency checks, state machine recording, tracing,
        and approval gates. Returns a dict with preparation state.

        Args:
            tool_call: Parsed tool call.
            state_machine: State machine.
            step_number: Current step.
            event_callback: SSE callback.
            run_id: Run ID.

        Returns:
            Dict with keys: tool_call, tc_record, tool_call_event_id,
            tool (or None), early_result (if resolved early).
        """
        from orchestrator.agent.tools.base import ToolResult

        prep: Dict[str, Any] = {"tool_call": tool_call}

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
        prep["tc_record"] = tc_record

        # Check if this was a duplicate (idempotent retry)
        if tc_record.get("id") != tool_call.id:
            if tc_record.get("status") == "success":
                logger.debug(
                    "Using cached tool result", extra={"key": idempotency_key}
                )
                prep["early_result"] = ToolResult(
                    success=True,
                    result_summary=tc_record.get("result_summary", ""),
                    error_message=None,
                )
                return prep
            else:
                logger.debug(
                    "Ignoring cached failure, re-executing tool",
                    extra={"key": idempotency_key, "status": tc_record.get("status")},
                )

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
        prep["tool_call_event_id"] = tool_call_event_id

        # Mark as running
        await state_machine.start_tool_execution(tc_record["id"])

        # Get tool
        tool = self._registry.get(tool_call.name)
        if tool is None:
            available_tools = list(self._registry._tools.keys())
            prep["early_result"] = ToolResult(
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
            return prep

        if (
            self._collaboration_mode == "plan"
            and tool_call.name in PLAN_MODE_MUTATING_TOOLS
        ):
            prep["early_result"] = ToolResult(
                success=False,
                result_summary=f"Blocked {tool_call.name} in Plan Mode",
                error_message=(
                    "Plan Mode is read-only. Do not modify files, run commands, "
                    "execute Python, or apply patches. Continue planning using "
                    "inspection tools only, then produce a <proposed_plan> block."
                ),
                duration_ms=0,
            )
            return prep

        # Validate required arguments
        required_args = tool.schema.parameters.get("required", [])
        missing_args = [arg for arg in required_args if arg not in tool_call.arguments]
        if missing_args:
            arg_list = ", ".join(f"'{a}'" for a in missing_args)
            prep["early_result"] = ToolResult(
                success=False,
                result_summary=f"Missing required args: {arg_list}",
                error_message=(
                    f"Missing required argument(s): {arg_list}. "
                    f"The {tool_call.name} tool requires these parameters."
                ),
                duration_ms=0,
            )
            return prep

        if tool_call.name == "read_file" and self._active_coding_session_state is not None:
            reread_payload = self._classify_coding_file_read_reason(tool_call)
            if reread_payload is not None:
                await self._add_trace_event(
                    run_id=run_id,
                    event_type="coding_session_file_reread",
                    content={
                        "conversation_id": self._active_conversation_id,
                        **reread_payload,
                    },
                    actor="system",
                    step_number=step_number,
                )

        # Permission gate
        permission_level = getattr(tool.schema, "permission_level", "auto")
        workspace_path = self._get_workspace_path()
        permission_decision = classify_tool_call(
            policy=self._permission_policy,
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            base_permission_level=permission_level,
            workspace_path=workspace_path,
        )
        permission_level = permission_decision.permission_level
        needs_approval = (
            permission_decision.needs_approval
            and self._approval_callback is not None
        )

        if needs_approval:
            # Compute diff preview before showing approval
            diff_preview = None
            if tool_call.name == "write_file":
                diff_preview = self._compute_write_diff_preview(tool_call.arguments)
            elif tool_call.name == "edit_file":
                diff_preview = self._compute_edit_diff_preview(tool_call.arguments)
            elif tool_call.name == "apply_patch":
                diff_preview = str(tool_call.arguments.get("patch", ""))[:5000]

            self._emit(
                event_callback,
                "tool_approval_required",
                run_id=run_id,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                permission_level=permission_level,
                diff_preview=diff_preview,
            )
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

            await state_machine.record_approval(
                tool_call_id=tc_record["id"],
                decision="approved" if approved else "denied",
                policy=self._permission_policy,
            )

            if not approved:
                denial_msg = (
                    f"The user DENIED this {tool_call.name} call. "
                    f"This is NOT a permissions error — the user rejected this specific action. "
                    f"Do NOT give up or say you lack permission. Instead:\n"
                    f"- Ask the user what they'd like you to do differently\n"
                    f"- Or try a different approach (e.g. edit_file instead of write_file)\n"
                    f"Continue working on the user's request."
                )
                result = ToolResult(
                    success=False,
                    result_summary=f"User denied {tool_call.name} — ask user for guidance",
                    error_message=denial_msg,
                    duration_ms=0,
                )
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
                prep["early_result"] = result
                return prep
        else:
            await state_machine.record_approval(
                tool_call_id=tc_record["id"],
                decision="auto",
                policy=self._permission_policy,
            )

        prep["tool"] = tool
        return prep

    def _get_workspace_path(self) -> Optional[str]:
        """Return the browser agent workspace path, if available."""
        for tool_name in ("exec_command", "apply_patch", "bash", "read_file", "write_file", "edit_file"):
            tool = self._registry.get(tool_name)
            working_dir = getattr(tool, "_working_dir", None)
            if isinstance(working_dir, Path):
                return str(working_dir)
        return None

    def _requested_read_span(
        self,
        tool_call: ParsedToolCall,
    ) -> tuple[Optional[int], Optional[int]]:
        """Return the requested read span from tool arguments."""
        offset = tool_call.arguments.get("offset", 1)
        limit = tool_call.arguments.get("limit")
        try:
            line_start = max(1, int(offset))
        except (TypeError, ValueError):
            line_start = 1
        try:
            limit_int = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            limit_int = None
        if limit_int is not None and limit_int > 0:
            return line_start, line_start + limit_int - 1
        return line_start, None

    def _classify_coding_file_read_reason(
        self,
        tool_call: ParsedToolCall,
    ) -> Optional[dict[str, Any]]:
        """Classify why a coding run is rereading a file."""
        session_state = self._active_coding_session_state
        if tool_call.name != "read_file" or session_state is None:
            return None
        path = self._canonical_workspace_path(
            str(tool_call.arguments.get("file_path", "unknown"))
        )
        file_state = session_state.file_evidence.get(path)
        line_start, line_end = self._requested_read_span(tool_call)
        if file_state is None:
            if path in session_state.read_files or path in session_state.modified_files:
                return {
                    "path": path,
                    "reason": "missing_evidence",
                    "detail": "Stored file history exists but concrete evidence is missing.",
                    "line_start": line_start,
                    "line_end": line_end,
                }
            return {
                "path": path,
                "reason": "new_file_needed",
                "detail": "This file has not been captured in the coding session yet.",
                "line_start": line_start,
                "line_end": line_end,
            }
        is_fresh, reason_code, detail = self._assess_file_freshness(file_state)
        if not is_fresh:
            return {
                "path": path,
                "reason": reason_code or "stale_hash",
                "detail": detail,
                "line_start": line_start,
                "line_end": line_end,
            }
        if not file_state.spans:
            return {
                "path": path,
                "reason": "missing_evidence",
                "detail": "Stored file state has no reusable spans.",
                "line_start": line_start,
                "line_end": line_end,
            }
        if not file_state.covers_range(line_start, line_end):
            return {
                "path": path,
                "reason": "span_insufficient",
                "detail": "Stored evidence does not cover the requested line range.",
                "line_start": line_start,
                "line_end": line_end,
            }
        return {
            "path": path,
            "reason": "explicit_model_request",
            "detail": "Fresh stored evidence already covered this file span.",
            "line_start": line_start,
            "line_end": line_end,
        }

    async def _finalize_tool_call(
        self,
        tool_call: "ParsedToolCall",
        result: "ToolResult",
        tc_record: Dict[str, Any],
        tool_call_event_id: Optional[str],
        state_machine: AgentStateMachine,
        step_number: int,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
    ) -> None:
        """Post-execution bookkeeping for a tool call.

        Records completion, artifacts, citations, findings, and emits events.

        Args:
            tool_call: Parsed tool call.
            result: Execution result.
            tc_record: State machine tool call record.
            tool_call_event_id: Trace event ID for the tool call.
            state_machine: State machine.
            step_number: Current step.
            event_callback: SSE callback.
            run_id: Run ID.
        """
        # Capture full result_detail for write tools
        result_detail = None
        if tool_call.name in ("write_file", "edit_file", "apply_patch", "bash", "exec_command", "write_stdin", "update_plan_doc") and result.result_data:
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
        if result.success and tool_call.name in ("write_file", "edit_file", "apply_patch", "bash", "exec_command", "write_stdin", "update_plan_doc"):
            artifact_type = {
                "write_file": "file_write",
                "edit_file": "file_edit",
                "apply_patch": "file_patch",
                "bash": "command_run",
                "exec_command": "command_run",
                "write_stdin": "command_run",
                "update_plan_doc": "plan_doc",
            }.get(tool_call.name, tool_call.name)
            result_data_path = (
                result.result_data.get("file_path", "")
                if isinstance(result.result_data, dict)
                else ""
            )
            file_path = tool_call.arguments.get(
                "file_path",
                tool_call.arguments.get(
                    "command",
                    tool_call.arguments.get(
                        "cmd",
                        result_data_path,
                    ),
                ),
            )
            try:
                await self._repo.create_run_artifact(
                    run_id=run_id,
                    artifact_type=artifact_type,
                    file_path=file_path,
                    action=(
                        "updated"
                        if tool_call.name == "update_plan_doc"
                        else tool_call.name
                    ),
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

        # Emit tool result event (include diff data and command output details)
        emit_kwargs: Dict[str, Any] = {
            "run_id": run_id,
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.name,
            "success": result.success,
            "result_summary": result.result_summary,
            "duration_ms": result.duration_ms,
        }
        diff_data = display_result_data(tool_call.name, result.result_data)
        if diff_data:
            emit_kwargs["result_data"] = diff_data
        bash_output = bash_output_from_result_data(result.result_data)
        if tool_call.name in {"bash", "exec_command", "write_stdin"} and bash_output:
            emit_kwargs["bash_output"] = bash_output
        self._emit(event_callback, "tool_result", **emit_kwargs)
        if tool_call.name == "update_plan_doc" and result.success:
            result_data = result.result_data if isinstance(result.result_data, dict) else {}
            self._emit(
                event_callback,
                "plan_doc_updated",
                run_id=run_id,
                file_path=result_data.get("file_path", ""),
                action="updated",
                bytes=result_data.get("bytes"),
                summary=result_data.get("summary", result.result_summary),
                diff=result_data.get("diff"),
                step_number=step_number,
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

    def _compute_write_diff_preview(self, arguments: Dict[str, Any]) -> Optional[str]:
        """Compute a unified diff preview for write_file before approval.

        Reads the existing file and diffs against the proposed content.
        Returns None for new files or if the file can't be read.

        Args:
            arguments: write_file arguments with file_path and content.

        Returns:
            Unified diff string (capped at 5KB), or None.
        """
        import difflib
        from pathlib import Path

        file_path = arguments.get("file_path", "")
        new_content = arguments.get("content", "")
        if not file_path:
            return None

        try:
            # Resolve path the same way the tool does
            path = Path(file_path)
            if not path.is_absolute():
                # Use registry's working dir if available
                tool = self._registry.get("write_file")
                if tool and hasattr(tool, "_working_dir"):
                    path = tool._working_dir / path
                path = path.resolve()

            old_content = ""
            if path.exists():
                old_content = path.read_text(encoding="utf-8")
            if old_content == new_content:
                return None  # No changes

            display_name = path.name
            try:
                tool = self._registry.get("write_file")
                if tool and hasattr(tool, "_working_dir"):
                    display_name = str(path.relative_to(tool._working_dir))
            except Exception:
                display_name = path.name

            diff_lines = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{display_name}",
                tofile=f"b/{display_name}",
                n=3,
            )
            diff_text = "".join(diff_lines)
            # Cap at 5KB to keep approval UI manageable
            if len(diff_text) > 5000:
                diff_text = diff_text[:5000] + "\n... (diff truncated)"
            return diff_text or None
        except Exception:
            return None

    def _compute_edit_diff_preview(self, arguments: Dict[str, Any]) -> Optional[str]:
        """Compute a unified diff preview for edit_file before approval.

        Uses old_string/new_string from arguments to show the change.

        Args:
            arguments: edit_file arguments with old_string and new_string.

        Returns:
            Unified diff string (capped at 5KB), or None.
        """
        import difflib

        old_string = arguments.get("old_string", "")
        new_string = arguments.get("new_string", "")
        file_path = arguments.get("file_path", "unknown")

        if not old_string:
            return None

        diff_lines = difflib.unified_diff(
            old_string.splitlines(keepends=True),
            new_string.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=3,
        )
        diff_text = "".join(diff_lines)
        if len(diff_text) > 5000:
            diff_text = diff_text[:5000] + "\n... (diff truncated)"
        return diff_text or None

    def _truncate_text_to_tokens(self, text: str, max_tokens: int, preserve_tail: bool = False) -> str:
        if not text:
            return text
        counter = self._pruner  # estimate_tokens delegates to shared token counter
        if counter.estimate_tokens([{"content": text}]) <= max_tokens:
            return text
        if not preserve_tail:
            estimated_chars = max_tokens * 4
            return text[:estimated_chars] + "\n... [truncated for prompt budget]"
        half = max(200, (max_tokens * 4) // 2)
        return (
            text[:half]
            + "\n... [middle truncated for prompt budget] ...\n"
            + text[-half:]
        )

    def _bounded_json(self, payload: Dict[str, Any], max_tokens: int) -> str:
        text = json.dumps(payload, ensure_ascii=False)
        if self._pruner.estimate_tokens([{"content": text}]) <= max_tokens:
            return text
        return self._truncate_text_to_tokens(text, max_tokens, preserve_tail=True)

    def _format_tool_result(self, result: "ToolResult", tool_name: Optional[str] = None) -> str:
        """Format tool result for prompt history with per-tool token budgets."""
        if not result.success:
            return self._bounded_json(
                {
                    "error": result.error_message or "Unknown error",
                    "summary": result.result_summary,
                },
                800,
            )

        if not result.result_data:
            return result.result_summary

        tool_name = tool_name or "unknown"
        data = result.result_data

        if tool_name == "read_file":
            content = str(data)
            lines = []
            if result.result_summary:
                lines.append(f"[{result.result_summary}]")
            for raw_line in content.splitlines()[: 400 - len(lines)]:
                if len(raw_line) > 300:
                    lines.append(raw_line[:300] + "...")
                else:
                    lines.append(raw_line)
            return self._truncate_text_to_tokens("\n".join(lines), 6000)

        if tool_name == "grep":
            lines = str(data).splitlines()[:75]
            return self._truncate_text_to_tokens("\n".join(lines), 3000)

        if tool_name == "glob":
            lines = str(data).splitlines()[:200]
            return self._truncate_text_to_tokens("\n".join(lines), 1500)

        if tool_name == "list_directory":
            lines = str(data).splitlines()[:200]
            return self._truncate_text_to_tokens("\n".join(lines), 1500)

        if tool_name == "view_image" and isinstance(data, dict):
            return self._bounded_json(
                {
                    "attached_images": [
                        {
                            "name": image.get("name"),
                            "mime_type": image.get("mime_type"),
                        }
                        for image in (data.get("images") or [])[:8]
                    ],
                    "instruction": "Images are attached to the following user message for visual inspection.",
                },
                1200,
            )

        if tool_name == "web_search" and isinstance(data, dict):
            results = []
            for entry in (data.get("results") or [])[:8]:
                results.append({
                    "title": str(entry.get("title", ""))[:160],
                    "url": entry.get("url", ""),
                    "snippet": str(entry.get("snippet", ""))[:300],
                })
            return self._bounded_json({"query": data.get("query", ""), "results": results}, 2000)

        if tool_name == "web_extract" and isinstance(data, dict):
            extractions = []
            for entry in (data.get("extractions") or [])[:2]:
                extractions.append({
                    "url": entry.get("url", ""),
                    "title": str(entry.get("title", ""))[:160],
                    "excerpt": self._truncate_text_to_tokens(str(entry.get("content", "")), 1500),
                    "success": entry.get("success", True),
                })
            return self._bounded_json({"extractions": extractions}, 4000)

        if tool_name in {"bash", "exec_command", "write_stdin"} and isinstance(data, dict):
            return self._bounded_json(
                {
                    "command": data.get("command") or data.get("cmd") or data.get("cmd", ""),
                    "session_id": data.get("session_id"),
                    "status": data.get("status"),
                    "exit_code": data.get("exit_code"),
                    "timed_out": data.get("timed_out", False),
                    "stdout": self._truncate_text_to_tokens(str(data.get("stdout", "")), 1500, preserve_tail=True),
                    "stderr": self._truncate_text_to_tokens(str(data.get("stderr", "")), 1500, preserve_tail=True),
                    "truncated": data.get("truncated", False),
                },
                4000,
            )

        if tool_name == "python_execute" and isinstance(data, dict):
            code = data.get("code") or data.get("command") or ""
            output = data.get("output") or data.get("stdout") or ""
            return self._bounded_json(
                {
                    "code": self._truncate_text_to_tokens(str(code), 600),
                    "stdout": self._truncate_text_to_tokens(str(output), 1800, preserve_tail=True),
                    "stderr": self._truncate_text_to_tokens(str(data.get("stderr", "")), 600, preserve_tail=True),
                    "exit_code": data.get("exit_code"),
                },
                3000,
            )

        if tool_name in {"write_file", "edit_file", "apply_patch"}:
            payload = data if isinstance(data, dict) else {"result": str(data)}
            bounded = {
                "file_path": payload.get("file_path"),
                "summary": result.result_summary,
                "diff": self._truncate_text_to_tokens(str(payload.get("diff") or payload.get("preview") or payload), 2000, preserve_tail=True),
            }
            return self._bounded_json(bounded, 2500)

        content = json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
        if len(content) > self.MAX_TOOL_RESULT_CHARS:
            truncated = content[: self.MAX_TOOL_RESULT_CHARS - 100]
            content = truncated + f"\n\n[... truncated {len(content) - len(truncated)} chars ...]"
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

        elif tool_name == "read_file":
            # Keep imports/headers + tail for file reads
            head = content[:500]
            tail = content[-200:] if content_len > 700 else ""
            if tail:
                summary = f"[read_file: {head}\n...\n{tail}]"
            else:
                summary = f"[read_file: {head}]"

        elif tool_name == "grep":
            # Keep first matches
            summary = f"[grep results: {content[:500]}...]" if content_len > 500 else content

        elif tool_name in ("glob", "list_directory"):
            # Keep first portion of listing
            summary = f"[{tool_name} results: {content[:400]}...]" if content_len > 400 else content

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

    def _detect_redundant_calls(
        self,
        tool_calls: List["ParsedToolCall"],
    ) -> List[tuple]:
        """Detect redundant or low-quality tool calls.

        Checks incoming tool calls against the existing tool call log to find:
        1. Exact duplicates (same tool + same arguments)
        2. Overly broad glob patterns that scan the entire project
        3. Repeated list_directory calls

        Args:
            tool_calls: List of parsed tool calls to check.

        Returns:
            List of (tool_call, reason) tuples for calls that should be skipped.
        """
        redundant = []
        seen_in_batch: list[dict] = []
        self._last_redundant_filter_codes = {}

        for tc in tool_calls:
            # Intra-batch duplicate check (same tool+args within this LLM response)
            is_dup = False
            for seen in seen_in_batch:
                if seen["tool_name"] == tc.name and seen["arguments"] == tc.arguments:
                    redundant.append((tc, f"Duplicate in same step: {tc.name} called twice with same arguments"))
                    self._last_redundant_filter_codes[tc.id] = "duplicate"
                    is_dup = True
                    break
            if is_dup:
                continue

            # Exact duplicate check against history
            if tc.name != "read_file":
                allow_edit_retry_after_reread = False
                matching_history = [
                    prev
                    for prev in self._tool_call_log
                    if (
                        prev["tool_name"] == tc.name
                        and prev["arguments"] == tc.arguments
                        and prev.get("state_version_after", 0) == self._tool_state_version
                    )
                ]
                if tc.name == "edit_file" and matching_history:
                    prev = matching_history[-1]
                    file_path = self._canonical_workspace_path(
                        str(tc.arguments.get("file_path", ""))
                    )
                    previous_failure_type = (
                        (prev.get("result_metadata") or {}).get("match_failure_type")
                    )
                    if previous_failure_type in {"not_found", "ambiguous"}:
                        if self._has_reread_since_edit_failure(file_path):
                            allow_edit_retry_after_reread = True
                        else:
                            redundant.append(
                                (
                                    tc,
                                    "Retrying the same failed edit_file call without rereading the file first",
                                )
                            )
                            self._last_redundant_filter_codes[tc.id] = (
                                "edit_reread_required"
                            )
                            is_dup = True
                if is_dup or allow_edit_retry_after_reread:
                    continue
                for prev in self._tool_call_log:
                    if (
                        prev["tool_name"] == tc.name
                        and prev["arguments"] == tc.arguments
                        and prev.get("state_version_after", 0) == self._tool_state_version
                    ):
                        redundant.append((tc, f"Duplicate: already called {tc.name} with same arguments"))
                        self._last_redundant_filter_codes[tc.id] = "duplicate"
                        is_dup = True
                        break
            if is_dup:
                continue

            if tc.name in {"edit_file", "write_file"}:
                file_path = self._canonical_workspace_path(
                    str(tc.arguments.get("file_path", ""))
                )
                failure = self._apply_patch_failure_for_path(file_path)
                if failure:
                    redundant.append(
                        (
                            tc,
                            "apply_patch failed for this file; retry apply_patch with a smaller "
                            "fresh hunk instead of falling back to edit_file/write_file",
                        )
                    )
                    self._last_redundant_filter_codes[tc.id] = (
                        "apply_patch_recovery_required"
                    )
                    continue

            seen_in_batch.append({"tool_name": tc.name, "arguments": tc.arguments})

            # Overly broad glob patterns
            if tc.name == "glob":
                pattern = tc.arguments.get("pattern", "")
                if pattern in ("**/*.py", "**/*.md", "**/*.ts", "**/*.tsx", "**/*"):
                    redundant.append((tc, f"Too broad: glob '{pattern}' scans entire project"))
                    self._last_redundant_filter_codes[tc.id] = "broad_glob"
                    continue

            # Repeated list_directory on root
            if tc.name == "list_directory":
                path = tc.arguments.get("path", ".")
                if path in (".", "./", ""):
                    for prev in self._tool_call_log:
                        if (
                            prev["tool_name"] == "list_directory"
                            and prev.get("state_version_after", 0) == self._tool_state_version
                        ):
                            redundant.append((tc, "Duplicate: already listed directory"))
                            self._last_redundant_filter_codes[tc.id] = "duplicate"
                            break

        return redundant

    def _did_tool_call_change_state(self, tool_name: str, result: "ToolResult") -> bool:
        """Return whether a tool call materially changed the agent's working state."""
        if not result.success:
            return True

        if tool_name in {
            "write_file",
            "edit_file",
            "apply_patch",
            "bash",
            "exec_command",
            "write_stdin",
            "web_search",
            "web_extract",
        }:
            return True

        return False

    def _compute_run_metrics(self) -> Dict[str, Any]:
        """Compute run metrics from tool call log.

        Returns:
            Dict with navigation_overhead, total_tool_calls, distinct_files_read,
            distinct_files_modified, retries, profile name.
        """
        read_tools = {"read_file", "glob", "grep", "list_directory"}
        write_tools = {"write_file", "edit_file", "apply_patch"}

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
                if tool_name == "apply_patch":
                    for changed in (entry.get("result_metadata") or {}).get("changed_files") or []:
                        files_modified.add(str(changed))
                if not first_write_seen:
                    first_write_seen = True

            # Navigation overhead
            if not first_write_seen and tool_name in read_tools:
                navigation_overhead += 1

            # Retries: same tool + same primary arg
            primary_arg = ""
            if tool_name in ("read_file", "write_file", "edit_file"):
                primary_arg = arguments.get("file_path", "")
            elif tool_name == "apply_patch":
                primary_arg = str(arguments.get("patch", ""))[:120]
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
            metrics["usage"] = self._usage_totals.copy()
            metrics["cost"] = self._current_cost()
            metrics["context_usage"] = self._last_context_usage
            metrics["stored_context"] = self._last_stored_context
            metrics["context_profile"] = self._context_profile_dict()
            metrics["compaction_count"] = self._compaction_count
            metrics["last_compacted_at_step"] = self._last_compacted_at_step

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

    async def _finalize_successful_run(
        self,
        *,
        final_answer: str,
        messages: list[dict[str, Any]],
        state_machine: Any,
        step_number: int,
        start_time: float,
        event_callback: Optional[Callable[[Dict[str, Any]], None]],
        run_id: str,
        query: str,
        conversation_id: Optional[str] = None,
        working_memory: Optional[WorkingMemory] = None,
        coding_session_state: Optional[CodingSessionState] = None,
        coding_session_dirty: bool = False,
        forced_synthesis: bool = False,
    ) -> AgentResult:
        """Finalize a successful run and persist artifacts/metrics."""
        if final_answer and (
            not messages
            or messages[-1].get("role") != "assistant"
            or (messages[-1].get("content") or "") != final_answer
        ):
            messages.append(
                {
                    "role": "assistant",
                    "content": final_answer,
                }
            )

        citations = await self._extract_and_store_citations(
            run_id=run_id,
            answer=final_answer,
        )

        await state_machine.complete_run(final_answer)

        if (
            coding_session_dirty
            and conversation_id
            and working_memory is not None
            and coding_session_state is not None
        ):
            await self._persist_coding_session_final_answer(
                conversation_id=conversation_id,
                run_id=run_id,
                step_number=step_number,
                final_answer=final_answer,
                replay_eligible=not (
                    forced_synthesis or self._coding_last_step_structural_failure
                ),
            )
            await self._persist_coding_session_state(
                conversation_id=conversation_id,
                run_id=run_id,
                working_memory=working_memory,
                session_state=coding_session_state,
                final_answer=final_answer,
                reason="run_complete",
            )
            await self._refresh_coding_stored_context(
                conversation_id=conversation_id,
                session_state=coding_session_state,
                working_memory=working_memory,
            )

        total_timing_ms = int((time.perf_counter() - start_time) * 1000)
        context_usage = self._current_context_usage_payload(self._pruner.estimate_tokens(messages))
        self._last_context_usage = context_usage

        self._emit(
            event_callback,
            "agent_complete",
            run_id=run_id,
            success=True,
            final_answer=final_answer,
            citations=citations,
            total_steps=step_number,
            timing_ms=total_timing_ms,
            context_usage=context_usage,
            stored_context=self._last_stored_context,
            context_profile=self._context_profile_dict(),
            compaction_count=self._compaction_count,
            last_compacted_at_step=self._last_compacted_at_step,
            total_tokens=self._total_tokens,
            usage=self._usage_totals,
            cost=self._current_cost(),
        )
        await self._add_trace_event(
            run_id=run_id,
            event_type="agent_complete",
            content={
                "success": True,
                "total_steps": step_number,
                "answer_length": len(final_answer) if final_answer else 0,
                "citations_count": len(citations),
                "forced_synthesis": forced_synthesis,
            },
            duration_ms=total_timing_ms,
        )

        await self._store_run_metrics(run_id, total_timing_ms)
        await self._store_turn_summary(run_id, query, final_answer)
        await self._store_conversation_messages(run_id, messages)

        return AgentResult(
            run_id=run_id,
            success=True,
            final_answer=final_answer,
            citations=citations,
            total_steps=step_number,
            timing_ms=total_timing_ms,
            total_tokens=self._total_tokens,
            context_usage=context_usage,
            stored_context=self._last_stored_context,
            context_profile=self._context_profile_dict(),
            compaction_count=self._compaction_count,
            last_compacted_at_step=self._last_compacted_at_step,
            usage=self._usage_totals.copy(),
            cost=self._current_cost(),
            approved_plan=self._approved_plan,
            implementation_run_id=self._implementation_run_id,
            implementation_stream_token=self._implementation_stream_token,
        )

    async def _store_turn_summary(
        self, run_id: str, query: str, final_answer: str
    ) -> None:
        """Generate and store a compact turn summary for cross-turn context.

        Args:
            run_id: Run ID.
            query: Original user query.
            final_answer: Final answer text.
        """
        if not self._trace_repo:
            return
        try:
            from orchestrator.context.turn_summary import TurnSummarizer
            from orchestrator.utils.tokens import get_token_counter

            summarizer = TurnSummarizer(get_token_counter())

            # Get tool calls and artifacts for this run
            tool_calls = await self._repo.get_tool_calls_for_run(run_id)
            artifacts = await self._repo.get_run_artifacts(run_id)

            summary = summarizer.summarize_agent_run(
                run={
                    "run_id": run_id,
                    "user_message": query,
                    "final_answer": final_answer,
                    "thinking_summary": "",
                    "mode": "agent",
                },
                tool_calls=tool_calls,
                artifacts=artifacts,
            )

            await self._trace_repo.update_run(
                run_id, turn_summary=summary.to_context_string()
            )
            logger.debug(
                "Turn summary stored",
                extra={"run_id": run_id, "token_cost": summary.token_cost},
            )
        except Exception as e:
            logger.warning(
                "Failed to store turn summary",
                extra={"run_id": run_id, "error": str(e)},
            )

    async def _store_conversation_messages(
        self, run_id: str, messages: list
    ) -> None:
        """Store a compact scaffold snapshot for debugging only.

        Args:
            run_id: Run ID.
            messages: Current scaffold message list from the agent loop.
        """
        if not self._trace_repo:
            return
        try:
            clean_messages = []
            for msg in messages:
                clean_messages.append(
                    {k: v for k, v in msg.items() if not k.startswith("_")}
                )
            serialized = json.dumps(
                {
                    "mode": "scaffold_only",
                    "messages": clean_messages,
                    "message_count": len(clean_messages),
                },
                ensure_ascii=False,
            )
            if len(serialized) > 500_000:
                return
            await self._trace_repo.update_run(run_id, agent_state=serialized)
        except Exception as e:
            logger.warning(
                "Failed to store conversation messages",
                extra={"error": str(e)},
            )

    async def _load_prior_messages(
        self, conversation_id: str
    ) -> list | None:
        """Deprecated: normal cross-turn continuation no longer reloads agent_state.

        Args:
            conversation_id: Conversation ID to look up.

        Returns:
            Always None.
        """
        return None

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
        # Inspired by OpenCode's forced summarization: require structured output
        if self._findings:
            findings_text = "\n".join(
                f"- {f['content']}" for f in self._findings
            )
            synthesis_content = (
                f"MAXIMUM STEPS REACHED. Tools are disabled. Respond with text only.\n\n"
                f"STRICT REQUIREMENTS:\n"
                f"1. Do NOT make any tool calls — they will fail.\n"
                f"2. You MUST provide a text response that DIRECTLY ANSWERS the user's question.\n"
                f"3. Do NOT output your internal thoughts, plans, or next steps as the answer.\n\n"
                f"ORIGINAL QUERY: {self._current_query}\n\n"
                f"KEY FINDINGS ({len(self._findings)} items):\n"
                f"{findings_text}\n\n"
                f"Your response must include:\n"
                f"- A direct answer to the original query based on findings above\n"
                f"- Any important caveats or gaps in the research\n\n"
                f"Do NOT include inline citation numbers like [1], [2] - the UI shows sources automatically."
            )
        else:
            synthesis_content = (
                "MAXIMUM STEPS REACHED. Tools are disabled. Respond with text only.\n\n"
                "STRICT REQUIREMENTS:\n"
                "1. Do NOT make any tool calls — they will fail.\n"
                "2. You MUST provide a text response that DIRECTLY ANSWERS the user's question.\n"
                "3. Do NOT output your internal thoughts, plans, or next steps as the answer.\n\n"
                f"ORIGINAL QUERY: {self._current_query}\n\n"
                "Your response must include:\n"
                "- A summary of what you found so far\n"
                "- What you were unable to determine\n"
                "- Recommendations for what the user could try next\n\n"
                "Do NOT include inline citation numbers like [1], [2] - the UI shows sources automatically."
            )

        force_msg = {
            "role": "user",
            "content": synthesis_content,
        }
        messages = messages + [force_msg]
        messages = self._normalize_system_messages(messages)

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

        synthesis_max_tokens, extra_kwargs = self._reasoning_provider_kwargs()
        synthesis_max_tokens = max(synthesis_max_tokens, 8192)

        response = await self._provider.complete_streaming(
            messages=messages,
            model=self._model_name,
            on_token=on_token,
            on_reasoning=on_reasoning,
            tools=None,  # No tools - force text response
            max_tokens=synthesis_max_tokens,
            temperature=self._temperature,
            **extra_kwargs,
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

        # Accumulate normalized token usage from forced synthesis.
        normalized_usage = self._record_usage(
            response.usage,
            prompt_messages=messages,
            output_text=response.text,
            reasoning_text=response.reasoning,
        )
        self._emit(
            event_callback,
            "usage_update",
            run_id=run_id,
            usage=self._usage_totals,
            latest_usage=normalized_usage,
            cost=self._current_cost(),
        )

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
