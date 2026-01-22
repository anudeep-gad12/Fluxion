"""Tests for research planner."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.agent.planner import (
    Planner,
    ResearchPlan,
    PlanStep,
    PlanStepType,
    PlanStepStatus,
)


class TestPlanStep:
    """Tests for PlanStep dataclass."""

    def test_default_values(self):
        """PlanStep has correct defaults."""
        step = PlanStep()
        assert step.step_number == 0
        assert step.step_type == PlanStepType.SEARCH
        assert step.description == ""
        assert step.rationale == ""
        assert step.expected_tool is None
        assert step.status == PlanStepStatus.PENDING
        assert len(step.id) == 8  # UUID first 8 chars

    def test_to_dict(self):
        """PlanStep converts to dict correctly."""
        step = PlanStep(
            id="test123",
            step_number=1,
            step_type=PlanStepType.EXTRACT,
            description="Extract data from URL",
            rationale="Need detailed information",
            expected_tool="web_extract",
            status=PlanStepStatus.COMPLETED,
        )
        d = step.to_dict()

        assert d["id"] == "test123"
        assert d["step_number"] == 1
        assert d["step_type"] == "extract"
        assert d["description"] == "Extract data from URL"
        assert d["rationale"] == "Need detailed information"
        assert d["expected_tool"] == "web_extract"
        assert d["status"] == "completed"


class TestResearchPlan:
    """Tests for ResearchPlan dataclass."""

    def test_default_values(self):
        """ResearchPlan has correct defaults."""
        plan = ResearchPlan()
        assert plan.query == ""
        assert plan.query_analysis == ""
        assert plan.approach == ""
        assert plan.steps == []
        assert plan.estimated_complexity == "medium"
        assert plan.created_at is None
        assert len(plan.id) == 8

    def test_to_dict(self):
        """ResearchPlan converts to dict correctly."""
        plan = ResearchPlan(
            id="plan123",
            query="What is the population of France?",
            query_analysis="Simple factual question",
            approach="Single search",
            steps=[
                PlanStep(step_number=1, description="Search for info"),
            ],
            estimated_complexity="low",
            created_at="2026-01-20T00:00:00Z",
        )
        d = plan.to_dict()

        assert d["id"] == "plan123"
        assert d["query"] == "What is the population of France?"
        assert d["query_analysis"] == "Simple factual question"
        assert d["approach"] == "Single search"
        assert d["estimated_complexity"] == "low"
        assert d["step_count"] == 1
        assert d["created_at"] == "2026-01-20T00:00:00Z"
        assert len(d["steps"]) == 1

    def test_to_dict_truncates_long_query(self):
        """Long queries are truncated in to_dict."""
        plan = ResearchPlan(query="x" * 300)
        d = plan.to_dict()
        assert len(d["query"]) == 200

    def test_to_injection_text(self):
        """Plan generates injection text correctly."""
        plan = ResearchPlan(
            query_analysis="User wants info about Python",
            approach="Search and summarize",
            steps=[
                PlanStep(
                    step_number=1,
                    description="Search for Python info",
                    expected_tool="web_search",
                ),
                PlanStep(
                    step_number=2,
                    description="Synthesize findings",
                    expected_tool=None,
                ),
            ],
        )
        text = plan.to_injection_text()

        assert "RESEARCH PLAN" in text
        assert "User wants info about Python" in text
        assert "Search and summarize" in text
        assert "1. Search for Python info (use web_search)" in text
        assert "2. Synthesize findings" in text
        assert "(use " not in text.split("2.")[1]  # No tool hint for None

    def test_get_current_step(self):
        """Gets first pending step."""
        plan = ResearchPlan(
            steps=[
                PlanStep(step_number=1, status=PlanStepStatus.COMPLETED),
                PlanStep(step_number=2, status=PlanStepStatus.PENDING),
                PlanStep(step_number=3, status=PlanStepStatus.PENDING),
            ]
        )
        current = plan.get_current_step()

        assert current is not None
        assert current.step_number == 2

    def test_get_current_step_none_when_all_complete(self):
        """Returns None when all steps complete."""
        plan = ResearchPlan(
            steps=[
                PlanStep(step_number=1, status=PlanStepStatus.COMPLETED),
                PlanStep(step_number=2, status=PlanStepStatus.COMPLETED),
            ]
        )
        assert plan.get_current_step() is None

    def test_mark_step_completed(self):
        """Marks step as completed by ID."""
        plan = ResearchPlan(
            steps=[
                PlanStep(id="step1", step_number=1),
                PlanStep(id="step2", step_number=2),
            ]
        )
        plan.mark_step_completed("step1")

        assert plan.steps[0].status == PlanStepStatus.COMPLETED
        assert plan.steps[1].status == PlanStepStatus.PENDING

    def test_mark_step_in_progress(self):
        """Marks step as in progress."""
        plan = ResearchPlan(
            steps=[
                PlanStep(id="step1", step_number=1),
            ]
        )
        plan.mark_step_in_progress("step1")

        assert plan.steps[0].status == PlanStepStatus.IN_PROGRESS


class TestPlanner:
    """Tests for Planner class."""

    @pytest.mark.asyncio
    async def test_create_plan_success(self):
        """Creates plan from valid LLM response."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "User needs info about Python",
                "approach": "Search then summarize",
                "estimated_complexity": "low",
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "search",
                        "description": "Search for Python info",
                        "expected_tool": "web_search",
                        "rationale": "Find basic info"
                    }
                ]
            }"""
            )
        )

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("What is Python?", ["web_search"])

        assert plan is not None
        assert plan.query == "What is Python?"
        assert plan.query_analysis == "User needs info about Python"
        assert plan.approach == "Search then summarize"
        assert plan.estimated_complexity == "low"
        assert len(plan.steps) == 1
        assert plan.steps[0].step_number == 1
        assert plan.steps[0].step_type == PlanStepType.SEARCH
        assert plan.steps[0].expected_tool == "web_search"
        assert plan.created_at is not None

    @pytest.mark.asyncio
    async def test_create_plan_multi_step(self):
        """Creates multi-step plan for complex query."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Complex comparison request",
                "approach": "Search, extract, calculate, synthesize",
                "estimated_complexity": "high",
                "steps": [
                    {"step_number": 1, "step_type": "search", "description": "Search", "expected_tool": "web_search", "rationale": "r1"},
                    {"step_number": 2, "step_type": "extract", "description": "Extract", "expected_tool": "web_extract", "rationale": "r2"},
                    {"step_number": 3, "step_type": "calculate", "description": "Calculate", "expected_tool": "python_execute", "rationale": "r3"},
                    {"step_number": 4, "step_type": "synthesize", "description": "Synthesize", "expected_tool": null, "rationale": "r4"}
                ]
            }"""
            )
        )

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan(
            "Compare solar vs wind energy costs", ["web_search", "web_extract", "python_execute"]
        )

        assert plan is not None
        assert len(plan.steps) == 4
        assert plan.estimated_complexity == "high"
        assert plan.steps[0].step_type == PlanStepType.SEARCH
        assert plan.steps[1].step_type == PlanStepType.EXTRACT
        assert plan.steps[2].step_type == PlanStepType.CALCULATE
        assert plan.steps[3].step_type == PlanStepType.SYNTHESIZE
        assert plan.steps[3].expected_tool is None

    @pytest.mark.asyncio
    async def test_create_plan_handles_llm_error(self):
        """Returns None on LLM error."""
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=Exception("API error"))

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_handles_invalid_json(self):
        """Returns None on invalid JSON."""
        provider = MagicMock()
        provider.complete = AsyncMock(return_value=MagicMock(text="not json at all"))

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_handles_empty_response(self):
        """Returns None on empty response."""
        provider = MagicMock()
        provider.complete = AsyncMock(return_value=MagicMock(text=""))

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_handles_no_steps(self):
        """Returns None when plan has no steps."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Analysis",
                "approach": "Approach",
                "steps": []
            }"""
            )
        )

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is None

    @pytest.mark.asyncio
    async def test_create_plan_handles_json_in_markdown(self):
        """Extracts JSON from markdown code blocks."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""Here's the plan:
```json
{
    "query_analysis": "Test",
    "approach": "Test",
    "estimated_complexity": "low",
    "steps": [
        {"step_number": 1, "step_type": "search", "description": "Search", "expected_tool": "web_search", "rationale": "r"}
    ]
}
```"""
            )
        )

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is not None
        assert len(plan.steps) == 1

    @pytest.mark.asyncio
    async def test_create_plan_handles_null_string_for_tool(self):
        """Handles 'null' string as None for expected_tool."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Test",
                "approach": "Test",
                "estimated_complexity": "low",
                "steps": [
                    {"step_number": 1, "step_type": "synthesize", "description": "Synthesize", "expected_tool": "null", "rationale": "r"}
                ]
            }"""
            )
        )

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is not None
        assert plan.steps[0].expected_tool is None

    @pytest.mark.asyncio
    async def test_create_plan_handles_unknown_step_type(self):
        """Falls back to SEARCH for unknown step types."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Test",
                "approach": "Test",
                "estimated_complexity": "low",
                "steps": [
                    {"step_number": 1, "step_type": "unknown_type", "description": "Do something", "expected_tool": "web_search", "rationale": "r"}
                ]
            }"""
            )
        )

        planner = Planner(provider, "test-model")
        plan = await planner.create_plan("Test query", ["web_search"])

        assert plan is not None
        assert plan.steps[0].step_type == PlanStepType.SEARCH

    @pytest.mark.asyncio
    async def test_planner_uses_low_temperature(self):
        """Planner uses low temperature for deterministic output."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Test",
                "approach": "Test",
                "steps": [{"step_number": 1, "step_type": "search", "description": "Search", "expected_tool": "web_search", "rationale": "r"}]
            }"""
            )
        )

        planner = Planner(provider, "test-model")
        await planner.create_plan("Test", ["web_search"])

        # Verify the call was made with low temperature
        call_args = provider.complete.call_args
        assert call_args.kwargs["temperature"] == 0.3
        assert call_args.kwargs["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_max_plan_steps_in_prompt(self):
        """Verifies max_plan_steps is used in the prompt."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Test",
                "approach": "Test",
                "steps": [{"step_number": 1, "step_type": "search", "description": "Search", "expected_tool": "web_search", "rationale": "r"}]
            }"""
            )
        )

        # Test with custom max_plan_steps
        planner = Planner(provider, "test-model", max_plan_steps=7)
        await planner.create_plan("Complex query", ["web_search"])

        # Verify prompt contains max_steps value
        call_args = provider.complete.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "at most 7 steps" in prompt
        assert "up to 7 steps" in prompt

    @pytest.mark.asyncio
    async def test_default_max_plan_steps(self):
        """Verifies default max_plan_steps is 5."""
        provider = MagicMock()
        provider.complete = AsyncMock(
            return_value=MagicMock(
                text="""{
                "query_analysis": "Test",
                "approach": "Test",
                "steps": [{"step_number": 1, "step_type": "search", "description": "Search", "expected_tool": "web_search", "rationale": "r"}]
            }"""
            )
        )

        planner = Planner(provider, "test-model")  # Uses default
        await planner.create_plan("Test", ["web_search"])

        # Verify prompt contains default max_steps value
        call_args = provider.complete.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "at most 5 steps" in prompt
