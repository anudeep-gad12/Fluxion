"""Browser terminal routes and websocket attach endpoint."""

from __future__ import annotations

import asyncio
import secrets
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from orchestrator.config import get_chat_config
from orchestrator.middleware.session import COOKIE_NAME
from orchestrator.schemas import TerminalSessionRequest, TerminalSessionResponse
from orchestrator.services.browser_terminal import (
    DEFAULT_COLS,
    DEFAULT_ROWS,
    get_terminal_manager,
)
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.routes.workspaces import _resolve_workspace_path

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


def _get_http_session_context(request: Request) -> Tuple[Optional[str], bool]:
    return getattr(request.state, "session_id", None), getattr(request.state, "is_owner", True)


def _get_ws_session_context(websocket: WebSocket) -> Tuple[Optional[str], bool]:
    config = get_chat_config()
    if not config.demo or not config.demo.enabled:
        return None, True

    owner_secret = config.demo.owner_secret
    owner_token = websocket.query_params.get("owner")
    if owner_secret and owner_token and secrets.compare_digest(owner_token, owner_secret):
        return websocket.cookies.get(COOKIE_NAME), True
    return websocket.cookies.get(COOKIE_NAME), False


async def _require_conversation_access(
    conversation_id: str,
    *,
    session_id: Optional[str],
    is_owner: bool,
) -> dict:
    db = await get_db()
    repo = ConversationRepo(db)
    conversation = await repo.get_with_session_check(
        conversation_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations/{conversation_id}/session", response_model=TerminalSessionResponse)
async def get_terminal_session(conversation_id: str, http_request: Request):
    session_id, is_owner = _get_http_session_context(http_request)
    await _require_conversation_access(conversation_id, session_id=session_id, is_owner=is_owner)
    manager = get_terminal_manager()
    metadata = await manager.get_metadata(conversation_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    return metadata


@router.post("/conversations/{conversation_id}/session", response_model=TerminalSessionResponse)
async def create_terminal_session(
    conversation_id: str,
    request: TerminalSessionRequest,
    http_request: Request,
):
    session_id, is_owner = _get_http_session_context(http_request)
    await _require_conversation_access(conversation_id, session_id=session_id, is_owner=is_owner)
    workspace_path = str(_resolve_workspace_path(request.workspace_path)) if request.workspace_path else None
    manager = get_terminal_manager()
    return await manager.get_or_create(
        conversation_id=conversation_id,
        workspace_path=workspace_path,
        session_owner=None if is_owner else session_id,
        cols=max(40, request.cols or DEFAULT_COLS),
        rows=max(10, request.rows or DEFAULT_ROWS),
    )


@router.post("/conversations/{conversation_id}/session/restart", response_model=TerminalSessionResponse)
async def restart_terminal_session(
    conversation_id: str,
    request: TerminalSessionRequest,
    http_request: Request,
):
    session_id, is_owner = _get_http_session_context(http_request)
    await _require_conversation_access(conversation_id, session_id=session_id, is_owner=is_owner)
    workspace_path = str(_resolve_workspace_path(request.workspace_path)) if request.workspace_path else None
    manager = get_terminal_manager()
    return await manager.restart(
        conversation_id=conversation_id,
        workspace_path=workspace_path,
        session_owner=None if is_owner else session_id,
        cols=max(40, request.cols or DEFAULT_COLS),
        rows=max(10, request.rows or DEFAULT_ROWS),
    )


@router.post("/conversations/{conversation_id}/session/close")
async def close_terminal_session(conversation_id: str, http_request: Request):
    session_id, is_owner = _get_http_session_context(http_request)
    await _require_conversation_access(conversation_id, session_id=session_id, is_owner=is_owner)
    manager = get_terminal_manager()
    await manager.close(conversation_id)
    return {"status": "closed", "conversation_id": conversation_id}


@router.websocket("/conversations/{conversation_id}/ws")
async def terminal_websocket(
    websocket: WebSocket,
    conversation_id: str,
    session_id: str = Query(...),
):
    requester_session_id, is_owner = _get_ws_session_context(websocket)
    try:
        await _require_conversation_access(
            conversation_id,
            session_id=requester_session_id,
            is_owner=is_owner,
        )
    except HTTPException:
        await websocket.close(code=4404)
        return

    manager = get_terminal_manager()
    metadata = await manager.get_metadata(conversation_id)
    if not metadata or metadata["session_id"] != session_id:
        await websocket.close(code=4404)
        return

    live_session = await manager.get_live(session_id)
    if live_session is None or live_session.status != "running":
        await websocket.accept()
        await websocket.send_json({"type": "status", "status": "stale"})
        await websocket.close()
        return

    await websocket.accept()
    await websocket.send_json(
        {
            "type": "status",
            "status": live_session.status,
            "session_id": live_session.session_id,
            "workspace_path": live_session.workspace_path,
            "shell": live_session.shell,
        }
    )
    replay_text = live_session.replay_text()
    if replay_text:
        await websocket.send_json({"type": "replay", "data": replay_text})

    queue = live_session.attach()

    async def sender() -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(event)

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")
            if event_type == "input":
                await live_session.write(str(payload.get("data", "")))
            elif event_type == "resize":
                cols = int(payload.get("cols") or live_session.cols)
                rows = int(payload.get("rows") or live_session.rows)
                await live_session.resize(cols, rows)
                await manager.touch_resize(conversation_id, live_session.cols, live_session.rows)
            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        live_session.detach(queue)
