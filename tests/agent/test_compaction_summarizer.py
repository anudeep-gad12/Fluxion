"""Tests for LLM-written compaction handoff summaries."""

from unittest.mock import AsyncMock

import pytest

from orchestrator.agent.coding_session import CodingSessionEntry
from orchestrator.agent.compaction_summarizer import (
    SUMMARY_HANDOFF_PREFIX,
    bound_transcript,
    render_entries_as_transcript,
    render_llm_checkpoint_content,
    summarize_for_compaction,
)
from orchestrator.providers.base import LLMResponse


def _entry(seq: int, entry_type: str, content_json: dict) -> CodingSessionEntry:
    role_by_type = {
        "user": "user",
        "assistant": "assistant",
        "assistant_tool_calls": "assistant",
        "tool_result": "tool",
        "compaction_summary": "user",
    }
    return CodingSessionEntry(
        conversation_id="conv-1",
        seq=seq,
        run_id="run-1",
        step_number=seq,
        entry_type=entry_type,
        role=role_by_type[entry_type],
        content_json=content_json,
        token_estimate=10,
    )


def _sample_entries() -> list[CodingSessionEntry]:
    return [
        _entry(1, "user", {"content": "Fix the sorting bug in chart.ts"}),
        _entry(
            2,
            "assistant_tool_calls",
            {
                "content": "Reading the file.",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "function": {"name": "read_file", "arguments": '{"file_path":"chart.ts"}'},
                    }
                ],
            },
        ),
        _entry(
            3,
            "tool_result",
            {"tool_call_id": "tc-1", "name": "read_file", "content": "const x = 1;", "success": True},
        ),
        _entry(4, "assistant", {"content": "Found the bug in the comparator."}),
    ]


def test_render_entries_as_transcript_covers_all_entry_types():
    transcript = render_entries_as_transcript(_sample_entries())
    assert "USER: Fix the sorting bug" in transcript
    assert "ASSISTANT_TOOL_CALLS:" in transcript
    assert "read_file(" in transcript
    assert "TOOL read_file (ok): const x = 1;" in transcript
    assert "ASSISTANT: Found the bug" in transcript


def test_render_entries_marks_failed_tools():
    entries = [
        _entry(
            1,
            "tool_result",
            {"tool_call_id": "tc-1", "name": "bash", "content": "boom", "success": False},
        )
    ]
    assert "TOOL bash (FAILED): boom" in render_entries_as_transcript(entries)


def test_bound_transcript_middle_truncates_with_marker():
    text = "a" * 500 + "MIDDLE" + "b" * 500
    bounded = bound_transcript(text, 300)
    assert len(bounded) < len(text)
    assert "chars of transcript omitted" in bounded
    assert bounded.startswith("a")
    assert bounded.endswith("b")


@pytest.mark.asyncio
async def test_summarize_for_compaction_returns_summary():
    provider = AsyncMock()
    provider.complete.return_value = LLMResponse(
        text="## Progress\n- Found comparator bug in chart.ts\n## Next Steps\n- Patch and test"
    )

    summary = await summarize_for_compaction(
        provider=provider,
        model="test-model",
        entries=_sample_entries(),
        durable_state_text="goal: fix sorting",
    )

    assert summary is not None
    assert "comparator bug" in summary
    call_kwargs = provider.complete.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["temperature"] == 0.2
    user_message = call_kwargs["messages"][1]["content"]
    assert "TRANSCRIPT TO COMPACT" in user_message
    assert "DURABLE SESSION STATE" in user_message


@pytest.mark.asyncio
async def test_summarize_for_compaction_swallows_provider_errors():
    provider = AsyncMock()
    provider.complete.side_effect = RuntimeError("provider down")

    summary = await summarize_for_compaction(
        provider=provider,
        model="test-model",
        entries=_sample_entries(),
    )

    assert summary is None


@pytest.mark.asyncio
async def test_summarize_for_compaction_rejects_trivial_output():
    provider = AsyncMock()
    provider.complete.return_value = LLMResponse(text="ok")

    summary = await summarize_for_compaction(
        provider=provider,
        model="test-model",
        entries=_sample_entries(),
    )

    assert summary is None


@pytest.mark.asyncio
async def test_summarize_for_compaction_empty_entries_returns_none():
    provider = AsyncMock()

    summary = await summarize_for_compaction(
        provider=provider,
        model="test-model",
        entries=[],
    )

    assert summary is None
    provider.complete.assert_not_called()


def test_render_llm_checkpoint_content_envelope():
    content = render_llm_checkpoint_content(
        "## Progress\n- did things",
        read_files=["a.py", "b.py"],
        modified_files=["c.py"],
    )
    assert content.startswith(SUMMARY_HANDOFF_PREFIX)
    assert "<summary>" in content and "</summary>" in content
    assert "<read-files>\na.py\nb.py\n</read-files>" in content
    assert "<modified-files>\nc.py\n</modified-files>" in content
