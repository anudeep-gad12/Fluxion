"""Browser workspace routes.

Read-only helpers for choosing local workspace folders from the browser UI.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("/browse")
async def browse_workspace_directories(path: Optional[str] = Query(None)):
    """List child directories for a local path.

    The app is local-first, so this endpoint intentionally exposes local
    directories to the browser UI for workspace selection. It does not return
    files or file contents.
    """
    target = Path(path).expanduser() if path else Path.home()
    try:
        target = target.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

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
