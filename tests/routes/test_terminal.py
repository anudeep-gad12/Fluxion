"""Tests for browser terminal routes and websocket terminal attach."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import orchestrator.storage.db as db_module
from orchestrator.app import app
from orchestrator.services import browser_terminal as terminal_module
from orchestrator.storage.db import Database


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
    terminal_module._terminal_manager = None
    with patch("orchestrator.services.browser_terminal._get_default_shell", return_value="/bin/sh"):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    terminal_module._terminal_manager = None


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
        first = websocket.receive_json()
        assert first["type"] == "status"
        websocket.send_json({"type": "input", "data": "printf '__HELLO__\\n'\r"})

        combined = ""
        for _ in range(20):
            payload = websocket.receive_json()
            if payload["type"] == "output":
                combined += payload.get("data", "")
                if "__HELLO__" in combined:
                    break

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
        websocket.receive_json()  # initial status

        websocket.send_json({"type": "input", "data": "cat\r"})
        websocket.send_json({"type": "input", "data": "hello from cat\n"})
        websocket.send_json({"type": "input", "data": "\u0003"})
        websocket.send_json({"type": "input", "data": "printf '__AFTER__\\n'\r"})

        combined = ""
        for _ in range(40):
            payload = websocket.receive_json()
            if payload["type"] == "output":
                combined += payload.get("data", "")
                if "__AFTER__" in combined:
                    break

        assert "__AFTER__" in combined

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
