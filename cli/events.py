"""Custom Textual Message types for SSE event handling.

Each SSE event from the backend is translated into a Textual Message
and posted to the widget tree for thread-safe UI updates.
"""

from textual.message import Message


class AgentEvent(Message):
    """Base class for agent SSE events."""

    def __init__(self, data: dict) -> None:
        super().__init__()
        self.data = data


class StepStartEvent(AgentEvent):
    """Agent started a new step."""
    pass


class ThinkingEvent(AgentEvent):
    """Thinking/reasoning token received."""
    pass


class ToolStartEvent(AgentEvent):
    """Tool execution started."""
    pass


class ToolApprovalRequiredEvent(AgentEvent):
    """Tool needs user approval before execution."""
    pass


class ToolResultEvent(AgentEvent):
    """Tool execution completed."""
    pass


class AnswerTokenEvent(AgentEvent):
    """Answer token received (streaming)."""
    pass


class AgentCompleteEvent(AgentEvent):
    """Agent run completed."""
    pass


class AgentErrorEvent(AgentEvent):
    """Agent run errored."""
    pass


class AgentStateEvent(AgentEvent):
    """Agent state change (initializing, synthesizing, etc.)."""
    pass


class HeartbeatEvent(AgentEvent):
    """SSE heartbeat."""
    pass
