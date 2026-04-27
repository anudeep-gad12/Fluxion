"""Pydantic schemas for API requests and responses."""

from enum import Enum
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
    # llm_request | llm_response | reasoning | tool_call | tool_response | error | retry
    event_type: str
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


# ==================== Agent Schemas ====================


class AgentStepState(str, Enum):
    """State of an agent step."""

    PLANNING = "planning"
    TOOL_CALLING = "tool_calling"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
    ERROR = "error"


class AgentToolCallStatus(str, Enum):
    """Status of an agent tool call."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


class AgentCapabilities(BaseModel):
    """Tool capabilities enabled for a browser agent run."""

    web: bool = True
    filesystem: bool = False
    bash: bool = False
    python: bool = False


class AgentStepResponse(BaseModel):
    """Agent step details."""

    id: str
    run_id: str
    step_number: int
    state: str
    thinking_text: Optional[str] = None
    decision: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class AgentToolCallResponse(BaseModel):
    """Agent tool call details."""

    id: str
    run_id: str
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: str
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    idempotency_key: str
    execution_attempt: int = 1
    approval_decision: Optional[str] = None
    approval_policy: Optional[str] = None
    approval_decided_at: Optional[str] = None
    result_detail: Optional[str] = None


class AgentCitationResponse(BaseModel):
    """Agent citation details."""

    id: str
    run_id: str
    tool_call_id: str
    source_url: str
    title: Optional[str] = None
    snippet: str
    used_in_answer: bool = False
    created_at: str




class ModelPricingResponse(BaseModel):
    """Known pricing metadata for an active model."""

    input_cost_per_million: Optional[float] = None
    cached_input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None


class ModelContextProfileResponse(BaseModel):
    """Normalized active model context profile."""

    provider_name: str
    model_id: str
    display_name: str
    context_window: int
    max_output_tokens: int
    effective_input_budget: int
    supports_tools: bool
    supports_reasoning: bool
    pricing: ModelPricingResponse = Field(default_factory=ModelPricingResponse)
    source: str


class AgentSystemEventResponse(BaseModel):
    """Visible system event for an agent run timeline."""

    event_type: str
    message: str
    step_number: Optional[int] = None
    seq: Optional[int] = None
    created_at: Optional[str] = None


class CreateAgentRunRequest(BaseModel):
    """Request to start an agent run."""

    query: str
    conversation_id: Optional[str] = None
    max_steps: int = 1000
    workspace_path: Optional[str] = None
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    filesystem_enabled: bool = False
    working_dir: Optional[str] = None
    permission_policy: str = "strict"
    profile: Optional[str] = None  # "research", "coding" — overrides filesystem_enabled
    python_provider: Optional[str] = (
        None  # "local" or "daytona" — overrides PYTHON_PROVIDER env var
    )


class CreateAgentRunResponse(BaseModel):
    """Response from creating an agent run."""

    run_id: str
    status: str
    stream_url: str
    stream_token: str
    conversation_id: Optional[str] = None


class AgentRunStatusResponse(BaseModel):
    """Agent run status."""

    run_id: str
    status: str
    agent_state: Optional[str] = None
    current_step: int = 0
    total_steps: Optional[int] = None  # Final step count when run completes
    max_steps: int = 1000
    final_answer: Optional[str] = None
    error_message: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    cost: Optional[dict[str, Any]] = None
    context_usage: Optional[dict[str, Any]] = None
    context_profile: Optional[ModelContextProfileResponse] = None
    compaction_count: int = 0
    last_compacted_at_step: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None


class RunArtifactResponse(BaseModel):
    """File change or command execution artifact."""

    id: str
    run_id: str
    artifact_type: str
    file_path: Optional[str] = None
    action: str
    detail: Optional[str] = None
    tool_call_id: Optional[str] = None
    created_at: str


class AgentRunTraceResponse(BaseModel):
    """Full trace of an agent run."""

    run_id: str
    status: str
    agent_state: Optional[str] = None
    steps: list[AgentStepResponse]
    tool_calls: list[AgentToolCallResponse]
    citations: list[AgentCitationResponse]
    artifacts: list[RunArtifactResponse] = []
    system_events: list[AgentSystemEventResponse] = []
    final_answer: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    cost: Optional[dict[str, Any]] = None
    context_usage: Optional[dict[str, Any]] = None
    context_profile: Optional[ModelContextProfileResponse] = None
    compaction_count: int = 0
    last_compacted_at_step: Optional[int] = None


# ==================== Local Model Schemas ====================


class LocalModelSchema(BaseModel):
    """A local model available on disk (GGUF or MLX)."""

    path: str
    name: str
    size_bytes: int
    model_type: str = "gguf"
    size_display: str


class StartModelRequest(BaseModel):
    """Request to start llama-server with a local model."""

    model_path: str
    ctx_size: Optional[int] = None  # None = use config context.max_tokens


class ModelStatusResponse(BaseModel):
    """Current provider status."""

    provider: str  # "local" or "cloud"
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    local_running: bool = False
    context_window: int = 32768
    max_output_tokens: int = 8192
    effective_input_budget: int = 24576
    supports_tools: bool = True
    supports_reasoning: bool = False
    source: str = "config_fallback"


class SelectModelRequest(BaseModel):
    """Request to select a model from the registry."""

    model: str  # Model alias, full ID, or "provider:model" string


class CustomProviderRequest(BaseModel):
    """Request to select a custom OpenAI-compatible provider."""

    name: str = "custom"
    base_url: str
    api_key: Optional[str] = None
    model: str
    context_window: int = 32768
    max_output_tokens: int = 8192
    supports_tools: bool = True
    supports_reasoning: bool = False
    input_cost_per_million: Optional[float] = None
    cached_input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None


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
