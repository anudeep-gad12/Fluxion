"""Permission policy helpers for browser agent tools."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


READ_ONLY_TOOLS = {
    "read_file",
    "list_directory",
    "glob",
    "grep",
    "web_search",
    "web_extract",
}

ALWAYS_AUTO_TOOLS = {"web_search", "web_extract"}

SAFE_BASH_COMMANDS = {
    "pwd",
    "ls",
    "find",
    "cat",
    "head",
    "tail",
    "grep",
    "rg",
    "ag",
    "ack",
    "wc",
    "sort",
    "cut",
    "uniq",
    "jq",
    "which",
    "whereis",
    "file",
    "stat",
    "git",
}

MUTATING_BASH_COMMANDS = {
    "touch",
    "mkdir",
    "mktemp",
    "cp",
    "mv",
    "ln",
    "chmod",
    "chown",
    "chgrp",
    "truncate",
    "xargs",
    "tee",
    "sed",
    "perl",
    "python",
    "python3",
    "node",
    "ruby",
    "php",
    "go",
    "cargo",
    "make",
    "just",
    "npm",
    "pnpm",
    "yarn",
    "bun",
    "uv",
    "pip",
    "pip3",
    "poetry",
    "docker",
    "docker-compose",
    "kubectl",
    "brew",
    "apt",
    "apt-get",
    "dnf",
    "yum",
    "scp",
    "rsync",
    "ssh",
    "curl",
    "wget",
    "open",
    "osascript",
    "kill",
    "pkill",
    "killall",
    "nohup",
}

DESTRUCTIVE_BASH_COMMANDS = {
    "rm",
    "rmdir",
    "dd",
    "mkfs",
    "fdisk",
    "diskutil",
}

READ_ONLY_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "log",
    "show",
    "rev-parse",
}

DESTRUCTIVE_PATTERNS = (
    r"\brm\s+-",
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
    r"\bgit\s+checkout\s+--\b",
    r"\bgit\s+restore\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bkill(all|)\b",
)

WRITE_OPERATOR_RE = re.compile(r"(^|[^<])>>?|2>|&>|<\(|\btee\b")
INPLACE_EDIT_RE = re.compile(r"\bsed\s+-i\b|\bperl\s+-pi\b|\bawk\b.*\binplace\b")
ABSOLUTE_PATH_RE = re.compile(r"(?<![\w./~-])(/[^ \t\n\r;|&]+)")


@dataclass(frozen=True)
class PermissionDecision:
    """Resolved permission outcome for a tool call."""

    needs_approval: bool
    permission_level: str
    reason: str


def classify_tool_call(
    *,
    policy: str,
    tool_name: str,
    arguments: dict[str, Any],
    base_permission_level: str,
    workspace_path: str | None,
) -> PermissionDecision:
    """Classify a tool call under the current permission policy."""
    if tool_name in ALWAYS_AUTO_TOOLS:
        return PermissionDecision(False, "auto", "web tools are always auto-approved")

    if policy == "yolo":
        return PermissionDecision(False, "auto", "yolo policy auto-approves all tools")

    if policy == "strict":
        return PermissionDecision(True, base_permission_level, "strict policy requires approval")

    if tool_name in READ_ONLY_TOOLS:
        return PermissionDecision(False, "auto", "read-only tool allowed in relaxed mode")

    if tool_name in {"write_file", "edit_file"}:
        return PermissionDecision(True, "confirm", "filesystem mutations require approval")

    if tool_name == "bash":
        return classify_bash_command(
            command=str(arguments.get("command", "")),
            workspace_path=workspace_path,
        )

    return PermissionDecision(
        base_permission_level != "auto",
        base_permission_level,
        "fallback tool permission",
    )


def classify_bash_command(command: str, workspace_path: str | None) -> PermissionDecision:
    """Classify a bash command for relaxed mode approval."""
    stripped = command.strip()
    if not stripped:
        return PermissionDecision(True, "dangerous", "empty command is not auto-approved")

    lowered = stripped.lower()
    if WRITE_OPERATOR_RE.search(stripped) or INPLACE_EDIT_RE.search(lowered):
        return PermissionDecision(True, "dangerous", "shell redirection or in-place editing can write files")

    if _references_outside_workspace(stripped, workspace_path):
        return PermissionDecision(True, "dangerous", "command references paths outside the workspace")

    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, lowered):
            return PermissionDecision(True, "destructive", "destructive shell command")

    for segment in _split_shell_segments(stripped):
        decision = _classify_bash_segment(segment)
        if decision is not None:
            return decision

    return PermissionDecision(False, "auto", "read-only shell command allowed in relaxed mode")


def _split_shell_segments(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"&&|\|\||;", command) if segment.strip()]


def _classify_bash_segment(segment: str) -> PermissionDecision | None:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        return PermissionDecision(True, "dangerous", "complex shell syntax requires approval")

    if not tokens:
        return None

    cmd = tokens[0]

    if cmd in DESTRUCTIVE_BASH_COMMANDS:
        return PermissionDecision(True, "destructive", f"{cmd} is destructive")

    if cmd == "git":
        subcommand = tokens[1] if len(tokens) > 1 else ""
        if subcommand in READ_ONLY_GIT_SUBCOMMANDS:
            return None
        if subcommand == "branch":
            if len(tokens) == 2 or tokens[2:] == ["-v"]:
                return None
            if any(flag in tokens for flag in ("-d", "-D", "-m", "-M", "--delete")):
                return PermissionDecision(True, "destructive", "git branch delete/rename modifies git state")
            return PermissionDecision(True, "dangerous", "git branch command modifies repository state")
        if subcommand == "remote":
            if len(tokens) == 2 or tokens[2:] == ["-v"]:
                return None
            return PermissionDecision(True, "dangerous", "git remote command modifies repository state")
        return PermissionDecision(True, "dangerous", "git command modifies repository state")

    if cmd in MUTATING_BASH_COMMANDS:
        return PermissionDecision(True, "dangerous", f"{cmd} may modify files, processes, or the system")

    if cmd not in SAFE_BASH_COMMANDS:
        return PermissionDecision(True, "dangerous", f"{cmd} is not in the read-only allowlist")

    return None


def _references_outside_workspace(command: str, workspace_path: str | None) -> bool:
    if not workspace_path:
        return False

    workspace = Path(workspace_path).resolve()
    for match in ABSOLUTE_PATH_RE.findall(command):
        path = Path(match).expanduser()
        try:
            resolved = path.resolve(strict=False)
        except RuntimeError:
            return True
        if not _is_within_workspace(resolved, workspace):
            return True
    return False


def _is_within_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.relative_to(workspace)
        return True
    except ValueError:
        return False
