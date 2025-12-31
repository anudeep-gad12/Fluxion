"""Chain-of-Thought strategy - explicit step-by-step reasoning.

This strategy uses the TALE-EP approach (ACL 2025) for budget-aware reasoning:
1. Phase 1: Generate thinking with explicit token budget in prompt + stop sequences
2. Phase 2: Generate answer based on the thinking

The key insight: Telling the model its budget makes it naturally conclude within it.
Research shows 67% token reduction while maintaining accuracy.

Reference: Token-Budget-Aware LLM Reasoning (ACL 2025)
https://arxiv.org/html/2412.18547v4
"""

import re
import time
from typing import Callable, List, Optional

from orchestrator.thinking.base import (
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
)


class ChainOfThoughtStrategy(ThinkingStrategy):
    """Chain-of-Thought: Two-phase reasoning with controlled token budgets.

    This strategy uses TALE-EP (Token-Budget-Aware LLM Reasoning):
    - Phase 1: Generate thinking with explicit budget in prompt + stop sequences
    - Phase 2: Generate answer based on the thinking
    - Model is AWARE of its budget → naturally concludes within it
    - Stop sequences catch the closing tag → clean end

    Research basis:
    - TALE-EP (ACL 2025): 67% token reduction with budget-aware prompting
    - Wei et al. (2022): Chain-of-Thought +17.9% on GSM8K
    """

    # Stop sequences for both Mistral [THINK] and DeepSeek <think> formats
    STOP_SEQUENCES = ["[/THINK]", "</think>", "\n</think>\n", "\n[/THINK]\n"]

    # Phase 2: Answer-only prompt
    ANSWER_PROMPT = """Based on your reasoning above, now provide ONLY the final answer.
Be direct and concise. Use Markdown for formatting and LaTeX for math equations."""

    def _get_thinking_prompt(self, budget: int) -> str:
        """Generate budget-aware thinking prompt (TALE-EP approach).

        The key insight from ACL 2025 research: explicitly stating the token
        budget in the prompt makes models naturally conclude within it.

        IMPORTANT: We explicitly tell the model to START with [THINK] so the
        StreamParser can detect thinking mode and route tokens to the Thinking UI.
        """
        return f"""Think through this problem step by step.
Start your response with [THINK] and end with [/THINK].
Use less than {budget} tokens for your reasoning.
Do NOT write the final answer yet - just reason through the problem.
Be concise and focused."""

    def __init__(
        self,
        trigger_phrase: str = "Let's think step by step.",
        thinking_budget: int = 512,
        answer_budget: int = 256,
        max_tokens: int = 1024,  # Kept for backward compatibility
    ):
        """Initialize CoT strategy.

        Args:
            trigger_phrase: Optional phrase to append to user message.
            thinking_budget: Max tokens for thinking phase.
            answer_budget: Max tokens for answer phase.
            max_tokens: Backward compatibility (ignored if thinking_budget set).
        """
        self.trigger_phrase = trigger_phrase
        self.thinking_budget = thinking_budget
        self.answer_budget = answer_budget

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
        """Execute two-phase Chain-of-Thought reasoning with TALE-EP approach.

        Phase 1: Generate thinking with budget-aware prompt + stop sequences
        Phase 2: Generate answer with answer_budget tokens

        The model KNOWS its budget → naturally tries to conclude within it.
        Stop sequences catch the closing tag → clean end without cutoff.
        """
        start_time = time.time()

        # Emit thinking started
        self.emit_event(
            event_callback,
            "THINKING_START",
            strategy=self.name,
        )

        # ===== PHASE 1: Generate thinking with budget awareness =====
        thinking_messages = self._prepare_thinking_messages(messages)

        # Use stop sequences to catch natural thinking end
        raw_response, thinking_usage = await model_call(
            thinking_messages,
            max_tokens=self.thinking_budget,
            stop=self.STOP_SEQUENCES,  # Stop at [/THINK] or </think>
        )

        # Check if model already included answer (Ollama often ignores stop sequences)
        existing_answer = self._extract_answer_if_present(raw_response)

        # Extract thinking content (strip tags if present)
        thinking_text = self._extract_thinking(raw_response)

        thinking_tokens = thinking_usage.get("completion_tokens", 0) if thinking_usage else 0

        # Emit thinking step
        self.emit_event(
            event_callback,
            "THINKING_STEP",
            seq=1,
            step_type="reasoning",
            summary=thinking_text[:200] + "..." if len(thinking_text) > 200 else thinking_text,
        )

        # ===== PHASE 2: Generate answer (skip if already present) =====
        if existing_answer:
            # Model already provided answer - use it directly
            answer_text = existing_answer
            answer_tokens = 0  # Already counted in thinking_tokens
            answer_usage = {}
        else:
            # Model only provided thinking - generate answer separately
            answer_messages = self._prepare_answer_messages(messages, thinking_text)

            answer_text, answer_usage = await model_call(
                answer_messages, max_tokens=self.answer_budget
            )

            answer_tokens = answer_usage.get("completion_tokens", 0) if answer_usage else 0

        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)

        # Create thinking step for trace
        step = ThinkingStep(
            seq=1,
            step_type="reasoning",
            raw_content=f"[THINK]{thinking_text}[/THINK]\n{answer_text}",
            messages_sent=thinking_messages,
            tokens={
                "input": (thinking_usage.get("prompt_tokens", 0) if thinking_usage else 0),
                "output": thinking_tokens + answer_tokens,
            },
            timing_ms=timing_ms,
            metadata={
                "strategy": self.name,
                "two_phase": True,
                "thinking_budget": self.thinking_budget,
                "answer_budget": self.answer_budget,
            },
            ui_summary=thinking_text.strip(),
            ui_status="done",
        )

        # Emit thinking completed
        self.emit_event(
            event_callback,
            "THINKING_COMPLETE",
            strategy=self.name,
            thinking_tokens=thinking_tokens,
        )

        return ThinkingResult(
            steps=[step],
            final_answer=answer_text.strip(),
            thinking_summary=thinking_text.strip(),
            thinking_tokens=thinking_tokens,
            answer_tokens=answer_tokens,
            metadata={
                "strategy": self.name,
                "two_phase": True,
                "timing_ms": timing_ms,
            },
        )

    def _prepare_thinking_messages(self, messages: List[dict]) -> List[dict]:
        """Prepare messages for Phase 1: thinking only with budget awareness."""
        # Use budget-aware prompt (TALE-EP approach)
        result = [{"role": "system", "content": self._get_thinking_prompt(self.thinking_budget)}]

        # Add conversation history (skip original system prompt)
        for msg in messages:
            if msg["role"] != "system":
                result.append(msg.copy())

        return result

    def _extract_thinking(self, text: str) -> str:
        """Extract thinking content, stripping tags if present.

        Handles both Mistral [THINK]...[/THINK] and DeepSeek <think>...</think> formats.
        """
        if not text:
            return ""

        # Try to match [THINK]...[/THINK] format (Mistral)
        match = re.search(r'\[THINK\](.*?)\[/THINK\]', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Try to match <think>...</think> format (DeepSeek/Qwen)
        match = re.search(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # No tags found, return as-is
        return text.strip()

    def _extract_answer_if_present(self, text: str) -> str | None:
        """Extract answer from response if model included it after thinking tags.

        Some models (especially with Ollama) ignore stop sequences and output both
        thinking AND answer in one response. This detects and extracts the answer.

        Returns:
            The answer if found after thinking tags, None otherwise.
        """
        if not text:
            return None

        # Look for content after [/THINK] tag
        match = re.search(r'\[/THINK\]\s*(.+)', text, re.DOTALL | re.IGNORECASE)
        if match:
            answer = match.group(1).strip()
            if answer:
                return answer

        # Look for content after </think> tag
        match = re.search(r'</think>\s*(.+)', text, re.DOTALL | re.IGNORECASE)
        if match:
            answer = match.group(1).strip()
            if answer:
                return answer

        return None

    def _prepare_answer_messages(
        self, messages: List[dict], thinking: str
    ) -> List[dict]:
        """Prepare messages for Phase 2: answer based on thinking."""
        result = [{"role": "system", "content": self.ANSWER_PROMPT}]

        # Add conversation history (skip original system prompt)
        for msg in messages:
            if msg["role"] != "system":
                result.append(msg.copy())

        # Add the thinking as assistant's prior reasoning
        result.append({
            "role": "assistant",
            "content": f"My reasoning:\n{thinking}",
        })

        # Ask for the answer
        result.append({
            "role": "user",
            "content": "Now give me the final answer based on your reasoning.",
        })

        return result
