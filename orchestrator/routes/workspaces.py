"""Browser workspace routes.

Read-only helpers for choosing local workspaces and searching files from the browser UI.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from orchestrator.logging_config import get_logger

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])
logger = get_logger(__name__)

_IGNORED_DIRS = {
    ".git",
    ".fluxion",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".cache",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "venv",
    "__pycache__",
}

_MAX_SEARCH_SCANNED_FILES = 10_000
_EMPTY_QUERY_BUFFER_MULTIPLIER = 25


class EnsureFluxionGitignoreRequest(BaseModel):
    workspace_path: str


def _resolve_workspace_path(path: Optional[str]) -> Path:
    """Resolve and validate a workspace path."""
    target = Path(path).expanduser() if path else Path.home()
    try:
        target = target.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")
    return target


def _is_git_controlled_workspace(workspace: Path) -> bool:
    """Return True when workspace is inside a Git working tree."""
    current = workspace.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return True
    return False


def _gitignore_has_fluxion_entry(content: str) -> bool:
    """Detect common `.fluxion` ignore entries without duplicating them."""
    entries = {
        ".fluxion",
        ".fluxion/",
        ".fluxion/**",
        "/.fluxion",
        "/.fluxion/",
        "/.fluxion/**",
    }
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in entries:
            return True
    return False


def ensure_fluxion_gitignore(workspace: Path) -> bool:
    """Ensure workspace-local `.fluxion/` is ignored by Git.

    Returns True if `.gitignore` was changed, False otherwise. Best effort:
    workspace creation/opening should not fail just because `.gitignore` is
    unwritable.
    """
    workspace = workspace.resolve()
    if not _is_git_controlled_workspace(workspace):
        return False

    gitignore = workspace / ".gitignore"
    try:
        content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if _gitignore_has_fluxion_entry(content):
            return False

        prefix = "" if not content or content.endswith("\n") else "\n"
        gitignore.write_text(f"{content}{prefix}.fluxion/\n", encoding="utf-8")
        logger.info(
            "Ensured .fluxion is gitignored",
            extra={"workspace_path": str(workspace), "gitignore": str(gitignore)},
        )
        return True
    except OSError as exc:
        logger.warning(
            "Could not update workspace .gitignore for .fluxion",
            extra={"workspace_path": str(workspace), "error": str(exc)},
        )
    return False


@router.post("/ensure-fluxion-gitignore")
async def ensure_workspace_fluxion_gitignore(request: EnsureFluxionGitignoreRequest):
    """Best-effort ensure the selected workspace ignores Fluxion scratch files."""
    workspace = _resolve_workspace_path(request.workspace_path)
    changed = ensure_fluxion_gitignore(workspace)
    gitignore_path = workspace / ".gitignore"
    ignored = False
    try:
        if gitignore_path.exists():
            ignored = _gitignore_has_fluxion_entry(gitignore_path.read_text(encoding="utf-8"))
    except OSError:
        ignored = False
    return {
        "workspace_path": str(workspace),
        "changed": changed,
        "ignored": ignored,
    }


@router.get("/browse")
async def browse_workspace_directories(path: Optional[str] = Query(None)):
    """List child directories for a local path.

    The app is local-first, so this endpoint intentionally exposes local
    directories to the browser UI for workspace selection. It does not return
    files or file contents.
    """
    target = _resolve_workspace_path(path)

    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        children = []

    for child in children:
        if not child.is_dir():
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "hidden": child.name.startswith("."),
            }
        )

    parent = target.parent if target.parent != target else None
    return {
        "path": str(target),
        "parent": str(parent) if parent else None,
        "entries": entries,
    }


@router.get("/search-files")
async def search_workspace_files(
    workspace_path: str = Query(...),
    q: str = Query(""),
    limit: int = Query(20, ge=1, le=100),
):
    """Search files within a workspace for @mention autocomplete."""
    workspace = _resolve_workspace_path(workspace_path)
    query = q.strip().lower()
    matches: list[dict[str, str]] = []
    scanned = 0
    empty_query_buffer = max(limit * _EMPTY_QUERY_BUFFER_MULTIPLIER, limit)

    try:
        for root, dirs, files in os.walk(workspace, topdown=True, onerror=lambda _e: None):
            dirs[:] = [
                name
                for name in dirs
                if not name.startswith(".") and name not in _IGNORED_DIRS
            ]
            for filename in files:
                if scanned >= _MAX_SEARCH_SCANNED_FILES:
                    break
                scanned += 1

                if filename.startswith("."):
                    continue

                try:
                    file_path = Path(root) / filename
                    if not file_path.is_file():
                        continue
                    rel_path = file_path.relative_to(workspace).as_posix()
                except (OSError, ValueError):
                    continue

                if query and query not in rel_path.lower():
                    continue
                matches.append(
                    {
                        "path": rel_path,
                        "name": filename,
                    }
                )

                if not query and len(matches) >= empty_query_buffer:
                    break

            if scanned >= _MAX_SEARCH_SCANNED_FILES or (
                not query and len(matches) >= empty_query_buffer
            ):
                break
    except OSError:
        pass

    matches.sort(
        key=lambda item: (
            query not in item["name"].lower(),
            item["path"].lower().find(query) if query else 0,
            len(item["path"]),
            item["path"].lower(),
        )
    )
    return {
        "workspace_path": str(workspace),
        "query": q,
        "entries": matches[:limit],
    }
