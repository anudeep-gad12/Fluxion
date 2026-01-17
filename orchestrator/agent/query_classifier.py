"""Query classifier for detecting calculation/physics queries.

This module provides keyword-based classification to detect queries that
require computational tools (python_execute) vs general web research.

Usage:
    classifier = QueryClassifier()
    result = classifier.classify("What is the kinetic energy of a 5kg object at 10m/s?")
    # result.query_type == QueryType.CALCULATION
    # result.recommended_tool_choice == "python_execute"
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)


class QueryType(Enum):
    """Classification of query types for tool selection."""

    GENERAL = "general"  # Default - no special handling
    CALCULATION = "calculation"  # Requires python_execute


@dataclass
class ClassificationResult:
    """Result from query classification.

    Attributes:
        query_type: The detected query type.
        confidence: Confidence score (number of matched patterns).
        matched_patterns: List of patterns that matched.
        recommended_tool_choice: Suggested tool_choice parameter value.
    """

    query_type: QueryType
    confidence: int
    matched_patterns: List[str]
    recommended_tool_choice: Optional[str] = None


class QueryClassifier:
    """Keyword-based query classifier.

    Detects calculation-heavy queries using pattern matching.
    Does NOT use LLM for classification - purely rule-based.

    Attributes:
        DEFAULT_CALCULATION_KEYWORDS: Keywords indicating calculation needed.
        DEFAULT_PHYSICS_UNITS: Physics unit patterns.
        SIMPLE_ARITHMETIC_PATTERNS: Patterns for simple math (allow direct answer).
    """

    DEFAULT_CALCULATION_KEYWORDS: Set[str] = {
        # Explicit code execution indicators (high confidence)
        "python",
        "code",
        "script",
        "program",
        "execute",
        "run code",
        # Action words
        "calculate",
        "compute",
        "solve",
        "derive",
        "evaluate",
        "determine",
        "find the value",
        # Math terms
        "square root",
        "cube root",
        "nth root",
        "equation",
        "formula",
        "integral",
        "derivative",
        "logarithm",
        "exponential",
        "factorial",
        # Physics terms
        "energy",
        "kinetic",
        "potential",
        "momentum",
        "velocity",
        "acceleration",
        "force",
        "mass",
        "weight",
        "power",
        "work",
        "torque",
        "frequency",
        "wavelength",
        "amplitude",
        "period",
        "temperature",
        "pressure",
        "volume",
        "density",
        "electric",
        "magnetic",
        "current",
        "voltage",
        "resistance",
        "gravity",
        "gravitational",
        "orbital",
        "centripetal",
        "relativistic",
    }

    DEFAULT_PHYSICS_UNITS: Set[str] = {
        # Energy units
        "joule",
        "joules",
        "ev",
        "kev",
        "mev",
        "gev",
        "tev",
        "erg",
        "calorie",
        "calories",
        # Mass units
        "kg",
        "kilogram",
        "gram",
        "microgram",
        # Length/distance units
        "meter",
        "meters",
        "km",
        "cm",
        "mm",
        "nm",
        # Velocity units
        "m/s",
        "km/h",
        "mph",
        # Force units
        "newton",
        "newtons",
        "dyne",
        # Pressure units
        "pascal",
        "pa",
        "kpa",
        "bar",
        "atm",
        "psi",
        # Temperature units
        "kelvin",
        "celsius",
        "fahrenheit",
        # Electrical units
        "ampere",
        "amp",
        "volt",
        "ohm",
        "watt",
        "coulomb",
        "farad",
        "tesla",
        # Frequency units
        "hertz",
        "hz",
        "khz",
        "mhz",
        "ghz",
        # Other
        "radian",
        "degree",
        "degrees",
    }

    # Patterns for simple arithmetic (allow direct answer)
    SIMPLE_ARITHMETIC_PATTERNS: List[str] = [
        r"^\d+\s*[\+\-\*\/]\s*\d+$",  # "5 + 3"
        r"^what\s+is\s+\d+\s*[\+\-\*\/x]\s*\d+",  # "what is 5 + 3"
        r"^\d+\s*(plus|minus|times|divided by)\s*\d+",  # "5 plus 3"
    ]

    def __init__(
        self,
        calculation_keywords: Optional[Set[str]] = None,
        physics_units: Optional[Set[str]] = None,
        simple_arithmetic_patterns: Optional[List[str]] = None,
        min_confidence_for_tool_choice: int = 2,
    ) -> None:
        """Initialize classifier.

        Args:
            calculation_keywords: Custom keywords (or use defaults).
            physics_units: Custom physics units (or use defaults).
            simple_arithmetic_patterns: Patterns for simple arithmetic.
            min_confidence_for_tool_choice: Minimum matches to enforce tool_choice.
        """
        self._keywords = calculation_keywords or self.DEFAULT_CALCULATION_KEYWORDS
        self._units = physics_units or self.DEFAULT_PHYSICS_UNITS
        self._simple_patterns = (
            simple_arithmetic_patterns or self.SIMPLE_ARITHMETIC_PATTERNS
        )
        self._min_confidence = min_confidence_for_tool_choice

        # Compile patterns for efficiency
        self._simple_compiled = [
            re.compile(p, re.IGNORECASE) for p in self._simple_patterns
        ]

    def classify(self, query: str) -> ClassificationResult:
        """Classify a query.

        Args:
            query: User's query text.

        Returns:
            ClassificationResult with type, confidence, and recommendations.
        """
        query_lower = query.lower()
        matched: List[str] = []

        # Check for simple arithmetic (allow direct answer)
        for pattern in self._simple_compiled:
            if pattern.search(query_lower):
                logger.debug(
                    "Query classified as simple arithmetic",
                    extra={"query": query[:100]},
                )
                return ClassificationResult(
                    query_type=QueryType.GENERAL,
                    confidence=0,
                    matched_patterns=["simple_arithmetic"],
                    recommended_tool_choice=None,
                )

        # Check calculation keywords
        for keyword in self._keywords:
            if keyword in query_lower:
                matched.append(f"keyword:{keyword}")

        # Check physics units (use word boundary matching)
        for unit in self._units:
            # Match unit as whole word or with number prefix
            # e.g., "5 kg", "10m/s", "joules"
            pattern = rf"(?:\d+\s*)?{re.escape(unit)}(?:\s|$|[,.\)])"
            if re.search(pattern, query_lower):
                matched.append(f"unit:{unit}")

        # Check for numeric patterns suggesting calculation
        if re.search(r"\d+\.?\d*\s*[\*\/\^]\s*\d", query_lower):
            matched.append("pattern:math_operator")
        if re.search(r"\d+\.?\d*e[+-]?\d+", query_lower):
            matched.append("pattern:scientific_notation")
        if re.search(r"\b(sin|cos|tan|log|ln|sqrt|exp)\s*\(", query_lower):
            matched.append("pattern:math_function")

        # Check for speed of light (special case)
        if re.search(r"\b0\.\d+\s*c\b", query_lower):
            matched.append("unit:c")  # e.g., "0.96c"

        # Determine classification
        confidence = len(matched)

        if confidence >= 1:
            # Any physics/calculation indicator = CALCULATION
            query_type = QueryType.CALCULATION
            # If high confidence, enforce tool usage
            tool_choice = (
                "python_execute" if confidence >= self._min_confidence else None
            )
        else:
            query_type = QueryType.GENERAL
            tool_choice = None

        logger.debug(
            "Query classified",
            extra={
                "query": query[:100],
                "query_type": query_type.value,
                "confidence": confidence,
                "matched_count": len(matched),
            },
        )

        return ClassificationResult(
            query_type=query_type,
            confidence=confidence,
            matched_patterns=matched,
            recommended_tool_choice=tool_choice,
        )
