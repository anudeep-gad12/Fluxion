"""Local Python execution as fallback when E2B fails.

This executes Python in a local subprocess - fast but less isolated.
Use for simple calculations when E2B is unavailable.
"""

import asyncio
import subprocess
import sys
import time
from typing import Any

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)


class LocalPythonTool:
    """Local Python execution via subprocess.

    Fast fallback for when E2B sandbox is unavailable.
    Less secure than E2B but reliable for math calculations.
    """

    def __init__(self, timeout_seconds: int = 30) -> None:
        """Initialize local Python tool.

        Args:
            timeout_seconds: Execution timeout.
        """
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        """Tool name."""
        return "python_execute"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="python_execute",
            description=(
                "Execute Python code for calculations. Use for:\n"
                "- Physics calculations (kinetic energy, momentum, etc.)\n"
                "- Mathematical computations\n"
                "- Unit conversions\n"
                "Returns stdout and stderr."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Use print() to show results.",
                    },
                },
                "required": ["code"],
            },
            is_idempotent=True,  # Safe to retry - stateless execution
        )

    async def execute(self, code: str, **kwargs: Any) -> ToolResult:
        """Execute Python code locally.

        Args:
            code: Python code to execute.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with stdout/stderr.
        """
        start_time = time.perf_counter()

        try:
            # Run in subprocess with timeout
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                return ToolResult(
                    success=False,
                    result_summary=f"Execution timed out after {self._timeout}s",
                    error_message="Execution timed out",
                    duration_ms=duration_ms,
                )

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            has_error = process.returncode != 0

            if has_error:
                result_summary = f"Execution failed (exit code {process.returncode})\n{stderr}"
            else:
                # Include actual output in summary for UI display
                result_summary = stdout.strip() if stdout.strip() else "(no output)"

            return ToolResult(
                success=not has_error,
                result_summary=result_summary,
                result_data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": process.returncode,
                },
                error_message=stderr if has_error else None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Local Python execution failed", extra={"error": str(e)})
            return ToolResult(
                success=False,
                result_summary="Execution failed with error",
                error_message=str(e),
                duration_ms=duration_ms,
            )

    async def health_check(self) -> bool:
        """Check if local Python works."""
        result = await self.execute("print('ok')")
        return result.success

    async def initialize(self) -> None:
        """No initialization needed for local execution."""
        logger.info("Local Python tool initialized")

    async def close(self) -> None:
        """No cleanup needed."""
        pass
