"""Context strategies for gathering project environment information.

Each strategy gathers different levels of context to inject into the
agent's system prompt. This gives the agent awareness of the project
it's working in, reducing wasted tool calls.

Strategies:
- ResearchContextStrategy: Date + knowledge cutoff only (current behavior)
- CodingContextStrategy: 5-layer context stack (env, rules, structure, git, working dir)
"""

import asyncio
import platform
from datetime import date
from pathlib import Path
from typing import Optional, Protocol

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

# Subprocess timeout to avoid blocking the agent
_SUBPROCESS_TIMEOUT = 5.0

# Token budget caps (approximate, using ~4 chars per token)
_CHARS_PER_TOKEN = 4
_ENV_CAP = 100 * _CHARS_PER_TOKEN        # 400 chars
_RULES_CAP = 500 * _CHARS_PER_TOKEN      # 2000 chars
_STRUCTURE_CAP = 300 * _CHARS_PER_TOKEN   # 1200 chars
_RUNTIME_CAP = 200 * _CHARS_PER_TOKEN     # 800 chars

# Rules file lookup order
_RULES_FILES = [".reasoner/rules.md", "CLAUDE.md", "AGENTS.md"]


class ContextStrategy(Protocol):
    """Protocol for context gathering strategies."""

    async def gather(self, working_dir: Optional[str] = None) -> str:
        """Gather context information for the system prompt.

        Args:
            working_dir: Optional working directory path.

        Returns:
            Formatted context string for injection into system prompt.
        """
        ...


async def _run_cmd(
    *args: str,
    cwd: Optional[str] = None,
    timeout: float = _SUBPROCESS_TIMEOUT,
) -> Optional[str]:
    """Run a subprocess command and return stdout.

    Args:
        args: Command and arguments.
        cwd: Working directory.
        timeout: Timeout in seconds.

    Returns:
        stdout string or None if command fails.
    """
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
        logger.debug(
            "Subprocess failed",
            extra={"cmd": args[0] if args else "?", "error": str(e)},
        )
    return None


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '...' if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


class ResearchContextStrategy:
    """Date + knowledge cutoff only (current behavior)."""

    async def gather(self, working_dir: Optional[str] = None) -> str:
        """Gather research context (date info only).

        Args:
            working_dir: Unused for research context.

        Returns:
            Date and knowledge cutoff string.
        """
        today = date.today()
        return (
            f"Current date: {today.strftime('%B %d, %Y')}\n"
            f"Your knowledge cutoff: June 2024. For information after this date, use web_search."
        )


class CodingContextStrategy:
    """5-layer context stack for coding tasks.

    Gathers:
    1. Environment (OS, shell, Python/Node versions)
    2. Project rules (.reasoner/rules.md or CLAUDE.md)
    3. Project structure (file tree, dependencies)
    4. Runtime state (git branch, status, recent commits)
    5. Working directory path
    """

    async def gather(self, working_dir: Optional[str] = None) -> str:
        """Gather full coding context.

        Args:
            working_dir: Project working directory.

        Returns:
            Formatted multi-layer context string (~400 tokens).
        """
        wd = working_dir or "."

        # Gather layers concurrently
        env_task = self._gather_environment()
        rules_task = self._load_rules(wd)
        structure_task = self._gather_project_structure(wd)
        runtime_task = self._gather_runtime_state(wd)

        env, rules, structure, runtime = await asyncio.gather(
            env_task, rules_task, structure_task, runtime_task,
        )

        sections = []

        sections.append("=== PROJECT CONTEXT ===")

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
        """Gather OS, shell, and language version info."""
        parts = [f"OS: {platform.system()} {platform.machine()}"]

        # Python version
        python_ver = await _run_cmd("python3", "--version")
        if python_ver:
            parts.append(f"Python: {python_ver.replace('Python ', '')}")

        # Node version
        node_ver = await _run_cmd("node", "--version")
        if node_ver:
            parts.append(f"Node: {node_ver}")

        result = ", ".join(parts)
        return _truncate(result, _ENV_CAP)

    async def _load_rules(self, working_dir: str) -> Optional[str]:
        """Load project rules file if present.

        Checks: .reasoner/rules.md → CLAUDE.md → AGENTS.md
        """
        wd = Path(working_dir)
        for rules_file in _RULES_FILES:
            rules_path = wd / rules_file
            try:
                if rules_path.is_file():
                    content = rules_path.read_text(encoding="utf-8", errors="replace")
                    if content.strip():
                        return _truncate(content.strip(), _RULES_CAP)
            except (OSError, PermissionError) as e:
                logger.debug(
                    "Failed to read rules file",
                    extra={"path": str(rules_path), "error": str(e)},
                )
        return None

    async def _gather_project_structure(self, working_dir: str) -> Optional[str]:
        """Gather indented file tree (max 3 levels) and key dependency files."""
        import os

        _EXCLUDE_DIRS = {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            ".next", "dist", "build", ".tox", ".mypy_cache", ".ruff_cache",
            ".pytest_cache", "eggs", "*.egg-info",
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

            # Filter out excluded dirs and files
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

        # Dependencies: check pyproject.toml or package.json
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

        package_json = wd / "package.json"
        if package_json.is_file():
            parts.append("Build: package.json (Node.js)")

        if not parts:
            return None

        result = "\n".join(parts)
        return _truncate(result, _STRUCTURE_CAP)

    async def _gather_runtime_state(self, working_dir: str) -> Optional[str]:
        """Gather git branch, status, and recent commits."""
        # Check if it's a git repo
        branch = await _run_cmd("git", "branch", "--show-current", cwd=working_dir)
        if branch is None:
            return None

        parts = [f"Branch: {branch}"]

        # Status (short format)
        status = await _run_cmd("git", "status", "--short", cwd=working_dir)
        if status:
            lines = status.split("\n")
            if len(lines) > 10:
                status_text = "\n".join(lines[:10]) + f"\n... ({len(lines) - 10} more)"
            else:
                status_text = status
            parts.append(f"Status:\n{status_text}")
        else:
            parts.append("Status: clean")

        # Recent commits (last 3)
        log = await _run_cmd(
            "git", "log", "--oneline", "-3", cwd=working_dir,
        )
        if log:
            parts.append(f"Recent commits:\n{log}")

        result = "\n".join(parts)
        return _truncate(result, _RUNTIME_CAP)


# =============================================================================
# Strategy Registry
# =============================================================================

_STRATEGIES = {
    "research": ResearchContextStrategy,
    "coding": CodingContextStrategy,
}


def get_context_strategy(name: str) -> ContextStrategy:
    """Get a context strategy by name.

    Args:
        name: Strategy name ("research", "coding").

    Returns:
        ContextStrategy instance.

    Raises:
        ValueError: If strategy name is not recognized.
    """
    strategy_cls = _STRATEGIES.get(name)
    if strategy_cls is None:
        valid = ", ".join(sorted(_STRATEGIES.keys()))
        raise ValueError(f"Unknown context strategy '{name}'. Valid: {valid}")
    return strategy_cls()
