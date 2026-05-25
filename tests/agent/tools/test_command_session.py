"""Tests for Codex-style command session tools."""

import pytest
import pytest_asyncio

from orchestrator.agent.tools.command_session import (
    CommandSessionManager,
    ExecCommandTool,
    WriteStdinTool,
)


@pytest_asyncio.fixture
async def tools(tmp_path):
    manager = CommandSessionManager(str(tmp_path))
    try:
        yield ExecCommandTool(manager), WriteStdinTool(manager), manager
    finally:
        await manager.cleanup()


@pytest.mark.asyncio
async def test_quick_command_completes_with_output(tools):
    exec_tool, _, _ = tools
    result = await exec_tool.execute(cmd="echo hello", yield_time_ms=1000)
    assert result.success is True
    assert result.result_data["status"] == "completed"
    assert result.result_data["exit_code"] == 0
    assert result.result_data["stdout"].strip() == "hello"


@pytest.mark.asyncio
async def test_long_command_returns_session_id(tools):
    exec_tool, _, _ = tools
    result = await exec_tool.execute(
        cmd=(
            "python3 -c 'import time; print(\"start\", flush=True); "
            "time.sleep(2); print(\"done\", flush=True)'"
        ),
        yield_time_ms=100,
    )
    assert result.success is True
    assert result.result_data["status"] == "running"
    assert result.result_data["session_id"]
    assert "start" in result.result_data["stdout"]


@pytest.mark.asyncio
async def test_write_stdin_polls_running_output(tools):
    exec_tool, stdin_tool, _ = tools
    result = await exec_tool.execute(
        cmd=(
            "python3 -c 'import time; print(\"start\", flush=True); "
            "time.sleep(.3); print(\"done\", flush=True)'"
        ),
        yield_time_ms=50,
    )
    session_id = result.result_data["session_id"]
    polled = await stdin_tool.execute(session_id=session_id, yield_time_ms=1000)
    assert polled.result_data["status"] == "completed"
    assert "done" in polled.result_data["stdout"]


@pytest.mark.asyncio
async def test_stdin_write_for_interactive_process(tools):
    exec_tool, stdin_tool, _ = tools
    result = await exec_tool.execute(
        cmd=(
            "python3 -c 'import sys; line=sys.stdin.readline(); "
            "print(\"got:\" + line.strip(), flush=True)'"
        ),
        yield_time_ms=50,
    )
    session_id = result.result_data["session_id"]
    completed = await stdin_tool.execute(
        session_id=session_id,
        chars="hello\n",
        yield_time_ms=1000,
    )
    assert completed.result_data["status"] == "completed"
    assert "got:hello" in completed.result_data["stdout"]


@pytest.mark.asyncio
async def test_max_output_truncation(tools):
    exec_tool, _, _ = tools
    result = await exec_tool.execute(
        cmd="python3 -c 'print(\"x\" * 2000)'",
        yield_time_ms=1000,
        max_output_tokens=100,
    )
    assert result.result_data["truncated"] is True
    assert "output truncated" in result.result_data["output"]


@pytest.mark.asyncio
async def test_cleanup_kills_running_process(tools):
    exec_tool, _, manager = tools
    result = await exec_tool.execute(cmd="sleep 20", yield_time_ms=50)
    assert result.result_data["status"] == "running"
    assert manager.get(result.result_data["session_id"]) is not None
    await manager.cleanup()
    assert manager.get(result.result_data["session_id"]) is None
