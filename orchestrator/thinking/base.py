"""Base classes for thinking strategies.

This module defines the abstract interface that all thinking strategies
must implement, plus the data classes for thinking results and stream parsing.
"""

import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple


def strip_thinking_tags(content: str) -> str:
    """Strip thinking tags from content and extract ONLY the answer portion.

    This function handles the case where the model outputs:
    - [THINK]...thinking...[/THINK]answer -> returns "answer"
    - [THINK]...thinking... (no closing tag) -> returns "" (still thinking, no answer yet)
    - Harmony format: ...thinking...<|channel|>final<|message|>answer -> returns "answer"
    - No tags at all -> returns original content

    Handles:
    - Case variations: [THINK], [think], [Think]
    - Whitespace around tags: [ THINK ], [THINK ]
    - Legacy <think>...</think> format
    - Harmony format (gpt-oss) with <|channel|>final<|message|> marker
    - Unclosed thinking blocks (returns empty string)

    Args:
        content: Raw content that may contain thinking tags.

    Returns:
        Clean answer content only, or empty string if no answer found.
    """
    if not content:
        return ""

    # Check for Harmony format first (gpt-oss models)
    # <|channel|>final<|message|> marks start of final answer
    harmony_marker = "<|channel|>final<|message|>"
    if harmony_marker in content:
        parts = content.split(harmony_marker, 1)
        if len(parts) > 1:
            answer = parts[1].strip()
            # Strip any remaining Harmony tokens from answer
            answer = re.sub(r'<\|[^|]*\|>', '', answer)
            return answer.strip()
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

    # Tag constants - support multiple formats for maximum compatibility
    # Mistral API reasoning models use <think> natively
    # Ollama-served models often use [THINK] when prompted
    # gpt-oss models use Harmony format with channels (analysis=thinking, final=answer)
    START_TAGS = ["<think>", "[think]"]  # Check both formats
    END_TAGS = ["</think>", "[/think]"]  # Check both formats
    # Native reasoning marker - used when reasoning comes from API field (e.g., gpt-oss via LM Studio)
    NATIVE_REASONING_MARKER = "[THINK_NATIVE]"
    # Harmony format: <|channel|>final<|message|> marks start of final answer
    # Everything before this (in analysis channel) is reasoning
    HARMONY_ANSWER_MARKER = "<|channel|>final<|message|>"
    HARMONY_END_TAG = "<|end|>"
    BUFFER_SIZE = 50  # Increased for longer Harmony tokens
    DIRECT_THRESHOLD = 50  # After this many chars without think tag, treat as direct answer

    def __init__(self):
        self.buffer = ""
        self.in_thinking = False
        self.after_thinking = False  # Everything after closing think tag is answer
        self.is_direct = False  # No thinking tags detected, treat as direct answer
        self.is_harmony = False  # gpt-oss Harmony format detected
        self.thinking_content = ""
        self.answer_content = ""
        self.total_received = 0  # Track total chars received
        self.detected_end_tag = None  # Remember which end tag format to look for

    def _find_any_tag(self, text: str, tags: list) -> Tuple[int, str]:
        """Find any of the tags in text (case-insensitive).

        Returns (position, matched_tag) or (-1, None) if not found.
        """
        text_upper = text.upper()
        for tag in tags:
            pos = text_upper.find(tag.upper())
            if pos >= 0:
                return pos, tag
        return -1, None

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

    def _strip_harmony_tokens(self, text: str) -> str:
        """Strip Harmony format tokens from text.

        Removes tokens like <|end|>, <|start|>, <|channel|>analysis, etc.
        keeping only the actual content.
        """
        import re
        # Remove all <|...|> style tokens
        cleaned = re.sub(r'<\|[^|]*\|>', '', text)
        # Remove channel identifiers that may appear without proper tokens
        cleaned = re.sub(r'\b(analysis|commentary|final)\b', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def feed(self, token: str, debug: bool = False) -> Tuple[str, str]:
        """Process a token and return (thinking_token, answer_token).

        One of the returned values will be empty string.
        """
        self.buffer += token
        self.total_received += len(token)
        thinking_out = ""
        answer_out = ""

        if debug:
            sys.stderr.write(f"[StreamParser] feed: token={repr(token[:20] if len(token) > 20 else token)}, in_thinking={self.in_thinking}, after_thinking={self.after_thinking}, is_direct={self.is_direct}, buffer_len={len(self.buffer)}\n")
            sys.stderr.flush()

        # Check for tag transitions
        while True:
            # Check for native reasoning marker first (gpt-oss via LM Studio API field)
            # This marker is added by chat_engine when reasoning comes from a separate API field
            native_pos = self.buffer.find(self.NATIVE_REASONING_MARKER)
            if native_pos >= 0:
                # Any content before the marker (shouldn't be any) goes to answer
                if native_pos > 0:
                    answer_out += self.buffer[:native_pos]
                    self.answer_content += self.buffer[:native_pos]
                # Content after the marker is reasoning - emit directly
                reasoning_content = self.buffer[native_pos + len(self.NATIVE_REASONING_MARKER):]
                if reasoning_content:
                    thinking_out += reasoning_content
                    self.thinking_content += reasoning_content
                self.buffer = ""
                self.in_thinking = True  # Mark that we're receiving thinking content
                if debug:
                    sys.stderr.write(f"[StreamParser] NATIVE REASONING: {len(reasoning_content)} chars\n")
                    sys.stderr.flush()
                break

            # Check for Harmony format first (gpt-oss models)
            # Look for <|channel|>final<|message|> which marks start of final answer
            harmony_pos = self.buffer.find(self.HARMONY_ANSWER_MARKER)
            if harmony_pos >= 0:
                self.is_harmony = True
                # Everything before the marker is thinking (analysis channel)
                thinking_content = self.buffer[:harmony_pos]
                # Strip any leading Harmony tokens from thinking content
                thinking_content = self._strip_harmony_tokens(thinking_content)
                if thinking_content:
                    thinking_out += thinking_content
                    self.thinking_content += thinking_content
                # Everything after the marker is the final answer
                answer_start = harmony_pos + len(self.HARMONY_ANSWER_MARKER)
                self.buffer = self.buffer[answer_start:]
                self.in_thinking = False
                self.after_thinking = True
                if debug:
                    sys.stderr.write(f"[StreamParser] HARMONY FORMAT: Found final channel marker\n")
                    sys.stderr.flush()
                continue

            if self.is_direct:
                # Direct answer mode - emit everything as answer
                answer_out += self.buffer
                self.answer_content += self.buffer
                self.buffer = ""
                break

            if not self.in_thinking and not self.after_thinking:
                # Looking for any start tag (case-insensitive) - supports <think> and [THINK]
                pos, matched_tag = self._find_any_tag(self.buffer, self.START_TAGS)
                if pos >= 0:
                    self.in_thinking = True
                    # Remember which end tag format to look for based on start tag
                    if matched_tag.startswith("<"):
                        self.detected_end_tag = "</think>"
                    else:
                        self.detected_end_tag = "[/think]"
                    if debug:
                        sys.stderr.write(f"[StreamParser] THINKING MODE: Found {matched_tag} tag\n")
                        sys.stderr.flush()
                    # Any content BEFORE the [THINK] tag goes to answer (preamble)
                    preamble = self.buffer[:pos].strip()
                    if preamble:
                        answer_out += preamble
                        self.answer_content += preamble
                    _, self.buffer = self._split_at_tag(self.buffer, matched_tag)
                    continue
                elif self.total_received > self.DIRECT_THRESHOLD:
                    # No think tag after threshold, treat as direct answer
                    self.is_direct = True
                    if debug:
                        sys.stderr.write(f"[StreamParser] DIRECT MODE: No think tag found after {self.total_received} chars\n")
                        sys.stderr.flush()
                    answer_out += self.buffer
                    self.answer_content += self.buffer
                    self.buffer = ""
                    break
                else:
                    # Still looking for tag - DO NOT emit anything yet
                    # Buffer content until we've made a decision (found tag or passed threshold)
                    # This prevents premature emission that causes UI confusion
                    break

            elif self.in_thinking:
                # Looking for end tag (case-insensitive) - try detected format first, then any
                end_tag = self.detected_end_tag or "</think>"
                # Try detected end tag first
                pos = self._find_tag(self.buffer, end_tag)
                if pos < 0:
                    # Try alternative end tag format
                    for alt_tag in self.END_TAGS:
                        pos = self._find_tag(self.buffer, alt_tag)
                        if pos >= 0:
                            end_tag = alt_tag
                            break
                if pos >= 0:
                    content, self.buffer = self._split_at_tag(self.buffer, end_tag)
                    thinking_out += content
                    self.thinking_content += content
                    self.in_thinking = False
                    self.after_thinking = True  # Now in answer section
                    if debug:
                        sys.stderr.write(f"[StreamParser] END TAG FOUND: transitioning to answer mode\n")
                        sys.stderr.flush()
                    continue
                else:
                    # We're IN thinking mode - emit content more aggressively
                    # Only hold back enough for potential end tag (9 chars for "[/think]")
                    END_TAG_MAX_LEN = 9
                    if len(self.buffer) > END_TAG_MAX_LEN:
                        safe_content = self.buffer[:-END_TAG_MAX_LEN]
                        self.buffer = self.buffer[-END_TAG_MAX_LEN:]
                        thinking_out += safe_content
                        self.thinking_content += safe_content
                    break

            elif self.after_thinking:
                # Everything after [/THINK] is answer (no end tag needed)
                answer_out += self.buffer
                self.answer_content += self.buffer
                self.buffer = ""
                break

        if debug and (thinking_out or answer_out):
            sys.stderr.write(f"[StreamParser] emit: thinking={repr(thinking_out[:50] if len(thinking_out) > 50 else thinking_out)}, answer={repr(answer_out[:50] if len(answer_out) > 50 else answer_out)}\n")
            sys.stderr.flush()

        return thinking_out, answer_out

    def flush(self) -> Tuple[str, str]:
        """Flush remaining buffer content."""
        thinking_out = ""
        answer_out = ""

        if self.in_thinking:
            thinking_out = self.buffer
            self.thinking_content += self.buffer
        elif self.after_thinking or self.is_direct:
            answer_out = self.buffer
            self.answer_content += self.buffer
        else:
            # Never saw [THINK] tag, treat remaining as answer
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
        self.is_direct = False
        self.is_harmony = False
        self.thinking_content = ""
        self.answer_content = ""
        self.total_received = 0


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
