"""Tests for current-run artifact storage."""

from pathlib import Path

import pytest

from orchestrator.agent.artifacts import AgentArtifactManager
from orchestrator.agent.tools.run_artifacts import ListRunArtifactsTool, ReadArtifactTool


def test_artifact_manager_writes_inside_workspace(tmp_path: Path):
    """Artifacts are saved under .fluxion/runs/<run_id> and can be paged."""
    manager = AgentArtifactManager(str(tmp_path), "run-1")

    artifact = manager.write_text("tool-calls/tc-1/output.txt", "one\ntwo\nthree")

    assert artifact.artifact_path == ".fluxion/runs/run-1/tool-calls/tc-1/output.txt"
    assert (tmp_path / artifact.artifact_path).is_file()

    page = manager.read_text_artifact(artifact.artifact_path, offset=2, limit=1)
    assert page["line_start"] == 2
    assert page["line_end"] == 2
    assert page["next_offset"] == 3
    assert "two" in page["content"]


def test_artifact_manager_rejects_path_traversal(tmp_path: Path):
    """Artifact writes and reads cannot escape the current run directory."""
    manager = AgentArtifactManager(str(tmp_path), "run-1")

    with pytest.raises(ValueError, match="escapes run directory"):
        manager.write_text("../escape.txt", "nope")

    with pytest.raises(ValueError, match="outside this run"):
        manager.read_text_artifact("../escape.txt")


@pytest.mark.asyncio
async def test_run_artifact_tools_list_and_read(tmp_path: Path):
    """Read-only artifact tools expose current-run command/web artifacts."""
    manager = AgentArtifactManager(str(tmp_path), "run-1")
    artifact = manager.write_text("tool-calls/tc-1/stdout.txt", "hello\nworld")

    list_result = await ListRunArtifactsTool(manager).execute()
    assert list_result.success
    assert list_result.result_data["artifacts"][0]["artifact_path"] == artifact.artifact_path

    read_result = await ReadArtifactTool(manager).execute(artifact.artifact_path, limit=1)
    assert read_result.success
    assert read_result.result_data["next_offset"] == 2
    assert "hello" in read_result.result_data["content"]
