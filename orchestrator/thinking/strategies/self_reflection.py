"""Self-Reflection strategy - critique and revise loop.

This strategy generates an initial answer, then critiques it for errors
and improvements, revising if necessary. Based on research showing
+4-6% improvement on benchmarks.

Research: Madaan et al. (2023) - "Self-Refine: Iterative Refinement with
Self-Feedback"
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


class SelfReflectionStrategy(ThinkingStrategy):
    """Self-Reflection: Critique and revise loop.

    This strategy:
    1. Generates initial answer with reasoning
    2. Critiques the answer for errors, gaps, or improvements
    3. Revises if issues are found (up to max_iterations)
    4. Returns final refined answer

    Best for: Tasks where quality matters more than speed
    Trade-off: 2-3x cost/latency, but improved accuracy
    """

    # Initial reasoning prompt (Mistral native format)
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

    # Critique prompt
    CRITIQUE_PROMPT = """You are a careful reviewer. Analyze the following response for:

1. Factual errors or mistakes in reasoning
2. Missing steps or incomplete analysis
3. Unclear explanations
4. Opportunities for improvement

Previous response to critique:
{response}

Format your critique as:

<critique>
[List specific issues you found, or state "No issues found" if the answer is correct]
</critique>

<should_revise>
[YES if there are significant issues to fix, NO if the answer is good]
</should_revise>

Be thorough but fair. Only recommend revision for actual errors or significant improvements."""

    # Revision prompt (Mistral native format)
    REVISION_PROMPT = """Based on this critique, provide an improved response.

Original response:
{original_response}

Critique:
{critique}

Provide your revised response using this template:
[THINK]
Your improved reasoning, addressing the critique.
[/THINK]
Your revised answer, incorporating improvements."""

    def __init__(self, max_iterations: int = 2):
        """Initialize Self-Reflection strategy.

        Args:
            max_iterations: Maximum number of critique-revise cycles.
        """
        self.max_iterations = max_iterations

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "self_reflection"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute Self-Reflection reasoning.

        Args:
            messages: List of message dicts to send to the model.
            model_call: Async function to call the model.
            event_callback: Optional callback for emitting events.

        Returns:
            ThinkingResult with thinking trace and final answer.
        """
        start_time = time.time()
        steps = []
        step_seq = 0

        # Emit thinking started
        self.emit_event(
            event_callback,
            "THINKING_START",
            strategy=self.name,
            max_iterations=self.max_iterations,
        )

        # Step 1: Generate initial response
        step_seq += 1
        self.emit_event(
            event_callback,
            "THINKING_STEP_START",
            step=step_seq,
            label="Initial reasoning",
        )

        initial_messages = self._prepare_messages_for_reasoning(messages)
        initial_response, initial_usage = await model_call(initial_messages)

        # Parse initial response
        parser = StreamParser()
        parser.feed(initial_response)
        parser.flush()
        initial_thinking, initial_answer = parser.get_sections()

        if not initial_thinking and not initial_answer:
            initial_answer = initial_response
            initial_thinking = ""

        # Record initial step
        initial_step = ThinkingStep(
            seq=step_seq,
            step_type="reasoning",
            raw_content=initial_response,
            messages_sent=initial_messages,
            tokens={"input": initial_usage.get("prompt_tokens", 0), "output": initial_usage.get("completion_tokens", 0)},
            timing_ms=0,  # Will calculate total at end
            metadata={"strategy": self.name, "phase": "initial"},
            ui_summary=initial_thinking[:200] + "..." if len(initial_thinking) > 200 else initial_thinking,
            ui_status="done",
        )
        steps.append(initial_step)

        self.emit_event(
            event_callback,
            "THINKING_STEP_COMPLETE",
            step=step_seq,
        )

        # Current best response
        current_response = initial_response
        current_thinking = initial_thinking
        current_answer = initial_answer.strip()
        total_tokens = initial_usage.get("completion_tokens", 0)

        # Iterate: critique and revise
        for iteration in range(self.max_iterations):
            # Step 2: Critique
            step_seq += 1
            self.emit_event(
                event_callback,
                "THINKING_STEP_START",
                step=step_seq,
                label=f"Critique (iteration {iteration + 1})",
            )

            critique_messages = self._prepare_messages_for_critique(messages, current_response)
            critique_response, critique_usage = await model_call(critique_messages)

            # Parse critique
            critique_text, should_revise = self._parse_critique(critique_response)

            # Record critique step
            critique_step = ThinkingStep(
                seq=step_seq,
                step_type="critique",
                raw_content=critique_response,
                messages_sent=critique_messages,
                tokens={"input": critique_usage.get("prompt_tokens", 0), "output": critique_usage.get("completion_tokens", 0)},
                timing_ms=0,
                metadata={
                    "strategy": self.name,
                    "phase": "critique",
                    "iteration": iteration + 1,
                    "should_revise": should_revise,
                },
                ui_summary=f"Critique: {critique_text[:150]}..." if len(critique_text) > 150 else f"Critique: {critique_text}",
                ui_status="done",
            )
            steps.append(critique_step)
            total_tokens += critique_usage.get("completion_tokens", 0)

            self.emit_event(
                event_callback,
                "THINKING_STEP_COMPLETE",
                step=step_seq,
                should_revise=should_revise,
            )

            # Check if revision needed
            if not should_revise:
                # No issues found, we're done
                break

            # Step 3: Revise
            step_seq += 1
            self.emit_event(
                event_callback,
                "THINKING_STEP_START",
                step=step_seq,
                label=f"Revision (iteration {iteration + 1})",
            )

            revision_messages = self._prepare_messages_for_revision(
                messages, current_response, critique_text
            )
            revision_response, revision_usage = await model_call(revision_messages)

            # Parse revision
            parser.reset()
            parser.feed(revision_response)
            parser.flush()
            revised_thinking, revised_answer = parser.get_sections()

            if not revised_thinking and not revised_answer:
                revised_answer = revision_response
                revised_thinking = ""

            # Record revision step
            revision_step = ThinkingStep(
                seq=step_seq,
                step_type="revision",
                raw_content=revision_response,
                messages_sent=revision_messages,
                tokens={"input": revision_usage.get("prompt_tokens", 0), "output": revision_usage.get("completion_tokens", 0)},
                timing_ms=0,
                metadata={
                    "strategy": self.name,
                    "phase": "revision",
                    "iteration": iteration + 1,
                },
                ui_summary=revised_thinking[:200] + "..." if len(revised_thinking) > 200 else revised_thinking,
                ui_status="done",
            )
            steps.append(revision_step)
            total_tokens += revision_usage.get("completion_tokens", 0)

            # Update current response
            current_response = revision_response
            current_thinking = revised_thinking
            current_answer = revised_answer.strip()

            self.emit_event(
                event_callback,
                "THINKING_STEP_COMPLETE",
                step=step_seq,
            )

        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)

        # Build thinking summary
        thinking_summary = self._build_summary(steps, current_answer)

        # Emit thinking complete
        self.emit_event(
            event_callback,
            "THINKING_COMPLETE",
            strategy=self.name,
            total_steps=len(steps),
            iterations=min(iteration + 1 for iteration in range(self.max_iterations)),
        )

        # Safety net: strip any thinking tags from the final answer
        clean_answer = strip_thinking_tags(current_answer)

        return ThinkingResult(
            steps=steps,
            final_answer=clean_answer,
            thinking_summary=thinking_summary,
            thinking_tokens=total_tokens,
            answer_tokens=len(clean_answer.split()),
            metadata={
                "strategy": self.name,
                "iterations": len([s for s in steps if s.step_type == "revision"]) + 1,
                "timing_ms": timing_ms,
            },
        )

    def _prepare_messages_for_reasoning(self, messages: List[dict]) -> List[dict]:
        """Prepare messages with reasoning system prompt."""
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

    def _prepare_messages_for_critique(
        self, messages: List[dict], response: str
    ) -> List[dict]:
        """Prepare messages for critique phase."""
        # Get original query
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

        return [
            {
                "role": "system",
                "content": self.CRITIQUE_PROMPT.format(response=response),
            },
            {
                "role": "user",
                "content": f"Original question: {query}\n\nCritique the response above.",
            },
        ]

    def _prepare_messages_for_revision(
        self, messages: List[dict], original_response: str, critique: str
    ) -> List[dict]:
        """Prepare messages for revision phase."""
        # Get original query
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

        return [
            {
                "role": "system",
                "content": self.REVISION_PROMPT.format(
                    original_response=original_response,
                    critique=critique,
                ),
            },
            {
                "role": "user",
                "content": f"Original question: {query}\n\nProvide your revised response.",
            },
        ]

    def _parse_critique(self, response: str) -> tuple:
        """Parse critique response to extract critique text and revision decision.

        Returns:
            Tuple of (critique_text, should_revise)
        """
        # Extract critique text
        critique_text = ""
        if "<critique>" in response and "</critique>" in response:
            start = response.index("<critique>") + len("<critique>")
            end = response.index("</critique>")
            critique_text = response[start:end].strip()
        else:
            # Fallback: use entire response as critique
            critique_text = response.strip()

        # Determine if revision is needed
        should_revise = False
        if "<should_revise>" in response and "</should_revise>" in response:
            start = response.index("<should_revise>") + len("<should_revise>")
            end = response.index("</should_revise>")
            decision = response[start:end].strip().upper()
            should_revise = decision == "YES"
        else:
            # Fallback: check for keywords
            critique_lower = critique_text.lower()
            should_revise = any(
                word in critique_lower
                for word in ["error", "mistake", "incorrect", "wrong", "issue", "problem"]
            ) and not (
                "no error" in critique_lower
                or "no issue" in critique_lower
                or "correct" in critique_lower
            )

        return critique_text, should_revise

    def _build_summary(self, steps: List[ThinkingStep], final_answer: str) -> str:
        """Build human-readable thinking summary."""
        lines = [f"Self-reflection with {len(steps)} steps:"]

        for step in steps:
            if step.step_type == "reasoning":
                lines.append(f"  1. Initial reasoning: {step.ui_summary[:100]}...")
            elif step.step_type == "critique":
                should_revise = step.metadata.get("should_revise", False)
                revision_needed = "needs revision" if should_revise else "looks good"
                lines.append(f"  {step.seq}. Critique: {revision_needed}")
            elif step.step_type == "revision":
                lines.append(f"  {step.seq}. Revised answer")

        lines.append("")
        lines.append(f"Final answer: {final_answer[:100]}..." if len(final_answer) > 100 else f"Final answer: {final_answer}")

        return "\n".join(lines)
