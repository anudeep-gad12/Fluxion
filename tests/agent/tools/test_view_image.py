"""Tests for ViewImageTool."""

import pytest

from orchestrator.agent.tools.view_image import ViewImageTool


@pytest.mark.asyncio
async def test_sibling_prefix_path_blocked(tmp_path):
    workspace = tmp_path / "work"
    sibling = tmp_path / "work-evil"
    workspace.mkdir()
    sibling.mkdir()
    (sibling / "image.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    )

    result = await ViewImageTool(working_dir=str(workspace)).execute(
        paths=[str(sibling / "image.png")]
    )

    assert result.success is False
    assert "outside" in result.error_message.lower()
