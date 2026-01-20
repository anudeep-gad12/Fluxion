"""Research planner for agent queries.

This module provides:
- ResearchPlan: Structured plan with steps
- PlanStep: Individual step in a plan
- Planner: Creates plans using LLM

The planner runs BEFORE the main agent loop and generates a plan
that guides execution. The LLM naturally scales plan complexity:
- Simple queries: 1 step
- Moderate research: 2-3 steps
- Complex analysis: 3-5 steps
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from orchestrator.logging_config import get_logger

if TYPE_CHECKING:
    from orchestrator.providers.base import LLMProvider

logger = get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class PlanStepType(str, Enum):
    """Types of plan steps."""

    SEARCH = "search"
    EXTRACT = "extract"
    CALCULATE = "calculate"
    SYNTHESIZE = "synthesize"


class PlanStepStatus(str, Enum):
    """Status of a plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PlanStep:
    """A single step in the research plan.

    Attributes:
        id: Unique identifier for the step.
        step_number: Position in plan (1-indexed).
        step_type: Type of action (search, extract, calculate, synthesize).
        description: What this step aims to accomplish.
        rationale: Why this step is needed.
        expected_tool: Which tool will likely be used.
        status: Current status of the step.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_number: int = 0
    step_type: PlanStepType = PlanStepType.SEARCH
    description: str = ""
    rationale: str = ""
    expected_tool: Optional[str] = None  # "web_search" | "web_extract" | "python_execute" | None
    status: PlanStepStatus = PlanStepStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "step_number": self.step_number,
            "step_type": self.step_type.value,
            "description": self.description,
            "rationale": self.rationale,
            "expected_tool": self.expected_tool,
            "status": self.status.value,
        }


@dataclass
class ResearchPlan:
    """Structured research plan for the agent.

    Attributes:
        id: Unique identifier for the plan.
        query: Original user query.
        query_analysis: Brief analysis of what the query needs.
        approach: High-level approach description.
        steps: Ordered list of plan steps.
        estimated_complexity: low, medium, high.
        created_at: Timestamp of creation.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    query: str = ""
    query_analysis: str = ""
    approach: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    estimated_complexity: str = "medium"  # "low" | "medium" | "high"
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for trace serialization."""
        return {
            "id": self.id,
            "query": self.query[:200],  # Truncate for storage
            "query_analysis": self.query_analysis,
            "approach": self.approach,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_complexity": self.estimated_complexity,
            "step_count": len(self.steps),
            "created_at": self.created_at,
        }

    def to_injection_text(self) -> str:
        """Convert plan to text for message injection."""
        lines = [
            "RESEARCH PLAN",
            f"Analysis: {self.query_analysis}",
            f"Approach: {self.approach}",
            "",
            "Steps:",
        ]
        for step in self.steps:
            tool_hint = f" (use {step.expected_tool})" if step.expected_tool else ""
            lines.append(f"  {step.step_number}. {step.description}{tool_hint}")
        return "\n".join(lines)

    def get_current_step(self) -> Optional[PlanStep]:
        """Get the first pending step."""
        for step in self.steps:
            if step.status == PlanStepStatus.PENDING:
                return step
        return None

    def mark_step_completed(self, step_id: str) -> None:
        """Mark a step as completed by ID."""
        for step in self.steps:
            if step.id == step_id:
                step.status = PlanStepStatus.COMPLETED
                break

    def mark_step_in_progress(self, step_id: str) -> None:
        """Mark a step as in progress."""
        for step in self.steps:
            if step.id == step_id:
                step.status = PlanStepStatus.IN_PROGRESS
                break


# =============================================================================
# Planning Prompt
# =============================================================================

PLANNING_PROMPT = """You are a research planning assistant. Given a user query, create a focused research plan.

User Query: {query}

Create a plan with the appropriate number of steps:
- For simple factual questions: 1 step (just answer or single search)
- For moderate research: 2-3 steps
- For complex analysis/comparison: 3-5 steps

For each step specify:
1. What to do (brief description)
2. Which tool to use: web_search, web_extract, python_execute, or null (for synthesis)
3. Why this step is needed

Output ONLY valid JSON:
{{
  "query_analysis": "Brief analysis of what the user needs",
  "approach": "High-level approach (1 sentence)",
  "estimated_complexity": "low|medium|high",
  "steps": [
    {{
      "step_number": 1,
      "step_type": "search|extract|calculate|synthesize",
      "description": "What to do",
      "expected_tool": "web_search|web_extract|python_execute|null",
      "rationale": "Why this step"
    }}
  ]
}}

Guidelines:
- Match plan complexity to query complexity
- Simple queries like "What is X?" need only 1 step
- For calculations, include python_execute early
- Final synthesis step has expected_tool: null
- Output ONLY JSON, no other text"""


# =============================================================================
# Planner Class
# =============================================================================


class Planner:
    """Creates research plans for agent queries.

    Uses a lightweight LLM call to generate a structured plan
    before the main agent loop begins. The planner naturally
    scales plan complexity based on query complexity.

    Example:
        planner = Planner(provider, "gpt-4")
        plan = await planner.create_plan(
            "Compare solar vs wind energy costs",
            ["web_search", "web_extract", "python_execute"],
        )
    """

    # Lower temperature for more deterministic planning
    PLANNING_TEMPERATURE: float = 0.3
    PLANNING_MAX_TOKENS: int = 1024

    def __init__(
        self,
        provider: "LLMProvider",
        model_name: str,
    ) -> None:
        """Initialize planner.

        Args:
            provider: LLM provider for planning call.
            model_name: Model to use for planning.
        """
        self._provider = provider
        self._model_name = model_name

    async def create_plan(
        self,
        query: str,
        available_tools: List[str],
    ) -> Optional[ResearchPlan]:
        """Create a research plan for the query.

        The planner LLM naturally scales plan complexity:
        - Simple queries get 1-step plans
        - Complex queries get 3-5 step plans

        Args:
            query: User's research query.
            available_tools: List of available tool names.

        Returns:
            ResearchPlan if successful, None if planning fails.
        """
        prompt = PLANNING_PROMPT.format(query=query)

        try:
            response = await self._provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model_name,
                max_tokens=self.PLANNING_MAX_TOKENS,
                temperature=self.PLANNING_TEMPERATURE,
            )

            plan = self._parse_plan_response(response.text, query)
            if plan:
                plan.created_at = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Created research plan",
                    extra={
                        "plan_id": plan.id,
                        "steps": len(plan.steps),
                        "complexity": plan.estimated_complexity,
                    },
                )
            return plan

        except Exception as e:
            logger.warning(
                "Planning failed, agent will proceed without plan",
                extra={"error": str(e)},
            )
            return None

    def _parse_plan_response(
        self,
        text: str,
        query: str,
    ) -> Optional[ResearchPlan]:
        """Parse LLM response into ResearchPlan.

        Args:
            text: Raw LLM response text.
            query: Original query for context.

        Returns:
            ResearchPlan if parsing succeeds, None otherwise.
        """
        if not text:
            return None

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            logger.debug("No JSON found in planning response")
            return None

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.debug(f"JSON parse failed: {e}")
            return None

        # Build plan from parsed data
        plan = ResearchPlan(
            query=query,
            query_analysis=data.get("query_analysis", ""),
            approach=data.get("approach", ""),
            estimated_complexity=data.get("estimated_complexity", "medium"),
        )

        # Parse steps
        for step_data in data.get("steps", []):
            step_type_str = step_data.get("step_type", "search")
            try:
                step_type = PlanStepType(step_type_str)
            except ValueError:
                step_type = PlanStepType.SEARCH

            # Handle "null" string as None
            expected_tool = step_data.get("expected_tool")
            if expected_tool == "null" or expected_tool == "":
                expected_tool = None

            step = PlanStep(
                step_number=step_data.get("step_number", 0),
                step_type=step_type,
                description=step_data.get("description", ""),
                rationale=step_data.get("rationale", ""),
                expected_tool=expected_tool,
            )
            plan.steps.append(step)

        # Validate: need at least one step
        if not plan.steps:
            logger.debug("Plan has no steps")
            return None

        return plan
