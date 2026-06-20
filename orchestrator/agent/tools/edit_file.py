"""Edit file tool with resilient exact-first string replacement."""

import difflib
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema
from .path_utils import display_workspace_path, resolve_workspace_path

logger = get_logger(__name__)


MatchPredicate = Callable[[list[str], list[str]], bool]


class EditFileTool:
    """Edit files using deterministic exact-first string replacement."""

    _FALLBACK_MULTILINE_DRIFT = 2
    _ANCHOR_SCORE_THRESHOLD = 0.72

    def __init__(self, working_dir: str = ".") -> None:
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="edit_file",
            description=(
                "Edit a file by replacing an exact string with a new string. "
                "The old_string must resolve to one unique location in the file. "
                "Returns a diff-style summary of the change."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to edit",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact string to find",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The string to replace it with",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
            is_idempotent=False,
            permission_level="confirm",
        )

    def _resolve_path(self, file_path: str) -> Path:
        return resolve_workspace_path(self._working_dir, file_path)

    def _read_with_native_newlines(self, path: Path) -> tuple[str, str]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            content = handle.read()
        newline = "\n"
        if "\r\n" in content:
            newline = "\r\n"
        elif "\r" in content:
            newline = "\r"
        return content, newline

    def _normalize_newlines(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _restore_newlines(self, text: str, newline: str) -> str:
        if newline == "\n":
            return text
        return text.replace("\n", newline)

    def _all_indices(self, content: str, target: str) -> list[int]:
        if not target:
            return []
        indices: list[int] = []
        start = 0
        while True:
            idx = content.find(target, start)
            if idx == -1:
                break
            indices.append(idx)
            start = idx + 1
        return indices

    def _line_offsets(self, text: str) -> tuple[list[str], list[int]]:
        lines = text.split("\n")
        offsets: list[int] = []
        position = 0
        for index, line in enumerate(lines):
            offsets.append(position)
            position += len(line)
            if index < len(lines) - 1:
                position += 1
        return lines, offsets

    def _span_from_line_window(
        self,
        offsets: list[int],
        lines: list[str],
        start_line: int,
        line_count: int,
    ) -> tuple[int, int]:
        start = offsets[start_line]
        end_line = start_line + line_count - 1
        end = offsets[end_line] + len(lines[end_line])
        return start, end

    def _normalize_inline_whitespace(self, value: str) -> str:
        return re.sub(r"[ \t]+", " ", value).strip()

    def _line_trimmed_match(self, old_lines: list[str], candidate_lines: list[str]) -> bool:
        return [line.strip() for line in candidate_lines] == [line.strip() for line in old_lines]

    def _whitespace_normalized_match(
        self,
        old_lines: list[str],
        candidate_lines: list[str],
    ) -> bool:
        return [self._normalize_inline_whitespace(line) for line in candidate_lines] == [
            self._normalize_inline_whitespace(line) for line in old_lines
        ]

    def _indentation_flexible_match(
        self,
        old_lines: list[str],
        candidate_lines: list[str],
    ) -> bool:
        return [line.lstrip() for line in candidate_lines] == [line.lstrip() for line in old_lines]

    def _trimmed_boundary_match(
        self,
        old_lines: list[str],
        candidate_lines: list[str],
    ) -> bool:
        def _trim_boundaries(lines: list[str]) -> list[str]:
            start = 0
            end = len(lines)
            while start < end and not lines[start].strip():
                start += 1
            while end > start and not lines[end - 1].strip():
                end -= 1
            return [line.strip() for line in lines[start:end]]

        return _trim_boundaries(candidate_lines) == _trim_boundaries(old_lines)

    def _find_line_window_matches(
        self,
        content: str,
        old_string: str,
        predicate: MatchPredicate,
        *,
        allow_window_drift: int = 0,
    ) -> list[tuple[int, int]]:
        old_lines = old_string.split("\n")
        content_lines, offsets = self._line_offsets(content)
        if not old_lines or not content_lines:
            return []

        min_window = max(1, len(old_lines) - allow_window_drift)
        max_window = min(len(content_lines), len(old_lines) + allow_window_drift)
        matches: list[tuple[int, int]] = []

        for window_size in range(min_window, max_window + 1):
            if window_size > len(content_lines):
                continue
            for start_line in range(0, len(content_lines) - window_size + 1):
                candidate_lines = content_lines[start_line:start_line + window_size]
                if predicate(old_lines, candidate_lines):
                    matches.append(
                        self._span_from_line_window(offsets, content_lines, start_line, window_size)
                    )
        return matches

    def _block_anchor_matches(self, content: str, old_string: str) -> list[tuple[int, int]]:
        old_lines = old_string.split("\n")
        content_lines, offsets = self._line_offsets(content)
        if len(old_lines) < 2 or len(content_lines) < 2:
            return []

        try:
            first_idx = next(idx for idx, line in enumerate(old_lines) if line.strip())
            last_idx = len(old_lines) - 1 - next(
                idx for idx, line in enumerate(reversed(old_lines)) if line.strip()
            )
        except StopIteration:
            return []

        if first_idx >= last_idx:
            return []

        first_anchor = self._normalize_inline_whitespace(old_lines[first_idx])
        last_anchor = self._normalize_inline_whitespace(old_lines[last_idx])
        old_core = "\n".join(
            self._normalize_inline_whitespace(line) for line in old_lines[first_idx:last_idx + 1]
        )

        matches: list[tuple[int, int]] = []
        for start_line, line in enumerate(content_lines):
            if self._normalize_inline_whitespace(line) != first_anchor:
                continue

            min_end = start_line + max(1, last_idx - first_idx)
            max_end = min(
                len(content_lines) - 1,
                start_line + len(old_lines) + self._FALLBACK_MULTILINE_DRIFT,
            )
            for end_line in range(min_end, max_end + 1):
                if self._normalize_inline_whitespace(content_lines[end_line]) != last_anchor:
                    continue
                candidate_lines = content_lines[start_line:end_line + 1]
                candidate_core = "\n".join(
                    self._normalize_inline_whitespace(line) for line in candidate_lines
                )
                score = difflib.SequenceMatcher(None, old_core, candidate_core).ratio()
                if score >= self._ANCHOR_SCORE_THRESHOLD:
                    matches.append(
                        self._span_from_line_window(
                            offsets,
                            content_lines,
                            start_line,
                            end_line - start_line + 1,
                        )
                    )
        return matches

    def _match_exact(self, content: str, old_string: str) -> list[tuple[int, int]]:
        return [(idx, idx + len(old_string)) for idx in self._all_indices(content, old_string)]

    def _closest_snippets(self, content: str, old_string: str, limit: int = 3) -> list[str]:
        if not old_string.strip():
            return []

        old_lines = old_string.splitlines() or [old_string]
        window = max(1, min(len(old_lines), 8))
        lines = content.splitlines()
        candidates: list[tuple[float, str]] = []

        for idx in range(max(1, len(lines) - window + 1)):
            snippet = "\n".join(lines[idx: idx + window])
            score = difflib.SequenceMatcher(None, old_string, snippet).ratio()
            if score > 0.45:
                candidates.append((score, snippet))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [snippet for _, snippet in candidates[:limit]]

    def _snippet_for_span(self, content: str, span: tuple[int, int], padding: int = 120) -> str:
        start, end = span
        excerpt_start = max(0, start - padding)
        excerpt_end = min(len(content), end + padding)
        return content[excerpt_start:excerpt_end].strip("\n")

    def _dedupe_spans(self, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
        seen = set()
        ordered: list[tuple[int, int]] = []
        for span in spans:
            if span in seen:
                continue
            seen.add(span)
            ordered.append(span)
        return ordered

    def _resolve_match(self, content: str, old_string: str) -> tuple[Optional[tuple[int, int]], dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        strategies: list[tuple[str, Callable[[], list[tuple[int, int]]]]] = [
            ("exact", lambda: self._match_exact(content, old_string)),
            (
                "line_trimmed",
                lambda: self._find_line_window_matches(content, old_string, self._line_trimmed_match),
            ),
            (
                "whitespace_normalized",
                lambda: self._find_line_window_matches(
                    content,
                    old_string,
                    self._whitespace_normalized_match,
                ),
            ),
            (
                "indentation_flexible",
                lambda: self._find_line_window_matches(
                    content,
                    old_string,
                    self._indentation_flexible_match,
                ),
            ),
            ("block_anchor", lambda: self._block_anchor_matches(content, old_string)),
            (
                "trimmed_boundary",
                lambda: self._find_line_window_matches(
                    content,
                    old_string,
                    self._trimmed_boundary_match,
                    allow_window_drift=1,
                ),
            ),
        ]

        best_spans: list[tuple[int, int]] = []
        best_matcher: Optional[str] = None
        for matcher_name, matcher in strategies:
            spans = self._dedupe_spans(matcher())
            attempts.append(
                {
                    "matcher": matcher_name,
                    "match_count": len(spans),
                    "matched": len(spans) == 1,
                }
            )
            if spans and not best_spans:
                best_spans = spans
                best_matcher = matcher_name
            if len(spans) == 1:
                return spans[0], {
                    "matcher": matcher_name,
                    "failure_type": None,
                    "match_count": 1,
                    "attempted_matchers": attempts,
                    "candidate_spans": spans,
                }
            if len(spans) > 1:
                return None, {
                    "matcher": matcher_name,
                    "failure_type": "ambiguous",
                    "match_count": len(spans),
                    "attempted_matchers": attempts,
                    "candidate_spans": spans,
                }

        return None, {
            "matcher": best_matcher,
            "failure_type": "not_found",
            "match_count": 0,
            "attempted_matchers": attempts,
            "candidate_spans": best_spans,
        }

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        **kwargs: Any,
    ) -> ToolResult:
        start_time = time.perf_counter()

        try:
            path = self._resolve_path(file_path)

            if not path.exists():
                return ToolResult(
                    success=False,
                    result_summary=f"File not found: {file_path}",
                    error_message=f"File does not exist: {path}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            if not path.is_file():
                return ToolResult(
                    success=False,
                    result_summary=f"Not a file: {file_path}",
                    error_message=f"Path is not a file: {path}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            raw_content, file_newline = self._read_with_native_newlines(path)
            content = self._normalize_newlines(raw_content)
            normalized_old = self._normalize_newlines(old_string)
            normalized_new = self._normalize_newlines(new_string)

            display_path = display_workspace_path(self._working_dir, path)

            if normalized_old == normalized_new:
                return ToolResult(
                    success=False,
                    result_summary=f"No-op edit refused for {display_path}",
                    error_message=(
                        f"The requested edit for {display_path} is a no-op because old_string "
                        "and new_string are identical. Provide an actual change."
                    ),
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                    metadata={
                        "match_failure_type": "no_op",
                        "file_path": display_path,
                    },
                )

            match_span, match_info = self._resolve_match(content, normalized_old)
            if match_span is None:
                candidate_spans = match_info.get("candidate_spans") or []
                snippets = [self._snippet_for_span(content, span) for span in candidate_spans[:3]]
                if not snippets:
                    snippets = self._closest_snippets(content, normalized_old)
                failure_type = match_info.get("failure_type") or "not_found"
                matcher = match_info.get("matcher")
                if failure_type == "ambiguous":
                    summary = f"String matched multiple locations in {display_path}"
                    error_message = (
                        f"The old_string matched {match_info.get('match_count', 0)} locations in {display_path} "
                        f"using matcher '{matcher}'. Provide more surrounding context so the match is unique."
                    )
                else:
                    summary = f"String not found in {display_path}"
                    error_message = (
                        f"The old_string was not found in {display_path}. Exact matching and fallback matchers failed"
                        f" through '{matcher or 'trimmed_boundary'}'. Reread the relevant file region and retry with"
                        " current text instead of repeating stale edit arguments."
                    )
                if snippets:
                    error_message += "\n\nCandidate snippets for recovery:\n" + "\n---\n".join(snippets)
                return ToolResult(
                    success=False,
                    result_summary=summary,
                    error_message=error_message,
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                    metadata={
                        "file_path": display_path,
                        "match_failure_type": failure_type,
                        "matched_by": matcher,
                        "candidate_count": match_info.get("match_count", 0),
                        "candidate_snippets": snippets,
                        "attempted_matchers": match_info.get("attempted_matchers", []),
                    },
                )

            start, end = match_span
            new_content = content[:start] + normalized_new + content[end:]
            final_content = self._restore_newlines(new_content, file_newline)
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(final_content)

            old_lines = raw_content.splitlines(keepends=True)
            new_lines = final_content.splitlines(keepends=True)
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{display_path}",
                tofile=f"b/{display_path}",
                n=3,
            )
            diff_text = "".join(diff)

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolResult(
                success=True,
                result_summary=f"Edited {display_path}",
                result_data={
                    "file_path": display_path,
                    "diff": diff_text or f"Replaced string in {display_path}",
                    "matched_by": match_info.get("matcher", "exact"),
                },
                duration_ms=duration_ms,
                metadata={
                    "file_path": display_path,
                    "matched_by": match_info.get("matcher", "exact"),
                    "attempted_matchers": match_info.get("attempted_matchers", []),
                },
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                result_summary=f"Path error: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            logger.error("edit_file failed", extra={"file_path": file_path, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Edit failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        return self._working_dir.is_dir()

    async def close(self) -> None:
        pass
