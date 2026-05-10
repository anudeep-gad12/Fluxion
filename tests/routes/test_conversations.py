"""Tests for conversation rewind routes."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

import orchestrator.storage.db as db_module
from orchestrator.app import app
from orchestrator.storage.db import Database
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory database for each test."""
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
        with patch("orchestrator.app.get_db", mock_get_db):
            with patch("orchestrator.routes.conversations.get_db", mock_get_db):
                with patch("orchestrator.routes.runs.get_db", mock_get_db):
                    with patch("orchestrator.routes.agent_runs.get_db", mock_get_db):
                        with patch("orchestrator.engine.chat_engine.get_db", mock_get_db):
                            with patch("orchestrator.agent.factory.get_db", mock_get_db):
                                with patch("orchestrator.services.reasoning_settings.get_db", mock_get_db):
                                    yield database

    loop.run_until_complete(database.close())
    db_module._db = None


@pytest.fixture
def client(test_db):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


async def _seed_rewindable_conversation(db: Database, conversation_id: str) -> None:
    trace_repo = TraceRepo(db)
    agent_repo = AgentRepo(db)

    await trace_repo.create_run(
        "run-1",
        conversation_id,
        "agent",
        "agent",
        {"mode": "agent"},
        user_message="Prompt 1",
    )
    await trace_repo.update_run("run-1", final_answer="Answer 1", status="succeeded")
    await trace_repo.create_run(
        "run-2",
        conversation_id,
        "agent",
        "agent",
        {"mode": "agent"},
        user_message="Prompt 2",
    )
    await trace_repo.update_run("run-2", final_answer="Answer 2", status="succeeded")
    await trace_repo.create_run(
        "run-3",
        conversation_id,
        "agent",
        "agent",
        {"mode": "agent"},
        user_message="Prompt 3",
    )
    await trace_repo.update_run("run-3", final_answer="Answer 3", status="succeeded")

    await agent_repo.upsert_coding_session_state(
        conversation_id,
        {
            "objective": "latest",
            "read_files": ["c.py"],
            "modified_files": ["c.py"],
            "file_evidence": {},
            "recent_commands": ["pytest"],
        },
        last_run_id="run-3",
    )
    await agent_repo.append_coding_session_entries(
        conversation_id,
        [
            {
                "run_id": "run-1",
                "step_number": 0,
                "entry_type": "user",
                "role": "user",
                "content_json": {"content": "Prompt 1"},
                "token_estimate": 3,
            },
            {
                "run_id": "run-1",
                "step_number": 1,
                "entry_type": "assistant",
                "role": "assistant",
                "content_json": {"content": "Answer 1"},
                "token_estimate": 3,
            },
            {
                "run_id": "run-2",
                "step_number": 0,
                "entry_type": "user",
                "role": "user",
                "content_json": {"content": "Prompt 2"},
                "token_estimate": 3,
            },
            {
                "run_id": "run-2",
                "step_number": 1,
                "entry_type": "assistant",
                "role": "assistant",
                "content_json": {"content": "Answer 2"},
                "token_estimate": 3,
            },
            {
                "run_id": "run-3",
                "step_number": 0,
                "entry_type": "user",
                "role": "user",
                "content_json": {"content": "Prompt 3"},
                "token_estimate": 3,
            },
            {
                "run_id": "run-3",
                "step_number": 1,
                "entry_type": "assistant",
                "role": "assistant",
                "content_json": {"content": "Answer 3"},
                "token_estimate": 3,
            },
        ],
    )

    conv_repo = ConversationRepo(db)
    await conv_repo.create_rewind_checkpoint(
        conversation_id=conversation_id,
        run_id="run-1",
        user_message="Prompt 1",
        entry_seq_before=0,
        state_before={},
    )
    await conv_repo.create_rewind_checkpoint(
        conversation_id=conversation_id,
        run_id="run-2",
        user_message="Prompt 2",
        entry_seq_before=2,
        state_before={
            "objective": "after first turn",
            "read_files": ["a.py"],
            "modified_files": ["a.py"],
            "file_evidence": {},
            "recent_commands": ["pytest tests/a.py"],
        },
    )
    await conv_repo.create_rewind_checkpoint(
        conversation_id=conversation_id,
        run_id="run-3",
        user_message="Prompt 3",
        entry_seq_before=4,
        state_before={
            "objective": "after second turn",
            "read_files": ["b.py"],
            "modified_files": ["b.py"],
            "file_evidence": {},
            "recent_commands": ["pytest tests/b.py"],
        },
    )


class TestConversationRewindRoutes:
    """Tests for conversation rewind endpoints."""

    def test_list_checkpoints_excludes_rewound_runs(self, client, test_db, tmp_path):
        loop = asyncio.get_event_loop()
        workspace_path = tmp_path / "project-a"
        workspace_path.mkdir()
        conversation_id = client.post(
            "/api/conversations/",
            json={"title": "Workspace thread", "workspace_path": str(workspace_path)},
        ).json()["conversation_id"]
        loop.run_until_complete(_seed_rewindable_conversation(test_db, conversation_id))
        loop.run_until_complete(
            TraceRepo(test_db).mark_runs_rewound(
                ["run-3"],
                rewound_at="2026-05-10T10:00:00Z",
                rewind_group_id="group-1",
            )
        )

        response = client.get(f"/api/conversations/{conversation_id}/rewind/checkpoints")

        assert response.status_code == 200
        assert [item["run_id"] for item in response.json()["checkpoints"]] == ["run-2", "run-1"]

    def test_rewind_marks_tail_hidden_restores_prompt_and_state(self, client, test_db, tmp_path):
        loop = asyncio.get_event_loop()
        workspace_path = tmp_path / "project-a"
        workspace_path.mkdir()
        conversation_id = client.post(
            "/api/conversations/",
            json={"title": "Workspace thread", "workspace_path": str(workspace_path)},
        ).json()["conversation_id"]
        loop.run_until_complete(_seed_rewindable_conversation(test_db, conversation_id))

        response = client.post(
            f"/api/conversations/{conversation_id}/rewind",
            json={"run_id": "run-2"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["restored_prompt"] == "Prompt 2"
        assert [run["run_id"] for run in payload["runs"]] == ["run-1"]
        assert payload["rewound_run_ids"] == ["run-2", "run-3"]

        async def assert_db_state():
            trace_repo = TraceRepo(test_db)
            agent_repo = AgentRepo(test_db)
            conv_repo = ConversationRepo(test_db)

            visible_runs = await trace_repo.list_runs_for_conversation(conversation_id)
            assert [run["run_id"] for run in visible_runs] == ["run-1"]

            all_entries = await agent_repo.list_coding_session_entries(
                conversation_id,
                include_rewound=True,
            )
            active_entries = await agent_repo.list_coding_session_entries(conversation_id)
            assert [entry["seq"] for entry in active_entries] == [1, 2]
            assert [entry["rewound_at"] is not None for entry in all_entries] == [
                False,
                False,
                True,
                True,
                True,
                True,
            ]

            state = await agent_repo.get_coding_session_state(conversation_id)
            assert state is not None
            assert state["state"]["objective"] == "after first turn"
            assert state["state"]["recent_commands"] == ["pytest tests/a.py"]

            conversation = await conv_repo.get(conversation_id)
            assert conversation is not None
            assert conversation["summary"] == "user: Prompt 1\nassistant: Answer 1"

        loop.run_until_complete(assert_db_state())

    def test_rewind_rejects_active_runs(self, client, test_db, tmp_path):
        loop = asyncio.get_event_loop()
        workspace_path = tmp_path / "project-a"
        workspace_path.mkdir()
        conversation_id = client.post(
            "/api/conversations/",
            json={"title": "Workspace thread", "workspace_path": str(workspace_path)},
        ).json()["conversation_id"]
        loop.run_until_complete(_seed_rewindable_conversation(test_db, conversation_id))
        loop.run_until_complete(
            test_db.conn.execute(
                "UPDATE runs SET status = 'running' WHERE run_id = ?",
                ("run-3",),
            )
        )
        loop.run_until_complete(test_db.conn.commit())

        response = client.post(
            f"/api/conversations/{conversation_id}/rewind",
            json={"run_id": "run-2"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot rewind while a run is still active"
