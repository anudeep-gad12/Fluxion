"""Tests for GrepTool."""

import pytest

from orchestrator.agent.tools.grep_tool import GrepTool


@pytest.fixture
def working_dir(tmp_path):
    (tmp_path / "app.py").write_text("import os\ndef main():\n    print('hello')\n")
    (tmp_path / "utils.py").write_text("import sys\ndef helper():\n    return 42\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "module.py").write_text("class Foo:\n    pass\n")
    # Binary file should be skipped
    (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02pattern\x03")
    return tmp_path


@pytest.fixture
def tool(working_dir):
    return GrepTool(working_dir=str(working_dir))


@pytest.mark.asyncio
async def test_grep_simple_pattern(tool):
    result = await tool.execute(pattern="import")
    assert result.success is True
    assert result.metadata["count"] >= 2
    assert "app.py" in result.result_data
    assert "utils.py" in result.result_data


@pytest.mark.asyncio
async def test_grep_regex(tool):
    result = await tool.execute(pattern="def \\w+\\(")
    assert result.success is True
    assert "main" in result.result_data
    assert "helper" in result.result_data


@pytest.mark.asyncio
async def test_grep_no_matches(tool):
    result = await tool.execute(pattern="zzz_no_match_zzz")
    assert result.success is True
    assert result.metadata["count"] == 0


@pytest.mark.asyncio
async def test_grep_in_specific_path(tool, working_dir):
    result = await tool.execute(pattern="class", path="sub")
    assert result.success is True
    assert "Foo" in result.result_data


@pytest.mark.asyncio
async def test_grep_glob_filter(tool):
    result = await tool.execute(pattern="import", glob="*.py")
    assert result.success is True
    assert "import" in result.result_data


@pytest.mark.asyncio
async def test_grep_skips_binary(tool):
    result = await tool.execute(pattern="pattern")
    assert result.success is True
    assert "data.bin" not in result.result_data


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "grep"
    assert schema.is_idempotent is True
    assert schema.permission_level == "auto"
