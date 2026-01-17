"""FastAPI application - minimal entry point with routers."""

# Load .env FIRST, before any other imports that might read config
from dotenv import load_dotenv
load_dotenv()

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from orchestrator.config import get_chat_config
from orchestrator.logging_config import (
    setup_logging,
    get_logger,
    set_request_id,
    set_component,
)
from orchestrator.storage.db import get_db
from orchestrator.routes import conversations, runs, agent_runs


logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request ID correlation and request/response logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(request_id)
        set_component("http")

        # Log request start
        start_time = time.time()
        logger.info(
            f"{request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.query_params) if request.query_params else None,
            }
        )

        try:
            response = await call_next(request)
            duration_ms = int((time.time() - start_time) * 1000)

            # Log response
            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code}",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"{request.method} {request.url.path} -> ERROR: {e}",
                exc_info=True,
                extra={"duration_ms": duration_ms}
            )
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Setup logging first
    setup_logging(
        log_level="DEBUG",
        log_dir="./logs",
        log_file="app.log",
    )

    logger.info("Starting Reasoner API server")

    # Log config summary (redacted)
    try:
        config = get_chat_config()
        base_url = config.provider.base_url
        logger.info(
            "Configuration loaded",
            extra={
                "model": config.model.name,
                "endpoint": config.provider.endpoint,
                "base_url": base_url[:30] + "..." if len(base_url) > 30 else base_url,
                "max_tokens": config.model.max_tokens,
                "thinking_modes": list(config.thinking.mode_mapping.keys()),
            }
        )
    except Exception as e:
        logger.warning(f"Could not load config for logging: {e}")

    # Startup: ensure database is initialized
    await get_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down Reasoner API server")


# Create FastAPI app
app = FastAPI(
    title="Reasoner",
    description="Local AI Chat",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Include routers
app.include_router(conversations.router)
app.include_router(runs.router)
app.include_router(agent_runs.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    """Get current chat configuration."""
    config = get_chat_config()
    return {
        "config": config.get_snapshot(),
    }


# Run with: uvicorn orchestrator.app:app --host 127.0.0.1 --port 9000 --reload
