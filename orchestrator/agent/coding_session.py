"""Persistent coding-session models and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable, Optional


_MAX_TEXT = 4_000
_MAX_EXCERPT = 1_500
_MAX_LIST_ITEM = 1_500
_MAX_SUMMARY = 8_000


def _trim_text(value: Any, max_len: int = _MAX_TEXT) -> str:
    """Normalize arbitrary values into capped strings."""
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _dedupe_ordered(items: Iterable[Any], max_len: int = _MAX_LIST_ITEM) -> list[str]:
    """Keep ordered unique non-empty strings."""
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _trim_text(item, max_len=max_len)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped


def _dedupe_tail(items: Iterable[Any], limit: int, max_len: int = _MAX_LIST_ITEM) -> list[str]:
    """Keep the most recent unique non-empty strings."""
    normalized = [_trim_text(item, max_len=max_len) for item in items]
    seen: set[str] = set()
    deduped: list[str] = []
    for item in reversed([item for item in normalized if item]):
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    deduped.reverse()
    return deduped[-limit:]


def _json_clone(value: Any) -> Any:
    """Return a JSON-safe deep clone."""
    return json.loads(json.dumps(value, ensure_ascii=False))


@dataclass
class CodingFileSpan:
    """Concrete line-span evidence stored for a file."""

    line_start: Optional[int] = None
    line_end: Optional[int] = None
    excerpt: str = ""
    reason: str = "read"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingFileSpan":
        """Deserialize a stored file span."""
        return cls(
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            excerpt=_trim_text(data.get("excerpt"), max_len=_MAX_EXCERPT),
            reason=_trim_text(data.get("reason")) or "read",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the span for JSON storage."""
        return {
            "line_start": self.line_start,
            "line_end": self.line_end,
            "excerpt": _trim_text(self.excerpt, max_len=_MAX_EXCERPT),
            "reason": _trim_text(self.reason) or "read",
        }

    def covers(self, line_start: Optional[int], line_end: Optional[int]) -> bool:
        """Return whether this span covers the requested range."""
        if line_start is None:
            return True
        if self.line_start is None:
            return False
        if line_start < self.line_start:
            return False
        if line_end is None:
            return self.line_end is None or line_start <= self.line_end
        if self.line_end is None:
            return False
        return line_end <= self.line_end


@dataclass
class CodingFileState:
    """Stored evidence for a workspace file across coding turns."""

    path: str
    summary: str = ""
    content_hash: Optional[str] = None
    source: str = "read_file"
    captured_at: Optional[str] = None
    spans: list[CodingFileSpan] = field(default_factory=list)
    last_read_run_id: Optional[str] = None
    last_modified_run_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingFileState":
        """Deserialize from persisted JSON."""
        spans_data = data.get("spans") or []
        spans = [
            CodingFileSpan.from_dict(span)
            for span in spans_data
            if isinstance(span, dict)
        ]
        legacy_excerpt = _trim_text(data.get("excerpt"), max_len=_MAX_EXCERPT)
        if legacy_excerpt:
            spans.append(
                CodingFileSpan(
                    line_start=data.get("line_start"),
                    line_end=data.get("line_end"),
                    excerpt=legacy_excerpt,
                    reason=_trim_text(data.get("reason")) or "read",
                )
            )
        state = cls(
            path=_trim_text(data.get("path")),
            summary=_trim_text(data.get("summary"), max_len=_MAX_EXCERPT),
            content_hash=_trim_text(data.get("content_hash")) or None,
            source=_trim_text(data.get("source")) or "read_file",
            captured_at=_trim_text(data.get("captured_at")) or None,
            spans=spans,
            last_read_run_id=_trim_text(data.get("last_read_run_id")) or None,
            last_modified_run_id=_trim_text(data.get("last_modified_run_id")) or None,
        )
        state.normalize()
        return state

    def normalize(self) -> None:
        """Normalize persisted file evidence."""
        self.path = _trim_text(self.path)
        self.summary = _trim_text(self.summary, max_len=_MAX_EXCERPT)
        self.content_hash = _trim_text(self.content_hash) or None
        self.source = _trim_text(self.source) or "read_file"
        self.captured_at = _trim_text(self.captured_at) or None
        self.last_read_run_id = _trim_text(self.last_read_run_id) or None
        self.last_modified_run_id = _trim_text(self.last_modified_run_id) or None
        normalized_spans: list[CodingFileSpan] = []
        seen: set[tuple[Optional[int], Optional[int], str, str]] = set()
        for span in self.spans:
            normalized = CodingFileSpan.from_dict(span.to_dict())
            key = (
                normalized.line_start,
                normalized.line_end,
                normalized.excerpt,
                normalized.reason,
            )
            if key in seen:
                continue
            seen.add(key)
            normalized_spans.append(normalized)
        self.spans = normalized_spans

    def add_span(
        self,
        *,
        line_start: Optional[int],
        line_end: Optional[int],
        excerpt: Optional[str],
        reason: str,
    ) -> None:
        """Append a concrete evidence span."""
        clean_excerpt = _trim_text(excerpt, max_len=_MAX_EXCERPT)
        if not clean_excerpt and line_start is None and line_end is None:
            return
        self.spans.append(
            CodingFileSpan(
                line_start=line_start,
                line_end=line_end,
                excerpt=clean_excerpt,
                reason=_trim_text(reason) or "read",
            )
        )
        self.normalize()

    def covers_range(self, line_start: Optional[int], line_end: Optional[int]) -> bool:
        """Return whether any stored span covers the requested range."""
        if not self.spans:
            return False
        return any(span.covers(line_start, line_end) for span in self.spans)

    def latest_excerpt(self) -> Optional[str]:
        """Return the newest non-empty excerpt if present."""
        for span in reversed(self.spans):
            if span.excerpt:
                return span.excerpt
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persisted JSON storage."""
        self.normalize()
        return {
            "path": _trim_text(self.path),
            "summary": _trim_text(self.summary, max_len=_MAX_EXCERPT),
            "content_hash": _trim_text(self.content_hash) or None,
            "source": _trim_text(self.source) or "read_file",
            "captured_at": _trim_text(self.captured_at) or None,
            "spans": [span.to_dict() for span in self.spans],
            "last_read_run_id": _trim_text(self.last_read_run_id) or None,
            "last_modified_run_id": _trim_text(self.last_modified_run_id) or None,
        }


@dataclass
class CodingSessionEntry:
    """Normalized replayable coding-session history entry."""

    conversation_id: str
    seq: int
    run_id: str
    step_number: Optional[int]
    entry_type: str
    role: str
    content_json: dict[str, Any]
    token_estimate: int = 0
    created_at: Optional[str] = None
    compacted_at: Optional[str] = None
    entry_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingSessionEntry":
        """Deserialize a stored entry row."""
        raw_content = data.get("content_json")
        if isinstance(raw_content, str):
            try:
                raw_content = json.loads(raw_content)
            except json.JSONDecodeError:
                raw_content = {"content": raw_content}
        if not isinstance(raw_content, dict):
            raw_content = {"content": raw_content}
        return cls(
            conversation_id=_trim_text(data.get("conversation_id")),
            seq=int(data.get("seq") or 0),
            run_id=_trim_text(data.get("run_id")),
            step_number=data.get("step_number"),
            entry_type=_trim_text(data.get("entry_type")),
            role=_trim_text(data.get("role")),
            content_json=_json_clone(raw_content),
            token_estimate=int(data.get("token_estimate") or 0),
            created_at=_trim_text(data.get("created_at")) or None,
            compacted_at=_trim_text(data.get("compacted_at")) or None,
            entry_id=_trim_text(data.get("id")) or _trim_text(data.get("entry_id")) or None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize a session entry."""
        return {
            "id": self.entry_id,
            "conversation_id": _trim_text(self.conversation_id),
            "seq": int(self.seq),
            "run_id": _trim_text(self.run_id),
            "step_number": self.step_number,
            "entry_type": _trim_text(self.entry_type),
            "role": _trim_text(self.role),
            "content_json": _json_clone(self.content_json),
            "token_estimate": int(self.token_estimate or 0),
            "created_at": _trim_text(self.created_at) or None,
            "compacted_at": _trim_text(self.compacted_at) or None,
        }


@dataclass
class CodingSessionState:
    """Durable coding session state restored across turns."""

    objective: str = ""
    accepted_plan: list[str] = field(default_factory=list)
    prior_outcomes: list[str] = field(default_factory=list)
    read_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    file_evidence: dict[str, CodingFileState] = field(default_factory=dict)
    validation_results: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    recent_commands: list[str] = field(default_factory=list)
    current_hypothesis: Optional[str] = None
    checkpoint_summary: str = ""
    checkpoint_through_seq: int = 0
    raw_tail_start_seq: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingSessionState":
        """Deserialize persisted JSON into a normalized session state."""
        accepted_plan = data.get("accepted_plan") or []
        if isinstance(accepted_plan, str):
            accepted_plan = [accepted_plan]

        read_files = list(data.get("read_files") or [])
        modified_files = list(data.get("modified_files") or [])

        legacy_files_inspected = data.get("files_inspected") or {}
        legacy_files_changed = data.get("files_changed") or {}
        if not read_files and isinstance(legacy_files_inspected, dict):
            read_files = list(legacy_files_inspected.keys())
        if not modified_files and isinstance(legacy_files_changed, dict):
            modified_files = list(legacy_files_changed.keys())

        state = cls(
            objective=_trim_text(data.get("objective")),
            accepted_plan=list(accepted_plan),
            prior_outcomes=list(data.get("prior_outcomes") or []),
            read_files=read_files,
            modified_files=modified_files,
            file_evidence={
                _trim_text(path): CodingFileState.from_dict(file_state)
                for path, file_state in (data.get("file_evidence") or {}).items()
                if isinstance(file_state, dict) and _trim_text(path)
            },
            validation_results=list(data.get("validation_results") or []),
            open_tasks=list(
                data.get("open_tasks")
                or data.get("unresolved_tasks")
                or []
            ),
            recent_commands=list(data.get("recent_commands") or []),
            current_hypothesis=_trim_text(data.get("current_hypothesis")) or None,
            checkpoint_summary=_trim_text(
                data.get("checkpoint_summary"),
                max_len=_MAX_SUMMARY,
            ),
            checkpoint_through_seq=int(data.get("checkpoint_through_seq") or 0),
            raw_tail_start_seq=int(data.get("raw_tail_start_seq") or 1),
        )
        state.normalize()
        return state

    def normalize(self) -> None:
        """Normalize persisted session state."""
        self.objective = _trim_text(self.objective)
        self.accepted_plan = _dedupe_ordered(self.accepted_plan)
        self.prior_outcomes = _dedupe_ordered(self.prior_outcomes)
        self.read_files = _dedupe_ordered(self.read_files, max_len=_MAX_TEXT)
        self.modified_files = _dedupe_ordered(self.modified_files, max_len=_MAX_TEXT)
        self.validation_results = _dedupe_ordered(self.validation_results)
        self.open_tasks = _dedupe_ordered(self.open_tasks)
        self.recent_commands = _dedupe_ordered(self.recent_commands)
        self.current_hypothesis = _trim_text(self.current_hypothesis) or None
        self.checkpoint_summary = _trim_text(
            self.checkpoint_summary,
            max_len=_MAX_SUMMARY,
        )
        self.checkpoint_through_seq = max(0, int(self.checkpoint_through_seq or 0))
        self.raw_tail_start_seq = max(1, int(self.raw_tail_start_seq or 1))
        self.file_evidence = {
            path: CodingFileState.from_dict(file_state.to_dict())
            for path, file_state in self.file_evidence.items()
            if _trim_text(path)
        }

    def note_read_file(self, path: str) -> None:
        """Track a cumulative read file."""
        clean = _trim_text(path)
        if not clean:
            return
        if clean in self.read_files:
            self.read_files.remove(clean)
        self.read_files.append(clean)

    def note_modified_file(self, path: str) -> None:
        """Track a cumulative modified file."""
        clean = _trim_text(path)
        if not clean:
            return
        if clean in self.modified_files:
            self.modified_files.remove(clean)
        self.modified_files.append(clean)

    def to_dict(self) -> dict[str, Any]:
        """Serialize a normalized session state for database storage."""
        self.normalize()
        return {
            "objective": self.objective,
            "accepted_plan": self.accepted_plan,
            "prior_outcomes": self.prior_outcomes,
            "read_files": self.read_files,
            "modified_files": self.modified_files,
            "file_evidence": {
                path: file_state.to_dict()
                for path, file_state in self.file_evidence.items()
            },
            "validation_results": self.validation_results,
            "open_tasks": self.open_tasks,
            "recent_commands": self.recent_commands,
            "current_hypothesis": self.current_hypothesis,
            "checkpoint_summary": self.checkpoint_summary,
            "checkpoint_through_seq": self.checkpoint_through_seq,
            "raw_tail_start_seq": self.raw_tail_start_seq,
        }


def render_checkpoint_summary(
    session_state: CodingSessionState,
    *,
    stale_file_notes: Optional[dict[str, str]] = None,
    next_actions: Optional[list[str]] = None,
) -> str:
    """Render a compact deterministic checkpoint summary for prompt replay."""
    session_state.normalize()
    sections = ["CODING SESSION CHECKPOINT"]
    if session_state.objective:
        sections.append(f"- Objective: {session_state.objective}")
    if session_state.accepted_plan:
        sections.append(
            "- Accepted plan: "
            + " | ".join(_dedupe_tail(session_state.accepted_plan, 8))
        )
    if session_state.prior_outcomes:
        sections.append(
            "- Progress so far: "
            + " | ".join(_dedupe_tail(session_state.prior_outcomes, 8))
        )
    if session_state.current_hypothesis:
        sections.append(f"- Current subtask: {session_state.current_hypothesis}")
    if session_state.open_tasks:
        sections.append(
            "- Unresolved issues: "
            + " | ".join(_dedupe_tail(session_state.open_tasks, 8))
        )
    if session_state.validation_results:
        sections.append(
            "- Validation status: "
            + " | ".join(_dedupe_tail(session_state.validation_results, 8))
        )
    if session_state.read_files:
        sections.append("- Read files: " + ", ".join(session_state.read_files))
    if session_state.modified_files:
        sections.append("- Modified files: " + ", ".join(session_state.modified_files))
    if stale_file_notes:
        sections.append(
            "- Stale file notes: "
            + " | ".join(
                f"{path}: {_trim_text(reason, max_len=240)}"
                for path, reason in stale_file_notes.items()
            )
        )
    if session_state.recent_commands:
        sections.append(
            "- Recent commands: "
            + " | ".join(_dedupe_tail(session_state.recent_commands, 8))
        )
    if next_actions:
        sections.append(
            "- Next likely actions: "
            + " | ".join(_dedupe_tail(next_actions, 6))
        )
    return _trim_text("\n".join(sections), max_len=_MAX_SUMMARY)
