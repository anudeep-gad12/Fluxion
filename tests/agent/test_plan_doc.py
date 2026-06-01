"""Tests for durable Plan Mode markdown documents."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.agent.plan_doc import (
    create_initial_plan_doc,
    plan_doc_relative_path,
    resolve_plan_doc_path,
)
from orchestrator.agent.plan_mode import PLAN_MODE_MUTATING_TOOLS
from orchestrator.agent.tools.registry import create_browser_agent_tool_registry
from orchestrator.agent.tools.update_plan_doc import UpdatePlanDocTool


def test_plan_doc_relative_path_stays_inside_fluxion_plans():
    rel = plan_doc_relative_path("run-123")
    assert rel == ".fluxion/plans/run-123.md"


@pytest.mark.parametrize("bad_id", ["../evil", "a/b", "", "..", "/tmp/evil"])
def test_plan_doc_relative_path_rejects_traversal(bad_id: str):
    with pytest.raises(ValueError):
        plan_doc_relative_path(bad_id)


def test_resolve_plan_doc_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        resolve_plan_doc_path(str(tmp_path), ".fluxion/plans/../../evil.md")


@pytest.mark.asyncio
async def test_initial_plan_file_is_created(tmp_path: Path):
    rel, byte_count = await create_initial_plan_doc(
        workspace_path=str(tmp_path),
        plan_run_id="run-123",
        original_request="Build the thing",
    )
    path = tmp_path / rel
    assert path.exists()
    assert byte_count == path.stat().st_size
    content = path.read_text()
    assert "Build the thing" in content
    assert "## Progress Checklist" in content


@pytest.mark.asyncio
async def test_update_plan_doc_atomically_updates_assigned_file(tmp_path: Path):
    rel, _ = await create_initial_plan_doc(
        workspace_path=str(tmp_path),
        plan_run_id="run-123",
        original_request="Build",
    )
    tool = UpdatePlanDocTool(workspace_path=str(tmp_path), relative_path=rel)
    result = await tool.execute(
        content="# Updated\n\n- note",
        summary="Added note",
        include_diff=True,
    )
    assert result.success
    assert (tmp_path / rel).read_text() == "# Updated\n\n- note"
    assert result.result_data["file_path"] == rel
    assert "--- a/.fluxion/plans/run-123.md" in result.result_data["diff"]


def test_missing_workspace_disables_update_plan_doc():
    registry = create_browser_agent_tool_registry(
        SimpleNamespace(parallel=None),
        {"web": False, "filesystem": False, "bash": False, "python": False},
        working_dir=None,
        collaboration_mode="plan",
        plan_doc_relative_path=".fluxion/plans/run.md",
    )
    assert "request_user_input" in registry.tool_names
    assert "update_plan_doc" not in registry.tool_names


def test_plan_mode_mutating_tools_still_block_source_mutation():
    assert {
        "write_file",
        "edit_file",
        "apply_patch",
        "exec_command",
        "bash",
        "python_execute",
    } <= PLAN_MODE_MUTATING_TOOLS
    assert "update_plan_doc" not in PLAN_MODE_MUTATING_TOOLS
