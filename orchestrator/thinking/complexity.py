"""Intent-based routing for auto-selecting thinking strategies.

This module analyzes user queries to determine if reasoning is needed,
using intent detection rather than topic classification.

Design philosophy:
- Default to direct (no thinking) unless clear signals suggest otherwise
- Explicit user requests always override heuristics
- Conversation context matters (follow-ups usually don't need thinking)
- Fast bailouts for obviously simple queries
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RoutingDecision:
    """Result of routing analysis.

    Attributes:
        should_think: Whether to use reasoning (CoT) strategy.
        reason: Human-readable explanation for the decision.
        signals: List of signals detected.
        confidence: How confident we are (0.0-1.0).
    """

    should_think: bool
    reason: str
    signals: List[str]
    confidence: float = 0.8


class IntentRouter:
    """Routes queries to appropriate strategy based on intent, not topic.

    Priority order:
    1. Explicit user request ("use thinking", "reason through this")
    2. Fast bailout (greetings, meta questions, acknowledgments)
    3. Follow-up detection (short queries after long responses)
    4. Reasoning triggers (explain, compare, debug, multi-step)
    5. Default: no thinking (direct strategy)
    """

    # === EXPLICIT TRIGGERS ===
    # User explicitly asks for reasoning - ALWAYS honor this
    EXPLICIT_THINKING_PATTERNS = [
        (r"\b(use|enable|turn on|activate)\s*(thinking|reasoning|cot|chain.of.thought)\b", "explicit thinking request"),
        (r"\b(think|reason)\s*(about|through|step.by.step|carefully|deeply)\b", "explicit thinking request"),
        (r"\blet'?s?\s*think\b", "explicit thinking request"),
        (r"\b(think harder|think more|think again)\b", "explicit thinking request"),
        (r"\breason(ing)?\s*(mode|enabled?)\b", "explicit reasoning mode"),
        (r"\b(with|using)\s*(reasoning|thinking|cot)\b", "explicit reasoning request"),
    ]

    # === FAST BAILOUTS ===
    # These NEVER need thinking - return direct immediately
    BAILOUT_PATTERNS = [
        # Greetings and social
        (r"^(hi|hello|hey|yo|sup|hiya|howdy)[\s\!\.\?]*$", "greeting"),
        (r"^(thanks?|thank\s*you|thx|ty|cheers|appreciated?)[\s\!\.\?]*$", "thanks"),
        (r"^(bye|goodbye|see\s*ya|later|cya)[\s\!\.\?]*$", "farewell"),
        (r"^(ok|okay|k|sure|alright|got\s*it|sounds?\s*good|cool|nice|great)[\s\!\.\?]*$", "acknowledgment"),
        (r"^(yes|no|yep|nope|yeah|nah|yup)[\s\!\.\?]*$", "yes/no response"),

        # Meta questions about the conversation/model
        (r"\b(how much|how long|how many)\s*(did you|have you|were you)\s*(think|thought|reason)", "meta about thinking"),
        (r"\b(what|how)\s*(did you|are you)\s*(think|do|say|respond)", "meta about response"),
        (r"\bcan you (remember|recall|see)\b", "meta about capabilities"),
        (r"\b(your|the) (last|previous) (response|answer|message)\b", "meta about previous"),

        # Simple commands
        (r"^(stop|wait|hold on|pause|cancel|never\s*mind)[\s\!\.\?]*$", "command"),
        (r"^(continue|go on|proceed|more|next)[\s\!\.\?]*$", "continuation"),
    ]

    # === REASONING TRIGGERS ===
    # These suggest thinking would help
    REASONING_PATTERNS = [
        # Explicit explanation requests
        (r"\b(explain|describe)\s*(how|why|what|the)\b", "explanation request"),
        (r"\bwhy\s+(does|do|is|are|did|would|should|can|won't|doesn't)\b", "why question"),
        (r"\bhow\s+(does|do|is|are|would|should|can|could)\s+\w+\s+work\b", "how-it-works"),

        # Comparison and analysis
        (r"\b(compare|contrast|versus|vs\.?|difference\s*between)\b", "comparison"),
        (r"\b(pros?\s*(and|&)?\s*cons?|trade.?offs?|advantages?\s*(and|&)?\s*disadvantages?)\b", "trade-off analysis"),
        (r"\b(analyze|evaluate|assess|review)\b", "analysis request"),

        # Multi-step / complex tasks
        (r"\b(step\s*by\s*step|one\s*by\s*one|walk\s*me\s*through)\b", "step-by-step request"),
        (r"\b(solve|calculate|compute|figure\s*out)\b.*\b(then|and\s*then|after\s*that|next)\b", "multi-step problem"),
        (r"\b(first|then|finally|after|before|next|lastly)\b.*\b(first|then|finally|after|before|next|lastly)\b", "sequential steps"),

        # Debugging and troubleshooting
        (r"\b(debug|fix|what'?s?\s*wrong|why\s*(is|isn't|does|doesn't)\s*\w+\s*work)", "debugging"),
        (r"\b(error|bug|issue|problem|broken|failing|crashed)\b", "error mention"),

        # Complex reasoning indicators
        (r"\b(if|assuming|suppose|given\s*that|considering)\b.*\b(then|would|should|could)\b", "conditional reasoning"),
        (r"\b(prove|derive|deduce|conclude|infer)\b", "logical deduction"),

        # Scientific/technical problem solving
        (r"\b(identify|determine|find|predict)\s+(the\s+)?(number|amount|value|result|product|structure)\b", "scientific analysis"),
        (r"\b(nmr|ir|mass\s*spec|spectroscop|chromatograph|titrat|synthesis)\b", "chemistry/lab technique"),
        (r"\b(reaction|mechanism|equilibrium|kinetics|thermodynamic)\b", "chemistry concept"),
        (r"\b(integral|derivative|differential|equation|matrix|vector|eigenvalue)\b", "advanced math"),
        (r"\b(algorithm|complexity|big\s*o|recursion|dynamic\s*programming)\b", "cs/algorithms"),
        (r"\b(circuit|voltage|current|resistance|capacit|induct)\b", "electronics/physics"),

        # Multi-step reactions or processes (arrows indicate steps)
        (r"->|→|-->|==>", "multi-step process"),

        # Quantitative problems
        (r"\b(solve|calculate|compute|find)\s+(for\s+)?\w+", "calculation request"),
    ]

    # === SHORT QUERY THRESHOLD ===
    # Very short queries after a response are usually follow-ups
    SHORT_QUERY_WORDS = 8

    def __init__(self):
        """Initialize the intent router."""
        pass

    def route(
        self,
        query: str,
        conversation_history: Optional[List[dict]] = None,
    ) -> RoutingDecision:
        """Determine if query needs reasoning.

        Args:
            query: The user's current query.
            conversation_history: List of previous messages (optional).

        Returns:
            RoutingDecision with should_think, reason, and signals.
        """
        query_lower = query.lower().strip()
        signals = []

        # === PRIORITY 1: Explicit user request ===
        for pattern, desc in self.EXPLICIT_THINKING_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                signals.append(f"explicit: {desc}")
                return RoutingDecision(
                    should_think=True,
                    reason="User explicitly requested reasoning",
                    signals=signals,
                    confidence=1.0,
                )

        # === PRIORITY 2: Fast bailout ===
        for pattern, desc in self.BAILOUT_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                signals.append(f"bailout: {desc}")
                return RoutingDecision(
                    should_think=False,
                    reason=f"Simple query ({desc})",
                    signals=signals,
                    confidence=0.95,
                )

        # === PRIORITY 3: Follow-up detection ===
        if conversation_history and len(conversation_history) >= 2:
            if self._is_likely_followup(query, conversation_history):
                signals.append("context: likely follow-up")
                return RoutingDecision(
                    should_think=False,
                    reason="Likely a follow-up question",
                    signals=signals,
                    confidence=0.7,
                )

        # === PRIORITY 4: Reasoning triggers ===
        reasoning_matches = []
        for pattern, desc in self.REASONING_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                reasoning_matches.append(desc)
                signals.append(f"reasoning: {desc}")

        if len(reasoning_matches) >= 2:
            # Multiple reasoning signals = definitely think
            return RoutingDecision(
                should_think=True,
                reason=f"Multiple reasoning signals: {', '.join(reasoning_matches[:3])}",
                signals=signals,
                confidence=0.9,
            )
        elif len(reasoning_matches) == 1:
            # Single signal = probably think
            return RoutingDecision(
                should_think=True,
                reason=f"Reasoning signal: {reasoning_matches[0]}",
                signals=signals,
                confidence=0.75,
            )

        # === PRIORITY 5: Default - no thinking ===
        signals.append("default: no strong signals")
        return RoutingDecision(
            should_think=False,
            reason="No reasoning signals detected, using direct response",
            signals=signals,
            confidence=0.6,
        )

    def _is_likely_followup(
        self,
        query: str,
        history: List[dict],
    ) -> bool:
        """Detect if query is likely a follow-up.

        Args:
            query: Current query.
            history: Conversation history.

        Returns:
            True if this looks like a follow-up question.
        """
        query_words = len(query.split())

        # Very short query after a conversation
        if query_words <= self.SHORT_QUERY_WORDS:
            # Check for pronouns referencing previous context
            if re.search(r"\b(it|that|this|those|them|these|the above)\b", query, re.I):
                return True

            # Check for clarification patterns
            if re.search(r"\b(what|how|why)\s+(do you mean|about|exactly)\b", query, re.I):
                return True

            # Get last assistant message
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    assistant_response = msg.get("content", "")
                    # Short query after long response = likely follow-up
                    if len(assistant_response) > 200:
                        return True
                    break

        return False


# === BACKWARDS COMPATIBILITY ===
# Keep the old interface working for existing code

@dataclass
class ComplexityResult:
    """Legacy result format for backwards compatibility."""

    score: float
    category: str
    signals: List[str]
    recommended_strategy: str


class ComplexityDetector:
    """Legacy interface wrapping IntentRouter for backwards compatibility."""

    def __init__(
        self,
        simple_threshold: float = 0.3,
        complex_threshold: float = 0.7,
    ):
        self.simple_threshold = simple_threshold
        self.complex_threshold = complex_threshold
        self._router = IntentRouter()

    def detect(self, query: str, history: Optional[List[dict]] = None) -> ComplexityResult:
        """Analyze query using intent-based routing.

        Args:
            query: The user's query.
            history: Optional conversation history.

        Returns:
            ComplexityResult with score, category, and recommended strategy.
        """
        decision = self._router.route(query, history)

        # Convert to legacy score format
        if decision.should_think:
            if decision.confidence >= 0.9:
                score = 0.8  # High confidence reasoning = complex
                category = "complex"
                strategy = "cot"
            else:
                score = 0.5  # Medium confidence = moderate
                category = "moderate"
                strategy = "cot"
        else:
            if decision.confidence >= 0.9:
                score = 0.1  # High confidence direct = simple
            else:
                score = 0.25  # Lower confidence direct
            category = "simple"
            strategy = "direct"

        return ComplexityResult(
            score=score,
            category=category,
            signals=decision.signals,
            recommended_strategy=strategy,
        )


# Convenience function
def detect_complexity(query: str, history: Optional[List[dict]] = None) -> ComplexityResult:
    """Quick complexity detection with default settings."""
    detector = ComplexityDetector()
    return detector.detect(query, history)


def should_think(query: str, history: Optional[List[dict]] = None) -> bool:
    """Simple boolean: should we use reasoning for this query?"""
    router = IntentRouter()
    decision = router.route(query, history)
    return decision.should_think
