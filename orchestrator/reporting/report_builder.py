"""Report builder - transform model calls into human-readable reports."""

from typing import Any, Optional


class ReportBuilder:
    """Builds human-readable reports from run data."""

    def __init__(self, format: str = "markdown") -> None:
        self._format = format
        self._sections: list[dict[str, Any]] = []

    def add_summary(self, run_id: str, status: str) -> None:
        """Add a summary section."""
        self._sections.append({
            "type": "summary",
            "run_id": run_id,
            "status": status,
        })

    def build(self) -> str:
        """Build the final report."""
        lines = ["# Chat Report", ""]
        
        for section in self._sections:
            if section["type"] == "summary":
                lines.append(f"**Run ID**: {section['run_id']}")
                lines.append(f"**Status**: {section['status']}")
                lines.append("")
        
        return "\n".join(lines)

    def build_timeline(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build a structured timeline from events.

        Args:
            events: List of events/model calls from a run

        Returns:
            List of timeline entries for UI rendering
        """
        timeline = []
        for event in events:
            meta = event.get("metadata", {})
            entry = {
                "seq": event.get("seq", 0),
                "ts": event.get("created_at", ""),
                "type": event.get("step_type", "model_call"),
                "title": "Model Call",
                "summary": f"{meta.get('input_tokens', 0)} in / {meta.get('output_tokens', 0)} out tokens",
                "timing_ms": meta.get("timing_ms", 0),
            }
            timeline.append(entry)
        return timeline
