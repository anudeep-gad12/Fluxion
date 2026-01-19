"""Tests for DaytonaPythonTool."""

import asyncio
import pytest
from unittest.mock import MagicMock, patch


class TestDaytonaPythonToolProperties:
    """Tests for DaytonaPythonTool properties."""

    def test_name_property(self):
        """Name is 'python_execute'."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test-key")
            assert tool.name == "python_execute"

    def test_schema_is_idempotent(self):
        """Schema marks tool as idempotent (each execution is isolated)."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test-key")
            assert tool.schema.is_idempotent is True

    def test_schema_name(self):
        """Schema name matches tool name."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test-key")
            assert tool.schema.name == "python_execute"

    def test_schema_has_description(self):
        """Schema has a description."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test-key")
            assert tool.schema.description
            assert "python" in tool.schema.description.lower()

    def test_schema_parameters(self):
        """Schema has correct parameters."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test-key")
            params = tool.schema.parameters

            assert params["type"] == "object"
            assert "code" in params["properties"]
            assert "code" in params["required"]


class TestDaytonaPythonToolInit:
    """Tests for DaytonaPythonTool initialization."""

    def test_api_key_from_arg(self):
        """API key can be passed as argument."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="my-api-key")
            assert tool._api_key == "my-api-key"

    def test_api_key_from_env(self):
        """API key falls back to environment variable."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch.dict("os.environ", {"DAYTONA_API_KEY": "env-api-key"}):
                from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                tool = DaytonaPythonTool()
                assert tool._api_key == "env-api-key"

    def test_timeout_stored(self):
        """Timeout is stored."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test", timeout_seconds=60)
            assert tool._timeout == 60

    def test_default_timeout(self):
        """Default timeout is 30 seconds."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test")
            assert tool._timeout == 30

    def test_client_lazy_init(self):
        """Client is not initialized until needed."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test")
            assert tool._client is None


class TestDaytonaPythonToolExecution:
    """Tests for DaytonaPythonTool execution."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Successful execution returns stdout."""
        mock_sandbox = MagicMock()
        mock_response = MagicMock()
        mock_response.result = "Hello, World!"
        mock_response.exit_code = 0
        mock_sandbox.process.code_run.return_value = mock_response

        mock_client = MagicMock()
        mock_client.create.return_value = mock_sandbox
        mock_client.delete.return_value = None

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    result = await tool.execute(code='print("Hello, World!")')

        assert result.success is True
        assert "Hello, World!" in result.result_summary
        assert result.duration_ms is not None

    @pytest.mark.asyncio
    async def test_execute_with_error_exit_code(self):
        """Execution with non-zero exit code returns failure."""
        mock_sandbox = MagicMock()
        mock_response = MagicMock()
        mock_response.result = "NameError: name 'undefined' is not defined"
        mock_response.exit_code = 1
        mock_sandbox.process.code_run.return_value = mock_response

        mock_client = MagicMock()
        mock_client.create.return_value = mock_sandbox
        mock_client.delete.return_value = None

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    result = await tool.execute(code="print(undefined)")

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Timeout returns failure result."""
        mock_client = MagicMock()
        mock_client.create.side_effect = lambda: exec("import time; time.sleep(100)")

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                        from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                        tool = DaytonaPythonTool(api_key="test", timeout_seconds=1)
                        result = await tool.execute(code="import time; time.sleep(100)")

        assert result.success is False
        assert "timed out" in result.result_summary.lower()

    @pytest.mark.asyncio
    async def test_execute_sandbox_cleaned_up_on_success(self):
        """Sandbox is cleaned up after successful execution."""
        mock_sandbox = MagicMock()
        mock_response = MagicMock()
        mock_response.result = "output"
        mock_response.exit_code = 0
        mock_sandbox.process.code_run.return_value = mock_response

        mock_client = MagicMock()
        mock_client.create.return_value = mock_sandbox
        mock_client.delete.return_value = None

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    await tool.execute(code="print('test')")

        # Verify remove was called
        mock_client.delete.assert_called_once_with(mock_sandbox)

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self):
        """Returns failure when exception occurs."""
        mock_client = MagicMock()
        mock_client.create.side_effect = Exception("Connection failed")

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    result = await tool.execute(code="print('test')")

        assert result.success is False
        assert "Connection failed" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_no_output(self):
        """Execution with no output shows '(no output)'."""
        mock_sandbox = MagicMock()
        mock_response = MagicMock()
        mock_response.result = ""
        mock_response.exit_code = 0
        mock_sandbox.process.code_run.return_value = mock_response

        mock_client = MagicMock()
        mock_client.create.return_value = mock_sandbox
        mock_client.delete.return_value = None

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    result = await tool.execute(code="x = 1")

        assert result.success is True
        assert "(no output)" in result.result_summary


class TestDaytonaPythonToolHealthCheck:
    """Tests for DaytonaPythonTool health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check returns True when execution works."""
        mock_sandbox = MagicMock()
        mock_response = MagicMock()
        mock_response.result = "ok"
        mock_response.exit_code = 0
        mock_sandbox.process.code_run.return_value = mock_response

        mock_client = MagicMock()
        mock_client.create.return_value = mock_sandbox
        mock_client.delete.return_value = None

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    result = await tool.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure_no_api_key(self):
        """Health check returns False when no API key."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch.dict("os.environ", {}, clear=True):
                from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                tool = DaytonaPythonTool(api_key=None)
                # Clear any env var that might be set
                tool._api_key = None
                result = await tool.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_failure_on_exception(self):
        """Health check returns False when exception occurs."""
        mock_client = MagicMock()
        mock_client.create.side_effect = Exception("API error")

        mock_daytona_class = MagicMock(return_value=mock_client)

        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            with patch(
                "daytona_sdk.Daytona",
                mock_daytona_class,
            ):
                with patch("daytona_sdk.DaytonaConfig"):
                    from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                    tool = DaytonaPythonTool(api_key="test")
                    result = await tool.health_check()

        assert result is False


class TestDaytonaPythonToolLifecycle:
    """Tests for DaytonaPythonTool lifecycle methods."""

    @pytest.mark.asyncio
    async def test_initialize_with_api_key(self):
        """Initialize logs success with API key."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test")
            await tool.initialize()
            # Just check it doesn't raise

    @pytest.mark.asyncio
    async def test_initialize_without_api_key(self):
        """Initialize logs warning without API key."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger") as mock_logger:
            mock_logger.return_value = MagicMock()
            with patch.dict("os.environ", {}, clear=True):
                from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

                tool = DaytonaPythonTool(api_key=None)
                tool._api_key = None
                await tool.initialize()
                # Just check it doesn't raise

    @pytest.mark.asyncio
    async def test_close_clears_client(self):
        """Close clears the client reference."""
        with patch("orchestrator.agent.tools.python_daytona.get_logger"):
            from orchestrator.agent.tools.python_daytona import DaytonaPythonTool

            tool = DaytonaPythonTool(api_key="test")
            tool._client = MagicMock()  # Simulate initialized client
            await tool.close()
            assert tool._client is None
