"""Context-window introspection tools for coding agents."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import ToolResult, ToolSchema


class GetContextRemainingTool:
    """Report the current context-window budget."""

    def __init__(self, payload_provider: Callable[[], dict[str, Any]]) -> None:
        self._payload_provider = payload_provider

    @property
    def name(self) -> str:
        return "get_context_remaining"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=(
                "Return the current coding-session context budget, including "
                "tokens left before compaction and active context tokens."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            is_idempotent=True,
            permission_level="auto",
        )

    async def execute(self) -> ToolResult:
        payload = self._payload_provider()
        tokens_left = payload.get("tokens_left")
        summary = (
            f"{tokens_left} tokens left before compaction"
            if tokens_left is not None
            else "context remaining is unknown"
        )
        return ToolResult(
            success=True,
            result_summary=summary,
            result_data=payload,
        )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class NewContextWindowTool:
    """Request compaction into a fresh context window."""

    def __init__(self, request_callback: Callable[[], dict[str, Any]]) -> None:
        self._request_callback = request_callback

    @property
    def name(self) -> str:
        return "new_context_window"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=(
                "Request that the next coding step starts a fresh compacted "
                "context window while preserving durable session state."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            is_idempotent=False,
            permission_level="auto",
        )

    async def execute(self) -> ToolResult:
        payload = self._request_callback()
        return ToolResult(
            success=True,
            result_summary="New context window requested",
            result_data=payload,
        )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None
