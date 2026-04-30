"""Coding-session prompt reconstruction from checkpoint + raw tail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from orchestrator.agent.coding_session import (
    CodingSessionEntry,
    CodingSessionState,
    render_checkpoint_summary,
)
from orchestrator.context.budget import ContextBudget
from orchestrator.context.history_builder import HistoryBuilder
from orchestrator.utils.tokens import TokenCounter


@dataclass
class CodingSessionContext:
    """Built coding-session context for prompt replay."""

    messages: list[dict[str, Any]]
    budget: ContextBudget
    used_session_entries: bool
    used_state_fallback: bool
    raw_tail_start_seq: int
    checkpoint_through_seq: int
    replayed_entry_count: int


class CodingSessionContextBuilder:
    """Build prompt history for coding conversations."""

    def __init__(
        self,
        token_counter: TokenCounter,
        max_context_tokens: int,
        reserve_for_response: int,
    ) -> None:
        self._counter = token_counter
        self._max_context_tokens = max_context_tokens
        self._reserve_for_response = reserve_for_response

    def build(
        self,
        *,
        system_prompt: str,
        session_state: Optional[CodingSessionState],
        raw_entries: list[CodingSessionEntry],
        current_query: Optional[str] = None,
        state_fallback_message: Optional[str] = None,
    ) -> CodingSessionContext:
        """Build system + checkpoint + raw-tail messages for a coding session."""
        budget = ContextBudget(
            max_tokens=self._max_context_tokens,
            reserve_for_response=self._reserve_for_response,
        )
        budget.system_prompt_tokens = (
            self._counter.count_tokens(system_prompt) + HistoryBuilder.MSG_OVERHEAD
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        used_session_entries = bool(raw_entries)
        used_state_fallback = False
        raw_tail_start_seq = session_state.raw_tail_start_seq if session_state else 1
        checkpoint_through_seq = session_state.checkpoint_through_seq if session_state else 0

        checkpoint_message = self._checkpoint_message(
            session_state=session_state,
            explicit_summary=state_fallback_message,
        )
        if checkpoint_message:
            messages.append(checkpoint_message)

        if raw_entries:
            messages.extend(self._entries_to_messages(raw_entries))
        elif current_query is not None:
            if current_query:
                budget.current_query_tokens = (
                    self._counter.count_tokens(current_query) + HistoryBuilder.MSG_OVERHEAD
                )
                messages.append({"role": "user", "content": current_query})
            if checkpoint_message:
                used_state_fallback = True

        if not raw_entries and checkpoint_message and not current_query:
            used_state_fallback = True

        total_tokens = self.estimate_tokens(messages)
        budget.history_tokens = max(0, total_tokens - budget.system_prompt_tokens)
        return CodingSessionContext(
            messages=messages,
            budget=budget,
            used_session_entries=used_session_entries,
            used_state_fallback=used_state_fallback,
            raw_tail_start_seq=raw_tail_start_seq,
            checkpoint_through_seq=checkpoint_through_seq,
            replayed_entry_count=len(raw_entries),
        )

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate prompt tokens for a message list."""
        total = 0
        for message in messages:
            total += self._counter.count_tokens(self._message_token_text(message))
            total += HistoryBuilder.MSG_OVERHEAD
        return total

    def _checkpoint_message(
        self,
        *,
        session_state: Optional[CodingSessionState],
        explicit_summary: Optional[str],
    ) -> Optional[dict[str, Any]]:
        if explicit_summary:
            summary = explicit_summary.strip()
        elif session_state and session_state.checkpoint_summary:
            summary = session_state.checkpoint_summary.strip()
        elif session_state and self._should_render_state_checkpoint(session_state):
            summary = render_checkpoint_summary(session_state)
        else:
            summary = ""
        if not summary:
            return None
        return {"role": "system", "content": summary}

    def _should_render_state_checkpoint(self, session_state: CodingSessionState) -> bool:
        return bool(
            session_state.objective
            or session_state.accepted_plan
            or session_state.prior_outcomes
            or session_state.read_files
            or session_state.modified_files
            or session_state.validation_results
            or session_state.open_tasks
            or session_state.recent_commands
            or session_state.current_hypothesis
        )

    def _entries_to_messages(
        self,
        entries: list[CodingSessionEntry],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            if (
                entry.entry_type == "assistant"
                and index + 1 < len(entries)
                and entries[index + 1].entry_type == "assistant_tool_calls"
                and entries[index + 1].run_id == entry.run_id
                and entries[index + 1].step_number == entry.step_number
            ):
                tool_entry = entries[index + 1]
                content = tool_entry.content_json.get("content")
                if content in (None, ""):
                    content = entry.content_json.get("content")
                assistant_message = self._assistant_tool_call_message(tool_entry, content=content)
                if assistant_message:
                    messages.append(assistant_message)
                index += 2
                continue

            if entry.entry_type == "assistant_tool_calls":
                assistant_message = self._assistant_tool_call_message(entry)
                if assistant_message:
                    messages.append(assistant_message)
            elif entry.entry_type == "tool_result":
                messages.extend(self._tool_result_messages(entry))
            elif entry.entry_type in {"assistant", "user"}:
                content = entry.content_json.get("content")
                if content not in (None, "", []):
                    messages.append({"role": entry.role, "content": content})
            elif entry.entry_type == "checkpoint":
                content = entry.content_json.get("content")
                if content:
                    messages.append({"role": "system", "content": content})
            index += 1
        return messages

    def _assistant_tool_call_message(
        self,
        entry: CodingSessionEntry,
        *,
        content: Any = None,
    ) -> Optional[dict[str, Any]]:
        tool_calls = entry.content_json.get("tool_calls") or []
        assistant_content = entry.content_json.get("content") if content is None else content
        if not tool_calls and assistant_content in (None, "", []):
            return None
        message: dict[str, Any] = {"role": "assistant", "content": assistant_content or ""}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message

    def _tool_result_messages(self, entry: CodingSessionEntry) -> list[dict[str, Any]]:
        content = entry.content_json.get("content") or ""
        messages = [
            {
                "role": "tool",
                "tool_call_id": entry.content_json.get("tool_call_id"),
                "name": entry.content_json.get("name"),
                "content": content,
            }
        ]
        recovery_note = entry.content_json.get("recovery_note")
        if recovery_note:
            messages.append({"role": "system", "content": str(recovery_note)})
        return messages

    def _message_token_text(self, message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            text = content
        else:
            text = str(content)
        if message.get("tool_calls"):
            text += str(message["tool_calls"])
        if message.get("tool_call_id"):
            text += str(message.get("tool_call_id"))
        if message.get("name"):
            text += str(message.get("name"))
        return text
