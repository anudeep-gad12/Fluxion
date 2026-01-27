"""Python execution via Daytona sandbox.

Daytona provides fast (~90ms startup), isolated Python execution.
Use this in production for secure code execution.
"""

import asyncio
import os
import time
from typing import Any, Optional

from orchestrator.logging_config import get_logger

from .base import ToolResult, ToolSchema

logger = get_logger(__name__)


class DaytonaPythonTool:
    """Python execution via Daytona sandbox.

    Fast, isolated execution for production use.
    Sandboxes are created per-execution and cleaned up after.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: int = 30,
    ) -> None:
        """Initialize Daytona Python tool.

        Args:
            api_key: Daytona API key. Falls back to DAYTONA_API_KEY or DAYTONA_API env var.
            timeout_seconds: Execution timeout.
        """
        self._api_key = api_key or os.environ.get("DAYTONA_API_KEY") or os.environ.get("DAYTONA_API")
        self._timeout = timeout_seconds
        self._client = None

    def _get_client(self):
        """Lazy initialization of Daytona client."""
        if self._client is None:
            from daytona_sdk import Daytona, DaytonaConfig

            self._client = Daytona(DaytonaConfig(api_key=self._api_key))
        return self._client

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
                "Execute Python code in an isolated sandbox. "
                "IMPORTANT: Always provide the 'code' argument with your Python code. "
                "Use for calculations, data processing, simulations. Returns stdout/stderr."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "REQUIRED: Python code to execute. Must include actual code, not empty. Use print() for output.",
                    },
                },
                "required": ["code"],
            },
            is_idempotent=True,  # Safe to retry - each execution is isolated
        )

    async def execute(self, code: str, **kwargs: Any) -> ToolResult:
        """Execute Python code in Daytona sandbox.

        Args:
            code: Python code to execute.
            **kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with stdout/stderr.
        """
        start_time = time.perf_counter()
        sandbox = None
        sandbox_id = None

        try:
            # Create sandbox and execute code
            # Daytona SDK is synchronous, so run in thread pool
            def run_in_sandbox():
                client = self._get_client()
                sb = client.create()

                # Extract sandbox ID for logging
                sb_id = getattr(sb, 'id', None) or getattr(sb, 'sandbox_id', None) or 'unknown'

                logger.info(
                    "Daytona sandbox created",
                    extra={
                        "sandbox_id": sb_id,
                        "code_preview": code[:100] + "..." if len(code) > 100 else code,
                        "code_length": len(code),
                    }
                )

                try:
                    response = sb.process.code_run(code, timeout=self._timeout)
                    return sb, sb_id, response
                except Exception as e:
                    logger.error(
                        "Daytona code execution failed",
                        extra={"sandbox_id": sb_id, "error": str(e)}
                    )
                    client.delete(sb)
                    raise

            sandbox, sandbox_id, response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, run_in_sandbox),
                timeout=self._timeout + 10,  # Extra buffer for sandbox creation
            )

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Extract output
            stdout = response.result or ""
            exit_code = response.exit_code if hasattr(response, "exit_code") else 0
            has_error = exit_code != 0

            if has_error:
                result_summary = f"Execution failed (exit code {exit_code})\n{stdout}"
                logger.warning(
                    "Daytona execution failed with non-zero exit code",
                    extra={
                        "sandbox_id": sandbox_id,
                        "exit_code": exit_code,
                        "duration_ms": duration_ms,
                        "output_preview": stdout[:200] if stdout else None,
                    }
                )
            else:
                result_summary = stdout.strip() if stdout.strip() else "(no output)"
                logger.info(
                    "Daytona execution completed successfully",
                    extra={
                        "sandbox_id": sandbox_id,
                        "duration_ms": duration_ms,
                        "output_length": len(stdout),
                    }
                )

            return ToolResult(
                success=not has_error,
                result_summary=result_summary[:500],  # Limit for DB storage
                result_data={
                    "stdout": stdout,
                    "stderr": "",
                    "exit_code": exit_code,
                },
                error_message=stdout if has_error else None,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                "Daytona execution timed out",
                extra={
                    "sandbox_id": sandbox_id,
                    "timeout": self._timeout,
                    "duration_ms": duration_ms
                },
            )
            return ToolResult(
                success=False,
                result_summary=f"Execution timed out after {self._timeout}s",
                error_message="Execution timed out",
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "Daytona execution failed",
                extra={
                    "sandbox_id": sandbox_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms
                },
            )
            return ToolResult(
                success=False,
                result_summary="Execution failed with error",
                error_message=str(e),
                duration_ms=duration_ms,
            )

        finally:
            # Always clean up sandbox
            if sandbox is not None:
                try:
                    logger.info(
                        "Attempting to delete Daytona sandbox",
                        extra={"sandbox_id": sandbox_id}
                    )

                    def cleanup():
                        client = self._get_client()
                        client.delete(sandbox)

                    await asyncio.get_event_loop().run_in_executor(None, cleanup)

                    logger.info(
                        "Daytona sandbox deleted successfully",
                        extra={"sandbox_id": sandbox_id}
                    )
                except Exception as e:
                    logger.error(
                        "Failed to delete Daytona sandbox",
                        extra={
                            "sandbox_id": sandbox_id,
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )

    async def health_check(self) -> bool:
        """Check if Daytona is available."""
        if not self._api_key:
            logger.warning("Daytona API key not configured")
            return False

        try:
            result = await self.execute("print('ok')")
            return result.success
        except Exception as e:
            logger.warning("Daytona health check failed", extra={"error": str(e)})
            return False

    async def initialize(self) -> None:
        """Initialize Daytona client."""
        if self._api_key:
            logger.info("Daytona Python tool initialized")
        else:
            logger.warning("Daytona API key not set - tool will fail on execute")

    async def close(self) -> None:
        """Clean up Daytona client."""
        self._client = None
