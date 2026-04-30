"""Persistent coding-session state for cross-turn coding continuity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


_MAX_TEXT = 500
_MAX_OUTCOMES = 6
_MAX_FILES = 8
_MAX_VALIDATION = 8
_MAX_TASKS = 6
_MAX_EVIDENCE = 8


def _trim_text(value: Any, max_len: int = _MAX_TEXT) -> str:
    """Normalize arbitrary values into capped strings."""
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _dedupe_tail(items: list[Any], limit: int) -> list[str]:
    """Keep the most recent unique non-empty strings."""
    normalized = [_trim_text(item) for item in items if _trim_text(item)]
    seen: set[str] = set()
    deduped: list[str] = []
    for item in reversed(normalized):
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    deduped.reverse()
    return deduped[-limit:]


def _trim_mapping(mapping: dict[Any, Any], limit: int) -> dict[str, str]:
    """Keep the newest mapping entries in insertion order."""
    cleaned = {
        _trim_text(key): _trim_text(value)
        for key, value in mapping.items()
        if _trim_text(key) and _trim_text(value)
    }
    if len(cleaned) <= limit:
        return cleaned
    return dict(list(cleaned.items())[-limit:])


@dataclass
class CodingFileState:
    """Stored evidence for a workspace file across coding turns."""

    path: str
    summary: str
    excerpt: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    content_hash: Optional[str] = None
    source: str = "read_file"
    captured_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingFileState":
        """Deserialize from persisted JSON."""
        return cls(
            path=_trim_text(data.get("path")),
            summary=_trim_text(data.get("summary")),
            excerpt=_trim_text(data.get("excerpt")) or None,
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            content_hash=_trim_text(data.get("content_hash")) or None,
            source=_trim_text(data.get("source")) or "read_file",
            captured_at=_trim_text(data.get("captured_at")) or None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persisted JSON storage."""
        return {
            "path": _trim_text(self.path),
            "summary": _trim_text(self.summary),
            "excerpt": _trim_text(self.excerpt) or None,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "content_hash": _trim_text(self.content_hash) or None,
            "source": _trim_text(self.source) or "read_file",
            "captured_at": _trim_text(self.captured_at) or None,
        }


@dataclass
class CodingSessionState:
    """Durable coding session state restored across turns."""

    objective: str = ""
    prior_outcomes: list[str] = field(default_factory=list)
    files_inspected: dict[str, str] = field(default_factory=dict)
    files_changed: dict[str, str] = field(default_factory=dict)
    validation_results: list[str] = field(default_factory=list)
    current_hypothesis: Optional[str] = None
    unresolved_tasks: list[str] = field(default_factory=list)
    recent_raw_evidence: list[str] = field(default_factory=list)
    file_evidence: dict[str, CodingFileState] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingSessionState":
        """Deserialize persisted JSON into a normalized session state."""
        state = cls(
            objective=_trim_text(data.get("objective")),
            prior_outcomes=list(data.get("prior_outcomes") or []),
            files_inspected=dict(data.get("files_inspected") or {}),
            files_changed=dict(data.get("files_changed") or {}),
            validation_results=list(data.get("validation_results") or []),
            current_hypothesis=_trim_text(data.get("current_hypothesis")) or None,
            unresolved_tasks=list(data.get("unresolved_tasks") or []),
            recent_raw_evidence=list(data.get("recent_raw_evidence") or []),
            file_evidence={
                _trim_text(path): CodingFileState.from_dict(file_state)
                for path, file_state in (data.get("file_evidence") or {}).items()
                if isinstance(file_state, dict) and _trim_text(path)
            },
        )
        state.normalize()
        return state

    def normalize(self) -> None:
        """Apply length caps and de-duplicate persisted state."""
        self.objective = _trim_text(self.objective)
        self.prior_outcomes = _dedupe_tail(self.prior_outcomes, _MAX_OUTCOMES)
        self.files_inspected = _trim_mapping(self.files_inspected, _MAX_FILES)
        self.files_changed = _trim_mapping(self.files_changed, _MAX_FILES)
        self.validation_results = _dedupe_tail(
            self.validation_results, _MAX_VALIDATION
        )
        self.current_hypothesis = _trim_text(self.current_hypothesis) or None
        self.unresolved_tasks = _dedupe_tail(self.unresolved_tasks, _MAX_TASKS)
        self.recent_raw_evidence = _dedupe_tail(
            self.recent_raw_evidence, _MAX_EVIDENCE
        )
        if len(self.file_evidence) > _MAX_FILES:
            self.file_evidence = dict(list(self.file_evidence.items())[-_MAX_FILES:])
        self.file_evidence = {
            path: CodingFileState.from_dict(file_state.to_dict())
            for path, file_state in self.file_evidence.items()
            if _trim_text(path)
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize a normalized session state for database storage."""
        self.normalize()
        return {
            "objective": self.objective,
            "prior_outcomes": self.prior_outcomes,
            "files_inspected": self.files_inspected,
            "files_changed": self.files_changed,
            "validation_results": self.validation_results,
            "current_hypothesis": self.current_hypothesis,
            "unresolved_tasks": self.unresolved_tasks,
            "recent_raw_evidence": self.recent_raw_evidence,
            "file_evidence": {
                path: file_state.to_dict()
                for path, file_state in self.file_evidence.items()
            },
        }
