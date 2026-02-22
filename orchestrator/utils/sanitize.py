"""Text sanitization utilities for LLM output.

Handles cleaning of gpt-oss Harmony format tokens that should not be displayed to users.
"""

import re
from typing import Optional


def sanitize_harmony_tokens(text: Optional[str], *, streaming: bool = False) -> str:
    """Remove Harmony format control tokens from text.

    Args:
        text: Raw text that may contain Harmony control tokens.
        streaming: If True, preserve whitespace for token-by-token streaming.
            When processing individual streaming tokens, stripping whitespace
            would destroy inter-token spacing (e.g. " We " → "We" causing
            words to run together).

    Returns:
        Cleaned text with all control tokens removed.
    """
    if not text:
        return ""

    cleaned = text

    # Remove channel markers with their tokens first (before stripping tokens)
    # Matches: <|channel|>final<|message|>, <|channel|>commentary<|message|>, etc.
    cleaned = re.sub(
        r"<\|channel\|>(commentary|analysis|final)(?:<\|message\|>)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove <|...|> style tokens (Harmony format)
    cleaned = re.sub(r"<\|[^|]*\|>", "", cleaned)

    # Remove </...|> style tokens (closing variants)
    cleaned = re.sub(r"</[^|]*\|>", "", cleaned)

    # Remove channel/constraint annotations with tool targets
    cleaned = re.sub(
        r"\b(commentary|analysis|final)\s+to=[\w.]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove standalone channel identifiers (with optional trailing space)
    cleaned = re.sub(
        r"\b(commentary|analysis|final)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove tool target patterns
    cleaned = re.sub(r"\bto=[\w.]+\b", "", cleaned, flags=re.IGNORECASE)

    # Remove constraint markers before JSON/XML
    cleaned = re.sub(
        r"\b(json|xml|code)\b(?=\s*[\{\[])",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL)

    # Remove [THINK]...[/THINK] blocks
    cleaned = re.sub(r"\[THINK\].*?\[/THINK\]", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    if not streaming:
        # Clean up whitespace (only for complete text, not streaming tokens)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    return cleaned
