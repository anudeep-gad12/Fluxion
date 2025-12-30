"""CAR Strategy - Certainty-based Adaptive Routing.

This strategy implements the CAR approach from the paper:
"Prolonged Reasoning Is Not All You Need: Certainty-Based Adaptive Routing"

It works by:
1. First generating a short, direct answer
2. Calculating the perplexity of that answer from logprobs
3. If perplexity is high (low confidence), retry with full CoT reasoning
4. If perplexity is low (high confidence), return the short answer

This avoids expensive reasoning for simple queries while ensuring
complex queries get the thinking they need.
"""

import math
import time
from typing import Callable, List, Optional

from orchestrator.thinking.base import ThinkingResult, ThinkingStep, ThinkingStrategy


class CARStrategy(ThinkingStrategy):
    """Certainty-based Adaptive Routing strategy.

    Uses perplexity as a confidence measure to decide whether to
    use direct answering or chain-of-thought reasoning.
    """

    # Prompt for short, direct answers
    SHORT_ANSWER_PROMPT = """Answer the question directly and concisely. 
Give only the essential answer, no explanations or reasoning."""

    # Prompt for full reasoning (when confidence is low)
    REASONING_PROMPT = """You are a thoughtful reasoning assistant. When solving problems:

1. Think out loud in a clear, readable way
2. Use simple language a human would understand
3. Structure your thinking with bullet points or numbered steps
4. Show your work naturally, as if explaining to a friend

Your thinking process must follow this template:
[THINK]
Your thoughts or draft, like working through an exercise on scratch paper.
Be as casual and as long as you want until you are confident to generate a correct answer.
[/THINK]
Here, provide a concise, self-contained response.

Think step by step. Be thorough but readable."""

    def __init__(
        self,
        ppl_threshold: float = 5.0,
        max_short_tokens: int = 100,
    ):
        """Initialize CAR strategy.

        Args:
            ppl_threshold: Perplexity threshold. Above this = low confidence = use CoT.
                          Lower values are more aggressive (more CoT usage).
                          Typical range: 3.0 (aggressive) to 8.0 (conservative).
            max_short_tokens: Max tokens for the short answer attempt.
        """
        self.ppl_threshold = ppl_threshold
        self.max_short_tokens = max_short_tokens

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

        # Low confidence - trigger full reasoning
        self.emit_event(
            event_callback,
            "CAR_ESCALATE",
            reason=f"Perplexity {ppl:.2f} > threshold {self.ppl_threshold}",
        )

        # Prepare reasoning messages
        reasoning_messages = self._prepare_reasoning_messages(messages)

        self.emit_event(
            event_callback,
            "THINKING_START",
            strategy="car_cot",
        )

        # Call model with reasoning prompt
        reasoning_response, reasoning_usage = await model_call(reasoning_messages)

        timing_ms = int((time.time() - start_time) * 1000)

        # Parse thinking from response
        thinking_content, answer_content = self._parse_thinking(reasoning_response)

        # Create thinking step
        step = ThinkingStep(
            seq=1,
            step_type="reasoning",
            raw_content=reasoning_response,
            messages_sent=reasoning_messages,
            tokens={
                "input": reasoning_usage.get("prompt_tokens", 0) if reasoning_usage else 0,
                "output": reasoning_usage.get("completion_tokens", 0) if reasoning_usage else 0,
            },
            timing_ms=timing_ms,
            metadata={"strategy": self.name, "escalated": True},
            ui_summary=thinking_content[:200] + "..." if len(thinking_content) > 200 else thinking_content,
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
            final_answer=answer_content or reasoning_response,
            thinking_summary=thinking_content,
            thinking_tokens=reasoning_usage.get("completion_tokens", 0) if reasoning_usage else 0,
            answer_tokens=0,
            metadata={
                "strategy": self.name,
                "used_reasoning": True,
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

    def _prepare_reasoning_messages(self, messages: List[dict]) -> List[dict]:
        """Prepare messages for reasoning generation.

        Args:
            messages: Original messages.

        Returns:
            Messages with reasoning system prompt.
        """
        result = []

        for msg in messages:
            if msg["role"] == "system":
                result.append({
                    "role": "system",
                    "content": self.REASONING_PROMPT,
                })
            else:
                result.append(msg.copy())

        if not any(m["role"] == "system" for m in result):
            result.insert(0, {
                "role": "system",
                "content": self.REASONING_PROMPT,
            })

        return result

    def _parse_thinking(self, response: str) -> tuple[str, str]:
        """Parse thinking and answer from response.

        Args:
            response: Full model response.

        Returns:
            Tuple of (thinking_content, answer_content).
        """
        import re

        # Look for [THINK]...[/THINK] pattern
        think_pattern = r'\[THINK\](.*?)\[/THINK\]'
        match = re.search(think_pattern, response, re.DOTALL | re.IGNORECASE)

        if match:
            thinking = match.group(1).strip()
            # Everything after [/THINK] is the answer
            answer_start = match.end()
            answer = response[answer_start:].strip()
            return thinking, answer

        # No tags found - return empty thinking
        return "", response
