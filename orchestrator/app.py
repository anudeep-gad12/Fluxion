"""FastAPI application - minimal entry point with routers."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.config import get_chat_config
from orchestrator.storage.db import get_db
from orchestrator.routes import conversations, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup: ensure database is initialized
    await get_db()
    yield
    # Shutdown: cleanup if needed


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

# Include routers
app.include_router(conversations.router)
app.include_router(runs.router)


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
