"""Normalized prompt-history management for coding-session entries."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Optional

from orchestrator.agent.coding_session import CodingSessionEntry


@dataclass
class CodingContextNormalizationStats:
    """Counters emitted while normalizing coding transcript history."""

    repaired_missing_tool_outputs: int = 0
    dropped_orphan_tool_outputs: int = 0
    stripped_unsupported_media: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serialize stats for trace payloads."""
        return {
            "repaired_missing_tool_outputs": self.repaired_missing_tool_outputs,
            "dropped_orphan_tool_outputs": self.dropped_orphan_tool_outputs,
            "stripped_unsupported_media": self.stripped_unsupported_media,
        }


@dataclass
class CodingContextManagerResult:
    """Normalized message list plus normalization metadata."""

    messages: list[dict[str, Any]]
    stats: CodingContextNormalizationStats


class CodingContextManager:
    """Normalize replayable coding-session entries into prompt messages.

    The stored table is intentionally simple, but model prompts need stronger
    invariants: assistant tool calls must be followed by matching tool outputs,
    orphan tool outputs should not be replayed, and unsupported media should not
    leak into text-only model calls.
    """

    _REPLAYABLE_TYPES = {
        "user",
        "assistant_tool_calls",
        "tool_result",
        "assistant",
        "compaction_summary",
    }

    def __init__(self, *, supports_vision: bool = False) -> None:
        self._supports_vision = supports_vision

    def normalize_entries(
        self,
        entries: list[CodingSessionEntry],
    ) -> CodingContextManagerResult:
        """Return normalized OpenAI-compatible messages for replay."""
        stats = CodingContextNormalizationStats()
        loose_messages = self._entries_to_loose_messages(entries)
        media_stripped = [
            self._strip_unsupported_media(message, stats)
            for message in loose_messages
        ]
        return CodingContextManagerResult(
            messages=self._normalize_tool_pairs(media_stripped, stats),
            stats=stats,
        )

    def is_replay_eligible(self, entry: CodingSessionEntry) -> bool:
        """Return whether a persisted entry should be replayed into prompts."""
        if entry.entry_type not in self._REPLAYABLE_TYPES:
            return False
        return entry.content_json.get("replay_eligible", True) is not False

    def _entries_to_loose_messages(
        self,
        entries: list[CodingSessionEntry],
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            if not self.is_replay_eligible(entry):
                index += 1
                continue

            if (
                entry.entry_type == "assistant"
                and index + 1 < len(entries)
                and entries[index + 1].entry_type == "assistant_tool_calls"
                and entries[index + 1].run_id == entry.run_id
                and entries[index + 1].step_number == entry.step_number
                and self.is_replay_eligible(entries[index + 1])
            ):
                tool_entry = entries[index + 1]
                content = tool_entry.content_json.get("content")
                if content in (None, ""):
                    content = entry.content_json.get("content")
                assistant_message = self._assistant_tool_call_message(
                    tool_entry,
                    content=content,
                )
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
            elif entry.entry_type in {"assistant", "user", "compaction_summary"}:
                content = entry.content_json.get("content")
                if content not in (None, "", []):
                    messages.append({"role": entry.role, "content": content})
            index += 1
        return messages

    def _assistant_tool_call_message(
        self,
        entry: CodingSessionEntry,
        *,
        content: Any = None,
    ) -> Optional[dict[str, Any]]:
        tool_calls = [
            tool_call
            for tool_call in (entry.content_json.get("tool_calls") or [])
            if isinstance(tool_call, dict)
        ]
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

    def _normalize_tool_pairs(
        self,
        messages: list[dict[str, Any]],
        stats: CodingContextNormalizationStats,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        pending_tool_calls: list[tuple[str, Optional[str]]] = []

        def flush_missing_outputs() -> None:
            nonlocal pending_tool_calls
            for tool_call_id, tool_name in pending_tool_calls:
                normalized.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": (
                            "[Missing tool output repaired during context replay. "
                            "The original result was not persisted in this coding session.]"
                        ),
                    }
                )
                stats.repaired_missing_tool_outputs += 1
            pending_tool_calls = []

        for message in messages:
            role = message.get("role")
            if role == "tool":
                tool_call_id = str(message.get("tool_call_id") or "").strip()
                if not tool_call_id:
                    stats.dropped_orphan_tool_outputs += 1
                    continue
                pending_ids = [item[0] for item in pending_tool_calls]
                if tool_call_id not in pending_ids:
                    stats.dropped_orphan_tool_outputs += 1
                    continue
                normalized.append(message)
                pending_tool_calls = [
                    item for item in pending_tool_calls if item[0] != tool_call_id
                ]
                continue

            if pending_tool_calls:
                flush_missing_outputs()

            normalized.append(message)
            if role == "assistant":
                pending_tool_calls.extend(self._tool_call_refs(message))

        if pending_tool_calls:
            flush_missing_outputs()
        return normalized

    def _tool_call_refs(
        self,
        message: dict[str, Any],
    ) -> list[tuple[str, Optional[str]]]:
        refs: list[tuple[str, Optional[str]]] = []
        for index, tool_call in enumerate(message.get("tool_calls") or [], start=1):
            if not isinstance(tool_call, dict):
                continue
            tool_call_id = str(tool_call.get("id") or "").strip()
            if not tool_call_id:
                tool_call_id = f"missing-tool-call-{index}"
                tool_call["id"] = tool_call_id
            function = (
                tool_call.get("function")
                if isinstance(tool_call.get("function"), dict)
                else {}
            )
            tool_name = function.get("name") if isinstance(function, dict) else None
            refs.append((tool_call_id, str(tool_name) if tool_name else None))
        return refs

    def _strip_unsupported_media(
        self,
        message: dict[str, Any],
        stats: CodingContextNormalizationStats,
    ) -> dict[str, Any]:
        if self._supports_vision:
            return message
        cloned = copy.deepcopy(message)
        content = cloned.get("content")
        if not isinstance(content, list):
            return cloned
        stripped: list[Any] = []
        for item in content:
            if isinstance(item, dict) and str(item.get("type") or "") in {
                "image_url",
                "input_image",
            }:
                stats.stripped_unsupported_media += 1
                continue
            stripped.append(item)
        cloned["content"] = stripped
        return cloned
