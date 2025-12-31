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

        Uses [THINK] tags for Ollama-served models (Mistral API uses <think>).
        StreamParser supports both formats.
        """
        return f"""Think through your reasoning process before answering. Use [THINK][/THINK] tags.

CORRECT example of internal reasoning:
[THINK]
The user asks about X. I need to consider:
1. What they actually want to know
2. Key points to cover
3. How to structure my response
Let me think about their core question...
[/THINK]

INCORRECT - this is NOT thinking, this is answering:
[THINK]
Yes! Here's what you need to know: X is great because...
[/THINK]

Now, reason through THIS question internally. Do NOT write your answer inside [THINK] tags.
Your answer comes AFTER [/THINK], not inside it.
Use plain text, no LaTeX. Budget: {budget} tokens."""

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
        phase1_result = await model_call(
            thinking_messages,
            max_tokens=self.thinking_budget,
            stop=self.STOP_SEQUENCES,  # Stop at [/THINK] or </think>
        )
        # Unpack result - supports both (text, usage) and (text, usage, reasoning)
        if len(phase1_result) == 3:
            raw_response, thinking_usage, _ = phase1_result  # Ignore native reasoning in CoT
        else:
            raw_response, thinking_usage = phase1_result

        # Check if model already included answer (Ollama often ignores stop sequences)
        existing_answer = self._extract_answer_if_present(raw_response)

        # Extract thinking content (strip tags if present)
        thinking_text = self._extract_thinking(raw_response)

        thinking_tokens = thinking_usage.get("completion_tokens", 0) if thinking_usage else 0

        # Check if model put answer inside [THINK] tags (ignored instructions)
        answer_in_thinking = self._is_answer_not_thinking(thinking_text)

        # Emit thinking step
        self.emit_event(
            event_callback,
            "THINKING_STEP",
            seq=1,
            step_type="reasoning",
            summary=thinking_text[:200] + "..." if len(thinking_text) > 200 else thinking_text,
        )

        # ===== PHASE 2: Generate answer (skip if already present or misrouted) =====
        if answer_in_thinking:
            # Model put answer inside [THINK] tags - use it directly, skip Phase 2
            answer_text = thinking_text
            thinking_text = "(Model provided direct response)"
            answer_tokens = 0  # Already counted in thinking_tokens
        elif existing_answer:
            # Model already provided answer after tags - use it directly
            answer_text = existing_answer
            answer_tokens = 0  # Already counted in thinking_tokens
        else:
            # Model only provided thinking - generate answer separately
            answer_messages = self._prepare_answer_messages(messages, thinking_text)

            phase2_result = await model_call(
                answer_messages, max_tokens=self.answer_budget
            )
            # Unpack result - supports both (text, usage) and (text, usage, reasoning)
            if len(phase2_result) == 3:
                answer_text, answer_usage, _ = phase2_result
            else:
                answer_text, answer_usage = phase2_result

            answer_tokens = answer_usage.get("completion_tokens", 0) if answer_usage else 0

        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)

        # Create thinking step for trace
        # Clean thinking for UI display (remove LaTeX gibberish)
        # If answer was misrouted to thinking, show appropriate message
        if answer_in_thinking:
            clean_thinking = "(Direct response - no internal reasoning shown)"
        else:
            clean_thinking = self._clean_thinking_for_ui(thinking_text)

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
                "answer_in_thinking": answer_in_thinking,
            },
            ui_summary=clean_thinking,
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
            thinking_summary=clean_thinking,
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

    def _clean_thinking_for_ui(self, text: str) -> str:
        """Remove LaTeX display math delimiters that look like gibberish in plain text.

        Models sometimes use \\[...\\] for display math in their reasoning,
        which renders as literal backslash-bracket when not processed as LaTeX.
        """
        # Remove \[ and \] display math delimiters
        text = re.sub(r'\\[\[\]]', '', text)
        # Remove \( and \) inline math delimiters if alone on line
        text = re.sub(r'^\s*\\[()]\s*$', '', text, flags=re.MULTILINE)
        # Clean up excess newlines created by removals
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _is_answer_not_thinking(self, text: str) -> bool:
        """Detect if thinking content is actually an answer (model ignored instructions).

        Some models put their final answer inside [THINK] tags instead of internal
        reasoning. This detects that pattern so we can handle it gracefully.

        Returns:
            True if the content looks like an answer, not reasoning.
        """
        if not text or len(text) < 50:
            return False

        text_lower = text.lower().strip()

        # Check for explicit answer markers
        answer_markers = [
            r'\*\*final answer\*\*',
            r'\\boxed\{',
            r'^here\'?s?\s+(what|how|the|my)',
        ]
        for pattern in answer_markers:
            if re.search(pattern, text_lower):
                return True

        # Check for direct response patterns at the start
        direct_response_starts = [
            r'^(yes|no|sure|absolutely|definitely|of course)[,!.\s]',
            r'^(hell yeah|yeah|yep|nope)[,!.\s]',
            r'^i can (help|do|handle|assist)',
            r'^i\'m (sure|ready|here|happy)',
        ]
        for pattern in direct_response_starts:
            if re.search(pattern, text_lower):
                return True

        # Check for reasoning indicators - if present, it's likely actual thinking
        reasoning_indicators = [
            r'(need to|should i|let me|consider|analyze|understand)',
            r'(the question is|asking about|wants to know|wondering)',
            r'(first|step \d|approach|strategy)',
            r'(key point|main idea|core issue)',
            r'(on one hand|alternatively|however)',
        ]
        has_reasoning = any(re.search(p, text_lower) for p in reasoning_indicators)

        # If no reasoning indicators and text is substantial, likely an answer
        if not has_reasoning and len(text) > 100:
            # Additional check: does it look like a formatted answer?
            # (numbered lists, bullet points, headers)
            formatted_answer = bool(re.search(r'^(\d+\.|•|-|\*\*\d)', text_lower, re.MULTILINE))
            if formatted_answer:
                return True

        return False

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
            The answer if found COMPLETE after thinking tags, None otherwise.
            Returns None if the answer appears truncated (ends mid-sentence).
        """
        if not text:
            return None

        answer = None

        # Look for content after [/THINK] tag
        match = re.search(r'\[/THINK\]\s*(.+)', text, re.DOTALL | re.IGNORECASE)
        if match:
            answer = match.group(1).strip()

        # Look for content after </think> tag
        if not answer:
            match = re.search(r'</think>\s*(.+)', text, re.DOTALL | re.IGNORECASE)
            if match:
                answer = match.group(1).strip()

        if not answer:
            return None

        # Check if the answer appears complete (not truncated mid-sentence)
        # Signs of truncation:
        # - Ends with incomplete word (no space before last character)
        # - Ends with common truncation patterns (comma, "the", "a", "and", etc.)
        # - Too short (less than 50 chars)
        if len(answer) < 50:
            return None

        # Check for common truncation indicators
        truncation_endings = [
            ', the', ', a', ', an', ', and', ', or', ', but',
            ' the', ' a', ' an', ' and', ' or', ' but',
            '..', ', ', ': ',
        ]
        answer_lower = answer.lower()
        for ending in truncation_endings:
            if answer_lower.endswith(ending):
                return None

        # Check if ends with punctuation (good sign of completion)
        if not answer.rstrip().endswith(('.', '!', '?', ')', ']', '}')):
            # Might be truncated - check if it ends mid-word
            # If last char is alphanumeric and no space before common endings, likely truncated
            if answer[-1].isalnum():
                return None

        return answer

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
