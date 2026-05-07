"""Coding-agent context gathering.

Agent runs now always use the coding workspace context strategy. Plain chat runs
use the chat engine and do not pass through this module.
"""

import asyncio
import platform
from pathlib import Path
from typing import Optional, Protocol

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

_SUBPROCESS_TIMEOUT = 5.0
_CHARS_PER_TOKEN = 4
_ENV_CAP = 100 * _CHARS_PER_TOKEN
_RULES_CAP = 500 * _CHARS_PER_TOKEN
_STRUCTURE_CAP = 300 * _CHARS_PER_TOKEN
_RUNTIME_CAP = 200 * _CHARS_PER_TOKEN
_RULES_FILES = [".reasoner/rules.md", "CLAUDE.md", "AGENTS.md"]


class ContextStrategy(Protocol):
    async def gather(self, working_dir: Optional[str] = None) -> str:
        ...


async def _run_cmd(*args: str, cwd: Optional[str] = None, timeout: float = _SUBPROCESS_TIMEOUT) -> Optional[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0 and stdout:
            return stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        logger.debug("Subprocess failed", extra={"cmd": args[0] if args else "?", "error": str(e)})
    return None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


class CodingContextStrategy:
    """5-layer context stack for coding tasks."""

    async def gather(self, working_dir: Optional[str] = None) -> str:
        wd = working_dir or "."
        env_task = self._gather_environment()
        rules_task = self._load_rules(wd)
        structure_task = self._gather_project_structure(wd)
        runtime_task = self._gather_runtime_state(wd)
        env, rules, structure, runtime = await asyncio.gather(
            env_task, rules_task, structure_task, runtime_task,
        )
        sections = ["=== PROJECT CONTEXT ==="]
        if env:
            sections.append(f"\n[Environment]\n{env}")
        if rules:
            sections.append(f"\n[Project Rules]\n{rules}")
        if structure:
            sections.append(f"\n[Project Structure]\n{structure}")
        if runtime:
            sections.append(f"\n[Git State]\n{runtime}")
        sections.append(f"\n[Working Directory]\n{wd}")
        return "\n".join(sections)

    async def _gather_environment(self) -> str:
        parts = [f"OS: {platform.system()} {platform.machine()}"]
        python_ver = await _run_cmd("python3", "--version")
        if python_ver:
            parts.append(f"Python: {python_ver.replace('Python ', '')}")
        node_ver = await _run_cmd("node", "--version")
        if node_ver:
            parts.append(f"Node: {node_ver}")
        return _truncate(", ".join(parts), _ENV_CAP)

    async def _load_rules(self, working_dir: str) -> Optional[str]:
        wd = Path(working_dir)
        for rules_file in _RULES_FILES:
            rules_path = wd / rules_file
            try:
                if rules_path.is_file():
                    content = rules_path.read_text(encoding="utf-8", errors="replace")
                    if content.strip():
                        return _truncate(content.strip(), _RULES_CAP)
            except (OSError, PermissionError) as e:
                logger.debug("Failed to read rules file", extra={"path": str(rules_path), "error": str(e)})
        return None

    async def _gather_project_structure(self, working_dir: str) -> Optional[str]:
        _EXCLUDE_DIRS = {
            ".git", "node_modules", "__pycache__", ".venv", "venv", ".next", "dist", "build",
            ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache", "eggs", "*.egg-info",
        }
        _EXCLUDE_EXTS = {".pyc", ".pyo", ".class", ".o", ".so"}
        _MAX_DEPTH = 3
        _MAX_ENTRIES = 60
        wd = Path(working_dir)
        lines: list[str] = []

        def _walk_tree(directory: Path, prefix: str, depth: int) -> None:
            if depth > _MAX_DEPTH or len(lines) >= _MAX_ENTRIES:
                return
            try:
                entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except (OSError, PermissionError):
                return
            filtered = []
            for entry in entries:
                if entry.name.startswith(".") and entry.name in _EXCLUDE_DIRS:
                    continue
                if entry.is_dir() and entry.name in _EXCLUDE_DIRS:
                    continue
                if entry.is_file() and entry.suffix in _EXCLUDE_EXTS:
                    continue
                filtered.append(entry)
            for i, entry in enumerate(filtered):
                if len(lines) >= _MAX_ENTRIES:
                    lines.append(f"{prefix}...")
                    return
                is_last = i == len(filtered) - 1
                connector = "└── " if is_last else "├── "
                display_name = entry.name + ("/" if entry.is_dir() else "")
                lines.append(f"{prefix}{connector}{display_name}")
                if entry.is_dir():
                    extension = "    " if is_last else "│   "
                    _walk_tree(entry, prefix + extension, depth + 1)

        _walk_tree(wd, "", 0)
        parts = []
        if lines:
            parts.append("Files:\n" + "\n".join(lines))
        pyproject = wd / "pyproject.toml"
        if pyproject.is_file():
            try:
                content = pyproject.read_text(encoding="utf-8", errors="replace")
                if "[project]" in content:
                    parts.append("Build: pyproject.toml (Python)")
                elif "[tool.poetry]" in content:
                    parts.append("Build: pyproject.toml (Poetry)")
            except OSError:
                pass
        if (wd / "package.json").is_file():
            parts.append("Build: package.json (Node.js)")
        if not parts:
            return None
        return _truncate("\n".join(parts), _STRUCTURE_CAP)

    async def _gather_runtime_state(self, working_dir: str) -> Optional[str]:
        branch = await _run_cmd("git", "branch", "--show-current", cwd=working_dir)
        if branch is None:
            return None
        parts = [f"Branch: {branch}"]
        status = await _run_cmd("git", "status", "--short", cwd=working_dir)
        if status:
            lines = status.split("\n")
            status_text = "\n".join(lines[:10]) + (f"\n... ({len(lines) - 10} more)" if len(lines) > 10 else "")
            parts.append(f"Status:\n{status_text}")
        else:
            parts.append("Status: clean")
        log = await _run_cmd("git", "log", "--oneline", "-3", cwd=working_dir)
        if log:
            parts.append(f"Recent commits:\n{log}")
        return _truncate("\n".join(parts), _RUNTIME_CAP)


CODING_CONTEXT_STRATEGY = CodingContextStrategy()


def get_context_strategy(name: str = "coding") -> ContextStrategy:
    if name != "coding":
        raise ValueError("Only the 'coding' context strategy exists for agent runs.")
    return CODING_CONTEXT_STRATEGY
