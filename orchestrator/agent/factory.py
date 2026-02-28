"""Factory for creating configured AgentEngine instances.

This module provides a single entry point for creating AgentEngine
instances with all required dependencies (provider, repository, registry).

Supports profile-based configuration:
- "research": Web research agent (default, backward compatible)
- "coding": Coding assistant with filesystem tools and project context
"""

from typing import TYPE_CHECKING, Optional

from orchestrator.config import get_chat_config
from orchestrator.logging_config import get_logger
from orchestrator.providers.factory import create_provider
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo

from .agent_engine import AgentEngine, get_system_prompt_for_query_type
from .context import get_context_strategy
from .profile import get_profile
from .query_classifier import QueryClassifier
from .tools import create_tool_registry
from .tools.registry import create_tool_registry_from_profile

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
    profile_name: Optional[str] = None,
    python_provider: Optional[str] = None,
) -> AgentEngine:
    """Create a fully configured AgentEngine.

    Instantiates all dependencies:
    - Provider (or ProviderChain if chain enabled)
    - Tool registry (based on profile or legacy flags)
    - Agent repository (for persistence)
    - Context strategy (gathers project info for system prompt)

    If profile_name is provided, it drives tool selection, system prompt,
    planning, and context gathering. Otherwise falls back to legacy behavior
    with filesystem_enabled flag.

    Args:
        model_name: Override default model name from config.
        max_steps: Override default max steps (default: 10).
        max_tokens: Override default max tokens from config.
        temperature: Override default temperature from config.
        system_prompt: Override default system prompt.
        query: User query for classification-based prompt selection.
        provider_override: Optional pre-configured LLM provider.
        filesystem_enabled: Legacy flag — True maps to profile="coding".
        working_dir: Working directory for filesystem/coding tools.
        approval_callback: Callback for tool approval permission system.
        profile_name: Agent profile ("research", "coding").

    Returns:
        Configured AgentEngine ready for execution.
    """
    config = get_chat_config()

    # Resolve profile: explicit profile_name takes precedence,
    # then filesystem_enabled=True maps to "coding", else "research"
    if profile_name is None:
        profile_name = "coding" if filesystem_enabled else "research"

    profile = get_profile(profile_name)

    # Classify query if provided (and system_prompt not explicitly set)
    tool_choice = None
    calculation_only = False
    qc_config = getattr(config, "query_classification", None)
    classification_enabled = qc_config.enabled if qc_config else True

    if query and not system_prompt and classification_enabled:
        classifier = QueryClassifier()
        classification = classifier.classify(query)

        # Only use query classification for research profile
        if profile.name == "research":
            system_prompt = get_system_prompt_for_query_type(classification.query_type)

        tool_choice = classification.recommended_tool_choice

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
                "matched_patterns": classification.matched_patterns[:5],
                "profile": profile.name,
            },
        )
    elif query and not system_prompt:
        logger.debug("Query classification disabled, using default system prompt")

    # Create provider (use override if provided, otherwise config)
    if provider_override is not None:
        provider = provider_override
    else:
        provider = create_provider(
            config.provider,
            chain_config=config.provider_chain,
        )

    # Create tool registry from profile
    registry = create_tool_registry_from_profile(
        config, profile, working_dir, python_provider=python_provider,
    )

    # Create repositories
    db = await get_db()
    repo = AgentRepo(db)
    trace_repo = TraceRepo(db)

    # Gather context using the profile's context strategy
    strategy = get_context_strategy(profile.context_strategy)
    project_context = await strategy.gather(working_dir)

    # Build system prompt from profile template (unless explicitly overridden)
    if not system_prompt:
        # For research profile, the date_context IS the project_context
        # (ResearchContextStrategy returns date + cutoff)
        if profile.context_strategy == "research":
            system_prompt = profile.system_prompt_template.format(
                date_context=project_context,
                project_context="",
            )
        else:
            # For coding/full, gather date context separately
            from datetime import date
            today = date.today()
            date_context = (
                f"Current date: {today.strftime('%B %d, %Y')}\n"
                f"Your knowledge cutoff: June 2024. For information after this date, use web_search."
            )
            system_prompt = profile.system_prompt_template.format(
                date_context=date_context,
                project_context=project_context,
            )

    # Get planning config
    planning_config = getattr(config, "agent_planning", None)
    planning_enabled = planning_config.enabled if planning_config else True
    max_plan_steps = planning_config.max_plan_steps if planning_config else profile.max_plan_steps

    # Detect provider context capacity
    if provider_override and hasattr(provider_override, '_default_model'):
        model = provider_override._default_model
        if 'gpt-5' in model or 'codex' in model:
            max_context = 250000  # GPT-5.2 has 400k, reserve 128k for output + 22k buffer
        else:
            max_context = config.context.max_tokens
    else:
        max_context = config.context.max_tokens

    # Build engine with overrides
    engine = AgentEngine(
        provider=provider,
        repo=repo,
        registry=registry,
        trace_repo=trace_repo,
        model_name=model_name or config.model.name,
        max_steps=max_steps or profile.max_steps,
        max_tokens=max_tokens or config.model.max_tokens,
        temperature=temperature or config.model.temperature,
        system_prompt=system_prompt,
        tool_choice=tool_choice,
        max_context_tokens=max_context,
        slow_response_threshold=config.provider.slow_response_threshold,
        planning_enabled=planning_enabled,
        max_plan_steps=max_plan_steps,
        approval_callback=approval_callback,
        profile=profile,
        reasoning_effort=getattr(config.model, "reasoning_effort", None),
    )

    logger.info(
        "AgentEngine created",
        extra={
            "model": engine._model_name,
            "max_steps": engine._max_steps,
            "tools": registry.tool_names,
            "tool_choice": tool_choice,
            "profile": profile.name,
        },
    )

    return engine
