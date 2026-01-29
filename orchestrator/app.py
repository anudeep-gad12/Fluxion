"""FastAPI application - minimal entry point with routers."""

# Load .env FIRST, before any other imports that might read config
from dotenv import load_dotenv
load_dotenv()

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware

from orchestrator.config import get_chat_config
from orchestrator.logging_config import (
    setup_logging,
    get_logger,
    set_request_id,
    set_component,
)
from orchestrator.storage.db import get_db
from orchestrator.routes import conversations, runs, agent_runs, benchmarks
from orchestrator.middleware.rate_limit import RateLimitMiddleware


logger = get_logger(__name__)


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment or defaults."""
    origins = os.environ.get("CORS_ORIGINS", "")
    if origins:
        return [o.strip() for o in origins.split(",")]
    return ["http://127.0.0.1:3000", "http://localhost:3000"]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


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
    # Setup logging first (configurable via env vars for production)
    setup_logging(
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        log_dir=os.environ.get("LOG_DIR", "./logs"),
        log_file="app.log",
        enable_file=os.environ.get("LOG_TO_FILE", "true").lower() == "true",
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
    db = await get_db()
    logger.info("Database initialized")

    # Clean up orphaned data (stuck in 'running' state from previous crash/restart)
    # This runs unconditionally to catch any orphaned tool_calls/steps even if runs were already cleaned

    # Count orphaned runs
    cursor = await db.conn.execute(
        "SELECT COUNT(*) FROM runs WHERE status = 'running'"
    )
    row = await cursor.fetchone()
    orphaned_runs = row[0] if row else 0

    # Count orphaned tool calls
    cursor = await db.conn.execute(
        "SELECT COUNT(*) FROM agent_tool_calls WHERE status IN ('running', 'pending')"
    )
    row = await cursor.fetchone()
    orphaned_tool_calls = row[0] if row else 0

    # Count orphaned steps
    cursor = await db.conn.execute(
        "SELECT COUNT(*) FROM agent_steps WHERE state IN ('tool_calling', 'planning')"
    )
    row = await cursor.fetchone()
    orphaned_steps = row[0] if row else 0

    if orphaned_runs > 0 or orphaned_tool_calls > 0 or orphaned_steps > 0:
        # Mark orphaned runs as failed
        if orphaned_runs > 0:
            await db.conn.execute(
                """
                UPDATE runs
                SET status = 'failed',
                    error_message = 'Server restarted - run was interrupted'
                WHERE status = 'running'
                """
            )

        # Clean up orphaned agent_tool_calls (status = running/pending)
        if orphaned_tool_calls > 0:
            await db.conn.execute(
                """
                UPDATE agent_tool_calls
                SET status = 'interrupted',
                    error_message = 'Server restarted - tool call was interrupted'
                WHERE status IN ('running', 'pending')
                """
            )

        # Clean up orphaned agent_steps (state = tool_calling/planning)
        if orphaned_steps > 0:
            await db.conn.execute(
                """
                UPDATE agent_steps
                SET state = 'error',
                    error_message = 'Server restarted - step was interrupted'
                WHERE state IN ('tool_calling', 'planning')
                """
            )

        await db.conn.commit()
        logger.warning(
            "Cleaned up orphaned data on startup",
            extra={
                "orphaned_runs": orphaned_runs,
                "orphaned_tool_calls": orphaned_tool_calls,
                "orphaned_steps": orphaned_steps,
            }
        )

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

# CORS middleware (configurable via CORS_ORIGINS env var)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Rate limiting middleware (only active when demo mode enabled)
app.add_middleware(RateLimitMiddleware)

# Include routers
app.include_router(conversations.router)
app.include_router(runs.router)
app.include_router(agent_runs.router)
app.include_router(benchmarks.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    """Get current chat configuration.

    Returns config snapshot plus demo mode status (without secrets).
    """
    config = get_chat_config()
    response = {
        "config": config.get_snapshot(),
        "demo": {
            "enabled": config.demo.enabled if config.demo else False,
            # Don't expose owner_secret - frontend validates locally
        },
    }
    return response


# Static file serving for production (when SERVE_STATIC=true)
STATIC_DIR = Path(__file__).parent.parent / "ui" / "dist"
if STATIC_DIR.exists() and os.environ.get("SERVE_STATIC", "false").lower() == "true":
    # Serve static assets with caching
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not built")


# Run with: uvicorn orchestrator.app:app --host 0.0.0.0 --port 9000
