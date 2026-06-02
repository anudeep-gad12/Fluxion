"""Run routes - includes creation, listing, details, and SSE streaming."""

import asyncio
import json
import time
import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from orchestrator.config import get_chat_config
from orchestrator.logging_config import get_logger, get_request_id, set_request_id, set_component

logger = get_logger(__name__)
from orchestrator.engine.chat_engine import ChatEngine
from orchestrator.reporting.report_builder import ReportBuilder
from orchestrator.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    CreateConversationRunRequest,
    RunResponse,
    RunListResponse,
    EventResponse,
    TraceEventResponse,
    RunTimelineResponse,
    trace_to_run,
)
from orchestrator.storage.db import get_db
from orchestrator.services.reasoning_settings import get_runtime_reasoning_settings
from orchestrator.services.conversation_rewind import capture_rewind_checkpoint
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo
from orchestrator.conversation_titles import conversation_title_from_message


router = APIRouter(prefix="/api", tags=["runs"])

# Background task tracking - shared state
# WARNING: _active_runs is in-memory, single-process only.
# For multi-worker prod deployment, use Redis pub/sub or durable event bus.
_active_runs: dict[str, asyncio.Queue] = {}

# Abort signals for cancellation - maps run_id to asyncio.Event
# When set, the background task should stop generating and clean up
_abort_signals: dict[str, asyncio.Event] = {}

# Track session_id for active runs (for SSE stream validation)
_run_sessions: dict[str, str] = {}


def get_session_context(request: Request) -> Tuple[Optional[str], bool]:
    """Extract session context from request.

    Returns:
        Tuple of (session_id, is_owner).
    """
    session_id = getattr(request.state, "session_id", None)
    is_owner = getattr(request.state, "is_owner", True)
    return session_id, is_owner


async def _check_session_usage(session_id: Optional[str], is_owner: bool) -> None:
    """Check if session has exceeded message limit. Raises 429 if over limit."""
    if is_owner or not session_id:
        return
    config = get_chat_config()
    if not config.demo or not config.demo.enabled:
        return
    limit = int(getattr(config.demo, "message_limit", 10) or 10)
    if limit <= 0:
        return
    db = await get_db()
    cursor = await db.conn.execute(
        "SELECT COUNT(*) FROM runs WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    used = row[0] if row else 0
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Message limit reached. You can send {limit} messages per session.",
        )


@router.get("/usage")
async def get_usage(http_request: Request):
    """Get session usage stats for rate limit display."""
    session_id, is_owner = get_session_context(http_request)
    if is_owner:
        return {"limit": -1, "used": 0, "remaining": -1}

    config = get_chat_config()
    if not config.demo or not config.demo.enabled:
        return {"limit": -1, "used": 0, "remaining": -1}

    limit = int(getattr(config.demo, "message_limit", 10) or 10)
    if limit <= 0:
        return {"limit": -1, "used": 0, "remaining": -1}

    db = await get_db()
    cursor = await db.conn.execute(
        "SELECT COUNT(*) FROM runs WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    used = row[0] if row else 0
    return {"limit": limit, "used": used, "remaining": max(0, limit - used)}


def _append_turn_to_summary(
    existing_summary: str, user_msg: str, assistant_msg: str, max_chars: int = 2000
) -> str:
    """Append a single turn to existing summary incrementally."""
    new_turn = f"user: {user_msg.strip()}\nassistant: {assistant_msg.strip()}"
    if not existing_summary:
        return new_turn
    combined = f"{existing_summary}\n{new_turn}"
    if len(combined) <= max_chars:
        return combined
    return "..." + combined[-max_chars:]


def _mode_to_strategy(thinking_mode: str, mode_mapping: dict) -> str:
    """Map UI thinking mode to strategy name using config."""
    return mode_mapping.get(thinking_mode, "direct")


async def _get_provider_for_session(
    session_id: Optional[str],
    is_owner: bool,
    provider_header: Optional[str],
    model: Optional[str] = None,
) -> Optional[object]:
    """Get a provider override based on session's ChatGPT tokens or model registry.

    Returns a ChatGPTProvider if the user has valid ChatGPT tokens and
    has requested the chatgpt provider. If model is specified and provider
    is not chatgpt, tries model registry resolution. Returns None to use default.

    Args:
        session_id: Browser session ID.
        provider_header: Value of X-Provider header (e.g., "chatgpt").
        model: Optional model name override (e.g., "qwen3-72b").

    Returns:
        LLMProvider instance or None for default.
    """
    from orchestrator.routes.auth import get_chatgpt_auth_session_id

    auth_session_id = get_chatgpt_auth_session_id(session_id=session_id, is_owner=is_owner)

    # ChatGPT path
    if auth_session_id and provider_header == "chatgpt":
        try:
            from orchestrator.routes.auth import get_valid_tokens
            from orchestrator.providers.factory import create_chatgpt_provider

            tokens = await get_valid_tokens(auth_session_id)
            if tokens:
                return create_chatgpt_provider(
                    tokens,
                    model=model,
                    auth_session_id=auth_session_id,
                )
        except Exception as e:
            logger.warning("Failed to create ChatGPT provider", extra={"error": str(e)})
        return None

    # Model registry path: if model header is set and not chatgpt, try registry
    if model and provider_header != "chatgpt":
        try:
            from orchestrator.providers.factory import create_provider_for_model

            provider, _resolved = create_provider_for_model(model)
            return provider
        except (ValueError, Exception) as e:
            logger.warning(
                "Failed to resolve model via registry",
                extra={"model": model, "error": str(e)},
            )

    # Web UI fallback: use the last model selected via picker
    if not model and provider_header != "chatgpt":
        from orchestrator.routes.models import get_active_model, get_active_model_name

        active_model = get_active_model()
        if active_model and active_model.provider_name == "chatgpt" and auth_session_id:
            try:
                from orchestrator.routes.auth import get_valid_tokens
                from orchestrator.providers.factory import create_chatgpt_provider

                tokens = await get_valid_tokens(auth_session_id)
                if tokens:
                    return create_chatgpt_provider(
                        tokens,
                        model=active_model.model_id,
                        auth_session_id=auth_session_id,
                    )
            except Exception as e:
                logger.warning("Failed to create active ChatGPT provider", extra={"error": str(e)})

        active_name = get_active_model_name()
        if active_name and not (active_model and active_model.provider_name == "chatgpt"):
            try:
                from orchestrator.providers.factory import create_provider_for_model

                provider, _resolved = create_provider_for_model(active_name)
                return provider
            except Exception:
                pass

    return None


@router.post("/conversations/{conversation_id}/runs", response_model=CreateRunResponse)
async def create_conversation_run(
    conversation_id: str,
    request: CreateConversationRunRequest,
    http_request: Request,
):
    """Send a message to a conversation and get a response."""
    session_id, is_owner = get_session_context(http_request)
    await _check_session_usage(session_id, is_owner)

    db = await get_db()
    conv_repo = ConversationRepo(db)
    trace_repo = TraceRepo(db)

    conversation = await conv_repo.get_with_session_check(
        conversation_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    run_id = str(uuid.uuid4())
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _active_runs[run_id] = event_queue

    # Track session for SSE validation
    if session_id:
        _run_sessions[run_id] = session_id

    # Auto-title from first message
    if not conversation.get("title") or conversation.get("title") == "New conversation":
        title = conversation_title_from_message(request.message)
        await conv_repo.update(conversation_id, title=title)

    await capture_rewind_checkpoint(
        conversation=conversation,
        run_id=run_id,
        user_message=request.message,
        conversation_repo=conv_repo,
        agent_repo=AgentRepo(db),
    )

    # Capture session_id for background task
    run_session_id = session_id
    reasoning_settings, _, _ = await get_runtime_reasoning_settings()

    async def run_chat():
        config = get_chat_config()

        # Check for ChatGPT provider override or model registry
        model_header = http_request.headers.get("x-model")
        provider_override = await _get_provider_for_session(
            run_session_id,
            is_owner,
            http_request.headers.get("x-provider"),
            model=model_header,
        )
        engine = ChatEngine(config, provider=provider_override, model_name=model_header)

        def event_callback(event: dict):
            try:
                event_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Event queue full", extra={"run_id": run_id})

        # Map UI mode to strategy (from config)
        strategy = _mode_to_strategy(request.thinking_mode, config.thinking.mode_mapping)

        try:
            result = await engine.chat(
                conversation_id=conversation_id,
                message=request.message,
                run_id=run_id,
                event_callback=event_callback,
                thinking_strategy=strategy,
                reasoning_effort=request.reasoning_effort,
                reasoning_settings=reasoning_settings,
                session_id=run_session_id,
                image_attachments=request.image_attachments,
            )

            # Update conversation summary
            if result.status == "succeeded":
                current_summary = conversation.get("summary") or ""
                new_summary = _append_turn_to_summary(
                    current_summary,
                    request.message,
                    result.response,
                )
                await conv_repo.update(conversation_id, summary=new_summary)

            # Signal completion
            event_queue.put_nowait(
                {
                    "type": "_STREAM_END",
                    "result": {
                        "run_id": result.run_id,
                        "final_answer": result.response,
                        "status": result.status,
                        "error": result.error,
                        "thinking_summary": result.thinking_summary,
                    },
                }
            )
        except Exception:
            logger.exception("Chat run failed", extra={"run_id": run_id})
            event_queue.put_nowait({"type": "_STREAM_ERROR", "error": "Internal server error"})
            # Immediate cleanup on error
            _active_runs.pop(run_id, None)
            _run_sessions.pop(run_id, None)
            return
        finally:
            # Always close the engine to release HTTP connections
            await engine.close()
        # Delay cleanup on success for late joiners
        await asyncio.sleep(2)
        _active_runs.pop(run_id, None)
        _run_sessions.pop(run_id, None)

    asyncio.create_task(run_chat())

    return CreateRunResponse(
        run_id=run_id,
        stream_url=f"/api/runs/{run_id}/stream",
    )


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(request: CreateRunRequest, http_request: Request):
    """Create a new standalone chat run.

    Returns immediately with run_id and stream URL.
    Creates an ephemeral conversation for the run.
    """
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    conv_repo = ConversationRepo(db)

    # Create ephemeral conversation with session_id
    conversation_id = str(uuid.uuid4())
    await conv_repo.create(
        conversation_id=conversation_id,
        title=conversation_title_from_message(request.prompt),
        session_id=session_id,
    )

    run_id = str(uuid.uuid4())
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _active_runs[run_id] = event_queue

    # Track session for SSE validation
    if session_id:
        _run_sessions[run_id] = session_id

    # Capture session_id for background task
    run_session_id = session_id
    reasoning_settings, _, _ = await get_runtime_reasoning_settings()

    async def run_chat():
        config = get_chat_config()

        # Check for ChatGPT provider override or model registry
        model_header = http_request.headers.get("x-model")
        provider_override = await _get_provider_for_session(
            run_session_id,
            is_owner,
            http_request.headers.get("x-provider"),
            model=model_header,
        )
        engine = ChatEngine(config, provider=provider_override, model_name=model_header)

        def event_callback(event: dict):
            try:
                event_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Event queue full", extra={"run_id": run_id})

        try:
            result = await engine.chat(
                conversation_id=conversation_id,
                message=request.prompt,
                run_id=run_id,
                event_callback=event_callback,
                reasoning_settings=reasoning_settings,
                session_id=run_session_id,
                image_attachments=request.image_attachments,
            )

            event_queue.put_nowait(
                {
                    "type": "_STREAM_END",
                    "result": {
                        "run_id": result.run_id,
                        "final_answer": result.response,
                        "status": result.status,
                        "error": result.error,
                        "thinking_summary": result.thinking_summary,
                    },
                }
            )
        except Exception:
            logger.exception("Chat run failed", extra={"run_id": run_id})
            event_queue.put_nowait({"type": "_STREAM_ERROR", "error": "Internal server error"})
            # Immediate cleanup on error
            _active_runs.pop(run_id, None)
            _run_sessions.pop(run_id, None)
            return
        finally:
            # Always close the engine to release HTTP connections
            await engine.close()
        # Delay cleanup on success for late joiners
        await asyncio.sleep(2)
        _active_runs.pop(run_id, None)
        _run_sessions.pop(run_id, None)

    asyncio.create_task(run_chat())

    return CreateRunResponse(
        run_id=run_id,
        stream_url=f"/api/runs/{run_id}/stream",
    )


@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str, http_request: Request):
    """Stream events for a run using Server-Sent Events."""
    session_id, is_owner = get_session_context(http_request)

    # Verify session ownership for active runs
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
        # Restore request ID in generator context
        if parent_request_id:
            set_request_id(parent_request_id)
        set_component("sse")

        chunk_count = 0
        stream_start = time.time()

        logger.info(f"SSE stream opened", extra={"run_id": run_id})

        try:
            if run_id in _active_runs:
                queue = _active_runs[run_id]
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        chunk_count += 1

                        if event.get("type") == "_STREAM_END":
                            duration_ms = int((time.time() - stream_start) * 1000)
                            logger.info(
                                "SSE stream completed",
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
                            break
                        elif event.get("type") == "_STREAM_ERROR":
                            logger.error(
                                "SSE stream error",
                                extra={
                                    "run_id": run_id,
                                    "error": event.get("error"),
                                    "chunk_count": chunk_count,
                                },
                            )
                            # Don't leak internal error details to client
                            yield {
                                "event": "error",
                                "data": json.dumps({"error": "Internal server error"}),
                            }
                            break
                        elif event.get("type") == "_STREAM_ABORTED":
                            logger.warning(
                                "SSE stream aborted",
                                extra={
                                    "run_id": run_id,
                                    "chunk_count": chunk_count,
                                },
                            )
                            yield {
                                "event": "aborted",
                                "data": json.dumps({"run_id": run_id}),
                            }
                            break
                        else:
                            yield {
                                "event": "event",
                                "data": json.dumps(event),
                            }
                    except asyncio.TimeoutError:
                        yield {"event": "ping", "data": "{}"}
            else:
                # Run not active, check DB
                logger.debug(f"SSE stream fallback to DB", extra={"run_id": run_id})
                db = await get_db()
                trace_repo = TraceRepo(db)
                trace = await trace_repo.get_run(run_id)
                if trace:
                    if trace.get("status") in ("succeeded", "failed"):
                        yield {
                            "event": "complete",
                            "data": json.dumps(
                                {
                                    "run_id": run_id,
                                    "status": trace.get("status"),
                                    "final_answer": trace.get("final_answer"),
                                    "thinking_summary": trace.get("thinking_summary"),
                                }
                            ),
                        }
        except asyncio.CancelledError:
            duration_ms = int((time.time() - stream_start) * 1000)
            logger.warning(
                "SSE stream client disconnected",
                extra={
                    "run_id": run_id,
                    "chunk_count": chunk_count,
                    "duration_ms": duration_ms,
                },
            )
            raise

    return EventSourceResponse(event_generator())


@router.post("/runs/{run_id}/abort")
async def abort_run(run_id: str, http_request: Request):
    """Abort a running generation and void the run.

    This immediately:
    1. Signals the background task to stop
    2. Closes the SSE stream by sending abort event
    3. Removes the run from active tracking
    4. Deletes the run from DB (no partial data saved)
    """
    session_id, is_owner = get_session_context(http_request)

    # Verify session ownership
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    # Signal abort if there's an abort signal registered
    if run_id in _abort_signals:
        _abort_signals[run_id].set()

    # Get the queue and signal abort to SSE clients
    queue = _active_runs.pop(run_id, None)
    if queue:
        # Drain queue first
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        # Signal abort to any listening SSE clients
        queue.put_nowait({"type": "_STREAM_ABORTED"})

    # Clean up abort signal and session tracking
    _abort_signals.pop(run_id, None)
    _run_sessions.pop(run_id, None)

    # Delete the run from DB (void - no partial save)
    db = await get_db()
    trace_repo = TraceRepo(db)
    await trace_repo.delete_run(run_id)

    return {"status": "aborted", "run_id": run_id}


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    http_request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all runs with optional filtering."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    traces = await trace_repo.list_runs(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        session_id=session_id,
        is_owner=is_owner,
    )

    runs = []
    for t in traces:
        if status is None or t.get("status") == status:
            runs.append(trace_to_run(t))

    return RunListResponse(runs=runs, total=len(runs))


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, http_request: Request):
    """Get details of a specific run."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    trace = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")

    return trace_to_run(trace)


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    http_request: Request,
    since_seq: Optional[int] = Query(None, description="Get events after this sequence number"),
):
    """Get events for a run."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    trace = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")

    trace_events = await trace_repo.get_trace_events(run_id)

    events = []
    for event in trace_events:
        seq = event.get("seq", 0)
        if since_seq is not None and seq <= since_seq:
            continue
        content = event.get("content", {})
        # Include duration_ms and token_count in payload
        payload = {
            **content,
            "duration_ms": event.get("duration_ms"),
            "token_count": event.get("token_count"),
        }
        events.append(
            EventResponse(
                run_id=run_id,
                seq=seq,
                ts=event.get("created_at", ""),
                type=event.get("event_type", "unknown"),
                display=content,
                payload=payload,
            )
        )

    return {"events": [e.model_dump() for e in events]}


@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: str, http_request: Request):
    """Get human-readable report for a run."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    trace = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")

    trace_events = await trace_repo.get_trace_events(run_id)

    # Build report
    builder = ReportBuilder(format="markdown")
    builder.add_summary(run_id=run_id, status=trace.get("status", "unknown"))

    timeline = []
    for event in trace_events:
        timeline.append(
            {
                "seq": event.get("seq"),
                "type": event.get("event_type"),
                "duration_ms": event.get("duration_ms"),
            }
        )

    report = builder.build()

    return {
        "run_id": run_id,
        "report": report,
        "timeline": timeline,
    }


@router.get("/runs/{run_id}/thinking")
async def get_run_thinking(
    run_id: str,
    http_request: Request,
    detail: str = Query("user", description="Detail level: user, internal, or full"),
):
    """Get thinking trace for a run.

    Args:
        run_id: The run ID.
        detail: Level of detail:
            - "user": Clean, UI-friendly summaries (default)
            - "internal": Full raw traces with tokens, timing, messages
            - "full": Both internal and UI data

    Returns:
        Thinking trace data based on detail level.
    """
    session_id, is_owner = get_session_context(http_request)

    if detail not in ("user", "internal", "full"):
        raise HTTPException(
            status_code=400,
            detail="Invalid detail level. Use 'user', 'internal', or 'full'",
        )

    db = await get_db()
    trace_repo = TraceRepo(db)

    # Verify session ownership first
    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    thinking = await trace_repo.get_thinking(run_id, detail=detail)

    if "error" in thinking:
        raise HTTPException(status_code=404, detail=thinking["error"])

    return thinking


@router.get("/runs/{run_id}/timeline", response_model=RunTimelineResponse)
async def get_run_timeline(run_id: str, http_request: Request):
    """Get complete timeline for a run with all trace events.

    Returns chronologically ordered trace events for debugging and observability.
    Events include: llm_request, llm_response, reasoning, tool_call, tool_response, error, retry.
    """
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    # Verify session ownership first
    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    timeline = await trace_repo.get_run_timeline(run_id)

    if "error" in timeline:
        raise HTTPException(status_code=404, detail=timeline["error"])

    # Convert events to response schema
    events = [
        TraceEventResponse(
            id=e.get("id", ""),
            run_id=e.get("run_id", ""),
            seq=e.get("seq", 0),
            created_at=e.get("created_at", ""),
            event_type=e.get("event_type", ""),
            event_status=e.get("event_status", ""),
            actor=e.get("actor", ""),
            endpoint=e.get("endpoint"),
            attempt=e.get("attempt", 1),
            content=e.get("content", {}),
            parent_event_id=e.get("parent_event_id"),
            step_number=e.get("step_number"),
            duration_ms=e.get("duration_ms"),
            token_count=e.get("token_count"),
            error_message=e.get("error_message"),
        )
        for e in timeline.get("events", [])
    ]

    return RunTimelineResponse(
        run_id=run_id,
        status=timeline.get("status", "unknown"),
        created_at=timeline.get("created_at", ""),
        events=events,
        total_events=timeline.get("total_events", 0),
    )
