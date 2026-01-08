"""Tests for PythonSandboxTool."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys


class TestPythonSandboxToolProperties:
    """Tests for PythonSandboxTool properties."""

    def test_name_property(self):
        """Name is 'python_execute'."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                assert tool.name == "python_execute"

    def test_schema_not_idempotent(self):
        """Schema marks tool as NOT idempotent."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                assert tool.schema.is_idempotent is False

    def test_schema_name(self):
        """Schema name matches tool name."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                assert tool.schema.name == "python_execute"

    def test_schema_has_description(self):
        """Schema has a description."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                assert tool.schema.description
                assert "python" in tool.schema.description.lower()

    def test_schema_parameters(self):
        """Schema has correct parameters."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                params = tool.schema.parameters

                assert params["type"] == "object"
                assert "code" in params["properties"]
                assert "code" in params["required"]


class TestPythonSandboxToolInit:
    """Tests for PythonSandboxTool initialization."""

    def test_raises_without_e2b(self):
        """Raises ImportError if E2B not available."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", False):
            from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

            with pytest.raises(ImportError, match="e2b_code_interpreter"):
                PythonSandboxTool(api_key="test")

    def test_default_metadata(self):
        """Default metadata includes app name."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                assert tool._metadata == {"app": "reasoner"}

    def test_custom_metadata(self):
        """Custom metadata is stored."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(
                    api_key="test",
                    metadata={"app": "custom", "env": "test"},
                    cleanup_on_init=False,
                )
                assert tool._metadata == {"app": "custom", "env": "test"}

    def test_timeout_stored(self):
        """Timeout is stored."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(
                    api_key="test", timeout_seconds=60, cleanup_on_init=False
                )
                assert tool._timeout == 60


class TestPythonSandboxToolExecution:
    """Tests for PythonSandboxTool execution."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Successful execution returns stdout."""
        mock_sandbox = MagicMock()
        mock_execution = MagicMock()
        mock_execution.logs = MagicMock()
        mock_execution.logs.stdout = ["Hello, World!"]
        mock_execution.logs.stderr = []
        mock_execution.error = None
        mock_execution.results = []

        # AsyncSandbox uses async methods
        mock_sandbox.run_code = AsyncMock(return_value=mock_execution)
        mock_sandbox.kill = AsyncMock()

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.AsyncSandbox",
                mock_sandbox_class,
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                result = await tool.execute(code='print("Hello, World!")')

        assert result.success is True
        assert "Hello, World!" in result.result_summary  # Output shown in summary
        assert "Hello, World!" in result.result_data["stdout"]
        assert result.duration_ms is not None

    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Execution with error returns stderr."""
        mock_sandbox = MagicMock()
        mock_execution = MagicMock()
        mock_execution.logs = MagicMock()
        mock_execution.logs.stdout = []
        mock_execution.logs.stderr = ["NameError: name 'undefined' is not defined"]
        mock_execution.error = "NameError: name 'undefined' is not defined"
        mock_execution.results = []

        mock_sandbox.run_code = AsyncMock(return_value=mock_execution)
        mock_sandbox.kill = AsyncMock()

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.AsyncSandbox",
                mock_sandbox_class,
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                result = await tool.execute(code="print(undefined)")

        assert result.success is False
        assert "error" in result.result_summary.lower()
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Timeout returns failure result."""
        mock_sandbox = MagicMock()
        mock_sandbox.kill = AsyncMock()

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.AsyncSandbox",
                mock_sandbox_class,
            ):
                with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                    from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                    tool = PythonSandboxTool(
                        api_key="test", timeout_seconds=1, cleanup_on_init=False
                    )
                    result = await tool.execute(code="import time; time.sleep(100)")

        assert result.success is False
        assert "timed out" in result.result_summary.lower()

    @pytest.mark.asyncio
    async def test_execute_sandbox_killed_on_success(self):
        """Sandbox is killed after successful execution."""
        mock_sandbox = MagicMock()
        mock_execution = MagicMock()
        mock_execution.logs = MagicMock()
        mock_execution.logs.stdout = ["output"]
        mock_execution.logs.stderr = []
        mock_execution.error = None
        mock_execution.results = []

        mock_sandbox.run_code = AsyncMock(return_value=mock_execution)
        mock_sandbox.kill = AsyncMock()

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.AsyncSandbox",
                mock_sandbox_class,
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                await tool.execute(code="print('test')")

        # Verify kill was called (async)
        mock_sandbox.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_e2b_not_available(self):
        """Returns failure when E2B is not available."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.AsyncSandbox", MagicMock()):
                with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                    from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                    tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)

        # Now patch E2B_AVAILABLE to False for execution
        with patch.object(
            sys.modules["orchestrator.agent.tools.python_sandbox"],
            "E2B_AVAILABLE",
            False,
        ):
            with patch.object(
                sys.modules["orchestrator.agent.tools.python_sandbox"], "AsyncSandbox", None
            ):
                result = await tool.execute(code="print('test')")

        assert result.success is False
        assert "not available" in result.result_summary.lower()


class TestPythonSandboxToolCleanup:
    """Tests for PythonSandboxTool cleanup functionality."""

    @pytest.mark.asyncio
    async def test_initialize_runs_cleanup(self):
        """Initialize runs cleanup when cleanup_on_init is True."""
        mock_sandbox_class = MagicMock()
        mock_sandbox_class.list.return_value = []

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.Sandbox", mock_sandbox_class
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=True)
                await tool.initialize()

                assert tool._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_skips_cleanup_when_disabled(self):
        """Initialize skips cleanup when cleanup_on_init is False."""
        mock_sandbox_class = MagicMock()

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.Sandbox", mock_sandbox_class
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                await tool.initialize()

                assert tool._initialized is True
                # list should not be called when cleanup is disabled
                mock_sandbox_class.list.assert_not_called()


class TestPythonSandboxToolHealthCheck:
    """Tests for PythonSandboxTool health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check returns True when sandbox can be created."""
        mock_sandbox = MagicMock()
        mock_sandbox.kill = AsyncMock()

        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = AsyncMock(return_value=mock_sandbox)

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.AsyncSandbox",
                mock_sandbox_class,
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                result = await tool.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Health check returns False when sandbox creation fails."""
        mock_sandbox_class = MagicMock()
        mock_sandbox_class.create = AsyncMock(side_effect=Exception("API error"))

        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch(
                "orchestrator.agent.tools.python_sandbox.AsyncSandbox",
                mock_sandbox_class,
            ):
                from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)
                result = await tool.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_e2b_not_available(self):
        """Health check returns False when E2B not available."""
        with patch("orchestrator.agent.tools.python_sandbox.E2B_AVAILABLE", True):
            with patch("orchestrator.agent.tools.python_sandbox.AsyncSandbox", MagicMock()):
                with patch("orchestrator.agent.tools.python_sandbox.Sandbox", MagicMock()):
                    from orchestrator.agent.tools.python_sandbox import PythonSandboxTool

                    tool = PythonSandboxTool(api_key="test", cleanup_on_init=False)

        # Patch E2B_AVAILABLE to False
        with patch.object(
            sys.modules["orchestrator.agent.tools.python_sandbox"],
            "E2B_AVAILABLE",
            False,
        ):
            result = await tool.health_check()

        assert result is False
