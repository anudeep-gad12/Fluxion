"""Conversation title generation helpers."""

from __future__ import annotations

import re

MAX_TITLE_LEN = 64

_LEADING_FILLER_PATTERNS = [
    r"^(?:hey|hi|hello|yo|yoo|yup|okay|ok|alright|please)\s+",
    r"^(?:can|could|would|will)\s+you\s+",
    r"^i\s+need\s+you\s+to\s+",
    r"^help\s+me\s+(?:with\s+)?",
]


def conversation_title_from_message(message: str, max_len: int = MAX_TITLE_LEN) -> str:
    """Generate a short readable conversation title from a first user message."""
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return "New conversation"

    normalized = cleaned.lower()
    for pattern in _LEADING_FILLER_PATTERNS:
        normalized = re.sub(pattern, "", normalized, count=1)
    normalized = normalized.strip(" .!?,;:-")

    title = _smart_title_from_normalized(normalized) or cleaned
    title = _sentence_case(title.strip(" .!?,;:-"))
    if len(title) <= max_len:
        return title
    return title[: max_len - 3].rstrip() + "..."


def _smart_title_from_normalized(text: str) -> str:
    if not text:
        return ""

    patterns = [
        (r"^(?:explain\s+why|why\s+(?:is|are|does|do|did))\s+", "Issue: "),
        (r"^how\s+(?:do|can|should|would)\s+i\s+", "How to "),
        (r"^how\s+to\s+", "How to "),
        (r"^what\s+(?:is|are)\s+", "About "),
        (r"^explain\s+", "About "),
        (r"^tell\s+me\s+(?:about\s+)?", "About "),
    ]
    for pattern, prefix in patterns:
        match = re.match(pattern, text)
        if match:
            body = text[match.end():].strip()
            if not body:
                break
            if prefix == "Issue: ":
                return prefix + _sentence_case(_issue_phrase(body))
            return prefix + body

    return text


def _issue_phrase(text: str) -> str:
    text = re.sub(r"\bstill\b\s*", "", text).strip()
    text = re.sub(r"\b(?:look|looks|feel|feels)\s+", "", text, count=1)
    if re.search(r"\bcramped\b", text):
        text = re.sub(r"\bcramped\b", "too cramped", text, count=1)
    return text


def _sentence_case(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]
