"""Durable workspace-local Plan Mode markdown documents."""

from __future__ import annotations

import asyncio
import difflib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PLAN_DOC_DIR = ".fluxion/plans"
_SAFE_PLAN_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LOCKS: dict[str, asyncio.Lock] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_doc_relative_path(plan_run_id: str) -> str:
    """Return the workspace-relative plan doc path for a plan run id."""
    clean_id = (plan_run_id or "").strip()
    if not _SAFE_PLAN_RUN_ID_RE.fullmatch(clean_id):
        raise ValueError("Invalid plan_run_id")
    if ".." in Path(clean_id).parts:
        raise ValueError("Invalid plan_run_id")
    return f"{PLAN_DOC_DIR}/{clean_id}.md"


def resolve_plan_doc_path(workspace_path: str, relative_path: str) -> Path:
    """Resolve and validate a plan doc path inside <workspace>/.fluxion/plans."""
    workspace = Path(workspace_path).expanduser().resolve()
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Plan doc path must be workspace-relative")
    target = (workspace / rel).resolve()
    allowed_root = (workspace / PLAN_DOC_DIR).resolve()
    if not target.is_relative_to(allowed_root):
        raise ValueError("Plan doc path must stay inside .fluxion/plans")
    if target.suffix != ".md":
        raise ValueError("Plan doc path must be a markdown file")
    return target


def build_initial_plan_doc(
    *,
    plan_run_id: str,
    original_request: str,
    objective: Optional[str] = None,
) -> str:
    """Build the initial markdown scaffold for a Plan Mode run."""
    clean_request = (original_request or "").strip()
    clean_objective = (objective or clean_request or "TBD").strip()
    return (
        f"# Fluxion Plan: {plan_run_id}\n\n"
        f"- Created: {_now_iso()}\n"
        f"- Plan run id: `{plan_run_id}`\n\n"
        "## Original Request\n\n"
        f"{clean_request or 'TBD'}\n\n"
        "## Objective\n\n"
        f"{clean_objective}\n\n"
        "## Research Notes\n\n"
        "- TBD\n\n"
        "## Decisions / Assumptions\n\n"
        "- TBD\n\n"
        "## Open Questions\n\n"
        "- TBD\n\n"
        "## Draft Plan\n\n"
        "- TBD\n\n"
        "## Progress Checklist\n\n"
        "- [ ] Planning complete\n"
        "- [ ] Plan approved\n"
        "- [ ] Implementation started\n"
        "- [ ] Validation complete\n"
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _lock_for(path: Path) -> asyncio.Lock:
    key = str(path)
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


async def create_initial_plan_doc(
    *,
    workspace_path: str,
    plan_run_id: str,
    original_request: str,
) -> tuple[str, int]:
    """Create the initial plan doc if missing and return relative path + bytes."""
    relative_path = plan_doc_relative_path(plan_run_id)
    target = resolve_plan_doc_path(workspace_path, relative_path)
    async with _lock_for(target):
        if not target.exists():
            content = build_initial_plan_doc(
                plan_run_id=plan_run_id,
                original_request=original_request,
            )
            _atomic_write(target, content)
        byte_count = target.stat().st_size
    return relative_path, byte_count


async def update_plan_doc_content(
    *,
    workspace_path: str,
    relative_path: str,
    content: str,
    include_diff: bool = False,
) -> tuple[int, Optional[str]]:
    """Atomically replace the assigned plan doc content."""
    target = resolve_plan_doc_path(workspace_path, relative_path)
    async with _lock_for(target):
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        _atomic_write(target, content)
        byte_count = target.stat().st_size
    diff = None
    if include_diff:
        diff = "".join(
            difflib.unified_diff(
                previous.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
                lineterm="",
            )
        )
    return byte_count, diff


async def append_plan_doc_section(
    *,
    workspace_path: str,
    relative_path: str,
    heading: str,
    body: str,
) -> int:
    """Append a timestamped section to a plan doc atomically."""
    target = resolve_plan_doc_path(workspace_path, relative_path)
    section = (
        "\n\n"
        f"## {heading}\n\n"
        f"- Updated: {_now_iso()}\n\n"
        f"{body.strip()}\n"
    )
    async with _lock_for(target):
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        content = previous.rstrip() + section
        _atomic_write(target, content)
        return target.stat().st_size


def summarize_plan_doc_update(content: str) -> str:
    """Return a concise summary string for a new plan doc body."""
    headings = [
        line.strip("# ").strip()
        for line in content.splitlines()
        if line.startswith("#")
    ]
    if headings:
        return f"Updated plan doc sections: {', '.join(headings[:3])}"
    return "Updated plan doc"
