"""Model management routes.

Endpoints for scanning local GGUF models, starting/stopping llama-server,
querying current provider status, and model registry selection.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException

from orchestrator.logging_config import get_logger
from orchestrator.models.registry import ModelRegistry, ResolvedModel
from orchestrator.providers.factory import (
    create_provider_for_model,
    get_provider_override,
    set_provider_override,
)

# Note: set_provider_override is still imported for local model start/stop only
from orchestrator.providers.openai_compat import OpenAICompatProvider
from orchestrator.schemas import (
    LocalModelSchema,
    ModelStatusResponse,
    SelectModelRequest,
    StartModelRequest,
)
from orchestrator.services import local_models

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
        raise HTTPException(
            status_code=500, detail="llama-server failed to start. Check logs/llama.log"
        )

    # Swap the provider to point at local llama-server
    local_provider = OpenAICompatProvider(
        base_url=f"http://localhost:{local_models.LLAMA_PORT}/v1",
        api_key="not-needed",
        endpoint="chat_completions",
    )
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
        return ModelStatusResponse(
            provider="local",
            model_name=local_info.get("model_name"),
            base_url=f"http://localhost:{local_models.LLAMA_PORT}/v1",
            local_running=True,
        )

    # Check if a registry model is active
    if _active_model:
        return ModelStatusResponse(
            provider=_active_model.provider_name,
            model_name=_active_model.display_name,
            base_url=_active_model.base_url,
            local_running=local_running,
        )

    # Fall back to config-based info
    from orchestrator.config import get_chat_config

    config = get_chat_config()
    return ModelStatusResponse(
        provider="cloud",
        model_name=config.model.name,
        base_url=config.provider.base_url,
        local_running=local_running,
    )


@router.get("")
async def list_models():
    """List all available model presets grouped by provider.

    Returns presets with availability info based on API key presence.
    """
    grouped = ModelRegistry.list_models()

    # Add current active model info
    return {
        "providers": grouped,
        "active_model": _active_model_name,
        "active_model_id": _active_model.model_id if _active_model else None,
    }


@router.post("/select")
async def select_model(request: SelectModelRequest):
    """Select a model from the registry and hot-swap the provider.

    Resolves the model string via ModelRegistry, creates a new provider,
    and sets it as the global override. Disabled in production/staging.
    """
    import os
    if os.environ.get("SERVE_STATIC", "false").lower() == "true":
        raise HTTPException(status_code=403, detail="Model selection is disabled in production")

    global _active_model, _active_model_name

    try:
        provider, resolved = create_provider_for_model(request.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Store resolved model for status display and web UI fallback
    # NOTE: We intentionally do NOT call set_provider_override() here.
    # That function is reserved for local llama-server start/stop only.
    # Provider resolution for registry models happens per-request.
    _active_model = resolved
    _active_model_name = request.model

    logger.info(
        "Model selected via registry",
        extra={
            "model": resolved.model_id,
            "display_name": resolved.display_name,
            "provider": resolved.provider_name,
            "context_window": resolved.context_window,
        },
    )

    return {
        "status": "ok",
        "model_id": resolved.model_id,
        "display_name": resolved.display_name,
        "provider": resolved.provider_name,
        "context_window": resolved.context_window,
        "max_output_tokens": resolved.max_output_tokens,
        "supports_tools": resolved.supports_tools,
        "supports_reasoning": resolved.reasoning_effort is not None,
    }
