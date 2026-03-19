"""State machine for agent execution flow.

This module provides:
- State transition management
- Crash recovery with hint injection
- Step limit enforcement
- Persistence via AgentRepo
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from orchestrator.logging_config import get_logger
from orchestrator.schemas import AgentStepState, AgentToolCallStatus

if TYPE_CHECKING:
    from orchestrator.storage.repositories.agent_repo import AgentRepo
    from orchestrator.agent.tools.registry import ToolRegistry

logger = get_logger(__name__)


class AgentState(str, Enum):
    """Agent-level states (different from step states).

    These track the overall agent execution state.
    """

    INIT = "init"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    pass


class MaxStepsExceededError(Exception):
    """Raised when max_steps limit is reached."""

    pass


@dataclass
class RecoveryContext:
    """Context for crash recovery.

    Attributes:
        needs_recovery: Whether recovery is needed.
        interrupted_tool_calls: List of interrupted tool call dicts.
        hints: List of hint messages to inject.
        last_completed_step: Last fully completed step number.
    """

    needs_recovery: bool
    interrupted_tool_calls: List[Dict[str, Any]]
    hints: List[Dict[str, Any]]
    last_completed_step: int


@dataclass
class StepResult:
    """Result from completing a step.

    Attributes:
        step_id: The step ID.
        step_number: The step number.
        state: Final state of the step.
        decision: Decision made (call_tool, synthesize, error).
        tool_calls_made: Number of tool calls made in this step.
    """

    step_id: str
    step_number: int
    state: AgentStepState
    decision: Optional[str]
    tool_calls_made: int


class AgentStateMachine:
    """Manages agent execution state and transitions.

    The state machine:
    1. Tracks current state and step number
    2. Validates state transitions
    3. Enforces max_steps limit
    4. Provides recovery context for non-idempotent tools
    5. Persists state changes via AgentRepo

    State Diagram:
        INIT -> PLANNING -> TOOL_CALLING -> PLANNING (loop)
                                         -> SYNTHESIZING -> COMPLETE
                         -> SYNTHESIZING -> COMPLETE
                         -> ERROR

    Example:
        sm = AgentStateMachine(run_id, repo, registry, max_steps=25)
        await sm.initialize()

        step = await sm.start_step()
        await sm.transition_to(AgentStepState.TOOL_CALLING)
        await sm.record_tool_call(tool_call_id, "web_search", {...})
        await sm.complete_tool_call(tool_call_id, result)
        await sm.complete_step("call_tool")
    """

    # Valid state transitions for steps
    VALID_TRANSITIONS: Dict[AgentStepState, List[AgentStepState]] = {
        AgentStepState.PLANNING: [
            AgentStepState.TOOL_CALLING,
            AgentStepState.SYNTHESIZING,
            AgentStepState.ERROR,
        ],
        AgentStepState.TOOL_CALLING: [
            AgentStepState.PLANNING,  # Loop back after tool execution
            AgentStepState.SYNTHESIZING,
            AgentStepState.COMPLETE,
            AgentStepState.ERROR,
        ],
        AgentStepState.SYNTHESIZING: [
            AgentStepState.COMPLETE,
            AgentStepState.ERROR,
        ],
        AgentStepState.COMPLETE: [],  # Terminal state
        AgentStepState.ERROR: [],  # Terminal state
    }

    def __init__(
        self,
        run_id: str,
        repo: "AgentRepo",
        tool_registry: "ToolRegistry",
        max_steps: int = 25,
    ) -> None:
        """Initialize state machine.

        Args:
            run_id: The run ID.
            repo: AgentRepo for persistence.
            tool_registry: ToolRegistry for idempotency checks.
            max_steps: Maximum allowed steps.
        """
        self._run_id = run_id
        self._repo = repo
        self._registry = tool_registry
        self._max_steps = max_steps

        # Runtime state (not persisted directly)
        self._current_step: int = 0
        self._current_step_id: Optional[str] = None
        self._current_step_state: Optional[AgentStepState] = None
        self._agent_state: AgentState = AgentState.INIT
        self._initialized: bool = False

    @property
    def run_id(self) -> str:
        """Get the run ID."""
        return self._run_id

    @property
    def current_step(self) -> int:
        """Get current step number."""
        return self._current_step

    @property
    def current_step_id(self) -> Optional[str]:
        """Get current step ID."""
        return self._current_step_id

    @property
    def current_step_state(self) -> Optional[AgentStepState]:
        """Get current step state."""
        return self._current_step_state

    @property
    def agent_state(self) -> AgentState:
        """Get overall agent state."""
        return self._agent_state

    @property
    def max_steps(self) -> int:
        """Get max steps limit."""
        return self._max_steps

    @property
    def steps_remaining(self) -> int:
        """Get number of steps remaining."""
        return max(0, self._max_steps - self._current_step)

    @property
    def is_initialized(self) -> bool:
        """Check if state machine is initialized."""
        return self._initialized

    async def initialize(self) -> RecoveryContext:
        """Initialize state machine and check for crash recovery.

        Should be called once when starting or resuming a run.

        Returns:
            RecoveryContext with recovery information.

        Raises:
            StateTransitionError: If already initialized.
        """
        if self._initialized:
            raise StateTransitionError("State machine already initialized")

        # Get existing steps and tool calls
        steps = await self._repo.get_steps_for_run(self._run_id)

        if not steps:
            # Fresh run
            self._current_step = 0
            self._agent_state = AgentState.RUNNING
            self._initialized = True

            await self._repo.update_run_agent_state(
                self._run_id,
                agent_state=self._agent_state.value,
                current_step=0,
                max_steps=self._max_steps,
            )

            return RecoveryContext(
                needs_recovery=False,
                interrupted_tool_calls=[],
                hints=[],
                last_completed_step=0,
            )

        # Resume from existing state
        return await self._recover_from_crash(steps)

    async def _recover_from_crash(
        self,
        steps: List[Dict[str, Any]],
    ) -> RecoveryContext:
        """Recover state from crash.

        Args:
            steps: List of existing step dicts.

        Returns:
            RecoveryContext with hints for non-idempotent tools.
        """
        # Find last completed step
        last_completed_step = 0
        incomplete_steps: List[Dict[str, Any]] = []

        for step in steps:
            state = AgentStepState(step["state"])
            if state == AgentStepState.COMPLETE:
                last_completed_step = max(last_completed_step, step["step_number"])
            elif state not in (AgentStepState.COMPLETE, AgentStepState.ERROR):
                incomplete_steps.append(step)

        # Get pending/running tool calls
        pending_tool_calls = await self._repo.get_pending_tool_calls(self._run_id)

        # Build recovery hints for non-idempotent tools
        hints: List[Dict[str, Any]] = []
        interrupted_non_idempotent: List[Dict[str, Any]] = []

        for tc in pending_tool_calls:
            tool_name = tc["tool_name"]
            is_idempotent = self._registry.is_idempotent(tool_name)

            if tc["status"] == "running":
                # Mark as interrupted
                await self._repo.update_tool_call(
                    tc["id"],
                    status=AgentToolCallStatus.INTERRUPTED.value,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

                if not is_idempotent:
                    interrupted_non_idempotent.append(tc)
                    hints.append(self._create_recovery_hint(tc))

        # Set current state
        if incomplete_steps:
            # Sort by step_number descending and take the latest
            incomplete_steps.sort(key=lambda s: s["step_number"], reverse=True)
            latest_incomplete = incomplete_steps[0]
            self._current_step = latest_incomplete["step_number"]
            self._current_step_id = latest_incomplete["id"]
            self._current_step_state = AgentStepState(latest_incomplete["state"])
        else:
            self._current_step = last_completed_step
            self._current_step_id = None
            self._current_step_state = None

        self._agent_state = AgentState.RUNNING
        self._initialized = True

        # Update run state
        await self._repo.update_run_agent_state(
            self._run_id,
            agent_state=self._agent_state.value,
            current_step=self._current_step,
        )

        logger.info(
            "Recovered agent state",
            extra={
                "run_id": self._run_id,
                "last_completed_step": last_completed_step,
                "interrupted_tools": len(interrupted_non_idempotent),
            },
        )

        return RecoveryContext(
            needs_recovery=bool(pending_tool_calls),
            interrupted_tool_calls=interrupted_non_idempotent,
            hints=hints,
            last_completed_step=last_completed_step,
        )

    def _create_recovery_hint(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Create a recovery hint message for non-idempotent tool.

        Args:
            tool_call: The interrupted tool call dict.

        Returns:
            System message dict with recovery hint.
        """
        tool_name = tool_call["tool_name"]
        return {
            "role": "system",
            "content": (
                f"IMPORTANT: The previous {tool_name} execution was "
                f"interrupted by a system restart. The result was lost. "
                f"Please regenerate and re-run the code to get the result."
            ),
            "_recovery_hint": True,
            "_tool_call_id": tool_call["id"],
        }

    async def start_step(self) -> Dict[str, Any]:
        """Start a new step.

        Returns:
            Step dict with id, step_number, state.

        Raises:
            MaxStepsExceededError: If max_steps reached.
            StateTransitionError: If not initialized.
        """
        self._ensure_initialized()

        if self._current_step >= self._max_steps:
            raise MaxStepsExceededError(
                f"Max steps ({self._max_steps}) exceeded"
            )

        # Check if there's an incomplete step to resume
        if self._current_step_id and self._current_step_state not in (
            AgentStepState.COMPLETE,
            AgentStepState.ERROR,
        ):
            # Resume existing step
            return {
                "id": self._current_step_id,
                "step_number": self._current_step,
                "state": (
                    self._current_step_state.value
                    if self._current_step_state
                    else "planning"
                ),
            }

        # Create new step
        self._current_step += 1
        step = await self._repo.create_step(
            run_id=self._run_id,
            step_number=self._current_step,
            state=AgentStepState.PLANNING.value,
        )

        self._current_step_id = step["id"]
        self._current_step_state = AgentStepState.PLANNING

        # Update run state
        await self._repo.update_run_agent_state(
            self._run_id,
            current_step=self._current_step,
        )

        logger.debug(
            "Started step",
            extra={
                "run_id": self._run_id,
                "step_number": self._current_step,
            },
        )

        return step

    async def transition_to(self, new_state: AgentStepState) -> None:
        """Transition current step to new state.

        Args:
            new_state: Target state.

        Raises:
            StateTransitionError: If transition is invalid.
        """
        self._ensure_initialized()
        self._ensure_active_step()

        # Validate transition
        if self._current_step_state:
            valid_targets = self.VALID_TRANSITIONS.get(self._current_step_state, [])
            if new_state not in valid_targets:
                raise StateTransitionError(
                    f"Invalid transition: {self._current_step_state.value} -> {new_state.value}"
                )

        # Update step state
        await self._repo.update_step(
            self._current_step_id,
            state=new_state.value,
        )

        self._current_step_state = new_state

        logger.debug(
            "Step state transition",
            extra={
                "run_id": self._run_id,
                "step": self._current_step,
                "new_state": new_state.value,
            },
        )

    async def record_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """Record a new tool call.

        Args:
            tool_call_id: Unique ID for the tool call.
            tool_name: Name of the tool.
            arguments: Tool arguments.
            idempotency_key: Key for idempotent retry detection.

        Returns:
            Tool call dict.
        """
        self._ensure_initialized()
        self._ensure_active_step()

        # Check for existing tool call with same idempotency key
        existing = await self._repo.get_tool_call_by_idempotency_key(
            self._run_id,
            idempotency_key,
        )
        if existing:
            return existing

        tool_call = await self._repo.create_tool_call(
            run_id=self._run_id,
            step_id=self._current_step_id,
            tool_name=tool_name,
            arguments=arguments,
            idempotency_key=idempotency_key,
        )

        return tool_call

    async def start_tool_execution(self, tool_call_id: str) -> None:
        """Mark tool call as running.

        Args:
            tool_call_id: The tool call ID.
        """
        await self._repo.update_tool_call(
            tool_call_id,
            status=AgentToolCallStatus.RUNNING.value,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    async def complete_tool_call(
        self,
        tool_call_id: str,
        success: bool,
        result_summary: str,
        duration_ms: int,
        error_message: Optional[str] = None,
        result_detail: Optional[str] = None,
    ) -> None:
        """Complete a tool call.

        Args:
            tool_call_id: The tool call ID.
            success: Whether execution succeeded.
            result_summary: 1-line summary.
            duration_ms: Execution duration.
            error_message: Error message if failed.
            result_detail: Full tool result text (for write tools).
        """
        status = (
            AgentToolCallStatus.SUCCESS.value
            if success
            else AgentToolCallStatus.ERROR.value
        )

        await self._repo.update_tool_call(
            tool_call_id,
            status=status,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            result_summary=result_summary,
            error_message=error_message,
            result_detail=result_detail,
        )

    async def record_approval(
        self,
        tool_call_id: str,
        decision: str,
        policy: str,
    ) -> None:
        """Record a tool approval decision.

        Args:
            tool_call_id: The tool call ID.
            decision: Approval decision (approved/denied/auto/timeout).
            policy: Permission policy in effect (strict/relaxed/yolo).
        """
        await self._repo.update_tool_call(
            tool_call_id,
            approval_decision=decision,
            approval_policy=policy,
            approval_decided_at=datetime.now(timezone.utc).isoformat(),
        )

    async def timeout_tool_call(
        self,
        tool_call_id: str,
        duration_ms: int,
    ) -> None:
        """Mark tool call as timed out.

        Args:
            tool_call_id: The tool call ID.
            duration_ms: Duration before timeout.
        """
        await self._repo.update_tool_call(
            tool_call_id,
            status=AgentToolCallStatus.TIMEOUT.value,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            error_message="Execution timed out",
        )

    async def complete_step(
        self,
        decision: str,
        thinking_text: Optional[str] = None,
    ) -> StepResult:
        """Complete the current step.

        Args:
            decision: Decision made (call_tool, synthesize, error).
            thinking_text: Model's reasoning text.

        Returns:
            StepResult with completion info.
        """
        self._ensure_initialized()
        self._ensure_active_step()

        # Get tool calls for this step
        tool_calls = await self._repo.get_tool_calls_for_step(self._current_step_id)

        # Update step as complete
        await self._repo.update_step(
            self._current_step_id,
            state=AgentStepState.COMPLETE.value,
            decision=decision,
            thinking_text=thinking_text,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        result = StepResult(
            step_id=self._current_step_id,
            step_number=self._current_step,
            state=AgentStepState.COMPLETE,
            decision=decision,
            tool_calls_made=len(tool_calls),
        )

        # Clear current step state (step is done)
        self._current_step_state = AgentStepState.COMPLETE

        logger.debug(
            "Completed step",
            extra={
                "run_id": self._run_id,
                "step": self._current_step,
                "decision": decision,
                "tool_calls": len(tool_calls),
            },
        )

        return result

    async def error_step(self, error_message: str) -> None:
        """Mark current step as error.

        Args:
            error_message: Error description.
        """
        self._ensure_initialized()
        self._ensure_active_step()

        await self._repo.update_step(
            self._current_step_id,
            state=AgentStepState.ERROR.value,
            error_message=error_message,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._current_step_state = AgentStepState.ERROR

    async def complete_run(self, final_answer: str) -> None:
        """Mark the run as complete.

        Args:
            final_answer: The final answer text.
        """
        self._ensure_initialized()

        self._agent_state = AgentState.COMPLETE

        await self._repo.update_run_agent_state(
            self._run_id,
            agent_state=self._agent_state.value,
            status="succeeded",
            final_answer=final_answer,
        )

        logger.info(
            "Agent run completed",
            extra={
                "run_id": self._run_id,
                "total_steps": self._current_step,
            },
        )

    async def error_run(self, error_message: str) -> None:
        """Mark the run as failed.

        Args:
            error_message: Error description.
        """
        self._ensure_initialized()

        self._agent_state = AgentState.ERROR

        await self._repo.update_run_agent_state(
            self._run_id,
            agent_state=self._agent_state.value,
            status="failed",
            error_message=error_message,
        )

        logger.error(
            "Agent run failed",
            extra={
                "run_id": self._run_id,
                "error": error_message,
            },
        )

    async def pause_run(self) -> None:
        """Pause the run between steps."""
        self._ensure_initialized()

        self._agent_state = AgentState.PAUSED

        await self._repo.update_run_agent_state(
            self._run_id,
            agent_state=self._agent_state.value,
        )

        logger.info(
            "Agent run paused",
            extra={
                "run_id": self._run_id,
                "step": self._current_step,
            },
        )

    async def resume_run(self) -> None:
        """Resume a paused run."""
        self._ensure_initialized()

        self._agent_state = AgentState.RUNNING

        await self._repo.update_run_agent_state(
            self._run_id,
            agent_state=self._agent_state.value,
        )

        logger.info(
            "Agent run resumed",
            extra={
                "run_id": self._run_id,
                "step": self._current_step,
            },
        )

    async def cancel_run(self) -> None:
        """Cancel the run."""
        self._ensure_initialized()

        self._agent_state = AgentState.CANCELLED

        await self._repo.update_run_agent_state(
            self._run_id,
            agent_state=self._agent_state.value,
            status="cancelled",
        )

        logger.info(
            "Agent run cancelled",
            extra={
                "run_id": self._run_id,
            },
        )

    def _ensure_initialized(self) -> None:
        """Ensure state machine is initialized."""
        if not self._initialized:
            raise StateTransitionError("State machine not initialized")

    def _ensure_active_step(self) -> None:
        """Ensure there's an active step."""
        if not self._current_step_id:
            raise StateTransitionError("No active step")

    def can_continue(self) -> bool:
        """Check if agent can continue execution.

        Returns:
            True if more steps allowed and not in terminal state.
        """
        if self._agent_state in (
            AgentState.COMPLETE,
            AgentState.ERROR,
            AgentState.CANCELLED,
        ):
            return False
        return self._current_step < self._max_steps
