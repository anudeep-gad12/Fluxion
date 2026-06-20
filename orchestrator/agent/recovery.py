"""Recovery helpers for agent crash recovery.

This module provides:
- Idempotent tool result caching lookup
- Recovery hint injection into message context
- Tool retry decision logic
- Idempotency key generation
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.agent.state_machine import RecoveryContext
    from orchestrator.agent.tools.registry import ToolRegistry


@dataclass
class RecoveryAction:
    """Describes what action to take for a recovered tool call.

    Attributes:
        tool_call_id: The original tool call ID.
        tool_name: Name of the tool.
        action: Action to take - "retry", "skip", or "inject_hint".
        cached_result: If available, the cached result to use.
        hint_message: If action is "inject_hint", the system message to inject.
    """

    tool_call_id: str
    tool_name: str
    action: str  # "retry" | "skip" | "inject_hint"
    cached_result: Optional[Dict[str, Any]] = None
    hint_message: Optional[Dict[str, Any]] = None


def should_retry_tool(
    tool_name: str,
    tool_call_status: str,
    registry: "ToolRegistry",
) -> bool:
    """Determine if a tool call should be retried after crash.

    Decision logic:
    - Idempotent tools (web_search, web_extract) can always be safely retried
    - Non-idempotent tools in "pending" state never started,
      so they can be retried
    - Non-idempotent tools in "running" state were interrupted mid-execution,
      and cannot be safely retried - need hint injection instead

    Args:
        tool_name: Name of the tool.
        tool_call_status: Current status (pending, running, interrupted).
        registry: Tool registry for idempotency check.

    Returns:
        True if safe to retry, False if hint should be injected instead.
    """
    # Idempotent tools can always be retried safely
    if registry.is_idempotent(tool_name):
        return True

    # Non-idempotent tools in "pending" state never started executing
    if tool_call_status == "pending":
        return True

    # Non-idempotent tools in "running" or "interrupted" state were
    # mid-execution and cannot be safely retried
    return False


def build_recovery_messages(
    recovery_context: "RecoveryContext",
    existing_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Inject recovery hints into message context.

    Inserts system messages from recovery_context.hints at appropriate
    positions in the conversation to inform the model about interrupted
    non-idempotent tool calls.

    Args:
        recovery_context: RecoveryContext from state machine.
        existing_messages: Current message list.

    Returns:
        New message list with hints injected (does not mutate original).
    """
    if not recovery_context.hints:
        return existing_messages

    # Create a copy to avoid mutating the original
    messages = list(existing_messages)

    # Find insertion point - after system message but before user content
    insert_idx = 0
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            insert_idx = i + 1
            break

    # Insert all hints at the insertion point
    for hint in recovery_context.hints:
        messages.insert(insert_idx, hint)
        insert_idx += 1

    return messages


def get_cached_tool_result(
    tool_call_id: str,
    tool_calls: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Get cached result for a completed tool call.

    Used during recovery to avoid re-executing tools that completed
    successfully before the crash.

    Args:
        tool_call_id: The tool call ID to look up.
        tool_calls: List of tool call records from DB.

    Returns:
        Result dict with result_summary if found and successful, None otherwise.
    """
    for tc in tool_calls:
        if tc.get("id") == tool_call_id:
            if tc.get("status") == "success":
                return {
                    "result_summary": tc.get("result_summary", ""),
                    "tool_call_id": tool_call_id,
                }
    return None


def create_idempotency_key(
    run_id: str,
    step_number: int,
    tool_name: str,
    arguments_hash: str,
) -> str:
    """Create a unique idempotency key for a tool call.

    The key ensures that duplicate tool calls (from retries or crashes)
    are deduplicated at the database level. If a tool call with the same
    idempotency key already exists, we can use the cached result instead
    of re-executing.

    Format: {run_id}:{step_number}:{tool_name}:{arguments_hash}

    Args:
        run_id: The agent run ID.
        step_number: Current step number.
        tool_name: Name of the tool.
        arguments_hash: Hash of the tool arguments (e.g., MD5 of JSON).

    Returns:
        Idempotency key string.
    """
    return f"{run_id}:{step_number}:{tool_name}:{arguments_hash}"


def determine_recovery_actions(
    interrupted_tool_calls: List[Dict[str, Any]],
    registry: "ToolRegistry",
) -> List[RecoveryAction]:
    """Determine recovery actions for all interrupted tool calls.

    Analyzes each interrupted tool call and determines the appropriate
    recovery action based on idempotency.

    Args:
        interrupted_tool_calls: List of interrupted tool call dicts.
        registry: Tool registry for idempotency checks.

    Returns:
        List of RecoveryAction objects describing what to do.
    """
    actions = []

    for tc in interrupted_tool_calls:
        tool_name = tc.get("tool_name", "")
        status = tc.get("status", "")
        tool_call_id = tc.get("id", "")

        if should_retry_tool(tool_name, status, registry):
            # Safe to retry
            actions.append(
                RecoveryAction(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    action="retry",
                )
            )
        else:
            # Need to inject hint for non-idempotent tool
            hint_message = {
                "role": "system",
                "content": (
                    f"IMPORTANT: The previous {tool_name} execution was "
                    f"interrupted by a system restart. The result was lost. "
                    f"Please regenerate and re-run the code to get the result."
                ),
                "_recovery_hint": True,
                "_tool_call_id": tool_call_id,
            }
            actions.append(
                RecoveryAction(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    action="inject_hint",
                    hint_message=hint_message,
                )
            )

    return actions
