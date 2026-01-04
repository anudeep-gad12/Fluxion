"""Tests for AgentStateMachine."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from orchestrator.schemas import AgentStepState, AgentToolCallStatus
from orchestrator.agent.state_machine import (
    AgentState,
    AgentStateMachine,
    MaxStepsExceededError,
    RecoveryContext,
    StateTransitionError,
    StepResult,
)


def create_mock_repo():
    """Create mock AgentRepo."""
    repo = MagicMock()
    repo.create_step = AsyncMock(
        return_value={
            "id": "step-1",
            "run_id": "run-1",
            "step_number": 1,
            "state": "planning",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    repo.update_step = AsyncMock()
    repo.get_steps_for_run = AsyncMock(return_value=[])
    repo.get_pending_tool_calls = AsyncMock(return_value=[])
    repo.get_tool_calls_for_step = AsyncMock(return_value=[])
    repo.update_run_agent_state = AsyncMock()
    repo.create_tool_call = AsyncMock(return_value={"id": "tc-1"})
    repo.update_tool_call = AsyncMock()
    repo.get_tool_call_by_idempotency_key = AsyncMock(return_value=None)
    return repo


def create_mock_registry():
    """Create mock ToolRegistry."""
    registry = MagicMock()
    registry.is_idempotent = MagicMock(return_value=True)
    return registry


class TestAgentStateMachineInit:
    """Tests for initialization."""

    @pytest.mark.asyncio
    async def test_fresh_initialization(self):
        """Fresh run initializes to RUNNING state."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        context = await sm.initialize()

        assert sm.agent_state == AgentState.RUNNING
        assert sm.current_step == 0
        assert sm.is_initialized is True
        assert context.needs_recovery is False
        assert context.hints == []
        assert context.interrupted_tool_calls == []

    @pytest.mark.asyncio
    async def test_double_init_raises(self):
        """Double initialization raises error."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        with pytest.raises(StateTransitionError, match="already initialized"):
            await sm.initialize()

    @pytest.mark.asyncio
    async def test_initialization_updates_run_state(self):
        """Initialization updates run state in repo."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry, max_steps=5)
        await sm.initialize()

        repo.update_run_agent_state.assert_called_once_with(
            "run-1",
            agent_state="running",
            current_step=0,
            max_steps=5,
        )

    @pytest.mark.asyncio
    async def test_recovery_with_completed_steps(self):
        """Recovery finds last completed step."""
        repo = create_mock_repo()
        repo.get_steps_for_run = AsyncMock(
            return_value=[
                {"id": "step-1", "step_number": 1, "state": "complete"},
                {"id": "step-2", "step_number": 2, "state": "complete"},
            ]
        )
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        context = await sm.initialize()

        assert sm.current_step == 2
        assert context.last_completed_step == 2
        assert context.needs_recovery is False

    @pytest.mark.asyncio
    async def test_recovery_with_incomplete_step(self):
        """Recovery resumes incomplete step."""
        repo = create_mock_repo()
        repo.get_steps_for_run = AsyncMock(
            return_value=[
                {"id": "step-1", "step_number": 1, "state": "complete"},
                {"id": "step-2", "step_number": 2, "state": "tool_calling"},
            ]
        )
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        context = await sm.initialize()

        assert sm.current_step == 2
        assert sm.current_step_id == "step-2"
        assert sm.current_step_state == AgentStepState.TOOL_CALLING
        assert context.last_completed_step == 1

    @pytest.mark.asyncio
    async def test_recovery_with_interrupted_tools(self):
        """Recovery detects interrupted tool calls."""
        repo = create_mock_repo()
        repo.get_steps_for_run = AsyncMock(
            return_value=[
                {"id": "step-1", "step_number": 1, "state": "tool_calling"},
            ]
        )
        repo.get_pending_tool_calls = AsyncMock(
            return_value=[
                {"id": "tc-1", "tool_name": "web_search", "status": "running"},
            ]
        )

        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        context = await sm.initialize()

        assert context.needs_recovery is True
        # Tool was marked as interrupted
        repo.update_tool_call.assert_called()

    @pytest.mark.asyncio
    async def test_recovery_creates_hints_for_non_idempotent(self):
        """Recovery creates hints for non-idempotent tools."""
        repo = create_mock_repo()
        repo.get_steps_for_run = AsyncMock(
            return_value=[
                {"id": "step-1", "step_number": 1, "state": "tool_calling"},
            ]
        )
        repo.get_pending_tool_calls = AsyncMock(
            return_value=[
                {"id": "tc-1", "tool_name": "python_execute", "status": "running"},
            ]
        )

        registry = create_mock_registry()
        registry.is_idempotent = MagicMock(return_value=False)

        sm = AgentStateMachine("run-1", repo, registry)
        context = await sm.initialize()

        assert len(context.hints) == 1
        assert "python_execute" in context.hints[0]["content"]
        assert context.hints[0]["_recovery_hint"] is True
        assert len(context.interrupted_tool_calls) == 1


class TestAgentStateMachineSteps:
    """Tests for step management."""

    @pytest.mark.asyncio
    async def test_start_step(self):
        """Starting a step creates new step record."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        step = await sm.start_step()

        assert step["step_number"] == 1
        assert sm.current_step == 1
        assert sm.current_step_state == AgentStepState.PLANNING
        repo.create_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_step_not_initialized_raises(self):
        """Starting step without initialization raises."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)

        with pytest.raises(StateTransitionError, match="not initialized"):
            await sm.start_step()

    @pytest.mark.asyncio
    async def test_max_steps_exceeded(self):
        """Starting step beyond max_steps raises."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry, max_steps=1)
        await sm.initialize()

        await sm.start_step()
        await sm.complete_step("call_tool")

        with pytest.raises(MaxStepsExceededError, match="Max steps"):
            await sm.start_step()

    @pytest.mark.asyncio
    async def test_steps_remaining(self):
        """steps_remaining tracks correctly."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry, max_steps=5)
        await sm.initialize()

        assert sm.steps_remaining == 5
        await sm.start_step()
        assert sm.steps_remaining == 4

    @pytest.mark.asyncio
    async def test_resume_incomplete_step(self):
        """start_step resumes incomplete step instead of creating new."""
        repo = create_mock_repo()
        repo.get_steps_for_run = AsyncMock(
            return_value=[
                {"id": "step-1", "step_number": 1, "state": "planning"},
            ]
        )
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        step = await sm.start_step()

        assert step["id"] == "step-1"
        assert step["step_number"] == 1
        # Should not create a new step
        repo.create_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_step(self):
        """Completing step updates DB and returns result."""
        repo = create_mock_repo()
        repo.get_tool_calls_for_step = AsyncMock(
            return_value=[{"id": "tc-1"}, {"id": "tc-2"}]
        )
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        result = await sm.complete_step("call_tool", thinking_text="I need to search")

        assert result.step_number == 1
        assert result.state == AgentStepState.COMPLETE
        assert result.decision == "call_tool"
        assert result.tool_calls_made == 2
        repo.update_step.assert_called()

    @pytest.mark.asyncio
    async def test_error_step(self):
        """Error step updates state correctly."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.error_step("Something went wrong")

        assert sm.current_step_state == AgentStepState.ERROR
        repo.update_step.assert_called()


class TestAgentStateMachineTransitions:
    """Tests for state transitions."""

    @pytest.mark.asyncio
    async def test_valid_transition_planning_to_tool_calling(self):
        """PLANNING -> TOOL_CALLING is valid."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.transition_to(AgentStepState.TOOL_CALLING)

        assert sm.current_step_state == AgentStepState.TOOL_CALLING

    @pytest.mark.asyncio
    async def test_valid_transition_planning_to_synthesizing(self):
        """PLANNING -> SYNTHESIZING is valid."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.transition_to(AgentStepState.SYNTHESIZING)

        assert sm.current_step_state == AgentStepState.SYNTHESIZING

    @pytest.mark.asyncio
    async def test_valid_transition_tool_calling_to_planning(self):
        """TOOL_CALLING -> PLANNING is valid (for loop)."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()
        await sm.transition_to(AgentStepState.TOOL_CALLING)

        await sm.transition_to(AgentStepState.PLANNING)

        assert sm.current_step_state == AgentStepState.PLANNING

    @pytest.mark.asyncio
    async def test_invalid_transition_planning_to_complete(self):
        """PLANNING -> COMPLETE is invalid."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        with pytest.raises(StateTransitionError, match="Invalid transition"):
            await sm.transition_to(AgentStepState.COMPLETE)

    @pytest.mark.asyncio
    async def test_invalid_transition_from_complete(self):
        """COMPLETE -> anything is invalid."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()
        await sm.transition_to(AgentStepState.TOOL_CALLING)
        await sm.transition_to(AgentStepState.COMPLETE)

        with pytest.raises(StateTransitionError, match="Invalid transition"):
            await sm.transition_to(AgentStepState.PLANNING)

    @pytest.mark.asyncio
    async def test_transition_no_active_step_raises(self):
        """Transition without active step raises."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        with pytest.raises(StateTransitionError, match="No active step"):
            await sm.transition_to(AgentStepState.TOOL_CALLING)


class TestAgentStateMachineToolCalls:
    """Tests for tool call management."""

    @pytest.mark.asyncio
    async def test_record_tool_call(self):
        """Recording tool call creates DB entry."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        tc = await sm.record_tool_call(
            tool_call_id="tc-1",
            tool_name="web_search",
            arguments={"query": "test"},
            idempotency_key="key-1",
        )

        assert tc["id"] == "tc-1"
        repo.create_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_tool_call_returns_existing(self):
        """Same idempotency key returns existing tool call."""
        repo = create_mock_repo()
        repo.get_tool_call_by_idempotency_key = AsyncMock(
            return_value={"id": "existing-tc"}
        )
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        tc = await sm.record_tool_call(
            tool_call_id="tc-1",
            tool_name="web_search",
            arguments={"query": "test"},
            idempotency_key="key-1",
        )

        assert tc["id"] == "existing-tc"
        repo.create_tool_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_tool_execution(self):
        """Starting tool execution updates status."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.start_tool_execution("tc-1")

        repo.update_tool_call.assert_called_once()
        call_kwargs = repo.update_tool_call.call_args.kwargs
        assert call_kwargs["status"] == "running"
        assert "started_at" in call_kwargs

    @pytest.mark.asyncio
    async def test_complete_tool_call_success(self):
        """Completing tool call with success updates status."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.complete_tool_call(
            tool_call_id="tc-1",
            success=True,
            result_summary="Found 10 results",
            duration_ms=150,
        )

        call_kwargs = repo.update_tool_call.call_args.kwargs
        assert call_kwargs["status"] == "success"
        assert call_kwargs["result_summary"] == "Found 10 results"
        assert call_kwargs["duration_ms"] == 150

    @pytest.mark.asyncio
    async def test_complete_tool_call_error(self):
        """Completing tool call with error updates status."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.complete_tool_call(
            tool_call_id="tc-1",
            success=False,
            result_summary="Failed",
            duration_ms=100,
            error_message="Network error",
        )

        call_kwargs = repo.update_tool_call.call_args.kwargs
        assert call_kwargs["status"] == "error"
        assert call_kwargs["error_message"] == "Network error"

    @pytest.mark.asyncio
    async def test_timeout_tool_call(self):
        """Timeout tool call updates status correctly."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.start_step()

        await sm.timeout_tool_call("tc-1", duration_ms=30000)

        call_kwargs = repo.update_tool_call.call_args.kwargs
        assert call_kwargs["status"] == "timeout"
        assert call_kwargs["error_message"] == "Execution timed out"


class TestAgentStateMachineRun:
    """Tests for run completion."""

    @pytest.mark.asyncio
    async def test_complete_run(self):
        """Completing run updates agent state."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        await sm.complete_run("The answer is 42")

        assert sm.agent_state == AgentState.COMPLETE
        call_kwargs = repo.update_run_agent_state.call_args.kwargs
        assert call_kwargs["status"] == "succeeded"
        assert call_kwargs["final_answer"] == "The answer is 42"

    @pytest.mark.asyncio
    async def test_error_run(self):
        """Error run updates agent state."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        await sm.error_run("Something went wrong")

        assert sm.agent_state == AgentState.ERROR
        call_kwargs = repo.update_run_agent_state.call_args.kwargs
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["error_message"] == "Something went wrong"

    @pytest.mark.asyncio
    async def test_cancel_run(self):
        """Cancel run updates agent state."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()

        await sm.cancel_run()

        assert sm.agent_state == AgentState.CANCELLED
        call_kwargs = repo.update_run_agent_state.call_args.kwargs
        assert call_kwargs["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_can_continue_returns_true_initially(self):
        """can_continue returns True when initialized."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry, max_steps=5)
        await sm.initialize()

        assert sm.can_continue() is True

    @pytest.mark.asyncio
    async def test_can_continue_returns_false_after_complete(self):
        """can_continue returns False after completion."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.complete_run("Done")

        assert sm.can_continue() is False

    @pytest.mark.asyncio
    async def test_can_continue_returns_false_after_error(self):
        """can_continue returns False after error."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry)
        await sm.initialize()
        await sm.error_run("Failed")

        assert sm.can_continue() is False

    @pytest.mark.asyncio
    async def test_can_continue_returns_false_at_max_steps(self):
        """can_continue returns False at max steps."""
        repo = create_mock_repo()
        registry = create_mock_registry()

        sm = AgentStateMachine("run-1", repo, registry, max_steps=1)
        await sm.initialize()
        await sm.start_step()
        await sm.complete_step("call_tool")

        assert sm.can_continue() is False


class TestRecoveryContext:
    """Tests for RecoveryContext dataclass."""

    def test_recovery_context_fields(self):
        """RecoveryContext has expected fields."""
        ctx = RecoveryContext(
            needs_recovery=True,
            interrupted_tool_calls=[{"id": "tc-1"}],
            hints=[{"role": "system", "content": "hint"}],
            last_completed_step=2,
        )
        assert ctx.needs_recovery is True
        assert len(ctx.interrupted_tool_calls) == 1
        assert len(ctx.hints) == 1
        assert ctx.last_completed_step == 2


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_step_result_fields(self):
        """StepResult has expected fields."""
        result = StepResult(
            step_id="step-1",
            step_number=1,
            state=AgentStepState.COMPLETE,
            decision="call_tool",
            tool_calls_made=2,
        )
        assert result.step_id == "step-1"
        assert result.step_number == 1
        assert result.state == AgentStepState.COMPLETE
        assert result.decision == "call_tool"
        assert result.tool_calls_made == 2


class TestAgentState:
    """Tests for AgentState enum."""

    def test_agent_state_values(self):
        """AgentState has expected values."""
        assert AgentState.INIT.value == "init"
        assert AgentState.RUNNING.value == "running"
        assert AgentState.COMPLETE.value == "complete"
        assert AgentState.ERROR.value == "error"
        assert AgentState.CANCELLED.value == "cancelled"
