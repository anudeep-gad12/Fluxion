"""Chain-of-Thought strategy - explicit step-by-step reasoning.

This strategy prompts the model to think step by step, producing
readable reasoning that can be streamed to the user in real-time.
Uses Mistral native [THINK]/[/THINK] tags to separate thinking from final answer.

Based on research showing +17% improvement on math/reasoning tasks.
"""

import time
from typing import Callable, List, Optional

from orchestrator.thinking.base import (
    StreamParser,
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
    strip_thinking_tags,
)


class ChainOfThoughtStrategy(ThinkingStrategy):
    """Chain-of-Thought: Explicit step-by-step reasoning with streaming.

    This strategy:
    - Uses Mistral native [THINK]/[/THINK] format for reasoning
    - Streams thinking tokens in real-time
    - Parses output to separate thinking from final answer
    - Creates detailed traces for both internal and UI display

    Research basis: Wei et al. (2022) - "Chain-of-Thought Prompting Elicits
    Reasoning in Large Language Models" - +17.9% on GSM8K
    """

    # Official Mistral Reasoning system prompt (from SYSTEM_PROMPT.txt)
    REASONING_PROMPT = """# HOW YOU SHOULD THINK AND ANSWER

First draft your thinking process (inner monologue) until you arrive at a response. Format your response using Markdown, and use LaTeX for any mathematical equations. Write both your thoughts and the response in the same language as the input.

Your thinking process must follow the template below:

[THINK]
Your thoughts or/and draft, like working through an exercise on scratch paper. Be as casual and as long as you want until you are confident to generate the response to the user.
[/THINK]

Here, provide a self-contained response."""

    def __init__(self, trigger_phrase: str = "Let's think step by step."):
        """Initialize CoT strategy.

        Args:
            trigger_phrase: Optional phrase to append to user message.
        """
        self.trigger_phrase = trigger_phrase

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "cot"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute Chain-of-Thought reasoning.

        Args:
            messages: List of message dicts to send to the model.
            model_call: Async function to call the model.
            event_callback: Optional callback for emitting events.

        Returns:
            ThinkingResult with thinking trace and final answer.
        """
        start_time = time.time()

        # Emit thinking started
        self.emit_event(
            event_callback,
            "THINKING_START",
            strategy=self.name,
        )

        # Prepare messages with reasoning system prompt
        cot_messages = self._prepare_messages(messages)

        # Track the messages we're sending
        messages_sent = cot_messages.copy()

        # Call model
        response_text, usage = await model_call(cot_messages)

        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)

        # Parse response to separate thinking and answer
        parser = StreamParser()
        parser.feed(response_text)
        parser.flush()
        thinking_content, answer_content = parser.get_sections()

        # If no tags found, treat entire response as answer
        if not thinking_content and not answer_content:
            thinking_content = ""
            answer_content = response_text

        # Extract token counts
        input_tokens = usage.get("prompt_tokens", 0) if usage else 0
        output_tokens = usage.get("completion_tokens", 0) if usage else 0

        # Create thinking step
        step = ThinkingStep(
            seq=1,
            step_type="reasoning",
            raw_content=response_text,
            messages_sent=messages_sent,
            tokens={"input": input_tokens, "output": output_tokens},
            timing_ms=timing_ms,
            metadata={"strategy": self.name},
            ui_summary=thinking_content.strip() if thinking_content else "Thinking...",
            ui_status="done",
        )

        # Emit thinking step event
        self.emit_event(
            event_callback,
            "THINKING_STEP",
            seq=1,
            step_type="reasoning",
            summary=step.ui_summary[:200] + "..." if len(step.ui_summary) > 200 else step.ui_summary,
        )

        # Emit thinking completed
        self.emit_event(
            event_callback,
            "THINKING_COMPLETE",
            strategy=self.name,
            thinking_tokens=output_tokens,
        )

        # Get the answer content (prefer parsed, fallback to full response)
        raw_answer = answer_content.strip() if answer_content else response_text

        # Safety net: always strip thinking tags from final answer
        # This catches cases where streaming parser might miss tags
        clean_answer = strip_thinking_tags(raw_answer)

        return ThinkingResult(
            steps=[step],
            final_answer=clean_answer,
            thinking_summary=thinking_content.strip() if thinking_content else "",
            thinking_tokens=output_tokens,
            answer_tokens=0,  # Answer is part of same generation
            metadata={
                "strategy": self.name,
                "usage": usage,
                "timing_ms": timing_ms,
            },
        )

    def _prepare_messages(self, messages: List[dict]) -> List[dict]:
        """Prepare messages with reasoning system prompt.

        Args:
            messages: Original messages.

        Returns:
            Messages with reasoning system prompt.
        """
        result = []

        for msg in messages:
            if msg["role"] == "system":
                # Replace system prompt with reasoning prompt
                result.append({
                    "role": "system",
                    "content": self.REASONING_PROMPT,
                })
            else:
                result.append(msg.copy())

        # If no system message was found, prepend one
        if not any(m["role"] == "system" for m in result):
            result.insert(0, {
                "role": "system",
                "content": self.REASONING_PROMPT,
            })

        return result
