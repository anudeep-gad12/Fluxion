"""Tests for image input helpers."""

import base64
import struct
import zlib

import pytest

from orchestrator.vision import (
    MAX_IMAGES_PER_MESSAGE,
    build_multimodal_user_content,
    validate_image_attachments,
    validate_image_attachments_for_provider,
)


def _data_url(payload: bytes = b"image", mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64," + base64.b64encode(payload).decode("ascii")


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def test_validate_image_attachment_accepts_png_data_url():
    attachments = validate_image_attachments(
        [{"name": "shot.png", "mime_type": "image/png", "data_url": _data_url()}]
    )

    assert attachments == [
        {"name": "shot.png", "mime_type": "image/png", "data_url": _data_url()}
    ]


def test_validate_image_attachment_rejects_non_image_data_url():
    with pytest.raises(ValueError, match="png, jpeg, or webp"):
        validate_image_attachments(
            [{"name": "x.txt", "mime_type": "text/plain", "data_url": "data:text/plain;base64,SGk="}]
        )


def test_build_multimodal_user_content_places_text_first():
    attachments = validate_image_attachments(
        [{"name": "shot.png", "mime_type": "image/png", "data_url": _data_url()}]
    )

    content = build_multimodal_user_content("what is this?", attachments)

    assert content == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": _data_url()}},
    ]


def test_validate_image_attachment_accepts_up_to_twenty_images():
    attachments = [
        {"name": f"shot-{index}.png", "mime_type": "image/png", "data_url": _data_url()}
        for index in range(MAX_IMAGES_PER_MESSAGE)
    ]

    assert len(validate_image_attachments(attachments)) == 20


def test_validate_image_attachment_rejects_more_than_twenty_images():
    attachments = [
        {"name": f"shot-{index}.png", "mime_type": "image/png", "data_url": _data_url()}
        for index in range(MAX_IMAGES_PER_MESSAGE + 1)
    ]

    with pytest.raises(ValueError, match="At most 20 images"):
        validate_image_attachments(attachments)


def test_grok_provider_rejects_webp_images():
    attachments = validate_image_attachments(
        [{"name": "shot.webp", "mime_type": "image/webp", "data_url": _data_url(b"webp", "image/webp")}]
    )

    with pytest.raises(ValueError, match="png or jpeg"):
        validate_image_attachments_for_provider(attachments, "grok")


def test_grok_provider_rejects_tiny_images():
    attachments = validate_image_attachments(
        [{"name": "tiny.png", "mime_type": "image/png", "data_url": _data_url(_png(10, 10))}]
    )

    with pytest.raises(ValueError, match="at least 512"):
        validate_image_attachments_for_provider(attachments, "grok")


def test_grok_provider_accepts_png_above_minimum_size():
    attachments = validate_image_attachments(
        [{"name": "ok.png", "mime_type": "image/png", "data_url": _data_url(_png(32, 32))}]
    )

    validate_image_attachments_for_provider(attachments, "grok")
