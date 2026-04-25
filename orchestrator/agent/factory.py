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
from .tools import create_tool_registry  # noqa: F401 - compatibility for existing tests
from .tools.registry import create_browser_agent_tool_registry, create_tool_registry_from_profile

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
    permission_policy: str = "strict",
    profile_name: Optional[str] = None,
    python_provider: Optional[str] = None,
    agent_capabilities: Optional[dict] = None,
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
        permission_policy: Tool permission policy ("strict", "relaxed", "yolo").
        profile_name: Internal agent profile ("research", "coding").
        agent_capabilities: Browser-owned tool capability flags.

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

    # Per-request model metadata resolution via registry.
    # Only use registry when the model is a KNOWN preset (has aliases/model_id match).
    # Unknown models fall through to config.provider which reads LLM_BASE_URL/LLM_API_KEY.
    resolved_model = None
    resolve_name = model_name or config.model.name
    if resolve_name:
        try:
            from orchestrator.models.registry import (
                _ALIAS_INDEX,
                _MODEL_ID_INDEX,
                ModelRegistry,
            )

            # Only resolve if model is actually in the registry (preset match).
            # If a known preset is selected but its key is missing, surface that
            # configuration error instead of falling through to an unauthenticated
            # raw HTTP request that fails later as a cryptic provider 401.
            lower_name = resolve_name.strip().lower()
            if lower_name in _ALIAS_INDEX or lower_name in _MODEL_ID_INDEX:
                resolved_model = ModelRegistry.resolve(resolve_name)
        except ValueError:
            raise
        except Exception:
            logger.warning(
                "Failed to resolve known model metadata; using config provider",
                extra={"model": resolve_name},
                exc_info=True,
            )

    # Create provider (use override if provided, resolved model, or config)
    if provider_override is not None:
        provider = provider_override
    elif resolved_model:
        from orchestrator.providers.factory import create_provider_for_model

        provider, _ = create_provider_for_model(resolve_name)
    else:
        provider = create_provider(
            config.provider,
            chain_config=config.provider_chain,
        )

    # Create tool registry. Browser agent runs are capability-based and are
    # intentionally not modeled as CLI/TUI profiles.
    if agent_capabilities is not None:
        registry = create_browser_agent_tool_registry(
            config,
            agent_capabilities,
            working_dir,
            python_provider=python_provider,
        )
    else:
        registry = create_tool_registry_from_profile(
            config,
            profile,
            working_dir,
            python_provider=python_provider,
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
                "Your knowledge cutoff: June 2024. For information after this date, "
                "use web_search."
            )
            system_prompt = profile.system_prompt_template.format(
                date_context=date_context,
                project_context=project_context,
            )

    # Get planning config
    planning_config = getattr(config, "agent_planning", None)
    max_plan_steps = planning_config.max_plan_steps if planning_config else profile.max_plan_steps

    # Detect provider context capacity (resolved_model set above)
    if resolved_model:
        max_context = resolved_model.context_window
    elif provider_override and hasattr(provider_override, "_context_window"):
        max_context = int(getattr(provider_override, "_context_window"))
    elif provider_override and hasattr(provider_override, "_default_model"):
        model = provider_override._default_model
        if "gpt-5" in model or "codex" in model:
            max_context = 250000  # GPT-5.2 has 400k, reserve 128k for output + 22k buffer
        else:
            max_context = config.context.max_tokens
    else:
        max_context = config.context.max_tokens

    # Resolve model name, temperature, and reasoning per-request
    if resolved_model:
        effective_model = resolved_model.model_id
        effective_temp = temperature or resolved_model.temperature
        effective_max_tokens = max_tokens or resolved_model.max_output_tokens
        effective_reasoning = resolved_model.reasoning_effort
        effective_reasoning_request_param = resolved_model.reasoning_request_param
        input_cost_per_million = resolved_model.input_cost_per_million
        cached_input_cost_per_million = resolved_model.cached_input_cost_per_million
        output_cost_per_million = resolved_model.output_cost_per_million
    else:
        effective_model = model_name or config.model.name
        effective_temp = temperature or config.model.temperature
        provider_max_output = getattr(provider_override, "_max_output_tokens", None)
        effective_max_tokens = max_tokens or provider_max_output or config.model.max_tokens
        effective_reasoning = getattr(config.model, "reasoning_effort", None)
        effective_reasoning_request_param = getattr(
            provider_override,
            "_reasoning_request_param",
            None,
        )
        input_cost_per_million = getattr(provider_override, "_input_cost_per_million", None)
        cached_input_cost_per_million = getattr(
            provider_override, "_cached_input_cost_per_million", None
        )
        output_cost_per_million = getattr(provider_override, "_output_cost_per_million", None)

    effective_max_steps = max_steps if max_steps is not None else 10

    # Build engine with overrides
    engine = AgentEngine(
        provider=provider,
        repo=repo,
        registry=registry,
        trace_repo=trace_repo,
        model_name=effective_model,
        max_steps=effective_max_steps,
        max_tokens=effective_max_tokens,
        temperature=effective_temp,
        system_prompt=system_prompt,
        tool_choice=tool_choice,
        max_context_tokens=max_context,
        slow_response_threshold=config.provider.slow_response_threshold,
        planning_enabled=False,  # Disabled: extra LLM call adds latency/cost with no benefit
        max_plan_steps=max_plan_steps,
        approval_callback=approval_callback,
        permission_policy=permission_policy,
        profile=profile,
        reasoning_effort=effective_reasoning,
        reasoning_request_param=effective_reasoning_request_param,
        input_cost_per_million=input_cost_per_million,
        cached_input_cost_per_million=cached_input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
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
