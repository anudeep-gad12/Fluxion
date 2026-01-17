"""Tests for tool base types."""

import pytest

from orchestrator.agent.tools.base import (
    BaseTool,
    ToolError,
    ToolExecutionError,
    ToolResult,
    ToolSchema,
    ToolTimeoutError,
)


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_success_result(self):
        """Success result has correct fields."""
        result = ToolResult(
            success=True,
            result_summary="Found 10 results",
            result_data={"results": []},
        )
        assert result.success is True
        assert result.result_summary == "Found 10 results"
        assert result.result_data == {"results": []}
        assert result.error_message is None
        assert result.duration_ms is None
        assert result.metadata == {}

    def test_failure_result(self):
        """Failure result has error message."""
        result = ToolResult(
            success=False,
            result_summary="Search failed",
            error_message="Connection timeout",
        )
        assert result.success is False
        assert result.result_summary == "Search failed"
        assert result.error_message == "Connection timeout"
        assert result.result_data is None

    def test_result_with_duration(self):
        """Result tracks execution duration."""
        result = ToolResult(
            success=True,
            result_summary="Completed",
            duration_ms=150,
        )
        assert result.duration_ms == 150

    def test_result_with_metadata(self):
        """Result can include metadata."""
        result = ToolResult(
            success=True,
            result_summary="Completed",
            metadata={"retries": 2, "source": "cache"},
        )
        assert result.metadata == {"retries": 2, "source": "cache"}

    def test_default_metadata_is_empty_dict(self):
        """Default metadata is empty dict, not None."""
        result = ToolResult(success=True, result_summary="Test")
        assert result.metadata == {}
        assert isinstance(result.metadata, dict)


class TestToolSchema:
    """Tests for ToolSchema."""

    def test_idempotent_default(self):
        """Schema is idempotent by default."""
        schema = ToolSchema(
            name="test",
            description="Test tool",
            parameters={},
        )
        assert schema.is_idempotent is True

    def test_non_idempotent_flag(self):
        """Schema can be marked non-idempotent."""
        schema = ToolSchema(
            name="python_execute",
            description="Execute Python code",
            parameters={"type": "object"},
            is_idempotent=False,
        )
        assert schema.is_idempotent is False

    def test_schema_fields(self):
        """Schema has all required fields."""
        schema = ToolSchema(
            name="web_search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        )
        assert schema.name == "web_search"
        assert schema.description == "Search the web"
        assert "query" in schema.parameters["properties"]


class TestToolExceptions:
    """Tests for tool exceptions."""

    def test_tool_error_is_base_exception(self):
        """ToolError is the base exception."""
        error = ToolError("Something went wrong")
        assert isinstance(error, Exception)
        assert str(error) == "Something went wrong"

    def test_timeout_error_inherits_from_tool_error(self):
        """ToolTimeoutError inherits from ToolError."""
        error = ToolTimeoutError("Timed out after 30s")
        assert isinstance(error, ToolError)
        assert isinstance(error, Exception)

    def test_execution_error_inherits_from_tool_error(self):
        """ToolExecutionError inherits from ToolError."""
        error = ToolExecutionError("API returned 500")
        assert isinstance(error, ToolError)
        assert isinstance(error, Exception)

    def test_can_catch_specific_exceptions(self):
        """Can catch specific exception types."""
        with pytest.raises(ToolTimeoutError):
            raise ToolTimeoutError("timeout")

        with pytest.raises(ToolExecutionError):
            raise ToolExecutionError("execution failed")

    def test_can_catch_all_as_tool_error(self):
        """Can catch all tool errors as ToolError."""
        errors = [
            ToolError("base"),
            ToolTimeoutError("timeout"),
            ToolExecutionError("exec"),
        ]
        for error in errors:
            with pytest.raises(ToolError):
                raise error


class TestBaseToolProtocol:
    """Tests for BaseTool protocol."""

    def test_protocol_is_runtime_checkable(self):
        """BaseTool protocol can be checked at runtime."""

        class MockTool:
            @property
            def name(self) -> str:
                return "mock"

            @property
            def schema(self) -> ToolSchema:
                return ToolSchema(
                    name="mock",
                    description="Mock tool",
                    parameters={},
                )

            async def execute(self, **kwargs):
                return ToolResult(success=True, result_summary="Done")

            async def health_check(self) -> bool:
                return True

            async def close(self) -> None:
                pass

        tool = MockTool()
        assert isinstance(tool, BaseTool)

    def test_incomplete_implementation_fails_check(self):
        """Incomplete implementations fail isinstance check."""

        class IncompleteTool:
            @property
            def name(self) -> str:
                return "incomplete"

            # Missing schema, execute, health_check, close

        tool = IncompleteTool()
        assert not isinstance(tool, BaseTool)
