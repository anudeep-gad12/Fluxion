"""Tests for EditFileTool."""

import pytest

from orchestrator.agent.tools.edit_file import EditFileTool


@pytest.fixture
def working_dir(tmp_path):
    (tmp_path / "example.py").write_text(
        "def hello():\n    print('hello')\n\ndef world():\n    print('world')\n"
    )
    return tmp_path


@pytest.fixture
def tool(working_dir):
    return EditFileTool(working_dir=str(working_dir))


@pytest.mark.asyncio
async def test_edit_exact_replacement(tool, working_dir):
    result = await tool.execute(
        file_path="example.py",
        old_string="    print('hello')",
        new_string="    print('hi there')",
    )
    assert result.success is True
    assert "Edited" in result.result_summary

    content = (working_dir / "example.py").read_text()
    assert "print('hi there')" in content
    assert "print('hello')" not in content


@pytest.mark.asyncio
async def test_edit_string_not_found(tool):
    result = await tool.execute(
        file_path="example.py",
        old_string="this does not exist",
        new_string="replacement",
    )
    assert result.success is False
    assert "not found" in result.error_message.lower()


@pytest.mark.asyncio
async def test_edit_multiple_occurrences(tool, working_dir):
    # Both functions have "print(" — should fail
    result = await tool.execute(
        file_path="example.py",
        old_string="print(",
        new_string="log(",
    )
    assert result.success is False
    assert "2 times" in result.error_message


@pytest.mark.asyncio
async def test_edit_file_not_found(tool):
    result = await tool.execute(
        file_path="missing.py",
        old_string="x",
        new_string="y",
    )
    assert result.success is False


@pytest.mark.asyncio
async def test_edit_generates_diff(tool, working_dir):
    result = await tool.execute(
        file_path="example.py",
        old_string="def hello():",
        new_string="def greet():",
    )
    assert result.success is True
    # Diff should contain - and + lines
    assert "-def hello():" in result.result_data or "def greet():" in result.result_data


@pytest.mark.asyncio
async def test_path_traversal_blocked(tool):
    result = await tool.execute(
        file_path="../../etc/passwd",
        old_string="root",
        new_string="hacked",
    )
    assert result.success is False
    assert "outside" in result.error_message.lower()


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "edit_file"
    assert schema.is_idempotent is False
    assert schema.permission_level == "confirm"
    assert "file_path" in schema.parameters["required"]
    assert "old_string" in schema.parameters["required"]
    assert "new_string" in schema.parameters["required"]
