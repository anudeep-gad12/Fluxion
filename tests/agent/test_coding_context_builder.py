"""Tests for coding-session prompt reconstruction."""

from orchestrator.agent.coding_context_builder import CodingSessionContextBuilder
from orchestrator.agent.coding_session import (
    CodingContextWindowState,
    CodingSessionEntry,
    CodingSessionState,
)
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
        "user",
        "assistant",
        "system",
    ]
    assert "CODING SESSION CURRENT STATE" in context.messages[-1]["content"]
    assert "changed_files: src/chart.ts" in context.messages[-1]["content"]
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

    assistant = next(message for message in context.messages if message["role"] == "assistant")
    tool = next(message for message in context.messages if message["role"] == "tool")
    assert assistant["content"] == "Reading the file first."
    assert assistant["tool_calls"][0]["id"] == "tc-1"
    assert tool["tool_call_id"] == "tc-1"


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

    assert [message["role"] for message in context.messages] == ["system", "system"]


def test_builder_repairs_missing_tool_outputs():
    builder = _builder()
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=1,
            run_id="run-1",
            step_number=1,
            entry_type="assistant_tool_calls",
            role="assistant",
            content_json={
                "content": "Reading.",
                "tool_calls": [
                    {
                        "id": "tc-missing",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            token_estimate=10,
        ),
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=2,
            run_id="run-1",
            step_number=1,
            entry_type="assistant",
            role="assistant",
            content_json={"content": "Continuing."},
            token_estimate=10,
        ),
    ]

    context = builder.build(
        system_prompt="System prompt",
        session_state=CodingSessionState(),
        transcript_entries=entries,
    )

    assert [message["role"] for message in context.messages] == [
        "system",
        "assistant",
        "tool",
        "assistant",
        "system",
    ]
    assert context.messages[2]["tool_call_id"] == "tc-missing"
    assert "Missing tool output repaired" in context.messages[2]["content"]
    assert context.normalization_stats["repaired_missing_tool_outputs"] == 1


def test_builder_drops_orphan_tool_outputs():
    builder = _builder()
    entries = [
        CodingSessionEntry(
            conversation_id="conv-1",
            seq=1,
            run_id="run-1",
            step_number=1,
            entry_type="tool_result",
            role="tool",
            content_json={
                "tool_call_id": "tc-orphan",
                "name": "read_file",
                "content": "orphan",
            },
            token_estimate=10,
        )
    ]

    context = builder.build(
        system_prompt="System prompt",
        session_state=CodingSessionState(),
        transcript_entries=entries,
    )

    assert [message["role"] for message in context.messages] == ["system", "system"]
    assert context.normalization_stats["dropped_orphan_tool_outputs"] == 1


def _user_entry(seq: int, text: str) -> CodingSessionEntry:
    return CodingSessionEntry(
        conversation_id="conv-1",
        seq=seq,
        run_id=f"run-{seq}",
        step_number=0,
        entry_type="user",
        role="user",
        content_json={"content": text},
        token_estimate=10,
    )


def test_builder_prefix_is_stable_when_entries_append():
    """Appending a transcript entry must extend, not rewrite, the prefix.

    The mutable metadata block is the final message, so everything before it
    must be byte-identical across steps for provider prompt caching to work.
    """
    builder = _builder()
    session_state = CodingSessionState(objective="Fix sorting")
    entries = [_user_entry(1, "first"), _user_entry(2, "second")]

    before = builder.build(
        system_prompt="System prompt",
        session_state=session_state,
        transcript_entries=list(entries),
    )
    session_state.modified_files.append("src/new_file.ts")
    after = builder.build(
        system_prompt="System prompt",
        session_state=session_state,
        transcript_entries=[*entries, _user_entry(3, "third")],
    )

    before_prefix = before.messages[:-1]
    after_prefix = after.messages[: len(before_prefix)]
    assert before_prefix == after_prefix
    assert after.messages[-2]["content"] == "third"
    assert "CODING SESSION CURRENT STATE" in after.messages[-1]["content"]


def test_builder_output_is_deterministic():
    builder = _builder()
    session_state = CodingSessionState(objective="ship", modified_files=["a.py"])
    entries = [_user_entry(1, "hello"), _user_entry(2, "again")]

    first = builder.build(
        system_prompt="System prompt",
        session_state=session_state,
        transcript_entries=list(entries),
    )
    second = builder.build(
        system_prompt="System prompt",
        session_state=session_state,
        transcript_entries=list(entries),
    )

    assert first.messages == second.messages


def test_coding_session_state_persists_context_window_state():
    state = CodingSessionState(
        objective="ship",
        context_window=CodingContextWindowState(
            window_number=2,
            first_window_id="first",
            previous_window_id="prev",
            window_id="current",
            prefill_input_tokens=123,
            pending_new_window_request=True,
            budget_reminder_delivered=True,
            last_active_context_tokens=456,
        ),
    )

    restored = CodingSessionState.from_dict(state.to_dict())

    assert restored.context_window.window_number == 2
    assert restored.context_window.first_window_id == "first"
    assert restored.context_window.previous_window_id == "prev"
    assert restored.context_window.window_id == "current"
    assert restored.context_window.prefill_input_tokens == 123
    assert restored.context_window.pending_new_window_request is True
    assert restored.context_window.budget_reminder_delivered is True
    assert restored.context_window.last_active_context_tokens == 456


def test_builder_replays_checkpoint_then_restored_files_then_tail_then_metadata():
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
        "assistant",
        "tool",
        "user",
        "system",
    ]
    assert "CODING SESSION CURRENT STATE" in context.messages[-1]["content"]
    assert context.checkpoint_present is True
    assert context.restored_file_count == 1
    assert context.preserved_tail_count == 1
    assert context.replay_source_ranges["checkpoint_seq"] == 4
    assert context.replay_source_ranges["tail_start_seq"] == 5
