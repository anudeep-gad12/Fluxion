"""Plan Mode-only tool for updating the assigned durable plan document."""

from __future__ import annotations

import time
from typing import Any

from orchestrator.agent.plan_doc import (
    summarize_plan_doc_update,
    update_plan_doc_content,
)

from .base import ToolResult, ToolSchema


class UpdatePlanDocTool:
    """Atomically replace the assigned Plan Mode markdown scratchpad."""

    def __init__(self, *, workspace_path: str, relative_path: str) -> None:
        self._workspace_path = workspace_path
        self._relative_path = relative_path

    @property
    def name(self) -> str:
        return "update_plan_doc"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=(
                "Plan Mode only. Replace the assigned durable markdown plan "
                "document with updated research notes, decisions, open questions, "
                "draft plan, and checklist progress. This tool can only write the "
                "preassigned .fluxion/plans/<plan_run_id>.md file."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Full markdown content for the plan document.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Concise human-readable summary of the update.",
                    },
                    "include_diff": {
                        "type": "boolean",
                        "description": "Whether to include a unified diff in the result.",
                    },
                },
                "required": ["content"],
            },
            is_idempotent=False,
            permission_level="auto",
        )

    async def execute(
        self,
        content: str,
        summary: str | None = None,
        include_diff: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        start = time.perf_counter()
        try:
            byte_count, diff = await update_plan_doc_content(
                workspace_path=self._workspace_path,
                relative_path=self._relative_path,
                content=content,
                include_diff=include_diff,
            )
            clean_summary = (summary or "").strip() or summarize_plan_doc_update(content)
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                success=True,
                result_summary=(
                    f"{clean_summary} ({self._relative_path}, {byte_count} bytes)"
                ),
                result_data={
                    "file_path": self._relative_path,
                    "bytes": byte_count,
                    "summary": clean_summary,
                    "diff": diff,
                },
                duration_ms=duration_ms,
                metadata={
                    "file_path": self._relative_path,
                    "bytes": byte_count,
                    "diff": diff,
                },
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolResult(
                success=False,
                result_summary=f"Failed to update plan doc: {exc}",
                error_message=str(exc),
                duration_ms=duration_ms,
            )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None
