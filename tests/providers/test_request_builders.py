"""Tests for request builders."""

import pytest
from orchestrator.providers.request_builders import (
    build_responses_request,
    build_chat_completions_request,
)


class TestBuildResponsesRequest:
    """Tests for /v1/responses request builder."""

    def test_minimal_request(self):
        """Minimal request has required fields."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(messages, model="gpt-oss-20b")

        assert payload["model"] == "gpt-oss-20b"
        assert payload["input"] == messages
        assert payload["stream"] is True
        assert "instructions" not in payload
        assert "tools" not in payload
        assert "reasoning" not in payload

    def test_with_instructions(self):
        """Instructions are included when provided."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(
            messages, model="gpt-oss-20b", instructions="Be helpful"
        )

        assert payload["instructions"] == "Be helpful"

    def test_with_max_output_tokens(self):
        """max_output_tokens is used (not max_tokens)."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(
            messages, model="gpt-oss-20b", max_output_tokens=1024
        )

        assert payload["max_output_tokens"] == 1024
        assert "max_tokens" not in payload

    def test_with_tools(self):
        """Tools are transformed to responses API format (flat, not nested)."""
        messages = [{"role": "user", "content": "Hello"}]
        tools = [
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "Get weather", "parameters": {}},
            }
        ]
        payload = build_responses_request(messages, model="gpt-oss-20b", tools=tools)

        assert len(payload["tools"]) == 1
        # Responses API uses flat format, not nested under "function"
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["name"] == "get_weather"
        assert payload["tools"][0]["description"] == "Get weather"
        assert payload["tools"][0]["parameters"] == {}

    def test_with_reasoning_effort(self):
        """Reasoning effort is nested under 'reasoning' key."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(
            messages, model="gpt-oss-20b", reasoning_effort="high"
        )

        assert payload["reasoning"] == {"effort": "high"}

    def test_with_reasoning_object_overrides_effort(self):
        """Explicit reasoning object should pass through untouched."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(
            messages,
            model="gpt-oss-20b",
            reasoning_effort="high",
            reasoning={"effort": "low", "summary": "auto"},
        )

        assert payload["reasoning"] == {"effort": "low", "summary": "auto"}

    def test_with_previous_response_id(self):
        """Stateful mode includes previous_response_id."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(
            messages, model="gpt-oss-20b", previous_response_id="resp_123"
        )

        assert payload["previous_response_id"] == "resp_123"

    def test_stream_can_be_disabled(self):
        """Stream can be set to False."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(messages, model="gpt-oss-20b", stream=False)

        assert payload["stream"] is False

    def test_tool_result_transformed_to_function_call_output(self):
        """Tool result messages are transformed to function_call_output format."""
        messages = [
            {"role": "user", "content": "What's the weather?"},
            {"role": "tool", "tool_call_id": "call_123", "name": "get_weather", "content": "Sunny, 25°C"},
        ]
        payload = build_responses_request(messages, model="gpt-oss-20b")

        # First message stays as user message
        assert payload["input"][0]["role"] == "user"
        assert payload["input"][0]["content"] == "What's the weather?"

        # Tool result is transformed to function_call_output
        assert payload["input"][1]["type"] == "function_call_output"
        assert payload["input"][1]["call_id"] == "call_123"
        assert payload["input"][1]["output"] == "Sunny, 25°C"
        assert "role" not in payload["input"][1]

    def test_assistant_with_tool_calls_expanded(self):
        """Assistant message with tool_calls is expanded into function_call items."""
        messages = [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": "Let me check the weather.",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city": "NYC"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_123", "content": "Sunny, 25°C"},
        ]
        payload = build_responses_request(messages, model="gpt-oss-20b")

        # User message
        assert payload["input"][0]["role"] == "user"

        # Assistant content becomes a separate message
        assert payload["input"][1]["role"] == "assistant"
        assert payload["input"][1]["content"] == "Let me check the weather."

        # Tool call becomes a function_call item
        assert payload["input"][2]["type"] == "function_call"
        assert payload["input"][2]["call_id"] == "call_123"
        assert payload["input"][2]["name"] == "get_weather"
        assert payload["input"][2]["arguments"] == '{"city": "NYC"}'

        # Tool result
        assert payload["input"][3]["type"] == "function_call_output"
        assert payload["input"][3]["call_id"] == "call_123"

    def test_assistant_with_tool_calls_no_content(self):
        """Assistant message with tool_calls but no content is handled."""
        messages = [
            {"role": "user", "content": "Search for weather"},
            {
                "role": "assistant",
                "content": None,  # No content, just tool call
                "tool_calls": [
                    {
                        "id": "call_456",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query": "weather"}'},
                    }
                ],
            },
        ]
        payload = build_responses_request(messages, model="gpt-oss-20b")

        # User message
        assert payload["input"][0]["role"] == "user"

        # No assistant content message (it was None)
        # Only function_call item
        assert payload["input"][1]["type"] == "function_call"
        assert payload["input"][1]["name"] == "web_search"

        # Total should be 2 items (user + function_call)
        assert len(payload["input"]) == 2


class TestBuildChatCompletionsRequest:
    """Tests for /v1/chat/completions request builder."""

    def test_minimal_request(self):
        """Minimal request has required fields."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(messages, model="gpt-4")

        assert payload["model"] == "gpt-4"
        assert payload["messages"] == messages
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        assert "tools" not in payload
        assert "max_tokens" not in payload

    def test_with_max_tokens(self):
        """max_tokens is used (not max_output_tokens)."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(
            messages, model="gpt-4", max_tokens=1024
        )

        assert payload["max_tokens"] == 1024
        assert "max_output_tokens" not in payload

    def test_with_temperature(self):
        """Temperature is included when provided."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(
            messages, model="gpt-4", temperature=0.5
        )

        assert payload["temperature"] == 0.5

    def test_temperature_zero_is_included(self):
        """Temperature of 0 is included (not treated as falsy)."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(
            messages, model="gpt-4", temperature=0.0
        )

        assert payload["temperature"] == 0.0

    def test_with_tools(self):
        """Tools include tool_choice=auto."""
        messages = [{"role": "user", "content": "Hello"}]
        tools = [
            {
                "type": "function",
                "function": {"name": "get_weather", "parameters": {}},
            }
        ]
        payload = build_chat_completions_request(messages, model="gpt-4", tools=tools)

        assert payload["tools"] == tools
        assert payload["tool_choice"] == "auto"

    def test_optional_params(self):
        """Optional params (seed, top_p, etc.) are included."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(
            messages,
            model="gpt-4",
            seed=42,
            top_p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3,
        )

        assert payload["seed"] == 42
        assert payload["top_p"] == 0.9
        assert payload["frequency_penalty"] == 0.5
        assert payload["presence_penalty"] == 0.3

    def test_none_optional_params_excluded(self):
        """None values for optional params are excluded."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(
            messages, model="gpt-4", seed=None, top_p=None
        )

        assert "seed" not in payload
        assert "top_p" not in payload

    def test_stream_can_be_disabled(self):
        """Stream can be set to False."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(
            messages, model="gpt-4", stream=False
        )

        assert payload["stream"] is False
        assert "stream_options" not in payload

    def test_internal_message_metadata_is_stripped(self):
        """Underscore-prefixed internal message keys are not sent to providers."""
        messages = [
            {
                "role": "system",
                "content": "You are helpful.",
                "_working_memory": True,
                "_step": 2,
            },
            {
                "role": "tool",
                "name": "read_file",
                "content": "file excerpt",
                "tool_call_id": "tc-1",
                "_custom_internal": "x",
            },
        ]

        payload = build_chat_completions_request(messages, model="gpt-4")

        assert payload["messages"][0] == {
            "role": "system",
            "content": "You are helpful.",
        }
        assert payload["messages"][1] == {
            "role": "tool",
            "name": "read_file",
            "content": "file excerpt",
            "tool_call_id": "tc-1",
        }
