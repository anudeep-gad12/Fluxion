"""Tests for WebSearchTool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from orchestrator.agent.tools.web_search import WebSearchTool


class TestWebSearchToolProperties:
    """Tests for WebSearchTool properties."""

    def test_name_property(self):
        """Name is 'web_search'."""
        tool = WebSearchTool(api_key="test")
        assert tool.name == "web_search"

    def test_schema_is_idempotent(self):
        """Schema marks tool as idempotent."""
        tool = WebSearchTool(api_key="test")
        assert tool.schema.is_idempotent is True

    def test_schema_name(self):
        """Schema name matches tool name."""
        tool = WebSearchTool(api_key="test")
        assert tool.schema.name == "web_search"

    def test_schema_has_description(self):
        """Schema has a description."""
        tool = WebSearchTool(api_key="test")
        assert tool.schema.description
        assert "search" in tool.schema.description.lower()

    def test_schema_parameters(self):
        """Schema has correct parameters."""
        tool = WebSearchTool(api_key="test")
        params = tool.schema.parameters

        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert "num_results" in params["properties"]
        assert "query" in params["required"]

    def test_schema_num_results_has_max(self):
        """num_results parameter has maximum value."""
        tool = WebSearchTool(api_key="test")
        params = tool.schema.parameters

        assert params["properties"]["num_results"]["maximum"] == 10


class TestWebSearchToolExecution:
    """Tests for WebSearchTool execution."""

    @pytest.fixture
    def tool(self):
        """Create tool with mocked client."""
        return WebSearchTool(api_key="test-key", timeout_ms=5000)

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Successful search returns results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "snippet": "Test snippet",
                },
                {
                    "url": "https://example2.com",
                    "title": "Example 2",
                    "snippet": "Another snippet",
                },
            ]
        }

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(query="test query")

        assert result.success is True
        assert "Found 2 results" in result.result_summary
        assert len(result.result_data["results"]) == 2
        assert result.result_data["query"] == "test query"
        assert result.duration_ms is not None
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_empty_results(self, tool):
        """Search with no results still succeeds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(query="obscure query xyz123")

        assert result.success is True
        assert "Found 0 results" in result.result_summary
        assert result.result_data["results"] == []
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tool):
        """Timeout returns failure result."""
        with patch.object(
            tool._client, "post", side_effect=httpx.TimeoutException("timeout")
        ):
            result = await tool.execute(query="test query")

        assert result.success is False
        assert "timed out" in result.result_summary.lower() or "failed" in result.result_summary.lower()
        assert result.error_message is not None
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_connection_error(self, tool):
        """Connection error returns failure result."""
        with patch.object(
            tool._client, "post", side_effect=httpx.ConnectError("Connection refused")
        ):
            result = await tool.execute(query="test query")

        assert result.success is False
        assert result.error_message is not None
        await tool.close()

    @pytest.mark.asyncio
    async def test_num_results_capped(self, tool):
        """num_results is capped to max_results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        with patch.object(tool._client, "post", return_value=mock_response) as mock_post:
            await tool.execute(query="test", num_results=100)

            # Check the actual call (Parallel.ai API uses 'max_results' not 'num_results')
            call_args = mock_post.call_args
            assert call_args[1]["json"]["max_results"] == 10  # Capped to max

        await tool.close()

    @pytest.mark.asyncio
    async def test_long_query_truncated_in_summary(self, tool):
        """Long queries are truncated in summary."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        long_query = "a" * 100  # 100 character query

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(query=long_query)

        # Summary should be truncated
        assert len(result.result_summary) < 150
        assert "..." in result.result_summary
        await tool.close()

    @pytest.mark.asyncio
    async def test_result_data_structure(self, tool):
        """Result data has correct structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"url": "https://test.com", "title": "Test", "snippet": "Snippet"},
            ]
        }

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(query="test")

        assert "query" in result.result_data
        assert "results" in result.result_data
        assert result.result_data["results"][0]["url"] == "https://test.com"
        assert result.result_data["results"][0]["title"] == "Test"
        assert result.result_data["results"][0]["snippet"] == "Snippet"
        await tool.close()


class TestWebSearchToolRetry:
    """Tests for WebSearchTool retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """Retries on 500 error."""
        tool = WebSearchTool(api_key="test", max_retries=3, base_delay=0.01)

        responses = [
            MagicMock(status_code=500),
            MagicMock(status_code=500),
            MagicMock(status_code=200, json=MagicMock(return_value={"results": []})),
        ]

        with patch.object(tool._client, "post", side_effect=responses):
            result = await tool.execute(query="test")

        assert result.success is True
        await tool.close()

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        """Retries on 429 rate limit."""
        tool = WebSearchTool(api_key="test", max_retries=2, base_delay=0.01)

        responses = [
            MagicMock(status_code=429),
            MagicMock(status_code=200, json=MagicMock(return_value={"results": []})),
        ]

        with patch.object(tool._client, "post", side_effect=responses):
            result = await tool.execute(query="test")

        assert result.success is True
        await tool.close()

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Returns failure after max retries."""
        tool = WebSearchTool(api_key="test", max_retries=2, base_delay=0.01)

        with patch.object(
            tool._client, "post", return_value=MagicMock(status_code=500)
        ):
            result = await tool.execute(query="test")

        assert result.success is False
        assert "failed" in result.result_summary.lower()
        await tool.close()

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        """Does not retry on 400 client error."""
        tool = WebSearchTool(api_key="test", max_retries=3, base_delay=0.01)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        )

        call_count = 0
        def track_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_response

        with patch.object(tool._client, "post", side_effect=track_calls):
            result = await tool.execute(query="test")

        assert result.success is False
        assert call_count == 1  # No retries on 400
        await tool.close()


class TestWebSearchToolHealthCheck:
    """Tests for WebSearchTool health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check returns True when API responds 200."""
        tool = WebSearchTool(api_key="test")

        mock_response = MagicMock(status_code=200)
        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.health_check()

        assert result is True
        await tool.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Health check returns False when API fails."""
        tool = WebSearchTool(api_key="test")

        with patch.object(
            tool._client, "post", side_effect=httpx.ConnectError("Connection failed")
        ):
            result = await tool.health_check()

        assert result is False
        await tool.close()

    @pytest.mark.asyncio
    async def test_health_check_non_200(self):
        """Health check returns False on non-200 status."""
        tool = WebSearchTool(api_key="test")

        mock_response = MagicMock(status_code=500)
        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.health_check()

        assert result is False
        await tool.close()


class TestWebSearchToolInit:
    """Tests for WebSearchTool initialization."""

    def test_default_base_url(self):
        """Default base URL is Parallel.ai."""
        tool = WebSearchTool(api_key="test")
        assert "parallel.ai" in tool._base_url

    def test_custom_base_url(self):
        """Can set custom base URL."""
        tool = WebSearchTool(api_key="test", base_url="https://custom.api.com/")
        assert tool._base_url == "https://custom.api.com"  # Trailing slash stripped

    def test_timeout_conversion(self):
        """Timeout is converted from ms to seconds."""
        tool = WebSearchTool(api_key="test", timeout_ms=5000)
        assert tool._timeout == 5.0

    def test_max_results_stored(self):
        """Max results is stored."""
        tool = WebSearchTool(api_key="test", max_results=5)
        assert tool._max_results == 5

    def test_authorization_header_set(self):
        """Authorization header is set with API key."""
        tool = WebSearchTool(api_key="test-key-123")
        assert tool._client.headers["Authorization"] == "Bearer test-key-123"

    def test_no_auth_without_api_key(self):
        """No Authorization header without API key."""
        tool = WebSearchTool()
        assert "Authorization" not in tool._client.headers
