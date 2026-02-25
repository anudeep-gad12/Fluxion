"""Base types and protocols for agent tools.

All tools must implement the BaseTool protocol to ensure consistent
behavior across web_search, web_extract, and python_execute tools.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

# =============================================================================
# Exceptions
# =============================================================================


class ToolError(Exception):
    """Base exception for tool errors."""

    pass


class ToolTimeoutError(ToolError):
    """Raised when tool execution times out."""

    pass


class ToolExecutionError(ToolError):
    """Raised when tool execution fails."""

    pass


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class ToolResult:
    """Result from tool execution.

    Attributes:
        success: Whether execution succeeded.
        result_summary: 1-line summary for DB storage (prevents WAL bloat).
        result_data: Full result data (NOT stored in DB, used in-memory only).
        error_message: Error message if failed.
        duration_ms: Execution time in milliseconds.
        metadata: Optional additional metadata.
    """

    success: bool
    result_summary: str  # 1-line only - stored in DB
    result_data: Optional[Any] = None  # Full data - in-memory only
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSchema:
    """OpenAI function schema for tool.

    Attributes:
        name: Tool name (web_search, web_extract, python_execute).
        description: Tool description for LLM.
        parameters: JSON Schema for parameters.
        is_idempotent: Whether tool is safe to retry on crash.
        permission_level: "auto" (read-only), "confirm" (write), "dangerous" (shell).
    """

    name: str
    description: str
    parameters: Dict[str, Any]
    is_idempotent: bool = True
    permission_level: str = "auto"


# =============================================================================
# Tool Protocol
# =============================================================================


@runtime_checkable
class BaseTool(Protocol):
    """Protocol for agent tools.

    All tools must implement this interface for consistent behavior.
    This follows the same pattern as LLMProvider in providers/base.py.
    """

    @property
    def name(self) -> str:
        """Tool name (e.g., 'web_search').

        Returns:
            Tool name string.
        """
        ...

    @property
    def schema(self) -> ToolSchema:
        """OpenAI function schema for this tool.

        Returns:
            ToolSchema with name, description, parameters, and idempotency flag.
        """
        ...

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments matching schema.

        Returns:
            ToolResult with success/failure and summary.
        """
        ...

    async def health_check(self) -> bool:
        """Check if tool is available and healthy.

        Returns:
            True if healthy, False otherwise.
        """
        ...

    async def close(self) -> None:
        """Clean up tool resources."""
        ...
