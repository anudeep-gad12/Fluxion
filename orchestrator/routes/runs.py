"""Run routes - includes creation, listing, details, and SSE streaming."""

import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from orchestrator.config import get_chat_config
from orchestrator.engine.chat_engine import ChatEngine
from orchestrator.reporting.report_builder import ReportBuilder
from orchestrator.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    CreateConversationRunRequest,
    RunResponse,
    RunListResponse,
    EventResponse,
    trace_to_run,
)
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


router = APIRouter(prefix="/api", tags=["runs"])

# Background task tracking - shared state
_active_runs: dict[str, asyncio.Queue] = {}


def _append_turn_to_summary(existing_summary: str, user_msg: str, assistant_msg: str, max_chars: int = 2000) -> str:
    """Append a single turn to existing summary incrementally."""
    new_turn = f"user: {user_msg.strip()}\nassistant: {assistant_msg.strip()}"
    if not existing_summary:
        return new_turn
    combined = f"{existing_summary}\n{new_turn}"
    if len(combined) <= max_chars:
        return combined
    return "..." + combined[-max_chars:]


def _conversation_title_from_message(message: str, max_len: int = 64) -> str:
    """Generate title from first message."""
    cleaned = " ".join(message.strip().split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


@router.post("/conversations/{conversation_id}/runs", response_model=CreateRunResponse)
async def create_conversation_run(conversation_id: str, request: CreateConversationRunRequest):
    """Send a message to a conversation and get a response."""
    db = await get_db()
    conv_repo = ConversationRepo(db)
    trace_repo = TraceRepo(db)

    conversation = await conv_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    run_id = str(uuid.uuid4())[:8]
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _active_runs[run_id] = event_queue

    # Auto-title from first message
    if not conversation.get("title") or conversation.get("title") == "New conversation":
        title = _conversation_title_from_message(request.message)
        await conv_repo.update(conversation_id, title=title)

    async def run_chat():
        config = get_chat_config()
        engine = ChatEngine(config)

        def event_callback(event: dict):
            try:
                event_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        try:
            result = await engine.chat(
                conversation_id=conversation_id,
                message=request.message,
                run_id=run_id,
                event_callback=event_callback,
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
            event_queue.put_nowait({
                "type": "_STREAM_END",
                "result": {
                    "run_id": result.run_id,
                    "final_answer": result.response,
                    "status": result.status,
                    "error": result.error,
                    "thinking_summary": result.thinking_summary,
                },
            })
        except Exception as e:
            event_queue.put_nowait({"type": "_STREAM_ERROR", "error": str(e)})
        finally:
            await asyncio.sleep(5)
            _active_runs.pop(run_id, None)

    asyncio.create_task(run_chat())

    return CreateRunResponse(
        run_id=run_id,
        stream_url=f"/api/runs/{run_id}/stream",
    )


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(request: CreateRunRequest):
    """Create a new standalone chat run.

    Returns immediately with run_id and stream URL.
    Creates an ephemeral conversation for the run.
    """
    db = await get_db()
    conv_repo = ConversationRepo(db)

    # Create ephemeral conversation
    conversation_id = str(uuid.uuid4())
    await conv_repo.create(
        conversation_id=conversation_id,
        title=_conversation_title_from_message(request.prompt),
    )

    run_id = str(uuid.uuid4())[:8]
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _active_runs[run_id] = event_queue

    async def run_chat():
        config = get_chat_config()
        engine = ChatEngine(config)

        def event_callback(event: dict):
            try:
                event_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        try:
            result = await engine.chat(
                conversation_id=conversation_id,
                message=request.prompt,
                run_id=run_id,
                event_callback=event_callback,
            )

            event_queue.put_nowait({
                "type": "_STREAM_END",
                "result": {
                    "run_id": result.run_id,
                    "final_answer": result.response,
                    "status": result.status,
                    "error": result.error,
                    "thinking_summary": result.thinking_summary,
                },
            })
        except Exception as e:
            event_queue.put_nowait({"type": "_STREAM_ERROR", "error": str(e)})
        finally:
            await asyncio.sleep(5)
            _active_runs.pop(run_id, None)

    asyncio.create_task(run_chat())

    return CreateRunResponse(
        run_id=run_id,
        stream_url=f"/api/runs/{run_id}/stream",
    )


@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: str):
    """Stream events for a run using Server-Sent Events."""

    async def event_generator():
        if run_id in _active_runs:
            queue = _active_runs[run_id]
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if event.get("type") == "_STREAM_END":
                        yield {
                            "event": "complete",
                            "data": json.dumps(event.get("result", {})),
                        }
                        break
                    elif event.get("type") == "_STREAM_ERROR":
                        yield {
                            "event": "error",
                            "data": json.dumps({"error": event.get("error")}),
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
            db = await get_db()
            trace_repo = TraceRepo(db)
            trace = await trace_repo.get_run(run_id)
            if trace:
                if trace.get("status") in ("succeeded", "failed"):
                    yield {
                        "event": "complete",
                        "data": json.dumps({
                            "run_id": run_id,
                            "status": trace.get("status"),
                            "final_answer": trace.get("final_answer"),
                            "thinking_summary": trace.get("thinking_summary"),
                        }),
                    }

    return EventSourceResponse(event_generator())


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    status: Optional[str] = Query(None, description="Filter by status"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all runs with optional filtering."""
    db = await get_db()
    trace_repo = TraceRepo(db)

    traces = await trace_repo.list_runs(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )

    runs = []
    for t in traces:
        if status is None or t.get("status") == status:
            runs.append(trace_to_run(t))

    return RunListResponse(runs=runs, total=len(runs))


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get details of a specific run."""
    db = await get_db()
    trace_repo = TraceRepo(db)

    trace = await trace_repo.get_run(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")

    return trace_to_run(trace)


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    since_seq: Optional[int] = Query(None, description="Get events after this sequence number"),
):
    """Get events for a run."""
    db = await get_db()
    trace_repo = TraceRepo(db)

    trace = await trace_repo.get_run(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = await trace_repo.get_model_calls(run_id)

    events = []
    for step in steps:
        seq = step.get("seq", 0)
        if since_seq is not None and seq <= since_seq:
            continue
        metadata = step.get("metadata", {})
        events.append(EventResponse(
            run_id=run_id,
            seq=seq,
            ts=step.get("created_at", ""),
            type=step.get("step_type", "unknown"),
            display=metadata,
            payload=metadata,
        ))

    return {"events": [e.model_dump() for e in events]}


@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: str):
    """Get human-readable report for a run."""
    db = await get_db()
    trace_repo = TraceRepo(db)

    trace = await trace_repo.get_run(run_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = await trace_repo.get_model_calls(run_id)

    # Build report
    builder = ReportBuilder(format="markdown")
    builder.add_summary(run_id=run_id, status=trace.get("status", "unknown"))

    timeline = []
    for step in steps:
        meta = step.get("metadata", {})
        timeline.append({
            "seq": step.get("seq"),
            "type": step.get("step_type"),
            "duration_ms": meta.get("timing_ms"),
        })

    report = builder.build()

    return {
        "run_id": run_id,
        "report": report,
        "timeline": timeline,
    }


@router.get("/runs/{run_id}/thinking")
async def get_run_thinking(
    run_id: str,
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
    if detail not in ("user", "internal", "full"):
        raise HTTPException(
            status_code=400,
            detail="Invalid detail level. Use 'user', 'internal', or 'full'",
        )

    db = await get_db()
    trace_repo = TraceRepo(db)

    thinking = await trace_repo.get_thinking(run_id, detail=detail)

    if "error" in thinking:
        raise HTTPException(status_code=404, detail=thinking["error"])

    return thinking
