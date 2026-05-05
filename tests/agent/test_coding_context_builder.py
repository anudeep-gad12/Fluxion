"""Tests for coding-session prompt reconstruction."""

from orchestrator.agent.coding_context_builder import CodingSessionContextBuilder
from orchestrator.agent.coding_session import CodingSessionEntry, CodingSessionState
from orchestrator.utils.tokens import get_token_counter


def _builder() -> CodingSessionContextBuilder:
    return CodingSessionContextBuilder(
        token_counter=get_token_counter(),
        max_context_tokens=100000,
        reserve_for_response=4096,
    )


def test_builder_replays_transcript_and_metadata_in_order():
    builder = _builder()
    session_state = CodingSessionState(
        objective="Fix sorting",
        modified_files=["src/chart.ts"],
        read_files=["src/chart.ts", "src/table.ts"],
    )
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=1,
            run_id="run-1",
            step_number=0,
            entry_type="user",
            role="user",
            content_json={"content": "Do all of it."},
            token_estimate=10,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=2,
            run_id="run-1",
            step_number=1,
            entry_type="assistant",
            role="assistant",
            content_json={"content": "Inspecting the relevant file."},
            token_estimate=10,
        ),
    ]

    context = builder.build(
        system_prompt="System prompt",
        session_state=session_state,
        transcript_entries=entries,
    )

    assert [message["role"] for message in context.messages] == [
        "system",
        "system",
        "user",
        "assistant",
    ]
    assert "CODING SESSION METADATA" in context.messages[1]["content"]
    assert "touched_files: src/chart.ts" in context.messages[1]["content"]
    assert context.metadata_included is True


def test_builder_merges_assistant_text_with_canonical_tool_calls():
    builder = _builder()
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=1,
            run_id="run-1",
            step_number=1,
            entry_type="assistant",
            role="assistant",
            content_json={"content": "Reading the file first."},
            token_estimate=10,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=2,
            run_id="run-1",
            step_number=1,
            entry_type="assistant_tool_calls",
            role="assistant",
            content_json={
                "content": "",
                "tool_calls": [{"id": "tc-1", "function": {"name": "read_file"}}],
            },
            token_estimate=10,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=3,
            run_id="run-1",
            step_number=1,
            entry_type="tool_result",
            role="tool",
            content_json={
                "tool_call_id": "tc-1",
                "name": "read_file",
                "content": "Read src/chart.ts",
            },
            token_estimate=10,
        ),
    ]

    context = builder.build(
        system_prompt="System prompt",
        session_state=CodingSessionState(),
        transcript_entries=entries,
    )

    assert context.messages[1]["role"] == "assistant"
    assert context.messages[1]["content"] == "Reading the file first."
    assert context.messages[1]["tool_calls"][0]["id"] == "tc-1"
    assert context.messages[2]["role"] == "tool"
    assert context.messages[2]["tool_call_id"] == "tc-1"


def test_builder_skips_replay_ineligible_assistant_entries():
    builder = _builder()
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=1,
            run_id="run-1",
            step_number=1,
            entry_type="assistant",
            role="assistant",
            content_json={"content": "Manual patch dump", "replay_eligible": False},
            token_estimate=10,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=2,
            run_id="run-1",
            step_number=1,
            entry_type="tool_result",
            role="tool",
            content_json={
                "tool_call_id": "tc-1",
                "name": "edit_file",
                "content": "Missing required args",
                "replay_eligible": True,
            },
            token_estimate=10,
        ),
    ]

    context = builder.build(
        system_prompt="System prompt",
        session_state=CodingSessionState(),
        transcript_entries=entries,
    )

    assert [message["role"] for message in context.messages] == ["system", "tool"]


def test_builder_replays_checkpoint_then_metadata_then_restored_files_then_tail():
    builder = _builder()
    session_state = CodingSessionState(
        modified_files=["src/app.ts"],
        read_files=["src/app.ts", "src/util.ts"],
    )
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=4,
            run_id="run-2",
            step_number=2,
            entry_type="compaction_summary",
            role="user",
            content_json={
                "content": "The earlier part of this coding conversation was compacted...",
                "covered_through_seq": 3,
            },
            token_estimate=20,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=5,
            run_id="run-3",
            step_number=0,
            entry_type="user",
            role="user",
            content_json={"content": "still broken in src/app.ts"},
            token_estimate=10,
        ),
    ]
    restored_messages = [
        {
            "role": "assistant",
            "content": "Restoring important current file context from the workspace before continuing.",
            "tool_calls": [
                {
                    "id": "checkpoint-read-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"file_path":"src/app.ts"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "checkpoint-read-1",
            "name": "read_file",
            "content": "     1\tconst app = true;",
        },
    ]

    context = builder.build(
        system_prompt="System prompt",
        session_state=session_state,
        transcript_entries=entries,
        restored_file_messages=restored_messages,
    )

    assert [message["role"] for message in context.messages] == [
        "system",
        "user",
        "system",
        "assistant",
        "tool",
        "user",
    ]
    assert context.checkpoint_present is True
    assert context.restored_file_count == 1
    assert context.preserved_tail_count == 1
    assert context.replay_source_ranges["checkpoint_seq"] == 4
    assert context.replay_source_ranges["tail_start_seq"] == 5
