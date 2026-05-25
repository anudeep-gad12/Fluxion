"""Codex-style command session tools for long-running shell commands."""

from __future__ import annotations

import asyncio
import os
import pty
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)

_DEFAULT_YIELD_MS = 1000
_DEFAULT_TIMEOUT = 300
_MAX_TIMEOUT = 1800
_DEFAULT_MAX_OUTPUT_TOKENS = 6000


def _max_chars(max_output_tokens: Optional[int]) -> int:
    tokens = max(1, int(max_output_tokens or _DEFAULT_MAX_OUTPUT_TOKENS))
    return tokens * 4


def _truncate(text: str, max_output_tokens: Optional[int]) -> tuple[str, bool]:
    limit = _max_chars(max_output_tokens)
    if len(text) <= limit:
        return text, False
    half = max(1000, limit // 2)
    return (
        text[:half]
        + (
            "\n\n... (output truncated to "
            f"~{max_output_tokens or _DEFAULT_MAX_OUTPUT_TOKENS} tokens; "
            "showing head and tail) ...\n\n"
        )
        + text[-half:],
        True,
    )


@dataclass
class CommandSession:
    """Running subprocess session."""

    session_id: int
    cmd: str
    cwd: Path
    proc: asyncio.subprocess.Process
    tty: bool = False
    started_at: float = field(default_factory=time.perf_counter)
    stdout_buffer: bytearray = field(default_factory=bytearray)
    stderr_buffer: bytearray = field(default_factory=bytearray)
    drain_tasks: list[asyncio.Task] = field(default_factory=list)
    timeout_task: Optional[asyncio.Task] = None
    timed_out: bool = False
    master_fd: Optional[int] = None


class CommandSessionManager:
    """Owns running command sessions for one tool registry/agent run."""

    def __init__(self, working_dir: str = ".") -> None:
        self._working_dir = Path(working_dir).resolve()
        self._cwd = self._working_dir
        self._next_id = 1
        self._sessions: dict[int, CommandSession] = {}

    def resolve_workdir(self, workdir: Optional[str]) -> Path:
        if not workdir:
            return self._cwd
        path = Path(workdir)
        if not path.is_absolute():
            path = self._working_dir / path
        resolved = path.resolve()
        try:
            resolved.relative_to(self._working_dir)
        except ValueError as exc:
            raise ValueError(f"workdir '{workdir}' is outside working directory") from exc
        if not resolved.is_dir():
            raise ValueError(f"workdir '{workdir}' is not a directory")
        return resolved

    async def start(
        self,
        *,
        cmd: str,
        workdir: Optional[str],
        timeout: int,
        tty: bool,
    ) -> CommandSession:
        clean_cmd = str(cmd or "").strip()
        if not clean_cmd:
            raise ValueError("cmd is required")
        cwd = self.resolve_workdir(workdir)
        timeout = min(max(1, int(timeout or _DEFAULT_TIMEOUT)), _MAX_TIMEOUT)
        session_id = self._next_id
        self._next_id += 1

        master_fd: Optional[int] = None
        if tty:
            master_fd, slave_fd = pty.openpty()
            proc = await asyncio.create_subprocess_shell(
                clean_cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=str(cwd),
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            os.close(slave_fd)
        else:
            proc = await asyncio.create_subprocess_shell(
                clean_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )

        session = CommandSession(
            session_id=session_id,
            cmd=clean_cmd,
            cwd=cwd,
            proc=proc,
            tty=tty,
            master_fd=master_fd,
        )
        self._sessions[session_id] = session

        if tty:
            session.drain_tasks.append(asyncio.create_task(self._drain_pty(session)))
        else:
            session.drain_tasks.append(
                asyncio.create_task(self._drain_stream(proc.stdout, session.stdout_buffer))
            )
            session.drain_tasks.append(
                asyncio.create_task(self._drain_stream(proc.stderr, session.stderr_buffer))
            )
        session.timeout_task = asyncio.create_task(self._kill_after_timeout(session, timeout))
        return session

    async def _drain_stream(self, stream: asyncio.StreamReader | None, buffer: bytearray) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            buffer.extend(chunk)

    async def _drain_pty(self, session: CommandSession) -> None:
        if session.master_fd is None:
            return
        fd = session.master_fd
        try:
            while True:
                try:
                    chunk = await asyncio.to_thread(os.read, fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                session.stdout_buffer.extend(chunk)
                if session.proc.returncode is not None:
                    break
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            session.master_fd = None

    async def _kill_after_timeout(self, session: CommandSession, timeout: int) -> None:
        try:
            await asyncio.sleep(timeout)
            if session.proc.returncode is None:
                session.timed_out = True
                await self._terminate(session)
        except asyncio.CancelledError:
            return

    async def wait_briefly(self, session: CommandSession, yield_time_ms: int) -> bool:
        timeout = max(0, int(yield_time_ms or 0)) / 1000
        try:
            await asyncio.wait_for(session.proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        await self._settle_drains(session)
        return True

    async def _settle_drains(self, session: CommandSession) -> None:
        if session.timeout_task:
            session.timeout_task.cancel()
        if session.drain_tasks:
            await asyncio.gather(*session.drain_tasks, return_exceptions=True)

    def get(self, session_id: int) -> Optional[CommandSession]:
        return self._sessions.get(int(session_id))

    async def poll(self, session: CommandSession, yield_time_ms: int) -> bool:
        if session.proc.returncode is None:
            return await self.wait_briefly(session, yield_time_ms)
        await self._settle_drains(session)
        return True

    async def write(self, session: CommandSession, chars: str) -> None:
        if session.proc.returncode is not None:
            return
        if not chars:
            return
        data = chars.encode("utf-8")
        if session.tty and session.master_fd is not None:
            await asyncio.to_thread(os.write, session.master_fd, data)
            return
        if session.proc.stdin is not None:
            session.proc.stdin.write(data)
            await session.proc.stdin.drain()

    async def remove_if_done(self, session: CommandSession) -> None:
        if session.proc.returncode is not None:
            await self._settle_drains(session)
            self._sessions.pop(session.session_id, None)

    def render(self, session: CommandSession, max_output_tokens: Optional[int]) -> dict[str, Any]:
        stdout = session.stdout_buffer.decode("utf-8", errors="replace")
        stderr = session.stderr_buffer.decode("utf-8", errors="replace")
        output = "\n".join(
            part for part in (stdout, f"STDERR:\n{stderr}" if stderr else "") if part
        )
        output, output_truncated = _truncate(output or "", max_output_tokens)
        stdout_display, stdout_truncated = _truncate(stdout, max_output_tokens)
        stderr_display, stderr_truncated = _truncate(stderr, max_output_tokens)
        running = session.proc.returncode is None
        return {
            "session_id": session.session_id,
            "cmd": session.cmd,
            "workdir": str(session.cwd),
            "status": "running" if running else "completed",
            "running": running,
            "exit_code": session.proc.returncode,
            "stdout": stdout_display,
            "stderr": stderr_display,
            "output": output if output else "(no output)",
            "truncated": output_truncated or stdout_truncated or stderr_truncated,
            "timed_out": session.timed_out,
        }

    async def _terminate(self, session: CommandSession) -> None:
        if session.proc.returncode is not None:
            return
        try:
            session.proc.terminate()
            await asyncio.wait_for(session.proc.wait(), timeout=2)
        except Exception:
            try:
                session.proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(session.proc.wait(), timeout=2)
            except Exception:
                pass
        await self._settle_drains(session)

    async def cleanup(self) -> None:
        sessions = list(self._sessions.values())
        for session in sessions:
            await self._terminate(session)
        self._sessions.clear()


class ExecCommandTool:
    """Start a shell command and keep a session open if it is still running."""

    def __init__(self, manager: CommandSessionManager) -> None:
        self._manager = manager
        self._working_dir = manager._working_dir

    @property
    def name(self) -> str:
        return "exec_command"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="exec_command",
            description=(
                "Run a shell command in the workspace. Prefer this over bash for tests, "
                "builds, dev servers, inspection commands, and focused verification. "
                "If the command is still running after yield_time_ms, returns a session_id "
                "that can be polled or written to with write_stdin."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Optional workspace-relative working directory.",
                    },
                    "yield_time_ms": {
                        "type": "integer",
                        "description": (
                            "Milliseconds to wait before returning a running session."
                        ),
                        "default": _DEFAULT_YIELD_MS,
                    },
                    "max_output_tokens": {
                        "type": "integer",
                        "description": "Approximate maximum output tokens to return.",
                        "default": _DEFAULT_MAX_OUTPUT_TOKENS,
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum runtime in seconds (default 300, max 1800).",
                        "default": _DEFAULT_TIMEOUT,
                    },
                    "tty": {
                        "type": "boolean",
                        "description": "Run under a pseudo-terminal for interactive commands.",
                        "default": False,
                    },
                },
                "required": ["cmd"],
            },
            is_idempotent=False,
            permission_level="dangerous",
        )

    async def execute(
        self,
        cmd: str,
        workdir: Optional[str] = None,
        yield_time_ms: int = _DEFAULT_YIELD_MS,
        max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
        timeout: int = _DEFAULT_TIMEOUT,
        tty: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        del kwargs
        start_time = time.perf_counter()
        try:
            session = await self._manager.start(
                cmd=cmd,
                workdir=workdir,
                timeout=timeout,
                tty=bool(tty),
            )
            completed = await self._manager.wait_briefly(session, yield_time_ms)
            data = self._manager.render(session, max_output_tokens)
            if completed:
                await self._manager.remove_if_done(session)
                exit_code = data.get("exit_code")
                success = exit_code == 0 and not data.get("timed_out")
                status_word = "succeeded" if success else "failed"
                summary = f"Command {status_word} (exit {exit_code}): {cmd[:80]}"
            else:
                success = True
                summary = f"Command still running (session {session.session_id}): {cmd[:80]}"
            return ToolResult(
                success=success,
                result_summary=summary,
                result_data=data,
                error_message=None if success else data.get("stderr") or summary,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                metadata={
                    "session_id": data.get("session_id"),
                    "status": data.get("status"),
                    "exit_code": data.get("exit_code"),
                    "truncated": data.get("truncated"),
                    "timed_out": data.get("timed_out"),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                result_summary=f"Command error: {str(e)[:100]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        return self._working_dir.is_dir()

    async def close(self) -> None:
        await self._manager.cleanup()


class WriteStdinTool:
    """Write to or poll a running exec_command session."""

    def __init__(self, manager: CommandSessionManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "write_stdin"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_stdin",
            description=(
                "Poll a running exec_command session, optionally writing text to stdin first. "
                "Use with the session_id returned by exec_command."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "integer",
                        "description": "Running command session id.",
                    },
                    "chars": {
                        "type": "string",
                        "description": (
                            "Optional characters to write to stdin before polling."
                        ),
                    },
                    "yield_time_ms": {
                        "type": "integer",
                        "description": "Milliseconds to wait for output or completion.",
                        "default": _DEFAULT_YIELD_MS,
                    },
                    "max_output_tokens": {
                        "type": "integer",
                        "description": "Approximate maximum output tokens to return.",
                        "default": _DEFAULT_MAX_OUTPUT_TOKENS,
                    },
                },
                "required": ["session_id"],
            },
            is_idempotent=False,
            permission_level="dangerous",
        )

    async def execute(
        self,
        session_id: int,
        chars: Optional[str] = None,
        yield_time_ms: int = _DEFAULT_YIELD_MS,
        max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS,
        **kwargs: Any,
    ) -> ToolResult:
        del kwargs
        start_time = time.perf_counter()
        session = self._manager.get(int(session_id))
        if session is None:
            return ToolResult(
                success=False,
                result_summary=f"Command session not found: {session_id}",
                error_message=f"No running command session with id {session_id}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        try:
            await self._manager.write(session, chars or "")
            completed = await self._manager.poll(session, yield_time_ms)
            data = self._manager.render(session, max_output_tokens)
            if completed:
                await self._manager.remove_if_done(session)
            exit_code = data.get("exit_code")
            summary = (
                f"Command session {session_id} completed (exit {exit_code})"
                if completed
                else f"Command session {session_id} still running"
            )
            success = (exit_code == 0 and not data.get("timed_out")) if completed else True
            return ToolResult(
                success=success,
                result_summary=summary,
                result_data=data,
                error_message=None if success else data.get("stderr") or summary,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                metadata={
                    "session_id": data.get("session_id"),
                    "status": data.get("status"),
                    "exit_code": data.get("exit_code"),
                    "truncated": data.get("truncated"),
                    "timed_out": data.get("timed_out"),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                result_summary=f"write_stdin error: {str(e)[:100]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        return self._manager._working_dir.is_dir()

    async def close(self) -> None:
        await self._manager.cleanup()
