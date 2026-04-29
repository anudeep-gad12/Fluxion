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
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from orchestrator.agent.context_pruner import ContextPruner
from orchestrator.agent.intent import (
    AgentIntent,
    classify_agent_intent,
    render_intent_guidance,
)
from orchestrator.agent.permissions import classify_tool_call
from orchestrator.context.budget import ContextBudget
from orchestrator.context.context_profile import ModelContextProfile
from orchestrator.context.history_builder import HistoryBuilder
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
from orchestrator.providers.usage import add_usage, estimate_cost, normalize_usage
from orchestrator.reasoning_controls import ReasoningSettings, apply_reasoning_settings
from orchestrator.schemas import AgentStepState
from orchestrator.utils.sanitize import sanitize_harmony_tokens
from orchestrator.vision import build_multimodal_user_content, validate_image_attachments

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
    context_usage: Optional[Dict[str, Any]] = None
    context_profile: Optional[Dict[str, Any]] = None
    compaction_count: int = 0
    last_compacted_at_step: Optional[int] = None
    usage: Optional[Dict[str, int]] = None
    cost: Optional[Dict[str, Any]] = None


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


@dataclass
class WorkingMemory:
    """Compact agent working memory used for prompt reconstruction."""

    objective: str
    latest_user_intent: str = ""
    tool_guidance: str = ""
    prior_outcomes: List[str] = field(default_factory=list)
    files_inspected: Dict[str, str] = field(default_factory=dict)
    files_changed: Dict[str, str] = field(default_factory=dict)
    validation_results: List[str] = field(default_factory=list)
    latest_diagnostics: List[str] = field(default_factory=list)
    current_hypothesis: Optional[str] = None
    recent_validation: Optional[str] = None
    unresolved_tasks: List[str] = field(default_factory=list)
    recent_raw_evidence: List[str] = field(default_factory=list)
    discoveries: List[str] = field(default_factory=list)

    def render(self) -> str:
        """Render compact working memory for model context."""
        sections = [
            "This is continuing state for the same run, not a new user request.",
            f"Objective: {self.objective}",
        ]
        if self.latest_user_intent:
            sections.append(f"Latest user intent: {self.latest_user_intent}")
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

        validations = list(self.validation_results)
        if self.recent_validation:
            validations.append(self.recent_validation)
        if validations:
            sections.append(
                "Validation:\n"
                + "\n".join(f"- {item}" for item in validations[-6:])
            )

        if self.discoveries:
            sections.append(
                "Recent discoveries:\n"
                + "\n".join(f"- {item}" for item in self.discoveries[-8:])
            )

        if self.latest_diagnostics:
            sections.append(
                "Latest diagnostics:\n"
                + "\n".join(f"- {item}" for item in self.latest_diagnostics[-6:])
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
        if self.tool_guidance:
            sections.append(f"Tool guidance: {self.tool_guidance}")

        sections.append(
            "Use this working memory as the durable state. Raw tool outputs that follow "
            "are only from the most recent tool step. Continue from the current state; "
            "do not restart by restating the objective, your plan, or prior discoveries."
        )
        return "\n\n".join(sections)


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

        # Planning configuration
        self._planning_enabled = planning_enabled
        self._max_plan_steps = max_plan_steps
        self._current_plan: Optional["ResearchPlan"] = None

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
        if scaffold_messages:
            prompt_messages.append(scaffold_messages[0])
            prompt_messages.append(
                {
                    "role": "system",
                    "content": "WORKING MEMORY\n" + working_memory.render(),
                    "_working_memory": True,
                }
            )
            prompt_messages.extend(scaffold_messages[1:])
        else:
            prompt_messages.append(
                {
                    "role": "system",
                    "content": "WORKING MEMORY\n" + working_memory.render(),
                    "_working_memory": True,
                }
            )

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

    def _first_step_tool_choice(
        self,
        intent: AgentIntent,
        tool_steps_completed: int,
        step_number: int,
    ) -> Optional[str]:
        """Choose first-step tool forcing without forcing conversational turns."""
        if (
            self._profile
            and self._profile.name == "coding"
            and tool_steps_completed == 0
            and intent in {AgentIntent.ACTIONABLE_WORKSPACE, AgentIntent.READ_ONLY_WORKSPACE}
        ):
            return "required"
        if step_number == 1 and self._tool_choice:
            return self._tool_choice
        return None

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
                file_path = str(tool_call.arguments.get("file_path", "unknown"))
                excerpt = self._extract_read_file_excerpt(result.result_data)
                memory.files_inspected[file_path] = (
                    f"{summary}. Key excerpt: {excerpt}" if excerpt else summary
                )[:500]
                memory.current_hypothesis = f"Latest inspected file: {file_path}"
            elif tool_call.name in ("edit_file", "write_file"):
                file_path = str(tool_call.arguments.get("file_path", "unknown"))
                diff_summary = self._summarize_diff(result.result_data) or summary
                memory.files_changed[file_path] = diff_summary[:500]
                memory.current_hypothesis = f"Changed {file_path}"
            elif tool_call.name == "bash":
                memory.recent_validation = summary
                memory.validation_results.append(summary[:500])
                memory.validation_results = memory.validation_results[-8:]
                diagnostics = self._extract_bash_diagnostics(result.result_data, summary)
                memory.latest_diagnostics = diagnostics
            elif tool_call.name in ("grep", "glob", "list_directory"):
                discovery = self._summarize_discovery(tool_call, result)
                if discovery:
                    memory.discoveries.append(discovery)
                    memory.discoveries = memory.discoveries[-12:]
            else:
                memory.discoveries.append(f"{tool_call.name}: {summary}")
                memory.discoveries = memory.discoveries[-12:]

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

            # Build initial scaffold from system prompt + turn summaries.
            messages, self._context_budget = await self._build_initial_messages(
                query, conversation_id
            )
            if validated_images and messages and messages[-1].get("role") == "user":
                messages[-1]["content"] = build_multimodal_user_content(query, validated_images)
            latest_intent = (
                classify_agent_intent(query)
                if self._profile and self._profile.name == "coding"
                else AgentIntent.ACTIONABLE_WORKSPACE
            )
            working_memory = WorkingMemory(
                objective=query,
                latest_user_intent=render_intent_guidance(latest_intent),
                tool_guidance=render_intent_guidance(latest_intent),
                prior_outcomes=self._prior_outcomes_from_scaffold(messages),
            )
            if latest_intent == AgentIntent.CONVERSATIONAL:
                working_memory.unresolved_tasks.append(
                    "No new workspace task from latest user message."
                )

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
            if self._planning_enabled and latest_intent != AgentIntent.CONVERSATIONAL:
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

                prompt_messages = self._build_prompt_messages(
                    scaffold_messages=messages,
                    working_memory=working_memory,
                )

                pruned_messages, context_usage_payload, compacted_now = self._enforce_prompt_budget(
                    prompt_messages,
                    step_number,
                )
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
                        "context_profile": self._context_profile_dict(),
                    },
                    step_number=step_number,
                )

                if compacted_now:
                    context_usage_payload = self._current_context_usage_payload(
                        self._pruner.estimate_tokens(pruned_messages)
                    )
                    self._emit(
                        event_callback,
                        "conversation_compacted",
                        run_id=run_id,
                        step_number=step_number,
                        message=self.COMPACTION_PREFIX,
                        context_usage=context_usage_payload,
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
                    step_tool_choice = self._first_step_tool_choice(
                        intent=latest_intent,
                        tool_steps_completed=tool_steps_completed,
                        step_number=step_number,
                    )
                    llm_response = await self._call_llm_with_tools(
                        messages=pruned_messages,
                        event_callback=event_callback,
                        run_id=run_id,
                        tool_choice=step_tool_choice,
                        tool_schemas=tool_schemas,
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
                normalized_usage = self._record_usage(llm_response.usage)
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
                        messages.append({
                            "role": "assistant",
                            "content": self._summarize_assistant_content(llm_response.text),
                        })
                    if length_only:
                        length_only_continuations += 1
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your last response hit the length limit before producing answer text. "
                            "Continue once from the compact working memory. "
                            "Prefer a concise final answer; call a tool only if essential."
                        ),
                    })
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
                    redundant = self._detect_redundant_calls(parsed_for_check)
                    if redundant:
                        redundant_ids = {tc.id for tc, _ in redundant}
                        tool_calls = [tc for tc in tool_calls if tc["id"] not in redundant_ids]
                        reasons = "; ".join(r for _, r in redundant)
                        logger.info(
                            "Filtered redundant tool calls",
                            extra={"reasons": reasons, "filtered_count": len(redundant)},
                        )
                        messages.append({
                            "role": "system",
                            "content": f"[Tool calls filtered — {reasons}. Try a different query or tool.]",
                        })
                        if not tool_calls:
                            await state_machine.complete_step(
                                decision="filtered",
                                thinking_text=thinking_text,
                            )
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
                                    forced_synthesis=True,
                                )

                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Do not repeat filtered or duplicate tool calls. "
                                    "Either provide the final answer now or choose a genuinely different tool call."
                                ),
                            }
                        )
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
                    if assistant_content:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": assistant_content,
                                "tool_calls": tool_calls,
                            }
                        )
                    else:
                        messages.append(
                            {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": tool_calls,
                            }
                        )
                    self._update_working_memory_from_tools(working_memory, tool_results)
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

                    if image_parts_for_next_call:
                        messages.append(
                            {
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
                        )

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
                forced_synthesis=True,
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
                usage=self._usage_totals.copy(),
                cost=self._current_cost(),
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
                usage=self._usage_totals.copy(),
                cost=self._current_cost(),
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

    def _context_profile_dict(self) -> Dict[str, Any]:
        return self._context_profile.to_dict()

    def _current_context_usage_payload(
        self,
        prompt_tokens_current_call: int,
    ) -> Dict[str, Any]:
        effective_budget = self._context_profile.effective_input_budget
        remaining = max(0, effective_budget - prompt_tokens_current_call)
        utilization_pct = (prompt_tokens_current_call / effective_budget * 100) if effective_budget else 0.0
        return {
            "context_window": self._context_profile.context_window,
            "reserved_output_tokens": self._context_profile.max_output_tokens,
            "effective_input_budget": effective_budget,
            "prompt_tokens_current_call": prompt_tokens_current_call,
            "conversation_tokens_active_history": prompt_tokens_current_call,
            "utilization_pct_effective": round(utilization_pct, 1),
            "utilization_pct": round(utilization_pct, 1),
            "compaction_threshold_pct": self.COMPACTION_THRESHOLD_PCT,
            "next_compaction_at_tokens": int(effective_budget * self.COMPACTION_THRESHOLD_PCT / 100),
            "remaining_tokens": remaining,
            "compactions_so_far": self._compaction_count,
            "compaction_count": self._compaction_count,
            "last_compacted_at_step": self._last_compacted_at_step,
        }

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
            elif tool_name == "bash" and summary:
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
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
        effective_budget = self._context_profile.effective_input_budget
        threshold_tokens = int(effective_budget * self.COMPACTION_THRESHOLD_PCT / 100)
        prompt_tokens = self._pruner.estimate_tokens(messages)
        compacted_now = False

        if prompt_tokens >= threshold_tokens:
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

    def _record_usage(self, raw_usage: dict[str, Any] | None) -> dict[str, int]:
        """Normalize and accumulate LLM token usage."""
        usage = normalize_usage(raw_usage)
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
    ) -> tuple[List[Dict[str, Any]], ContextBudget]:
        """Build initial message list with system prompt, history, and query.

        Uses HistoryBuilder turn summaries for cross-turn continuity. Agent
        prompt replay no longer resumes from prior serialized tool transcripts.

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
        if self._profile:
            system_prompt = self._system_prompt
        else:
            today = date.today()
            date_context = (
                f"Current date: {today.strftime('%B %d, %Y')}\n"
                f"Your knowledge cutoff: June 2024. For information after this date, use web_search."
            )
            system_prompt = self._system_prompt.format(date_context=date_context)
        system_prompt = self._effective_system_prompt(system_prompt)

        # Load conversation history
        prior_runs: list[dict] = []
        if conversation_id and self._trace_repo:
            prior_runs = await self._trace_repo.list_runs_for_conversation(
                conversation_id
            )

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

            # Log tool call for run metrics
            self._tool_call_log.append({
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "success": result.success,
                "result_summary": result.result_summary,
                "step_number": step_number,
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
        for tool_name in ("bash", "read_file", "write_file", "edit_file"):
            tool = self._registry.get(tool_name)
            working_dir = getattr(tool, "_working_dir", None)
            if isinstance(working_dir, Path):
                return str(working_dir)
        return None

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
        if tool_call.name in ("write_file", "edit_file", "bash") and result.result_data:
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
        if result.success and tool_call.name in ("write_file", "edit_file", "bash"):
            artifact_type = {
                "write_file": "file_write",
                "edit_file": "file_edit",
                "bash": "command_run",
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

        # Emit tool result event (include diff data and command output details)
        emit_kwargs: Dict[str, Any] = {
            "run_id": run_id,
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.name,
            "success": result.success,
            "result_summary": result.result_summary,
            "duration_ms": result.duration_ms,
        }
        if tool_call.name in ("write_file", "edit_file") and result.result_data:
            emit_kwargs["result_data"] = str(result.result_data)[:10000]
        if tool_call.name == "bash" and isinstance(result.result_data, dict):
            emit_kwargs["bash_output"] = {
                "stdout": str(result.result_data.get("stdout", ""))[:10000],
                "stderr": str(result.result_data.get("stderr", ""))[:10000],
                "exit_code": result.result_data.get("exit_code"),
                "truncated": bool(result.result_data.get("truncated")),
            }
        self._emit(event_callback, "tool_result", **emit_kwargs)

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
            for raw_line in content.splitlines()[:400]:
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

        if tool_name == "bash" and isinstance(data, dict):
            return self._bounded_json(
                {
                    "command": data.get("command", ""),
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

        if tool_name in {"write_file", "edit_file"}:
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

        for tc in tool_calls:
            # Intra-batch duplicate check (same tool+args within this LLM response)
            is_dup = False
            for seen in seen_in_batch:
                if seen["tool_name"] == tc.name and seen["arguments"] == tc.arguments:
                    redundant.append((tc, f"Duplicate in same step: {tc.name} called twice with same arguments"))
                    is_dup = True
                    break
            if is_dup:
                continue

            # Exact duplicate check against history
            if tc.name != "read_file":
                for prev in self._tool_call_log:
                    if prev["tool_name"] == tc.name and prev["arguments"] == tc.arguments:
                        redundant.append((tc, f"Duplicate: already called {tc.name} with same arguments"))
                        is_dup = True
                        break
            if is_dup:
                continue

            seen_in_batch.append({"tool_name": tc.name, "arguments": tc.arguments})

            # Overly broad glob patterns
            if tc.name == "glob":
                pattern = tc.arguments.get("pattern", "")
                if pattern in ("**/*.py", "**/*.md", "**/*.ts", "**/*.tsx", "**/*"):
                    redundant.append((tc, f"Too broad: glob '{pattern}' scans entire project"))
                    continue

            # Repeated list_directory on root
            if tc.name == "list_directory":
                path = tc.arguments.get("path", ".")
                if path in (".", "./", ""):
                    for prev in self._tool_call_log:
                        if prev["tool_name"] == "list_directory":
                            redundant.append((tc, "Duplicate: already listed directory"))
                            break

        return redundant

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
            metrics["usage"] = self._usage_totals.copy()
            metrics["cost"] = self._current_cost()
            metrics["context_usage"] = self._current_context_usage_payload(
                self._pruner.estimate_tokens([{"role": "system", "content": self._system_prompt}])
            )
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

        total_timing_ms = int((time.perf_counter() - start_time) * 1000)
        context_usage = self._current_context_usage_payload(self._pruner.estimate_tokens(messages))

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
            context_profile=self._context_profile_dict(),
            compaction_count=self._compaction_count,
            last_compacted_at_step=self._last_compacted_at_step,
            usage=self._usage_totals.copy(),
            cost=self._current_cost(),
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
        normalized_usage = self._record_usage(response.usage)
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
