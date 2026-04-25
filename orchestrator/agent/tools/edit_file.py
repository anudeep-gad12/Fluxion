"""Edit file tool for exact string replacement.

Performs precise find-and-replace in files. Requires approval (non-idempotent).
"""

import difflib
import time
from pathlib import Path
from typing import Any

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)


class EditFileTool:
    """Edit files using exact string replacement.

    Uses the Claude Code pattern: old_string must appear exactly once in the file.
    This is the most reliable edit approach — no regex ambiguity.

    Attributes:
        name: "edit_file"
        is_idempotent: False
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize edit file tool.

        Args:
            working_dir: Base directory for resolving relative paths.
        """
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        """Tool name."""
        return "edit_file"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="edit_file",
            description=(
                "Edit a file by replacing an exact string with a new string. "
                "The old_string must appear exactly once in the file. "
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
                        "description": "The exact string to find (must appear exactly once)",
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
        """Resolve path relative to working directory.

        Raises:
            ValueError: If path escapes working directory.
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self._working_dir / path
        path = path.resolve()

        if not str(path).startswith(str(self._working_dir)):
            raise ValueError(f"Path '{file_path}' is outside working directory")

        return path

    def _closest_snippets(self, content: str, old_string: str, limit: int = 3) -> list[str]:
        """Find nearby snippets to help the model recover from failed edits."""
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

    async def execute(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Edit file by exact string replacement.

        Args:
            file_path: Path to file.
            old_string: Exact string to find.
            new_string: Replacement string.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with diff summary.
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

            content = path.read_text(encoding="utf-8")

            # Check occurrences
            count = content.count(old_string)
            try:
                display_path = str(path.relative_to(self._working_dir))
            except ValueError:
                display_path = str(path)

            if count == 0:
                candidates = self._closest_snippets(content, old_string)
                hint = ""
                if candidates:
                    hint = "\n\nClosest candidate snippets:\n" + "\n---\n".join(candidates)
                return ToolResult(
                    success=False,
                    result_summary=f"String not found in {display_path}",
                    error_message=(
                        f"The old_string was not found in {display_path}. "
                        "Make sure the string matches exactly, "
                        "including whitespace and indentation."
                        f"{hint}"
                    ),
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                    metadata={"candidate_snippets": candidates},
                )

            if count > 1:
                return ToolResult(
                    success=False,
                    result_summary=f"String found {count} times in {display_path}",
                    error_message=(
                        f"The old_string appears {count} times in {display_path}. "
                        "Provide more surrounding context to make the match unique."
                    ),
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Perform replacement
            new_content = content.replace(old_string, new_string, 1)
            path.write_text(new_content, encoding="utf-8")

            # Generate diff summary
            old_lines = content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff = difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{display_path}",
                tofile=f"b/{display_path}",
                n=3,
            )
            diff_text = "".join(diff)

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            return ToolResult(
                success=True,
                result_summary=f"Edited {display_path}",
                result_data=diff_text if diff_text else f"Replaced string in {display_path}",
                duration_ms=duration_ms,
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
        """Check if working directory is accessible."""
        return self._working_dir.is_dir()

    async def close(self) -> None:
        """No resources to clean up."""
        pass
