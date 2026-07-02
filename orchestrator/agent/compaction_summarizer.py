"""LLM-written handoff summaries for coding-session compaction.

When a coding session's context window is compacted, the entries being
dropped are summarized by the active conversation model into a structured
handoff (progress, decisions, constraints, next steps) instead of relying
solely on heuristic string slicing. Failures fall back silently to the
heuristic checkpoint — a compaction must never fail a run.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from orchestrator.logging_config import get_logger

if TYPE_CHECKING:
    from orchestrator.agent.coding_session import CodingSessionEntry
    from orchestrator.providers.base import LLMProvider

logger = get_logger(__name__)

COMPACTION_SUMMARY_PROMPT = """\
You are performing a CONTEXT CHECKPOINT COMPACTION for a coding agent.
The transcript below is the earlier part of a coding session that is about
to be dropped from the model's context. Write a handoff summary for another
LLM that will resume the task with only your summary plus the most recent
turns.

Include:
- Current progress and key decisions made (what was tried, what worked,
  what failed and why)
- Important constraints, requirements, or user preferences stated so far
- What remains to be done, as clear next steps
- Critical data needed to continue: exact file paths, function/class names,
  commands, error messages, identifiers

Be concise and structured (markdown headings and bullets). Do not invent
details that are not in the transcript. Do not address the user; the
audience is the resuming model."""

SUMMARY_HANDOFF_PREFIX = (
    "The earlier part of this coding conversation was compacted. "
    "A model produced the handoff summary below from the dropped turns. "
    "Continue from it naturally; do not restart the task."
)

_ENTRY_TEXT_CAP = 1200
_MIN_SUMMARY_CHARS = 40


def render_entries_as_transcript(entries: list["CodingSessionEntry"]) -> str:
    """Render session entries as a plain-text transcript for the summarizer."""
    lines: list[str] = []
    for entry in entries:
        content_json = entry.content_json or {}
        if entry.entry_type == "user":
            text = str(content_json.get("content") or "").strip()
            if text:
                lines.append(f"USER: {text[:_ENTRY_TEXT_CAP]}")
        elif entry.entry_type == "assistant":
            text = str(content_json.get("content") or "").strip()
            if text:
                lines.append(f"ASSISTANT: {text[:_ENTRY_TEXT_CAP]}")
        elif entry.entry_type == "assistant_tool_calls":
            calls = []
            for tool_call in content_json.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function") or {}
                name = str(function.get("name") or "tool")
                arguments = str(function.get("arguments") or "")[:200]
                calls.append(f"{name}({arguments})")
            text = str(content_json.get("content") or "").strip()
            rendered = "; ".join(calls)
            if text:
                rendered = f"{text[:400]} | calls: {rendered}" if rendered else text[:400]
            if rendered:
                lines.append(f"ASSISTANT_TOOL_CALLS: {rendered}")
        elif entry.entry_type == "tool_result":
            name = str(content_json.get("name") or "tool")
            status = "ok" if content_json.get("success", True) else "FAILED"
            text = str(content_json.get("content") or "").strip()
            lines.append(f"TOOL {name} ({status}): {text[:_ENTRY_TEXT_CAP]}")
        elif entry.entry_type == "compaction_summary":
            text = str(content_json.get("content") or "").strip()
            if text:
                lines.append(f"PRIOR_CHECKPOINT: {text[:_ENTRY_TEXT_CAP]}")
    return "\n".join(lines)


def bound_transcript(transcript: str, max_chars: int) -> str:
    """Middle-truncate a transcript to fit the summarizer input budget."""
    if len(transcript) <= max_chars or max_chars <= 0:
        return transcript
    head = int(max_chars * 0.6)
    tail = max_chars - head
    omitted = len(transcript) - max_chars
    return (
        transcript[:head].rstrip()
        + f"\n... [{omitted} chars of transcript omitted] ...\n"
        + transcript[-tail:].lstrip()
    )


async def summarize_for_compaction(
    *,
    provider: "LLMProvider",
    model: str,
    entries: list["CodingSessionEntry"],
    durable_state_text: str = "",
    max_input_chars: int = 120000,
    max_output_tokens: int = 1500,
    timeout_s: float = 45.0,
) -> Optional[str]:
    """Ask the active model for a compaction handoff summary.

    Returns the summary text, or None on any failure — callers must fall
    back to the heuristic checkpoint and never surface this as a run error.
    """
    transcript = render_entries_as_transcript(entries)
    if not transcript.strip():
        return None
    transcript = bound_transcript(transcript, max_input_chars)
    user_content = "TRANSCRIPT TO COMPACT:\n" + transcript
    if durable_state_text.strip():
        user_content += (
            "\n\nDURABLE SESSION STATE (already tracked; use for accuracy):\n"
            + durable_state_text.strip()
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": COMPACTION_SUMMARY_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        response = await asyncio.wait_for(
            provider.complete(
                messages=messages,
                model=model,
                max_tokens=max_output_tokens,
                temperature=0.2,
            ),
            timeout=timeout_s,
        )
    except Exception as error:  # noqa: BLE001 - compaction must never fail a run
        logger.warning(
            "compaction_summarizer_failed",
            extra={"error": str(error), "model": model, "entry_count": len(entries)},
        )
        return None

    summary = (getattr(response, "text", None) or "").strip()
    if len(summary) < _MIN_SUMMARY_CHARS:
        logger.warning(
            "compaction_summarizer_empty",
            extra={"model": model, "summary_chars": len(summary)},
        )
        return None
    return summary


def render_llm_checkpoint_content(
    summary: str,
    *,
    read_files: list[str],
    modified_files: list[str],
) -> str:
    """Wrap an LLM handoff summary in the replayable checkpoint envelope."""
    lines = [
        SUMMARY_HANDOFF_PREFIX,
        "",
        "<summary>",
        summary.strip(),
        "",
        "<read-files>",
        *read_files,
        "</read-files>",
        "<modified-files>",
        *modified_files,
        "</modified-files>",
        "</summary>",
    ]
    return "\n".join(lines)
