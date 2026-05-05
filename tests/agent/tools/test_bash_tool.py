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
    assert result.result_data["timed_out"] is True


@pytest.mark.asyncio
async def test_timeout_captures_partial_output(tool):
    result = await tool.execute(
        command=(
            "python3 -c \"import sys,time; "
            "print('server starting', flush=True); "
            "print('warming stderr', file=sys.stderr, flush=True); "
            "time.sleep(10)\""
        ),
        timeout=1,
    )
    assert result.success is False
    assert result.result_data["timed_out"] is True
    assert "server starting" in result.result_data["stdout"]
    assert "warming stderr" in result.result_data["stderr"]
    assert "partial output captured" in result.result_summary


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
    assert schema.parameters["properties"]["timeout"]["default"] == 300
    assert "one-off Python or Node scripts" in schema.description
    assert "curl requests" in schema.description


@pytest.mark.asyncio
async def test_health_check(tool):
    assert await tool.health_check() is True
