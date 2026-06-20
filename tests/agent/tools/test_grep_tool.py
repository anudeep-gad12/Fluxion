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
async def test_grep_global_max_results_and_top_files(tmp_path):
    (tmp_path / "a.txt").write_text("\n".join("needle" for _ in range(10)))
    (tmp_path / "b.txt").write_text("\n".join("needle" for _ in range(10)))
    tool = GrepTool(working_dir=str(tmp_path))

    result = await tool.execute(pattern="needle", context=0, max_results=5)

    assert result.success is True
    assert result.metadata["returned"] == 5
    assert result.metadata["truncated"] is True
    assert "top files:" in result.result_summary
    assert len(result.result_data.splitlines()) == 5


@pytest.mark.asyncio
async def test_grep_context_lines_not_counted_as_matches(tmp_path):
    (tmp_path / "a.txt").write_text("before\nneedle\nafter\n")
    tool = GrepTool(working_dir=str(tmp_path))

    result = await tool.execute(pattern="needle", context=1, max_results=5)

    assert result.success is True
    assert result.metadata["count"] == 1


@pytest.mark.asyncio
async def test_sibling_prefix_path_blocked(tmp_path):
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-evil"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("SECRET")

    result = await GrepTool(working_dir=str(workspace)).execute(
        pattern="SECRET",
        path=str(sibling),
    )

    assert result.success is False
    assert "outside" in result.error_message.lower()


@pytest.mark.asyncio
async def test_grep_respects_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored/\n*.log\n")
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "hidden.txt").write_text("needle")
    (tmp_path / "debug.log").write_text("needle")
    (tmp_path / "keep.txt").write_text("needle")

    result = await GrepTool(working_dir=str(tmp_path)).execute(
        pattern="needle",
        context=0,
        glob="*.txt",
    )

    assert result.success is True
    assert "keep.txt" in result.result_data
    assert "hidden.txt" not in result.result_data
    assert "debug.log" not in result.result_data


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
