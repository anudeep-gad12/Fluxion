"""CAR Strategy - Certainty-based Adaptive Routing.

This strategy implements the CAR approach from the paper:
"Prolonged Reasoning Is Not All You Need: Certainty-Based Adaptive Routing"

It works by:
1. First generating a short, direct answer
2. Calculating the perplexity of that answer from logprobs
3. If perplexity is high (low confidence), use TALE-EP two-phase reasoning:
   - Phase 1: Generate thinking with budget-aware prompt + stop sequences
   - Phase 2: Generate answer with answer_budget tokens
4. If perplexity is low (high confidence), return the direct answer

This avoids expensive reasoning for simple queries while ensuring
complex queries get controlled thinking that naturally concludes.

References:
- CAR: "Prolonged Reasoning Is Not All You Need"
- TALE-EP (ACL 2025): Token-Budget-Aware LLM Reasoning
"""

import math
import re
import time
from typing import Callable, List, Optional

from orchestrator.thinking.base import ThinkingResult, ThinkingStep, ThinkingStrategy


class CARStrategy(ThinkingStrategy):
    """Certainty-based Adaptive Routing strategy.

    Uses perplexity as a confidence measure to decide whether to
    use direct answering or TALE-EP budget-aware chain-of-thought reasoning.
    """

    # Prompt for short, direct answers
    SHORT_ANSWER_PROMPT = """Answer the question directly and concisely.
Give only the essential answer, no explanations or reasoning."""

    # Phase 2: Answer-only prompt (when escalating)
    ANSWER_PROMPT = """Based on your reasoning above, now provide ONLY the final answer.
Be direct and concise. Use Markdown for formatting and LaTeX for math equations."""

    # Stop sequences for both Mistral [THINK] and DeepSeek <think> formats
    STOP_SEQUENCES = ["[/THINK]", "</think>", "\n</think>\n", "\n[/THINK]\n"]

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
        ppl_threshold: float = 5.0,
        max_short_tokens: int = 100,
        thinking_budget: int = 512,
        answer_budget: int = 256,
        max_tokens: int = 1024,  # Kept for backward compatibility
    ):
        """Initialize CAR strategy.

        Args:
            ppl_threshold: Perplexity threshold. Above this = low confidence = use CoT.
                          Lower values are more aggressive (more CoT usage).
                          Typical range: 3.0 (aggressive) to 8.0 (conservative).
            max_short_tokens: Max tokens for the short answer attempt.
            thinking_budget: Max tokens for thinking phase (when escalating).
            answer_budget: Max tokens for answer phase (when escalating).
            max_tokens: Backward compatibility (ignored).
        """
        self.ppl_threshold = ppl_threshold
        self.max_short_tokens = max_short_tokens
        self.thinking_budget = thinking_budget
        self.answer_budget = answer_budget

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "car"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute CAR strategy.

        Args:
            messages: List of message dicts to send to the model.
            model_call: Async function to call the model.
            event_callback: Optional callback for emitting events.

        Returns:
            ThinkingResult with the response.
        """
        start_time = time.time()

        # Emit CAR started event
        self.emit_event(
            event_callback,
            "CAR_START",
            strategy=self.name,
        )

        # Phase 1: Try direct answer first
        short_messages = self._prepare_short_messages(messages)

        self.emit_event(
            event_callback,
            "CAR_SHORT_ANSWER",
            status="generating",
        )

        # Call model with logprobs enabled
        short_response, usage, logprobs = await model_call(
            short_messages,
            max_tokens=self.max_short_tokens,
            logprobs=True,
        )

        # Calculate perplexity
        ppl = self._calculate_perplexity(logprobs)

        self.emit_event(
            event_callback,
            "CAR_CONFIDENCE",
            perplexity=ppl,
            threshold=self.ppl_threshold,
            confident=ppl < self.ppl_threshold,
        )

        # Phase 2: Decide based on confidence
        if ppl < self.ppl_threshold:
            # High confidence - generate full response (short probe was just for perplexity)
            self.emit_event(
                event_callback,
                "CAR_DIRECT",
                reason=f"Perplexity {ppl:.2f} < threshold {self.ppl_threshold}, using direct answer",
            )

            # Generate full response with streaming (no logprobs needed)
            full_response, full_usage = await model_call(short_messages)

            timing_ms = int((time.time() - start_time) * 1000)

            self.emit_event(
                event_callback,
                "CAR_COMPLETE",
                used_reasoning=False,
                perplexity=ppl,
            )

            # Create a trace step for the direct answer (so UI can show it)
            step = ThinkingStep(
                seq=1,
                step_type="direct",
                raw_content=full_response,
                messages_sent=short_messages,
                tokens={
                    "input": full_usage.get("prompt_tokens", 0) if full_usage else 0,
                    "output": full_usage.get("completion_tokens", 0) if full_usage else 0,
                },
                timing_ms=timing_ms,
                metadata={
                    "strategy": self.name,
                    "perplexity": ppl,
                    "threshold": self.ppl_threshold,
                    "routed": "direct",
                },
                ui_summary=f"Direct answer (PPL: {ppl:.2f})",
                ui_status="done",
            )

            return ThinkingResult(
                steps=[step],
                final_answer=full_response,
                thinking_summary=f"CAR routed to direct answer (perplexity: {ppl:.2f})",
                thinking_tokens=0,
                answer_tokens=full_usage.get("completion_tokens", 0) if full_usage else 0,
                metadata={
                    "strategy": self.name,
                    "used_reasoning": False,
                    "perplexity": ppl,
                    "threshold": self.ppl_threshold,
                    "timing_ms": timing_ms,
                },
            )

        # Low confidence - trigger two-phase reasoning
        self.emit_event(
            event_callback,
            "CAR_ESCALATE",
            reason=f"Perplexity {ppl:.2f} > threshold {self.ppl_threshold}",
        )

        self.emit_event(
            event_callback,
            "THINKING_START",
            strategy="car_cot",
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

        timing_ms = int((time.time() - start_time) * 1000)

        # Create thinking step for trace
        step = ThinkingStep(
            seq=1,
            step_type="reasoning",
            raw_content=f"[THINK]{thinking_text}[/THINK]\n{answer_text}",
            messages_sent=thinking_messages,
            tokens={
                "input": thinking_usage.get("prompt_tokens", 0) if thinking_usage else 0,
                "output": thinking_tokens + answer_tokens,
            },
            timing_ms=timing_ms,
            metadata={
                "strategy": self.name,
                "escalated": True,
                "two_phase": True,
                "thinking_budget": self.thinking_budget,
                "answer_budget": self.answer_budget,
            },
            ui_summary=thinking_text[:200] + "..." if len(thinking_text) > 200 else thinking_text,
            ui_status="done",
        )

        self.emit_event(
            event_callback,
            "CAR_COMPLETE",
            used_reasoning=True,
            perplexity=ppl,
        )

        return ThinkingResult(
            steps=[step],
            final_answer=answer_text.strip(),
            thinking_summary=thinking_text.strip(),
            thinking_tokens=thinking_tokens,
            answer_tokens=answer_tokens,
            metadata={
                "strategy": self.name,
                "used_reasoning": True,
                "two_phase": True,
                "perplexity": ppl,
                "threshold": self.ppl_threshold,
                "timing_ms": timing_ms,
                "short_answer_discarded": short_response,
            },
        )

    def _calculate_perplexity(self, logprobs: Optional[List[dict]]) -> float:
        """Calculate perplexity from logprobs.

        PPL = exp(-1/N * sum(log_probs))

        Args:
            logprobs: List of logprob dicts from the model.

        Returns:
            Perplexity score. Lower = more confident.
        """
        if not logprobs:
            # No logprobs available - return high value to trigger reasoning
            return float('inf')

        total_logprob = 0.0
        count = 0

        for token_info in logprobs:
            if isinstance(token_info, dict):
                logprob = token_info.get("logprob")
                if logprob is not None:
                    total_logprob += logprob
                    count += 1
            elif isinstance(token_info, (int, float)):
                total_logprob += token_info
                count += 1

        if count == 0:
            return float('inf')

        avg_logprob = total_logprob / count
        perplexity = math.exp(-avg_logprob)

        return perplexity

    def _prepare_short_messages(self, messages: List[dict]) -> List[dict]:
        """Prepare messages for short answer generation.

        Args:
            messages: Original messages.

        Returns:
            Messages with short answer system prompt.
        """
        result = []

        for msg in messages:
            if msg["role"] == "system":
                # Replace system prompt with short answer prompt
                result.append({
                    "role": "system",
                    "content": self.SHORT_ANSWER_PROMPT,
                })
            else:
                result.append(msg.copy())

        # If no system message, prepend one
        if not any(m["role"] == "system" for m in result):
            result.insert(0, {
                "role": "system",
                "content": self.SHORT_ANSWER_PROMPT,
            })

        return result

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
