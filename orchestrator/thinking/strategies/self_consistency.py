"""Self-Consistency strategy - multiple paths with majority voting.

This strategy generates N independent reasoning paths and uses
majority voting to select the final answer. Based on research
showing +12-18% improvement on hard reasoning tasks.

Research: Wang et al. (2022) - "Self-Consistency Improves Chain of Thought
Reasoning in Language Models" - +17.9% on GSM8K
"""

import asyncio
import re
import time
from collections import Counter
from typing import Callable, List, Optional

from orchestrator.thinking.base import (
    StreamParser,
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
    strip_thinking_tags,
)


class SelfConsistencyStrategy(ThinkingStrategy):
    """Self-Consistency: Generate multiple paths and vote on final answer.

    This strategy:
    1. Generates N independent reasoning paths using higher temperature
    2. Extracts answers from each path
    3. Uses majority voting to select the final answer
    4. Reports confidence based on vote distribution

    Best for: Complex math, logic puzzles, multi-step reasoning
    Trade-off: N times the cost/latency, but significantly better accuracy
    """

    # Reasoning prompt for each path (Mistral native format)
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
        n_samples: int = 3,
        temperature: float = 0.7,
        parallel: bool = True,
    ):
        """Initialize Self-Consistency strategy.

        Args:
            n_samples: Number of independent reasoning paths to generate.
            temperature: Sampling temperature (higher = more diverse paths).
            parallel: Whether to generate paths in parallel.
        """
        self.n_samples = n_samples
        self.temperature = temperature
        self.parallel = parallel

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "self_consistency"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute Self-Consistency reasoning.

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
            n_samples=self.n_samples,
        )

        # Prepare messages with reasoning system prompt
        sc_messages = self._prepare_messages(messages)

        # Generate N reasoning paths
        if self.parallel:
            candidates = await self._generate_parallel(sc_messages, model_call, event_callback)
        else:
            candidates = await self._generate_sequential(sc_messages, model_call, event_callback)

        # Extract answers and vote
        answers = []
        for i, (response, thinking, answer) in enumerate(candidates):
            answers.append(answer)

        # Majority vote
        vote_counts = Counter(answers)
        winner, votes = vote_counts.most_common(1)[0]
        confidence = votes / len(answers)

        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)

        # Create thinking steps for each candidate
        steps = []
        total_tokens = 0
        for i, (response, thinking, answer) in enumerate(candidates):
            is_winner = answer == winner
            step = ThinkingStep(
                seq=i + 1,
                step_type="candidate",
                raw_content=response,
                messages_sent=sc_messages,
                tokens={"input": 0, "output": len(response.split())},  # Approximate
                timing_ms=timing_ms // len(candidates),
                metadata={
                    "strategy": self.name,
                    "path_id": i + 1,
                    "answer": answer,
                    "selected": is_winner,
                },
                ui_summary=thinking[:200] + "..." if len(thinking) > 200 else thinking,
                ui_status="selected" if is_winner else "rejected",
            )
            steps.append(step)
            total_tokens += len(response.split())

        # Build thinking summary
        thinking_summary = self._build_summary(candidates, winner, votes, len(answers))

        # Emit thinking complete
        self.emit_event(
            event_callback,
            "THINKING_COMPLETE",
            strategy=self.name,
            n_samples=self.n_samples,
            confidence=confidence,
            votes=dict(vote_counts),
        )

        # Safety net: strip any thinking tags from the winning answer
        clean_winner = strip_thinking_tags(winner)

        return ThinkingResult(
            steps=steps,
            final_answer=clean_winner,
            thinking_summary=thinking_summary,
            thinking_tokens=total_tokens,
            answer_tokens=len(clean_winner.split()),
            metadata={
                "strategy": self.name,
                "n_samples": self.n_samples,
                "confidence": confidence,
                "votes": dict(vote_counts),
                "timing_ms": timing_ms,
            },
        )

    async def _generate_parallel(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]],
    ) -> List[tuple]:
        """Generate N reasoning paths in parallel.

        Returns:
            List of (full_response, thinking_content, answer_content) tuples.
        """
        async def generate_one(path_id: int) -> tuple:
            self.emit_event(
                event_callback,
                "THINKING_STEP_START",
                step=path_id,
                label=f"Reasoning path {path_id}",
            )

            # Use higher temperature for diverse reasoning
            response, usage = await model_call(messages, temperature=self.temperature)

            # Parse response
            parser = StreamParser()
            parser.feed(response)
            parser.flush()
            thinking, answer = parser.get_sections()

            # Fallback if no tags
            if not thinking and not answer:
                answer = self._extract_answer_heuristic(response)
                thinking = response

            self.emit_event(
                event_callback,
                "THINKING_STEP_COMPLETE",
                step=path_id,
            )

            return (response, thinking, answer.strip())

        # Run all paths in parallel
        tasks = [generate_one(i + 1) for i in range(self.n_samples)]
        results = await asyncio.gather(*tasks)

        return list(results)

    async def _generate_sequential(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]],
    ) -> List[tuple]:
        """Generate N reasoning paths sequentially.

        Returns:
            List of (full_response, thinking_content, answer_content) tuples.
        """
        results = []
        for i in range(self.n_samples):
            self.emit_event(
                event_callback,
                "THINKING_STEP_START",
                step=i + 1,
                label=f"Reasoning path {i + 1}",
            )

            response, usage = await model_call(messages, temperature=self.temperature)

            # Parse response
            parser = StreamParser()
            parser.feed(response)
            parser.flush()
            thinking, answer = parser.get_sections()

            # Fallback if no tags
            if not thinking and not answer:
                answer = self._extract_answer_heuristic(response)
                thinking = response

            results.append((response, thinking, answer.strip()))

            self.emit_event(
                event_callback,
                "THINKING_STEP_COMPLETE",
                step=i + 1,
            )

        return results

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

    def _extract_answer_heuristic(self, response: str) -> str:
        """Extract answer when no tags are present using heuristics.

        Looks for common answer patterns like:
        - "The answer is X"
        - "Therefore, X"
        - "Final answer: X"
        - Last line/sentence

        Args:
            response: Full response text.

        Returns:
            Extracted answer.
        """
        response = response.strip()

        # Try common patterns
        patterns = [
            r"[Tt]he answer is[:\s]+(.+?)(?:\.|$)",
            r"[Tt]herefore[,\s]+(.+?)(?:\.|$)",
            r"[Ff]inal answer[:\s]+(.+?)(?:\.|$)",
            r"[Ss]o[,\s]+(.+?)(?:\.|$)",
            r"= (.+?)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, response, re.MULTILINE | re.DOTALL)
            if match:
                return match.group(1).strip()

        # Fallback: return last non-empty line
        lines = [l.strip() for l in response.split('\n') if l.strip()]
        if lines:
            return lines[-1]

        return response

    def _build_summary(
        self,
        candidates: List[tuple],
        winner: str,
        votes: int,
        total: int,
    ) -> str:
        """Build human-readable thinking summary.

        Args:
            candidates: List of (response, thinking, answer) tuples.
            winner: The winning answer.
            votes: Number of votes for winner.
            total: Total number of paths.

        Returns:
            Human-readable summary.
        """
        lines = [f"Generated {total} reasoning paths:"]

        for i, (_, thinking, answer) in enumerate(candidates):
            selected = "selected" if answer == winner else ""
            preview = thinking[:100].replace('\n', ' ').strip()
            lines.append(f"  Path {i + 1}: {preview}... -> {answer} {selected}")

        lines.append("")
        lines.append(f"Majority vote ({votes}/{total}): {winner}")

        return "\n".join(lines)
