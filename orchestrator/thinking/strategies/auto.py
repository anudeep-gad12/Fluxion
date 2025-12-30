"""Auto strategy - routes to appropriate strategy based on complexity.

This strategy analyzes the query complexity and automatically selects
the most appropriate thinking strategy:
- Simple queries -> Direct (fast, no overhead)
- Moderate queries -> Chain-of-Thought (balanced)
- Complex queries -> Self-Consistency (maximum accuracy)
"""

from typing import Callable, List, Optional

from orchestrator.thinking.base import ThinkingResult, ThinkingStrategy
from orchestrator.thinking.complexity import ComplexityDetector
from orchestrator.thinking.strategies.direct import DirectStrategy
from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy
from orchestrator.thinking.strategies.self_consistency import SelfConsistencyStrategy


class AutoStrategy(ThinkingStrategy):
    """Auto-routing strategy based on query complexity.

    This strategy:
    - Analyzes the user query for complexity signals
    - Routes to the appropriate sub-strategy
    - Adds routing metadata to the result

    Routing logic:
    - score < 0.3 (simple): direct strategy
    - 0.3 <= score < 0.7 (moderate): cot strategy
    - score >= 0.7 (complex): self_consistency strategy (falls back to cot if not available)
    """

    def __init__(
        self,
        simple_threshold: float = 0.3,
        complex_threshold: float = 0.7,
    ):
        """Initialize auto strategy with thresholds.

        Args:
            simple_threshold: Score below this uses direct strategy.
            complex_threshold: Score above this uses self_consistency (or cot fallback).
        """
        self.detector = ComplexityDetector(
            simple_threshold=simple_threshold,
            complex_threshold=complex_threshold,
        )
        self.simple_threshold = simple_threshold
        self.complex_threshold = complex_threshold

        # Initialize sub-strategies
        self.direct = DirectStrategy()
        self.cot = ChainOfThoughtStrategy()
        self.self_consistency = SelfConsistencyStrategy(n_samples=3, temperature=0.7)

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return "auto"

    async def think(
        self,
        messages: List[dict],
        model_call: Callable,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> ThinkingResult:
        """Execute auto-routing strategy.

        Args:
            messages: List of message dicts to send to the model.
            model_call: Async function to call the model.
            event_callback: Optional callback for emitting events.

        Returns:
            ThinkingResult from the selected sub-strategy.
        """
        # Extract user query from messages (last user message)
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

        # Detect complexity with conversation history for context awareness
        complexity = self.detector.detect(query, history=messages)

        # Emit complexity detection event
        self.emit_event(
            event_callback,
            "COMPLEXITY_DETECTED",
            score=complexity.score,
            category=complexity.category,
            signals=complexity.signals,
            recommended_strategy=complexity.recommended_strategy,
        )

        # Select strategy based on complexity
        if complexity.score < self.simple_threshold:
            strategy = self.direct
            selected_name = "direct"
        elif complexity.score < self.complex_threshold:
            strategy = self.cot
            selected_name = "cot"
        else:
            # Complex: use self_consistency for maximum accuracy
            strategy = self.self_consistency
            selected_name = "self_consistency"

        # Emit strategy selection event
        self.emit_event(
            event_callback,
            "STRATEGY_SELECTED",
            strategy=selected_name,
            complexity_score=complexity.score,
            complexity_category=complexity.category,
        )

        # Delegate to selected strategy
        result = await strategy.think(messages, model_call, event_callback)

        # Add auto-routing metadata
        result.metadata["auto_routing"] = {
            "complexity_score": complexity.score,
            "complexity_category": complexity.category,
            "complexity_signals": complexity.signals,
            "selected_strategy": selected_name,
            "recommended_strategy": complexity.recommended_strategy,
        }

        return result
