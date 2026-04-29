"""Tests for image input helpers."""

import base64

import pytest

from orchestrator.vision import build_multimodal_user_content, validate_image_attachments


def _data_url(payload: bytes = b"image") -> str:
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


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
