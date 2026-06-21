"""Shared filesystem helpers for workspace-bound tools."""

from __future__ import annotations

import fnmatch
import os
import tempfile
from pathlib import Path
from typing import Iterable

DEFAULT_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    ".tox",
    ".mypy_cache",
}


def resolve_workspace_path(base: Path, raw_path: str | None, *, default: str = ".") -> Path:
    """Resolve a path and ensure it stays inside the workspace."""
    path_value = default if raw_path in (None, "") else str(raw_path)
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = base / path
    resolved = path.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Path '{path_value}' is outside working directory") from exc
    return resolved


def display_workspace_path(base: Path, path: Path) -> str:
    """Return a stable workspace-relative display path."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def atomic_write_text(path: Path, content: str, *, expected_bytes: bytes | None = None) -> None:
    """Atomically replace a text file, optionally rejecting concurrent changes."""
    if expected_bytes is not None:
        try:
            current = path.read_bytes()
        except FileNotFoundError as exc:
            raise ValueError(f"File changed before write: {path}") from exc
        if current != expected_bytes:
            raise ValueError(f"File changed before write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = path.stat().st_mode if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if existing_mode is not None:
            os.chmod(tmp_name, existing_mode)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


class GitIgnoreMatcher:
    """Small gitignore-style matcher for common workspace ignore patterns.

    Uses pathspec when available. Falls back to a deterministic matcher covering
    exact paths, directory patterns, globs, anchored patterns, **, and negation.
    """

    def __init__(self, base: Path, patterns: Iterable[str]) -> None:
        self._base = base
        self._patterns = [p for p in patterns if p]
        self._spec = None
        try:
            import pathspec  # type: ignore

            self._spec = pathspec.PathSpec.from_lines("gitwildmatch", self._patterns)
        except Exception:
            self._spec = None

    @classmethod
    def from_workspace(cls, base: Path) -> "GitIgnoreMatcher":
        patterns: list[str] = []
        ignore_files = [base / ".gitignore", base / ".git" / "info" / "exclude"]
        try:
            for root, dirs, files in os.walk(base):
                dirs[:] = [name for name in dirs if name not in DEFAULT_SKIP_DIRS]
                candidate = Path(root) / ".gitignore"
                if ".gitignore" in files and candidate != base / ".gitignore":
                    ignore_files.append(candidate)
        except OSError:
            pass
        for gitignore in ignore_files:
            if not gitignore.is_file():
                continue
            try:
                parent = gitignore.parent
                if gitignore.parts[-3:] == (".git", "info", "exclude"):
                    parent = base
                prefix = parent.relative_to(base).as_posix()
                for raw_line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        if prefix == ".":
                            patterns.append(line)
                            continue
                        negation = "!" if line.startswith("!") else ""
                        clean = line.removeprefix("!").lstrip("/")
                        patterns.append(f"{negation}{prefix}/{clean}")
            except Exception:
                pass
        return cls(base, patterns)

    def is_ignored(self, path: Path) -> bool:
        """Return whether path should be hidden from discovery tools."""
        if any(part in DEFAULT_SKIP_DIRS for part in path.parts):
            return True

        try:
            rel = path.relative_to(self._base).as_posix()
        except ValueError:
            return True
        if not rel or rel == ".":
            return False

        if self._spec is not None:
            try:
                return bool(self._spec.match_file(rel))
            except Exception:
                pass

        ignored = False
        for pattern in self._patterns:
            negated = pattern.startswith("!")
            clean = pattern[1:] if negated else pattern
            clean = clean.strip()
            if not clean:
                continue
            if self._matches(clean, rel, path.is_dir()):
                ignored = not negated
        return ignored

    def _matches(self, pattern: str, rel: str, is_dir: bool) -> bool:
        directory_only = pattern.endswith("/")
        clean = pattern.rstrip("/")
        if directory_only and not is_dir and not any(part == clean for part in rel.split("/")[:-1]):
            return False

        anchored = clean.startswith("/")
        clean = clean.lstrip("/")
        if not clean:
            return False

        candidates = [rel] if anchored or "/" in clean else [rel, Path(rel).name, *rel.split("/")]
        if directory_only:
            parts = rel.split("/")
            candidates.extend("/".join(parts[:idx]) for idx in range(1, len(parts) + 1))

        for candidate in candidates:
            if candidate == clean or fnmatch.fnmatch(candidate, clean):
                return True
            if clean.endswith("/**") and candidate.startswith(clean[:-3].rstrip("/") + "/"):
                return True
            if clean.startswith("**/") and fnmatch.fnmatch(candidate, clean[3:]):
                return True
        return False
