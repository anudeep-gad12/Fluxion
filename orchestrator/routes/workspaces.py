"""Browser workspace routes.

Read-only helpers for choosing local workspaces and searching files from the browser UI.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

_IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".cache",
    "__pycache__",
}


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

    try:
        for root, dirs, files in workspace.walk(top_down=True):
            dirs[:] = [
                name
                for name in dirs
                if not name.startswith(".") and name not in _IGNORED_DIRS
            ]
            for filename in files:
                if filename.startswith("."):
                    continue
                file_path = root / filename
                rel_path = file_path.relative_to(workspace).as_posix()
                if query and query not in rel_path.lower():
                    continue
                matches.append(
                    {
                        "path": rel_path,
                        "name": filename,
                    }
                )
    except PermissionError:
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
