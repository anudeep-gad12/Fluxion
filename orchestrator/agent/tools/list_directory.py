"""List directory tool for filesystem exploration.

Lists directory contents with tree-style output. Auto-approves (read-only, idempotent).
"""

import time
from pathlib import Path
from typing import Any, List, Set

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)


def _parse_gitignore(gitignore_path: Path) -> Set[str]:
    """Parse .gitignore and return set of ignore patterns."""
    patterns = set()
    if not gitignore_path.exists():
        return patterns
    try:
        for line in gitignore_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.add(line.rstrip("/"))
    except Exception:
        pass
    return patterns


def _should_ignore(path: Path, ignore_patterns: Set[str], base_dir: Path) -> bool:
    """Check if path matches any gitignore pattern."""
    name = path.name
    rel = str(path.relative_to(base_dir))

    # Always ignore these
    if name in (".git", "__pycache__", "node_modules", ".venv", "venv", ".env"):
        return True

    for pattern in ignore_patterns:
        if name == pattern or rel == pattern:
            return True
        # Simple glob matching
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True

    return False


class ListDirectoryTool:
    """List directory contents in tree format.

    Attributes:
        name: "list_directory"
        is_idempotent: True
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize list directory tool.

        Args:
            working_dir: Base directory for resolving relative paths.
        """
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        """Tool name."""
        return "list_directory"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="list_directory",
            description=(
                "List files and directories at a given path. "
                "Returns tree-style output with file sizes. "
                "Respects .gitignore for recursive listings."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: working directory)",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "List recursively (default: false)",
                        "default": False,
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth for recursive listing (default: 3)",
                        "default": 3,
                    },
                },
                "required": [],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, dir_path: str) -> Path:
        """Resolve path relative to working directory."""
        path = Path(dir_path)
        if not path.is_absolute():
            path = self._working_dir / path
        path = path.resolve()

        if not str(path).startswith(str(self._working_dir)):
            raise ValueError(f"Path '{dir_path}' is outside working directory")

        return path

    def _format_size(self, size: int) -> str:
        """Format byte size to human-readable string."""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def _build_tree(
        self,
        dir_path: Path,
        prefix: str,
        depth: int,
        max_depth: int,
        ignore_patterns: Set[str],
        lines: List[str],
        max_entries: int = 500,
        entry_count: List[int] = None,
    ) -> None:
        """Build tree-style directory listing."""
        if entry_count is None:
            entry_count = [0]

        if entry_count[0] >= max_entries:
            return

        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}[permission denied]")
            return

        # Filter ignored entries
        entries = [e for e in entries if not _should_ignore(e, ignore_patterns, self._working_dir)]

        for i, entry in enumerate(entries):
            if entry_count[0] >= max_entries:
                lines.append(f"{prefix}... (truncated at {max_entries} entries)")
                return

            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                entry_count[0] += 1
                if depth < max_depth:
                    self._build_tree(
                        entry, prefix + extension, depth + 1, max_depth,
                        ignore_patterns, lines, max_entries, entry_count,
                    )
            else:
                try:
                    size = self._format_size(entry.stat().st_size)
                except OSError:
                    size = "?"
                lines.append(f"{prefix}{connector}{entry.name} ({size})")
                entry_count[0] += 1

    async def execute(
        self,
        path: str = ".",
        recursive: bool = False,
        max_depth: int = 3,
        **kwargs: Any,
    ) -> ToolResult:
        """List directory contents.

        Args:
            path: Directory path.
            recursive: Whether to list recursively.
            max_depth: Max depth for recursive listing.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with tree-style directory listing.
        """
        start_time = time.perf_counter()

        try:
            dir_path = self._resolve_path(path)

            if not dir_path.exists():
                return ToolResult(
                    success=False,
                    result_summary=f"Directory not found: {path}",
                    error_message=f"Directory does not exist: {dir_path}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            if not dir_path.is_dir():
                return ToolResult(
                    success=False,
                    result_summary=f"Not a directory: {path}",
                    error_message=f"Path is not a directory: {dir_path}",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                )

            # Parse gitignore if recursive
            ignore_patterns: Set[str] = set()
            if recursive:
                gitignore = self._working_dir / ".gitignore"
                ignore_patterns = _parse_gitignore(gitignore)

            try:
                display_path = str(dir_path.relative_to(self._working_dir))
            except ValueError:
                display_path = str(dir_path)
            if display_path == ".":
                display_path = dir_path.name

            lines: List[str] = [f"{display_path}/"]
            effective_depth = max_depth if recursive else 1
            entry_count = [0]

            self._build_tree(
                dir_path, "", 0, effective_depth, ignore_patterns,
                lines, max_entries=500, entry_count=entry_count,
            )

            content = "\n".join(lines)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            return ToolResult(
                success=True,
                result_summary=f"Listed {entry_count[0]} entries in {display_path}/",
                result_data=content,
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
            logger.error("list_directory failed", extra={"path": path, "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"List failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        """Check if working directory is accessible."""
        return self._working_dir.is_dir()

    async def close(self) -> None:
        """No resources to clean up."""
        pass
