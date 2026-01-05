"""Factory for creating configured AgentEngine instances.

This module provides a single entry point for creating AgentEngine
instances with all required dependencies (provider, repository, registry).
"""

from typing import TYPE_CHECKING, Optional

from orchestrator.config import get_chat_config
from orchestrator.logging_config import get_logger
from orchestrator.providers.factory import create_provider
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo

from .agent_engine import AgentEngine
from .tools import create_tool_registry

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


async def create_agent_engine(
    model_name: Optional[str] = None,
    max_steps: Optional[int] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    system_prompt: Optional[str] = None,
) -> AgentEngine:
    """Create a fully configured AgentEngine.

    Instantiates all dependencies:
    - Provider (or ProviderChain if chain enabled)
    - Tool registry (web_search, web_extract, python_execute)
    - Agent repository (for persistence)

    Args:
        model_name: Override default model name from config.
        max_steps: Override default max steps (default: 10).
        max_tokens: Override default max tokens from config.
        temperature: Override default temperature from config.
        system_prompt: Override default system prompt.

    Returns:
        Configured AgentEngine ready for execution.
    """
    config = get_chat_config()

    # Create provider (with chain if configured)
    provider = create_provider(
        config.provider,
        chain_config=config.provider_chain,
    )

    # Create tool registry with configured tools
    registry = create_tool_registry(config)

    # Create repositories
    db = await get_db()
    repo = AgentRepo(db)
    trace_repo = TraceRepo(db)

    # Build engine with overrides
    engine = AgentEngine(
        provider=provider,
        repo=repo,
        registry=registry,
        trace_repo=trace_repo,
        model_name=model_name or config.model.name,
        max_steps=max_steps or 10,
        max_tokens=max_tokens or config.model.max_tokens,
        temperature=temperature or config.model.temperature,
        system_prompt=system_prompt,
    )

    logger.info(
        "AgentEngine created",
        extra={
            "model": engine._model_name,
            "max_steps": engine._max_steps,
            "tools": registry.tool_names,
        },
    )

    return engine
