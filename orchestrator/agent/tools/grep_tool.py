"""Grep tool for content search.

Searches file contents with regex. Uses ripgrep if available, falls back to Python re.
Auto-approves (read-only, idempotent).
"""

import asyncio
from collections import Counter
import re
import shutil
import time
from pathlib import Path
from typing import Any, List, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema
from .path_utils import (
    DEFAULT_SKIP_DIRS,
    GitIgnoreMatcher,
    display_workspace_path,
    resolve_workspace_path,
)

logger = get_logger(__name__)


class GrepTool:
    """Search file contents with regex patterns.

    Attributes:
        name: "grep"
        is_idempotent: True
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize grep tool.

        Args:
            working_dir: Base directory for resolving relative paths.
        """
        self._working_dir = Path(working_dir).resolve()
        self._rg_path = shutil.which("rg")

    @property
    def name(self) -> str:
        """Tool name."""
        return "grep"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="grep",
            description=(
                "Search file contents using regex patterns. "
                "Returns matching lines with file paths and line numbers. "
                "Uses ripgrep if available for speed, falls back to Python regex."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory or file to search in "
                            "(default: working directory)"
                        ),
                    },
                    "glob": {
                        "type": "string",
                        "description": 'File pattern filter (e.g., "*.py", "*.ts")',
                    },
                    "context": {
                        "type": "integer",
                        "description": (
                            "Number of context lines before and "
                            "after each match (default: 1, hard max 2)"
                        ),
                        "default": 1,
                        "maximum": 2,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return (default: 40, hard max 75)",
                        "default": 40,
                        "maximum": 75,
                    },
                },
                "required": ["pattern"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, search_path: Optional[str]) -> Path:
        """Resolve path relative to working directory."""
        return resolve_workspace_path(self._working_dir, search_path)

    def _is_binary(self, path: Path) -> bool:
        """Quick binary detection."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(4096)
                return b"\x00" in chunk
        except Exception:
            return True

    async def _search_with_rg(
        self,
        pattern: str,
        search_path: Path,
        glob_filter: Optional[str],
        context: int,
        max_results: int,
    ) -> str:
        """Search using ripgrep subprocess."""
        cmd = [
            self._rg_path,
            "--no-heading",
            "--line-number",
            "--color=never",
        ]

        if context > 0:
            cmd.append(f"--context={context}")

        if glob_filter:
            cmd.extend(["--glob", glob_filter])

        gitignore = self._working_dir / ".gitignore"
        if gitignore.exists():
            cmd.extend(["--ignore-file", str(gitignore)])

        for skip_dir in DEFAULT_SKIP_DIRS:
            cmd.extend(["--glob", f"!**/{skip_dir}/**"])

        cmd.extend([pattern, str(search_path)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        return stdout.decode("utf-8", errors="replace")

    def _iter_result_files(
        self,
        search_path: Path,
        glob_filter: Optional[str],
        ignore_matcher: GitIgnoreMatcher,
    ):
        """Yield searchable files under a path."""
        if search_path.is_file():
            if not ignore_matcher.is_ignored(search_path):
                yield search_path
            return

        def walk(directory: Path):
            try:
                for entry in sorted(directory.iterdir()):
                    if ignore_matcher.is_ignored(entry):
                        continue
                    if entry.is_dir():
                        yield from walk(entry)
                    elif entry.is_file():
                        if glob_filter and not entry.match(glob_filter):
                            continue
                        yield entry
            except PermissionError:
                return

        yield from walk(search_path)

    def _search_with_python(
        self,
        pattern: str,
        search_path: Path,
        glob_filter: Optional[str],
        context: int,
        max_results: int,
        ignore_matcher: GitIgnoreMatcher,
    ) -> tuple[str, int, Counter[str], bool]:
        """Search using Python re module."""
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex: {e}", 0, Counter(), False

        results: List[str] = []
        match_count = 0
        file_counts: Counter[str] = Counter()
        truncated = False
        files = self._iter_result_files(search_path, glob_filter, ignore_matcher)

        for file_path in files:
            if self._is_binary(file_path):
                continue

            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            rel_path = display_workspace_path(self._working_dir, file_path)

            for i, line in enumerate(lines):
                if match_count >= max_results:
                    truncated = True
                    break

                if regex.search(line):
                    match_count += 1
                    file_counts[rel_path] += 1

                    if context > 0:
                        start = max(0, i - context)
                        end = min(len(lines), i + context + 1)
                        for j in range(start, end):
                            marker = ">" if j == i else " "
                            results.append(f"{rel_path}:{j + 1}:{marker} {lines[j]}")
                        results.append("--")
                    else:
                        results.append(f"{rel_path}:{i + 1}: {line}")
            if truncated:
                break

        return "\n".join(results), match_count, file_counts, truncated

    def _normalize_rg_output(
        self,
        output: str,
        max_results: int,
    ) -> tuple[str, int, Counter[str], bool]:
        """Enforce a global match cap over ripgrep line output."""
        kept: list[str] = []
        match_count = 0
        file_counts: Counter[str] = Counter()
        truncated = False

        for line in output.splitlines():
            is_separator = line == "--"
            is_context = bool(re.match(r"^(.+?)-\d+-", line))
            match = re.match(r"^(.+?):\d+:", line)
            if match and not is_context:
                if match_count >= max_results:
                    truncated = True
                    break
                match_count += 1
                file_path = match.group(1)
                try:
                    file_path = display_workspace_path(
                        self._working_dir,
                        Path(file_path).resolve(),
                    )
                except Exception:
                    pass
                file_counts[file_path] += 1
            kept.append(line)
            if is_separator and match_count >= max_results:
                truncated = True
                break
        return "\n".join(kept), match_count, file_counts, truncated

    def _summary(
        self,
        pattern: str,
        returned_count: int,
        file_counts: Counter[str],
        truncated: bool,
    ) -> str:
        if returned_count == 0:
            return f"No matches for pattern '{pattern[:40]}'"
        top_files = ", ".join(f"{path} ({count})" for path, count in file_counts.most_common(5))
        summary = (
            f"Found {returned_count}{'+' if truncated else ''} matches for "
            f"'{pattern[:40]}' across {len(file_counts)} files"
        )
        if truncated:
            summary += f"; returned first {returned_count} matches"
        if top_files:
            summary += f"; top files: {top_files}"
        return summary

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        context: int = 1,
        max_results: int = 40,
        **kwargs: Any,
    ) -> ToolResult:
        """Search for pattern in files.

        Args:
            pattern: Regex pattern to search for.
            path: Directory or file to search.
            glob: File pattern filter.
            context: Context lines around matches.
            max_results: Maximum matches.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with matching lines.
        """
        start_time = time.perf_counter()

        try:
            search_path = self._resolve_path(path)

            if not search_path.exists():
                return ToolResult(
                    success=False,
                    result_summary=f"Path not found: {path or '.'}",
                    error_message=f"Path does not exist: {search_path}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            context = min(max(0, context), 2)
            max_results = min(max(1, max_results), 75)
            ignore_matcher = GitIgnoreMatcher.from_workspace(self._working_dir)

            # Try ripgrep first, fall back to Python
            if self._rg_path:
                try:
                    output = await self._search_with_rg(
                        pattern, search_path, glob, context, max_results
                    )
                    output, match_count, file_counts, truncated = self._normalize_rg_output(
                        output,
                        max_results,
                    )
                except Exception as e:
                    logger.debug("ripgrep failed, falling back to Python", extra={"error": str(e)})
                    output, match_count, file_counts, truncated = self._search_with_python(
                        pattern, search_path, glob, context, max_results, ignore_matcher
                    )
            else:
                output, match_count, file_counts, truncated = self._search_with_python(
                    pattern, search_path, glob, context, max_results, ignore_matcher
                )

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            if match_count == 0:
                return ToolResult(
                    success=True,
                    result_summary=f"No matches for pattern '{pattern[:40]}'",
                    result_data="No matches found.",
                    duration_ms=duration_ms,
                    metadata={"count": 0, "returned": 0, "truncated": False},
                )

            return ToolResult(
                success=True,
                result_summary=self._summary(pattern, match_count, file_counts, truncated),
                result_data=output,
                duration_ms=duration_ms,
                metadata={
                    "count": match_count,
                    "returned": match_count,
                    "truncated": truncated,
                    "top_files": dict(file_counts.most_common(10)),
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
            logger.error("grep failed", extra={"pattern": pattern, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Grep failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        """Check if working directory is accessible."""
        return self._working_dir.is_dir()

    async def close(self) -> None:
        """No resources to clean up."""
        pass
