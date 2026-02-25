"""Grep tool for content search.

Searches file contents with regex. Uses ripgrep if available, falls back to Python re.
Auto-approves (read-only, idempotent).
"""

import asyncio
import re
import shutil
import time
from pathlib import Path
from typing import Any, List, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)

# Directories to always skip
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".env", ".tox", ".mypy_cache"}


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
                            "after each match (default: 0)"
                        ),
                        "default": 0,
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["pattern"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, search_path: Optional[str]) -> Path:
        """Resolve path relative to working directory."""
        if search_path is None:
            return self._working_dir

        path = Path(search_path)
        if not path.is_absolute():
            path = self._working_dir / path
        path = path.resolve()

        if not str(path).startswith(str(self._working_dir)):
            raise ValueError(f"Path '{search_path}' is outside working directory")

        return path

    def _is_binary(self, path: Path) -> bool:
        """Quick binary detection."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(4096)
                return b"\x00" in chunk
        except Exception:
            return True

    def _should_skip_dir(self, name: str) -> bool:
        """Check if directory should be skipped."""
        return name in _SKIP_DIRS

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
            f"--max-count={max_results}",
        ]

        if context > 0:
            cmd.append(f"--context={context}")

        if glob_filter:
            cmd.extend(["--glob", glob_filter])

        # Skip common directories
        for skip_dir in _SKIP_DIRS:
            cmd.extend(["--glob", f"!{skip_dir}"])

        cmd.extend([pattern, str(search_path)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        return stdout.decode("utf-8", errors="replace")

    def _search_with_python(
        self,
        pattern: str,
        search_path: Path,
        glob_filter: Optional[str],
        context: int,
        max_results: int,
    ) -> str:
        """Search using Python re module."""
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex: {e}"

        results: List[str] = []
        match_count = 0

        def walk_files(directory: Path):
            """Walk directory yielding files."""
            try:
                for entry in sorted(directory.iterdir()):
                    if entry.is_dir():
                        if not self._should_skip_dir(entry.name):
                            yield from walk_files(entry)
                    elif entry.is_file():
                        # Apply glob filter
                        if glob_filter and not entry.match(glob_filter):
                            continue
                        yield entry
            except PermissionError:
                pass

        if search_path.is_file():
            files = [search_path]
        else:
            files = walk_files(search_path)

        for file_path in files:
            if match_count >= max_results:
                break

            if self._is_binary(file_path):
                continue

            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            try:
                rel_path = str(file_path.relative_to(self._working_dir))
            except ValueError:
                rel_path = str(file_path)

            for i, line in enumerate(lines):
                if match_count >= max_results:
                    break

                if regex.search(line):
                    match_count += 1

                    if context > 0:
                        start = max(0, i - context)
                        end = min(len(lines), i + context + 1)
                        for j in range(start, end):
                            marker = ">" if j == i else " "
                            results.append(f"{rel_path}:{j + 1}:{marker} {lines[j]}")
                        results.append("--")
                    else:
                        results.append(f"{rel_path}:{i + 1}: {line}")

        return "\n".join(results)

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        context: int = 0,
        max_results: int = 50,
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

            # Try ripgrep first, fall back to Python
            if self._rg_path:
                try:
                    output = await self._search_with_rg(
                        pattern, search_path, glob, context, max_results
                    )
                except Exception as e:
                    logger.debug("ripgrep failed, falling back to Python", extra={"error": str(e)})
                    output = self._search_with_python(
                        pattern, search_path, glob, context, max_results
                    )
            else:
                output = self._search_with_python(
                    pattern, search_path, glob, context, max_results
                )

            # Count matches
            lines = output.strip().split("\n") if output.strip() else []
            match_lines = [ln for ln in lines if ln and ln != "--"]
            match_count = len(match_lines)

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            if match_count == 0:
                return ToolResult(
                    success=True,
                    result_summary=f"No matches for pattern '{pattern[:40]}'",
                    result_data="No matches found.",
                    duration_ms=duration_ms,
                    metadata={"count": 0},
                )

            return ToolResult(
                success=True,
                result_summary=f"Found {match_count} matches for '{pattern[:40]}'",
                result_data=output,
                duration_ms=duration_ms,
                metadata={"count": match_count},
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
