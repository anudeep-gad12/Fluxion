"""Conversation routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=CreateConversationResponse)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversation_id = str(uuid.uuid4())
    await conv_repo.create(
        conversation_id=conversation_id,
        title=request.title,
    )
    return CreateConversationResponse(conversation_id=conversation_id)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List conversations with optional filtering."""
    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversations = await conv_repo.list(status=status, limit=limit, offset=offset)
    return ConversationListResponse(
        conversations=[ConversationResponse(**c) for c in conversations],
        total=len(conversations),
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str):
    """Get a conversation and its runs."""
    db = await get_db()
    conv_repo = ConversationRepo(db)
    trace_repo = TraceRepo(db)

    conversation = await conv_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    traces = await trace_repo.list_runs(conversation_id=conversation_id)
    runs = [trace_to_run(t) for t in traces]

    return ConversationDetailResponse(
        conversation=ConversationResponse(**conversation),
        runs=runs,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its runs."""
    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversation = await conv_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await conv_repo.delete(conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    """Update conversation metadata (title, status)."""
    db = await get_db()
    conv_repo = ConversationRepo(db)

    conversation = await conv_repo.get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await conv_repo.update(
        conversation_id=conversation_id,
        title=request.title,
        status=request.status,
    )

    updated = await conv_repo.get(conversation_id)
    return ConversationResponse(**updated)
