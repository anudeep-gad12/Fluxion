"""Glob tool for file pattern matching.

Finds files matching glob patterns. Auto-approves (read-only, idempotent).
"""

import time
from pathlib import Path
from typing import Any, List, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)

# Directories to always skip
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".env", ".tox", ".mypy_cache"}


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
                'Examples: "**/*.py", "src/**/*.ts", "*.json"'
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
                },
                "required": ["pattern"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, dir_path: Optional[str]) -> Path:
        """Resolve path relative to working directory."""
        if dir_path is None:
            return self._working_dir

        path = Path(dir_path)
        if not path.is_absolute():
            path = self._working_dir / path
        path = path.resolve()

        if not str(path).startswith(str(self._working_dir)):
            raise ValueError(f"Path '{dir_path}' is outside working directory")

        return path

    def _should_skip(self, path: Path) -> bool:
        """Check if any path component is in skip list."""
        return any(part in _SKIP_DIRS for part in path.parts)

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
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
        max_results = 1000

        try:
            search_dir = self._resolve_path(path)

            if not search_dir.exists() or not search_dir.is_dir():
                return ToolResult(
                    success=False,
                    result_summary=f"Directory not found: {path or '.'}",
                    error_message=f"Directory does not exist: {search_dir}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Collect matches
            matches: List[Path] = []
            for match in search_dir.glob(pattern):
                if match.is_file() and not self._should_skip(match):
                    matches.append(match)
                    if len(matches) > max_results:
                        break

            # Sort by mtime (most recent first)
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            truncated = len(matches) > max_results
            matches = matches[:max_results]

            # Format relative paths
            result_lines = []
            for m in matches:
                try:
                    rel = str(m.relative_to(self._working_dir))
                except ValueError:
                    rel = str(m)
                result_lines.append(rel)

            content = "\n".join(result_lines)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            summary = f"Found {len(matches)} files matching '{pattern}'"
            if truncated:
                summary += f" (truncated at {max_results})"

            return ToolResult(
                success=True,
                result_summary=summary,
                result_data=content,
                duration_ms=duration_ms,
                metadata={"count": len(matches), "truncated": truncated},
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
