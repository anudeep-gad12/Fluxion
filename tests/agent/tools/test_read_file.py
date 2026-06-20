"""Tests for ReadFileTool."""

import pytest

from orchestrator.agent.tools.read_file import ReadFileTool


@pytest.fixture
def working_dir(tmp_path):
    """Create a working directory with test files."""
    # Simple text file
    (tmp_path / "hello.txt").write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")

    # Python file
    (tmp_path / "script.py").write_text("# comment\nprint('hello')\n")

    # Binary file
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03")

    # Subdirectory
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content\n")

    return tmp_path


@pytest.fixture
def tool(working_dir):
    return ReadFileTool(working_dir=str(working_dir))


@pytest.mark.asyncio
async def test_read_simple_file(tool, working_dir):
    result = await tool.execute(file_path="hello.txt")
    assert result.success is True
    assert "line 1" in result.result_data
    assert "line 5" in result.result_data
    assert result.metadata["total_lines"] == 5


@pytest.mark.asyncio
async def test_read_with_offset_and_limit(tool, working_dir):
    result = await tool.execute(file_path="hello.txt", offset=2, limit=2)
    assert result.success is True
    assert "line 2" in result.result_data
    assert "line 3" in result.result_data
    assert "line 1" not in result.result_data
    assert "line 4" not in result.result_data


@pytest.mark.asyncio
async def test_read_without_offset_is_stable_after_partial_read(tool):
    first = await tool.execute(file_path="hello.txt", limit=2)
    second = await tool.execute(file_path="hello.txt", limit=2)

    assert first.success is True
    assert "next_offset=3" in first.result_summary
    assert first.metadata["next_offset"] == 3
    assert second.success is True
    assert "line 1" in second.result_data
    assert "line 2" in second.result_data
    assert "line 3" not in second.result_data
    assert second.metadata["line_start"] == 1
    assert second.metadata["line_end"] == 2


@pytest.mark.asyncio
async def test_read_explicit_next_offset_continues(tool):
    first = await tool.execute(file_path="hello.txt", limit=2)
    result = await tool.execute(file_path="hello.txt", offset=first.metadata["next_offset"], limit=2)

    assert result.success is True
    assert "line 3" in result.result_data
    assert "line 4" in result.result_data
    assert "line 1" not in result.result_data
    assert result.metadata["line_start"] == 3


@pytest.mark.asyncio
async def test_read_explicit_offset_one_rereads_beginning(tool):
    await tool.execute(file_path="hello.txt", limit=2)
    result = await tool.execute(file_path="hello.txt", offset=1, limit=2)

    assert result.success is True
    assert "line 1" in result.result_data
    assert "line 3" not in result.result_data
    assert result.metadata["line_start"] == 1


@pytest.mark.asyncio
async def test_read_explicit_offset_past_end_reports_eof(tool):
    result = await tool.execute(file_path="hello.txt", offset=10, limit=4)

    assert result.success is True
    assert result.result_data == ""
    assert "already at end" in result.result_summary


@pytest.mark.asyncio
async def test_read_file_not_found(tool):
    result = await tool.execute(file_path="nonexistent.txt")
    assert result.success is False
    assert "not found" in result.result_summary.lower() or "not exist" in result.error_message.lower()


@pytest.mark.asyncio
async def test_read_binary_file_rejected(tool, working_dir):
    result = await tool.execute(file_path="binary.bin")
    assert result.success is False
    assert "binary" in result.result_summary.lower() or "binary" in result.error_message.lower()


@pytest.mark.asyncio
async def test_read_nested_file(tool, working_dir):
    result = await tool.execute(file_path="sub/nested.txt")
    assert result.success is True
    assert "nested content" in result.result_data


@pytest.mark.asyncio
async def test_read_absolute_path(tool, working_dir):
    abs_path = str(working_dir / "hello.txt")
    result = await tool.execute(file_path=abs_path)
    assert result.success is True


@pytest.mark.asyncio
async def test_path_traversal_blocked(tool, working_dir):
    result = await tool.execute(file_path="../../../etc/passwd")
    assert result.success is False
    assert "outside" in result.error_message.lower()


@pytest.mark.asyncio
async def test_sibling_prefix_path_blocked(tmp_path):
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-evil"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret")

    result = await ReadFileTool(working_dir=str(workspace)).execute(
        file_path=str(sibling / "secret.txt")
    )

    assert result.success is False
    assert "outside" in result.error_message.lower()


@pytest.mark.asyncio
async def test_long_line_uses_explicit_head_tail_marker(tmp_path):
    (tmp_path / "long.txt").write_text("a" * 1500 + "\n")
    result = await ReadFileTool(working_dir=str(tmp_path)).execute(file_path="long.txt")

    assert result.success is True
    assert "[line truncated: 1500 chars, showing head/tail]" in result.result_data
    assert result.metadata["truncated_lines"][0]["line"] == 1


@pytest.mark.asyncio
async def test_read_directory_rejected(tool, working_dir):
    result = await tool.execute(file_path="sub")
    assert result.success is False
    assert "not a file" in result.error_message.lower()


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "read_file"
    assert schema.is_idempotent is True
    assert schema.permission_level == "auto"
    assert "file_path" in schema.parameters["required"]


@pytest.mark.asyncio
async def test_health_check(tool):
    assert await tool.health_check() is True
