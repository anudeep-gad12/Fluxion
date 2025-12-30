"""Complexity detection for auto-routing queries to appropriate strategies.

This module analyzes user queries to determine their complexity level
and recommend the most suitable thinking strategy.
"""

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ComplexityResult:
    """Result of complexity analysis.

    Attributes:
        score: Complexity score from 0.0 (simple) to 1.0 (complex).
        category: Category label ("simple", "moderate", "complex").
        signals: List of signals detected that contributed to the score.
        recommended_strategy: Suggested thinking strategy.
    """

    score: float
    category: str
    signals: List[str]
    recommended_strategy: str


class ComplexityDetector:
    """Detects query complexity to route to appropriate thinking strategy.

    Uses pattern matching and heuristics to analyze queries and determine
    their complexity level. Based on research showing different strategies
    work better for different complexity levels.

    Strategy mapping:
        - simple (score < 0.3): direct (no thinking overhead)
        - moderate (0.3 <= score < 0.7): cot (chain-of-thought)
        - complex (score >= 0.7): self_consistency (multiple paths + voting)
    """

    # Patterns indicating mathematical/calculation content
    MATH_PATTERNS = [
        (r"\d+\s*[\+\-\*\/\^]\s*\d+", "arithmetic expression"),
        (r"\b(solve|calculate|compute|evaluate|find)\b", "calculation keyword"),
        (r"\b(equation|formula|expression|integral|derivative)\b", "math concept"),
        (r"\b(percent|ratio|proportion|fraction)\b", "ratio/percent"),
        (r"\b(sum|product|difference|quotient)\b", "arithmetic operation"),
        (r"\b(graph|plot|function)\b", "math visualization"),
    ]

    # Patterns indicating logical reasoning
    LOGIC_PATTERNS = [
        (r"\b(if|then|therefore|because|since|hence)\b", "conditional logic"),
        (r"\b(prove|deduce|conclude|infer|derive)\b", "deduction"),
        (r"\b(all|every|some|none|any|each)\b", "quantifier"),
        (r"\b(true|false|valid|invalid|correct)\b", "truth value"),
        (r"\b(assume|given|suppose|let)\b", "assumption"),
        (r"\b(contradiction|paradox)\b", "logical construct"),
    ]

    # Patterns indicating multi-step problems
    MULTI_STEP_PATTERNS = [
        (r"\b(first|then|next|finally|after|before)\b", "sequential steps"),
        (r"\b(step\s*by\s*step|one\s*by\s*one)\b", "explicit step request"),
        (r"\b(compare|contrast|analyze|evaluate)\b", "analysis"),
        (r"\b(explain\s*(why|how)|how\s*(does|do|can|would))\b", "explanation"),
        (r"^\d+\.\s|^\*\s|^\-\s", "numbered/bulleted list"),
        (r"\b(multiple|several|various|different)\b", "multiple items"),
    ]

    # Patterns indicating simple queries (reduce complexity)
    SIMPLE_PATTERNS = [
        (r"^(what|who|when|where)\s+is\b", "simple factual question"),
        (r"^(yes|no)\??$", "yes/no question"),
        (r"\b(define|meaning\s+of|what\s+does.*mean)\b", "definition"),
        (r"^(hi|hello|hey|thanks|thank\s*you)\b", "greeting/thanks"),
        (r"^(list|name)\s+(the|some|a few)\b", "simple list"),
    ]

    # Patterns indicating coding tasks
    CODE_PATTERNS = [
        (r"\b(debug|fix|bug|error|exception)\b", "debugging"),
        (r"\b(implement|write|create|build)\s+a?\s*(function|class|method)\b", "implementation"),
        (r"\b(refactor|optimize|improve)\b", "code improvement"),
        (r"```[\s\S]*```", "code block present"),
    ]

    def __init__(
        self,
        simple_threshold: float = 0.3,
        complex_threshold: float = 0.7,
    ):
        """Initialize detector with thresholds.

        Args:
            simple_threshold: Score below this = simple (use direct strategy).
            complex_threshold: Score above this = complex (use self_consistency).
        """
        self.simple_threshold = simple_threshold
        self.complex_threshold = complex_threshold

    def detect(self, query: str) -> ComplexityResult:
        """Analyze query and return complexity assessment.

        Args:
            query: The user's query to analyze.

        Returns:
            ComplexityResult with score, category, signals, and recommended strategy.
        """
        query_lower = query.lower()
        signals = []
        score = 0.5  # Start at neutral

        # Check for simple patterns (decrease score)
        simple_matches = self._count_pattern_matches(query_lower, self.SIMPLE_PATTERNS, signals)
        if simple_matches > 0:
            score -= 0.25 * simple_matches

        # Check for math patterns (increase score)
        math_matches = self._count_pattern_matches(query_lower, self.MATH_PATTERNS, signals)
        if math_matches > 0:
            score += 0.15 * math_matches

        # Check for logic patterns (increase score)
        logic_matches = self._count_pattern_matches(query_lower, self.LOGIC_PATTERNS, signals)
        if logic_matches > 0:
            score += 0.12 * logic_matches

        # Check for multi-step patterns (increase score)
        multi_matches = self._count_pattern_matches(query_lower, self.MULTI_STEP_PATTERNS, signals)
        if multi_matches > 0:
            score += 0.10 * multi_matches

        # Check for code patterns (moderate increase)
        code_matches = self._count_pattern_matches(query_lower, self.CODE_PATTERNS, signals)
        if code_matches > 0:
            score += 0.08 * code_matches

        # Length heuristic
        word_count = len(query.split())
        if word_count > 100:
            signals.append(f"very long query ({word_count} words)")
            score += 0.15
        elif word_count > 50:
            signals.append(f"long query ({word_count} words)")
            score += 0.10
        elif word_count < 5:
            signals.append(f"very short query ({word_count} words)")
            score -= 0.10

        # Question marks heuristic (multiple questions = more complex)
        question_count = query.count("?")
        if question_count > 2:
            signals.append(f"multiple questions ({question_count})")
            score += 0.10
        elif question_count == 0 and word_count > 20:
            signals.append("statement/instruction rather than question")
            score += 0.05

        # Clamp score to valid range
        score = max(0.0, min(1.0, score))

        # Categorize and recommend strategy
        if score < self.simple_threshold:
            category = "simple"
            recommended = "direct"
        elif score < self.complex_threshold:
            category = "moderate"
            recommended = "cot"
        else:
            category = "complex"
            recommended = "self_consistency"

        return ComplexityResult(
            score=round(score, 3),
            category=category,
            signals=signals,
            recommended_strategy=recommended,
        )

    def _count_pattern_matches(
        self,
        text: str,
        patterns: List[tuple],
        signals: List[str],
    ) -> int:
        """Count pattern matches and add to signals.

        Args:
            text: Text to search.
            patterns: List of (pattern, description) tuples.
            signals: List to append signal descriptions to.

        Returns:
            Number of patterns matched.
        """
        matches = 0
        for pattern, description in patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                signals.append(description)
                matches += 1
        return matches


# Convenience function for quick detection
def detect_complexity(query: str) -> ComplexityResult:
    """Quick complexity detection with default settings.

    Args:
        query: The user's query to analyze.

    Returns:
        ComplexityResult with complexity assessment.
    """
    detector = ComplexityDetector()
    return detector.detect(query)
