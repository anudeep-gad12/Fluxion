"""Tests for ToolRegistry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.agent.tools.base import ToolResult, ToolSchema
from orchestrator.agent.tools.registry import (
    ToolRegistry,
    create_browser_agent_tool_registry,
)


def create_mock_tool(name: str, is_idempotent: bool = True) -> MagicMock:
    """Create a mock tool for testing.

    Args:
        name: Tool name.
        is_idempotent: Whether tool is idempotent.

    Returns:
        Mock tool implementing BaseTool protocol.
    """
    tool = MagicMock()
    tool.name = name
    tool.schema = ToolSchema(
        name=name,
        description=f"Mock {name} tool",
        parameters={"type": "object", "properties": {}},
        is_idempotent=is_idempotent,
    )
    tool.execute = AsyncMock(
        return_value=ToolResult(
            success=True,
            result_summary="Success",
        )
    )
    tool.health_check = AsyncMock(return_value=True)
    tool.close = AsyncMock()
    return tool


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self):
        """Tool can be registered."""
        registry = ToolRegistry()
        tool = create_mock_tool("test_tool")

        registry.register(tool)

        assert registry.get("test_tool") is tool

    def test_register_duplicate_raises(self):
        """Registering duplicate name raises ValueError."""
        registry = ToolRegistry()
        tool1 = create_mock_tool("test_tool")
        tool2 = create_mock_tool("test_tool")

        registry.register(tool1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)

    def test_get_nonexistent_returns_none(self):
        """Getting nonexistent tool returns None."""
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_get_openai_schemas(self):
        """OpenAI schemas are generated correctly."""
        registry = ToolRegistry()
        registry.register(create_mock_tool("tool1"))
        registry.register(create_mock_tool("tool2"))

        schemas = registry.get_openai_schemas()

        assert len(schemas) == 2
        assert all(s["type"] == "function" for s in schemas)
        names = {s["function"]["name"] for s in schemas}
        assert names == {"tool1", "tool2"}

    def test_openai_schema_structure(self):
        """OpenAI schema has correct structure."""
        registry = ToolRegistry()
        tool = create_mock_tool("web_search")
        tool.schema = ToolSchema(
            name="web_search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        registry.register(tool)

        schemas = registry.get_openai_schemas()

        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_search"
        assert schema["function"]["description"] == "Search the web"
        assert "query" in schema["function"]["parameters"]["properties"]

    def test_is_idempotent_true(self):
        """Idempotent check returns True for idempotent tools."""
        registry = ToolRegistry()
        registry.register(create_mock_tool("idempotent", is_idempotent=True))

        assert registry.is_idempotent("idempotent") is True

    def test_is_idempotent_false(self):
        """Idempotent check returns False for non-idempotent tools."""
        registry = ToolRegistry()
        registry.register(create_mock_tool("non_idempotent", is_idempotent=False))

        assert registry.is_idempotent("non_idempotent") is False

    def test_is_idempotent_nonexistent_returns_false(self):
        """Idempotent check returns False for nonexistent tools."""
        registry = ToolRegistry()
        assert registry.is_idempotent("nonexistent") is False

    def test_tool_names_property(self):
        """tool_names returns list of registered names."""
        registry = ToolRegistry()
        registry.register(create_mock_tool("tool_a"))
        registry.register(create_mock_tool("tool_b"))
        registry.register(create_mock_tool("tool_c"))

        names = registry.tool_names

        assert len(names) == 3
        assert set(names) == {"tool_a", "tool_b", "tool_c"}

    def test_tool_names_empty_registry(self):
        """tool_names returns empty list for empty registry."""
        registry = ToolRegistry()
        assert registry.tool_names == []

    @pytest.mark.asyncio
    async def test_health_check_all_success(self):
        """Health check runs for all tools and returns results."""
        registry = ToolRegistry()
        tool1 = create_mock_tool("tool1")
        tool2 = create_mock_tool("tool2")

        registry.register(tool1)
        registry.register(tool2)

        results = await registry.health_check_all()

        assert results["tool1"] is True
        assert results["tool2"] is True
        tool1.health_check.assert_called_once()
        tool2.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_all_mixed_results(self):
        """Health check handles mixed results."""
        registry = ToolRegistry()
        tool1 = create_mock_tool("tool1")
        tool2 = create_mock_tool("tool2")
        tool2.health_check.return_value = False

        registry.register(tool1)
        registry.register(tool2)

        results = await registry.health_check_all()

        assert results["tool1"] is True
        assert results["tool2"] is False

    @pytest.mark.asyncio
    async def test_health_check_all_handles_exceptions(self):
        """Health check catches exceptions and returns False."""
        registry = ToolRegistry()
        tool = create_mock_tool("failing_tool")
        tool.health_check.side_effect = Exception("Connection failed")

        registry.register(tool)

        results = await registry.health_check_all()

        assert results["failing_tool"] is False

    @pytest.mark.asyncio
    async def test_close_all(self):
        """Close is called on all tools."""
        registry = ToolRegistry()
        tool1 = create_mock_tool("tool1")
        tool2 = create_mock_tool("tool2")

        registry.register(tool1)
        registry.register(tool2)

        await registry.close_all()

        tool1.close.assert_called_once()
        tool2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_all_handles_exceptions(self):
        """Close continues even if a tool raises an exception."""
        registry = ToolRegistry()
        tool1 = create_mock_tool("tool1")
        tool1.close.side_effect = Exception("Close failed")
        tool2 = create_mock_tool("tool2")

        registry.register(tool1)
        registry.register(tool2)

        # Should not raise
        await registry.close_all()

        # Both should be called
        tool1.close.assert_called_once()
        tool2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_all_empty_registry(self):
        """Close on empty registry succeeds."""
        registry = ToolRegistry()
        await registry.close_all()  # Should not raise


class TestBrowserAgentToolRegistry:
    """Tests for browser capability-based tool registration."""

    def test_filesystem_and_bash_capabilities_register_workspace_tools(self, tmp_path):
        """Browser agent capabilities control filesystem and bash tools."""
        config = SimpleNamespace(parallel=None, python=SimpleNamespace(timeout_seconds=30))

        registry = create_browser_agent_tool_registry(
            config,
            {
                "web": False,
                "filesystem": True,
                "bash": True,
                "python": False,
            },
            working_dir=str(tmp_path),
        )

        assert set(registry.tool_names) == {
            "read_file",
            "list_directory",
            "glob",
            "grep",
            "write_file",
            "edit_file",
            "bash",
        }

    def test_python_is_disabled_by_default_for_browser_agent(self, tmp_path):
        """Browser coding agent does not register python unless requested."""
        config = SimpleNamespace(parallel=None, python=SimpleNamespace(timeout_seconds=30))

        registry = create_browser_agent_tool_registry(
            config,
            {
                "web": False,
                "filesystem": True,
                "bash": False,
                "python": False,
            },
            working_dir=str(tmp_path),
        )

        assert "python_execute" not in registry.tool_names
        assert "bash" not in registry.tool_names
