"""Tool registry for agent tool management.

The registry provides:
- Tool registration and discovery
- OpenAI function schemas for LLM
- Lifecycle management (init, cleanup)
"""

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
                logger.warning(
                    "Tool health check failed", extra={"tool": name, "error": str(e)}
                )
                results[name] = False
        return results

    async def close_all(self) -> None:
        """Close all tools and release resources."""
        for name, tool in self._tools.items():
            try:
                await tool.close()
                logger.debug("Tool closed", extra={"tool": name})
            except Exception as e:
                logger.warning(
                    "Error closing tool", extra={"tool": name, "error": str(e)}
                )


def create_tool_registry(
    config: "ChatConfig",
    calculation_only: bool = False,
) -> ToolRegistry:
    """Factory function to create registry with configured tools.

    Args:
        config: Chat configuration with tool settings.
        calculation_only: If True, tool_choice=python_execute is used (tools still registered).
            Used for calculation queries where we want to force code execution
            without web search distraction.

    Returns:
        Configured ToolRegistry with tools.
    """
    from .python_local import LocalPythonTool
    from .web_extract import WebExtractTool
    from .web_search import WebSearchTool

    registry = ToolRegistry()

    # Get tool configs from chat_config
    parallel_config = getattr(config, "parallel", None)
    python_config = getattr(config, "python", None)

    # Get timeout from config
    timeout = 30
    if python_config:
        timeout = getattr(python_config, "timeout_seconds", 30)

    # Choose Python execution provider based on environment
    # - "daytona": Fast, isolated sandbox (~90ms startup) - recommended for production
    # - "local": Local subprocess - fast but less isolated, use for development
    python_provider = os.environ.get("PYTHON_PROVIDER", "local")

    if python_provider == "daytona":
        from .python_daytona import DaytonaPythonTool

        daytona_api_key = os.environ.get("DAYTONA_API_KEY") or os.environ.get("DAYTONA_API")
        if daytona_api_key:
            registry.register(DaytonaPythonTool(
                api_key=daytona_api_key,
                timeout_seconds=timeout,
            ))
            logger.info("Registered python_execute tool (Daytona sandbox)")
        else:
            # Fallback to local if no API key
            logger.warning(
                "PYTHON_PROVIDER=daytona but DAYTONA_API_KEY not set, falling back to local"
            )
            registry.register(LocalPythonTool(timeout_seconds=timeout))
            logger.info("Registered python_execute tool (local)")
    else:
        registry.register(LocalPythonTool(timeout_seconds=timeout))
        logger.info("Registered python_execute tool (local)")

    # Register web tools if Parallel.ai is configured
    # Note: Even for calculation_only queries, we register web tools because
    # the model might need web_search for reference data/constants.
    # tool_choice=python_execute ensures calculations use python_execute first.
    if parallel_config and parallel_config.api_key:
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
        logger.info("Registered web tools (web_search, web_extract)")

    return registry
