"""Factory for creating LLM providers from configuration."""

from typing import TYPE_CHECKING

from .base import LLMProvider
from .openai_compat import OpenAICompatProvider

if TYPE_CHECKING:
    from orchestrator.config import ProviderConfig


def create_provider(config: "ProviderConfig") -> LLMProvider:
    """Create an LLM provider from configuration.

    All providers are OpenAI-compatible, so we always use OpenAICompatProvider.
    The config determines endpoint selection, auth, retry behavior, etc.

    Args:
        config: Provider configuration with base_url, api_key, endpoint, etc.

    Returns:
        LLMProvider instance ready to use.
    """
    return OpenAICompatProvider(
        base_url=config.base_url,
        api_key=config.api_key,
        endpoint=config.endpoint,
        fallback_on_404=config.fallback_on_404,
        timeout=config.timeout,
        max_retries=config.max_retries,
        base_delay=config.base_delay,
        max_delay=config.max_delay,
        retryable_statuses=config.retryable_statuses,
        extra_headers=config.extra_headers,
    )
