"""Tests for BashTool."""

import pytest

from orchestrator.agent.tools.bash_tool import BashTool


@pytest.fixture
def tool(tmp_path):
    return BashTool(working_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_simple_command(tool):
    result = await tool.execute(command="echo hello")
    assert result.success is True
    assert result.result_data["stdout"].strip() == "hello"
    assert result.result_data["exit_code"] == 0


@pytest.mark.asyncio
async def test_exit_code_failure(tool):
    result = await tool.execute(command="exit 1")
    assert result.success is False
    assert result.metadata["exit_code"] == 1


@pytest.mark.asyncio
async def test_stderr_captured(tool):
    result = await tool.execute(command="echo error >&2")
    assert "error" in result.result_data["stderr"]


@pytest.mark.asyncio
async def test_timeout(tool):
    result = await tool.execute(command="sleep 10", timeout=1)
    assert result.success is False
    assert "timed out" in result.result_summary.lower()


@pytest.mark.asyncio
async def test_working_directory(tool, tmp_path):
    result = await tool.execute(command="pwd")
    assert result.success is True
    assert str(tmp_path) in result.result_data["stdout"]


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "bash"
    assert schema.is_idempotent is False
    assert schema.permission_level == "dangerous"


@pytest.mark.asyncio
async def test_health_check(tool):
    assert await tool.health_check() is True
