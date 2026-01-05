"""Tests for WebExtractTool."""

import pytest
from unittest.mock import MagicMock, patch
import httpx

from orchestrator.agent.tools.web_extract import WebExtractTool


class TestWebExtractToolProperties:
    """Tests for WebExtractTool properties."""

    def test_name_property(self):
        """Name is 'web_extract'."""
        tool = WebExtractTool(api_key="test")
        assert tool.name == "web_extract"

    def test_schema_is_idempotent(self):
        """Schema marks tool as idempotent."""
        tool = WebExtractTool(api_key="test")
        assert tool.schema.is_idempotent is True

    def test_schema_name(self):
        """Schema name matches tool name."""
        tool = WebExtractTool(api_key="test")
        assert tool.schema.name == "web_extract"

    def test_schema_has_description(self):
        """Schema has a description."""
        tool = WebExtractTool(api_key="test")
        assert tool.schema.description
        assert "extract" in tool.schema.description.lower()

    def test_schema_parameters(self):
        """Schema has correct parameters."""
        tool = WebExtractTool(api_key="test")
        params = tool.schema.parameters

        assert params["type"] == "object"
        assert "urls" in params["properties"]
        assert params["properties"]["urls"]["type"] == "array"
        assert "urls" in params["required"]

    def test_schema_urls_has_max_items(self):
        """urls parameter has maxItems."""
        tool = WebExtractTool(api_key="test")
        params = tool.schema.parameters

        assert params["properties"]["urls"]["maxItems"] == 5


class TestWebExtractToolExecution:
    """Tests for WebExtractTool execution."""

    @pytest.fixture
    def tool(self):
        """Create tool with mocked client."""
        return WebExtractTool(api_key="test-key", timeout_ms=5000)

    @pytest.mark.asyncio
    async def test_execute_success(self, tool):
        """Successful extraction returns content."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "excerpts": ["Page content here"],
                    "full_content": None,
                },
            ],
            "errors": [],
        }

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(urls=["https://example.com"])

        assert result.success is True
        assert "Extracted 1/1 URLs" in result.result_summary
        assert len(result.result_data["extractions"]) == 1
        assert result.metadata["successful_count"] == 1
        assert result.duration_ms is not None
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_partial_success(self, tool):
        """Partial success (some URLs fail) still succeeds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "excerpts": ["Content"],
                    "full_content": None,
                },
            ],
            "errors": [
                {
                    "url": "https://bad-url.com",
                    "error": "URL not found",
                },
            ],
        }

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(
                urls=["https://example.com", "https://bad-url.com"]
            )

        assert result.success is True  # Partial success is OK
        assert "Extracted 1/2 URLs" in result.result_summary
        assert result.metadata["successful_count"] == 1
        assert result.metadata["failed_count"] == 1
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_all_fail(self, tool):
        """All URLs failing returns failure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [],
            "errors": [
                {
                    "url": "https://bad1.com",
                    "error": "Failed",
                },
                {
                    "url": "https://bad2.com",
                    "error": "Failed",
                },
            ],
        }

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(urls=["https://bad1.com", "https://bad2.com"])

        assert result.success is False  # All failed
        assert "Extracted 0/2 URLs" in result.result_summary
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_empty_urls(self, tool):
        """Empty URL list returns failure."""
        result = await tool.execute(urls=[])

        assert result.success is False
        assert "No URLs provided" in result.result_summary
        assert result.error_message == "urls list is empty"
        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_urls_capped(self, tool):
        """URLs are capped to max_urls."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "errors": []}

        urls = [f"https://example{i}.com" for i in range(10)]

        with patch.object(tool._client, "post", return_value=mock_response) as mock_post:
            await tool.execute(urls=urls)

            # Check only 5 URLs were sent (max_urls default)
            call_args = mock_post.call_args
            assert len(call_args[1]["json"]["urls"]) == 5

        await tool.close()

    @pytest.mark.asyncio
    async def test_execute_timeout(self, tool):
        """Timeout returns failure result after retries."""
        # Use max_retries=1 to avoid long wait
        tool._max_retries = 1
        tool._base_delay = 0.01

        with patch.object(
            tool._client, "post", side_effect=httpx.TimeoutException("timeout")
        ):
            result = await tool.execute(urls=["https://example.com"])

        assert result.success is False
        assert "failed" in result.result_summary.lower()
        assert "Timeout" in result.error_message
        await tool.close()

    @pytest.mark.asyncio
    async def test_result_data_structure(self, tool):
        """Result data has correct structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "url": "https://test.com",
                    "title": "Test Page",
                    "excerpts": ["Content here"],
                    "full_content": None,
                },
            ],
            "errors": [],
        }

        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.execute(urls=["https://test.com"])

        assert "extractions" in result.result_data
        extraction = result.result_data["extractions"][0]
        assert extraction["url"] == "https://test.com"
        assert extraction["title"] == "Test Page"
        assert extraction["content"] == "Content here"
        assert extraction["success"] is True
        await tool.close()


class TestWebExtractToolRetry:
    """Tests for WebExtractTool retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """Retries on 500 error."""
        tool = WebExtractTool(api_key="test", max_retries=3, base_delay=0.01)

        responses = [
            MagicMock(status_code=500),
            MagicMock(status_code=500),
            MagicMock(
                status_code=200, json=MagicMock(return_value={"results": [], "errors": []})
            ),
        ]

        with patch.object(tool._client, "post", side_effect=responses):
            result = await tool.execute(urls=["https://example.com"])

        # Even with empty results, the request succeeded
        assert result.success is False  # No successful extractions
        assert "Extracted 0/1" in result.result_summary
        await tool.close()

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        """Retries on 429 rate limit."""
        tool = WebExtractTool(api_key="test", max_retries=2, base_delay=0.01)

        responses = [
            MagicMock(status_code=429),
            MagicMock(
                status_code=200,
                json=MagicMock(
                    return_value={
                        "results": [{"url": "test", "title": "Test", "excerpts": ["x"]}],
                        "errors": [],
                    }
                ),
            ),
        ]

        with patch.object(tool._client, "post", side_effect=responses):
            result = await tool.execute(urls=["https://example.com"])

        assert result.success is True
        await tool.close()

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Returns failure after max retries."""
        tool = WebExtractTool(api_key="test", max_retries=2, base_delay=0.01)

        with patch.object(
            tool._client, "post", return_value=MagicMock(status_code=500)
        ):
            result = await tool.execute(urls=["https://example.com"])

        assert result.success is False
        assert "failed" in result.result_summary.lower()
        await tool.close()


class TestWebExtractToolHealthCheck:
    """Tests for WebExtractTool health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check returns True when API responds 200."""
        tool = WebExtractTool(api_key="test")

        mock_response = MagicMock(status_code=200)
        with patch.object(tool._client, "post", return_value=mock_response):
            result = await tool.health_check()

        assert result is True
        await tool.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Health check returns False when API fails."""
        tool = WebExtractTool(api_key="test")

        with patch.object(
            tool._client, "post", side_effect=httpx.ConnectError("Connection failed")
        ):
            result = await tool.health_check()

        assert result is False
        await tool.close()


class TestWebExtractToolInit:
    """Tests for WebExtractTool initialization."""

    def test_default_base_url(self):
        """Default base URL is Parallel.ai."""
        tool = WebExtractTool(api_key="test")
        assert "parallel.ai" in tool._base_url

    def test_custom_base_url(self):
        """Can set custom base URL."""
        tool = WebExtractTool(api_key="test", base_url="https://custom.api.com/")
        assert tool._base_url == "https://custom.api.com"

    def test_timeout_conversion(self):
        """Timeout is converted from ms to seconds."""
        tool = WebExtractTool(api_key="test", timeout_ms=30000)
        assert tool._timeout == 30.0

    def test_max_urls_stored(self):
        """Max URLs is stored."""
        tool = WebExtractTool(api_key="test", max_urls=3)
        assert tool._max_urls == 3

    def test_authorization_header_set(self):
        """Authorization header is set with API key."""
        tool = WebExtractTool(api_key="test-key-456")
        assert tool._client.headers["Authorization"] == "Bearer test-key-456"
