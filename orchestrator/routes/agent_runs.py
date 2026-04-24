"""Agent run routes - creation, status, streaming, cancellation, and traces.

This module provides REST API endpoints for the web research agent:
- POST /api/agent/runs - Start a new agent run
- GET /api/agent/runs/{id} - Get run status
- GET /api/agent/runs/{id}/stream - SSE event stream with resumption support
- POST /api/agent/runs/{id}/cancel - Cancel an active run
- GET /api/agent/runs/{id}/trace - Get full execution trace
"""

import asyncio
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from orchestrator.logging_config import (
    get_logger,
    get_request_id,
    set_component,
    set_request_id,
)
from orchestrator.schemas import (
    AgentCitationResponse,
    AgentRunStatusResponse,
    AgentRunTraceResponse,
    AgentStepResponse,
    AgentToolCallResponse,
    CreateAgentRunRequest,
    CreateAgentRunResponse,
    RunArtifactResponse,
)
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo

logger = get_logger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# =============================================================================
# Module-level state for active runs
# =============================================================================

# WARNING: These are in-memory, single-process only.
# For multi-worker deployment, use Redis pub/sub or durable event bus.
_active_runs: Dict[str, bool] = {}  # run_id -> is_active (no queue; pub/sub via history + notify)
_abort_signals: Dict[str, asyncio.Event] = {}
_pause_signals: Dict[str, asyncio.Event] = {}  # Set when user requests pause
_resume_signals: Dict[str, asyncio.Event] = {}  # Set when user requests resume
_steer_queues: Dict[str, List[str]] = {}  # Pending steering messages per run
_event_history: Dict[str, List[Dict[str, Any]]] = {}  # Append-only event log per run
_event_notify: Dict[str, asyncio.Event] = {}  # Notifies SSE generators of new events
_run_tokens: Dict[str, str] = {}  # Per-run stream auth tokens
_run_sessions: Dict[str, str] = {}  # Per-run session IDs for access control
# run_id -> {tool_call_id -> Future[bool]}
_approval_queues: Dict[str, Dict[str, asyncio.Future]] = {}


def get_session_context(request: Request) -> Tuple[Optional[str], bool]:
    """Extract session context from request.

    CLI clients pass session ID via X-CLI-Session header (used to look
    up ChatGPT tokens). Falls back to session middleware cookie.

    Returns:
        Tuple of (session_id, is_owner).
    """
    session_id = request.headers.get("x-cli-session") or getattr(request.state, "session_id", None)
    is_owner = getattr(request.state, "is_owner", True)
    return session_id, is_owner


# =============================================================================
# SSE Event Translation
# =============================================================================

# Map engine event types to SSE event types
_EVENT_TYPE_MAP = {
    "agent_started": "agent_state",
    "step_started": "step_start",
    "thinking": "thinking",
    "tool_start": "tool_start",
    "tool_approval_required": "tool_approval_required",
    "tool_result": "tool_result",
    "synthesizing": "agent_state",
    "answer_token": "answer",
    "agent_complete": "complete",
    "agent_error": "error",
    "agent_paused": "paused",
    "agent_resumed": "resumed",
    "steer_injected": "steer",
    "slow_response": "slow_response",
}


def _translate_event(event: Dict[str, Any], seq: int) -> Dict[str, Any]:
    """Translate engine event to SSE format with sequence number.

    Args:
        event: Engine event dict with 'type' key.
        seq: Sequence number for resumption.

    Returns:
        SSE event dict with event type and JSON data.
    """
    engine_type = event.get("type", "unknown")
    sse_type = _EVENT_TYPE_MAP.get(engine_type, engine_type)

    # Build data payload
    data = {
        "seq": seq,
        "type": sse_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Copy relevant fields from engine event
    for key, value in event.items():
        if key != "type":
            data[key] = value

    return {
        "event": sse_type,
        "data": json.dumps(data),
    }


# =============================================================================
# Cleanup helpers
# =============================================================================


async def _persist_run_event(run_id: str, seq: int, event: Dict[str, Any]) -> None:
    """Fire-and-forget: persist a single SSE event to the database.

    Args:
        run_id: The run ID.
        seq: Sequence number.
        event: Event dict to persist.
    """
    try:
        db = await get_db()
        repo = AgentRepo(db)
        await repo.create_run_event(run_id, seq, event.get("type", "unknown"), event)
    except Exception as e:
        logger.warning(
            "Failed to persist run event",
            extra={"run_id": run_id, "seq": seq, "error": str(e)},
        )


async def _cleanup_run(run_id: str, delay_seconds: float = 5.0) -> None:
    """Clean up run state after completion.

    Delays cleanup to allow late-joining SSE clients to receive final events.

    Args:
        run_id: The run ID to clean up.
        delay_seconds: Delay before removing from active_runs.
    """
    await asyncio.sleep(delay_seconds)
    _active_runs.pop(run_id, None)
    _abort_signals.pop(run_id, None)
    _pause_signals.pop(run_id, None)
    _resume_signals.pop(run_id, None)
    _steer_queues.pop(run_id, None)
    _event_notify.pop(run_id, None)
    _run_sessions.pop(run_id, None)
    _approval_queues.pop(run_id, None)
    logger.debug("Cleaned up run state", extra={"run_id": run_id})

    # Schedule history cleanup (keep longer for resumption)
    asyncio.create_task(_cleanup_history(run_id, 300.0))


async def _cleanup_history(run_id: str, delay_seconds: float) -> None:
    """Clean up event history after delay.

    Args:
        run_id: The run ID to clean up.
        delay_seconds: Delay before removing history.
    """
    await asyncio.sleep(delay_seconds)
    _event_history.pop(run_id, None)
    _run_tokens.pop(run_id, None)
    logger.debug("Cleaned up event history", extra={"run_id": run_id})


# =============================================================================
# Background task for agent execution
# =============================================================================


async def _run_agent_task(
    run_id: str,
    query: str,
    conversation_id: Optional[str],
    max_steps: int,
    session_id: Optional[str] = None,
    provider_preference: Optional[str] = None,
    model_override: Optional[str] = None,
    filesystem_enabled: bool = False,
    working_dir: Optional[str] = None,
    permission_policy: str = "strict",
    profile_name: Optional[str] = None,
    python_provider: Optional[str] = None,
    agent_capabilities: Optional[dict] = None,
) -> None:
    """Background task that runs the agent.

    Args:
        run_id: Unique run identifier.
        query: User's research query.
        conversation_id: Optional conversation context.
        max_steps: Maximum steps for agent execution.
        session_id: Optional session ID for provider routing.
        provider_preference: Optional provider preference ("chatgpt" or None).
        model_override: Optional model name override (e.g., "o4-mini").
        filesystem_enabled: If True, register filesystem tools.
        working_dir: Working directory for filesystem tools.
        permission_policy: Permission policy ("strict", "relaxed", "yolo").
        profile_name: Agent profile name ("research", "coding").
        python_provider: Python execution provider ("local" or "daytona").
        agent_capabilities: Browser-owned tool capabilities for this run.
    """
    # Import here to avoid circular imports
    from orchestrator.agent.factory import create_agent_engine

    abort_signal = _abort_signals.get(run_id)

    if run_id not in _active_runs:
        logger.error("Run not active", extra={"run_id": run_id})
        return

    seq = 0

    def event_callback(event: Dict[str, Any]) -> None:
        """Callback for engine events.

        Appends to the shared event history (append-only log) and notifies
        all SSE generators via the asyncio.Event.  Each generator tracks its
        own read cursor so multiple clients never steal events from each other.
        """
        nonlocal seq
        if abort_signal and abort_signal.is_set():
            return
        seq += 1
        event["seq"] = seq
        _event_history.setdefault(run_id, []).append(event.copy())
        # Persist event to DB (fire-and-forget)
        asyncio.create_task(_persist_run_event(run_id, seq, event))
        # Wake up all SSE generators waiting for new events
        notify = _event_notify.get(run_id)
        if notify:
            notify.set()

    try:
        # Resolve provider override — check local model first
        from orchestrator.providers.factory import get_provider_override

        provider_override = get_provider_override()
        if provider_override is not None:
            pass  # Local model is active, use it
        elif session_id and provider_preference == "chatgpt":
            # ChatGPT path: use stored OAuth tokens
            try:
                from orchestrator.providers.factory import create_chatgpt_provider
                from orchestrator.routes.auth import get_valid_tokens

                tokens = await get_valid_tokens(session_id)
                if tokens:
                    provider_override = create_chatgpt_provider(tokens, model=model_override)
            except Exception as e:
                logger.warning(
                    "Failed to create ChatGPT provider for agent",
                    extra={"error": str(e)},
                )
        elif model_override:
            # Model registry path: resolve alias to provider + full model ID
            try:
                from orchestrator.providers.factory import create_provider_for_model

                provider_override, resolved = create_provider_for_model(model_override)
                model_override = resolved.model_id  # Replace alias with full ID
            except (ValueError, Exception) as e:
                logger.warning(
                    "Failed to resolve model via registry, using default",
                    extra={"model": model_override, "error": str(e)},
                )
        elif not model_override and not provider_preference:
            # Web UI fallback: use the last model selected via picker
            from orchestrator.routes.models import get_active_model_name

            active_name = get_active_model_name()
            if active_name:
                try:
                    from orchestrator.providers.factory import create_provider_for_model

                    provider_override, resolved = create_provider_for_model(active_name)
                    model_override = resolved.model_id
                except Exception:
                    pass

        # Build approval callback for permission system
        async def approval_callback(
            rid: str, tool_call_id: str, tool_name: str, arguments: dict
        ) -> bool:
            """Wait for user to approve/deny a tool call."""
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            _approval_queues.setdefault(rid, {})[tool_call_id] = future
            try:
                return await asyncio.wait_for(future, timeout=300)  # 5 min timeout
            except asyncio.TimeoutError:
                logger.warning(
                    "Tool approval timed out",
                    extra={
                        "run_id": rid,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "timeout_seconds": 300,
                    },
                )
                return False
            finally:
                _approval_queues.get(rid, {}).pop(tool_call_id, None)

        # Create engine and run (pass query for classification)
        engine = await create_agent_engine(
            model_name=model_override,
            max_steps=max_steps,
            query=query,
            provider_override=provider_override,
            filesystem_enabled=filesystem_enabled,
            working_dir=working_dir,
            approval_callback=approval_callback if permission_policy != "yolo" else None,
            profile_name=profile_name,
            python_provider=python_provider,
            agent_capabilities=agent_capabilities,
        )
        result = await engine.run(
            run_id=run_id,
            query=query,
            event_callback=event_callback,
            conversation_id=conversation_id,
            pause_signal=_pause_signals.get(run_id),
            resume_signal=_resume_signals.get(run_id),
            steer_queue=_steer_queues.get(run_id),
        )

        if abort_signal and not abort_signal.is_set():
            end_event = {
                "type": "_STREAM_END",
                "result": {
                    "run_id": result.run_id,
                    "success": result.success,
                    "final_answer": result.final_answer,
                    "citations": result.citations,
                    "total_steps": result.total_steps,
                    "timing_ms": result.timing_ms,
                    "total_tokens": result.total_tokens,
                    "context_usage": result.context_usage,
                },
            }
            _event_history.setdefault(run_id, []).append(end_event)
            notify = _event_notify.get(run_id)
            if notify:
                notify.set()
    except Exception as e:
        logger.error(
            "Agent run failed",
            extra={"run_id": run_id, "error": str(e)},
            exc_info=True,
        )
        if abort_signal is None or not abort_signal.is_set():
            err_event = {"type": "_STREAM_ERROR", "error": str(e)}
            _event_history.setdefault(run_id, []).append(err_event)
            notify = _event_notify.get(run_id)
            if notify:
                notify.set()
    finally:
        asyncio.create_task(_cleanup_run(run_id))


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/runs", response_model=CreateAgentRunResponse)
async def create_agent_run(request: CreateAgentRunRequest, http_request: Request):
    """Start a new agent research run.

    The agent executes asynchronously in a background task.
    Use the stream endpoint to receive real-time events.

    Returns:
        run_id and stream_url for SSE events.
    """
    session_id, is_owner = get_session_context(http_request)

    # Check per-session message limit
    if not is_owner and session_id:
        from orchestrator.config import get_chat_config as _get_config
        from orchestrator.storage.db import get_db as _get_db

        _cfg = _get_config()
        if _cfg.demo and _cfg.demo.enabled:
            _limit = int(getattr(_cfg.demo, "message_limit", 10) or 10)
            if _limit > 0:
                _db = await _get_db()
                _cursor = await _db.conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE session_id = ?", (session_id,)
                )
                _row = await _cursor.fetchone()
                if (_row[0] if _row else 0) >= _limit:
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            f"Message limit reached. You can send {_limit} messages per session."
                        ),
                    )

    run_id = str(uuid.uuid4())

    try:
        # Initialize state
        abort_signal = asyncio.Event()

        _active_runs[run_id] = True
        _abort_signals[run_id] = abort_signal
        _pause_signals[run_id] = asyncio.Event()
        _resume_signals[run_id] = asyncio.Event()
        _steer_queues[run_id] = []
        _event_history[run_id] = []
        _event_notify[run_id] = asyncio.Event()
        stream_token = secrets.token_urlsafe(16)
        _run_tokens[run_id] = stream_token

        # Track session for access control
        if session_id:
            _run_sessions[run_id] = session_id

        # Create run record in database
        db = await get_db()
        trace_repo = TraceRepo(db)

        # Import ConversationRepo for creating ephemeral conversations
        from orchestrator.storage.repositories.conversation_repo import ConversationRepo

        conv_repo = ConversationRepo(db)

        # Generate conversation_id if not provided, and create ephemeral conversation
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            # Create ephemeral conversation for standalone agent runs
            title = request.query[:64] + "..." if len(request.query) > 64 else request.query
            await conv_repo.create(
                conversation_id=conversation_id,
                title=title,
                session_id=session_id,
            )
        else:
            # Verify ownership of existing conversation
            conversation = await conv_repo.get_with_session_check(
                conversation_id,
                session_id=session_id,
                is_owner=is_owner,
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

        workspace_path = request.workspace_path or request.working_dir
        capabilities = request.capabilities.model_dump()
        if workspace_path and request.filesystem_enabled:
            capabilities["filesystem"] = True

        # Create model config snapshot for agent
        model_config = {
            "mode": "agent",
            "max_steps": request.max_steps,
            "workspace_path": workspace_path,
            "capabilities": capabilities,
            "permission_policy": request.permission_policy,
        }

        await trace_repo.create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="agent",
            profile_name="agent",
            model_config=model_config,
            user_message=request.query,
            session_id=session_id,
        )

        # Update agent-specific fields
        agent_repo = AgentRepo(db)
        await agent_repo.update_run_agent_state(
            run_id=run_id,
            agent_state="initializing",
            current_step=0,
            max_steps=request.max_steps,
        )

        # Start background task (pass provider/model preference from headers)
        provider_preference = http_request.headers.get("x-provider")
        model_override = http_request.headers.get("x-model")
        asyncio.create_task(
            _run_agent_task(
                run_id=run_id,
                query=request.query,
                conversation_id=conversation_id,
                max_steps=request.max_steps,
                session_id=session_id,
                provider_preference=provider_preference,
                model_override=model_override,
                filesystem_enabled=capabilities.get("filesystem", False),
                working_dir=workspace_path,
                permission_policy=request.permission_policy,
                profile_name=request.profile,
                python_provider=request.python_provider,
                agent_capabilities=capabilities,
            )
        )

        logger.info(
            "Agent run started",
            extra={
                "run_id": run_id,
                "query_length": len(request.query),
                "max_steps": request.max_steps,
            },
        )

        return CreateAgentRunResponse(
            run_id=run_id,
            status="running",
            stream_url=f"/api/agent/runs/{run_id}/stream?token={stream_token}",
            stream_token=stream_token,
            conversation_id=conversation_id,
        )

    except HTTPException:
        # Clean up on HTTP error (like 404)
        _active_runs.pop(run_id, None)
        _abort_signals.pop(run_id, None)
        _event_history.pop(run_id, None)
        _event_notify.pop(run_id, None)
        _run_tokens.pop(run_id, None)
        _run_sessions.pop(run_id, None)
        raise
    except Exception as e:
        # Clean up on failure
        _active_runs.pop(run_id, None)
        _abort_signals.pop(run_id, None)
        _event_history.pop(run_id, None)
        _event_notify.pop(run_id, None)
        _run_tokens.pop(run_id, None)
        _run_sessions.pop(run_id, None)
        logger.error("Failed to start agent run", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start agent run")


@router.get("/runs/{run_id}", response_model=AgentRunStatusResponse)
async def get_agent_run_status(run_id: str, http_request: Request):
    """Get current status of an agent run.

    Returns run metadata, current state, step count, and result if complete.
    """
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    # Get run from trace_repo with session check
    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Determine status
    is_active = run_id in _active_runs
    base_status = run.get("status", "unknown")
    status = "running" if is_active else base_status

    # total_steps is the final step count when run completes
    current_step = run.get("current_step", 0)
    total_steps = current_step if status in ("succeeded", "failed") else None

    return AgentRunStatusResponse(
        run_id=run_id,
        status=status,
        agent_state=run.get("agent_state"),
        current_step=current_step,
        total_steps=total_steps,
        max_steps=run.get("max_steps", 1000),
        final_answer=run.get("final_answer"),
        error_message=run.get("error_message"),
        created_at=run.get("created_at", ""),
        updated_at=run.get("updated_at"),
    )


@router.get("/runs/{run_id}/stream")
async def stream_agent_events(
    run_id: str,
    http_request: Request,
    since_seq: int = Query(0, description="Resume from this sequence number"),
    token: str = Query("", description="Stream auth token from run creation"),
):
    """Stream agent events via Server-Sent Events.

    Supports resumption via since_seq parameter for reconnection.
    Requires stream token for active runs (returned by POST /runs).
    Sends heartbeat every 30 seconds during idle.
    """
    session_id, is_owner = get_session_context(http_request)

    # Validate stream token: reject only if a non-empty token is provided but wrong.
    # Empty token is allowed as fallback for reconnection (e.g. page reload where
    # localStorage may not have persisted the token).
    expected_token = _run_tokens.get(run_id)
    if token and expected_token and token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid stream token")

    # Session-based access control for active runs
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    # For completed runs, check DB
    if run_id not in _active_runs:
        db = await get_db()
        trace_repo = TraceRepo(db)
        run = await trace_repo.get_run_with_session_check(
            run_id,
            session_id=session_id,
            is_owner=is_owner,
        )
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

    # Capture parent request ID for SSE context
    parent_request_id = get_request_id()

    async def event_generator():
        """Cursor-based SSE generator.

        Each SSE client maintains its own read cursor into the shared
        append-only event history.  This allows multiple concurrent clients
        (e.g. reconnects, React StrictMode double-mount) to each receive
        ALL events without stealing from each other.
        """
        # Restore request context in generator
        if parent_request_id:
            set_request_id(parent_request_id)
        set_component("agent-sse")

        chunk_count = 0
        stream_start = time.time()
        cursor = 0  # Index into _event_history[run_id]

        logger.info(
            "Agent SSE stream opened",
            extra={"run_id": run_id, "since_seq": since_seq},
        )

        try:
            while True:
                # Read any new events from history since our cursor
                history = _event_history.get(run_id, [])
                new_events = history[cursor:]
                cursor = len(history)

                for event in new_events:
                    event_type = event.get("type", "")

                    # Terminal events
                    if event_type == "_STREAM_END":
                        duration_ms = int((time.time() - stream_start) * 1000)
                        logger.info(
                            "Agent SSE stream completed",
                            extra={
                                "run_id": run_id,
                                "chunk_count": chunk_count,
                                "duration_ms": duration_ms,
                            },
                        )
                        yield {
                            "event": "complete",
                            "data": json.dumps(event.get("result", {})),
                        }
                        return
                    elif event_type == "_STREAM_ERROR":
                        logger.error(
                            "Agent SSE stream error",
                            extra={
                                "run_id": run_id,
                                "error": event.get("error"),
                                "chunk_count": chunk_count,
                            },
                        )
                        yield {
                            "event": "error",
                            "data": json.dumps({"error": "Internal server error"}),
                        }
                        return
                    elif event_type == "_STREAM_ABORTED":
                        logger.warning(
                            "Agent SSE stream aborted",
                            extra={"run_id": run_id, "chunk_count": chunk_count},
                        )
                        yield {
                            "event": "cancelled",
                            "data": json.dumps({"run_id": run_id}),
                        }
                        return

                    # Normal events — skip if already seen by this client
                    event_seq = event.get("seq", 0)
                    if event_seq > since_seq:
                        chunk_count += 1
                        yield _translate_event(event, event_seq)

                # If run is no longer active and we've drained all events, exit
                if run_id not in _active_runs:
                    # Check DB for completed run as fallback
                    db = await get_db()
                    trace_repo = TraceRepo(db)
                    run = await trace_repo.get_run(run_id)
                    if run:
                        status = run.get("status", "unknown")
                        if status in ("succeeded", "failed"):
                            yield {
                                "event": "complete",
                                "data": json.dumps(
                                    {
                                        "run_id": run_id,
                                        "status": status,
                                        "final_answer": run.get("final_answer"),
                                    }
                                ),
                            }
                    return

                # Wait for new events (or heartbeat timeout).
                # Clear before waiting so we don't miss events added
                # between our history read and the wait() call — any event
                # added after clear() will re-set() the flag, waking us.
                notify = _event_notify.get(run_id)
                if notify:
                    notify.clear()
                    # Double-check for events added between read and clear
                    if len(_event_history.get(run_id, [])) > cursor:
                        continue
                    try:
                        await asyncio.wait_for(notify.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        yield {"event": "heartbeat", "data": "{}"}
                else:
                    # No notify event means run cleaned up; exit
                    return

        except asyncio.CancelledError:
            duration_ms = int((time.time() - stream_start) * 1000)
            logger.warning(
                "Agent SSE stream client disconnected",
                extra={
                    "run_id": run_id,
                    "chunk_count": chunk_count,
                    "duration_ms": duration_ms,
                },
            )
            raise

    return EventSourceResponse(event_generator())


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str, http_request: Request):
    """Cancel an active agent run.

    Signals the background task to stop, drains the queue,
    and sends a cancelled event to SSE clients.
    """
    session_id, is_owner = get_session_context(http_request)

    # Verify session ownership for active runs
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    # Signal abort
    if run_id in _abort_signals:
        _abort_signals[run_id].set()

    # Resolve any pending approval futures so the engine unblocks immediately
    pending_approvals = _approval_queues.pop(run_id, {})
    for future in pending_approvals.values():
        if not future.done():
            future.set_result(False)

    # Signal cancellation to SSE clients via history + notify
    _active_runs.pop(run_id, None)
    _event_history.setdefault(run_id, []).append({"type": "_STREAM_ABORTED"})
    notify = _event_notify.get(run_id)
    if notify:
        notify.set()

    # Clean up session tracking
    _run_sessions.pop(run_id, None)

    # Update database status
    try:
        db = await get_db()
        trace_repo = TraceRepo(db)
        await trace_repo.update_run(run_id, status="cancelled")
    except Exception as e:
        logger.error(
            "Failed to update run status on cancel",
            extra={"run_id": run_id, "error": str(e)},
        )

    logger.info("Agent run cancelled", extra={"run_id": run_id})

    return {"run_id": run_id, "status": "cancelled"}


@router.post("/runs/{run_id}/pause")
async def pause_agent_run(run_id: str, http_request: Request):
    """Pause an active agent run after the current step completes."""
    session_id, is_owner = get_session_context(http_request)

    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    pause_signal = _pause_signals.get(run_id)
    if not pause_signal:
        raise HTTPException(status_code=404, detail="Run not found")

    pause_signal.set()
    logger.info("Agent run pause requested", extra={"run_id": run_id})

    return {"run_id": run_id, "status": "pausing"}


@router.post("/runs/{run_id}/resume")
async def resume_agent_run(run_id: str, http_request: Request):
    """Resume a paused agent run."""
    session_id, is_owner = get_session_context(http_request)

    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    resume_signal = _resume_signals.get(run_id)
    if not resume_signal:
        raise HTTPException(status_code=404, detail="Run not found")

    resume_signal.set()
    logger.info("Agent run resume requested", extra={"run_id": run_id})

    return {"run_id": run_id, "status": "resuming"}


@router.post("/runs/{run_id}/steer")
async def steer_agent_run(run_id: str, http_request: Request):
    """Inject a steering message into a running agent.

    The message is queued and injected before the next LLM call.
    Works whether the agent is running or paused.
    """
    session_id, is_owner = get_session_context(http_request)

    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    queue = _steer_queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Run not found")

    body = await http_request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    queue.append(message)
    logger.info(
        "Steering message queued",
        extra={"run_id": run_id, "queue_size": len(queue), "message_preview": message[:80]},
    )

    return {"run_id": run_id, "status": "queued", "queue_size": len(queue)}


@router.get("/runs/{run_id}/trace", response_model=AgentRunTraceResponse)
async def get_agent_run_trace(run_id: str, http_request: Request):
    """Get full execution trace for an agent run.

    Returns all steps, tool calls, and citations for detailed analysis.
    """
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)
    agent_repo = AgentRepo(db)

    # Get base run info with session check
    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get all steps
    steps_raw = await agent_repo.get_steps_for_run(run_id)
    steps = [
        AgentStepResponse(
            id=s["id"],  # DB column is 'id', not 'step_id'
            run_id=s["run_id"],
            step_number=s["step_number"],
            state=s["state"],
            thinking_text=s.get("thinking_text"),  # DB column is 'thinking_text'
            decision=s.get("decision"),
            created_at=s["created_at"],
            completed_at=s.get("completed_at"),
            error_message=s.get("error_message"),
        )
        for s in steps_raw
    ]

    # Get all tool calls
    tool_calls_raw = await agent_repo.get_tool_calls_for_run(run_id)
    tool_calls = [
        AgentToolCallResponse(
            id=tc["id"],  # DB column is 'id', not 'tool_call_id'
            run_id=tc["run_id"],
            step_id=tc["step_id"],
            tool_name=tc["tool_name"],
            arguments=(
                tc.get("arguments", {})
                if isinstance(tc.get("arguments"), dict)
                else json.loads(tc.get("arguments", "{}"))
            ),
            status=tc["status"],
            result_summary=tc.get("result_summary"),
            error_message=tc.get("error_message"),
            duration_ms=tc.get("duration_ms"),
            created_at=tc["created_at"],
            started_at=tc.get("started_at"),
            completed_at=tc.get("completed_at"),
            idempotency_key=tc.get("idempotency_key", ""),
            execution_attempt=tc.get("execution_attempt", 1),
            approval_decision=tc.get("approval_decision"),
            approval_policy=tc.get("approval_policy"),
            approval_decided_at=tc.get("approval_decided_at"),
            result_detail=tc.get("result_detail"),
        )
        for tc in tool_calls_raw
    ]

    # Get all citations
    citations_raw = await agent_repo.get_citations_for_run(run_id)
    citations = [
        AgentCitationResponse(
            id=c["id"],  # DB column is 'id', not 'citation_id'
            run_id=c["run_id"],
            tool_call_id=c.get("tool_call_id", ""),
            source_url=c["source_url"],
            title=c.get("title"),
            snippet=c.get("snippet", ""),
            used_in_answer=bool(c.get("used_in_answer", False)),
            created_at=c["created_at"],
        )
        for c in citations_raw
    ]

    # Get all artifacts
    artifacts_raw = await agent_repo.get_run_artifacts(run_id)
    artifacts = [
        RunArtifactResponse(
            id=a["id"],
            run_id=a["run_id"],
            artifact_type=a["artifact_type"],
            file_path=a.get("file_path"),
            action=a["action"],
            detail=a.get("detail"),
            tool_call_id=a.get("tool_call_id"),
            created_at=a["created_at"],
        )
        for a in artifacts_raw
    ]

    return AgentRunTraceResponse(
        run_id=run_id,
        status=run.get("status", "unknown"),
        agent_state=run.get("agent_state"),
        steps=steps,
        tool_calls=tool_calls,
        citations=citations,
        artifacts=artifacts,
        final_answer=run.get("final_answer"),
    )


# =============================================================================
# Tool Approval Endpoints
# =============================================================================


@router.post("/runs/{run_id}/approve/{tool_call_id}")
async def approve_tool_call(run_id: str, tool_call_id: str, http_request: Request):
    """Approve a tool call that requires permission.

    Resolves the approval Future with True, allowing tool execution to proceed.
    """
    session_id, is_owner = get_session_context(http_request)
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    queues = _approval_queues.get(run_id, {})
    future = queues.get(tool_call_id)

    if future is None:
        raise HTTPException(status_code=404, detail="No pending approval for this tool call")

    if not future.done():
        future.set_result(True)

    logger.info(
        "Tool call approved",
        extra={"run_id": run_id, "tool_call_id": tool_call_id},
    )
    return {"status": "approved", "run_id": run_id, "tool_call_id": tool_call_id}


@router.post("/runs/{run_id}/deny/{tool_call_id}")
async def deny_tool_call(run_id: str, tool_call_id: str, http_request: Request):
    """Deny a tool call that requires permission.

    Resolves the approval Future with False, blocking tool execution.
    """
    session_id, is_owner = get_session_context(http_request)
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    queues = _approval_queues.get(run_id, {})
    future = queues.get(tool_call_id)

    if future is None:
        raise HTTPException(status_code=404, detail="No pending approval for this tool call")

    if not future.done():
        future.set_result(False)

    logger.info(
        "Tool call denied",
        extra={"run_id": run_id, "tool_call_id": tool_call_id},
    )
    return {"status": "denied", "run_id": run_id, "tool_call_id": tool_call_id}
