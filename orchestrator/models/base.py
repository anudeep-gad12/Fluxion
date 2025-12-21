"""Base interfaces for model clients."""

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class Message:
    """A message in a conversation."""

    role: str  # system, user, assistant
    content: str


@dataclass
class ModelResponse:
    """Response from a model completion."""

    content: str
    raw: dict[str, Any]
    finish_reason: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0

    @property
    def is_complete(self) -> bool:
        """Check if the response completed normally."""
        return self.finish_reason in ("stop", "end_turn")


@runtime_checkable
class ModelClient(Protocol):
    """Protocol for model clients."""

    @property
    def endpoint(self) -> str:
        """Get the model endpoint URL."""
        ...

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        json_mode: bool = False,
        stop: Optional[list[str]] = None,
    ) -> ModelResponse:
        """Complete a conversation.

        Args:
            messages: Conversation history
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            json_mode: Request JSON output
            stop: Stop sequences

        Returns:
            Model response
        """
        ...

    async def health_check(self) -> bool:
        """Check if the model endpoint is healthy."""
        ...
