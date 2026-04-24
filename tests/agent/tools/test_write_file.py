"""Tests for WriteFileTool."""

import pytest

from orchestrator.agent.tools.write_file import WriteFileTool


@pytest.fixture
def tool(tmp_path):
    return WriteFileTool(working_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_write_new_file(tool, tmp_path):
    result = await tool.execute(file_path="new.txt", content="hello world")
    assert result.success is True
    assert "Created" in result.result_summary
    assert "--- a/new.txt" in result.result_data
    assert "+++ b/new.txt" in result.result_data
    assert "+hello world" in result.result_data
    assert (tmp_path / "new.txt").read_text() == "hello world"


@pytest.mark.asyncio
async def test_overwrite_existing_file(tool, tmp_path):
    (tmp_path / "existing.txt").write_text("old content")
    result = await tool.execute(
        file_path="existing.txt",
        content="new content",
        allow_overwrite=True,
    )
    assert result.success is True
    assert "Overwrote" in result.result_summary
    assert "-old content" in result.result_data
    assert "+new content" in result.result_data
    assert (tmp_path / "existing.txt").read_text() == "new content"


@pytest.mark.asyncio
async def test_refuses_existing_file_without_explicit_overwrite(tool, tmp_path):
    (tmp_path / "existing.txt").write_text("old content")
    result = await tool.execute(file_path="existing.txt", content="new content")
    assert result.success is False
    assert "Refused to overwrite" in result.result_summary
    assert "Use edit_file" in result.error_message
    assert (tmp_path / "existing.txt").read_text() == "old content"


@pytest.mark.asyncio
async def test_creates_parent_dirs(tool, tmp_path):
    result = await tool.execute(file_path="a/b/c/deep.txt", content="deep")
    assert result.success is True
    assert (tmp_path / "a" / "b" / "c" / "deep.txt").read_text() == "deep"


@pytest.mark.asyncio
async def test_reports_byte_count(tool, tmp_path):
    result = await tool.execute(file_path="sized.txt", content="abc")
    assert result.success is True
    assert result.metadata["bytes"] == 3


@pytest.mark.asyncio
async def test_path_traversal_blocked(tool):
    result = await tool.execute(file_path="../../../tmp/evil.txt", content="hacked")
    assert result.success is False
    assert "outside" in result.error_message.lower()


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "write_file"
    assert schema.is_idempotent is False
    assert schema.permission_level == "confirm"
