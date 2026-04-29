"""Intent classification for coding-agent turns."""

from __future__ import annotations

import re
from enum import StrEnum


class AgentIntent(StrEnum):
    """High-level routing intent for a user turn."""

    ACTIONABLE_WORKSPACE = "actionable_workspace"
    READ_ONLY_WORKSPACE = "read_only_workspace"
    CONVERSATIONAL = "conversational"
    AMBIGUOUS = "ambiguous"


_ACTIONABLE_PATTERNS = [
    (
        r"\b(fix|repair|resolve|debug|implement|add|create|write|edit|change|modify|"
        r"update|refactor|remove|delete|wire|hook up|integrate|migrate)\b"
    ),
    r"\b(run|execute)\b.+\b(test|build|lint|typecheck|pytest|npm|pnpm|uv|script|command)\b",
    r"\b(test|verify|validate)\b.+\b(it|this|change|fix|build|flow|feature|bug)\b",
    r"\b(do it|go ahead|ship it|make it happen|apply (that|those)|take care of it)\b",
]
_READ_ONLY_PATTERNS = [
    (
        r"\b(inspect|investigate|look into|check|review|explain|find|search|"
        r"trace|analyze|audit)\b"
    ),
    (
        r"\b(where|why|how)\b.+\b(code|file|component|function|class|route|api|"
        r"test|error|bug|repo|workspace)\b"
    ),
]
_CONVERSATIONAL_PATTERNS = [
    (
        r"^(thanks|thank you|thx|ty|ok|okay|cool|nice|great|awesome|perfect|"
        r"sounds good|got it|yep|yeah|yes|no worries)[.!\s]*$"
    ),
    (
        r"\b(love (this|these|it)|looks good|nice work|good stuff|cool stuff|"
        r"awesome work|great job|well done)\b"
    ),
    (
        r"^(woah|wow|haha|lol|lmao|sweet|sick|dope)\b.*"
        r"\b(cool|nice|love|awesome|great|stuff|changes)\b"
    ),
]
_FILE_REF_RE = re.compile(
    (
        r"(`[^`]+\.[A-Za-z0-9]{1,8}`|"
        r"\b[\w./-]+\.(py|ts|tsx|js|jsx|css|md|json|yaml|yml|toml|sql|sh)\b|"
        r"\b(orchestrator|ui|tests|docs|src)/)"
    ),
    re.IGNORECASE,
)


def classify_agent_intent(message: str) -> AgentIntent:
    """Classify the latest coding-agent user turn.

    The classifier is intentionally conservative about forcing tools: only clear
    workspace requests become actionable/read-only. Praise, acknowledgements,
    and meta feedback stay conversational even in a coding workspace.
    """
    text = " ".join((message or "").strip().lower().split())
    if not text:
        return AgentIntent.AMBIGUOUS

    if any(re.search(pattern, text) for pattern in _CONVERSATIONAL_PATTERNS):
        if not any(re.search(pattern, text) for pattern in _ACTIONABLE_PATTERNS):
            return AgentIntent.CONVERSATIONAL

    if _FILE_REF_RE.search(message or ""):
        if any(re.search(pattern, text) for pattern in _ACTIONABLE_PATTERNS):
            return AgentIntent.ACTIONABLE_WORKSPACE
        return AgentIntent.READ_ONLY_WORKSPACE

    if any(re.search(pattern, text) for pattern in _ACTIONABLE_PATTERNS):
        return AgentIntent.ACTIONABLE_WORKSPACE

    if any(re.search(pattern, text) for pattern in _READ_ONLY_PATTERNS):
        return AgentIntent.READ_ONLY_WORKSPACE

    return AgentIntent.AMBIGUOUS


def render_intent_guidance(intent: AgentIntent) -> str:
    """Render concise tool guidance for working memory."""
    if intent == AgentIntent.CONVERSATIONAL:
        return (
            "Conversational feedback only. No new implementation request. "
            "Do not call tools unless the latest user message asks for inspection or changes."
        )
    if intent == AgentIntent.ACTIONABLE_WORKSPACE:
        return (
            "Actionable workspace request. Inspect before editing, then implement "
            "and verify proportionally."
        )
    if intent == AgentIntent.READ_ONLY_WORKSPACE:
        return (
            "Read-only workspace request. Inspect or analyze as needed; do not edit "
            "unless the user asks for changes."
        )
    return (
        "Ambiguous coding turn. Tools are available, but call them only if needed "
        "to answer or continue safely."
    )
