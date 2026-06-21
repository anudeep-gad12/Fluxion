"""Agent run routes for the browser coding agent.

This module provides REST API endpoints for the browser coding agent:
- POST /api/agent/runs - Start a new agent run
- GET /api/agent/runs/{id} - Get run status
- GET /api/agent/runs/{id}/stream - SSE event stream with resumption support
- POST /api/agent/runs/{id}/cancel - Cancel an active run
- GET /api/agent/runs/{id}/trace - Get full execution trace
"""

import asyncio
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from orchestrator.agent.artifacts import AgentArtifactManager
from orchestrator.agent.plan_doc import (
    append_plan_doc_section,
    create_initial_plan_doc,
    plan_doc_relative_path,
)
from orchestrator.agent.plan_mode import (
    PlanDecision,
    build_plan_implementation_prompt,
    normalize_collaboration_mode,
)
from orchestrator.agent.tool_result_payloads import (
    bash_output_from_result_data,
    display_result_data,
    parse_stored_result_detail,
)
from orchestrator.conversation_titles import conversation_title_from_message
from orchestrator.logging_config import (
    get_logger,
    get_request_id,
    set_component,
    set_request_id,
)
from orchestrator.reasoning_controls import ReasoningSettings
from orchestrator.routes.workspaces import _resolve_workspace_path, ensure_fluxion_gitignore
from orchestrator.schemas import (
    AgentAssistantUpdateResponse,
    AgentCitationResponse,
    AgentRunStatusResponse,
    AgentRunTraceResponse,
    AgentStepResponse,
    AgentToolCallResponse,
    CreateAgentRunRequest,
    CreateAgentRunResponse,
    PlanApprovalRequest,
    PlanApprovalResponse,
    PlanRejectRequest,
    RunArtifactResponse,
    UserInputResponseRequest,
)
from orchestrator.services.conversation_rewind import capture_rewind_checkpoint
from orchestrator.services.reasoning_settings import get_runtime_reasoning_settings
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.agent_repo import AgentRepo
from orchestrator.storage.repositories.conversation_repo import ConversationRepo
from orchestrator.storage.repositories.trace_repo import TraceRepo

logger = get_logger(__name__)


MODEL_REGISTRY_PROVIDERS = {
    "openai",
    "xai",
    "grok",
    "openrouter",
    "deepinfra",
    "fireworks",
    "local",
}


def _registry_selection(provider_header: Optional[str], model: str) -> str:
    """Preserve explicit UI provider selection when resolving a model id."""
    provider = (provider_header or "").strip().lower()
    if provider in MODEL_REGISTRY_PROVIDERS and ":" not in model:
        return f"{provider}:{model}"
    return model

router = APIRouter(prefix="/api/agent", tags=["agent"])

# =============================================================================
# Module-level state for active runs
# =============================================================================

# WARNING: These are in-memory, single-process only.
# For multi-worker deployment, use Redis pub/sub or durable event bus.
_active_runs: Dict[str, bool] = {}  # run_id -> is_active (no queue; pub/sub via history + notify)
_abort_signals: Dict[str, asyncio.Event] = {}
_pause_signals: Dict[str, asyncio.Event] = {}  # Set when user requests pause
_resume_signals: Dict[str, asyncio.Event] = {}  # Set when user requests resume
_steer_queues: Dict[str, List[str]] = {}  # Pending steering messages per run
_event_history: Dict[str, List[Dict[str, Any]]] = {}  # Append-only event log per run
_event_notify: Dict[str, asyncio.Event] = {}  # Notifies SSE generators of new events
_run_tokens: Dict[str, str] = {}  # Per-run stream auth tokens
_run_sessions: Dict[str, str] = {}  # Per-run session IDs for access control
_run_tasks: Dict[str, asyncio.Task] = {}  # Background task per active run
# run_id -> {tool_call_id -> Future[bool]}
_approval_queues: Dict[str, Dict[str, asyncio.Future]] = {}
_plan_approval_queues: Dict[str, Dict[str, asyncio.Future]] = {}
_pending_plan_approvals: Dict[str, Dict[str, Dict[str, Any]]] = {}
_user_input_queues: Dict[str, Dict[str, asyncio.Future]] = {}


def _format_background_error(error: BaseException) -> str:
    """Format background task errors without dropping blank exception details."""
    message = str(error).strip()
    if message:
        return f"{error.__class__.__name__}: {message}"
    return f"{error.__class__.__name__}: {repr(error)}"


def get_session_context(request: Request) -> Tuple[Optional[str], bool]:
    """Extract session context from request.

    External clients may pass session ID via X-CLI-Session header for
    ChatGPT token lookup. Falls back to session middleware cookie.

    Returns:
        Tuple of (session_id, is_owner).
    """
    session_id = request.headers.get("x-cli-session") or getattr(request.state, "session_id", None)
    is_owner = getattr(request.state, "is_owner", True)
    return session_id, is_owner


# =============================================================================
# SSE Event Translation
# =============================================================================

# Map engine event types to SSE event types
_EVENT_TYPE_MAP = {
    "agent_started": "agent_state",
    "step_started": "step_start",
    "thinking": "thinking",
    "tool_start": "tool_start",
    "tool_approval_required": "tool_approval_required",
    "tool_approval_decided": "tool_approval_decided",
    "plan_approval_required": "plan_approval_required",
    "plan_approved": "plan_approved",
    "plan_doc_updated": "plan_doc_updated",
    "user_input_required": "user_input_required",
    "tool_result": "tool_result",
    "assistant_update": "assistant_update",
    "synthesizing": "agent_state",
    "answer_token": "answer",
    "agent_complete": "complete",
    "agent_error": "error",
    "agent_paused": "paused",
    "agent_resumed": "resumed",
    "steer_injected": "steer",
    "slow_response": "slow_response",
    "usage_update": "usage_update",
    "context_pruned": "context_pruned",
    "conversation_compacted": "conversation_compacted",
    "run_cancelled": "run_cancelled",
}


def _translate_event(event: Dict[str, Any], seq: int) -> Dict[str, Any]:
    """Translate engine event to SSE format with sequence number.

    Args:
        event: Engine event dict with 'type' key.
        seq: Sequence number for resumption.

    Returns:
        SSE event dict with event type and JSON data.
    """
    engine_type = event.get("type", "unknown")
    sse_type = _EVENT_TYPE_MAP.get(engine_type, engine_type)

    # Build data payload
    data = {
        "seq": seq,
        "type": sse_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Copy relevant fields from engine event
    for key, value in event.items():
        if key != "type":
            data[key] = value

    return {
        "event": sse_type,
        "data": json.dumps(data),
    }


# =============================================================================
# Cleanup helpers
# =============================================================================


async def _persist_run_event(run_id: str, seq: int, event: Dict[str, Any]) -> None:
    """Fire-and-forget: persist a single SSE event to the database.

    Args:
        run_id: The run ID.
        seq: Sequence number.
        event: Event dict to persist.
    """
    try:
        db = await get_db()
        repo = AgentRepo(db)
        await repo.create_run_event(run_id, seq, event.get("type", "unknown"), event)
    except Exception as e:
        logger.warning(
            "Failed to persist run event",
            extra={"run_id": run_id, "seq": seq, "error": str(e)},
        )


async def _emit_external_run_event(run_id: str, event: Dict[str, Any]) -> None:
    """Append an event from a route/helper outside the engine callback."""
    history = _event_history.setdefault(run_id, [])
    seq = len(history) + 1
    event["seq"] = seq
    history.append(event.copy())
    await _persist_run_event(run_id, seq, event)
    notify = _event_notify.get(run_id)
    if notify:
        notify.set()


def _resolve_pending_run_waiters(run_id: str) -> None:
    """Unblock route-owned waiters when a run is cancelled or finalized."""
    pending_approvals = _approval_queues.pop(run_id, {})
    for future in pending_approvals.values():
        if not future.done():
            future.set_result(False)

    pending_plans = _plan_approval_queues.pop(run_id, {})
    for future in pending_plans.values():
        if not future.done():
            future.set_result(PlanDecision(decision="rejected", feedback="Run cancelled."))

    pending_inputs = _user_input_queues.pop(run_id, {})
    for future in pending_inputs.values():
        if not future.done():
            future.set_result({})


async def _mark_run_cancelled(run_id: str, reason: str = "Stopped by user") -> None:
    """Persist cancellation in both run status and agent-state fields."""
    db = await get_db()
    trace_repo = TraceRepo(db)
    agent_repo = AgentRepo(db)
    await trace_repo.update_run(
        run_id,
        status="cancelled",
        error_message=reason,
        agent_state="cancelled",
    )
    await agent_repo.update_run_agent_state(
        run_id,
        status="cancelled",
        agent_state="cancelled",
        error_message=reason,
    )


async def _cancel_run_task_later(run_id: str, delay_seconds: float = 2.0) -> None:
    """Force-cancel a background task if cooperative abort does not finish."""
    await asyncio.sleep(delay_seconds)
    task = _run_tasks.get(run_id)
    if task and not task.done():
        logger.warning("Force-cancelling agent run task", extra={"run_id": run_id})
        task.cancel()


async def _emit_tool_approval_decided(
    *,
    run_id: str,
    tool_call_id: str,
    decision: str,
    status_label: str,
) -> None:
    """Persist and broadcast an immediate approval/denial state change."""
    try:
        db = await get_db()
        agent_repo = AgentRepo(db)
        await agent_repo.update_tool_call(
            tool_call_id,
            approval_decision=decision,
            approval_policy="user",
            approval_decided_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.debug(
            "Tool approval decision could not update DB row",
            extra={
                "run_id": run_id,
                "tool_call_id": tool_call_id,
                "decision": decision,
                "error": str(e),
            },
        )

    await _emit_external_run_event(
        run_id,
        {
            "type": "tool_approval_decided",
            "run_id": run_id,
            "tool_call_id": tool_call_id,
            "decision": decision,
            "status": status_label,
        },
    )


def _plan_doc_update_event(
    *,
    run_id: str,
    file_path: str,
    action: str,
    summary: str,
    byte_count: Optional[int] = None,
    step_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a plan_doc_updated engine event."""
    event: Dict[str, Any] = {
        "type": "plan_doc_updated",
        "run_id": run_id,
        "file_path": file_path,
        "action": action,
        "summary": summary,
    }
    if byte_count is not None:
        event["bytes"] = byte_count
    if step_number is not None:
        event["step_number"] = step_number
    return event


async def _record_plan_doc_artifact(
    *,
    run_id: str,
    file_path: str,
    action: str,
    detail: str,
) -> None:
    try:
        db = await get_db()
        repo = AgentRepo(db)
        await repo.create_run_artifact(
            run_id=run_id,
            artifact_type="plan_doc",
            file_path=file_path,
            action=action,
            detail=detail,
        )
    except Exception as e:
        logger.warning(
            "Failed to record plan doc artifact",
            extra={
                "run_id": run_id,
                "file_path": file_path,
                "action": action,
                "error": str(e),
            },
        )


async def _append_plan_doc_update(
    *,
    run_id: str,
    workspace_path: Optional[str],
    file_path: Optional[str],
    action: str,
    heading: str,
    body: str,
    event_callback: Optional[Any] = None,
) -> None:
    if not workspace_path or not file_path:
        return
    try:
        byte_count = await append_plan_doc_section(
            workspace_path=workspace_path,
            relative_path=file_path,
            heading=heading,
            body=body,
        )
        summary = f"{heading} appended"
        await _record_plan_doc_artifact(
            run_id=run_id,
            file_path=file_path,
            action=action,
            detail=summary,
        )
        if event_callback:
            event_callback(
                _plan_doc_update_event(
                    run_id=run_id,
                    file_path=file_path,
                    action=action,
                    summary=summary,
                    byte_count=byte_count,
                )
            )
        elif run_id in _event_history:
            await _emit_external_run_event(
                run_id,
                _plan_doc_update_event(
                    run_id=run_id,
                    file_path=file_path,
                    action=action,
                    summary=summary,
                    byte_count=byte_count,
                ),
            )
    except Exception as e:
        logger.warning(
            "Failed to append plan doc update",
            extra={
                "run_id": run_id,
                "file_path": file_path,
                "action": action,
                "error": str(e),
            },
        )


async def _record_implementation_plan_progress(
    *,
    run_id: str,
    workspace_path: Optional[str],
    file_path: Optional[str],
    event: Dict[str, Any],
) -> None:
    """Append concise implementation progress derived from existing events."""
    if not workspace_path or not file_path:
        return
    event_type = event.get("type")
    heading: Optional[str] = None
    body: Optional[str] = None
    if event_type == "agent_started":
        heading = "Implementation Progress"
        body = (
            f"- Implementation run id: `{run_id}`\n"
            "- Current phase: started\n"
            "- Status: implementation running"
        )
    elif event_type == "step_started":
        step_number = event.get("step_number")
        heading = "Implementation Progress"
        body = f"- Current phase: step {step_number} started"
    elif event_type == "tool_result":
        tool_name = event.get("tool_name")
        if tool_name not in {"write_file", "edit_file", "apply_patch", "bash", "exec_command"}:
            return
        summary = str(event.get("result_summary") or "").strip()
        success = "passed" if event.get("success") else "failed"
        heading = "Implementation Progress"
        body = (
            f"- Tool: `{tool_name}` {success}\n"
            f"- Outcome: {summary[:500]}"
        )
    elif event_type == "agent_complete":
        result = event.get("result") or {}
        success = bool(result.get("success", True))
        heading = "Final Implementation Status"
        body = (
            f"- Final status: {'succeeded' if success else 'failed'}\n"
            f"- Total steps: {result.get('total_steps', event.get('total_steps', 'unknown'))}\n"
            "- Progress checklist: implementation finished"
        )
    else:
        return

    await _append_plan_doc_update(
        run_id=run_id,
        workspace_path=workspace_path,
        file_path=file_path,
        action="implemented",
        heading=heading,
        body=body,
    )


async def _restore_event_history_from_db(run_id: str) -> int:
    """Restore persisted SSE events into memory for durable replay.

    This lets browser reconnects recover a run timeline even after the
    in-memory history has been cleaned up.
    """
    if _event_history.get(run_id):
        return len(_event_history[run_id])

    try:
        db = await get_db()
        repo = AgentRepo(db)
        rows = await repo.get_run_events(run_id)
    except Exception as e:
        logger.warning(
            "Failed to restore run events",
            extra={"run_id": run_id, "error": str(e)},
        )
        return 0

    restored: List[Dict[str, Any]] = []
    for row in rows:
        event_data = row.get("event_data") or {}
        if isinstance(event_data, dict):
            event = event_data.copy()
            event.setdefault("seq", row.get("seq", 0))
            restored.append(event)

    if restored:
        _event_history[run_id] = restored
        logger.info(
            "Restored run event history",
            extra={"run_id": run_id, "events": len(restored)},
        )
    return len(restored)


async def _cleanup_run(run_id: str, delay_seconds: float = 5.0) -> None:
    """Clean up run state after completion.

    Delays cleanup to allow late-joining SSE clients to receive final events.

    Args:
        run_id: The run ID to clean up.
        delay_seconds: Delay before removing from active_runs.
    """
    await asyncio.sleep(delay_seconds)
    _active_runs.pop(run_id, None)
    _abort_signals.pop(run_id, None)
    _pause_signals.pop(run_id, None)
    _resume_signals.pop(run_id, None)
    _steer_queues.pop(run_id, None)
    _event_notify.pop(run_id, None)
    _run_sessions.pop(run_id, None)
    _run_tasks.pop(run_id, None)
    _approval_queues.pop(run_id, None)
    _plan_approval_queues.pop(run_id, None)
    _pending_plan_approvals.pop(run_id, None)
    _user_input_queues.pop(run_id, None)
    logger.debug("Cleaned up run state", extra={"run_id": run_id})

    # Schedule history cleanup (keep longer for resumption)
    asyncio.create_task(_cleanup_history(run_id, 300.0))


async def _cleanup_history(run_id: str, delay_seconds: float) -> None:
    """Clean up event history after delay.

    Args:
        run_id: The run ID to clean up.
        delay_seconds: Delay before removing history.
    """
    await asyncio.sleep(delay_seconds)
    _event_history.pop(run_id, None)
    _run_tokens.pop(run_id, None)
    logger.debug("Cleaned up event history", extra={"run_id": run_id})


# =============================================================================
# Background task for agent execution
# =============================================================================


async def _run_agent_task(
    run_id: str,
    query: str,
    conversation_id: Optional[str],
    max_steps: int,
    session_id: Optional[str] = None,
    is_owner: bool = False,
    provider_preference: Optional[str] = None,
    model_override: Optional[str] = None,
    filesystem_enabled: bool = False,
    working_dir: Optional[str] = None,
    permission_policy: str = "strict",
    agent_capabilities: Optional[dict] = None,
    reasoning_settings: Optional[ReasoningSettings] = None,
    image_attachments: Optional[list[dict]] = None,
    collaboration_mode: str = "default",
    plan_doc_path: Optional[str] = None,
    source_plan_run_id: Optional[str] = None,
) -> None:
    """Background task that runs the agent.

    Args:
        run_id: Unique run identifier.
        query: User's coding query.
        conversation_id: Optional conversation context.
        max_steps: Maximum steps for agent execution.
        session_id: Optional session ID for provider routing.
        provider_preference: Optional provider preference ("chatgpt" or None).
        model_override: Optional model name override (e.g., "o4-mini").
        filesystem_enabled: If True, register filesystem tools.
        working_dir: Working directory for filesystem tools.
        permission_policy: Permission policy ("strict", "relaxed", "yolo").
        agent_capabilities: Browser-owned tool capabilities for this run.
    """
    # Import here to avoid circular imports
    from orchestrator.agent.factory import create_agent_engine

    abort_signal = _abort_signals.get(run_id)

    if run_id not in _active_runs:
        logger.error("Run not active", extra={"run_id": run_id})
        return

    seq = 0
    failure_message: Optional[str] = None

    def event_callback(event: Dict[str, Any]) -> None:
        """Callback for engine events.

        Appends to the shared event history (append-only log) and notifies
        all SSE generators via the asyncio.Event.  Each generator tracks its
        own read cursor so multiple clients never steal events from each other.
        """
        nonlocal seq
        if abort_signal and abort_signal.is_set():
            return
        if event.get("type") == "plan_approval_required" and plan_doc_path:
            event.setdefault("plan_doc_path", plan_doc_path)
        seq = max(seq, len(_event_history.get(run_id, []))) + 1
        event["seq"] = seq
        _event_history.setdefault(run_id, []).append(event.copy())
        if plan_doc_path and collaboration_mode != "plan":
            asyncio.create_task(
                _record_implementation_plan_progress(
                    run_id=run_id,
                    workspace_path=working_dir,
                    file_path=plan_doc_path,
                    event=event.copy(),
                )
            )
        # Persist event to DB (fire-and-forget)
        asyncio.create_task(_persist_run_event(run_id, seq, event))
        # Wake up all SSE generators waiting for new events
        notify = _event_notify.get(run_id)
        if notify:
            notify.set()

    try:
        # Resolve provider override — check local model first
        from orchestrator.providers.factory import get_provider_override

        if collaboration_mode == "plan" and working_dir and plan_doc_path:
            event_callback(
                _plan_doc_update_event(
                    run_id=run_id,
                    file_path=plan_doc_path,
                    action="created",
                    summary="Created durable Plan Mode document",
                )
            )
        elif collaboration_mode != "plan" and working_dir and plan_doc_path:
            await _record_plan_doc_artifact(
                run_id=run_id,
                file_path=plan_doc_path,
                action="implemented",
                detail=(
                    "Implementation run linked to approved plan"
                    + (f" from {source_plan_run_id}" if source_plan_run_id else "")
                ),
            )

        provider_override = get_provider_override()
        from orchestrator.routes.auth import get_chatgpt_auth_session_id

        auth_session_id = get_chatgpt_auth_session_id(session_id=session_id, is_owner=is_owner)

        if provider_override is not None:
            pass  # Local model is active, use it
        elif auth_session_id and provider_preference == "chatgpt":
            # ChatGPT path: use stored OAuth tokens
            try:
                from orchestrator.providers.factory import create_chatgpt_provider
                from orchestrator.routes.auth import get_valid_tokens

                tokens = await get_valid_tokens(auth_session_id)
                if tokens:
                    provider_override = create_chatgpt_provider(
                        tokens,
                        model=model_override,
                        auth_session_id=auth_session_id,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to create ChatGPT provider for agent",
                    extra={"error": str(e)},
                )
        elif model_override:
            # Model registry path: resolve alias to provider + full model ID.
            # Preserve the explicit provider selected in the UI; otherwise IDs
            # like grok:grok-build can silently fall through to the default
            # Fireworks provider when Grok auth is unavailable.
            selection = _registry_selection(provider_preference, model_override)
            try:
                from orchestrator.providers.factory import create_provider_for_model

                provider_override, resolved = create_provider_for_model(selection)
                model_override = resolved.model_id  # Replace alias with full ID
            except (ValueError, Exception) as e:
                logger.warning(
                    "Failed to resolve selected model via registry",
                    extra={
                        "provider": provider_preference,
                        "model": model_override,
                        "selection": selection,
                        "error": str(e),
                    },
                )
                raise RuntimeError(f"Failed to use selected model {selection}: {e}") from e
        elif not model_override and not provider_preference:
            # Web UI fallback: use the last model selected via picker
            from orchestrator.routes.models import get_active_model, get_active_model_name

            active_model = get_active_model()
            active_name = get_active_model_name()
            if active_model and active_model.provider_name == "chatgpt" and auth_session_id:
                try:
                    from orchestrator.providers.factory import create_chatgpt_provider
                    from orchestrator.routes.auth import get_valid_tokens

                    tokens = await get_valid_tokens(auth_session_id)
                    if tokens:
                        provider_override = create_chatgpt_provider(
                            tokens,
                            model=active_model.model_id,
                            auth_session_id=auth_session_id,
                        )
                        model_override = active_model.model_id
                except Exception as e:
                    logger.warning(
                        "Failed to create active ChatGPT provider for agent",
                        extra={"error": str(e)},
                    )
            elif active_name and not (active_model and active_model.provider_name == "chatgpt"):
                try:
                    from orchestrator.providers.factory import create_provider_for_model

                    provider_override, resolved = create_provider_for_model(active_name)
                    model_override = resolved.model_id
                except Exception as e:
                    logger.warning(
                        "Failed to resolve active model via registry, using default",
                        extra={"model": active_name, "error": str(e)},
                    )

        # Build approval callback for permission system
        async def approval_callback(
            rid: str, tool_call_id: str, tool_name: str, arguments: dict
        ) -> bool:
            """Wait for user to approve/deny a tool call."""
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            _approval_queues.setdefault(rid, {})[tool_call_id] = future
            try:
                return await asyncio.wait_for(future, timeout=300)  # 5 min timeout
            except asyncio.TimeoutError:
                logger.warning(
                    "Tool approval timed out",
                    extra={
                        "run_id": rid,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "timeout_seconds": 300,
                    },
                )
                return False
            finally:
                _approval_queues.get(rid, {}).pop(tool_call_id, None)

        async def plan_approval_callback(
            rid: str, plan_id: str, markdown: str
        ) -> PlanDecision:
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            _plan_approval_queues.setdefault(rid, {})[plan_id] = future
            _pending_plan_approvals.setdefault(rid, {})[plan_id] = {
                "plan_id": plan_id,
                "markdown": markdown,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "plan_doc_path": plan_doc_path,
                "workspace_path": working_dir,
            }
            try:
                result = await asyncio.wait_for(future, timeout=1800)
                if isinstance(result, PlanDecision):
                    return result
                return PlanDecision(**result)
            except asyncio.TimeoutError:
                logger.warning(
                    "Plan approval timed out",
                    extra={"run_id": rid, "plan_id": plan_id, "timeout_seconds": 1800},
                )
                return PlanDecision(decision="rejected", feedback="Plan approval timed out.")
            finally:
                _plan_approval_queues.get(rid, {}).pop(plan_id, None)
                _pending_plan_approvals.get(rid, {}).pop(plan_id, None)

        async def user_input_callback(questions: list[dict[str, Any]]) -> dict[str, Any]:
            request_id = str(uuid.uuid4())
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            _user_input_queues.setdefault(run_id, {})[request_id] = future
            event_callback(
                {
                    "type": "user_input_required",
                    "run_id": run_id,
                    "request_id": request_id,
                    "questions": questions,
                }
            )
            try:
                result = await asyncio.wait_for(future, timeout=1800)
                return result if isinstance(result, dict) else {}
            except asyncio.TimeoutError:
                return {}
            finally:
                _user_input_queues.get(run_id, {}).pop(request_id, None)

        # Create engine and run
        engine = await create_agent_engine(
            model_name=model_override,
            max_steps=max_steps,
            query=query,
            provider_override=provider_override,
            filesystem_enabled=filesystem_enabled,
            working_dir=working_dir,
            approval_callback=approval_callback if permission_policy != "yolo" else None,
            permission_policy=permission_policy,
            agent_capabilities=agent_capabilities,
            reasoning_settings=reasoning_settings,
            collaboration_mode=collaboration_mode,
            plan_approval_callback=(
                plan_approval_callback if collaboration_mode == "plan" else None
            ),
            user_input_callback=(
                user_input_callback if collaboration_mode == "plan" else None
            ),
            plan_doc_relative_path=plan_doc_path if collaboration_mode == "plan" else None,
            run_id=run_id,
        )
        db = await get_db()
        trace_repo = TraceRepo(db)
        await trace_repo.update_run(
            run_id,
            usage_stats={
                "context_profile": engine._context_profile_dict(),
                "compaction_count": 0,
                "last_compacted_at_step": None,
                "stored_context": None,
            },
        )

        result = await engine.run(
            run_id=run_id,
            query=query,
            event_callback=event_callback,
            conversation_id=conversation_id,
            pause_signal=_pause_signals.get(run_id),
            resume_signal=_resume_signals.get(run_id),
            steer_queue=_steer_queues.get(run_id),
            image_attachments=image_attachments,
        )

        if abort_signal and not abort_signal.is_set():
            end_event = {
                "type": "_STREAM_END",
                "result": {
                    "run_id": result.run_id,
                    "success": result.success,
                    "final_answer": result.final_answer,
                    "error_message": result.error_message,
                    "citations": result.citations,
                    "total_steps": result.total_steps,
                    "timing_ms": result.timing_ms,
                    "total_tokens": result.total_tokens,
                    "usage": result.usage,
                    "cost": result.cost,
                    "approved_plan": result.approved_plan,
                    "implementation_run_id": result.implementation_run_id,
                    "implementation_stream_token": result.implementation_stream_token,
                    "context_usage": result.context_usage,
                    "stored_context": result.stored_context,
                    "context_profile": result.context_profile,
                    "compaction_count": result.compaction_count,
                    "last_compacted_at_step": result.last_compacted_at_step,
                },
            }
            _event_history.setdefault(run_id, []).append(end_event)
            notify = _event_notify.get(run_id)
            if notify:
                notify.set()
    except BaseException as e:
        error_text = _format_background_error(e)
        failure_message = error_text
        cancelled_after_abort = isinstance(e, asyncio.CancelledError) and bool(
            abort_signal and abort_signal.is_set()
        )
        if cancelled_after_abort:
            logger.info(
                "Agent run task cancelled after user stop",
                extra={"run_id": run_id},
            )
        else:
            logger.error(
                "Agent run failed",
                extra={"run_id": run_id, "error": error_text},
                exc_info=True,
            )
        if abort_signal is None or not abort_signal.is_set():
            err_event = {"type": "_STREAM_ERROR", "error": error_text}
            _event_history.setdefault(run_id, []).append(err_event)
            notify = _event_notify.get(run_id)
            if notify:
                notify.set()
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        try:
            db = await get_db()
            cursor = await db.conn.execute(
                "SELECT status FROM runs WHERE run_id = ?", (run_id,)
            )
            row = await cursor.fetchone()
            if row and row[0] == "running":
                error_detail = failure_message or "Run did not complete — process interrupted"
                await db.conn.execute(
                    "UPDATE runs SET status = 'failed', error_message = ? WHERE run_id = ? AND status = 'running'",
                    (error_detail, run_id),
                )
                await db.conn.commit()
                logger.warning(
                    "Safety net: marked orphaned run as failed",
                    extra={"run_id": run_id, "error": error_detail},
                )
        except Exception:
            pass
        asyncio.create_task(_cleanup_run(run_id))


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/runs", response_model=CreateAgentRunResponse)
async def create_agent_run(request: CreateAgentRunRequest, http_request: Request):
    """Start a new browser coding agent run.

    The agent executes asynchronously in a background task.
    Use the stream endpoint to receive real-time events.

    Returns:
        run_id and stream_url for SSE events.
    """
    session_id, is_owner = get_session_context(http_request)

    # Check per-session message limit
    if not is_owner and session_id:
        from orchestrator.config import get_chat_config as _get_config
        from orchestrator.storage.db import get_db as _get_db

        _cfg = _get_config()
        if _cfg.demo and _cfg.demo.enabled:
            _limit = int(getattr(_cfg.demo, "message_limit", 10) or 10)
            if _limit > 0:
                _db = await _get_db()
                _cursor = await _db.conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE session_id = ?", (session_id,)
                )
                _row = await _cursor.fetchone()
                if (_row[0] if _row else 0) >= _limit:
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            f"Message limit reached. You can send {_limit} messages per session."
                        ),
                    )

    run_id = str(uuid.uuid4())
    collaboration_mode = normalize_collaboration_mode(request.collaboration_mode)
    plan_doc_path: Optional[str] = None

    try:
        # Initialize state
        abort_signal = asyncio.Event()

        _active_runs[run_id] = True
        _abort_signals[run_id] = abort_signal
        _pause_signals[run_id] = asyncio.Event()
        _resume_signals[run_id] = asyncio.Event()
        _steer_queues[run_id] = []
        _event_history[run_id] = []
        _event_notify[run_id] = asyncio.Event()
        stream_token = secrets.token_urlsafe(16)
        _run_tokens[run_id] = stream_token

        # Track session for access control
        if session_id:
            _run_sessions[run_id] = session_id

        # Create run record in database
        db = await get_db()
        trace_repo = TraceRepo(db)

        # Import ConversationRepo for creating ephemeral conversations
        from orchestrator.storage.repositories.conversation_repo import ConversationRepo

        conv_repo = ConversationRepo(db)

        # Generate conversation_id if not provided, and create ephemeral conversation
        conversation_id = request.conversation_id
        workspace_path: Optional[str] = None
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            # Create ephemeral conversation for standalone agent runs
            title = conversation_title_from_message(request.query)
            requested_workspace = request.workspace_path or request.working_dir
            workspace = (
                _resolve_workspace_path(requested_workspace) if requested_workspace else None
            )
            if workspace is not None:
                ensure_fluxion_gitignore(workspace)
            workspace_path = str(workspace) if workspace is not None else None
            await conv_repo.create(
                conversation_id=conversation_id,
                title=title,
                workspace_path=workspace_path,
                session_id=session_id,
            )
        else:
            # Verify ownership of existing conversation
            conversation = await conv_repo.get_with_session_check(
                conversation_id,
                session_id=session_id,
                is_owner=is_owner,
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            workspace_path = conversation.get("workspace_path")
            if workspace_path:
                ensure_fluxion_gitignore(Path(workspace_path))
            if not conversation.get("title") or conversation.get("title") == "New conversation":
                await conv_repo.update(
                    conversation_id=conversation_id,
                    title=conversation_title_from_message(request.query),
                )

        await capture_rewind_checkpoint(
            conversation={
                "conversation_id": conversation_id,
                "workspace_path": workspace_path,
            },
            run_id=run_id,
            user_message=request.query,
            conversation_repo=conv_repo,
            agent_repo=AgentRepo(db),
        )

        capabilities = request.capabilities.model_dump()
        capabilities["command"] = bool(
            capabilities.get("command") or capabilities.pop("bash", False)
        )
        if workspace_path and request.filesystem_enabled:
            capabilities["filesystem"] = True
        reasoning_settings, _, _ = await get_runtime_reasoning_settings()

        provider_preference = http_request.headers.get("x-provider")
        model_override = http_request.headers.get("x-model")

        # Create model config snapshot for agent
        model_config = {
            "mode": "agent",
            "max_steps": request.max_steps,
            "workspace_path": workspace_path,
            "capabilities": capabilities,
            "permission_policy": request.permission_policy,
            "collaboration_mode": collaboration_mode,
            "reasoning_settings": reasoning_settings.model_dump(),
            "image_attachments_count": len(request.image_attachments),
            "selected_provider": provider_preference,
            "selected_model": model_override,
            "plan_doc_path": request.plan_doc_path,
            "source_plan_run_id": request.source_plan_run_id,
        }
        if collaboration_mode == "plan" and workspace_path:
            plan_doc_path = plan_doc_relative_path(run_id)
            model_config["plan_doc_path"] = plan_doc_path

        await trace_repo.create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            mode="agent",
            profile_name="agent",
            model_config=model_config,
            user_message=request.query,
            session_id=session_id,
            collaboration_mode=collaboration_mode,
        )

        # Update agent-specific fields
        agent_repo = AgentRepo(db)
        await agent_repo.update_run_agent_state(
            run_id=run_id,
            agent_state="initializing",
            current_step=0,
            max_steps=request.max_steps,
        )
        if collaboration_mode == "plan" and workspace_path and plan_doc_path:
            created_path, byte_count = await create_initial_plan_doc(
                workspace_path=workspace_path,
                plan_run_id=run_id,
                original_request=request.query,
            )
            plan_doc_path = created_path
            await agent_repo.create_run_artifact(
                run_id=run_id,
                artifact_type="plan_doc",
                file_path=plan_doc_path,
                action="created",
                detail=f"Created durable Plan Mode document ({byte_count} bytes)",
            )

        # Start background task (pass provider/model preference from headers)
        task = asyncio.create_task(
            _run_agent_task(
                run_id=run_id,
                query=request.query,
                conversation_id=conversation_id,
                max_steps=request.max_steps,
                session_id=session_id,
                is_owner=is_owner,
                provider_preference=provider_preference,
                model_override=model_override,
                filesystem_enabled=capabilities.get("filesystem", False),
                working_dir=workspace_path,
                permission_policy=request.permission_policy,
                agent_capabilities=capabilities,
                reasoning_settings=reasoning_settings,
                image_attachments=request.image_attachments,
                collaboration_mode=collaboration_mode,
                plan_doc_path=plan_doc_path or request.plan_doc_path,
                source_plan_run_id=request.source_plan_run_id,
            )
        )
        _run_tasks[run_id] = task

        logger.info(
            "Agent run started",
            extra={
                "run_id": run_id,
                "query_length": len(request.query),
                "max_steps": request.max_steps,
                "collaboration_mode": collaboration_mode,
            },
        )

        return CreateAgentRunResponse(
            run_id=run_id,
            status="running",
            stream_url=f"/api/agent/runs/{run_id}/stream?token={stream_token}",
            stream_token=stream_token,
            conversation_id=conversation_id,
        )

    except HTTPException:
        # Clean up on HTTP error (like 404)
        _active_runs.pop(run_id, None)
        _abort_signals.pop(run_id, None)
        _event_history.pop(run_id, None)
        _event_notify.pop(run_id, None)
        _run_tokens.pop(run_id, None)
        _run_sessions.pop(run_id, None)
        _run_tasks.pop(run_id, None)
        _plan_approval_queues.pop(run_id, None)
        _pending_plan_approvals.pop(run_id, None)
        _user_input_queues.pop(run_id, None)
        raise
    except Exception as e:
        # Clean up on failure
        _active_runs.pop(run_id, None)
        _abort_signals.pop(run_id, None)
        _event_history.pop(run_id, None)
        _event_notify.pop(run_id, None)
        _run_tokens.pop(run_id, None)
        _run_sessions.pop(run_id, None)
        _run_tasks.pop(run_id, None)
        _plan_approval_queues.pop(run_id, None)
        _pending_plan_approvals.pop(run_id, None)
        _user_input_queues.pop(run_id, None)
        logger.error("Failed to start agent run", extra={"error": str(e)}, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start agent run")


@router.get("/runs/{run_id}", response_model=AgentRunStatusResponse)
async def get_agent_run_status(run_id: str, http_request: Request):
    """Get current status of an agent run.

    Returns run metadata, current state, step count, and result if complete.
    """
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)

    # Get run from trace_repo with session check
    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Determine status
    is_active = run_id in _active_runs
    base_status = run.get("status", "unknown")
    status = "running" if is_active else base_status

    # total_steps is the final step count when run completes
    current_step = run.get("current_step", 0)
    total_steps = current_step if status in ("succeeded", "failed") else None
    usage_stats = run.get("usage") or {}

    return AgentRunStatusResponse(
        run_id=run_id,
        status=status,
        agent_state=run.get("agent_state"),
        current_step=current_step,
        total_steps=total_steps,
        max_steps=run.get("max_steps", 1000),
        final_answer=run.get("final_answer"),
        error_message=run.get("error_message"),
        usage=usage_stats.get("usage"),
        cost=usage_stats.get("cost"),
        context_usage=usage_stats.get("context_usage"),
        stored_context=usage_stats.get("stored_context"),
        context_profile=usage_stats.get("context_profile"),
        compaction_count=usage_stats.get("compaction_count", 0),
        last_compacted_at_step=usage_stats.get("last_compacted_at_step"),
        created_at=run.get("created_at", ""),
        updated_at=run.get("updated_at"),
        collaboration_mode=normalize_collaboration_mode(run.get("collaboration_mode")),
    )


@router.get("/runs/{run_id}/stream")
async def stream_agent_events(
    run_id: str,
    http_request: Request,
    since_seq: int = Query(0, description="Resume from this sequence number"),
    token: str = Query("", description="Stream auth token from run creation"),
):
    """Stream agent events via Server-Sent Events.

    Supports resumption via since_seq parameter for reconnection.
    Requires stream token for active runs (returned by POST /runs).
    Sends heartbeat every 30 seconds during idle.
    """
    session_id, is_owner = get_session_context(http_request)

    # Validate stream token: reject only if a non-empty token is provided but wrong.
    # Empty token is allowed as fallback for reconnection (e.g. page reload where
    # localStorage may not have persisted the token).
    expected_token = _run_tokens.get(run_id)
    if token and expected_token and token != expected_token:
        raise HTTPException(status_code=403, detail="Invalid stream token")

    # Session-based access control for active runs
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    # For completed runs, check DB
    if run_id not in _active_runs:
        db = await get_db()
        trace_repo = TraceRepo(db)
        run = await trace_repo.get_run_with_session_check(
            run_id,
            session_id=session_id,
            is_owner=is_owner,
        )
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

    await _restore_event_history_from_db(run_id)

    # Capture parent request ID for SSE context
    parent_request_id = get_request_id()

    async def event_generator():
        """Cursor-based SSE generator.

        Each SSE client maintains its own read cursor into the shared
        append-only event history.  This allows multiple concurrent clients
        (e.g. reconnects, React StrictMode double-mount) to each receive
        ALL events without stealing from each other.
        """
        # Restore request context in generator
        if parent_request_id:
            set_request_id(parent_request_id)
        set_component("agent-sse")

        chunk_count = 0
        stream_start = time.time()
        cursor = 0  # Index into _event_history[run_id]

        logger.info(
            "Agent SSE stream opened",
            extra={"run_id": run_id, "since_seq": since_seq},
        )

        try:
            while True:
                # Read any new events from history since our cursor
                history = _event_history.get(run_id, [])
                new_events = history[cursor:]
                cursor = len(history)

                for event in new_events:
                    event_type = event.get("type", "")

                    # Terminal events
                    if event_type == "_STREAM_END":
                        duration_ms = int((time.time() - stream_start) * 1000)
                        logger.info(
                            "Agent SSE stream completed",
                            extra={
                                "run_id": run_id,
                                "chunk_count": chunk_count,
                                "duration_ms": duration_ms,
                            },
                        )
                        yield {
                            "event": "complete",
                            "data": json.dumps(event.get("result", {})),
                        }
                        return
                    elif event_type == "_STREAM_ERROR":
                        logger.error(
                            "Agent SSE stream error",
                            extra={
                                "run_id": run_id,
                                "error": event.get("error"),
                                "chunk_count": chunk_count,
                            },
                        )
                        yield {
                            "event": "error",
                            "data": json.dumps({"error": "Internal server error"}),
                        }
                        return
                    elif event_type == "_STREAM_ABORTED":
                        logger.warning(
                            "Agent SSE stream aborted",
                            extra={"run_id": run_id, "chunk_count": chunk_count},
                        )
                        yield {
                            "event": "cancelled",
                            "data": json.dumps({"run_id": run_id}),
                        }
                        return

                    # Normal events — skip if already seen by this client
                    event_seq = event.get("seq", 0)
                    if event_seq > since_seq:
                        chunk_count += 1
                        yield _translate_event(event, event_seq)

                # If run is no longer active and we've drained all events, exit
                if run_id not in _active_runs:
                    # Check DB for completed run as fallback
                    db = await get_db()
                    trace_repo = TraceRepo(db)
                    run = await trace_repo.get_run(run_id)
                    if run:
                        status = run.get("status", "unknown")
                        if status in ("succeeded", "failed", "cancelled", "interrupted"):
                            usage = run.get("usage") or {}
                            yield {
                                "event": "complete",
                                "data": json.dumps(
                                    {
                                        "run_id": run_id,
                                        "success": status == "succeeded",
                                        "status": status,
                                        "final_answer": run.get("final_answer"),
                                        "error_message": run.get("error_message"),
                                        "total_tokens": usage.get("total_tokens"),
                                        "usage": usage,
                                        "context_usage": usage.get("context_usage"),
                                        "context_profile": usage.get("context_profile"),
                                        "compaction_count": usage.get("compaction_count", 0),
                                        "last_compacted_at_step": usage.get("last_compacted_at_step"),
                                        "cost": usage.get("cost"),
                                    }
                                ),
                            }
                    return

                # Wait for new events (or heartbeat timeout).
                # Clear before waiting so we don't miss events added
                # between our history read and the wait() call — any event
                # added after clear() will re-set() the flag, waking us.
                notify = _event_notify.get(run_id)
                if notify:
                    notify.clear()
                    # Double-check for events added between read and clear
                    if len(_event_history.get(run_id, [])) > cursor:
                        continue
                    try:
                        await asyncio.wait_for(notify.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        yield {"event": "heartbeat", "data": "{}"}
                else:
                    # No notify event means run cleaned up; exit
                    return

        except asyncio.CancelledError:
            duration_ms = int((time.time() - stream_start) * 1000)
            logger.warning(
                "Agent SSE stream client disconnected",
                extra={
                    "run_id": run_id,
                    "chunk_count": chunk_count,
                    "duration_ms": duration_ms,
                },
            )
            raise

    return EventSourceResponse(event_generator())


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str, http_request: Request):
    """Cancel an active agent run.

    Signals the background task to stop, drains the queue,
    and sends a cancelled event to SSE clients.
    """
    session_id, is_owner = get_session_context(http_request)

    # Verify session ownership for active runs
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        db = await get_db()
        trace_repo = TraceRepo(db)
        run = await trace_repo.get_run_with_session_check(
            run_id,
            session_id=session_id,
            is_owner=is_owner,
        )
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        status = run.get("status") or "unknown"
        if status in {"cancelled", "succeeded", "failed"}:
            return {"run_id": run_id, "status": status}
        await _mark_run_cancelled(run_id)
        return {"run_id": run_id, "status": "cancelled"}

    # Signal abort
    if run_id in _abort_signals:
        _abort_signals[run_id].set()

    _resolve_pending_run_waiters(run_id)

    try:
        await _mark_run_cancelled(run_id)
    except Exception as e:
        logger.error(
            "Failed to update run status on cancel",
            extra={"run_id": run_id, "error": str(e)},
        )

    # Signal cancellation to SSE clients via a normal event, then a terminal event.
    await _emit_external_run_event(
        run_id,
        {
            "type": "run_cancelled",
            "run_id": run_id,
            "status": "cancelled",
            "reason": "Stopped by user",
        },
    )
    await _emit_external_run_event(run_id, {"type": "_STREAM_ABORTED"})
    _active_runs.pop(run_id, None)
    asyncio.create_task(_cancel_run_task_later(run_id))

    logger.info("Agent run cancelled", extra={"run_id": run_id})

    return {"run_id": run_id, "status": "cancelled"}


@router.post("/runs/{run_id}/pause")
async def pause_agent_run(run_id: str, http_request: Request):
    """Pause an active agent run after the current step completes."""
    session_id, is_owner = get_session_context(http_request)

    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    pause_signal = _pause_signals.get(run_id)
    if not pause_signal:
        raise HTTPException(status_code=404, detail="Run not found")

    pause_signal.set()
    logger.info("Agent run pause requested", extra={"run_id": run_id})

    return {"run_id": run_id, "status": "pausing"}


@router.post("/runs/{run_id}/resume")
async def resume_agent_run(run_id: str, http_request: Request):
    """Resume a paused agent run."""
    session_id, is_owner = get_session_context(http_request)

    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    resume_signal = _resume_signals.get(run_id)
    if not resume_signal:
        raise HTTPException(status_code=404, detail="Run not found")

    resume_signal.set()
    logger.info("Agent run resume requested", extra={"run_id": run_id})

    return {"run_id": run_id, "status": "resuming"}


@router.post("/runs/{run_id}/steer")
async def steer_agent_run(run_id: str, http_request: Request):
    """Inject a steering message into a running agent.

    The message is queued and injected before the next LLM call.
    Works whether the agent is running or paused.
    """
    session_id, is_owner = get_session_context(http_request)

    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    queue = _steer_queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Run not found")

    body = await http_request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    queue.append(message)
    logger.info(
        "Steering message queued",
        extra={"run_id": run_id, "queue_size": len(queue), "message_preview": message[:80]},
    )

    return {"run_id": run_id, "status": "queued", "queue_size": len(queue)}


@router.post("/runs/{run_id}/plan/reject", response_model=PlanApprovalResponse)
async def reject_agent_plan(
    run_id: str,
    request: PlanRejectRequest,
    http_request: Request,
):
    """Reject a pending Plan Mode proposal and keep the same run planning."""
    session_id, is_owner = get_session_context(http_request)
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    future = _plan_approval_queues.get(run_id, {}).get(request.plan_id)
    pending = _pending_plan_approvals.get(run_id, {}).get(request.plan_id)
    if future is None or future.done():
        raise HTTPException(status_code=404, detail="Pending plan approval not found")

    if pending:
        feedback = (request.feedback or "").strip() or "No specific feedback provided."
        await _append_plan_doc_update(
            run_id=run_id,
            workspace_path=pending.get("workspace_path"),
            file_path=pending.get("plan_doc_path"),
            action="rejected",
            heading="Plan Rejected",
            body=(
                f"- Plan id: `{request.plan_id}`\n"
                f"- Feedback: {feedback}\n"
                "- Status: continue planning and revise the plan."
            ),
        )

    future.set_result(
        PlanDecision(decision="rejected", feedback=(request.feedback or "").strip())
    )
    return PlanApprovalResponse(
        status="rejected",
        run_id=run_id,
        plan_id=request.plan_id,
    )


@router.post("/runs/{run_id}/plan/approve", response_model=PlanApprovalResponse)
async def approve_agent_plan(
    run_id: str,
    request: PlanApprovalRequest,
    http_request: Request,
):
    """Approve a Plan Mode proposal and start a Default Mode implementation run."""
    session_id, is_owner = get_session_context(http_request)
    db = await get_db()
    trace_repo = TraceRepo(db)
    original_run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not original_run:
        raise HTTPException(status_code=404, detail="Run not found")

    future = _plan_approval_queues.get(run_id, {}).get(request.plan_id)
    pending = _pending_plan_approvals.get(run_id, {}).get(request.plan_id)
    if future is None or future.done() or not pending:
        raise HTTPException(status_code=404, detail="Pending plan approval not found")

    plan_markdown = pending.get("markdown", "")
    plan_doc_path = pending.get("plan_doc_path")
    workspace_path = pending.get("workspace_path")
    await _append_plan_doc_update(
        run_id=run_id,
        workspace_path=workspace_path,
        file_path=plan_doc_path,
        action="approved",
        heading="Approved Plan",
        body=(
            f"- Plan id: `{request.plan_id}`\n"
            "- Status: approved for implementation\n\n"
            f"{plan_markdown}"
        ),
    )
    model_config = original_run.get("model_config") or {}
    implementation_request = CreateAgentRunRequest(
        query=build_plan_implementation_prompt(plan_markdown, plan_doc_path),
        conversation_id=original_run.get("conversation_id"),
        max_steps=int(model_config.get("max_steps") or 1000),
        workspace_path=model_config.get("workspace_path"),
        filesystem_enabled=bool(model_config.get("workspace_path")),
        capabilities=model_config.get("capabilities") or {},
        permission_policy=model_config.get("permission_policy") or "strict",
        collaboration_mode="default",
        plan_doc_path=plan_doc_path,
        source_plan_run_id=run_id,
    )
    implementation = await create_agent_run(implementation_request, http_request)
    decision = PlanDecision(
        decision="approved",
        implementation_run_id=implementation.run_id,
        implementation_stream_token=implementation.stream_token,
    )
    future.set_result(decision)
    return PlanApprovalResponse(
        status="approved",
        run_id=run_id,
        plan_id=request.plan_id,
        implementation_run_id=implementation.run_id,
        implementation_stream_token=implementation.stream_token,
        implementation_stream_url=implementation.stream_url,
    )


@router.post("/runs/{run_id}/input/{request_id}")
async def answer_user_input(
    run_id: str,
    request_id: str,
    request: UserInputResponseRequest,
    http_request: Request,
):
    """Answer a pending Plan Mode request_user_input prompt."""
    session_id, is_owner = get_session_context(http_request)
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    future = _user_input_queues.get(run_id, {}).get(request_id)
    if future is None or future.done():
        raise HTTPException(status_code=404, detail="Pending user input not found")
    future.set_result(request.answers)
    return {"run_id": run_id, "request_id": request_id, "status": "answered"}


@router.get("/runs/{run_id}/artifacts/read")
async def read_run_artifact(
    run_id: str,
    http_request: Request,
    artifact_path: str = Query(..., description="Workspace-relative artifact path"),
    offset: int = Query(1, ge=1),
    limit: int = Query(200, ge=1, le=1000),
):
    """Read a current-run text artifact from `.fluxion/runs/<run_id>`."""
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)
    conversation_repo = ConversationRepo(db)

    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    conversation_id = run.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=404, detail="Run workspace not found")
    conversation = await conversation_repo.get(conversation_id)
    workspace_path = conversation.get("workspace_path") if conversation else None
    if not workspace_path:
        raise HTTPException(status_code=404, detail="Run workspace not found")

    try:
        manager = AgentArtifactManager(workspace_path, run_id)
        return manager.read_text_artifact(artifact_path, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/trace", response_model=AgentRunTraceResponse)
async def get_agent_run_trace(run_id: str, http_request: Request):
    """Get full execution trace for an agent run.

    Returns all steps, tool calls, and citations for detailed analysis.
    """
    session_id, is_owner = get_session_context(http_request)

    db = await get_db()
    trace_repo = TraceRepo(db)
    agent_repo = AgentRepo(db)

    # Get base run info with session check
    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get all steps
    steps_raw = await agent_repo.get_steps_for_run(run_id)
    steps = [
        AgentStepResponse(
            id=s["id"],  # DB column is 'id', not 'step_id'
            run_id=s["run_id"],
            step_number=s["step_number"],
            state=s["state"],
            thinking_text=s.get("thinking_text"),  # DB column is 'thinking_text'
            decision=s.get("decision"),
            created_at=s["created_at"],
            completed_at=s.get("completed_at"),
            error_message=s.get("error_message"),
        )
        for s in steps_raw
    ]

    # Get all artifacts before tool-call hydration so command/web artifact refs
    # survive even if the stored tool result JSON was truncated.
    artifacts_raw = await agent_repo.get_run_artifacts(run_id)
    artifacts_by_tool_call: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts_raw:
        tool_call_id = artifact.get("tool_call_id")
        if tool_call_id and artifact.get("artifact_path"):
            artifacts_by_tool_call.setdefault(tool_call_id, []).append(
                {
                    "artifact_type": artifact.get("artifact_type"),
                    "artifact_path": artifact.get("artifact_path"),
                    "file_path": artifact.get("file_path"),
                    "content_type": artifact.get("content_type"),
                    "byte_count": artifact.get("byte_count"),
                    "sha256": artifact.get("sha256"),
                    "detail": artifact.get("detail"),
                    "metadata": artifact.get("metadata"),
                }
            )

    # Get all tool calls
    tool_calls_raw = await agent_repo.get_tool_calls_for_run(run_id)
    tool_calls = []
    for tc in tool_calls_raw:
        tool_name = tc["tool_name"]
        stored_result_data = parse_stored_result_detail(tc.get("result_detail"))
        stored_artifacts = (
            stored_result_data.get("artifacts", [])
            if isinstance(stored_result_data, dict)
            else []
        )
        tool_calls.append(
            AgentToolCallResponse(
                id=tc["id"],  # DB column is 'id', not 'tool_call_id'
                run_id=tc["run_id"],
                step_id=tc["step_id"],
                tool_name=tool_name,
                arguments=(
                    tc.get("arguments", {})
                    if isinstance(tc.get("arguments"), dict)
                    else json.loads(tc.get("arguments", "{}"))
                ),
                status=tc["status"],
                result_summary=tc.get("result_summary"),
                error_message=tc.get("error_message"),
                duration_ms=tc.get("duration_ms"),
                created_at=tc["created_at"],
                started_at=tc.get("started_at"),
                completed_at=tc.get("completed_at"),
                idempotency_key=tc.get("idempotency_key", ""),
                execution_attempt=tc.get("execution_attempt", 1),
                approval_decision=tc.get("approval_decision"),
                approval_policy=tc.get("approval_policy"),
                approval_decided_at=tc.get("approval_decided_at"),
                result_detail=tc.get("result_detail"),
                result_data=display_result_data(tool_name, stored_result_data),
                bash_output=(
                    bash_output_from_result_data(stored_result_data)
                    if tool_name in {"bash", "exec_command", "write_stdin"}
                    else None
                ),
                artifacts=artifacts_by_tool_call.get(
                    tc["id"],
                    stored_artifacts if isinstance(stored_artifacts, list) else [],
                ),
            )
        )

    # Get all citations
    citations_raw = await agent_repo.get_citations_for_run(run_id)
    citations = [
        AgentCitationResponse(
            id=c["id"],  # DB column is 'id', not 'citation_id'
            run_id=c["run_id"],
            tool_call_id=c.get("tool_call_id", ""),
            source_url=c["source_url"],
            title=c.get("title"),
            snippet=c.get("snippet", ""),
            used_in_answer=bool(c.get("used_in_answer", False)),
            created_at=c["created_at"],
        )
        for c in citations_raw
    ]

    # Get all artifacts
    artifacts = [
        RunArtifactResponse(
            id=a["id"],
            run_id=a["run_id"],
            artifact_type=a["artifact_type"],
            file_path=a.get("file_path"),
            action=a["action"],
            detail=a.get("detail"),
            tool_call_id=a.get("tool_call_id"),
            artifact_path=a.get("artifact_path"),
            byte_count=a.get("byte_count"),
            sha256=a.get("sha256"),
            content_type=a.get("content_type"),
            metadata=a.get("metadata"),
            created_at=a["created_at"],
        )
        for a in artifacts_raw
    ]

    usage_stats = run.get("usage") or {}
    run_events = await agent_repo.get_run_events(run_id)
    system_events = [
        {
            "event_type": "conversation_compacted",
            "message": (event.get("event_data") or {}).get(
                "message", "Conversation compacted to preserve context window"
            ),
            "step_number": (event.get("event_data") or {}).get("step_number"),
            "seq": event.get("seq"),
            "created_at": event.get("created_at"),
        }
        for event in run_events
        if event.get("event_type") == "conversation_compacted"
    ]
    assistant_updates = []
    for event in run_events:
        if event.get("event_type") != "assistant_update":
            continue
        data = event.get("event_data") or {}
        content = data.get("content")
        if not content:
            continue
        assistant_updates.append(
            AgentAssistantUpdateResponse(
                content=content,
                step_number=data.get("step_number"),
                seq=event.get("seq"),
                created_at=event.get("created_at"),
            )
        )

    return AgentRunTraceResponse(
        run_id=run_id,
        status=run.get("status", "unknown"),
        agent_state=run.get("agent_state"),
        steps=steps,
        tool_calls=tool_calls,
        citations=citations,
        artifacts=artifacts,
        system_events=system_events,
        assistant_updates=assistant_updates,
        final_answer=run.get("final_answer"),
        collaboration_mode=normalize_collaboration_mode(run.get("collaboration_mode")),
        usage=usage_stats.get("usage"),
        cost=usage_stats.get("cost"),
        context_usage=usage_stats.get("context_usage"),
        stored_context=usage_stats.get("stored_context"),
        context_profile=usage_stats.get("context_profile"),
        compaction_count=usage_stats.get("compaction_count", 0),
        last_compacted_at_step=usage_stats.get("last_compacted_at_step"),
    )


# =============================================================================
# Tool Approval Endpoints
# =============================================================================


async def _resolve_stale_tool_decision(
    *,
    run_id: str,
    tool_call_id: str,
    decision: str,
    status_label: str,
    session_id: Optional[str],
    is_owner: bool,
) -> Dict[str, str]:
    """Handle duplicate/stale tool approval requests with explicit outcomes.

    The tool_call_id from the URL is the provider's ID (e.g. ``functions.bash:9``),
    which differs from the UUID stored as the DB primary key.  We first try a
    direct lookup (covers the rare case where they coincide), then fall back to
    scanning the run's tool calls for a matching approval_decision.
    """
    db = await get_db()
    agent_repo = AgentRepo(db)
    trace_repo = TraceRepo(db)

    run = await trace_repo.get_run_with_session_check(
        run_id,
        session_id=session_id,
        is_owner=is_owner,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    tool_call = await agent_repo.get_tool_call(tool_call_id)

    if not tool_call or tool_call.get("run_id") != run_id:
        all_tool_calls = await agent_repo.get_tool_calls_for_run(run_id)
        for tc in reversed(all_tool_calls):
            if tc.get("approval_decision") == decision:
                return {"status": status_label, "run_id": run_id, "tool_call_id": tool_call_id}

    if tool_call and tool_call.get("run_id") == run_id:
        existing_decision = tool_call.get("approval_decision")
        if existing_decision == decision:
            return {"status": status_label, "run_id": run_id, "tool_call_id": tool_call_id}
        if existing_decision in {"approved", "denied"}:
            return {
                "status": existing_decision,
                "run_id": run_id,
                "tool_call_id": tool_call_id,
            }

    if run.get("status") in {"failed", "succeeded", "cancelled"}:
        return {
            "status": str(run.get("status")),
            "run_id": run_id,
            "tool_call_id": tool_call_id,
        }

    if run.get("status") == "running":
        logger.info(
            "Approval accepted for active run (future already consumed)",
            extra={"run_id": run_id, "tool_call_id": tool_call_id, "decision": decision},
        )
        await _emit_tool_approval_decided(
            run_id=run_id,
            tool_call_id=tool_call_id,
            decision=decision,
            status_label=status_label,
        )
        return {"status": status_label, "run_id": run_id, "tool_call_id": tool_call_id}

    raise HTTPException(status_code=404, detail="No pending approval for this tool call")


@router.post("/runs/{run_id}/approve/{tool_call_id}")
async def approve_tool_call(run_id: str, tool_call_id: str, http_request: Request):
    """Approve a tool call that requires permission.

    Resolves the approval Future with True, allowing tool execution to proceed.
    """
    session_id, is_owner = get_session_context(http_request)
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    queues = _approval_queues.get(run_id, {})
    future = queues.get(tool_call_id)

    if future is None:
        return await _resolve_stale_tool_decision(
            run_id=run_id,
            tool_call_id=tool_call_id,
            decision="approved",
            status_label="approved",
            session_id=session_id,
            is_owner=is_owner,
        )

    if not future.done():
        future.set_result(True)
    await _emit_tool_approval_decided(
        run_id=run_id,
        tool_call_id=tool_call_id,
        decision="approved",
        status_label="approved",
    )

    logger.info(
        "Tool call approved",
        extra={"run_id": run_id, "tool_call_id": tool_call_id},
    )
    return {"status": "approved", "run_id": run_id, "tool_call_id": tool_call_id}


@router.post("/runs/{run_id}/deny/{tool_call_id}")
async def deny_tool_call(run_id: str, tool_call_id: str, http_request: Request):
    """Deny a tool call that requires permission.

    Resolves the approval Future with False, blocking tool execution.
    """
    session_id, is_owner = get_session_context(http_request)
    if not is_owner and run_id in _run_sessions:
        run_session = _run_sessions.get(run_id)
        if run_session and run_session != session_id:
            raise HTTPException(status_code=404, detail="Run not found")

    queues = _approval_queues.get(run_id, {})
    future = queues.get(tool_call_id)

    if future is None:
        return await _resolve_stale_tool_decision(
            run_id=run_id,
            tool_call_id=tool_call_id,
            decision="denied",
            status_label="denied",
            session_id=session_id,
            is_owner=is_owner,
        )

    if not future.done():
        future.set_result(False)
    await _emit_tool_approval_decided(
        run_id=run_id,
        tool_call_id=tool_call_id,
        decision="denied",
        status_label="denied",
    )

    logger.info(
        "Tool call denied",
        extra={"run_id": run_id, "tool_call_id": tool_call_id},
    )
    return {"status": "denied", "run_id": run_id, "tool_call_id": tool_call_id}
