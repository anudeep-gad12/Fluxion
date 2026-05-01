"""Conversation routes."""

import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)

from orchestrator.schemas import (
    ConversationResponse,
    ConversationListResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    ConversationDetailResponse,
    UpdateConversationRequest,
    RunResponse,
    trace_to_run,
)
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo
from orchestrator.routes.workspaces import _resolve_workspace_path


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def get_session_context(request: Request) -> Tuple[Optional[str], bool]:
    """Extract session context from request.

    Returns:
        Tuple of (session_id, is_owner).
    """
    session_id = getattr(request.state, "session_id", None)
    is_owner = getattr(request.state, "is_owner", True)
    return session_id, is_owner


@router.post("", response_model=CreateConversationResponse)
async def create_conversation(
    request: CreateConversationRequest,
    http_request: Request,
):
    """Create a new conversation."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversation_id = str(uuid.uuid4())
    workspace_path = (
        str(_resolve_workspace_path(request.workspace_path))
        if request.workspace_path
        else None
    )
    await conv_repo.create(
        conversation_id=conversation_id,
        title=request.title,
        workspace_path=workspace_path,
        session_id=session_id,
    )
    return CreateConversationResponse(conversation_id=conversation_id)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    http_request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List conversations with optional filtering."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversations = await conv_repo.list(
        status=status,
        limit=limit,
        offset=offset,
        session_id=session_id,
        is_owner=is_owner,
    )
    return ConversationListResponse(
        conversations=[ConversationResponse(**c) for c in conversations],
        total=len(conversations),
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str, http_request: Request):
    """Get a conversation and its runs."""
    session_id, is_owner = get_session_context(http_request)

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

    traces = await trace_repo.list_runs_for_conversation(conversation_id)
    runs = [trace_to_run(t) for t in traces]

    return ConversationDetailResponse(
        conversation=ConversationResponse(**conversation),
        runs=runs,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, http_request: Request):
    """Delete a conversation and all its runs."""
    session_id, is_owner = get_session_context(http_request)

    try:
        db = await get_db()
        conv_repo = ConversationRepo(db)

        conversation = await conv_repo.get_with_session_check(
            conversation_id,
            session_id=session_id,
            is_owner=is_owner,
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        await conv_repo.delete(conversation_id)
        return {"status": "deleted", "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Delete conversation failed", extra={"conversation_id": conversation_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    http_request: Request,
):
    """Update conversation metadata (title, status)."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversation = await conv_repo.get_with_session_check(
        conversation_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await conv_repo.update(
        conversation_id=conversation_id,
        title=request.title,
        status=request.status,
    )

    updated = await conv_repo.get(conversation_id)
    return ConversationResponse(**updated)


@router.get("/{conversation_id}/traces")
async def get_conversation_traces(conversation_id: str, http_request: Request):
    """Get all trace events for all runs in a conversation.

    Returns trace events across all runs in chronological order,
    useful for viewing the complete conversation trace history.
    """
    session_id, is_owner = get_session_context(http_request)

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

    events = await trace_repo.get_trace_events_for_conversation(conversation_id)

    return {
        "conversation_id": conversation_id,
        "events": events,
        "total_events": len(events),
    }
