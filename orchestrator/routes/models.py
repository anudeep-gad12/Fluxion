"""Model management routes.

Endpoints for scanning local GGUF models, starting/stopping llama-server,
and querying current provider status.
"""

from fastapi import APIRouter, HTTPException

from orchestrator.logging_config import get_logger
from orchestrator.schemas import (
    LocalModelSchema,
    StartModelRequest,
    ModelStatusResponse,
)
from orchestrator.services import local_models
from orchestrator.providers.factory import get_provider_override, set_provider_override
from orchestrator.providers.openai_compat import OpenAICompatProvider

logger = get_logger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


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
        raise HTTPException(status_code=500, detail="llama-server failed to start. Check logs/llama.log")

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

    # Fall back to config-based info
    from orchestrator.config import get_chat_config
    config = get_chat_config()
    return ModelStatusResponse(
        provider="cloud",
        model_name=config.model.name,
        base_url=config.provider.base_url,
        local_running=local_running,
    )
