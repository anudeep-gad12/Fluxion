"""Utilities for OpenAI-compatible image inputs."""

from __future__ import annotations

import base64
import re
from typing import Any


SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGES_PER_MESSAGE = 8
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
