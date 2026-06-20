"""Glob tool for file pattern matching.

Finds files matching glob patterns. Auto-approves (read-only, idempotent).
"""

import time
import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, List, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema
from .path_utils import GitIgnoreMatcher, display_workspace_path, resolve_workspace_path

logger = get_logger(__name__)


class GlobTool:
    """Find files matching glob patterns.

    Attributes:
        name: "glob"
        is_idempotent: True
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize glob tool.

        Args:
            working_dir: Base directory for resolving relative paths.
        """
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        """Tool name."""
        return "glob"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="glob",
            description=(
                "Find files matching a glob pattern. "
                "Returns file paths sorted by modification time (most recent first). "
                "Basename patterns without '/' search recursively by default. "
                'Examples: "**/*.py", "src/**/*.ts", "*.json", "*Sleep*"'
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": 'Glob pattern to match (e.g., "**/*.py", "src/*.ts")',
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: working directory)",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": (
                            "Whether to search nested directories. Defaults true for "
                            "basename-only patterns and false for patterns with path separators."
                        ),
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": (
                            "Whether matching should be case-sensitive. Defaults false so "
                            "natural lowercase searches can find files like Sleep-Tracking.md."
                        ),
                    },
                },
                "required": ["pattern"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, dir_path: Optional[str]) -> Path:
        """Resolve path relative to working directory."""
        return resolve_workspace_path(self._working_dir, dir_path)

    def _should_recurse(self, pattern: str, recursive: Optional[bool]) -> bool:
        if recursive is not None:
            return bool(recursive)
        normalized = pattern.replace("\\", "/")
        return "/" not in normalized and "**" not in normalized

    def _case_insensitive_matches(
        self,
        search_dir: Path,
        effective_pattern: str,
    ) -> Iterable[Path]:
        """Yield files matching a glob pattern without case sensitivity."""
        normalized_pattern = effective_pattern.replace("\\", "/")
        pattern_lower = normalized_pattern.lower()
        root_pattern = pattern_lower[3:] if pattern_lower.startswith("**/") else None
        for candidate in search_dir.rglob("*"):
            if not candidate.is_file():
                continue
            rel_path = candidate.relative_to(search_dir).as_posix().lower()
            rel_posix = PurePosixPath(rel_path)
            if rel_posix.match(pattern_lower):
                yield candidate
            elif root_pattern and fnmatch.fnmatchcase(rel_path, root_pattern):
                yield candidate

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        recursive: Optional[bool] = None,
        case_sensitive: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Find files matching glob pattern.

        Args:
            pattern: Glob pattern to match.
            path: Directory to search in.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with matching file paths.
        """
        start_time = time.perf_counter()
        max_results = 200
        scan_cap = 10000

        try:
            search_dir = self._resolve_path(path)
            ignore_matcher = GitIgnoreMatcher.from_workspace(self._working_dir)

            if not search_dir.exists() or not search_dir.is_dir():
                return ToolResult(
                    success=False,
                    result_summary=f"Directory not found: {path or '.'}",
                    error_message=f"Directory does not exist: {search_dir}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Collect matches
            matches: List[Path] = []
            effective_pattern = pattern
            recursive_search = self._should_recurse(pattern, recursive)
            if recursive_search and not pattern.startswith("**/"):
                effective_pattern = f"**/{pattern}"

            total_seen = 0
            scan_truncated = False
            candidates: Iterable[Path]
            if case_sensitive:
                candidates = search_dir.glob(effective_pattern)
            else:
                candidates = self._case_insensitive_matches(search_dir, effective_pattern)

            for match in candidates:
                if ignore_matcher.is_ignored(match):
                    continue
                if match.is_file():
                    total_seen += 1
                    matches.append(match)
                    if total_seen >= scan_cap:
                        scan_truncated = True
                        break

            # Sort by mtime (most recent first)
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            truncated = len(matches) > max_results
            matches = matches[:max_results]

            # Format relative paths
            result_lines = []
            for m in matches:
                rel = display_workspace_path(self._working_dir, m)
                result_lines.append(rel)

            content = "\n".join(result_lines)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            first_paths = ", ".join(result_lines[:5])
            summary = (
                f"Found {total_seen} files matching '{pattern}' "
                f"({'recursive' if recursive_search else 'shallow'}, "
                f"{'case-sensitive' if case_sensitive else 'case-insensitive'}; "
                f"returned {len(matches)})"
            )
            if truncated:
                summary += f" — truncated at {max_results}"
            if scan_truncated:
                summary += f" — scan capped at {scan_cap}"
            if first_paths:
                summary += f"; first: {first_paths}"
            elif not recursive_search and "/" not in pattern.replace("\\", "/"):
                summary += "; no shallow matches. Use recursive=true or **/pattern for nested files."

            return ToolResult(
                success=True,
                result_summary=summary,
                result_data=content,
                duration_ms=duration_ms,
                metadata={
                    "count": total_seen,
                    "returned": len(matches),
                    "truncated": truncated or scan_truncated,
                    "recursive": recursive_search,
                    "case_sensitive": case_sensitive,
                    "effective_pattern": effective_pattern,
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
            logger.error("glob failed", extra={"pattern": pattern, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Glob failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        """Check if working directory is accessible."""
        return self._working_dir.is_dir()

    async def close(self) -> None:
        """No resources to clean up."""
        pass
