"""Python code execution in E2B sandbox.

This tool executes Python code in an isolated E2B sandbox.
It is NOT IDEMPOTENT - requires hint injection on crash recovery.

CRITICAL: Includes session cleanup on startup for zombie sessions.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)

# E2B SDK import (handle import error gracefully)
try:
    from e2b_code_interpreter import Sandbox

    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False
    Sandbox = None  # type: ignore


class PythonSandboxTool:
    """Python execution in E2B sandbox.

    Attributes:
        name: "python_execute"
        is_idempotent: False (requires hint injection on crash)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        template: str = "code-interpreter",  # Must use code-interpreter for port 49999
        timeout_seconds: int = 30,
        metadata: Optional[Dict[str, str]] = None,
        cleanup_on_init: bool = True,
        stale_session_minutes: int = 10,
    ) -> None:
        """Initialize Python sandbox tool.

        Args:
            api_key: E2B API key.
            template: E2B sandbox template.
            timeout_seconds: Execution timeout.
            metadata: Sandbox metadata for identification.
            cleanup_on_init: Whether to cleanup stale sessions on init.
            stale_session_minutes: Age threshold for stale sessions.

        Raises:
            ImportError: If e2b_code_interpreter is not installed.
        """
        if not E2B_AVAILABLE:
            raise ImportError(
                "e2b_code_interpreter package not installed. "
                "Install with: pip install e2b-code-interpreter"
            )

        self._api_key = api_key
        self._template = template
        self._timeout = timeout_seconds
        self._metadata = metadata or {"app": "reasoner"}
        self._stale_session_minutes = stale_session_minutes
        self._initialized = False
        self._cleanup_on_init = cleanup_on_init

    @property
    def name(self) -> str:
        """Tool name."""
        return "python_execute"

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema."""
        return ToolSchema(
            name="python_execute",
            description="Execute Python code in an isolated sandbox. Use for calculations, data processing, or any computation.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                },
                "required": ["code"],
            },
            is_idempotent=False,  # CRITICAL: Not safe to retry blindly
        )

    async def initialize(self) -> None:
        """Initialize tool and cleanup stale sessions.

        Call this on server startup before first use.
        """
        if self._cleanup_on_init:
            await self._cleanup_stale_sessions()
        self._initialized = True
        logger.info("Python sandbox tool initialized")

    async def _cleanup_stale_sessions(self) -> None:
        """Clean up zombie E2B sessions from previous crashes.

        This MUST be called on server startup to prevent orphan sessions.
        """
        if not E2B_AVAILABLE or Sandbox is None:
            return

        try:
            # List all active sessions
            sandboxes = await asyncio.to_thread(
                Sandbox.list, api_key=self._api_key
            )

            cleaned = 0
            now = datetime.now(timezone.utc)

            for sandbox in sandboxes:
                # Check if this sandbox belongs to our app
                sandbox_metadata = getattr(sandbox, "metadata", {}) or {}
                if sandbox_metadata.get("app") != self._metadata.get("app"):
                    continue

                # Check sandbox age
                started_at = getattr(sandbox, "started_at", None)
                if started_at:
                    # started_at might be a timestamp or datetime
                    if isinstance(started_at, (int, float)):
                        started_at = datetime.fromtimestamp(started_at, tz=timezone.utc)
                    elif not started_at.tzinfo:
                        started_at = started_at.replace(tzinfo=timezone.utc)

                    age_minutes = (now - started_at).total_seconds() / 60
                    if age_minutes > self._stale_session_minutes:
                        logger.info(
                            "Cleaning up stale E2B sandbox",
                            extra={
                                "sandbox_id": sandbox.sandbox_id,
                                "age_minutes": round(age_minutes, 1),
                            },
                        )
                        try:
                            await asyncio.to_thread(sandbox.kill)
                            cleaned += 1
                        except Exception as e:
                            logger.warning(
                                "Failed to kill stale sandbox",
                                extra={"sandbox_id": sandbox.sandbox_id, "error": str(e)},
                            )

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} stale E2B sandboxes")

        except Exception as e:
            # Non-fatal - log and continue
            logger.warning(f"E2B cleanup failed (non-fatal): {e}")

    async def execute(self, code: str, **kwargs: Any) -> ToolResult:
        """Execute Python code in sandbox.

        Args:
            code: Python code to execute.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with stdout/stderr.
        """
        if not E2B_AVAILABLE or Sandbox is None:
            return ToolResult(
                success=False,
                result_summary="E2B not available",
                error_message="e2b_code_interpreter package not installed",
                duration_ms=0,
            )

        start_time = time.perf_counter()
        max_retries = 3  # Increased from 2 - E2B can be flaky
        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            sandbox = None
            try:
                # Create sandbox using Sandbox.create() - the constructor doesn't accept api_key
                sandbox = await asyncio.to_thread(
                    Sandbox.create,
                    template=self._template,
                    timeout=self._timeout,
                    metadata=self._metadata,
                    api_key=self._api_key,
                )

                # Execute code with timeout
                execution = await asyncio.wait_for(
                    asyncio.to_thread(sandbox.run_code, code),
                    timeout=self._timeout,
                )

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # Extract output from execution results
                stdout_parts = []
                stderr_parts = []
                has_error = False

                # Process execution results
                if hasattr(execution, "logs"):
                    if hasattr(execution.logs, "stdout"):
                        stdout_parts.extend(execution.logs.stdout)
                    if hasattr(execution.logs, "stderr"):
                        stderr_parts.extend(execution.logs.stderr)

                # Check for execution error
                if hasattr(execution, "error") and execution.error:
                    has_error = True
                    stderr_parts.append(str(execution.error))

                stdout = "".join(stdout_parts) if stdout_parts else ""
                stderr = "".join(stderr_parts) if stderr_parts else ""

                # Also check results for output
                if hasattr(execution, "results"):
                    for result in execution.results:
                        if hasattr(result, "text") and result.text:
                            stdout += result.text + "\n"

                # 1-line summary
                if has_error or stderr:
                    result_summary = f"Execution completed with errors ({len(stderr)} chars stderr)"
                else:
                    result_summary = f"Execution successful ({len(stdout)} chars output)"

                return ToolResult(
                    success=not has_error,
                    result_summary=result_summary,
                    result_data={
                        "stdout": stdout,
                        "stderr": stderr,
                        "error": str(execution.error) if hasattr(execution, "error") and execution.error else None,
                    },
                    error_message=stderr if has_error else None,
                    duration_ms=duration_ms,
                )

            except asyncio.TimeoutError:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                return ToolResult(
                    success=False,
                    result_summary=f"Execution timed out after {self._timeout}s",
                    error_message="Execution timed out",
                    duration_ms=duration_ms,
                )
            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check if this is a transient E2B error that can be retried
                is_retryable = (
                    "port is not open" in error_str
                    or '"code":502' in error_str
                    or "502" in error_str
                )

                if is_retryable and attempt < max_retries:
                    # Exponential backoff: 2s, 4s, 8s
                    delay = 2 * (2 ** attempt)
                    logger.warning(
                        "E2B sandbox transient error, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "delay_seconds": delay,
                            "error": error_str[:200],
                        },
                    )
                    # Clean up failed sandbox before retry
                    if sandbox:
                        try:
                            await asyncio.to_thread(sandbox.kill)
                        except Exception:
                            pass
                    await asyncio.sleep(delay)  # Exponential backoff
                    continue

                # Non-retryable error or retries exhausted
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.error("Python execution failed", extra={"error": error_str})
                return ToolResult(
                    success=False,
                    result_summary="Execution failed with error",
                    error_message=error_str,
                    duration_ms=duration_ms,
                )
            finally:
                # CRITICAL: Always clean up sandbox after successful execution
                if sandbox:
                    try:
                        await asyncio.to_thread(sandbox.kill)
                    except Exception as e:
                        logger.warning(f"Failed to kill sandbox: {e}")

        # Should not reach here, but handle edge case
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return ToolResult(
            success=False,
            result_summary="Execution failed after retries",
            error_message=str(last_error) if last_error else "Unknown error",
            duration_ms=duration_ms,
        )

    async def health_check(self) -> bool:
        """Check if E2B API is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        if not E2B_AVAILABLE or Sandbox is None:
            return False

        try:
            # Quick sandbox creation/teardown test
            sandbox = await asyncio.to_thread(
                Sandbox.create,
                timeout=10,
                metadata={"app": "health_check"},
                api_key=self._api_key,
            )
            await asyncio.to_thread(sandbox.kill)
            return True
        except Exception as e:
            logger.warning(f"E2B health check failed: {e}")
            return False

    async def close(self) -> None:
        """Cleanup (sessions are cleaned per-execution)."""
        # Final cleanup of any lingering sessions
        if self._initialized:
            await self._cleanup_stale_sessions()
