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


def test_builder_replays_checkpoint_and_raw_tail_in_order():
    builder = _builder()
    session_state = CodingSessionState(
        objective="Fix sorting",
        checkpoint_summary="CODING SESSION CHECKPOINT\n- Objective: Fix sorting",
        checkpoint_through_seq=4,
        raw_tail_start_seq=5,
    )
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=5,
            run_id="run-1",
            step_number=0,
            entry_type="user",
            role="user",
            content_json={"content": "Do all of it."},
            token_estimate=10,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=6,
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
        raw_entries=entries,
    )

    assert [message["role"] for message in context.messages] == [
        "system",
        "system",
        "user",
        "assistant",
    ]
    assert "CHECKPOINT" in context.messages[1]["content"]
    assert context.raw_tail_start_seq == 5
    assert context.checkpoint_through_seq == 4


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
        raw_entries=entries,
    )

    assert context.messages[1]["role"] == "assistant"
    assert context.messages[1]["content"] == "Reading the file first."
    assert context.messages[1]["tool_calls"][0]["id"] == "tc-1"
    assert context.messages[2]["role"] == "tool"
    assert context.messages[2]["tool_call_id"] == "tc-1"
