"""Model management routes.

Endpoints for scanning local GGUF models, starting/stopping llama-server,
querying current provider status, and model registry selection.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from orchestrator.context.context_profile import resolve_model_context_profile
from orchestrator.logging_config import get_logger
from orchestrator.models.registry import ModelRegistry, ResolvedModel
from orchestrator.providers.factory import (
    create_provider_for_model,
    get_provider_override,
    set_provider_override,
)
from orchestrator.reasoning_controls import ReasoningSettingsResponse
from orchestrator.runtime_paths import is_hosted_production
from orchestrator.services.reasoning_settings import (
    get_reasoning_capabilities_for_target,
    get_runtime_reasoning_settings,
    update_runtime_reasoning_settings,
)
from orchestrator.services.model_catalog import list_model_catalog

# Note: set_provider_override is still imported for local model start/stop only
from orchestrator.providers.openai_compat import OpenAICompatProvider
from orchestrator.schemas import (
    LocalModelSchema,
    ModelStatusResponse,
    ProviderApiKeyRequest,
    ProviderKeyListResponse,
    ProviderKeyStatusResponse,
    SelectModelRequest,
    StartModelRequest,
    UpdateReasoningSettingsRequest,
)
from orchestrator.services import local_models
from orchestrator.services.provider_keys import (
    clear_provider_api_key,
    get_provider_key_statuses,
    set_provider_api_key,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])

# Active model state (set via POST /api/models/select)
_active_model: Optional[ResolvedModel] = None
_active_model_name: Optional[str] = None


def get_active_model() -> Optional[ResolvedModel]:
    """Get the currently active registry model (if any)."""
    return _active_model


def get_active_model_name() -> Optional[str]:
    """Get the name/alias of the active model (for web UI fallback)."""
    return _active_model_name


def get_active_model_provider() -> Optional[str]:
    """Get the currently active model provider."""
    return _active_model.provider_name if _active_model else None


def _resolve_status_reasoning_capabilities(
    *,
    provider_name: Optional[str],
    base_url: Optional[str],
    provider_obj: Optional[object],
    supports_reasoning: bool,
):
    capabilities = get_reasoning_capabilities_for_target(
        provider_name=provider_name,
        base_url=base_url,
        provider_obj=provider_obj,
        supports_reasoning=supports_reasoning,
    )
    return capabilities.provider_family, capabilities


@router.get("/local", response_model=list[LocalModelSchema])
async def list_local_models():
    """List available GGUF models on disk."""
    models = local_models.scan_models()
    return [
        LocalModelSchema(
            path=m.path,
            name=m.name,
            size_bytes=m.size_bytes,
            size_display=m.size_display,
            model_type=m.model_type.value,
        )
        for m in models
    ]


@router.post("/local/start")
async def start_local_model(request: StartModelRequest):
    """Start llama-server with the selected model and switch provider."""
    # Use config context window if no explicit ctx_size provided
    ctx_size = request.ctx_size
    if ctx_size is None:
        from orchestrator.config import get_chat_config

        config = get_chat_config()
        ctx_size = config.context.max_tokens

    try:
        ok = await local_models.start(request.model_path, ctx_size)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not ok:
        model_type = local_models.status().get("model_type", "gguf")
        log_file = "mlx.log" if model_type == "mlx" else "llama.log"
        raise HTTPException(
            status_code=500, detail=f"Server failed to start. Check logs/{log_file}"
        )

    # Swap the provider to point at local server
    local_status = local_models.status()
    local_model_name = local_status.get("model_name") or request.model_path
    local_provider = OpenAICompatProvider(
        base_url=f"http://localhost:{local_models.LLAMA_PORT}/v1",
        api_key="not-needed",
        endpoint="chat_completions",
        default_model=local_model_name,
    )
    local_provider._shared = True  # Prevent engine.close() from killing the shared client
    local_provider._input_cost_per_million = 0.0
    local_provider._cached_input_cost_per_million = 0.0
    local_provider._output_cost_per_million = 0.0
    local_provider._context_window = int(ctx_size)
    local_provider._max_output_tokens = 8192
    local_provider._supports_tools = True
    local_provider._supports_reasoning = False
    local_provider._reasoning_provider_family = "local"
    local_provider._context_profile_source = "local"
    local_provider._context_profile_provider_name = "local"
    local_provider._context_profile_model_id = local_model_name
    local_provider._context_profile_display_name = local_model_name
    set_provider_override(local_provider)

    model_name = local_models.status()["model_name"]
    logger.info(f"Provider switched to local: {model_name}")

    return {"status": "ok", "model_name": model_name}


@router.post("/local/stop")
async def stop_local_model():
    """Stop llama-server and revert to cloud provider."""
    await local_models.stop()
    set_provider_override(None)
    logger.info("Provider reverted to cloud")
    return {"status": "ok", "provider": "cloud"}


@router.get("/status", response_model=ModelStatusResponse)
async def get_model_status():
    """Get current provider info."""
    override = get_provider_override()
    local_running = await local_models.is_running()
    local_info = local_models.status()

    if override is not None and local_running:
        profile = resolve_model_context_profile(
            model_name=local_info.get("model_name"),
            provider_override=override,
        )
        provider_family, capabilities = _resolve_status_reasoning_capabilities(
            provider_name="local",
            base_url=f"http://localhost:{local_models.LLAMA_PORT}/v1",
            provider_obj=override,
            supports_reasoning=profile.supports_reasoning,
        )
        return ModelStatusResponse(
            provider="local",
            model_name=profile.display_name,
            base_url=f"http://localhost:{local_models.LLAMA_PORT}/v1",
            local_running=True,
            context_window=profile.context_window,
            max_output_tokens=profile.max_output_tokens,
            effective_input_budget=profile.effective_input_budget,
            supports_tools=profile.supports_tools,
            supports_reasoning=profile.supports_reasoning,
            supports_vision=profile.supports_vision,
            provider_family=provider_family,
            reasoning_capabilities=capabilities,
            source=profile.source,
        )

    if _active_model:
        profile = resolve_model_context_profile(model_name=_active_model.model_id, resolved_model=_active_model)
        provider_family, capabilities = _resolve_status_reasoning_capabilities(
            provider_name=_active_model.provider_name,
            base_url=_active_model.base_url,
            provider_obj=override,
            supports_reasoning=profile.supports_reasoning,
        )
        return ModelStatusResponse(
            provider=_active_model.provider_name,
            model_name=profile.display_name,
            base_url=_active_model.base_url,
            local_running=local_running,
            context_window=profile.context_window,
            max_output_tokens=profile.max_output_tokens,
            effective_input_budget=profile.effective_input_budget,
            supports_tools=profile.supports_tools,
            supports_reasoning=profile.supports_reasoning,
            supports_vision=profile.supports_vision,
            provider_family=provider_family,
            reasoning_capabilities=capabilities,
            source=profile.source,
        )

    from orchestrator.config import get_chat_config

    config = get_chat_config()
    profile = resolve_model_context_profile(model_name=config.model.name, config=config)
    provider_family, capabilities = _resolve_status_reasoning_capabilities(
        provider_name=None,
        base_url=config.provider.base_url,
        provider_obj=override,
        supports_reasoning=profile.supports_reasoning,
    )
    return ModelStatusResponse(
        provider="cloud",
        model_name=profile.display_name,
        base_url=config.provider.base_url,
        local_running=local_running,
        context_window=profile.context_window,
        max_output_tokens=profile.max_output_tokens,
        effective_input_budget=profile.effective_input_budget,
        supports_tools=profile.supports_tools,
        supports_reasoning=profile.supports_reasoning,
        supports_vision=profile.supports_vision,
        provider_family=provider_family,
        reasoning_capabilities=capabilities,
        source=profile.source,
    )


async def _chatgpt_auth_status(request: Request) -> dict:
    """Return ChatGPT auth state for the current browser session."""
    from orchestrator.config import get_chat_config
    from orchestrator.routes.auth import get_chatgpt_auth_session_id, get_valid_tokens

    config = get_chat_config()
    chatgpt_config = config.chatgpt
    if not chatgpt_config or not chatgpt_config.enabled:
        return {"enabled": False, "authenticated": False}

    session_id = get_chatgpt_auth_session_id(request)
    if not session_id:
        return {"enabled": True, "authenticated": False}

    tokens = await get_valid_tokens(session_id)
    if not tokens:
        return {"enabled": True, "authenticated": False}

    return {
        "enabled": True,
        "authenticated": True,
        "account_id": (tokens["account_id"][:8] + "..." if tokens.get("account_id") else None),
        "expires_at": tokens.get("expires_at"),
        "model": chatgpt_config.default_model,
        "available_models": chatgpt_config.available_models,
    }


@router.get("")
async def list_models(request: Request):
    """List all available model presets grouped by provider.

    Returns presets with availability info based on API key presence.
    """
    grouped = await list_model_catalog(chatgpt_status=await _chatgpt_auth_status(request))

    # Add current active model info
    return {
        "providers": grouped,
        "active_model": _active_model_name,
        "active_model_id": _active_model.model_id if _active_model else None,
        "active_provider": _active_model.provider_name if _active_model else None,
    }


@router.get("/provider-keys", response_model=ProviderKeyListResponse)
async def list_provider_keys():
    """List provider API key availability without exposing secrets."""
    statuses = await get_provider_key_statuses()
    return ProviderKeyListResponse(
        providers=[ProviderKeyStatusResponse(**status) for status in statuses]
    )


@router.put("/provider-keys/{provider}", response_model=ProviderKeyStatusResponse)
async def put_provider_key(provider: str, request: ProviderApiKeyRequest):
    """Persist a provider API key."""
    try:
        await set_provider_api_key(provider, request.api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    statuses = await get_provider_key_statuses()
    for status in statuses:
        if status["provider"] == provider.lower():
            return ProviderKeyStatusResponse(**status)
    raise HTTPException(status_code=404, detail="Provider not found")


@router.delete("/provider-keys/{provider}", response_model=ProviderKeyStatusResponse)
async def delete_provider_key(provider: str):
    """Delete a persisted provider API key."""
    try:
        await clear_provider_api_key(provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    statuses = await get_provider_key_statuses()
    for status in statuses:
        if status["provider"] == provider.lower():
            return ProviderKeyStatusResponse(**status)
    raise HTTPException(status_code=404, detail="Provider not found")


@router.post("/select")
async def select_model(request: SelectModelRequest, http_request: Request):
    """Select a model from the registry and hot-swap the provider.

    Resolves the model string via ModelRegistry, creates a new provider,
    and sets it as the global override. Disabled in production/staging.
    """
    if is_hosted_production():
        raise HTTPException(status_code=403, detail="Model selection is disabled in production")

    global _active_model, _active_model_name

    selection = request.model
    if request.provider and request.model_id:
        selection = f"{request.provider}:{request.model_id}"
    if not selection:
        raise HTTPException(status_code=400, detail="Missing model selection")

    try:
        _provider, resolved = create_provider_for_model(selection)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if resolved.provider_name == "chatgpt":
        status = await _chatgpt_auth_status(http_request)
        if not status.get("authenticated"):
            raise HTTPException(status_code=400, detail="Connect ChatGPT / Codex before selecting this model")

    # Store resolved model for status display and web UI fallback.
    # Clear any custom/local runtime override so registry resolution applies
    # to subsequent runs.
    set_provider_override(None)
    _active_model = resolved
    _active_model_name = request.model or f"{resolved.provider_name}:{resolved.model_id}"

    logger.info(
        "Model selected via registry",
        extra={
            "model": resolved.model_id,
            "display_name": resolved.display_name,
            "provider": resolved.provider_name,
            "context_window": resolved.context_window,
        },
    )

    profile = resolve_model_context_profile(model_name=resolved.model_id, resolved_model=resolved)
    return {
        "status": "ok",
        "model_id": resolved.model_id,
        "display_name": resolved.display_name,
        "provider": resolved.provider_name,
        "context_window": resolved.context_window,
        "max_output_tokens": resolved.max_output_tokens,
        "effective_input_budget": profile.effective_input_budget,
        "supports_tools": resolved.supports_tools,
        "supports_reasoning": resolved.reasoning_effort is not None,
        "supports_vision": resolved.supports_vision,
        "source": profile.source,
    }

@router.get("/reasoning-settings", response_model=ReasoningSettingsResponse)
async def get_reasoning_settings():
    """Get the global runtime reasoning settings and active-provider capabilities."""
    settings, updated_at, source = await get_runtime_reasoning_settings()
    status = await get_model_status()
    return ReasoningSettingsResponse(
        settings=settings,
        capabilities=status.reasoning_capabilities,
        provider_family=status.provider_family,
        model_name=status.model_name,
        updated_at=updated_at,
        source=source,
    )


@router.put("/reasoning-settings", response_model=ReasoningSettingsResponse)
async def put_reasoning_settings(request: UpdateReasoningSettingsRequest):
    """Update the global runtime reasoning settings."""
    settings, updated_at = await update_runtime_reasoning_settings(request.settings)
    status = await get_model_status()
    return ReasoningSettingsResponse(
        settings=settings,
        capabilities=status.reasoning_capabilities,
        provider_family=status.provider_family,
        model_name=status.model_name,
        updated_at=updated_at,
        source="database",
    )
