"""Chain-of-Draft strategy - minimal reasoning with maximum efficiency.

This strategy uses extremely concise drafts per reasoning step,
achieving up to 80% token reduction while maintaining accuracy.
Ideal for token-constrained scenarios or when speed is critical.

Research: Based on "Chain-of-Draft" prompting technique that limits
reasoning to minimal words per step (typically 5 words max).
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


class ChainOfDraftStrategy(ThinkingStrategy):
    """Chain-of-Draft: Minimal words per reasoning step.

    This strategy:
    1. Prompts the model to use extremely concise reasoning
    2. Each step limited to ~5 words
    3. Maintains logical flow with minimal tokens
    4. Produces final answer after brief reasoning chain

    Best for: Token-constrained scenarios, fast responses
    Trade-off: Less verbose reasoning, but similar accuracy
    """

    # Minimal draft reasoning prompt (Mistral native format)
    DRAFT_PROMPT = """You are an efficient reasoning assistant. Think in minimal drafts.

Rules:
1. Each reasoning step must be 5 words or fewer
2. Use abbreviations and symbols when possible
3. Skip obvious steps
4. Get to the answer quickly

Your thinking must follow this template:
[THINK]
step1: [max 5 words]
step2: [max 5 words]
step3: [max 5 words]
[/THINK]
Your final answer here.

Be extremely concise. Every word counts."""

    def __init__(self, max_words_per_step: int = 5):
        """Initialize Chain-of-Draft strategy.

        Args:
            max_words_per_step: Maximum words allowed per reasoning step.
        """
        self.max_words_per_step = max_words_per_step

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "chain_of_draft"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute Chain-of-Draft reasoning.

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
            max_words_per_step=self.max_words_per_step,
        )

        # Emit step start
        self.emit_event(
            event_callback,
            "THINKING_STEP_START",
            step=1,
            label="Draft reasoning",
        )

        # Prepare messages with draft prompt
        draft_messages = self._prepare_messages(messages)

        # Call model
        response_text, usage = await model_call(draft_messages)

        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)

        # Parse response
        parser = StreamParser()
        parser.feed(response_text)
        parser.flush()
        thinking_content, answer_content = parser.get_sections()

        # Fallback if no tags
        if not thinking_content and not answer_content:
            thinking_content = ""
            answer_content = response_text

        # Count draft steps
        draft_steps = self._count_draft_steps(thinking_content)

        # Calculate token savings (estimate)
        input_tokens = usage.get("prompt_tokens", 0) if usage else 0
        output_tokens = usage.get("completion_tokens", 0) if usage else 0

        # Create thinking step
        step = ThinkingStep(
            seq=1,
            step_type="draft_reasoning",
            raw_content=response_text,
            messages_sent=draft_messages,
            tokens={"input": input_tokens, "output": output_tokens},
            timing_ms=timing_ms,
            metadata={
                "strategy": self.name,
                "draft_steps": draft_steps,
                "max_words_per_step": self.max_words_per_step,
            },
            ui_summary=self._format_draft_summary(thinking_content),
            ui_status="done",
        )

        # Emit step complete
        self.emit_event(
            event_callback,
            "THINKING_STEP_COMPLETE",
            step=1,
            draft_steps=draft_steps,
        )

        # Emit thinking complete
        self.emit_event(
            event_callback,
            "THINKING_COMPLETE",
            strategy=self.name,
            draft_steps=draft_steps,
            tokens_used=output_tokens,
        )

        # Build summary
        thinking_summary = self._build_summary(thinking_content, draft_steps)

        # Get raw answer (prefer parsed, fallback to full response)
        raw_answer = answer_content.strip() if answer_content else response_text

        # Safety net: strip any thinking tags from the final answer
        clean_answer = strip_thinking_tags(raw_answer)

        return ThinkingResult(
            steps=[step],
            final_answer=clean_answer,
            thinking_summary=thinking_summary,
            thinking_tokens=output_tokens,
            answer_tokens=0,
            metadata={
                "strategy": self.name,
                "draft_steps": draft_steps,
                "timing_ms": timing_ms,
                "usage": usage,
            },
        )

    def _prepare_messages(self, messages: List[dict]) -> List[dict]:
        """Prepare messages with draft system prompt.

        Args:
            messages: Original messages.

        Returns:
            Messages with draft system prompt.
        """
        result = []

        for msg in messages:
            if msg["role"] == "system":
                # Replace system prompt with draft prompt
                result.append({
                    "role": "system",
                    "content": self.DRAFT_PROMPT,
                })
            else:
                result.append(msg.copy())

        # If no system message was found, prepend one
        if not any(m["role"] == "system" for m in result):
            result.insert(0, {
                "role": "system",
                "content": self.DRAFT_PROMPT,
            })

        return result

    def _count_draft_steps(self, thinking_content: str) -> int:
        """Count the number of draft steps in thinking content.

        Args:
            thinking_content: The thinking section content.

        Returns:
            Number of draft steps found.
        """
        if not thinking_content:
            return 0

        # Count lines that look like steps (step1:, step2:, 1., 2., -, etc.)
        lines = [l.strip() for l in thinking_content.split('\n') if l.strip()]
        step_count = 0

        for line in lines:
            # Check for step patterns
            if any(line.lower().startswith(p) for p in ['step', '1.', '2.', '3.', '4.', '5.', '-', '*', '>']):
                step_count += 1
            elif ':' in line and len(line.split(':')[0]) < 10:
                # Short prefix with colon (like "s1:" or "calc:")
                step_count += 1

        return max(step_count, len(lines))

    def _format_draft_summary(self, thinking_content: str) -> str:
        """Format draft content for UI display.

        Args:
            thinking_content: Raw thinking content.

        Returns:
            Formatted summary for UI.
        """
        if not thinking_content:
            return "Quick reasoning..."

        # Clean up and format
        lines = [l.strip() for l in thinking_content.split('\n') if l.strip()]
        if len(lines) <= 3:
            return " -> ".join(lines)
        else:
            return " -> ".join(lines[:3]) + f" -> ... ({len(lines)} steps)"

    def _build_summary(self, thinking_content: str, draft_steps: int) -> str:
        """Build human-readable thinking summary.

        Args:
            thinking_content: Raw thinking content.
            draft_steps: Number of draft steps.

        Returns:
            Human-readable summary.
        """
        lines = [f"Chain-of-Draft ({draft_steps} minimal steps):"]

        if thinking_content:
            # Show the actual draft steps
            draft_lines = [l.strip() for l in thinking_content.split('\n') if l.strip()]
            for line in draft_lines[:5]:  # Show first 5 steps
                lines.append(f"  {line}")
            if len(draft_lines) > 5:
                lines.append(f"  ... and {len(draft_lines) - 5} more steps")

        return "\n".join(lines)
