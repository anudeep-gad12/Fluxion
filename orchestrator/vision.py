"""Utilities for OpenAI-compatible image inputs."""

from __future__ import annotations

import base64
import re
import struct
from typing import Any


SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGES_PER_MESSAGE = 20
DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\s]+)$")


def validate_image_attachment(attachment: dict[str, Any]) -> dict[str, str]:
    """Validate a client-supplied image attachment."""
    name = str(attachment.get("name") or "image")
    mime_type = str(attachment.get("mime_type") or attachment.get("mimeType") or "")
    data_url = str(attachment.get("data_url") or attachment.get("dataUrl") or "")

    match = DATA_URL_RE.match(data_url)
    if not match:
        raise ValueError("Image attachment must be a png, jpeg, or webp data URL")

    data_mime = match.group(1)
    if mime_type and mime_type != data_mime:
        raise ValueError("Image MIME type does not match data URL")
    if data_mime not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError("Unsupported image MIME type")

    try:
        decoded = base64.b64decode(match.group(2), validate=True)
    except Exception as exc:
        raise ValueError("Image attachment is not valid base64") from exc

    if len(decoded) > MAX_IMAGE_BYTES:
        raise ValueError("Image attachment exceeds 20MB")

    return {
        "name": name[:120],
        "mime_type": data_mime,
        "data_url": f"data:{data_mime};base64,{match.group(2).replace(chr(10), '').replace(chr(13), '')}",
    }


def validate_image_attachments(attachments: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Validate all image attachments for a single message."""
    if not attachments:
        return []
    if len(attachments) > MAX_IMAGES_PER_MESSAGE:
        raise ValueError(f"At most {MAX_IMAGES_PER_MESSAGE} images can be attached")
    return [validate_image_attachment(attachment) for attachment in attachments]


def _decode_attachment_bytes(attachment: dict[str, str]) -> bytes:
    match = DATA_URL_RE.match(attachment["data_url"])
    if not match:
        raise ValueError("Image attachment must be a png, jpeg, or webp data URL")
    return base64.b64decode(match.group(2), validate=True)


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return struct.unpack(">II", data[16:24])


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return None
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(data):
            return None
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if segment_length < 7:
                return None
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return width, height
        index += segment_length
    return None


def _image_dimensions(attachment: dict[str, str]) -> tuple[int, int] | None:
    data = _decode_attachment_bytes(attachment)
    mime_type = attachment["mime_type"]
    if mime_type == "image/png":
        return _png_dimensions(data)
    if mime_type == "image/jpeg":
        return _jpeg_dimensions(data)
    return None


def validate_image_attachments_for_provider(
    attachments: list[dict[str, str]],
    provider_name: str | None,
) -> None:
    """Validate provider-specific image constraints after generic validation."""
    provider = (provider_name or "").lower()
    if provider not in {"grok", "xai"}:
        return
    for attachment in attachments:
        if attachment["mime_type"] == "image/webp":
            raise ValueError("Grok image inputs support png or jpeg, not webp")
        dimensions = _image_dimensions(attachment)
        if dimensions is None:
            continue
        width, height = dimensions
        if width * height < 512:
            raise ValueError("Grok image inputs require at least 512 total pixels")


def build_multimodal_user_content(
    text: str,
    attachments: list[dict[str, str]] | None,
) -> str | list[dict[str, Any]]:
    """Build OpenAI-compatible user content from text plus image attachments."""
    if not attachments:
        return text

    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for attachment in attachments:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": attachment["data_url"],
                },
            }
        )
    return content
