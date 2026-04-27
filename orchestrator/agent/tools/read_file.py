"""Read file tool for filesystem access.

Reads file contents with line numbers. Auto-approves (read-only, idempotent).
"""

import time
from pathlib import Path
from typing import Any

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)


class ReadFileTool:
    """Read file contents with line numbers.

    Attributes:
        name: "read_file"
        is_idempotent: True
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize read file tool.

        Args:
            working_dir: Base directory for resolving relative paths.
        """
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        """Tool name."""
        return "read_file"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="read_file",
            description=(
                "Read the contents of a file with line numbers. "
                "Reads up to 2000 lines by default — just pass file_path, "
                "do NOT set a small limit. Only use offset/limit to page "
                "through files longer than 2000 lines."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to the file (absolute or relative "
                            "to working directory)"
                        ),
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-based, default: 1)",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum lines to read. Default 250, hard max 400.",
                        "default": 250,
                        "maximum": 400,
                    },
                },
                "required": ["file_path"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve path relative to working directory.

        Args:
            file_path: Absolute or relative path.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path escapes working directory.
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self._working_dir / path
        path = path.resolve()

        # Security: ensure path is within working directory
        if not str(path).startswith(str(self._working_dir)):
            raise ValueError(f"Path '{file_path}' is outside working directory")

        return path

    def _display_path(self, path: Path) -> str:
        """Get a display-friendly relative path."""
        try:
            return str(path.relative_to(self._working_dir))
        except ValueError:
            return str(path)

    def _is_binary(self, path: Path) -> bool:
        """Check if file is binary by looking for null bytes in first 8KB."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
                return b"\x00" in chunk
        except Exception:
            return False

    async def execute(
        self,
        file_path: str,
        offset: int = 1,
        limit: int = 250,
        **kwargs: Any,
    ) -> ToolResult:
        """Read file contents.

        Args:
            file_path: Path to file.
            offset: Starting line number (1-based).
            limit: Max lines to read.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with file contents and line numbers.
        """
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

            if self._is_binary(path):
                return ToolResult(
                    success=False,
                    result_summary=f"Binary file: {file_path}",
                    error_message=f"Cannot read binary file: {path}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Read file with line numbers
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            total_lines = len(all_lines)
            start_idx = max(0, offset - 1)
            limit = min(max(1, limit), 400)
            end_idx = min(total_lines, start_idx + limit)
            selected_lines = all_lines[start_idx:end_idx]

            # Format with line numbers
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start_idx + 1):
                # Truncate very long lines
                if len(line) > 300:
                    line = line[:300] + "...\n"
                numbered_lines.append(f"{i:>6}\t{line.rstrip()}")

            content = "\n".join(numbered_lines)

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            display_path = self._display_path(path)

            summary = f"Read {len(selected_lines)} lines from {display_path} ({total_lines} total)"
            if start_idx > 0 or end_idx < total_lines:
                summary += f" [lines {start_idx + 1}-{end_idx}]"

            return ToolResult(
                success=True,
                result_summary=summary,
                result_data=content,
                duration_ms=duration_ms,
                metadata={"total_lines": total_lines, "lines_read": len(selected_lines)},
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                result_summary=f"Path error: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            logger.error("read_file failed", extra={"file_path": file_path, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Read failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        """Check if working directory is accessible."""
        return self._working_dir.is_dir()

    async def close(self) -> None:
        """No resources to clean up."""
        pass
