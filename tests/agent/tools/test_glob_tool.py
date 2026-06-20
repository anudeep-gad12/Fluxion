"""Tests for GlobTool."""

import pytest

from orchestrator.agent.tools.glob_tool import GlobTool


@pytest.fixture
def working_dir(tmp_path):
    (tmp_path / "a.py").write_text("python")
    (tmp_path / "b.py").write_text("python")
    (tmp_path / "readme.md").write_text("docs")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "c.py").write_text("python")
    (sub / "d.ts").write_text("typescript")
    return tmp_path


@pytest.fixture
def tool(working_dir):
    return GlobTool(working_dir=str(working_dir))


@pytest.mark.asyncio
async def test_glob_star_py(tool):
    result = await tool.execute(pattern="*.py")
    assert result.success is True
    assert "a.py" in result.result_data
    assert "b.py" in result.result_data
    assert "readme.md" not in result.result_data


@pytest.mark.asyncio
async def test_glob_recursive(tool):
    result = await tool.execute(pattern="**/*.py")
    assert result.success is True
    assert "a.py" in result.result_data
    assert "c.py" in result.result_data


@pytest.mark.asyncio
async def test_glob_no_matches(tool):
    result = await tool.execute(pattern="*.xyz")
    assert result.success is True
    assert result.metadata["count"] == 0


@pytest.mark.asyncio
async def test_glob_with_path(tool, working_dir):
    result = await tool.execute(pattern="*.py", path="src")
    assert result.success is True
    assert "c.py" in result.result_data


@pytest.mark.asyncio
async def test_basename_pattern_searches_recursively(tool):
    result = await tool.execute(pattern="c.py")
    assert result.success is True
    assert "src/c.py" in result.result_data
    assert result.metadata["recursive"] is True


@pytest.mark.asyncio
async def test_glob_matches_case_insensitively_by_default(tmp_path):
    health = tmp_path / "Health"
    health.mkdir()
    (health / "Sleep-Tracking.md").write_text("sleep data")

    result = await GlobTool(working_dir=str(tmp_path)).execute(pattern="**/*sleep*")

    assert result.success is True
    assert "Health/Sleep-Tracking.md" in result.result_data
    assert result.metadata["case_sensitive"] is False


@pytest.mark.asyncio
async def test_glob_can_force_case_sensitive_matching(tmp_path):
    health = tmp_path / "Health"
    health.mkdir()
    (health / "Sleep-Tracking.md").write_text("sleep data")

    result = await GlobTool(working_dir=str(tmp_path)).execute(
        pattern="**/*sleep*",
        case_sensitive=True,
    )

    assert result.success is True
    assert result.metadata["count"] == 0


@pytest.mark.asyncio
async def test_sibling_prefix_path_blocked(tmp_path):
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-evil"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret")

    result = await GlobTool(working_dir=str(workspace)).execute(
        pattern="*.txt",
        path=str(sibling),
    )

    assert result.success is False
    assert "outside" in result.error_message.lower()


@pytest.mark.asyncio
async def test_glob_respects_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored/\n*.log\n")
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "hidden.txt").write_text("hidden")
    (tmp_path / "debug.log").write_text("debug")
    (tmp_path / "keep.txt").write_text("keep")

    result = await GlobTool(working_dir=str(tmp_path)).execute(pattern="*.txt")

    assert result.success is True
    assert "keep.txt" in result.result_data
    assert "hidden.txt" not in result.result_data
    assert "debug.log" not in result.result_data


@pytest.mark.asyncio
async def test_glob_sorted_by_mtime(tool, working_dir):
    # Touch a.py to make it newer
    import time
    time.sleep(0.05)
    (working_dir / "a.py").write_text("updated")

    result = await tool.execute(pattern="*.py")
    assert result.success is True
    lines = result.result_data.strip().split("\n")
    # a.py should be first (most recent)
    assert lines[0] == "a.py"


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "glob"
    assert schema.is_idempotent is True
    assert schema.permission_level == "auto"
