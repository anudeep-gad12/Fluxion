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

from .agent_engine import AgentEngine, get_system_prompt_for_query_type
from .query_classifier import QueryClassifier
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
    query: Optional[str] = None,
    provider_override: Optional[object] = None,
    filesystem_enabled: bool = False,
    working_dir: Optional[str] = None,
    approval_callback: Optional[object] = None,
) -> AgentEngine:
    """Create a fully configured AgentEngine.

    Instantiates all dependencies:
    - Provider (or ProviderChain if chain enabled)
    - Tool registry (web_search, web_extract, python_execute)
    - Agent repository (for persistence)

    If query is provided and system_prompt is not explicitly set,
    classifies the query to select an appropriate system prompt
    and tool_choice for calculation-heavy queries.

    Args:
        model_name: Override default model name from config.
        max_steps: Override default max steps (default: 10).
        max_tokens: Override default max tokens from config.
        temperature: Override default temperature from config.
        system_prompt: Override default system prompt.
        query: User query for classification-based prompt selection.
        provider_override: Optional pre-configured LLM provider (e.g., ChatGPTProvider).

    Returns:
        Configured AgentEngine ready for execution.
    """
    config = get_chat_config()

    # Classify query if provided (and system_prompt not explicitly set)
    # Check if classification is enabled in config
    tool_choice = None
    calculation_only = False
    qc_config = getattr(config, "query_classification", None)
    classification_enabled = qc_config.enabled if qc_config else True

    if query and not system_prompt and classification_enabled:
        classifier = QueryClassifier()
        classification = classifier.classify(query)

        system_prompt = get_system_prompt_for_query_type(classification.query_type)
        tool_choice = classification.recommended_tool_choice

        # For high-confidence calculation queries, only provide python_execute
        # This forces the model to use code since it's the ONLY tool available
        from orchestrator.agent.query_classifier import QueryType
        if classification.query_type == QueryType.CALCULATION and tool_choice:
            calculation_only = True

        logger.info(
            "Query classified for agent",
            extra={
                "query_type": classification.query_type.value,
                "confidence": classification.confidence,
                "tool_choice": tool_choice,
                "calculation_only": calculation_only,
                "matched_patterns": classification.matched_patterns[:5],  # Limit for logging
            },
        )
    elif query and not system_prompt:
        # Classification disabled - use default prompt, no tool forcing
        logger.debug("Query classification disabled, using default system prompt")

    # Create provider (use override if provided, otherwise config)
    if provider_override is not None:
        provider = provider_override
    else:
        provider = create_provider(
            config.provider,
            chain_config=config.provider_chain,
        )

    # Create tool registry - for calculation queries, only python_execute
    registry = create_tool_registry(
        config,
        calculation_only=calculation_only,
        filesystem_enabled=filesystem_enabled,
        working_dir=working_dir,
    )

    # Create repositories
    db = await get_db()
    repo = AgentRepo(db)
    trace_repo = TraceRepo(db)

    # Augment system prompt when filesystem tools are enabled
    if filesystem_enabled:
        fs_addendum = """

=== FILESYSTEM TOOLS ===

You also have LOCAL filesystem tools for working with the user's codebase:
- read_file: Read file contents (with line numbers, offset/limit)
- list_directory: List directory tree (respects .gitignore)
- glob: Find files by pattern (e.g. "**/*.py")
- grep: Search file contents with regex
- write_file: Create or overwrite files
- edit_file: Make precise edits (exact string replacement)
- bash: Run shell commands

IMPORTANT:
- Use read_file/grep/glob for reading code. Do NOT use python_execute for local files.
- python_execute runs in a REMOTE sandbox — it cannot access the local filesystem.
- Filesystem tools operate relative to the working directory.
- For reading files, prefer read_file over bash cat.
- For searching, prefer grep over bash grep.
"""
        if system_prompt:
            system_prompt = system_prompt + fs_addendum
        else:
            system_prompt = AgentEngine.DEFAULT_SYSTEM_PROMPT + fs_addendum
        # Fix the "ONLY three tools" claim in the default prompt
        system_prompt = system_prompt.replace(
            "You have ONLY three tools available (no others exist):",
            "You have the following tools available:",
        )
        system_prompt = system_prompt.replace(
            "You have ONLY three tools (no others exist):",
            "You have the following tools available:",
        )

    # Get planning config
    planning_config = getattr(config, "agent_planning", None)
    planning_enabled = planning_config.enabled if planning_config else True
    max_plan_steps = planning_config.max_plan_steps if planning_config else 5

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
        tool_choice=tool_choice,
        max_context_tokens=config.context.max_tokens,
        slow_response_threshold=config.provider.slow_response_threshold,
        planning_enabled=planning_enabled,
        max_plan_steps=max_plan_steps,
        approval_callback=approval_callback,
    )

    logger.info(
        "AgentEngine created",
        extra={
            "model": engine._model_name,
            "max_steps": engine._max_steps,
            "tools": registry.tool_names,
            "tool_choice": tool_choice,
        },
    )

    return engine
