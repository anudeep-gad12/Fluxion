"""Pydantic schemas for API requests and responses."""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ==================== Run Schemas ====================

class CreateRunRequest(BaseModel):
    """Request to create a new run."""
    prompt: str
    mode: str = "chat"
    profile: str = "chat"


class CreateRunResponse(BaseModel):
    """Response from creating a run."""
    run_id: str
    stream_url: str


class RunResponse(BaseModel):
    """Full run details."""
    run_id: str
    created_at: str
    status: str
    mode: str = "chat"
    profile: str = "chat"
    prompt: str = ""
    user_message: Optional[str] = None
    conversation_id: Optional[str] = None
    conversation_summary: Optional[str] = None
    final_answer: Optional[str] = None
    final_report: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    # Thinking data for CoT mode
    thinking_summary: Optional[str] = None


class RunListResponse(BaseModel):
    """List of runs."""
    runs: list[RunResponse]
    total: int


class EventResponse(BaseModel):
    """Event response."""
    run_id: str
    seq: int
    ts: str
    type: str
    display: dict[str, Any]
    payload: dict[str, Any]


# ==================== Conversation Schemas ====================

class ConversationResponse(BaseModel):
    """Conversation metadata."""
    conversation_id: str
    created_at: str
    title: Optional[str] = None
    summary: Optional[str] = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationListResponse(BaseModel):
    """List of conversations."""
    conversations: list[ConversationResponse]
    total: int


class CreateConversationRequest(BaseModel):
    """Request to create a conversation."""
    title: Optional[str] = None


class CreateConversationResponse(BaseModel):
    """Response from creating a conversation."""
    conversation_id: str


class CreateConversationRunRequest(BaseModel):
    """Request to add a run to a conversation."""
    message: str
    thinking_mode: str = "default"  # "default" or "thinking" (maps to strategy via config)
    reasoning_effort: Optional[str] = None  # "low", "medium", "high" for native reasoning models


class ConversationDetailResponse(BaseModel):
    """Conversation with runs."""
    conversation: ConversationResponse
    runs: list[RunResponse]


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""
    title: Optional[str] = None
    status: Optional[str] = None


# ==================== Tool Use Schemas ====================

class ToolFunction(BaseModel):
    """Function definition for a tool call."""
    name: str
    arguments: str  # JSON-encoded arguments


class ToolCall(BaseModel):
    """A tool call from the model.

    Represents a function call the model wants to make.
    Compatible with OpenAI's tool_calls format.
    """
    id: str
    type: str = "function"
    function: ToolFunction


class ToolResponse(BaseModel):
    """Response from a tool execution.

    Used to send tool results back to the model.
    """
    tool_call_id: str
    role: str = "tool"
    content: str  # JSON-encoded result or error message


class ToolDefinition(BaseModel):
    """Definition of a tool available to the model.

    Compatible with OpenAI's tools format.
    """
    type: str = "function"
    function: dict[str, Any]  # {name, description, parameters}


# ==================== Trace Event Schemas ====================

class TraceEventResponse(BaseModel):
    """A trace event in a run timeline."""
    id: str
    run_id: str
    seq: int
    created_at: str
    event_type: str  # llm_request | llm_response | reasoning | tool_call | tool_response | error | retry
    event_status: str  # pending | success | error | skipped
    actor: str  # model | system | tool:<name>
    endpoint: Optional[str] = None
    attempt: int = 1
    content: dict[str, Any] = Field(default_factory=dict)
    parent_event_id: Optional[str] = None
    step_number: Optional[int] = None
    duration_ms: Optional[int] = None
    token_count: Optional[int] = None
    error_message: Optional[str] = None


class RunTimelineResponse(BaseModel):
    """Complete timeline for a run with all events."""
    run_id: str
    status: str
    created_at: str
    events: list[TraceEventResponse]
    total_events: int


# ==================== Helpers ====================

def trace_to_run(trace: dict) -> RunResponse:
    """Convert a trace dict to RunResponse."""
    return RunResponse(
        run_id=trace.get("run_id", ""),
        created_at=trace.get("created_at", ""),
        status=trace.get("status", "unknown"),
        mode=trace.get("mode", "chat"),
        profile=trace.get("profile_name", "chat"),
        prompt=trace.get("user_message", ""),
        user_message=trace.get("user_message"),
        conversation_id=trace.get("conversation_id"),
        final_answer=trace.get("final_answer"),
        error_detail=trace.get("error_message"),
        thinking_summary=trace.get("thinking_summary"),
    )
