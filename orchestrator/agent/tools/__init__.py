"""Agent tools package.

This package provides tools for the web research agent:
- web_search: Search the web using Parallel.ai
- web_extract: Extract content from URLs using Parallel.ai
- python_execute: Execute Python code in E2B sandbox
"""

from orchestrator.agent.tools.base import (
    BaseTool,
    ToolError,
    ToolExecutionError,
    ToolResult,
    ToolSchema,
    ToolTimeoutError,
)
from orchestrator.agent.tools.registry import ToolRegistry, create_tool_registry
from orchestrator.agent.tools.web_extract import WebExtractTool
from orchestrator.agent.tools.web_search import WebSearchTool

# PythonSandboxTool import may fail if e2b not installed
try:
    from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

    _SANDBOX_AVAILABLE = True
except ImportError:
    PythonSandboxTool = None  # type: ignore
    _SANDBOX_AVAILABLE = False

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
