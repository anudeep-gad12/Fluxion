"""Context pruner for preventing token blowout in agent conversations.

This module provides:
- Automatic summarization of old tool results
- Token count estimation
- Step-aware message pruning
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PruneStats:
    """Statistics from a pruning operation.

    Attributes:
        original_messages: Number of messages before pruning.
        pruned_messages: Number of messages after pruning.
        messages_summarized: Number of tool messages summarized.
        estimated_tokens_saved: Approximate tokens saved.
    """

    original_messages: int
    pruned_messages: int
    messages_summarized: int
    estimated_tokens_saved: int


class ContextPruner:
    """Prevents token blowout by summarizing old tool results.

    The pruner keeps the last N steps detailed and summarizes older tool
    results to 1-line summaries. This prevents context from exceeding
    the model's context window (128k tokens).

    Attributes:
        KEEP_FULL_STEPS: Default number of recent steps to keep detailed.
        MAX_PYTHON_OUTPUT_CHARS: Default max chars for python_execute before truncation.
        CHARS_PER_TOKEN: Rough estimate for token counting.

    Example:
        pruner = ContextPruner(keep_full_steps=2)
        messages = pruner.prune(messages, current_step=5)
    """

    KEEP_FULL_STEPS: int = 2
    MAX_PYTHON_OUTPUT_CHARS: int = 500
    CHARS_PER_TOKEN: float = 4.0  # Rough estimate

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
        )

        return pruned, stats

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
        """Summarize a tool result to 1-line summary.

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
