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


@pytest.mark.asyncio
async def test_rejects_extension_only_fake_image(tmp_path):
    image = tmp_path / "fake.png"
    image.write_text("not actually a png")

    result = await ViewImageTool(working_dir=str(tmp_path)).execute(paths=["fake.png"])

    assert result.success is False
    assert "unrecognized image data" in result.error_message


def test_schema_allows_twenty_images(tmp_path):
    tool = ViewImageTool(working_dir=str(tmp_path))

    assert tool.schema.parameters["properties"]["paths"]["maxItems"] == 20


@pytest.mark.asyncio
async def test_rejects_more_than_twenty_images(tmp_path):
    tool = ViewImageTool(working_dir=str(tmp_path))

    result = await tool.execute(paths=[f"{index}.png" for index in range(21)])

    assert result.success is False
    assert "at most 20 images" in result.error_message
