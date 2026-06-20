"""Tests for Codex-style Plan Mode helpers."""

from orchestrator.agent.plan_mode import (
    PLAN_MODE_MUTATING_TOOLS,
    build_plan_implementation_prompt,
    extract_proposed_plan,
    normalize_collaboration_mode,
)


def test_extract_proposed_plan_strips_block():
    parsed = extract_proposed_plan("Intro\n<proposed_plan>\n# Plan\nDo it\n</proposed_plan>")

    assert parsed is not None
    assert parsed.markdown == "# Plan\nDo it"
    assert parsed.visible_answer == "Intro"


def test_extract_proposed_plan_missing_block_returns_none():
    assert extract_proposed_plan("plain answer") is None


def test_normalize_collaboration_mode_defaults_unknown_values():
    assert normalize_collaboration_mode("plan") == "plan"
    assert normalize_collaboration_mode("default") == "default"
    assert normalize_collaboration_mode("execute") == "default"


def test_mutating_tool_set_blocks_runtime_primitives():
    assert {"apply_patch", "exec_command", "write_stdin"}.issubset(
        PLAN_MODE_MUTATING_TOOLS
    )


def test_build_plan_implementation_prompt_uses_codex_handoff():
    prompt = build_plan_implementation_prompt("# Approved Plan")

    assert "A previous agent produced the plan below" in prompt
    assert "# Approved Plan" in prompt
