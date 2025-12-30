"""Base classes for thinking strategies.

This module defines the abstract interface that all thinking strategies
must implement, plus the data classes for thinking results and stream parsing.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple


def strip_thinking_tags(content: str) -> str:
    """Strip thinking tags from content and extract ONLY the answer portion.

    This function handles the case where the model outputs:
    - [THINK]...thinking...[/THINK]answer -> returns "answer"
    - [THINK]...thinking... (no closing tag) -> returns "" (still thinking, no answer yet)
    - No tags at all -> returns original content

    Handles:
    - Case variations: [THINK], [think], [Think]
    - Whitespace around tags: [ THINK ], [THINK ]
    - Legacy <think>...</think> format
    - Unclosed thinking blocks (returns empty string)

    Args:
        content: Raw content that may contain thinking tags.

    Returns:
        Clean answer content only, or empty string if no answer found.
    """
    if not content:
        return ""

    # Check for [THINK] tag (case-insensitive)
    think_pattern = r'\[\s*THINK\s*\]'
    end_think_pattern = r'\[\s*/\s*THINK\s*\]'

    has_think_open = bool(re.search(think_pattern, content, re.IGNORECASE))
    has_think_close = bool(re.search(end_think_pattern, content, re.IGNORECASE))

    if has_think_open:
        if has_think_close:
            # Extract ONLY the content after the LAST [/THINK] tag
            parts = re.split(end_think_pattern, content, flags=re.IGNORECASE)
            if len(parts) > 1:
                # Take everything after the last closing tag
                result = parts[-1].strip()
                # Clean up any remaining tags
                result = re.sub(think_pattern, '', result, flags=re.IGNORECASE)
                result = re.sub(end_think_pattern, '', result, flags=re.IGNORECASE)
                return result.strip()
            return ""
        else:
            # Opening tag without closing - model is still thinking, no answer
            return ""

    # Check for legacy <think>...</think> format
    legacy_think_pattern = r'<\s*think\s*>'
    legacy_end_pattern = r'<\s*/\s*think\s*>'

    has_legacy_open = bool(re.search(legacy_think_pattern, content, re.IGNORECASE))
    has_legacy_close = bool(re.search(legacy_end_pattern, content, re.IGNORECASE))

    if has_legacy_open:
        if has_legacy_close:
            parts = re.split(legacy_end_pattern, content, flags=re.IGNORECASE)
            if len(parts) > 1:
                result = parts[-1].strip()
                result = re.sub(legacy_think_pattern, '', result, flags=re.IGNORECASE)
                result = re.sub(legacy_end_pattern, '', result, flags=re.IGNORECASE)
                result = re.sub(r'<\s*answer\s*>', '', result, flags=re.IGNORECASE)
                result = re.sub(r'<\s*/\s*answer\s*>', '', result, flags=re.IGNORECASE)
                return result.strip()
            return ""
        else:
            return ""

    # No thinking tags found - return original content as-is
    # (This is the case where model didn't use thinking tags at all)
    return content.strip()


class StreamParser:
    """Parse streaming tokens into thinking vs answer sections.

    Detects [THINK]...[/THINK] tags (Mistral native format) in real-time
    and routes tokens to appropriate handlers. Everything after [/THINK]
    is treated as the answer (no closing answer tag needed).

    Matching is case-insensitive to handle variations like [think], [THINK], etc.

    Usage:
        parser = StreamParser()
        for token in stream:
            thinking_token, answer_token = parser.feed(token)
            if thinking_token:
                on_thinking(thinking_token)
            if answer_token:
                on_answer(answer_token)
    """

    # Tag constants for Mistral native format (uppercase for comparison)
    START_TAG = "[THINK]"
    END_TAG = "[/THINK]"
    BUFFER_SIZE = 10  # Keep chars for partial tag detection

    def __init__(self):
        self.buffer = ""
        self.in_thinking = False
        self.after_thinking = False  # Everything after [/THINK] is answer
        self.thinking_content = ""
        self.answer_content = ""

    def _find_tag(self, text: str, tag: str) -> int:
        """Find tag position in text (case-insensitive).

        Returns -1 if not found, otherwise the start index.
        """
        return text.upper().find(tag.upper())

    def _split_at_tag(self, text: str, tag: str) -> Tuple[str, str]:
        """Split text at tag position (case-insensitive).

        Returns (before, after) tuple. The tag itself is removed.
        """
        pos = self._find_tag(text, tag)
        if pos == -1:
            return text, ""
        return text[:pos], text[pos + len(tag):]

    def feed(self, token: str) -> Tuple[str, str]:
        """Process a token and return (thinking_token, answer_token).

        One of the returned values will be empty string.
        """
        self.buffer += token
        thinking_out = ""
        answer_out = ""

        # Check for tag transitions
        while True:
            if not self.in_thinking and not self.after_thinking:
                # Looking for [THINK] start tag (case-insensitive)
                if self._find_tag(self.buffer, self.START_TAG) >= 0:
                    self.in_thinking = True
                    _, self.buffer = self._split_at_tag(self.buffer, self.START_TAG)
                    continue
                else:
                    # No tag found, keep buffer for partial tag detection
                    self.buffer = self.buffer[-self.BUFFER_SIZE:]
                    break

            elif self.in_thinking:
                # Looking for [/THINK] end tag (case-insensitive)
                if self._find_tag(self.buffer, self.END_TAG) >= 0:
                    content, self.buffer = self._split_at_tag(self.buffer, self.END_TAG)
                    thinking_out += content
                    self.thinking_content += content
                    self.in_thinking = False
                    self.after_thinking = True  # Now in answer section
                    continue
                else:
                    # Output everything except potential partial tag
                    if len(self.buffer) > self.BUFFER_SIZE:
                        safe_content = self.buffer[:-self.BUFFER_SIZE]
                        self.buffer = self.buffer[-self.BUFFER_SIZE:]
                        thinking_out += safe_content
                        self.thinking_content += safe_content
                    break

            elif self.after_thinking:
                # Everything after [/THINK] is answer (no end tag needed)
                answer_out += self.buffer
                self.answer_content += self.buffer
                self.buffer = ""
                break

        return thinking_out, answer_out

    def flush(self) -> Tuple[str, str]:
        """Flush remaining buffer content."""
        thinking_out = ""
        answer_out = ""

        if self.in_thinking:
            thinking_out = self.buffer
            self.thinking_content += self.buffer
        elif self.after_thinking:
            answer_out = self.buffer
            self.answer_content += self.buffer

        self.buffer = ""
        return thinking_out, answer_out

    def get_sections(self) -> Tuple[str, str]:
        """Get accumulated thinking and answer content."""
        return self.thinking_content, self.answer_content

    def reset(self):
        """Reset parser state."""
        self.buffer = ""
        self.in_thinking = False
        self.after_thinking = False
        self.thinking_content = ""
        self.answer_content = ""


@dataclass
class ThinkingStep:
    """A single step in the thinking process with dual-layer tracing.

    Supports both internal (full observability) and user-facing (humane) traces.

    Attributes:
        seq: Sequence number for ordering steps.
        step_type: Type of step (e.g., "reasoning", "critique", "candidate", "verification").

        # Internal trace (full observability)
        raw_content: Full unfiltered model output.
        messages_sent: Exact messages sent to model for this step.
        tokens: Token counts {"input": N, "output": N}.
        timing_ms: Time taken for this step in milliseconds.
        metadata: Additional metadata (branch_id, confidence, errors, etc.).

        # User-facing trace (humane)
        ui_summary: Clean, readable summary for UI display.
        ui_status: Status indicator ("thinking", "verifying", "done").
    """

    seq: int
    step_type: str

    # Internal trace (full observability)
    raw_content: str = ""
    messages_sent: List[dict] = field(default_factory=list)
    tokens: dict = field(default_factory=lambda: {"input": 0, "output": 0})
    timing_ms: int = 0
    metadata: dict = field(default_factory=dict)

    # User-facing trace (humane)
    ui_summary: str = ""
    ui_status: str = "thinking"

    # Legacy compatibility
    @property
    def content(self) -> str:
        """Legacy accessor for raw_content."""
        return self.raw_content

    def to_internal_dict(self) -> dict:
        """Convert to internal trace format for storage."""
        return {
            "seq": self.seq,
            "step_type": self.step_type,
            "raw_content": self.raw_content,
            "messages_sent": self.messages_sent,
            "tokens": self.tokens,
            "timing_ms": self.timing_ms,
            **self.metadata,
        }

    def to_ui_dict(self) -> dict:
        """Convert to user-facing format for UI."""
        return {
            "seq": self.seq,
            "step_type": self.step_type,
            "summary": self.ui_summary,
            "status": self.ui_status,
        }


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
