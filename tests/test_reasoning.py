"""Tests for the ReAct-style reasoning pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from orchestrator.engine.reasoner import (
    ReActReasoner,
    ChainOfThoughtReasoner,  # Alias for backward compatibility
    ParsedReactResponse,
    ParsedResponse,  # Legacy
    ReasoningResult,
    ReasoningStep,
    ReasoningStrategy,
)
from orchestrator.engine.state_machine import Stage, EVENT_CATEGORIES
from orchestrator.tools.base import ToolResult, ToolStatus


class TestReActParsing:
    """Test ReAct response parsing."""

    def test_parse_thinking(self):
        reasoner = ReActReasoner({})
        content = """<think>
I need to calculate 2 + 2.
Let me use Python for this.
</think>

Some other text."""

        result = reasoner._parse_response(content)

        assert result.think is not None
        assert "calculate 2 + 2" in result.think
        assert result.act is None
        assert result.answer is None

    def test_parse_thinking_alternate_tag(self):
        """Test that <thinking> tag also works for compatibility."""
        reasoner = ReActReasoner({})
        content = """<thinking>
Using the old tag format.
</thinking>"""

        result = reasoner._parse_response(content)

        assert result.think is not None
        assert "old tag format" in result.think

    def test_parse_act_new_format(self):
        reasoner = ReActReasoner({})
        content = """<think>Let me compute this.</think>

<act tool="python">
{"code": "print(2 + 2)"}
</act>"""

        result = reasoner._parse_response(content)

        assert result.think == "Let me compute this."
        assert result.act is not None
        assert result.act["tool"] == "python"
        assert result.act["params"]["code"] == "print(2 + 2)"

    def test_parse_tool_legacy_format(self):
        """Test backward compatibility with <tool> tag."""
        reasoner = ReActReasoner({})
        content = """<thinking>Let me compute this.</thinking>

<tool name="python">
{"code": "print(2 + 2)"}
</tool>"""

        result = reasoner._parse_response(content)

        assert result.think == "Let me compute this."
        assert result.act is not None
        assert result.act["tool"] == "python"
        assert result.act["params"]["code"] == "print(2 + 2)"

    def test_parse_answer(self):
        reasoner = ReActReasoner({})
        content = """<think>The result is 4.</think>

<answer>
The answer is **4**.
</answer>"""

        result = reasoner._parse_response(content)

        assert result.think == "The result is 4."
        assert result.answer == "The answer is **4**."

    def test_parse_plan(self):
        reasoner = ReActReasoner({})
        content = """<plan>
I will calculate using Python.
</plan>

<think>Working on it...</think>"""

        result = reasoner._parse_response(content)

        assert result.plan is not None
        assert "calculate using Python" in result.plan
        assert result.think == "Working on it..."

    def test_parse_verify(self):
        reasoner = ReActReasoner({})
        content = """<verify>
- Checked the calculation: correct
- Answer makes sense: yes
</verify>

<answer>Final answer</answer>"""

        result = reasoner._parse_response(content)

        assert result.verify is not None
        assert "Checked the calculation" in result.verify
        assert result.answer == "Final answer"


class TestEventCategories:
    """Test event categorization."""

    def test_thinking_events(self):
        assert "THINKING_STEP" in EVENT_CATEGORIES["thinking"]
        assert "TOOL_COMPLETED" in EVENT_CATEGORIES["thinking"]
        assert "REASONING_STARTED" in EVENT_CATEGORIES["thinking"]

    def test_answer_events(self):
        assert "ANSWER_READY" in EVENT_CATEGORIES["answer"]

    def test_internal_events(self):
        assert "RUN_STARTED" in EVENT_CATEGORIES["internal"]
        assert "ROUTE_COMPLETED" in EVENT_CATEGORIES["internal"]


class TestReasonerToolExecution:
    """Test tool execution in reasoning."""

    @pytest.mark.asyncio
    async def test_execute_known_tool(self):
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value=ToolResult(
            status=ToolStatus.OK,
            output="4",
            stdout="4\n",
            stderr="",
            exit_code=0,
        ))

        reasoner = ReActReasoner({"python": mock_tool})

        result = await reasoner._execute_tool("python", {"code": "print(2+2)"}, "run123")

        assert result.status == ToolStatus.OK
        assert result.output == "4"
        mock_tool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        reasoner = ReActReasoner({})

        result = await reasoner._execute_tool("unknown", {}, "run123")

        assert result.status == ToolStatus.ERROR
        assert "Unknown tool" in result.output


class TestConfidenceComputation:
    """Test confidence score computation."""

    def test_base_confidence(self):
        reasoner = ReActReasoner({})

        confidence = reasoner._compute_confidence([])

        assert confidence == 0.5  # Base confidence

    def test_thinking_increases_confidence(self):
        reasoner = ReActReasoner({})

        steps = [
            ReasoningStep(phase="think", content="step1"),
            ReasoningStep(phase="think", content="step2"),
            ReasoningStep(phase="think", content="step3"),
        ]
        confidence = reasoner._compute_confidence(steps)

        assert confidence > 0.5  # Should be higher than base

    def test_successful_tools_increase_confidence(self):
        reasoner = ReActReasoner({})

        steps = [
            ReasoningStep(
                phase="act",
                content="Tool call",
                tool_result=ToolResult(status=ToolStatus.OK, output="result", exit_code=0)
            ),
            ReasoningStep(
                phase="act", 
                content="Tool call 2",
                tool_result=ToolResult(status=ToolStatus.OK, output="result2", exit_code=0)
            ),
        ]
        confidence = reasoner._compute_confidence(steps)

        assert confidence > 0.5  # Should be higher than base

    def test_verification_increases_confidence(self):
        reasoner = ReActReasoner({})

        steps = [
            ReasoningStep(phase="verify", content="Checking results..."),
        ]
        confidence = reasoner._compute_confidence(steps)

        assert confidence > 0.5  # Verification adds confidence

    def test_plan_increases_confidence(self):
        reasoner = ReActReasoner({})

        steps = [
            ReasoningStep(phase="plan", content="My approach..."),
        ]
        confidence = reasoner._compute_confidence(steps)

        assert confidence > 0.5  # Planning adds confidence


class TestReasoningStrategies:
    """Test reasoning strategy enum."""

    def test_strategies_exist(self):
        assert ReasoningStrategy.DIRECT.value == "direct"
        assert ReasoningStrategy.CALCULATE.value == "calculate"
        assert ReasoningStrategy.ANALYZE.value == "analyze"
        assert ReasoningStrategy.PROVE.value == "prove"
        assert ReasoningStrategy.CODE.value == "code"


class TestReasoningResult:
    """Test ReasoningResult backward compatibility."""

    def test_thinking_steps_property(self):
        result = ReasoningResult(
            steps=[
                ReasoningStep(phase="plan", content="Planning..."),
                ReasoningStep(phase="think", content="Thinking 1"),
                ReasoningStep(phase="act", content="Tool call"),
                ReasoningStep(phase="think", content="Thinking 2"),
            ],
            final_answer="Answer",
            confidence=0.8,
        )

        # Should only return plan and think phases
        thinking = result.thinking_steps
        assert len(thinking) == 3
        assert "Planning..." in thinking
        assert "Thinking 1" in thinking
        assert "Thinking 2" in thinking

    def test_tool_calls_property(self):
        tool_result = ToolResult(status=ToolStatus.OK, output="result", exit_code=0)
        result = ReasoningResult(
            steps=[
                ReasoningStep(phase="think", content="Thinking"),
                ReasoningStep(phase="act", content="Tool call", tool_result=tool_result),
            ],
            final_answer="Answer",
        )

        # Should return act steps with tool results
        tool_calls = result.tool_calls
        assert len(tool_calls) == 1
        assert tool_calls[0]["result"] == tool_result


class TestStages:
    """Test simplified stage enum."""

    def test_stages_are_simplified(self):
        # Should only have ROUTE, REASON, COMPLETE, FAILED
        assert Stage.ROUTE.value == "route"
        assert Stage.REASON.value == "reason"
        assert Stage.COMPLETE.value == "complete"
        assert Stage.FAILED.value == "failed"

        # Should NOT have old stages
        with pytest.raises(ValueError):
            Stage("plan")
        with pytest.raises(ValueError):
            Stage("execute")
        with pytest.raises(ValueError):
            Stage("critique")


class TestBackwardCompatibility:
    """Test that old class names still work."""

    def test_chain_of_thought_alias(self):
        # ChainOfThoughtReasoner should be an alias for ReActReasoner
        assert ChainOfThoughtReasoner is ReActReasoner
        
        reasoner = ChainOfThoughtReasoner({})
        assert isinstance(reasoner, ReActReasoner)
