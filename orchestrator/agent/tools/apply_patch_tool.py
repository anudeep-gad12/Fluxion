"""Codex-style apply_patch tool for workspace-safe multi-file edits."""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)

PatchKind = Literal["add", "update", "delete"]


@dataclass
class PatchHunk:
    """One update hunk in Codex apply_patch format."""

    lines: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class PatchOperation:
    """Parsed file operation from an apply_patch payload."""

    kind: PatchKind
    path: str
    new_path: Optional[str] = None
    add_lines: list[str] = field(default_factory=list)
    hunks: list[PatchHunk] = field(default_factory=list)
    replace_lines: Optional[list[str]] = None


@dataclass
class FileChange:
    """Computed file content change before writing to disk."""

    old_path: Optional[Path]
    new_path: Optional[Path]
    display_old: str
    display_new: str
    old_content: str
    new_content: str
    action: str


class ApplyPatchParseError(ValueError):
    """Raised for malformed apply_patch input."""


class ApplyPatchTool:
    """Apply Codex `*** Begin Patch` / `*** End Patch` patches atomically."""

    def __init__(self, working_dir: str = ".") -> None:
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "apply_patch"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="apply_patch",
            description=(
                "Apply a Codex-style workspace patch atomically. Prefer this for edits "
                "to existing files and multi-file changes. Format starts with "
                "*** Begin Patch and ends with *** End Patch; supports Add File, "
                "Update File, Delete File, and optional Move to headers. All paths "
                "must stay inside the workspace. Returns changed files and a unified diff."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "string",
                        "description": "Complete Codex-style patch text to apply.",
                    }
                },
                "required": ["patch"],
            },
            is_idempotent=False,
            permission_level="confirm",
        )

    def _resolve_path(self, file_path: str) -> Path:
        clean = str(file_path or "").strip()
        if not clean:
            raise ValueError("Path is empty")
        path = Path(clean)
        if not path.is_absolute():
            path = self._working_dir / path
        resolved = path.resolve()
        try:
            resolved.relative_to(self._working_dir)
        except ValueError as exc:
            raise ValueError(f"Path '{file_path}' is outside working directory") from exc
        return resolved

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._working_dir))
        except ValueError:
            return str(path)

    def _parse(self, patch: str) -> list[PatchOperation]:
        lines = patch.splitlines()
        if not lines or lines[0].strip() != "*** Begin Patch":
            raise ApplyPatchParseError("Patch must start with '*** Begin Patch'")
        if lines[-1].strip() != "*** End Patch":
            raise ApplyPatchParseError("Patch must end with '*** End Patch'")

        operations: list[PatchOperation] = []
        i = 1
        while i < len(lines) - 1:
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if line.startswith("*** Add File: "):
                path = line.removeprefix("*** Add File: ").strip()
                if not path:
                    raise ApplyPatchParseError("Add File header missing path")
                i += 1
                add_lines: list[str] = []
                while i < len(lines) - 1 and not lines[i].startswith("*** "):
                    current = lines[i]
                    if not current.startswith("+"):
                        raise ApplyPatchParseError(
                            f"Add File '{path}' lines must start with '+'"
                        )
                    add_lines.append(current[1:])
                    i += 1
                operations.append(PatchOperation(kind="add", path=path, add_lines=add_lines))
                continue

            if line.startswith("*** Delete File: "):
                path = line.removeprefix("*** Delete File: ").strip()
                if not path:
                    raise ApplyPatchParseError("Delete File header missing path")
                operations.append(PatchOperation(kind="delete", path=path))
                i += 1
                continue

            if line.startswith("*** Update File: "):
                path = line.removeprefix("*** Update File: ").strip()
                if not path:
                    raise ApplyPatchParseError("Update File header missing path")
                op = PatchOperation(kind="update", path=path)
                i += 1
                current_hunk: Optional[PatchHunk] = None
                while (
                    i < len(lines) - 1
                    and not lines[i].startswith("*** Add File: ")
                    and not lines[i].startswith("*** Delete File: ")
                    and not lines[i].startswith("*** Update File: ")
                ):
                    current = lines[i]
                    if current.startswith("*** Move to: "):
                        if op.new_path is not None:
                            raise ApplyPatchParseError(
                                f"Update File '{path}' has multiple Move to headers"
                            )
                        op.new_path = current.removeprefix("*** Move to: ").strip()
                        if not op.new_path:
                            raise ApplyPatchParseError("Move to header missing path")
                        i += 1
                        continue
                    if current == "***" and current_hunk is None and not op.hunks:
                        # Be tolerant of a common model mistake: emitting
                        # `*** Update File: path` followed by `***` and then
                        # the complete replacement file with no +/- prefixes.
                        # Treat this as an atomic full-file replacement instead
                        # of forcing the model into write_file allow_overwrite.
                        i += 1
                        replacement: list[str] = []
                        while (
                            i < len(lines) - 1
                            and not lines[i].startswith("*** Add File: ")
                            and not lines[i].startswith("*** Delete File: ")
                            and not lines[i].startswith("*** Update File: ")
                        ):
                            replacement.append(lines[i])
                            i += 1
                        op.replace_lines = replacement
                        continue
                    if current.startswith("@@"):
                        current_hunk = PatchHunk()
                        op.hunks.append(current_hunk)
                        i += 1
                        continue
                    if current_hunk is None and (
                        current.startswith("--- ") or current.startswith("+++ ")
                    ):
                        # Be tolerant of models that wrap a conventional unified
                        # diff in Codex *** Update File blocks. The file paths are
                        # already carried by the Update File/Move to headers; if we
                        # treat these as +/- body lines, every hunk fails to match.
                        i += 1
                        continue
                    if current.startswith((" ", "-", "+")):
                        if current_hunk is None:
                            current_hunk = PatchHunk()
                            op.hunks.append(current_hunk)
                        current_hunk.lines.append((current[0], current[1:]))
                        i += 1
                        continue
                    if current == "":
                        if current_hunk is None:
                            current_hunk = PatchHunk()
                            op.hunks.append(current_hunk)
                        current_hunk.lines.append((" ", ""))
                        i += 1
                        continue
                    raise ApplyPatchParseError(f"Malformed update line in '{path}': {current[:80]}")
                if not op.hunks and op.new_path is None and op.replace_lines is None:
                    raise ApplyPatchParseError(f"Update File '{path}' has no hunks or move target")
                operations.append(op)
                continue

            raise ApplyPatchParseError(f"Unexpected patch line: {line[:80]}")

        if not operations:
            raise ApplyPatchParseError("Patch contains no file operations")
        return operations

    def _split_keepends(self, text: str) -> list[str]:
        return text.splitlines(keepends=True)

    def _join_patch_lines(self, lines: list[str], trailing_newline: bool) -> str:
        if not lines:
            return ""
        text = "\n".join(lines)
        if trailing_newline:
            text += "\n"
        return text

    def _apply_hunks(self, original: str, hunks: list[PatchHunk], display_path: str) -> str:
        content = original
        cursor = 0
        for hunk in hunks:
            old_lines = [text for prefix, text in hunk.lines if prefix in {" ", "-"}]
            new_lines = [text for prefix, text in hunk.lines if prefix in {" ", "+"}]
            if not old_lines and not new_lines:
                continue
            old_has_trailing = content.endswith("\n")
            old_block = self._join_patch_lines(old_lines, trailing_newline=old_has_trailing)
            new_block = self._join_patch_lines(new_lines, trailing_newline=old_has_trailing)

            search_start = cursor
            idx = content.find(old_block, search_start)
            if idx == -1 and old_block.endswith("\n"):
                idx = content.find(old_block[:-1], search_start)
                if idx != -1:
                    old_block = old_block[:-1]
                    new_block = new_block[:-1] if new_block.endswith("\n") else new_block
            if idx == -1:
                idx = content.find(old_block)
            if idx == -1:
                raise ApplyPatchParseError(
                    f"Patch hunk did not match current contents of {display_path}"
                )
            duplicate_idx = content.find(old_block, idx + 1) if old_block else -1
            if duplicate_idx != -1:
                raise ApplyPatchParseError(
                    f"Patch hunk matched multiple locations in {display_path}; add more context"
                )
            content = content[:idx] + new_block + content[idx + len(old_block):]
            cursor = idx + len(new_block)
        return content

    def _compute_changes(self, operations: list[PatchOperation]) -> list[FileChange]:
        changes: list[FileChange] = []
        touched_sources: set[Path] = set()
        touched_destinations: set[Path] = set()

        for op in operations:
            source = self._resolve_path(op.path)
            dest = self._resolve_path(op.new_path) if op.new_path else source
            if source in touched_sources or dest in touched_destinations:
                raise ApplyPatchParseError(
                    f"Path '{op.path}' is modified more than once in one patch"
                )
            touched_sources.add(source)
            touched_destinations.add(dest)

            if op.kind == "add":
                if source.exists():
                    raise ApplyPatchParseError(f"Add File target already exists: {op.path}")
                new_content = "\n".join(op.add_lines)
                if op.add_lines:
                    new_content += "\n"
                changes.append(
                    FileChange(
                        old_path=None,
                        new_path=source,
                        display_old="/dev/null",
                        display_new=self._display_path(source),
                        old_content="",
                        new_content=new_content,
                        action="add",
                    )
                )
                continue

            if op.kind == "delete":
                if not source.exists():
                    raise ApplyPatchParseError(f"Delete File target does not exist: {op.path}")
                if not source.is_file():
                    raise ApplyPatchParseError(f"Delete File target is not a file: {op.path}")
                old_content = source.read_text(encoding="utf-8")
                changes.append(
                    FileChange(
                        old_path=source,
                        new_path=None,
                        display_old=self._display_path(source),
                        display_new="/dev/null",
                        old_content=old_content,
                        new_content="",
                        action="delete",
                    )
                )
                continue

            if not source.exists():
                raise ApplyPatchParseError(f"Update File target does not exist: {op.path}")
            if not source.is_file():
                raise ApplyPatchParseError(f"Update File target is not a file: {op.path}")
            if dest != source and dest.exists():
                raise ApplyPatchParseError(f"Move target already exists: {op.new_path}")
            old_content = source.read_text(encoding="utf-8")
            if op.replace_lines is not None:
                new_content = "\n".join(op.replace_lines)
                if op.replace_lines:
                    new_content += "\n"
            else:
                new_content = self._apply_hunks(old_content, op.hunks, self._display_path(source))
            action = "move" if dest != source and new_content == old_content else "update"
            if dest != source and new_content != old_content:
                action = "move/update"
            if dest == source and new_content == old_content:
                raise ApplyPatchParseError(f"Update File '{op.path}' would not change content")
            changes.append(
                FileChange(
                    old_path=source,
                    new_path=dest,
                    display_old=self._display_path(source),
                    display_new=self._display_path(dest),
                    old_content=old_content,
                    new_content=new_content,
                    action=action,
                )
            )
        return changes

    def _diff_for_change(self, change: FileChange) -> str:
        fromfile = "/dev/null" if change.old_path is None else f"a/{change.display_old}"
        tofile = "/dev/null" if change.new_path is None else f"b/{change.display_new}"
        return "".join(
            difflib.unified_diff(
                change.old_content.splitlines(keepends=True),
                change.new_content.splitlines(keepends=True),
                fromfile=fromfile,
                tofile=tofile,
                n=3,
            )
        )

    def _write_changes(self, changes: list[FileChange]) -> None:
        for change in changes:
            if change.old_path is not None and change.new_path is None:
                change.old_path.unlink()
                continue
            if change.new_path is None:
                continue
            change.new_path.parent.mkdir(parents=True, exist_ok=True)
            change.new_path.write_text(change.new_content, encoding="utf-8")
            if change.old_path is not None and change.old_path != change.new_path:
                change.old_path.unlink()

    async def execute(self, patch: str, **kwargs: Any) -> ToolResult:
        start_time = time.perf_counter()
        del kwargs
        try:
            operations = self._parse(patch)
            changes = self._compute_changes(operations)
            diff_text = "".join(self._diff_for_change(change) for change in changes)
            self._write_changes(changes)

            changed_files = [
                change.display_new if change.new_path is not None else change.display_old
                for change in changes
            ]
            summary = f"Applied patch: {len(changes)} file(s) changed"
            if changed_files:
                suffix = ")" if len(changed_files) <= 5 else ", ...)"
                summary += " (" + ", ".join(changed_files[:5]) + suffix
            return ToolResult(
                success=True,
                result_summary=summary,
                result_data={
                    "changed_files": changed_files,
                    "operations": [change.action for change in changes],
                    "diff": diff_text,
                    "summary": summary,
                },
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                metadata={
                    "changed_files": changed_files,
                    "operations": [c.action for c in changes],
                },
            )
        except (ApplyPatchParseError, ValueError, UnicodeDecodeError) as e:
            return ToolResult(
                success=False,
                result_summary=f"Patch failed: {str(e)[:100]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            logger.error("apply_patch failed", extra={"error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Patch error: {str(e)[:100]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        return self._working_dir.is_dir()

    async def close(self) -> None:
        pass
