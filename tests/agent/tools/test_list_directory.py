"""Tests for ListDirectoryTool."""

import pytest

from orchestrator.agent.tools.list_directory import ListDirectoryTool


@pytest.fixture
def working_dir(tmp_path):
    (tmp_path / "file.txt").write_text("content")
    (tmp_path / "script.py").write_text("print('hello')")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")
    # Create .git dir (should be ignored in recursive mode)
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config")
    return tmp_path


@pytest.fixture
def tool(working_dir):
    return ListDirectoryTool(working_dir=str(working_dir))


@pytest.mark.asyncio
async def test_list_flat(tool):
    result = await tool.execute()
    assert result.success is True
    assert "file.txt" in result.result_data
    assert "script.py" in result.result_data
    assert "subdir" in result.result_data


@pytest.mark.asyncio
async def test_list_recursive(tool):
    result = await tool.execute(recursive=True)
    assert result.success is True
    assert "nested.txt" in result.result_data


@pytest.mark.asyncio
async def test_list_ignores_git(tool):
    result = await tool.execute(recursive=True)
    assert result.success is True
    assert ".git" not in result.result_data


@pytest.mark.asyncio
async def test_list_subdirectory(tool):
    result = await tool.execute(path="subdir")
    assert result.success is True
    assert "nested.txt" in result.result_data


@pytest.mark.asyncio
async def test_list_nonexistent(tool):
    result = await tool.execute(path="nonexistent")
    assert result.success is False


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "list_directory"
    assert schema.is_idempotent is True
    assert schema.permission_level == "auto"
