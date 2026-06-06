"""Tests for OpenAICompatProvider."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from orchestrator.providers.openai_compat import OpenAICompatProvider
from orchestrator.providers.base import ProviderAPIError, ToolFallbackError
from orchestrator.providers.base import RetryExhaustedError


class TestToolFallbackPolicy:
    """Tests for tool fallback behavior."""

    @pytest.mark.asyncio
    async def test_tool_fallback_raises_when_fail_on_tool_fallback_true(self):
        """Tools + fallback + fail_on_tool_fallback=True raises ToolFallbackError."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:1234",
            endpoint="responses",
            fallback_on_404=True,
            fail_on_tool_fallback=True,  # Default, but explicit
        )

        # Mock the fallback scenario - _handle_fallback is called when /v1/responses returns 404
        tools = [{"type": "function", "function": {"name": "test"}}]

        with pytest.raises(ToolFallbackError) as exc_info:
            await provider._handle_fallback(
                messages=[{"role": "user", "content": "test"}],
                model="some-model",
                tools=tools,
                max_tokens=100,
                temperature=0.7,
            )

        assert "fail_on_tool_fallback=False" in str(exc_info.value)
        await provider.close()

    @pytest.mark.asyncio
    async def test_tool_fallback_allowed_when_fail_on_tool_fallback_false(self):
        """Tools + fallback + fail_on_tool_fallback=False proceeds to chat_completions."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:1234",
            endpoint="responses",
            fallback_on_404=True,
            fail_on_tool_fallback=False,  # Allow fallback
        )

        # Mock the HTTP client to return a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        with patch.object(provider, "_request_with_retry", return_value=mock_response):
            response, url = await provider._handle_fallback(
                messages=[{"role": "user", "content": "test"}],
                model="some-model",
                tools=[{"type": "function", "function": {"name": "test"}}],
                max_tokens=100,
                temperature=0.7,
            )

            # Should fall back to chat_completions
            assert "/chat/completions" in url

        await provider.close()

    @pytest.mark.asyncio
    async def test_gpt_oss_always_fails_on_tool_fallback(self):
        """gpt-oss models always raise ToolFallbackError regardless of config."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:1234",
            endpoint="responses",
            fallback_on_404=True,
            fail_on_tool_fallback=False,  # Even with this set to False...
        )

        tools = [{"type": "function", "function": {"name": "test"}}]

        # gpt-oss model should ALWAYS fail
        with pytest.raises(ToolFallbackError) as exc_info:
            await provider._handle_fallback(
                messages=[{"role": "user", "content": "test"}],
                model="openai/gpt-oss-20b",  # gpt-oss model
                tools=tools,
                max_tokens=100,
                temperature=0.7,
            )

        assert "gpt-oss" in str(exc_info.value) or "requires /v1/responses" in str(exc_info.value)
        await provider.close()

    @pytest.mark.asyncio
    async def test_no_tools_fallback_allowed_regardless_of_config(self):
        """Without tools, fallback should proceed regardless of fail_on_tool_fallback."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:1234",
            endpoint="responses",
            fallback_on_404=True,
            fail_on_tool_fallback=True,  # Even with this True
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}, "finish_reason": "stop"}],
        }

        with patch.object(provider, "_request_with_retry", return_value=mock_response):
            response, url = await provider._handle_fallback(
                messages=[{"role": "user", "content": "test"}],
                model="some-model",
                tools=None,  # No tools
                max_tokens=100,
                temperature=0.7,
            )

            # Should succeed even with fail_on_tool_fallback=True
            assert "/chat/completions" in url

        await provider.close()


class TestPreviousResponseId:
    """Tests for previous_response_id parameter."""

    def test_build_responses_request_includes_previous_response_id(self):
        """Verify previous_response_id is included in payload when provided."""
        from orchestrator.providers.request_builders import build_responses_request

        payload = build_responses_request(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            previous_response_id="resp_12345",
        )

        assert payload["previous_response_id"] == "resp_12345"

    def test_build_responses_request_omits_previous_response_id_when_none(self):
        """Verify previous_response_id is not in payload when None."""
        from orchestrator.providers.request_builders import build_responses_request

        payload = build_responses_request(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            previous_response_id=None,
        )

        assert "previous_response_id" not in payload


class TestProviderErrors:
    """Tests for provider HTTP error diagnostics."""

    @pytest.mark.asyncio
    async def test_complete_includes_response_body_in_provider_error(self):
        """OpenAI-compatible 400s surface provider error message/body."""
        provider = OpenAICompatProvider(
            base_url="https://api.openai.com/v1",
            endpoint="responses",
        )
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        response = httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid tool schema: default is not permitted",
                    "param": "tools[0].parameters",
                    "type": "invalid_request_error",
                }
            },
            request=request,
        )

        with patch.object(provider, "_request_with_retry", return_value=response):
            with pytest.raises(ProviderAPIError) as exc_info:
                await provider.complete(
                    messages=[{"role": "user", "content": "test"}],
                    model="gpt-5",
                )

        message = str(exc_info.value)
        assert "400 Bad Request" in message
        assert "Invalid tool schema" in message
        assert "tools[0].parameters" in message
        await provider.close()


class TestStreamingRetry:
    """Tests for streaming retry behavior."""

    @pytest.mark.asyncio
    async def test_streaming_timeout_is_retried_and_error_is_non_empty(self):
        """Streaming timeouts are retryable and keep type info when exhausted."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:1234",
            endpoint="chat_completions",
            timeout=1,
            max_retries=1,
            base_delay=0,
        )

        with patch.object(
            provider,
            "_do_streaming",
            new=AsyncMock(side_effect=httpx.ReadTimeout("")),
        ) as mock_stream:
            with pytest.raises(RetryExhaustedError) as exc_info:
                await provider.complete_streaming(
                    messages=[{"role": "user", "content": "test"}],
                    model="test-model",
                    on_token=lambda _token: None,
                )

        assert mock_stream.await_count == 2
        assert "ReadTimeout" in str(exc_info.value)
        await provider.close()
