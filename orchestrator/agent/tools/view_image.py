"""Attach workspace images to the next vision model call."""

from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any

from orchestrator.vision import MAX_IMAGE_BYTES

from .base import ToolResult, ToolSchema
from .path_utils import display_workspace_path, resolve_workspace_path


class ViewImageTool:
    """Read local image files from the workspace for multimodal model input."""

    SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
    MAX_IMAGES = 8

    def __init__(self, working_dir: str = ".") -> None:
        self._working_dir = Path(working_dir).resolve()

    @property
    def name(self) -> str:
        return "view_image"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="view_image",
            description=(
                "Attach one or more png/jpg/webp workspace images so you can inspect them visually. "
                "Use this for screenshots, charts, forms, diagrams, medical/lab-result images, and UI captures. "
                "Pass relative paths from the current workspace. Do not use OCR first when visual details matter."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": self.MAX_IMAGES,
                        "description": "Image file paths relative to the workspace.",
                    }
                },
                "required": ["paths"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    def _resolve_path(self, file_path: str) -> Path:
        return resolve_workspace_path(self._working_dir, file_path)

    def _display_path(self, path: Path) -> str:
        return display_workspace_path(self._working_dir, path)

    async def execute(self, paths: list[str], **kwargs: Any) -> ToolResult:
        start_time = time.perf_counter()
        if not paths:
            return ToolResult(
                success=False,
                result_summary="No image paths provided",
                error_message="view_image requires at least one path",
                duration_ms=0,
            )
        if len(paths) > self.MAX_IMAGES:
            return ToolResult(
                success=False,
                result_summary=f"Too many images: {len(paths)}",
                error_message=f"view_image accepts at most {self.MAX_IMAGES} images per call",
                duration_ms=0,
            )

        images: list[dict[str, str]] = []
        try:
            for raw_path in paths:
                path = self._resolve_path(raw_path)
                if not path.exists() or not path.is_file():
                    raise ValueError(f"Image not found: {raw_path}")
                if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                    raise ValueError(f"Unsupported image type: {raw_path}")
                size = path.stat().st_size
                if size > MAX_IMAGE_BYTES:
                    raise ValueError(f"Image exceeds 20MB: {raw_path}")

                mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
                if mime_type == "image/jpg":
                    mime_type = "image/jpeg"
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                images.append(
                    {
                        "name": self._display_path(path),
                        "mime_type": mime_type,
                        "data_url": f"data:{mime_type};base64,{data}",
                    }
                )

            names = ", ".join(image["name"] for image in images)
            return ToolResult(
                success=True,
                result_summary=f"Attached {len(images)} image(s): {names}",
                result_data={"images": images},
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                metadata={"image_count": len(images), "paths": [image["name"] for image in images]},
            )
        except ValueError as exc:
            return ToolResult(
                success=False,
                result_summary=f"Image attach failed: {str(exc)[:80]}",
                error_message=str(exc),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    async def health_check(self) -> bool:
        return self._working_dir.is_dir()

    async def close(self) -> None:
        pass
