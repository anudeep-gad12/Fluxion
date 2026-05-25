"""Coding-session prompt reconstruction from transcript replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from orchestrator.agent.coding_session import CodingSessionEntry, CodingSessionState
from orchestrator.context.budget import ContextBudget
from orchestrator.context.history_builder import HistoryBuilder
from orchestrator.utils.tokens import TokenCounter


@dataclass
class CodingSessionContext:
    """Built coding-session context for prompt replay."""

    messages: list[dict[str, Any]]
    budget: ContextBudget
    used_session_entries: bool
    metadata_included: bool
    replayed_entry_count: int
    checkpoint_present: bool = False
    preserved_tail_count: int = 0
    restored_file_count: int = 0
    replay_source_ranges: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodingStoredContext:
    """Replayable stored coding context metrics."""

    messages: list[dict[str, Any]]
    token_count: int
    replayable_entry_count: int
    restored_file_count: int = 0


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
        transcript_entries: list[CodingSessionEntry],
        current_query: Optional[str] = None,
        metadata_message: Optional[str] = None,
        restored_file_messages: Optional[list[dict[str, Any]]] = None,
    ) -> CodingSessionContext:
        """Build system + metadata + transcript messages for a coding session."""
        budget = ContextBudget(
            max_tokens=self._max_context_tokens,
            reserve_for_response=self._reserve_for_response,
        )
        budget.system_prompt_tokens = (
            self._counter.count_tokens(system_prompt) + HistoryBuilder.MSG_OVERHEAD
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        used_session_entries = bool(transcript_entries)
        checkpoint_entry, tail_entries = self._split_checkpoint_and_tail(transcript_entries)
        checkpoint_message = self._checkpoint_message(checkpoint_entry)
        if checkpoint_message:
            messages.append(checkpoint_message)
        neutral_metadata = self._metadata_message(
            session_state=session_state,
            explicit_metadata=metadata_message,
        )
        if neutral_metadata:
            messages.append(neutral_metadata)
        restored_messages = restored_file_messages or []
        if restored_messages:
            messages.extend(restored_messages)

        if transcript_entries:
            messages.extend(self._entries_to_messages(tail_entries))
        elif current_query is not None:
            if current_query:
                budget.current_query_tokens = (
                    self._counter.count_tokens(current_query) + HistoryBuilder.MSG_OVERHEAD
                )
                messages.append({"role": "user", "content": current_query})

        total_tokens = self.estimate_tokens(messages)
        budget.history_tokens = max(0, total_tokens - budget.system_prompt_tokens)
        return CodingSessionContext(
            messages=messages,
            budget=budget,
            used_session_entries=used_session_entries,
            metadata_included=neutral_metadata is not None,
            replayed_entry_count=self._replayable_entry_count(
                tail_entries,
                checkpoint_present=checkpoint_entry is not None,
                restored_file_messages=restored_messages,
            ),
            checkpoint_present=checkpoint_entry is not None,
            preserved_tail_count=len(tail_entries),
            restored_file_count=self._restored_file_count(restored_messages),
            replay_source_ranges=self._replay_source_ranges(checkpoint_entry, tail_entries),
        )

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate prompt tokens for a message list."""
        total = 0
        for message in messages:
            total += self._counter.count_tokens(self._message_token_text(message))
            total += HistoryBuilder.MSG_OVERHEAD
        return total

    def build_stored_context(
        self,
        *,
        session_state: Optional[CodingSessionState],
        transcript_entries: list[CodingSessionEntry],
        metadata_message: Optional[str] = None,
        restored_file_messages: Optional[list[dict[str, Any]]] = None,
    ) -> CodingStoredContext:
        """Build replayable stored context without the system prompt."""
        messages: list[dict[str, Any]] = []
        checkpoint_entry, tail_entries = self._split_checkpoint_and_tail(transcript_entries)
        checkpoint_message = self._checkpoint_message(checkpoint_entry)
        if checkpoint_message:
            messages.append(checkpoint_message)
        neutral_metadata = self._metadata_message(
            session_state=session_state,
            explicit_metadata=metadata_message,
        )
        if neutral_metadata:
            messages.append(neutral_metadata)
        restored_messages = restored_file_messages or []
        if restored_messages:
            messages.extend(restored_messages)
        messages.extend(self._entries_to_messages(tail_entries))
        return CodingStoredContext(
            messages=messages,
            token_count=self.estimate_tokens(messages),
            replayable_entry_count=self._replayable_entry_count(
                tail_entries,
                checkpoint_present=checkpoint_entry is not None,
                restored_file_messages=restored_messages,
            ),
            restored_file_count=self._restored_file_count(restored_messages),
        )

    def _split_checkpoint_and_tail(
        self,
        entries: list[CodingSessionEntry],
    ) -> tuple[Optional[CodingSessionEntry], list[CodingSessionEntry]]:
        checkpoint_entries = [
            entry
            for entry in entries
            if entry.entry_type == "compaction_summary" and self._is_replay_eligible(entry)
        ]
        checkpoint_entry = checkpoint_entries[-1] if checkpoint_entries else None
        if checkpoint_entry is None:
            return None, [entry for entry in entries if entry.entry_type != "compaction_summary"]
        return (
            checkpoint_entry,
            [
                entry
                for entry in entries
                if entry.seq > checkpoint_entry.seq and entry.entry_type != "compaction_summary"
            ],
        )

    def _checkpoint_message(
        self,
        entry: Optional[CodingSessionEntry],
    ) -> Optional[dict[str, Any]]:
        if entry is None:
            return None
        content = entry.content_json.get("content")
        if content in (None, "", []):
            return None
        return {"role": entry.role or "user", "content": content}

    def _metadata_message(
        self,
        *,
        session_state: Optional[CodingSessionState],
        explicit_metadata: Optional[str],
    ) -> Optional[dict[str, Any]]:
        if explicit_metadata:
            metadata = explicit_metadata.strip()
        elif session_state:
            metadata = self._render_neutral_metadata(session_state)
        else:
            metadata = ""
        if not metadata:
            return None
        return {"role": "system", "content": metadata}

    def _render_neutral_metadata(self, session_state: CodingSessionState) -> str:
        session_state.normalize()
        lines: list[str] = []
        if session_state.objective:
            lines.append("- current_request: " + session_state.objective)
        if session_state.modified_files:
            lines.append("- changed_files: " + ", ".join(session_state.modified_files[-8:]))
        if session_state.read_files:
            lines.append("- referenced_files: " + ", ".join(session_state.read_files[-8:]))
        if session_state.recent_commands:
            lines.append("- recent_commands: " + " | ".join(session_state.recent_commands[-4:]))
        if not lines:
            return ""
        return "CODING SESSION CURRENT STATE\n" + "\n".join(lines)

    def _entries_to_messages(
        self,
        entries: list[CodingSessionEntry],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            if not self._is_replay_eligible(entry):
                index += 1
                continue
            if (
                entry.entry_type == "assistant"
                and index + 1 < len(entries)
                and entries[index + 1].entry_type == "assistant_tool_calls"
                and entries[index + 1].run_id == entry.run_id
                and entries[index + 1].step_number == entry.step_number
                and self._is_replay_eligible(entries[index + 1])
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
            index += 1
        return messages

    def _is_replay_eligible(self, entry: CodingSessionEntry) -> bool:
        """Return whether a persisted entry should be replayed into prompts."""
        if entry.entry_type not in {
            "user",
            "assistant_tool_calls",
            "tool_result",
            "assistant",
            "compaction_summary",
        }:
            return False
        return entry.content_json.get("replay_eligible", True) is not False

    def _restored_file_count(self, restored_file_messages: list[dict[str, Any]]) -> int:
        return sum(
            1
            for message in restored_file_messages
            if message.get("role") == "tool" and message.get("name") == "read_file"
        )

    def _replayable_entry_count(
        self,
        tail_entries: list[CodingSessionEntry],
        *,
        checkpoint_present: bool,
        restored_file_messages: list[dict[str, Any]],
    ) -> int:
        return (
            sum(1 for entry in tail_entries if self._is_replay_eligible(entry))
            + (1 if checkpoint_present else 0)
            + self._restored_file_count(restored_file_messages)
        )

    def _replay_source_ranges(
        self,
        checkpoint_entry: Optional[CodingSessionEntry],
        tail_entries: list[CodingSessionEntry],
    ) -> dict[str, Any]:
        return {
            "checkpoint_seq": checkpoint_entry.seq if checkpoint_entry else None,
            "checkpoint_covered_through_seq": (
                checkpoint_entry.content_json.get("covered_through_seq")
                if checkpoint_entry is not None
                else None
            ),
            "tail_start_seq": tail_entries[0].seq if tail_entries else None,
            "tail_end_seq": tail_entries[-1].seq if tail_entries else None,
        }

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
