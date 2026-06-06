"""Tests for ChatGPTProvider request/response translation."""

import json
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.config import ChatGPTConfig
from orchestrator.providers.base import ProviderAuthError
from orchestrator.providers.chatgpt import ChatGPTProvider
from orchestrator.providers.factory import create_chatgpt_provider


class TestRequestTranslation:
    """Tests for Chat Completions -> Codex Responses API translation."""

    def setup_method(self):
        self.provider = ChatGPTProvider(
            access_token="test-token",
            account_id="test-account",
        )

    @pytest.mark.asyncio
    async def test_teardown(self):
        await self.provider.close()

    def test_system_message_becomes_instructions(self):
        """System messages should be extracted as instructions."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        input_items, instructions = self.provider._translate_messages_to_input(messages)

        assert instructions == "You are helpful."
        assert len(input_items) == 1
        assert input_items[0]["role"] == "user"

    def test_user_message_format(self):
        """User messages should use input_text content type."""
        messages = [
            {"role": "user", "content": "What is 2+2?"},
        ]

        input_items, _ = self.provider._translate_messages_to_input(messages)

        assert len(input_items) == 1
        assert input_items[0]["type"] == "message"
        assert input_items[0]["role"] == "user"
        assert input_items[0]["content"][0]["type"] == "input_text"
        assert input_items[0]["content"][0]["text"] == "What is 2+2?"

    def test_assistant_message_format(self):
        """Assistant messages should use output_text content type."""
        messages = [
            {"role": "assistant", "content": "The answer is 4."},
        ]

        input_items, _ = self.provider._translate_messages_to_input(messages)

        assert len(input_items) == 1
        assert input_items[0]["type"] == "message"
        assert input_items[0]["role"] == "assistant"
        assert input_items[0]["content"][0]["type"] == "output_text"

    def test_tool_calls_become_function_call(self):
        """Assistant tool calls should become function_call items."""
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            },
        ]

        input_items, _ = self.provider._translate_messages_to_input(messages)

        assert len(input_items) == 1
        assert input_items[0]["type"] == "function_call"
        assert input_items[0]["call_id"] == "call_123"
        assert input_items[0]["name"] == "web_search"
        assert input_items[0]["arguments"] == '{"query": "test"}'

    def test_tool_result_becomes_function_call_output(self):
        """Tool result messages should become function_call_output items."""
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "content": "Search results: ...",
            },
        ]

        input_items, _ = self.provider._translate_messages_to_input(messages)

        assert len(input_items) == 2
        assert input_items[0]["type"] == "function_call"
        assert input_items[1]["type"] == "function_call_output"
        assert input_items[1]["call_id"] == "call_123"
        assert input_items[1]["output"] == "Search results: ..."

    def test_orphan_tool_result_becomes_user_context(self):
        """Orphan tool results should not become invalid function_call_output items."""
        messages = [
            {
                "role": "tool",
                "tool_call_id": "missing_call",
                "name": "grep",
                "content": "Found matches",
            },
        ]

        input_items, _ = self.provider._translate_messages_to_input(messages)

        assert len(input_items) == 1
        assert input_items[0]["type"] == "message"
        assert input_items[0]["role"] == "user"
        assert "Previous grep result" in input_items[0]["content"][0]["text"]
        assert "missing_call" in input_items[0]["content"][0]["text"]

    def test_instructions_parameter_overrides_system(self):
        """Explicit instructions parameter should take priority."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ]

        _, instructions = self.provider._translate_messages_to_input(
            messages, instructions="Override prompt"
        )

        assert instructions == "Override prompt"

    def test_flatten_tools(self):
        """Tool definitions should be flattened for Responses API."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        flattened = self.provider._translate_tools(tools)

        assert len(flattened) == 1
        assert flattened[0]["type"] == "function"
        assert flattened[0]["name"] == "web_search"
        assert flattened[0]["description"] == "Search the web"
        assert flattened[0]["strict"] is False
        # No nested "function" key
        assert "function" not in flattened[0]

    def test_flatten_tools_preserves_explicit_strict(self):
        """Explicit strict mode is preserved for ChatGPT Responses tools."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                    "strict": True,
                },
            }
        ]

        flattened = self.provider._translate_tools(tools)

        assert flattened[0]["strict"] is True

    def test_flatten_tools_none(self):
        """None tools should return None."""
        assert self.provider._translate_tools(None) is None

    def test_build_request_payload(self):
        """Full payload should include all required Codex fields."""
        messages = [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "Hello"},
        ]

        payload = self.provider._build_request_payload(
            messages=messages,
            model="gpt-5.2-codex",
            reasoning_effort="medium",
        )

        assert payload["model"] == "gpt-5.2-codex"
        assert payload["stream"] is True
        assert payload["store"] is False
        assert "reasoning.encrypted_content" in payload["include"]
        assert payload["reasoning"]["effort"] == "medium"
        assert payload["reasoning"]["summary"] == "auto"
        assert payload["instructions"] == "Be helpful."
        assert len(payload["input"]) == 1  # Only user message, system extracted

    def test_build_request_payload_with_reasoning_object_omits_max_tokens(self):
        """Codex backend should not receive unsupported max_output_tokens."""
        payload = self.provider._build_request_payload(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-5.2-codex",
            reasoning={
                "effort": "low",
                "summary": "auto",
            },
            max_output_tokens=512,
        )

        assert payload["reasoning"] == {"effort": "low", "summary": "auto"}
        assert "max_output_tokens" not in payload

    def test_build_request_payload_with_tools(self):
        """Payload with tools should include flattened tool definitions."""
        messages = [{"role": "user", "content": "Search for cats"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search",
                    "parameters": {},
                },
            }
        ]

        payload = self.provider._build_request_payload(
            messages=messages,
            model="gpt-5.2-codex",
            tools=tools,
        )

        assert "tools" in payload
        assert payload["tools"][0]["name"] == "web_search"
        assert payload["tools"][0]["strict"] is False

    @pytest.mark.asyncio
    async def test_factory_falls_back_from_stale_chatgpt_model(self):
        """Stored stale ChatGPT selections do not keep using unsupported models."""
        provider = create_chatgpt_provider(
            {
                "access_token": "test-token",
                "account_id": "test-account",
            },
            chatgpt_config=ChatGPTConfig(),
            model="gpt-5.3-codex",
        )

        assert provider._default_model == "gpt-5.5"
        await provider.close()


class TestResponseTranslation:
    """Tests for Codex SSE -> Standard format translation."""

    def setup_method(self):
        self.provider = ChatGPTProvider(
            access_token="test-token",
            account_id="test-account",
        )

    def test_content_delta(self):
        """response.output_text.delta should extract content."""
        event = {"type": "response.output_text.delta", "delta": "Hello"}
        parsed = self.provider._parse_sse_event(event)
        assert parsed["content_delta"] == "Hello"

    def test_reasoning_delta(self):
        """response.reasoning_summary_text.delta should extract reasoning."""
        event = {"type": "response.reasoning_summary_text.delta", "delta": "Thinking..."}
        parsed = self.provider._parse_sse_event(event)
        assert parsed["reasoning_delta"] == "Thinking..."

    def test_tool_call_args_delta(self):
        """response.function_call_arguments.delta should accumulate args."""
        event = {
            "type": "response.function_call_arguments.delta",
            "call_id": "call_123",
            "delta": '{"query":',
        }
        parsed = self.provider._parse_sse_event(event)
        assert parsed["tool_call_args_delta"]["call_id"] == "call_123"
        assert parsed["tool_call_args_delta"]["delta"] == '{"query":'

    def test_tool_call_complete(self):
        """response.function_call_arguments.done should emit full tool call."""
        event = {
            "type": "response.function_call_arguments.done",
            "call_id": "call_123",
            "name": "web_search",
            "arguments": '{"query": "test"}',
        }
        parsed = self.provider._parse_sse_event(event)
        assert parsed["tool_call_complete"]["call_id"] == "call_123"
        assert parsed["tool_call_complete"]["name"] == "web_search"
        assert parsed["tool_call_complete"]["arguments"] == '{"query": "test"}'

    def test_response_created(self):
        """response.created should capture response ID."""
        event = {
            "type": "response.created",
            "response": {"id": "resp_abc123"},
        }
        parsed = self.provider._parse_sse_event(event)
        assert parsed["response_id"] == "resp_abc123"

    def test_response_completed(self):
        """response.completed should extract usage and set done flag."""
        event = {
            "type": "response.completed",
            "response": {
                "id": "resp_abc123",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Final answer"}],
                    }
                ],
            },
        }
        parsed = self.provider._parse_sse_event(event)
        assert parsed["done"] is True
        assert parsed["response_id"] == "resp_abc123"
        assert parsed["usage"]["prompt_tokens"] == 100
        assert parsed["usage"]["completion_tokens"] == 50
        assert parsed["final_text"] == "Final answer"

    def test_unknown_event_returns_empty(self):
        """Unknown event types should return empty dict."""
        event = {"type": "response.some_unknown_event"}
        parsed = self.provider._parse_sse_event(event)
        assert parsed == {}


class TestHeaders:
    """Tests for request headers."""

    def test_headers_include_required_fields(self):
        """Provider should set all required ChatGPT backend headers."""
        provider = ChatGPTProvider(
            access_token="test-token-abc",
            account_id="acct-123",
        )

        # httpx Headers are case-insensitive
        headers = provider._client.headers

        assert headers["authorization"] == "Bearer test-token-abc"
        assert headers["chatgpt-account-id"] == "acct-123"
        assert headers["openai-beta"] == "responses=experimental"
        assert headers["originator"] == "codex_cli_rs"
        assert headers["content-type"] == "application/json"

    def test_update_token(self):
        """update_token should update the Authorization header."""
        provider = ChatGPTProvider(
            access_token="old-token",
            account_id="acct-123",
        )

        provider.update_token("new-token")

        assert provider._access_token == "new-token"
        assert provider._client.headers["Authorization"] == "Bearer new-token"

    @pytest.mark.asyncio
    async def test_401_token_revoked_invokes_auth_callback(self):
        """Revoked ChatGPT tokens should clear stored auth and raise a useful error."""
        callback = AsyncMock()
        provider = ChatGPTProvider(
            access_token="old-token",
            account_id="acct-123",
            on_auth_error=callback,
        )
        response = httpx.Response(
            401,
            request=httpx.Request("POST", "https://chatgpt.com/backend-api/codex/responses"),
        )
        body = json.dumps(
            {
                "error": {
                    "message": "Encountered invalidated oauth token for user, failing request",
                    "code": "token_revoked",
                },
                "status": 401,
            }
        ).encode()

        with pytest.raises(ProviderAuthError, match="revoked"):
            await provider._raise_for_error_response(response, body)

        callback.assert_awaited_once()
        await provider.close()


class TestConversationRoundtrip:
    """Tests for multi-turn conversation translation."""

    def setup_method(self):
        self.provider = ChatGPTProvider(
            access_token="test-token",
            account_id="test-account",
        )

    def test_full_conversation_translation(self):
        """Full conversation with tool use should translate correctly."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Search for cats"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "cats"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "Results about cats...",
            },
            {"role": "assistant", "content": "Here's what I found about cats..."},
            {"role": "user", "content": "Tell me more"},
        ]

        input_items, instructions = self.provider._translate_messages_to_input(messages)

        assert instructions == "You are a helpful assistant."
        assert len(input_items) == 5  # user, function_call, function_call_output, assistant, user

        assert input_items[0]["type"] == "message"
        assert input_items[0]["role"] == "user"

        assert input_items[1]["type"] == "function_call"
        assert input_items[1]["name"] == "web_search"

        assert input_items[2]["type"] == "function_call_output"
        assert input_items[2]["call_id"] == "call_1"

        assert input_items[3]["type"] == "message"
        assert input_items[3]["role"] == "assistant"

        assert input_items[4]["type"] == "message"
        assert input_items[4]["role"] == "user"
