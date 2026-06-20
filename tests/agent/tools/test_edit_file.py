"""Tests for EditFileTool."""

from pathlib import Path

import pytest

from orchestrator.agent.tools.edit_file import EditFileTool


@pytest.fixture
def working_dir(tmp_path: Path):
    (tmp_path / "example.py").write_text(
        "def hello():\n    print('hello')\n\ndef world():\n    print('world')\n"
    )
    return tmp_path


@pytest.fixture
def tool(working_dir: Path):
    return EditFileTool(working_dir=str(working_dir))


@pytest.mark.asyncio
async def test_edit_exact_replacement(tool, working_dir: Path):
    result = await tool.execute(
        file_path="example.py",
        old_string="    print('hello')",
        new_string="    print('hi there')",
    )
    assert result.success is True
    assert "Edited" in result.result_summary
    assert result.metadata["matched_by"] == "exact"

    content = (working_dir / "example.py").read_text()
    assert "print('hi there')" in content
    assert "print('hello')" not in content


@pytest.mark.asyncio
async def test_edit_normalizes_line_endings(tmp_path: Path):
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"alpha\r\nbeta\r\n")
    tool = EditFileTool(working_dir=str(tmp_path))

    result = await tool.execute(
        file_path="crlf.txt",
        old_string="alpha\nbeta\n",
        new_string="alpha\ngamma\n",
    )

    assert result.success is True
    assert b"alpha\r\ngamma\r\n" == path.read_bytes()


@pytest.mark.asyncio
async def test_edit_indentation_flexible_match(tool, working_dir: Path):
    result = await tool.execute(
        file_path="example.py",
        old_string="        print('hello')",
        new_string="        print('hi there')",
    )

    assert result.success is True
    assert result.metadata["matched_by"] in {"line_trimmed", "indentation_flexible"}
    assert "print('hi there')" in (working_dir / "example.py").read_text()


@pytest.mark.asyncio
async def test_edit_whitespace_normalized_multiline_block(tmp_path: Path):
    path = tmp_path / "sample.ts"
    path.write_text("const   total = 1 + 2;\nconst  label   =   total;\n")
    tool = EditFileTool(working_dir=str(tmp_path))

    result = await tool.execute(
        file_path="sample.ts",
        old_string="const total = 1 + 2;\nconst label = total;",
        new_string="const total=1+2;\nconst label = String(total);",
    )

    assert result.success is True
    assert result.metadata["matched_by"] == "whitespace_normalized"
    assert "String(total)" in path.read_text()


@pytest.mark.asyncio
async def test_edit_block_anchor_fallback_after_formatting_drift(tmp_path: Path):
    path = tmp_path / "sample.ts"
    path.write_text("const alpha = 1;\n\nconst beta = 2;\nreturn alpha + beta;\n")
    tool = EditFileTool(working_dir=str(tmp_path))

    result = await tool.execute(
        file_path="sample.ts",
        old_string="const alpha = 1;\nconst beta = 2;\nreturn alpha + beta;",
        new_string="const alpha = 1;\nconst beta = 3;\nreturn alpha + beta;",
    )

    assert result.success is True
    assert result.metadata["matched_by"] == "block_anchor"
    assert "const beta = 3;" in path.read_text()


@pytest.mark.asyncio
async def test_edit_string_not_found(tool):
    result = await tool.execute(
        file_path="example.py",
        old_string="this does not exist",
        new_string="replacement",
    )
    assert result.success is False
    assert result.metadata["match_failure_type"] == "not_found"
    assert "not found" in result.error_message.lower()


@pytest.mark.asyncio
async def test_edit_string_not_found_returns_candidate_hint(tool):
    result = await tool.execute(
        file_path="example.py",
        old_string="def hello():\n    print('helo')",
        new_string="def hello():\n    print('hi')",
    )
    assert result.success is False
    assert "Candidate snippets for recovery" in result.error_message
    assert result.metadata["candidate_snippets"]
    assert result.metadata["attempted_matchers"]


@pytest.mark.asyncio
async def test_edit_ambiguous_fallback_match_fails(tmp_path: Path):
    path = tmp_path / "sample.py"
    path.write_text(
        "def one():\n    print('same')\n\ndef two():\n        print('same')\n"
    )
    tool = EditFileTool(working_dir=str(tmp_path))

    result = await tool.execute(
        file_path="sample.py",
        old_string="print('same')",
        new_string="print('updated')",
    )

    assert result.success is False
    assert result.metadata["match_failure_type"] == "ambiguous"
    assert "matched 2 locations" in result.error_message


@pytest.mark.asyncio
async def test_edit_identical_old_and_new_is_noop(tool):
    result = await tool.execute(
        file_path="example.py",
        old_string="def hello():",
        new_string="def hello():",
    )

    assert result.success is False
    assert result.metadata["match_failure_type"] == "no_op"
    assert "no-op" in result.error_message.lower()


@pytest.mark.asyncio
async def test_edit_file_not_found(tool):
    result = await tool.execute(
        file_path="missing.py",
        old_string="x",
        new_string="y",
    )
    assert result.success is False


@pytest.mark.asyncio
async def test_edit_generates_diff(tool):
    result = await tool.execute(
        file_path="example.py",
        old_string="def hello():",
        new_string="def greet():",
    )
    assert result.success is True
    diff = result.result_data["diff"]
    assert "-def hello():" in diff or "def greet():" in diff


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
async def test_sibling_prefix_path_blocked(tmp_path: Path):
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-evil"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret")

    result = await EditFileTool(working_dir=str(workspace)).execute(
        file_path=str(sibling / "secret.txt"),
        old_string="secret",
        new_string="changed",
    )

    assert result.success is False
    assert "outside" in result.error_message.lower()
    assert (sibling / "secret.txt").read_text() == "secret"


@pytest.mark.asyncio
async def test_schema_properties(tool):
    schema = tool.schema
    assert schema.name == "edit_file"
    assert schema.is_idempotent is False
    assert schema.permission_level == "confirm"
    assert "file_path" in schema.parameters["required"]
    assert "old_string" in schema.parameters["required"]
    assert "new_string" in schema.parameters["required"]
