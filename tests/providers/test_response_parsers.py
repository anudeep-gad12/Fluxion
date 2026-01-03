"""Tests for response parsers."""

import pytest
from orchestrator.providers.response_parsers import (
    parse_responses_result,
    parse_chat_result,
    parse_streaming_delta,
)


class TestParseResponsesResult:
    """Tests for /v1/responses response parser."""

    def test_empty_output(self):
        """Empty output returns empty response."""
        raw = {"output": []}
        result = parse_responses_result(raw, "/v1/responses")

        assert result.text == ""
        assert result.tool_calls is None
        assert result.reasoning is None

    def test_text_message(self):
        """Text message is extracted correctly."""
        raw = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "text", "text": "Hello, world!"}],
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.text == "Hello, world!"

    def test_lm_studio_output_text_format(self):
        """LM Studio output_text format is handled."""
        raw = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "LM Studio response"}],
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.text == "LM Studio response"

    def test_multiple_text_blocks(self):
        """Multiple text blocks are concatenated."""
        raw = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": " Part 2"},
                    ],
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.text == "Part 1 Part 2"

    def test_tool_use_extraction(self):
        """Tool use blocks are converted to OpenAI format."""
        raw = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_123",
                            "name": "get_weather",
                            "input": {"city": "NYC"},
                        }
                    ],
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "call_123"
        assert result.tool_calls[0]["type"] == "function"
        assert result.tool_calls[0]["function"]["name"] == "get_weather"
        assert result.tool_calls[0]["function"]["arguments"] == '{"city": "NYC"}'

    def test_reasoning_from_summary_dict(self):
        """Reasoning is extracted from summary.text (OpenAI format)."""
        raw = {
            "output": [
                {
                    "type": "reasoning",
                    "summary": {"text": "I thought about this..."},
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.reasoning == "I thought about this..."

    def test_reasoning_from_summary_string(self):
        """Reasoning is extracted from string summary."""
        raw = {
            "output": [
                {
                    "type": "reasoning",
                    "summary": "Direct reasoning text",
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.reasoning == "Direct reasoning text"

    def test_reasoning_from_lm_studio_format(self):
        """Reasoning is extracted from LM Studio content array."""
        raw = {
            "output": [
                {
                    "type": "reasoning",
                    "summary": {},
                    "content": [
                        {"type": "reasoning_text", "text": "Step 1. "},
                        {"type": "reasoning_text", "text": "Step 2."},
                    ],
                }
            ]
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.reasoning == "Step 1. Step 2."

    def test_response_id_extraction(self):
        """Response ID is extracted for stateful mode."""
        raw = {"id": "resp_abc123", "output": []}
        result = parse_responses_result(raw, "/v1/responses")

        assert result.response_id == "resp_abc123"

    def test_usage_extraction(self):
        """Usage stats are extracted."""
        raw = {
            "output": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        result = parse_responses_result(raw, "/v1/responses")

        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 20

    def test_endpoint_tracking(self):
        """Endpoint used is tracked."""
        raw = {"output": []}
        result = parse_responses_result(raw, "/v1/responses")

        assert result.endpoint_used == "/v1/responses"


class TestParseChatResult:
    """Tests for /v1/chat/completions response parser."""

    def test_empty_choices(self):
        """Empty choices returns empty response."""
        raw = {"choices": []}
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.text == ""
        assert result.finish_reason == "error"

    def test_text_content(self):
        """Text content is extracted correctly."""
        raw = {
            "choices": [{"message": {"content": "Hello, world!"}, "finish_reason": "stop"}]
        }
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.text == "Hello, world!"
        assert result.finish_reason == "stop"

    def test_null_content_handled(self):
        """Null content is handled gracefully."""
        raw = {"choices": [{"message": {"content": None}, "finish_reason": "stop"}]}
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.text == ""

    def test_tool_calls_extraction(self):
        """Tool calls are passed through."""
        tool_calls = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": "{}"},
            }
        ]
        raw = {
            "choices": [
                {"message": {"content": "", "tool_calls": tool_calls}, "finish_reason": "tool_calls"}
            ]
        }
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.tool_calls == tool_calls

    def test_reasoning_field(self):
        """Reasoning field is extracted."""
        raw = {
            "choices": [
                {"message": {"content": "Answer", "reasoning": "My thought process"}, "finish_reason": "stop"}
            ]
        }
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.reasoning == "My thought process"

    def test_reasoning_content_field(self):
        """reasoning_content field is extracted (gpt-oss alternate name)."""
        raw = {
            "choices": [
                {"message": {"content": "Answer", "reasoning_content": "My reasoning"}, "finish_reason": "stop"}
            ]
        }
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.reasoning == "My reasoning"

    def test_usage_extraction(self):
        """Usage stats are extracted."""
        raw = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        }
        result = parse_chat_result(raw, "/v1/chat/completions")

        assert result.usage["prompt_tokens"] == 5
        assert result.usage["total_tokens"] == 15


class TestParseStreamingDelta:
    """Tests for streaming delta parser."""

    def test_responses_content_block_delta(self):
        """Responses API content_block_delta is parsed."""
        delta = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello"},
        }
        result = parse_streaming_delta(delta, "responses")

        assert result["content"] == "Hello"
        assert result["reasoning"] is None

    def test_responses_reasoning_delta(self):
        """Responses API reasoning_delta is parsed."""
        delta = {"type": "reasoning_delta", "delta": {"text": "Thinking..."}}
        result = parse_streaming_delta(delta, "responses")

        assert result["reasoning"] == "Thinking..."
        assert result["content"] is None

    def test_lm_studio_output_text_delta(self):
        """LM Studio response.output_text.delta is parsed."""
        delta = {"type": "response.output_text.delta", "delta": "Some text"}
        result = parse_streaming_delta(delta, "responses")

        assert result["content"] == "Some text"

    def test_lm_studio_reasoning_text_delta(self):
        """LM Studio response.reasoning_text.delta is parsed."""
        delta = {"type": "response.reasoning_text.delta", "delta": "Reasoning..."}
        result = parse_streaming_delta(delta, "responses")

        assert result["reasoning"] == "Reasoning..."

    def test_chat_completions_content(self):
        """Chat completions content delta is parsed."""
        delta = {"content": "Hello"}
        result = parse_streaming_delta(delta, "chat_completions")

        assert result["content"] == "Hello"

    def test_chat_completions_reasoning(self):
        """Chat completions reasoning delta is parsed."""
        delta = {"content": "Answer", "reasoning": "Thought process"}
        result = parse_streaming_delta(delta, "chat_completions")

        assert result["content"] == "Answer"
        assert result["reasoning"] == "Thought process"

    def test_chat_completions_reasoning_content(self):
        """Chat completions reasoning_content delta is parsed."""
        delta = {"reasoning_content": "Native reasoning"}
        result = parse_streaming_delta(delta, "chat_completions")

        assert result["reasoning"] == "Native reasoning"

    def test_chat_completions_tool_calls(self):
        """Chat completions tool_calls delta is parsed."""
        delta = {"tool_calls": [{"id": "call_123"}]}
        result = parse_streaming_delta(delta, "chat_completions")

        assert result["tool_call"] is not None
        assert "call_123" in result["tool_call"]
