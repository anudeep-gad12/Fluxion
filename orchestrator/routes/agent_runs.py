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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
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
_active_runs: Dict[str, asyncio.Queue] = {}
_abort_signals: Dict[str, asyncio.Event] = {}
_event_history: Dict[str, List[Dict[str, Any]]] = {}  # For SSE resumption
_run_tokens: Dict[str, str] = {}  # Per-run stream auth tokens


# =============================================================================
# SSE Event Translation
# =============================================================================

# Map engine event types to SSE event types
_EVENT_TYPE_MAP = {
    "agent_started": "agent_state",
    "step_started": "step_start",
    "thinking": "thinking",
    "tool_start": "tool_start",
    "tool_result": "tool_result",
    "synthesizing": "agent_state",
    "answer_token": "answer",
    "agent_complete": "complete",
    "agent_error": "error",
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
    run_id: str, query: str, conversation_id: Optional[str], max_steps: int
) -> None:
    """Background task that runs the agent.

    Args:
        run_id: Unique run identifier.
        query: User's research query.
        conversation_id: Optional conversation context.
        max_steps: Maximum steps for agent execution.
    """
    # Import here to avoid circular imports
    from orchestrator.agent.factory import create_agent_engine

    abort_signal = _abort_signals.get(run_id)
    event_queue = _active_runs.get(run_id)

    if not event_queue:
        logger.error("No event queue for run", extra={"run_id": run_id})
        return

    seq = 0

    def event_callback(event: Dict[str, Any]) -> None:
        """Callback for engine events."""
        nonlocal seq
        if abort_signal and abort_signal.is_set():
            return
        try:
            seq += 1
            event["seq"] = seq
            event_queue.put_nowait(event)
            # Store in history for resumption
            _event_history.setdefault(run_id, []).append(event.copy())
        except asyncio.QueueFull:
            logger.warning("Event queue full", extra={"run_id": run_id})

    try:
        # Create engine and run (pass query for classification)
        engine = await create_agent_engine(max_steps=max_steps, query=query)
        result = await engine.run(
            run_id=run_id,
            query=query,
            event_callback=event_callback,
            conversation_id=conversation_id,
        )

        if abort_signal and not abort_signal.is_set():
            event_queue.put_nowait(
                {
                    "type": "_STREAM_END",
                    "result": {
                        "run_id": result.run_id,
                        "success": result.success,
                        "final_answer": result.final_answer,
                        "citations": result.citations,
                        "total_steps": result.total_steps,
                        "timing_ms": result.timing_ms,
                        "total_tokens": result.total_tokens,
                    },
                }
            )
    except Exception as e:
        logger.error(
            "Agent run failed",
            extra={"run_id": run_id, "error": str(e)},
            exc_info=True,
        )
        if abort_signal is None or not abort_signal.is_set():
            event_queue.put_nowait({"type": "_STREAM_ERROR", "error": str(e)})
    finally:
        asyncio.create_task(_cleanup_run(run_id))


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/runs", response_model=CreateAgentRunResponse)
async def create_agent_run(request: CreateAgentRunRequest):
    """Start a new agent research run.

    The agent executes asynchronously in a background task.
    Use the stream endpoint to receive real-time events.

    Returns:
        run_id and stream_url for SSE events.
    """
    run_id = str(uuid.uuid4())

    try:
        # Initialize state
        event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        abort_signal = asyncio.Event()

        _active_runs[run_id] = event_queue
        _abort_signals[run_id] = abort_signal
        _event_history[run_id] = []
        stream_token = secrets.token_urlsafe(16)
        _run_tokens[run_id] = stream_token

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
            await conv_repo.create(conversation_id=conversation_id, title=title)

        # Create model config snapshot for agent
        model_config = {
            "mode": "agent",
            "max_steps": request.max_steps,
        }

        await trace_repo.create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="agent",
            profile_name="agent",
            model_config=model_config,
            user_message=request.query,
        )

        # Update agent-specific fields
        agent_repo = AgentRepo(db)
        await agent_repo.update_run_agent_state(
            run_id=run_id,
            agent_state="initializing",
            current_step=0,
            max_steps=request.max_steps,
        )

        # Start background task
        asyncio.create_task(
            _run_agent_task(
                run_id=run_id,
                query=request.query,
                conversation_id=conversation_id,
                max_steps=request.max_steps,
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
        )

    except Exception as e:
        # Clean up on failure
        _active_runs.pop(run_id, None)
        _abort_signals.pop(run_id, None)
        _event_history.pop(run_id, None)
        _run_tokens.pop(run_id, None)
        logger.error("Failed to start agent run", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start agent run")


@router.get("/runs/{run_id}", response_model=AgentRunStatusResponse)
async def get_agent_run_status(run_id: str):
    """Get current status of an agent run.

    Returns run metadata, current state, step count, and result if complete.
    """
    db = await get_db()
    trace_repo = TraceRepo(db)
    agent_repo = AgentRepo(db)

    # Get run from trace_repo (base run info)
    run = await trace_repo.get_run(run_id)
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
        max_steps=run.get("max_steps", 10),
        final_answer=run.get("final_answer"),
        error_message=run.get("error_message"),
        created_at=run.get("created_at", ""),
        updated_at=run.get("updated_at"),
    )


@router.get("/runs/{run_id}/stream")
async def stream_agent_events(
    run_id: str,
    since_seq: int = Query(0, description="Resume from this sequence number"),
    token: str = Query("", description="Stream auth token from run creation"),
):
    """Stream agent events via Server-Sent Events.

    Supports resumption via since_seq parameter for reconnection.
    Requires stream token for active runs (returned by POST /runs).
    Sends heartbeat every 30 seconds during idle.
    """
    # Validate stream token for active runs
    expected_token = _run_tokens.get(run_id)
    if expected_token and token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid stream token")
    # Capture parent request ID for SSE context
    parent_request_id = get_request_id()

    async def event_generator():
        # Restore request context in generator
        if parent_request_id:
            set_request_id(parent_request_id)
        set_component("agent-sse")

        chunk_count = 0
        stream_start = time.time()
        seq = since_seq

        logger.info(
            "Agent SSE stream opened",
            extra={"run_id": run_id, "since_seq": since_seq},
        )

        try:
            # Phase 1: Replay missed events if resuming
            if since_seq > 0 and run_id in _event_history:
                for event in _event_history[run_id]:
                    event_seq = event.get("seq", 0)
                    if event_seq > since_seq:
                        chunk_count += 1
                        yield _translate_event(event, event_seq)
                        seq = event_seq

            # Phase 2: Live events from queue
            if run_id in _active_runs:
                queue = _active_runs[run_id]
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        chunk_count += 1

                        if event.get("type") == "_STREAM_END":
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
                            break
                        elif event.get("type") == "_STREAM_ERROR":
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
                                "data": json.dumps({"error": event.get("error")}),
                            }
                            break
                        elif event.get("type") == "_STREAM_ABORTED":
                            logger.warning(
                                "Agent SSE stream aborted",
                                extra={"run_id": run_id, "chunk_count": chunk_count},
                            )
                            yield {
                                "event": "cancelled",
                                "data": json.dumps({"run_id": run_id}),
                            }
                            break
                        else:
                            seq = event.get("seq", seq + 1)
                            yield _translate_event(event, seq)

                    except asyncio.TimeoutError:
                        yield {"event": "heartbeat", "data": "{}"}

            else:
                # Run not active, check if completed in DB
                logger.debug(
                    "Agent SSE stream fallback to DB", extra={"run_id": run_id}
                )
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
async def cancel_agent_run(run_id: str):
    """Cancel an active agent run.

    Signals the background task to stop, drains the queue,
    and sends a cancelled event to SSE clients.
    """
    if run_id not in _active_runs:
        raise HTTPException(
            status_code=404, detail="Run not found or already completed"
        )

    # Signal abort
    if run_id in _abort_signals:
        _abort_signals[run_id].set()

    # Get queue and signal abort to SSE clients
    queue = _active_runs.pop(run_id, None)
    if queue:
        # Drain queue first
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        # Signal cancellation to any listening SSE clients
        try:
            queue.put_nowait({"type": "_STREAM_ABORTED"})
        except asyncio.QueueFull:
            pass

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


@router.get("/runs/{run_id}/trace", response_model=AgentRunTraceResponse)
async def get_agent_run_trace(run_id: str):
    """Get full execution trace for an agent run.

    Returns all steps, tool calls, and citations for detailed analysis.
    """
    db = await get_db()
    trace_repo = TraceRepo(db)
    agent_repo = AgentRepo(db)

    # Get base run info
    run = await trace_repo.get_run(run_id)
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
            arguments=tc.get("arguments", {}) if isinstance(tc.get("arguments"), dict) else json.loads(tc.get("arguments", "{}")),
            status=tc["status"],
            result_summary=tc.get("result_summary"),
            error_message=tc.get("error_message"),
            duration_ms=tc.get("duration_ms"),
            created_at=tc["created_at"],
            started_at=tc.get("started_at"),
            completed_at=tc.get("completed_at"),
            idempotency_key=tc.get("idempotency_key", ""),
            execution_attempt=tc.get("execution_attempt", 1),
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

    return AgentRunTraceResponse(
        run_id=run_id,
        status=run.get("status", "unknown"),
        agent_state=run.get("agent_state"),
        steps=steps,
        tool_calls=tool_calls,
        citations=citations,
        final_answer=run.get("final_answer"),
    )
