"""Tool registry for coding-agent tool management."""

import os
from typing import TYPE_CHECKING, Dict, List, Optional

from orchestrator.logging_config import get_logger

from .base import BaseTool

if TYPE_CHECKING:
    from orchestrator.config import ChatConfig

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for managing agent tools.

    Example:
        registry = ToolRegistry()
        registry.register(WebSearchTool(config))
        registry.register(WebExtractTool(config))

        # Get tool by name
        tool = registry.get("web_search")

        # Get all schemas for LLM
        schemas = registry.get_openai_schemas()
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool.

        Args:
            tool: Tool instance implementing BaseTool protocol.

        Raises:
            ValueError: If tool with same name already registered.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")

        self._tools[tool.name] = tool
        logger.info("Tool registered", extra={"tool": tool.name})

    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name.

        Args:
            name: Tool name.

        Returns:
            Tool instance or None if not found.
        """
        return self._tools.get(name)

    def get_openai_schemas(self) -> List[Dict]:
        """Get all tool schemas in OpenAI function format.

        Returns:
            List of OpenAI function definitions for LLM.
        """
        schemas = []
        for tool in self._tools.values():
            schema = tool.schema
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": schema.name,
                        "description": schema.description,
                        "parameters": schema.parameters,
                    },
                }
            )
        return schemas

    def is_idempotent(self, name: str) -> bool:
        """Check if tool is idempotent (safe to retry).

        Args:
            name: Tool name.

        Returns:
            True if idempotent, False otherwise.
        """
        tool = self._tools.get(name)
        if tool is None:
            return False
        return tool.schema.is_idempotent

    @property
    def tool_names(self) -> List[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all tools.

        Returns:
            Dict mapping tool name to health status.
        """
        results = {}
        for name, tool in self._tools.items():
            try:
                results[name] = await tool.health_check()
            except Exception as e:
                logger.warning("Tool health check failed", extra={"tool": name, "error": str(e)})
                results[name] = False
        return results

    async def close_all(self) -> None:
        """Close all tools and release resources."""
        for name, tool in self._tools.items():
            try:
                await tool.close()
                logger.debug("Tool closed", extra={"tool": name})
            except Exception as e:
                logger.warning("Error closing tool", extra={"tool": name, "error": str(e)})


def create_browser_agent_tool_registry(
    config: "ChatConfig",
    capabilities: dict,
    working_dir: Optional[str] = None,
    python_provider: Optional[str] = None,
) -> ToolRegistry:
    """Create the browser-first agent tool registry from capability flags.

    This is intentionally not tied to CLI/TUI behavior or product profiles.
    The browser decides which tool families are available for a run.
    """
    from .web_extract import WebExtractTool
    from .web_search import WebSearchTool

    registry = ToolRegistry()
    parallel_config = getattr(config, "parallel", None)

    if capabilities.get("web", True) and parallel_config and parallel_config.api_key:
        registry.register(
            WebSearchTool(
                base_url=parallel_config.base_url,
                api_key=parallel_config.api_key,
                max_results=parallel_config.search.max_results,
                timeout_ms=parallel_config.search.timeout_ms,
            )
        )
        registry.register(
            WebExtractTool(
                base_url=parallel_config.base_url,
                api_key=parallel_config.api_key,
                max_urls=parallel_config.extract.max_urls_per_request,
                timeout_ms=parallel_config.extract.timeout_ms,
            )
        )

    if capabilities.get("python", False):
        from .python_local import LocalPythonTool

        python_config = getattr(config, "python", None)
        timeout = getattr(python_config, "timeout_seconds", 30) if python_config else 30
        resolved_provider = python_provider or os.environ.get("PYTHON_PROVIDER", "local")
        if resolved_provider == "daytona":
            from .python_daytona import DaytonaPythonTool

            daytona_api_key = os.environ.get("DAYTONA_API_KEY") or os.environ.get("DAYTONA_API")
            if daytona_api_key:
                registry.register(
                    DaytonaPythonTool(api_key=daytona_api_key, timeout_seconds=timeout)
                )
            else:
                registry.register(LocalPythonTool(timeout_seconds=timeout))
        else:
            registry.register(LocalPythonTool(timeout_seconds=timeout))

    if capabilities.get("filesystem", False):
        wd = working_dir or os.getcwd()
        from .edit_file import EditFileTool
        from .glob_tool import GlobTool
        from .grep_tool import GrepTool
        from .list_directory import ListDirectoryTool
        from .read_file import ReadFileTool
        from .view_image import ViewImageTool
        from .write_file import WriteFileTool

        registry.register(ReadFileTool(working_dir=wd))
        registry.register(ViewImageTool(working_dir=wd))
        registry.register(ListDirectoryTool(working_dir=wd))
        registry.register(GlobTool(working_dir=wd))
        registry.register(GrepTool(working_dir=wd))
        registry.register(WriteFileTool(working_dir=wd))
        registry.register(EditFileTool(working_dir=wd))

    if capabilities.get("bash", False):
        wd = working_dir or os.getcwd()
        from .bash_tool import BashTool

        registry.register(BashTool(working_dir=wd))

    logger.info(
        "Browser agent tool registry created",
        extra={
            "capabilities": capabilities,
            "working_dir": working_dir,
            "tools": registry.tool_names,
        },
    )
    return registry
