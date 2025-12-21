import json

import pytest

from orchestrator.config import BudgetConfig as ProfileBudgetConfig
from orchestrator.config import ModelEndpoints, Profile
from orchestrator.engine.budgets import BudgetConfig, BudgetTracker
from orchestrator.engine.gates import GateChecker, GateType, RouteResult
from orchestrator.engine.state_machine import RunContext, SolverEngine, Stage
from orchestrator.engine.stuck import StuckDetector
from orchestrator.tools.base import ToolResult, ToolStatus


def _make_profile() -> Profile:
    return Profile(
        name="test",
        endpoints=ModelEndpoints(
            router="http://test",
            planner="http://test",
            worker_general="http://test",
            worker_code="http://test",
            critic="http://test",
        ),
        budgets=ProfileBudgetConfig(
            max_steps=50,
            max_tool_calls=20,
            max_time_seconds=120,
            max_revisions=2,
        ),
        num_candidates=2,
    )


def test_candidate_scoped_gates() -> None:
    checker = GateChecker()
    checker.set_route_result(
        RouteResult(
            task_type="math",
            required_gates=[GateType.REQUIRES_PYTHON],
            suggested_tools=[],
            metadata={},
        )
    )

    event = {
        "type": "TOOL_CALL_FINISHED",
        "display": {"status": "ok"},
        "payload": {
            "tool": "python",
            "code": "print(1 + 1)",
            "stdout": "2",
            "stderr": "",
            "exit_code": 0,
        },
    }

    checker.add_event(event, candidate_id="A")

    passed_a, _ = checker.check_all_gates(candidate_id="A")
    passed_b, _ = checker.check_all_gates(candidate_id="B")

    assert passed_a is True
    assert passed_b is False


def test_discriminator_parsing_fallbacks() -> None:
    engine = SolverEngine()
    candidate_ids = ["A", "B"]

    fallback = engine._parse_discriminator_response("not json", candidate_ids)
    assert fallback["best_id"] == "A"

    content = json.dumps({"best_id": "Z", "ranking": [{"id": "B", "score": 0.7}]})
    parsed = engine._parse_discriminator_response(content, candidate_ids)
    assert parsed["best_id"] == "B"
    assert any(item["id"] == "A" for item in parsed["ranking"])


class _VerifyEngine(SolverEngine):
    def __init__(self, verification_map: dict[str, dict]) -> None:
        super().__init__()
        self._verification_map = verification_map

    async def _verify_candidate(self, ctx: RunContext, candidate_id: str) -> dict:
        return self._verification_map[candidate_id]

    async def _emit_event(self, ctx: RunContext, event_type: str, display: dict, payload: dict, candidate_id=None) -> dict:
        return {"type": event_type, "display": display, "payload": payload}


@pytest.mark.asyncio
async def test_verifier_fallback_to_next_candidate() -> None:
    engine = _VerifyEngine(
        {
            "A": {"status": "fail", "confidence": 0.2, "failures": [], "suggested_next": "try_next_candidate"},
            "B": {"status": "pass", "confidence": 0.8, "failures": [], "suggested_next": "revise_best"},
        }
    )

    ctx = RunContext(
        run_id="run",
        prompt="task",
        mode="forked",
        profile=_make_profile(),
        db=object(),
        artifacts=object(),
        budgets=BudgetTracker(config=BudgetConfig()),
        gates=GateChecker(),
        stuck=StuckDetector(),
    )

    ctx.route_result = RouteResult(task_type="general", required_gates=[], suggested_tools=[], metadata={})
    ctx.candidate_results = {
        "A": {"draft": "bad"},
        "B": {"draft": "good"},
    }
    ctx.candidate_ranking = ["A", "B"]

    await engine._stage_verify(ctx)

    assert ctx.selected_candidate_id == "B"
    assert ctx.current_stage == Stage.FINALIZE
    assert "A" in ctx.candidate_attempts


class _ToolEngine(SolverEngine):
    async def _generate_python_for_step(self, ctx: RunContext, step: str, step_results=None, **kwargs):
        return "print(2 + 2)"

    async def _execute_tool(self, ctx: RunContext, tool_name: str, params: dict, **kwargs):
        result = ToolResult(
            status=ToolStatus.OK,
            output="4",
            stdout="4\n",
            stderr="",
            exit_code=0,
        )
        return {"result": result, "event": {}, "payload": {}}


@pytest.mark.asyncio
async def test_execute_plan_step_uses_tool_result() -> None:
    engine = _ToolEngine()

    ctx = RunContext(
        run_id="run",
        prompt="task",
        mode="baseline",
        profile=_make_profile(),
        db=object(),
        artifacts=object(),
        budgets=BudgetTracker(config=BudgetConfig()),
        gates=GateChecker(),
        stuck=StuckDetector(),
    )
    ctx.route_result = RouteResult(task_type="math", required_gates=[], suggested_tools=[], metadata={})

    result = await engine._execute_plan_step(ctx, "Use Python to compute", step_results=[])

    assert result["type"] == "tool_execution"
    assert result["stdout"].strip() == "4"
    assert result["exit_code"] == 0
