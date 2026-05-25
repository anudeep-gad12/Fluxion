"""Plan Mode user-input request tool."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Optional

from .base import ToolResult, ToolSchema

UserInputCallback = Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]


class RequestUserInputTool:
    """Ask the browser user a small set of planning questions."""

    def __init__(self, callback: Optional[UserInputCallback] = None) -> None:
        self._callback = callback

    @property
    def name(self) -> str:
        return "request_user_input"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=(
                "Plan Mode only. Ask the user 1-3 concise multiple-choice planning "
                "questions when the answer materially changes the plan and cannot "
                "be discovered from repo inspection."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 3,
                        "description": "Questions to show in the browser HUD.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "header": {
                                    "type": "string",
                                    "description": "Short label, 12 characters or fewer.",
                                },
                                "question": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": 3,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"},
                                        },
                                        "required": ["label", "description"],
                                    },
                                },
                            },
                            "required": ["id", "header", "question", "options"],
                        },
                    }
                },
                "required": ["questions"],
            },
            is_idempotent=False,
            permission_level="auto",
        )

    async def execute(self, questions: list[dict[str, Any]], **_: Any) -> ToolResult:
        start = time.perf_counter()
        if not self._callback:
            return ToolResult(
                success=False,
                result_summary="request_user_input unavailable",
                error_message="No browser user-input callback is registered.",
                duration_ms=0,
            )

        if not questions:
            return ToolResult(
                success=False,
                result_summary="No questions supplied",
                error_message="request_user_input requires at least one question.",
                duration_ms=0,
            )

        answers = await self._callback(questions)
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ToolResult(
            success=True,
            result_summary=f"User answered {len(answers)} planning question(s)",
            result_data={"answers": answers},
            duration_ms=duration_ms,
        )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None
