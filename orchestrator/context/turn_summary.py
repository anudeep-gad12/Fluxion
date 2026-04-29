"""Turn summary generation for compact cross-turn context."""

from dataclasses import dataclass, field
from typing import Any

from orchestrator.utils.tokens import TokenCounter


@dataclass
class TurnSummary:
    """Compact summary of a single turn for cross-turn context injection.

    Target: ~50-150 tokens per summary (vs ~500-3000 for raw final_answer).
    """

    run_id: str
    mode: str  # "chat" | "agent"
    query_brief: str  # first ~120 chars of user query
    answer_brief: str  # first ~200-300 chars of final answer
    tools_used: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    key_findings: str = ""
    token_cost: int = 0  # tokens this summary occupies

    def to_context_string(self) -> str:
        """Compact string for injection into context."""
        parts = [f"Q: {self.query_brief}"]
        if self.tools_used:
            parts.append(f"Tools: {', '.join(self.tools_used)}")
        if self.files_touched:
            parts.append(f"Files: {', '.join(self.files_touched[:5])}")
        if self.key_findings:
            parts.append(f"Findings: {self.key_findings}")
        parts.append(f"A: {self.answer_brief}")
        return " | ".join(parts)


class TurnSummarizer:
    """Generates compact turn summaries at run completion."""

    def __init__(self, token_counter: TokenCounter) -> None:
        self._counter = token_counter

    def summarize_agent_run(
        self,
        run: dict[str, Any],
        tool_calls: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
    ) -> TurnSummary:
        """Summarize an agent run into a compact context string.

        Args:
            run: Dict with user_message, final_answer, thinking_summary, mode.
            tool_calls: List of agent_tool_calls rows.
            artifacts: List of run_artifacts rows.

        Returns:
            TurnSummary with token cost.
        """
        user_message = run.get("user_message", "")
        final_answer = run.get("final_answer", "")
        _ = run.get("thinking_summary", "")

        # Deduplicated tool names
        tools = list(dict.fromkeys(
            tc.get("tool_name", "") for tc in tool_calls if tc.get("tool_name")
        ))

        # File paths from artifacts
        files = list(dict.fromkeys(
            a.get("file_path", "") for a in artifacts if a.get("file_path")
        ))

        # Extract key findings from tool results (more useful than raw thinking)
        key_facts: list[str] = []
        for tc in tool_calls:
            tool_name = tc.get("tool_name", "")
            result_summary = tc.get("result_summary", "")
            if tool_name in ("web_search", "web_extract") and result_summary:
                key_facts.append(result_summary[:100])
            elif tool_name in ("read_file", "grep") and result_summary:
                key_facts.append(result_summary[:80])
        if key_facts:
            key_findings = "; ".join(key_facts[:3])
        else:
            key_findings = final_answer[:200] if final_answer else ""

        summary = TurnSummary(
            run_id=run.get("run_id", ""),
            mode="agent",
            query_brief=user_message[:120],
            answer_brief=final_answer[:300] if final_answer else "",
            tools_used=tools,
            files_touched=files,
            key_findings=key_findings,
        )

        # Count tokens for the formatted string
        summary.token_cost = self._counter.count_tokens(summary.to_context_string())
        return summary

    def summarize_chat_run(
        self,
        user_message: str,
        final_answer: str,
    ) -> TurnSummary:
        """Summarize a chat run into a compact context string.

        Args:
            user_message: User's input.
            final_answer: Model's response.

        Returns:
            TurnSummary with token cost.
        """
        summary = TurnSummary(
            run_id="",
            mode="chat",
            query_brief=user_message[:120],
            answer_brief=final_answer[:200] if final_answer else "",
        )

        summary.token_cost = self._counter.count_tokens(summary.to_context_string())
        return summary
