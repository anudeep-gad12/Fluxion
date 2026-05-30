"""FastAPI application - minimal entry point with routers."""

# Load .env FIRST, before any other imports that might read config
from dotenv import load_dotenv

load_dotenv()

import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from orchestrator.config import get_chat_config
from orchestrator.logging_config import (
    get_logger,
    set_component,
    set_request_id,
    setup_logging,
)
from orchestrator.middleware.rate_limit import RateLimitMiddleware
from orchestrator.middleware.session import SessionMiddleware
from orchestrator.routes import (
    agent_runs,
    auth,
    benchmarks,
    conversations,
    models,
    runs,
    terminal,
    workspaces,
)
from orchestrator.runtime_paths import (
    app_version,
    build_id,
    is_hosted_production,
    is_packaged_app,
    is_static_serving_enabled,
    static_dir,
    ui_build_info,
)
from orchestrator.services.provider_keys import apply_persisted_provider_keys_to_environment
from orchestrator.storage.db import get_db

logger = get_logger(__name__)


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment or defaults."""
    origins = os.environ.get("CORS_ORIGINS", "")
    if origins:
        return [o.strip() for o in origins.split(",")]
    defaults = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:9000",
        "http://localhost:9000",
    ]
    if is_packaged_app():
        defaults.extend(
            [
                "http://tauri.localhost",
                "https://tauri.localhost",
                "tauri://localhost",
            ]
        )
    return defaults


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request ID correlation and request/response logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(request_id)
        set_component("http")

        # Log request start (redact sensitive query params)
        start_time = time.time()
        raw_query = str(request.query_params) if request.query_params else None
        if raw_query and "owner=" in raw_query:
            from urllib.parse import parse_qs, urlencode

            params = parse_qs(raw_query, keep_blank_values=True)
            if "owner" in params:
                params["owner"] = ["[REDACTED]"]
            raw_query = urlencode(params, doseq=True)
        logger.info(
            f"{request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "query": raw_query,
            },
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
                },
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"{request.method} {request.url.path} -> ERROR: {e}",
                exc_info=True,
                extra={"duration_ms": duration_ms},
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

    logger.info("Starting Fluxion API server")

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
            },
        )
    except Exception as e:
        logger.warning(f"Could not load config for logging: {e}")

    # Startup: ensure database is initialized
    db = await get_db()
    logger.info("Database initialized")
    await apply_persisted_provider_keys_to_environment()

    # Clean up orphaned data (stuck in 'running' state from previous crash/restart)
    # This runs unconditionally to catch any orphaned tool_calls/steps even if runs were already cleaned

    # Count orphaned runs
    cursor = await db.conn.execute("SELECT COUNT(*) FROM runs WHERE status = 'running'")
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
            },
        )

    # Start OAuth callback server on port 1455 (for ChatGPT login)
    await auth.start_callback_server()

    if is_static_serving_enabled():
        ui_root = static_dir()
        index_path = ui_root / "index.html"
        if index_path.is_file():
            logger.info(
                "Serving UI from %s",
                ui_root,
                extra={"ui_static_dir": str(ui_root), "ui_built_at": ui_build_info().get("built_at")},
            )
        else:
            logger.error(
                "SERVE_STATIC is enabled but %s is missing. "
                "Run: ./dev.sh desktop  (or: cd ui && pnpm build)",
                index_path,
                extra={"ui_static_dir": str(ui_root)},
            )

    yield

    # Shutdown
    await auth.stop_callback_server()
    logger.info("Shutting down Fluxion API server")


# Disable OpenAPI docs in hosted production. The local macOS package also uses
# SERVE_STATIC=true, but it is a localhost owner app.
_is_production = is_hosted_production()

# Create FastAPI app
app = FastAPI(
    title="Fluxion",
    description="Local AI Chat",
    version=app_version(),
    lifespan=lifespan,
    # Disable docs in production to avoid exposing API schema
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
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

# Session middleware for demo mode user isolation
app.add_middleware(SessionMiddleware)

# Include routers
app.include_router(conversations.router)
app.include_router(runs.router)
app.include_router(agent_runs.router)
app.include_router(benchmarks.router)
app.include_router(auth.router)
app.include_router(models.router)
app.include_router(workspaces.router)
app.include_router(terminal.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    ui_build = ui_build_info()
    payload = {
        "status": "ok",
        "app": "Fluxion",
        "packaged": is_packaged_app(),
        "version": app_version(),
        "build_id": build_id(),
    }
    if is_static_serving_enabled():
        ui_root = static_dir()
        payload["ui_static_dir"] = str(ui_root)
        payload["ui_ready"] = (ui_root / "index.html").is_file()
        if ui_build:
            payload["ui"] = ui_build
    return payload


@app.get("/api/config")
async def get_config():
    """Get demo mode status for frontend."""
    config = get_chat_config()
    local_app = is_packaged_app() or not is_hosted_production()
    demo_enabled = False
    if not local_app and config.demo:
        demo_enabled = config.demo.enabled
    return {
        "demo": {
            "enabled": demo_enabled,
        },
        "local_app": local_app,
        "local_models_enabled": not is_hosted_production(),
    }


# Static file serving (when SERVE_STATIC=true). Resolve ui/dist on each request so a
# build that finishes after API startup still works without a manual restart.
if is_static_serving_enabled():
    _assets_root = static_dir() / "assets"
    if _assets_root.is_dir():
        app.mount("/assets", StaticFiles(directory=_assets_root), name="assets")

    @app.get("/ui-build.json")
    async def serve_ui_build_stamp():
        """Expose the UI build stamp for verifying the served bundle."""
        stamp_path = static_dir() / "ui-build.json"
        if not stamp_path.is_file():
            raise HTTPException(status_code=404, detail="UI build stamp missing")
        return FileResponse(
            stamp_path,
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        if full_path.startswith("api/") or full_path.startswith("auth/"):
            raise HTTPException(status_code=404, detail="Not found")
        index_path = static_dir() / "index.html"
        if index_path.is_file():
            headers = None
            if is_packaged_app():
                headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
            return FileResponse(index_path, headers=headers)
        ui_root = static_dir()
        raise HTTPException(
            status_code=404,
            detail=(
                "Frontend not built. Run ./dev.sh desktop from the repo root "
                f"(expected index at {ui_root / 'index.html'})."
            ),
        )


# Run with: uvicorn orchestrator.app:app --host 0.0.0.0 --port 9000
