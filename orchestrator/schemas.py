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


class ConversationDetailResponse(BaseModel):
    """Conversation with runs."""
    conversation: ConversationResponse
    runs: list[RunResponse]


class UpdateConversationRequest(BaseModel):
    """Request to update a conversation."""
    title: Optional[str] = None
    status: Optional[str] = None


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
    )
