"""Tests for browser terminal routes and websocket terminal attach."""

import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import orchestrator.storage.db as db_module
from orchestrator.app import app
from orchestrator.services import browser_terminal as terminal_module
from orchestrator.storage.db import Database

_WS_RECEIVE_TIMEOUT_SECONDS = 8.0


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    # TestClient may already have a running loop; use a one-off loop instead.
    fresh = asyncio.new_event_loop()
    try:
        return fresh.run_until_complete(coro)
    finally:
        fresh.close()


def _shutdown_terminal_manager() -> None:
    manager = terminal_module._terminal_manager
    if manager is None:
        return
    if not manager._sessions_by_id:
        terminal_module._terminal_manager = None
        return
    _run_async(manager.shutdown_all())
    terminal_module._terminal_manager = None


def _receive_json_with_timeout(websocket, timeout_seconds: float = _WS_RECEIVE_TIMEOUT_SECONDS) -> Any:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(websocket.receive_json)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            pytest.fail(f"WebSocket receive timed out after {timeout_seconds}s")


def _collect_output_until(
    websocket,
    needle: str,
    *,
    max_messages: int = 40,
    timeout_seconds: float = _WS_RECEIVE_TIMEOUT_SECONDS,
) -> str:
    combined = ""
    for _ in range(max_messages):
        payload = _receive_json_with_timeout(websocket, timeout_seconds)
        if payload.get("type") == "output":
            combined += payload.get("data", "")
            if needle in combined:
                return combined
    return combined


@pytest.fixture(scope="function")
def test_db():
    db_module._db = None
    database = Database(":memory:")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(database.connect())

    async def mock_get_db():
        return database

    with patch("orchestrator.storage.db.get_db", mock_get_db):
        with patch("orchestrator.routes.conversations.get_db", mock_get_db):
            with patch("orchestrator.routes.terminal.get_db", mock_get_db):
                with patch("orchestrator.services.browser_terminal.get_db", mock_get_db):
                    yield database

    loop.run_until_complete(database.close())
    db_module._db = None


@pytest.fixture
def client(test_db):
    _shutdown_terminal_manager()
    with patch("orchestrator.services.browser_terminal._get_default_shell", return_value="/bin/sh"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    _shutdown_terminal_manager()


def _create_conversation(client: TestClient) -> str:
    response = client.post("/api/conversations", json={"title": "Terminal test"})
    assert response.status_code == 200
    return response.json()["conversation_id"]


def test_create_and_get_terminal_session(client, tmp_path: Path):
    conversation_id = _create_conversation(client)

    response = client.post(
        f"/api/terminal/conversations/{conversation_id}/session",
        json={"workspace_path": str(tmp_path), "cols": 100, "rows": 28},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == conversation_id
    assert data["workspace_path"] == str(tmp_path.resolve())
    assert data["status"] == "running"

    again = client.post(
        f"/api/terminal/conversations/{conversation_id}/session",
        json={"workspace_path": str(tmp_path)},
    )
    assert again.status_code == 200
    assert again.json()["session_id"] == data["session_id"]

    fetched = client.get(f"/api/terminal/conversations/{conversation_id}/session")
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == data["session_id"]

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_terminal_websocket_executes_command(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    created = client.post(
        f"/api/terminal/conversations/{conversation_id}/session",
        json={"workspace_path": str(tmp_path)},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with client.websocket_connect(
        f"/api/terminal/conversations/{conversation_id}/ws?session_id={session_id}"
    ) as websocket:
        first = _receive_json_with_timeout(websocket)
        assert first["type"] == "status"
        websocket.send_json({"type": "input", "data": "printf '__HELLO__\\n'\n"})

        combined = _collect_output_until(websocket, "__HELLO__", max_messages=25)
        assert "__HELLO__" in combined

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_terminal_websocket_ctrl_c_interrupts_foreground_process(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    created = client.post(
        f"/api/terminal/conversations/{conversation_id}/session",
        json={"workspace_path": str(tmp_path)},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with client.websocket_connect(
        f"/api/terminal/conversations/{conversation_id}/ws?session_id={session_id}"
    ) as websocket:
        _receive_json_with_timeout(websocket)  # initial status

        websocket.send_json({"type": "input", "data": "printf '__AFTER__\\n'\n"})

        combined = _collect_output_until(websocket, "__AFTER__", max_messages=25)
        assert "__AFTER__" in combined

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_terminal_websocket_allows_packaged_desktop_without_owner_token(client, tmp_path: Path):
    """Desktop HTTP is owner when FLUXION_PACKAGED=true; WebSocket must match."""
    conversation_id = _create_conversation(client)
    workspace = str(tmp_path)
    created = client.post(
        f"/api/terminal/conversations/{conversation_id}/session",
        json={"workspace_path": workspace, "cols": 80, "rows": 24},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with patch("orchestrator.routes.terminal.is_packaged_app", return_value=True):
        with client.websocket_connect(
            f"/api/terminal/conversations/{conversation_id}/ws?session_id={session_id}"
        ) as websocket:
            first = _receive_json_with_timeout(websocket)
            assert first["type"] == "status"
            assert first["status"] == "running"

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_list_and_create_multiple_terminal_sessions(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    workspace = str(tmp_path)

    listed = client.get(f"/api/terminal/conversations/{conversation_id}/sessions")
    assert listed.status_code == 200
    assert listed.json()["sessions"] == []

    first = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions",
        json={"workspace_path": workspace},
    )
    second = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions",
        json={"workspace_path": workspace},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] != second.json()["session_id"]

    listed = client.get(f"/api/terminal/conversations/{conversation_id}/sessions")
    assert listed.status_code == 200
    assert len(listed.json()["sessions"]) == 2

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_terminal_session_limit_returns_409(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    workspace = str(tmp_path)

    with patch.object(
        terminal_module.TerminalSessionManager,
        "_max_sessions",
        return_value=2,
    ):
        assert (
            client.post(
                f"/api/terminal/conversations/{conversation_id}/sessions",
                json={"workspace_path": workspace},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/terminal/conversations/{conversation_id}/sessions",
                json={"workspace_path": workspace},
            ).status_code
            == 200
        )
        blocked = client.post(
            f"/api/terminal/conversations/{conversation_id}/sessions",
            json={"workspace_path": workspace},
        )
        assert blocked.status_code == 409

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_close_single_terminal_session_keeps_others(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    workspace = str(tmp_path)

    first = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions",
        json={"workspace_path": workspace},
    ).json()
    second = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions",
        json={"workspace_path": workspace},
    ).json()

    closed = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions/{first['session_id']}/close"
    )
    assert closed.status_code == 200

    listed = client.get(f"/api/terminal/conversations/{conversation_id}/sessions")
    assert len(listed.json()["sessions"]) == 1
    assert listed.json()["sessions"][0]["session_id"] == second["session_id"]

    cleanup = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert cleanup.status_code == 200


def test_restart_terminal_session_by_id(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    workspace = str(tmp_path)

    created = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions",
        json={"workspace_path": workspace},
    )
    session_id = created.json()["session_id"]

    restarted = client.post(
        f"/api/terminal/conversations/{conversation_id}/sessions/{session_id}/restart",
        json={"workspace_path": workspace},
    )
    assert restarted.status_code == 200
    assert restarted.json()["session_id"] != session_id

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200


def test_restart_terminal_session_replaces_workspace(client, tmp_path: Path):
    conversation_id = _create_conversation(client)
    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()

    created = client.post(
        f"/api/terminal/conversations/{conversation_id}/session",
        json={"workspace_path": str(first_workspace)},
    )
    first_session_id = created.json()["session_id"]

    restarted = client.post(
        f"/api/terminal/conversations/{conversation_id}/session/restart",
        json={"workspace_path": str(second_workspace)},
    )
    assert restarted.status_code == 200
    data = restarted.json()
    assert data["session_id"] != first_session_id
    assert data["workspace_path"] == str(second_workspace.resolve())

    closed = client.post(f"/api/terminal/conversations/{conversation_id}/session/close")
    assert closed.status_code == 200
