"""Agent module for web research agent.

This module provides:
- Tool protocol and implementations
- Tool registry for management
- Factory functions for setup
"""

from orchestrator.agent.tools import (
    BaseTool,
    PythonSandboxTool,
    ToolError,
    ToolExecutionError,
    ToolRegistry,
    ToolResult,
    ToolSchema,
    ToolTimeoutError,
    WebExtractTool,
    WebSearchTool,
    create_tool_registry,
)

__all__ = [
    # Base types
    "BaseTool",
    "ToolError",
    "ToolExecutionError",
    "ToolResult",
    "ToolSchema",
    "ToolTimeoutError",
    # Registry
    "ToolRegistry",
    "create_tool_registry",
    # Tools
    "WebSearchTool",
    "WebExtractTool",
    "PythonSandboxTool",
]
