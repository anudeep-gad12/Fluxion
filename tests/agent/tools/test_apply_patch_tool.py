"""Tests for the Codex-style apply_patch tool."""

import pytest

from orchestrator.agent.tools.apply_patch_tool import ApplyPatchTool


@pytest.mark.asyncio
async def test_add_file(tmp_path):
    tool = ApplyPatchTool(str(tmp_path))
    result = await tool.execute(
        patch="""*** Begin Patch
*** Add File: src/hello.txt
+hello
+world
*** End Patch"""
    )
    assert result.success is True
    assert (tmp_path / "src/hello.txt").read_text() == "hello\nworld\n"
    assert "src/hello.txt" in result.result_data["changed_files"]
    assert "+hello" in result.result_data["diff"]


@pytest.mark.asyncio
async def test_update_file(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("def main():\n    return 'old'\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Update File: app.py
@@
 def main():
-    return 'old'
+    return 'new'
*** End Patch"""
    )

    assert result.success is True
    assert path.read_text() == "def main():\n    return 'new'\n"
    assert "-    return 'old'" in result.result_data["diff"]
    assert "+    return 'new'" in result.result_data["diff"]


@pytest.mark.asyncio
async def test_delete_file(tmp_path):
    path = tmp_path / "gone.txt"
    path.write_text("bye\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Delete File: gone.txt
*** End Patch"""
    )

    assert result.success is True
    assert not path.exists()
    assert "gone.txt" in result.result_data["changed_files"]


@pytest.mark.asyncio
async def test_move_and_update_file(tmp_path):
    path = tmp_path / "old.txt"
    path.write_text("name=old\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Update File: old.txt
*** Move to: new.txt
@@
-name=old
+name=new
*** End Patch"""
    )

    assert result.success is True
    assert not path.exists()
    assert (tmp_path / "new.txt").read_text() == "name=new\n"
    assert result.result_data["operations"] == ["move/update"]


@pytest.mark.asyncio
async def test_multiple_files(tmp_path):
    (tmp_path / "a.txt").write_text("a\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Update File: a.txt
@@
-a
+A
*** Add File: b.txt
+B
*** End Patch"""
    )

    assert result.success is True
    assert (tmp_path / "a.txt").read_text() == "A\n"
    assert (tmp_path / "b.txt").read_text() == "B\n"
    assert set(result.result_data["changed_files"]) == {"a.txt", "b.txt"}


@pytest.mark.asyncio
async def test_update_ignores_unified_diff_file_headers(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("def main():\n    return 'old'\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Update File: app.py
--- app.py
+++ app.py
@@ -1,2 +1,2 @@
 def main():
-    return 'old'
+    return 'new'
*** End Patch"""
    )

    assert result.success is True
    assert path.read_text() == "def main():\n    return 'new'\n"


@pytest.mark.asyncio
async def test_update_accepts_full_file_replacement_marker(tmp_path):
    path = tmp_path / "style.css"
    path.write_text("body {\n  color: red;\n}\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Update File: style.css
***
body {
  color: blue;
}

.plain-link {
  text-decoration: none;
}
*** End Patch"""
    )

    assert result.success is True
    assert path.read_text() == (
        "body {\n"
        "  color: blue;\n"
        "}\n"
        "\n"
        ".plain-link {\n"
        "  text-decoration: none;\n"
        "}\n"
    )


@pytest.mark.asyncio
async def test_rejects_malformed_patch(tmp_path):
    tool = ApplyPatchTool(str(tmp_path))
    result = await tool.execute(
        patch="*** Begin Patch\n*** Add File: a.txt\nmissing plus\n*** End Patch"
    )
    assert result.success is False
    assert "lines must start" in result.error_message


@pytest.mark.asyncio
async def test_rejects_path_escape(tmp_path):
    tool = ApplyPatchTool(str(tmp_path))
    result = await tool.execute(
        patch="""*** Begin Patch
*** Add File: ../escape.txt
+nope
*** End Patch"""
    )
    assert result.success is False
    assert "outside working directory" in result.error_message
    assert not (tmp_path.parent / "escape.txt").exists()


@pytest.mark.asyncio
async def test_no_partial_writes_when_one_hunk_fails(tmp_path):
    (tmp_path / "ok.txt").write_text("ok\n")
    (tmp_path / "bad.txt").write_text("actual\n")
    tool = ApplyPatchTool(str(tmp_path))

    result = await tool.execute(
        patch="""*** Begin Patch
*** Update File: ok.txt
@@
-ok
+changed
*** Update File: bad.txt
@@
-missing
+changed
*** End Patch"""
    )

    assert result.success is False
    assert (tmp_path / "ok.txt").read_text() == "ok\n"
    assert (tmp_path / "bad.txt").read_text() == "actual\n"
