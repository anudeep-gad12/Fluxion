"""Factory for creating configured coding-agent instances."""

from typing import TYPE_CHECKING, Optional

from orchestrator.config import get_chat_config
from orchestrator.context.context_profile import resolve_model_context_profile
from orchestrator.logging_config import get_logger
from orchestrator.providers.factory import create_provider
from orchestrator.reasoning_controls import ReasoningSettings, infer_provider_family
from orchestrator.agent.plan_mode import PLAN_MODE_INSTRUCTIONS, normalize_collaboration_mode
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo

from .agent_engine import AgentEngine
from .context import get_context_strategy
from .profile import get_profile
from .tools.registry import create_browser_agent_tool_registry

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
    python_provider: Optional[str] = None,
    agent_capabilities: Optional[dict] = None,
    reasoning_settings: Optional[ReasoningSettings] = None,
    collaboration_mode: str = "default",
    plan_approval_callback: Optional[object] = None,
    user_input_callback: Optional[object] = None,
    plan_doc_relative_path: Optional[str] = None,
    run_id: Optional[str] = None,
) -> AgentEngine:
    """Create a fully configured coding agent engine."""
    del query  # Agent runs are coding-only now.
    config = get_chat_config()
    profile = get_profile("coding")

    resolved_model = None
    override_model_name = None
    if provider_override is not None:
        override_model_name = getattr(provider_override, "_context_profile_model_id", None) or getattr(provider_override, "_default_model", None)
    resolve_name = model_name or override_model_name or config.model.name
    if resolve_name:
        try:
            from orchestrator.models.registry import _ALIAS_INDEX, _MODEL_ID_INDEX, ModelRegistry
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

    if provider_override is not None:
        provider = provider_override
    elif resolved_model:
        from orchestrator.providers.factory import create_provider_for_model
        provider, _ = create_provider_for_model(resolve_name)
    else:
        provider = create_provider(config.provider, chain_config=config.provider_chain)

    capabilities = agent_capabilities or {
        "web": True,
        "filesystem": bool(filesystem_enabled or working_dir),
        "bash": bool(filesystem_enabled or working_dir),
        "python": True,
    }
    resolved_collaboration_mode = normalize_collaboration_mode(collaboration_mode)
    registry = create_browser_agent_tool_registry(
        config,
        capabilities,
        working_dir,
        python_provider=python_provider,
        collaboration_mode=resolved_collaboration_mode,
        user_input_callback=user_input_callback,
        plan_doc_relative_path=plan_doc_relative_path,
        run_id=run_id,
    )

    db = await get_db()
    repo = AgentRepo(db)
    trace_repo = TraceRepo(db)

    strategy = get_context_strategy("coding")
    project_context = await strategy.gather(working_dir)

    if not system_prompt:
        from datetime import date
        today = date.today()
        has_web_tools = "web_search" in registry.tool_names
        if has_web_tools:
            date_context = (
                f"Current date: {today.strftime('%B %d, %Y')}\n"
                "Your knowledge cutoff: June 2024. For information after this date, use web_search."
            )
        else:
            date_context = f"Current date: {today.strftime('%B %d, %Y')}"
        system_prompt = profile.system_prompt_template.format(
            date_context=date_context,
            project_context=project_context,
        )
        if not has_web_tools:
            system_prompt = system_prompt.replace(
                "- Use `web_search` or `web_extract` only for external docs or current behavior you cannot reliably infer locally.\n",
                "",
            )
    if resolved_collaboration_mode == "plan":
        system_prompt = f"{system_prompt}\n\n{PLAN_MODE_INSTRUCTIONS}"

    context_profile = resolve_model_context_profile(
        model_name=resolve_name,
        provider_override=provider_override,
        resolved_model=resolved_model,
        config=config,
    )
    max_context = context_profile.context_window

    if resolved_model:
        effective_model = resolved_model.model_id
        effective_temp = temperature or resolved_model.temperature
        effective_max_tokens = (
            max_tokens
            or (reasoning_settings.max_output_tokens if reasoning_settings else None)
            or resolved_model.max_output_tokens
        )
        effective_reasoning = resolved_model.reasoning_effort
        effective_reasoning_request_param = resolved_model.reasoning_request_param
        input_cost_per_million = resolved_model.input_cost_per_million
        cached_input_cost_per_million = resolved_model.cached_input_cost_per_million
        output_cost_per_million = resolved_model.output_cost_per_million
    else:
        effective_model = (
            model_name
            or getattr(provider_override, "_default_model", None)
            or getattr(provider_override, "_context_profile_model_id", None)
            or config.model.name
        )
        effective_temp = temperature or config.model.temperature
        provider_max_output = getattr(provider_override, "_max_output_tokens", None)
        effective_max_tokens = (
            max_tokens
            or (reasoning_settings.max_output_tokens if reasoning_settings else None)
            or provider_max_output
            or config.model.max_tokens
        )
        effective_reasoning = getattr(config.model, "reasoning_effort", None)
        effective_reasoning_request_param = getattr(provider_override, "_reasoning_request_param", None)
        input_cost_per_million = getattr(provider_override, "_input_cost_per_million", None)
        cached_input_cost_per_million = getattr(provider_override, "_cached_input_cost_per_million", None)
        output_cost_per_million = getattr(provider_override, "_output_cost_per_million", None)

    effective_max_steps = max_steps if max_steps is not None else profile.max_steps

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
        max_context_tokens=max_context,
        context_profile=context_profile,
        slow_response_threshold=config.provider.slow_response_threshold,
        planning_enabled=False,
        max_plan_steps=0,
        approval_callback=approval_callback,
        permission_policy=permission_policy,
        profile=profile,
        reasoning_effort=effective_reasoning,
        reasoning_request_param=effective_reasoning_request_param,
        reasoning_provider_family=infer_provider_family(
            provider_name=getattr(resolved_model, "provider_name", None) if resolved_model else None,
            base_url=getattr(resolved_model, "base_url", None) if resolved_model else getattr(config.provider, "base_url", None),
            provider_obj=provider_override,
        ),
        reasoning_settings=reasoning_settings,
        input_cost_per_million=input_cost_per_million,
        cached_input_cost_per_million=cached_input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
        collaboration_mode=resolved_collaboration_mode,
        plan_approval_callback=plan_approval_callback,
    )

    logger.info(
        "AgentEngine created",
        extra={
            "model": engine._model_name,
            "max_steps": engine._max_steps,
            "tools": registry.tool_names,
            "profile": profile.name,
            "collaboration_mode": resolved_collaboration_mode,
        },
    )

    return engine
