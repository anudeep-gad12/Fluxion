"""Context pruner for preventing token blowout in agent conversations.

This module provides:
- Automatic summarization of old tool results
- LLM-based smart summarization (optional, preserves key facts)
- Token count estimation
- Step-aware message pruning
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from orchestrator.logging_config import get_logger

if TYPE_CHECKING:
    from orchestrator.providers.base import LLMProvider

logger = get_logger(__name__)


class SummarizerProvider(Protocol):
    """Protocol for providers that can summarize content."""

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """Complete a conversation."""
        ...


@dataclass
class PruneStats:
    """Statistics from a pruning operation.

    Attributes:
        original_messages: Number of messages before pruning.
        pruned_messages: Number of messages after pruning.
        messages_summarized: Number of tool messages summarized.
        estimated_tokens_saved: Approximate tokens saved.
        llm_summaries_generated: Number of LLM-generated summaries.
    """

    original_messages: int
    pruned_messages: int
    messages_summarized: int
    estimated_tokens_saved: int
    llm_summaries_generated: int = 0


class ContextPruner:
    """Prevents token blowout by summarizing old tool results.

    The pruner keeps the last N steps detailed and summarizes older tool
    results. Supports two modes:

    1. Basic mode: Simple char-count summaries "[Extracted - 5000 chars]"
    2. Smart mode: LLM-generated summaries that preserve key facts

    Attributes:
        KEEP_FULL_STEPS: Default number of recent steps to keep detailed.
        MAX_PYTHON_OUTPUT_CHARS: Default max chars for python_execute before truncation.
        CHARS_PER_TOKEN: Rough estimate for token counting.
        MAX_SUMMARY_TOKENS: Max tokens for LLM-generated summaries.

    Example:
        # Basic mode (no LLM)
        pruner = ContextPruner(keep_full_steps=2)
        messages = pruner.prune(messages, current_step=5)

        # Smart mode (with LLM)
        pruner = ContextPruner(keep_full_steps=2)
        pruner.set_llm(provider, model_name, query)
        messages = await pruner.prune_async(messages, current_step=5)
    """

    KEEP_FULL_STEPS: int = 2
    MAX_PYTHON_OUTPUT_CHARS: int = 500
    CHARS_PER_TOKEN: float = 4.0  # Rough estimate
    MAX_SUMMARY_TOKENS: int = 400  # Max tokens for LLM summaries (reasoning models need more)

    # Prompt template for LLM summarization
    SUMMARIZE_PROMPT: str = """Summarize the key facts from this tool result that help answer the user's query.

User query: {query}

Tool: {tool_name}
Result:
{content}

Extract ONLY facts relevant to the query. Include specific numbers, dates, names.
Output 2-3 sentences max. Do not include navigation, ads, or boilerplate."""

    def __init__(
        self,
        keep_full_steps: int = 2,
        max_python_output_chars: int = 500,
    ) -> None:
        """Initialize context pruner.

        Args:
            keep_full_steps: Number of recent steps to keep detailed.
            max_python_output_chars: Max chars for python output before truncation.
        """
        self._keep_full_steps = keep_full_steps
        self._max_python_chars = max_python_output_chars

        # LLM summarization (optional)
        self._provider: Optional[SummarizerProvider] = None
        self._model_name: Optional[str] = None
        self._query: Optional[str] = None
        self._summary_cache: Dict[str, str] = {}

    def set_llm(
        self,
        provider: SummarizerProvider,
        model_name: str,
        query: str,
    ) -> None:
        """Enable LLM-based smart summarization.

        Args:
            provider: LLM provider for generating summaries.
            model_name: Model to use for summarization.
            query: Original user query (used to determine relevance).
        """
        self._provider = provider
        self._model_name = model_name
        self._query = query
        self._summary_cache = {}  # Clear cache for new query
        logger.debug(
            "LLM summarization enabled",
            extra={"model": model_name, "query_len": len(query)},
        )

    @property
    def has_llm(self) -> bool:
        """Check if LLM summarization is enabled."""
        return self._provider is not None and self._model_name is not None

    @property
    def keep_full_steps(self) -> int:
        """Get number of steps to keep full."""
        return self._keep_full_steps

    @property
    def max_python_chars(self) -> int:
        """Get max python output chars."""
        return self._max_python_chars

    def prune(
        self,
        messages: List[Dict[str, Any]],
        current_step: int,
        step_metadata: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Prune messages by summarizing old tool results.

        Args:
            messages: List of message dicts (role, content, etc.).
            current_step: Current step number (1-indexed).
            step_metadata: Optional mapping of tool_call_id to step number.
                          If not provided, uses _step metadata in messages.

        Returns:
            New list of messages with old tool results summarized.
        """
        if not messages:
            return []

        pruned: List[Dict[str, Any]] = []
        summarized_count = 0

        for msg in messages:
            if msg.get("role") == "tool":
                # Determine step number for this tool message
                step = self._get_step_number(msg, step_metadata)

                # Summarize if older than threshold
                if step is not None and step < current_step - self._keep_full_steps:
                    summarized_msg = self._summarize_tool_result(msg)
                    pruned.append(summarized_msg)
                    if summarized_msg.get("_pruned"):
                        summarized_count += 1
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)

        if summarized_count > 0:
            logger.debug(
                "Pruned context messages",
                extra={
                    "summarized": summarized_count,
                    "current_step": current_step,
                },
            )

        return pruned

    def prune_with_stats(
        self,
        messages: List[Dict[str, Any]],
        current_step: int,
        step_metadata: Optional[Dict[str, int]] = None,
    ) -> tuple[List[Dict[str, Any]], PruneStats]:
        """Prune messages and return statistics.

        Args:
            messages: List of message dicts.
            current_step: Current step number.
            step_metadata: Optional mapping of tool_call_id to step number.

        Returns:
            Tuple of (pruned_messages, stats).
        """
        original_chars = sum(len(str(m.get("content", ""))) for m in messages)
        original_count = len(messages)

        pruned = self.prune(messages, current_step, step_metadata)

        pruned_chars = sum(len(str(m.get("content", ""))) for m in pruned)
        summarized = sum(1 for m in pruned if m.get("_pruned"))

        stats = PruneStats(
            original_messages=original_count,
            pruned_messages=len(pruned),
            messages_summarized=summarized,
            estimated_tokens_saved=int(
                (original_chars - pruned_chars) / self.CHARS_PER_TOKEN
            ),
            llm_summaries_generated=sum(1 for m in pruned if m.get("_llm_summary")),
        )

        return pruned, stats

    async def prune_async(
        self,
        messages: List[Dict[str, Any]],
        current_step: int,
        step_metadata: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Prune messages with LLM-based smart summarization (async).

        If LLM is not configured via set_llm(), falls back to basic summarization.

        Args:
            messages: List of message dicts (role, content, etc.).
            current_step: Current step number (1-indexed).
            step_metadata: Optional mapping of tool_call_id to step number.

        Returns:
            New list of messages with old tool results summarized.
        """
        if not messages:
            return []

        # Fall back to basic if no LLM configured
        if not self.has_llm:
            return self.prune(messages, current_step, step_metadata)

        pruned: List[Dict[str, Any]] = []
        summarized_count = 0
        llm_summaries = 0

        for msg in messages:
            if msg.get("role") == "tool":
                step = self._get_step_number(msg, step_metadata)

                if step is not None and step < current_step - self._keep_full_steps:
                    # Use LLM to summarize
                    summarized_msg = await self._summarize_tool_result_llm(msg)
                    pruned.append(summarized_msg)
                    if summarized_msg.get("_pruned"):
                        summarized_count += 1
                        if summarized_msg.get("_llm_summary"):
                            llm_summaries += 1
                else:
                    pruned.append(msg)
            else:
                pruned.append(msg)

        if summarized_count > 0:
            logger.info(
                "Pruned context messages (smart)",
                extra={
                    "summarized": summarized_count,
                    "llm_summaries": llm_summaries,
                    "current_step": current_step,
                },
            )

        return pruned

    def _get_step_number(
        self,
        msg: Dict[str, Any],
        step_metadata: Optional[Dict[str, int]] = None,
    ) -> Optional[int]:
        """Extract step number from message.

        Args:
            msg: Message dict.
            step_metadata: Optional mapping of tool_call_id to step.

        Returns:
            Step number or None if not determinable.
        """
        # Check for explicit _step metadata
        if "_step" in msg:
            return msg["_step"]

        # Check step_metadata mapping
        if step_metadata:
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id and tool_call_id in step_metadata:
                return step_metadata[tool_call_id]

        return None

    def _summarize_tool_result(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize a tool result to 1-line summary (basic mode).

        Args:
            msg: Tool message dict with content.

        Returns:
            New message dict with summarized content.
        """
        content = msg.get("content", "")
        tool_name = msg.get("name", "unknown")

        # Determine summary based on tool type
        if tool_name == "web_extract":
            summary = f"[Extracted content - {len(content)} chars]"
        elif tool_name == "web_search":
            summary = f"[Search results - {len(content)} chars]"
        elif tool_name == "python_execute":
            # Keep some context for python results
            if len(content) > self._max_python_chars:
                head = content[:200]
                tail = content[-200:]
                summary = f"[Output: {head}...{tail}]"
            else:
                # Short enough to keep as-is
                return msg
        else:
            summary = f"[Tool result - {len(content)} chars]"

        # Return new dict with summary (preserve other fields)
        return {**msg, "content": summary, "_pruned": True}

    async def _summarize_tool_result_llm(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize a tool result using LLM (smart mode).

        Uses the configured LLM to extract key facts relevant to the user's query.
        Falls back to basic summarization on error or for short content.

        Args:
            msg: Tool message dict with content.

        Returns:
            New message dict with LLM-generated summary.
        """
        content = msg.get("content", "")
        tool_name = msg.get("name", "unknown")
        tool_call_id = msg.get("tool_call_id", "")

        # Check cache first
        if tool_call_id and tool_call_id in self._summary_cache:
            cached = self._summary_cache[tool_call_id]
            return {**msg, "content": cached, "_pruned": True, "_llm_summary": True}

        # Skip LLM for very short content (not worth the cost)
        if len(content) < 500:
            return self._summarize_tool_result(msg)

        # Skip LLM for python output (usually structured, keep head/tail)
        if tool_name == "python_execute":
            return self._summarize_tool_result(msg)

        try:
            # Truncate content for LLM input (keep first 6K chars to stay within limits)
            truncated_content = content[:6000]
            if len(content) > 6000:
                truncated_content += f"\n[... {len(content) - 6000} more chars truncated ...]"

            prompt = self.SUMMARIZE_PROMPT.format(
                query=self._query or "Unknown query",
                tool_name=tool_name,
                content=truncated_content,
            )

            response = await self._provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model_name,
                max_tokens=self.MAX_SUMMARY_TOKENS,
                temperature=0.3,  # Low temperature for factual extraction
            )

            summary = response.text.strip() if response.text else None

            if summary:
                # Prefix with tool name for clarity
                summary = f"[{tool_name} summary]: {summary}"

                # Cache the summary
                if tool_call_id:
                    self._summary_cache[tool_call_id] = summary

                logger.debug(
                    "Generated LLM summary",
                    extra={
                        "tool_name": tool_name,
                        "original_chars": len(content),
                        "summary_chars": len(summary),
                    },
                )

                return {**msg, "content": summary, "_pruned": True, "_llm_summary": True}

        except Exception as e:
            logger.warning(
                "LLM summarization failed, using basic",
                extra={"error": str(e), "tool_name": tool_name},
            )

        # Fallback to basic summarization
        return self._summarize_tool_result(msg)

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate token count for messages.

        Args:
            messages: List of message dicts.

        Returns:
            Estimated token count.
        """
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        # Add overhead for message structure
        overhead = len(messages) * 10
        return int((total_chars + overhead) / self.CHARS_PER_TOKEN)
