"""LLM providers with OpenAI-compatible API support.

This module provides a portable LLM provider abstraction that works with:
- LM Studio (local)
- vLLM
- Ollama
- OpenAI
- Azure OpenAI
- Any other OpenAI-compatible API

Usage:
    from orchestrator.providers import create_provider, LLMResponse

    provider = create_provider(config.provider)
    response = await provider.complete(messages, model)
"""

from .base import (
    LLMProvider,
    LLMResponse,
    ProviderError,
    RetryExhaustedError,
    ToolFallbackError,
)
from .chain import AllProvidersFailedError, ChainedProvider, ProviderChain
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from .factory import create_provider
from .openai_compat import OpenAICompatProvider, normalize_base_url
from .request_builders import build_chat_completions_request, build_responses_request
from .response_parsers import parse_chat_result, parse_responses_result

__all__ = [
    # Core types
    "LLMProvider",
    "LLMResponse",
    # Exceptions
    "ProviderError",
    "RetryExhaustedError",
    "ToolFallbackError",
    "AllProvidersFailedError",
    # Factory
    "create_provider",
    # Provider implementations
    "OpenAICompatProvider",
    "ProviderChain",
    "ChainedProvider",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    # Utilities
    "normalize_base_url",
    "build_responses_request",
    "build_chat_completions_request",
    "parse_responses_result",
    "parse_chat_result",
]
