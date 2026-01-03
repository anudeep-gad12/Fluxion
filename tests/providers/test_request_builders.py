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
        """Tools are transformed to responses API format."""
        messages = [{"role": "user", "content": "Hello"}]
        tools = [
            {
                "type": "function",
                "function": {"name": "get_weather", "parameters": {}},
            }
        ]
        payload = build_responses_request(messages, model="gpt-oss-20b", tools=tools)

        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["function"]["name"] == "get_weather"

    def test_with_reasoning_effort(self):
        """Reasoning effort is nested under 'reasoning' key."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_responses_request(
            messages, model="gpt-oss-20b", reasoning_effort="high"
        )

        assert payload["reasoning"] == {"effort": "high"}

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


class TestBuildChatCompletionsRequest:
    """Tests for /v1/chat/completions request builder."""

    def test_minimal_request(self):
        """Minimal request has required fields."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = build_chat_completions_request(messages, model="gpt-4")

        assert payload["model"] == "gpt-4"
        assert payload["messages"] == messages
        assert payload["stream"] is True
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
