"""Base classes for thinking strategies.

This module defines the abstract interface that all thinking strategies
must implement, plus the data classes for thinking results.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


@dataclass
class ThinkingStep:
    """A single step in the thinking process.

    Attributes:
        seq: Sequence number for ordering steps.
        step_type: Type of step (e.g., "thinking", "candidate", "verification").
        content: Raw content of the step (internal, for traces).
        ui_summary: Cleaned summary for UI display.
        tokens: Number of tokens used in this step.
        duration_ms: Time taken for this step in milliseconds.
        metadata: Optional additional metadata.
    """

    seq: int
    step_type: str
    content: str
    ui_summary: str
    tokens: int = 0
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ThinkingResult:
    """Result of a thinking strategy execution.

    Attributes:
        steps: List of thinking steps (for logging/tracing).
        final_answer: The final answer to return to the user.
        thinking_summary: Cleaned summary of thinking for UI display.
        thinking_tokens: Total tokens used for thinking steps.
        answer_tokens: Tokens used for the final answer.
        metadata: Optional additional metadata about the thinking process.
    """

    steps: List[ThinkingStep]
    final_answer: str
    thinking_summary: str = ""
    thinking_tokens: int = 0
    answer_tokens: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """Total tokens used (thinking + answer)."""
        return self.thinking_tokens + self.answer_tokens


class ThinkingStrategy(ABC):
    """Abstract base class for thinking strategies.

    A thinking strategy defines how the model reasons about a problem.
    Different strategies can be swapped in without changing the chat engine.

    Examples:
        - DirectStrategy: Just call the model and return the response.
        - ChainOfThoughtStrategy: Add "Let's think step by step..." prompting.
        - VoteStrategy: Generate N responses and take majority vote.
        - SolveVerifyStrategy: Generate candidates, then verify the best one.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier (e.g., 'direct', 'cot', 'vote')."""
        pass

    @abstractmethod
    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute the thinking strategy.

        Args:
            messages: List of message dicts to send to the model.
            model_call: Async function to call the model.
                        Signature: async def(messages, **kwargs) -> (str, dict)
                        Returns (response_text, usage_stats).
            event_callback: Optional callback for emitting events.
                           Called with {"type": str, ...} dicts.

        Returns:
            ThinkingResult containing the final answer and thinking trace.
        """
        pass

    def clean_for_ui(self, raw_thinking: str) -> str:
        """Convert raw thinking content to user-friendly summary.

        Override this method to customize how thinking is displayed to users.
        By default, just strips whitespace.

        Args:
            raw_thinking: Raw thinking content from the model.

        Returns:
            Cleaned summary suitable for UI display.
        """
        return raw_thinking.strip()

    def emit_event(
        self,
        event_callback: Optional[Callable[[dict], None]],
        event_type: str,
        **kwargs: Any,
    ) -> None:
        """Helper to emit an event if callback is provided.

        Args:
            event_callback: Optional callback function.
            event_type: Type of event to emit.
            **kwargs: Additional event data.
        """
        if event_callback:
            event_callback({"type": event_type, **kwargs})
