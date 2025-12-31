"""Direct strategy - no explicit thinking, just generate answer.

This is the simplest strategy: send messages to the model and return
the response directly. No chain-of-thought, no voting, no verification.
This is the default strategy and matches the original ChatEngine behavior.

For models with native reasoning (gpt-oss via LM Studio), this strategy
captures the reasoning output and includes it as the thinking_summary.
"""

from typing import Callable, List, Optional

from orchestrator.thinking.base import ThinkingResult, ThinkingStrategy


class DirectStrategy(ThinkingStrategy):
    """Direct strategy - no explicit thinking.

    This strategy simply calls the model once with the given messages
    and returns the response. It's the simplest approach and the default
    for the chat engine.

    This strategy:
    - Makes exactly one model call
    - Returns the response directly
    - No additional prompting or processing
    - No thinking steps (empty steps list)
    - Captures native reasoning (gpt-oss) as thinking_summary
    """

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "direct"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute direct strategy - single model call.

        Args:
            messages: List of message dicts to send to the model.
            model_call: Async function to call the model.
                Returns: (response_text, usage) or (response_text, usage, reasoning)
            event_callback: Optional callback for emitting events.

        Returns:
            ThinkingResult with the model's response.
        """
        # Emit thinking started (even though we don't really "think")
        self.emit_event(event_callback, "THINKING_STARTED", strategy=self.name)

        # Call model directly - may return 2 or 3 values
        result = await model_call(messages)

        # Unpack result - supports both (text, usage) and (text, usage, reasoning)
        if len(result) == 3:
            response_text, usage, reasoning = result
        else:
            response_text, usage = result
            reasoning = None

        # Extract token counts from usage
        answer_tokens = usage.get("completion_tokens", 0) if usage else 0

        # Use native reasoning as thinking_summary if available
        thinking_summary = reasoning or ""
        thinking_tokens = 0
        if reasoning:
            # Estimate reasoning tokens (rough approximation: 4 chars per token)
            thinking_tokens = len(reasoning) // 4

        # Emit completion
        self.emit_event(event_callback, "THINKING_COMPLETED", strategy=self.name)

        return ThinkingResult(
            steps=[],  # No thinking steps for direct strategy
            final_answer=response_text,
            thinking_summary=thinking_summary,  # Captured from native reasoning
            thinking_tokens=thinking_tokens,
            answer_tokens=answer_tokens,
            metadata={"strategy": self.name, "usage": usage, "has_reasoning": bool(reasoning)},
        )
