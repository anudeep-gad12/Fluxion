"""Bash tool for shell command execution.

Runs shell commands with timeout and output capture. Requires approval (dangerous).
"""

import asyncio
import os
import signal
import time
from pathlib import Path
from typing import Any

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)

# Maximum output size in characters
_MAX_OUTPUT = 30000
_DEFAULT_TIMEOUT = 300
_MAX_TIMEOUT = 1800


class BashTool:
    """Execute shell commands with timeout and output capture.

    Attributes:
        name: "bash"
        is_idempotent: False
    """

    def __init__(self, working_dir: str = ".") -> None:
        """Initialize bash tool.

        Args:
            working_dir: Initial working directory for commands.
        """
        self._working_dir = Path(working_dir).resolve()
        self._cwd = str(self._working_dir)

    @property
    def name(self) -> str:
        """Tool name."""
        return "bash"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="bash",
            description=(
                "Execute a shell command. Captures stdout and stderr. "
                "Runs in the configured workspace directory. "
                "Use for general local execution: git operations, running tests, build/dev commands, "
                "one-off Python or Node scripts, scripted file edits, curl requests, quick calculations, "
                "and runtime verification. For file edits, use short Python/Node scripts that read the "
                "file, assert expected text exists, write the updated content, and exit nonzero if a "
                "target is missing. "
                "Stay task-focused and avoid destructive commands unless truly required."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 300, max: 1800)",
                        "default": 300,
                    },
                },
                "required": ["command"],
            },
            is_idempotent=False,
            permission_level="dangerous",
        )

    async def execute(
        self,
        command: str,
        timeout: int = _DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a shell command.

        Args:
            command: Shell command to run.
            timeout: Timeout in seconds (max 1800).
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with command output.
        """
        start_time = time.perf_counter()
        timeout = min(timeout, _MAX_TIMEOUT)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )

            stdout_buffer = bytearray()
            stderr_buffer = bytearray()

            async def _drain_stream(
                stream: asyncio.StreamReader | None,
                buffer: bytearray,
            ) -> None:
                if stream is None:
                    return
                while True:
                    chunk = await stream.read(4096)
                    if not chunk:
                        break
                    buffer.extend(chunk)

            try:
                stdout_task = asyncio.create_task(_drain_stream(proc.stdout, stdout_buffer))
                stderr_task = asyncio.create_task(_drain_stream(proc.stderr, stderr_buffer))
                await asyncio.wait_for(proc.wait(), timeout=timeout)
                await asyncio.gather(stdout_task, stderr_task)
            except asyncio.TimeoutError:
                self._terminate_process_group(proc, signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    self._terminate_process_group(proc, signal.SIGKILL)
                    await proc.wait()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                stdout_text = stdout_buffer.decode("utf-8", errors="replace")
                stderr_text = stderr_buffer.decode("utf-8", errors="replace")
                output = "\n".join(
                    part
                    for part in (
                        stdout_text,
                        f"STDERR:\n{stderr_text}" if stderr_text else "",
                    )
                    if part
                )
                truncated = False
                if len(output) > _MAX_OUTPUT:
                    head = output[: _MAX_OUTPUT // 2]
                    tail = output[-(_MAX_OUTPUT // 2):]
                    output = (
                        f"{head}\n\n... (output truncated at {_MAX_OUTPUT} chars; "
                        "showing head and tail) ...\n\n"
                        f"{tail}"
                    )
                    truncated = True
                return ToolResult(
                    success=False,
                    result_summary=(
                        f"Command timed out after {timeout}s"
                        + (" (partial output captured)" if output else "")
                    ),
                    result_data={
                        "command": command,
                        "exit_code": proc.returncode,
                        "stdout": stdout_text[:_MAX_OUTPUT],
                        "stderr": stderr_text[:_MAX_OUTPUT],
                        "output": output if output else "(no output before timeout)",
                        "truncated": truncated,
                        "timed_out": True,
                    },
                    error_message=f"Command timed out after {timeout} seconds: {command[:80]}",
                    duration_ms=duration_ms,
                    metadata={
                        "exit_code": proc.returncode,
                        "truncated": truncated,
                        "timed_out": True,
                    },
                )

            stdout_text = stdout_buffer.decode("utf-8", errors="replace")
            stderr_text = stderr_buffer.decode("utf-8", errors="replace")
            exit_code = proc.returncode

            # Build output
            output = "\n".join(
                part
                for part in (
                    stdout_text,
                    f"STDERR:\n{stderr_text}" if stderr_text else "",
                )
                if part
            )

            # Truncate combined output for model context, preserving full split
            # streams only up to the same hard cap.
            truncated = False
            if len(output) > _MAX_OUTPUT:
                head = output[: _MAX_OUTPUT // 2]
                tail = output[-(_MAX_OUTPUT // 2):]
                output = (
                    f"{head}\n\n... (output truncated at {_MAX_OUTPUT} chars; "
                    "showing head and tail) ...\n\n"
                    f"{tail}"
                )
                truncated = True

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            success = exit_code == 0

            cmd_preview = command[:60] + "..." if len(command) > 60 else command
            if success:
                summary = f"Command succeeded (exit 0): {cmd_preview}"
            else:
                summary = f"Command failed (exit {exit_code}): {cmd_preview}"

            return ToolResult(
                success=success,
                result_summary=summary,
                result_data={
                    "command": command,
                    "exit_code": exit_code,
                    "stdout": stdout_text[:_MAX_OUTPUT],
                    "stderr": stderr_text[:_MAX_OUTPUT],
                    "output": output if output else "(no output)",
                    "truncated": truncated,
                    "timed_out": False,
                },
                error_message=stderr_text[:500] if not success and stderr_text else None,
                duration_ms=duration_ms,
                metadata={
                    "exit_code": exit_code,
                    "truncated": truncated,
                    "timed_out": False,
                },
            )

        except Exception as e:
            logger.error("bash failed", extra={"command": command[:80], "error": str(e)})
            return ToolResult(
                success=False,
                result_summary=f"Bash error: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        """Check if shell is available."""
        try:
            proc = await asyncio.create_subprocess_shell(
                "echo ok",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return b"ok" in stdout
        except Exception:
            return False

    @staticmethod
    def _terminate_process_group(
        proc: asyncio.subprocess.Process,
        sig: signal.Signals,
    ) -> None:
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), sig)
            elif sig == signal.SIGTERM:
                proc.terminate()
            else:
                proc.kill()
        except ProcessLookupError:
            pass

    async def close(self) -> None:
        """No resources to clean up."""
        pass
