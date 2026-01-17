"""Base types and protocols for LLM providers."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


# =============================================================================
# Exceptions
# =============================================================================


class ProviderError(Exception):
    """Base exception for provider errors."""

    pass


class RetryExhaustedError(ProviderError):
    """Raised when all retry attempts have been exhausted."""

    pass


class ToolFallbackError(ProviderError):
    """Raised when tool use requires /v1/responses but server doesn't support it."""

    pass


# =============================================================================
# Response Types
# =============================================================================


@dataclass
class LLMResponse:
    """Normalized response from any endpoint.

    This provides a unified interface regardless of whether the response
    came from /v1/responses or /v1/chat/completions.
    """

    text: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning: Optional[str] = None
    response_id: Optional[str] = None  # ID from /v1/responses for stateful mode
    raw: Dict[str, Any] = field(default_factory=dict)
    endpoint_used: str = ""  # "/v1/responses" or "/v1/chat/completions"
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


# =============================================================================
# Provider Protocol
# =============================================================================


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers.

    All providers must implement this interface to ensure portability
    across different backends (LM Studio, OpenAI, vLLM, etc.).
    """

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        previous_response_id: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete a conversation.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name/ID.
            instructions: System prompt (used as 'instructions' in /v1/responses).
            tools: List of tool definitions for function calling.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            reasoning_effort: Native reasoning effort for gpt-oss ("low", "medium", "high").
            stream: Whether to stream the response.
            previous_response_id: Response ID from previous call for stateful mode.
            **kwargs: Additional provider-specific parameters.

        Returns:
            Normalized LLMResponse.
        """
        ...

    async def complete_streaming(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        on_token: Callable[[str], None],
        on_reasoning: Optional[Callable[[str], None]] = None,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        previous_response_id: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Stream a completion, calling callbacks for each token.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            on_token: Callback for each content token.
            on_reasoning: Callback for reasoning tokens (native reasoning).
            instructions: System prompt.
            tools: Tool definitions.
            tool_choice: Tool selection behavior (auto, required, or tool_name).
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            reasoning_effort: Native reasoning effort.
            previous_response_id: Response ID from previous call for stateful mode.
            **kwargs: Additional parameters.

        Returns:
            Final LLMResponse after streaming completes.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the provider is healthy and reachable.

        Returns:
            True if healthy, False otherwise.
        """
        ...

    async def close(self) -> None:
        """Clean up provider resources."""
        ...
