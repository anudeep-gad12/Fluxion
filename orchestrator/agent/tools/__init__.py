"""Agent tools package.

This package provides tools for the web research agent:
- web_search: Search the web using Parallel.ai
- web_extract: Extract content from URLs using Parallel.ai
- python_execute: Execute Python code in E2B sandbox

And filesystem/shell tools for the CLI coding assistant:
- read_file: Read file contents with line numbers
- list_directory: List directory contents in tree format
- glob: Find files matching glob patterns
- grep: Search file contents with regex
- write_file: Create or overwrite files
- edit_file: Exact string replacement editing
- bash: Execute shell commands
"""

from orchestrator.agent.tools.base import (
    BaseTool,
    ToolError,
    ToolExecutionError,
    ToolResult,
    ToolSchema,
    ToolTimeoutError,
)
from orchestrator.agent.tools.bash_tool import BashTool
from orchestrator.agent.tools.edit_file import EditFileTool
from orchestrator.agent.tools.glob_tool import GlobTool
from orchestrator.agent.tools.grep_tool import GrepTool
from orchestrator.agent.tools.list_directory import ListDirectoryTool
from orchestrator.agent.tools.read_file import ReadFileTool
from orchestrator.agent.tools.registry import ToolRegistry, create_tool_registry
from orchestrator.agent.tools.web_extract import WebExtractTool
from orchestrator.agent.tools.web_search import WebSearchTool
from orchestrator.agent.tools.write_file import WriteFileTool

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
    # Web tools
    "WebSearchTool",
    "WebExtractTool",
    "PythonSandboxTool",
    # Filesystem tools
    "ReadFileTool",
    "ListDirectoryTool",
    "GlobTool",
    "GrepTool",
    "WriteFileTool",
    "EditFileTool",
    "BashTool",
]
