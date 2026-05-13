"""Conversation rewind helpers for workspace-backed threads."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from orchestrator.agent.coding_session import CodingSessionState
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_turn_to_summary(
    existing_summary: str,
    user_msg: str,
    assistant_msg: str,
    max_chars: int = 2000,
) -> str:
    """Append one turn to a compact conversation summary."""
    new_turn = f"user: {user_msg.strip()}\nassistant: {assistant_msg.strip()}"
    if not existing_summary:
        return new_turn
    combined = f"{existing_summary}\n{new_turn}"
    if len(combined) <= max_chars:
        return combined
    return "..." + combined[-max_chars:]


def build_active_run_summary(runs: list[dict[str, Any]]) -> str:
    """Rebuild conversation summary text from visible runs only."""
    summary = ""
    for run in runs:
        user_message = str(run.get("user_message") or "").strip()
        assistant_message = str(run.get("final_answer") or "").strip()
        if not user_message and not assistant_message:
            continue
        summary = _append_turn_to_summary(summary, user_message, assistant_message)
    return summary


async def capture_rewind_checkpoint(
    *,
    conversation: dict[str, Any],
    run_id: str,
    user_message: str,
    conversation_repo: ConversationRepo,
    agent_repo: AgentRepo,
) -> Optional[dict[str, Any]]:
    """Persist a rewind checkpoint for a workspace-backed conversation."""
    workspace_path = str(conversation.get("workspace_path") or "").strip()
    if not workspace_path:
        return None

    state_record = await agent_repo.get_coding_session_state(conversation["conversation_id"])
    state_before = (
        state_record.get("state")
        if isinstance(state_record, dict)
        else CodingSessionState().to_dict()
    )
    entry_seq_before = await agent_repo.get_latest_coding_session_entry_seq(
        conversation["conversation_id"]
    )
    return await conversation_repo.create_rewind_checkpoint(
        conversation_id=conversation["conversation_id"],
        run_id=run_id,
        user_message=user_message,
        entry_seq_before=entry_seq_before,
        state_before=state_before,
    )


async def rewind_conversation_to_run(
    *,
    conversation_id: str,
    run_id: str,
    conversation_repo: ConversationRepo,
    trace_repo: TraceRepo,
    agent_repo: AgentRepo,
) -> dict[str, Any]:
    """Rewind the active branch of a conversation to before the target run."""
    if await trace_repo.has_active_run_for_conversation(conversation_id):
        raise ValueError("Cannot rewind while a run is still active")

    checkpoint = await conversation_repo.get_rewind_checkpoint(
        conversation_id=conversation_id,
        run_id=run_id,
    )
    if checkpoint is None:
        raise LookupError("Rewind checkpoint not found")

    visible_runs = await trace_repo.list_runs_for_conversation(conversation_id)
    target_index = next(
        (index for index, run in enumerate(visible_runs) if run.get("run_id") == run_id),
        None,
    )
    if target_index is None:
        target_run = await trace_repo.get_run(run_id)
        if (
            target_run
            and target_run.get("conversation_id") == conversation_id
            and target_run.get("rewound_at") is not None
        ):
            return {
                "conversation": await conversation_repo.get(conversation_id),
                "runs": visible_runs,
                "restored_prompt": checkpoint["user_message"],
                "rewound_run_ids": [],
                "rewind_group_id": target_run.get("rewind_group_id") or "",
            }
        raise ValueError("Target run is not on the active conversation branch")

    tail_runs = visible_runs[target_index:]
    rewind_group_id = str(uuid.uuid4())
    rewound_at = _utcnow()
    rewound_run_ids = [str(run["run_id"]) for run in tail_runs]

    await trace_repo.mark_runs_rewound(
        rewound_run_ids,
        rewound_at=rewound_at,
        rewind_group_id=rewind_group_id,
    )
    await agent_repo.mark_coding_session_entries_rewound(
        conversation_id,
        after_seq=int(checkpoint.get("entry_seq_before") or 0),
        rewound_at=rewound_at,
        rewind_group_id=rewind_group_id,
    )
    await agent_repo.upsert_coding_session_state(
        conversation_id,
        checkpoint.get("state_before") or CodingSessionState().to_dict(),
        last_run_id=None,
    )

    remaining_runs = await trace_repo.list_runs_for_conversation(conversation_id)
    await conversation_repo.update(
        conversation_id,
        summary=build_active_run_summary(remaining_runs),
    )
    updated_conversation = await conversation_repo.get(conversation_id)
    return {
        "conversation": updated_conversation,
        "runs": remaining_runs,
        "restored_prompt": checkpoint["user_message"],
        "rewound_run_ids": rewound_run_ids,
        "rewind_group_id": rewind_group_id,
    }
