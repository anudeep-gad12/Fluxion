"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError
from orchestrator.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    RunResponse,
    ConversationResponse,
    CreateConversationRequest,
    CreateConversationRunRequest,
    ToolCall,
    ToolFunction,
    ToolDefinition,
    trace_to_run,
)


class TestCreateRunRequest:
    """Tests for CreateRunRequest schema."""

    def test_minimal_request(self):
        """Minimal request with only required field."""
        request = CreateRunRequest(prompt="Hello")

        assert request.prompt == "Hello"
        assert request.mode == "chat"
        assert request.profile == "chat"

    def test_custom_mode_and_profile(self):
        """Custom mode and profile are accepted."""
        request = CreateRunRequest(prompt="Hello", mode="custom", profile="custom")

        assert request.mode == "custom"
        assert request.profile == "custom"


class TestCreateRunResponse:
    """Tests for CreateRunResponse schema."""

    def test_response_fields(self):
        """Response has required fields."""
        response = CreateRunResponse(
            run_id="run-123", stream_url="/api/runs/run-123/stream"
        )

        assert response.run_id == "run-123"
        assert response.stream_url == "/api/runs/run-123/stream"


class TestRunResponse:
    """Tests for RunResponse schema."""

    def test_minimal_response(self):
        """Minimal response with required fields."""
        response = RunResponse(
            run_id="run-123",
            created_at="2024-01-01T00:00:00Z",
            status="succeeded",
        )

        assert response.run_id == "run-123"
        assert response.status == "succeeded"
        assert response.final_answer is None

    def test_full_response(self):
        """Full response with all optional fields."""
        response = RunResponse(
            run_id="run-123",
            created_at="2024-01-01T00:00:00Z",
            status="succeeded",
            mode="chat",
            profile="chat",
            prompt="Hello",
            user_message="Hello",
            conversation_id="conv-123",
            final_answer="Hi there!",
            thinking_summary="I thought about it...",
            usage={"total_tokens": 123},
            stored_context={"stored_tokens": 45},
        )

        assert response.final_answer == "Hi there!"
        assert response.thinking_summary == "I thought about it..."
        assert response.conversation_id == "conv-123"
        assert response.usage == {"total_tokens": 123}
        assert response.stored_context == {"stored_tokens": 45}


class TestConversationResponse:
    """Tests for ConversationResponse schema."""

    def test_minimal_response(self):
        """Minimal response with required fields."""
        response = ConversationResponse(
            conversation_id="conv-123",
            created_at="2024-01-01T00:00:00Z",
            status="active",
        )

        assert response.conversation_id == "conv-123"
        assert response.status == "active"
        assert response.metadata == {}

    def test_with_metadata(self):
        """Response with metadata."""
        response = ConversationResponse(
            conversation_id="conv-123",
            created_at="2024-01-01T00:00:00Z",
            status="active",
            metadata={"key": "value"},
        )

        assert response.metadata == {"key": "value"}


class TestCreateConversationRequest:
    """Tests for CreateConversationRequest schema."""

    def test_empty_request(self):
        """Request with no fields."""
        request = CreateConversationRequest()
        assert request.title is None

    def test_with_title(self):
        """Request with title."""
        request = CreateConversationRequest(title="My Conversation")
        assert request.title == "My Conversation"


class TestCreateConversationRunRequest:
    """Tests for CreateConversationRunRequest schema."""

    def test_minimal_request(self):
        """Minimal request with message only."""
        request = CreateConversationRunRequest(message="Hello")

        assert request.message == "Hello"
        assert request.thinking_mode == "default"
        assert request.reasoning_effort is None

    def test_thinking_mode(self):
        """Request with thinking mode."""
        request = CreateConversationRunRequest(
            message="Hello", thinking_mode="thinking"
        )

        assert request.thinking_mode == "thinking"

    def test_reasoning_effort(self):
        """Request with reasoning effort."""
        request = CreateConversationRunRequest(
            message="Hello", reasoning_effort="high"
        )

        assert request.reasoning_effort == "high"


class TestToolSchemas:
    """Tests for tool-related schemas."""

    def test_tool_function(self):
        """ToolFunction validation."""
        func = ToolFunction(name="get_weather", arguments='{"city": "NYC"}')

        assert func.name == "get_weather"
        assert func.arguments == '{"city": "NYC"}'

    def test_tool_call(self):
        """ToolCall validation."""
        call = ToolCall(
            id="call_123",
            function=ToolFunction(name="get_weather", arguments="{}"),
        )

        assert call.id == "call_123"
        assert call.type == "function"
        assert call.function.name == "get_weather"

    def test_tool_definition(self):
        """ToolDefinition validation."""
        definition = ToolDefinition(
            function={
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object"},
            }
        )

        assert definition.type == "function"
        assert definition.function["name"] == "get_weather"


class TestTraceToRun:
    """Tests for trace_to_run helper."""

    def test_minimal_trace(self):
        """Convert minimal trace dict."""
        trace = {
            "run_id": "run-123",
            "created_at": "2024-01-01T00:00:00Z",
            "status": "succeeded",
        }

        run = trace_to_run(trace)

        assert run.run_id == "run-123"
        assert run.status == "succeeded"

    def test_full_trace(self):
        """Convert full trace dict."""
        trace = {
            "run_id": "run-123",
            "created_at": "2024-01-01T00:00:00Z",
            "status": "succeeded",
            "mode": "chat",
            "profile_name": "custom",
            "user_message": "Hello",
            "conversation_id": "conv-123",
            "final_answer": "Hi!",
            "thinking_summary": "Thinking...",
            "error_message": None,
            "usage": {
                "usage": {"total_tokens": 123},
                "stored_context": {"stored_tokens": 45},
                "context_profile": {"context_window": 200000},
            },
        }

        run = trace_to_run(trace)

        assert run.profile == "custom"
        assert run.user_message == "Hello"
        assert run.final_answer == "Hi!"
        assert run.thinking_summary == "Thinking..."
        assert run.usage == {"total_tokens": 123}
        assert run.stored_context == {"stored_tokens": 45}

    def test_missing_fields_use_defaults(self):
        """Missing fields use defaults."""
        trace = {}

        run = trace_to_run(trace)

        assert run.run_id == ""
        assert run.status == "unknown"
        assert run.mode == "chat"

    def test_chat_usage_stats_are_normalized_for_run_response(self):
        """Chat-style usage stats still expose total_tokens on runs."""
        trace = {
            "run_id": "run-123",
            "created_at": "2024-01-01T00:00:00Z",
            "status": "succeeded",
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "thinking_tokens": 4,
                "total_tokens": 30,
            },
        }

        run = trace_to_run(trace)

        assert run.usage == {
            "input_tokens": 20,
            "output_tokens": 10,
            "reasoning_tokens": 4,
            "cached_tokens": 0,
            "total_tokens": 30,
        }
