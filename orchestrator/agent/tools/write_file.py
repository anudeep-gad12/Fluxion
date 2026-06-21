"""Write file tool for filesystem access.

Creates or overwrites files. Requires approval (non-idempotent).
"""

import difflib
import time
from pathlib import Path
from typing import Any

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema
from .path_utils import atomic_write_text, display_workspace_path, resolve_workspace_path

logger = get_logger(__name__)


class WriteFileTool:
    """Write content to a file, creating parent directories as needed.

    Attributes:
        name: "write_file"
        is_idempotent: False
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize write file tool.

        Args:
            working_dir: Base directory for resolving relative paths.
        """
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        """Tool name."""
        return "write_file"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="write_file",
            description=(
                "Create a new file, or deliberately overwrite a whole existing file. "
                "Do NOT use this for normal edits to existing files; use edit_file instead. "
                "Set allow_overwrite=true only when a full-file rewrite is intentional. "
                "Creates parent directories as needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to the file (absolute or relative to working directory)"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                    "allow_overwrite": {
                        "type": "boolean",
                        "description": (
                            "Required as true to overwrite an existing file. "
                            "Leave false/omitted when creating new files."
                        ),
                    },
                },
                "required": ["file_path", "content"],
            },
            is_idempotent=False,
            permission_level="confirm",
        )

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve path relative to working directory.

        Raises:
            ValueError: If path escapes working directory.
        """
        return resolve_workspace_path(self._working_dir, file_path)

    async def execute(
        self,
        file_path: str,
        content: str,
        allow_overwrite: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Write content to file.

        Args:
            file_path: Path to file.
            content: Content to write.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with write confirmation.
        """
        start_time = time.perf_counter()

        try:
            path = self._resolve_path(file_path)
            existed = path.exists()

            if existed and not allow_overwrite:
                return ToolResult(
                    success=False,
                    result_summary=f"Refused to overwrite existing file: {file_path}",
                    error_message=(
                        "write_file is for creating files. Use edit_file for targeted "
                        "changes to existing files, or pass allow_overwrite=true only "
                        "for an intentional full-file rewrite."
                    ),
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Read existing content for diff generation
            old_content = ""
            expected_bytes = None
            if existed:
                try:
                    expected_bytes = path.read_bytes()
                    old_content = expected_bytes.decode("utf-8")
                except Exception:
                    old_content = ""

            # Create parent directories
            atomic_write_text(path, content, expected_bytes=expected_bytes)
            byte_count = len(content.encode("utf-8"))

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            display_path = display_workspace_path(self._working_dir, path)
            action = "Overwrote" if existed else "Created"

            # Generate unified diff for creates and overwrites so browser UI
            # can show exactly what was written.
            if old_content != content:
                diff_lines = difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"a/{display_path}",
                    tofile=f"b/{display_path}",
                    n=3,
                )
                result_data = "".join(diff_lines) or (
                    f"{action} {display_path} ({byte_count} bytes)"
                )
            else:
                result_data = f"{action} {display_path} ({byte_count} bytes written)"

            return ToolResult(
                success=True,
                result_summary=f"{action} {display_path} ({byte_count} bytes)",
                result_data=result_data,
                duration_ms=duration_ms,
                metadata={"bytes": byte_count, "created": not existed},
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                result_summary=f"Path error: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            logger.error("write_file failed", extra={"file_path": file_path, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Write failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        """Check if working directory is writable."""
        try:
            test_file = self._working_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """No resources to clean up."""
        pass
