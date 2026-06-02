"""Read-only tools for current-run durable artifacts."""

from __future__ import annotations

import time
from typing import Any

from orchestrator.agent.artifacts import AgentArtifactManager

from .base import ToolResult, ToolSchema


class ListRunArtifactsTool:
    """List durable artifacts saved for the current run."""

    def __init__(self, manager: AgentArtifactManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "list_run_artifacts"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=(
                "List durable artifacts saved for this run, such as terminal "
                "output and web extracts. Source files are not artifacts; use "
                "read_file for source files."
            ),
            parameters={"type": "object", "properties": {}},
            is_idempotent=True,
            permission_level="auto",
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        del kwargs
        start = time.perf_counter()
        try:
            artifacts = self._manager.list_artifacts()
            return ToolResult(
                success=True,
                result_summary=f"Found {len(artifacts)} run artifacts",
                result_data={"artifacts": artifacts},
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                result_summary=f"Artifact list failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class ReadArtifactTool:
    """Read a text artifact saved for the current run."""

    def __init__(self, manager: AgentArtifactManager) -> None:
        self._manager = manager

    @property
    def name(self) -> str:
        return "read_artifact"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=(
                "Read a text artifact from this run by artifact_path. Use this "
                "for saved terminal output or web extracts when the summary is "
                "not enough. Cannot read source files; use read_file for source."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "artifact_path": {
                        "type": "string",
                        "description": (
                            "Path from an artifact ref, e.g. "
                            ".fluxion/runs/<run_id>/tool-calls/<id>/output.txt"
                        ),
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-based line number to start from.",
                        "default": 1,
                        "minimum": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum lines to read, default 200, max 1000.",
                        "default": 200,
                        "maximum": 1000,
                    },
                },
                "required": ["artifact_path"],
            },
            is_idempotent=True,
            permission_level="auto",
        )

    async def execute(
        self,
        artifact_path: str,
        offset: int = 1,
        limit: int = 200,
        **kwargs: Any,
    ) -> ToolResult:
        del kwargs
        start = time.perf_counter()
        try:
            data = self._manager.read_text_artifact(
                artifact_path,
                offset=offset,
                limit=limit,
            )
            summary = (
                f"Read artifact {data['artifact_path']} "
                f"[lines {data['line_start']}-{data['line_end'] or data['line_start'] - 1}"
                f" of {data['total_lines']}]"
            )
            if data.get("next_offset"):
                summary += f" — next_offset={data['next_offset']}"
            return ToolResult(
                success=True,
                result_summary=summary,
                result_data=data,
                duration_ms=int((time.perf_counter() - start) * 1000),
                metadata={
                    "artifact_path": data["artifact_path"],
                    "next_offset": data.get("next_offset"),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                result_summary=f"Artifact read failed: {str(e)[:80]}",
                error_message=str(e),
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass
