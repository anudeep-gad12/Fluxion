"""Tests for QueryClassifier."""

import pytest

from orchestrator.agent.query_classifier import (
    ClassificationResult,
    QueryClassifier,
    QueryType,
)


class TestQueryClassifier:
    """Tests for QueryClassifier."""

    def test_simple_arithmetic_is_general(self):
        """Simple arithmetic like '5 + 3' allows direct answer."""
        classifier = QueryClassifier()

        test_cases = [
            "5 + 3",
            "10 - 2",
            "4 * 7",
            "100 / 5",
            "What is 5 + 3?",
            "what is 10 * 2",
            "5 plus 3",
            "10 times 2",
        ]

        for query in test_cases:
            result = classifier.classify(query)
            assert result.query_type == QueryType.GENERAL, f"Failed for: {query}"
            assert "simple_arithmetic" in result.matched_patterns
            assert result.recommended_tool_choice is None

    def test_physics_energy_is_calculation(self):
        """Physics energy questions are CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify(
            "What is the kinetic energy of a 5kg object at 10m/s?"
        )

        assert result.query_type == QueryType.CALCULATION
        assert result.confidence >= 2
        assert result.recommended_tool_choice == "python_execute"
        assert any("energy" in p or "kinetic" in p for p in result.matched_patterns)

    def test_physics_units_trigger_calculation(self):
        """Physics units like GeV, MeV trigger CALCULATION."""
        classifier = QueryClassifier()

        queries = [
            "Convert 1 GeV to joules",
            "What is 500 MeV in electron volts?",
            "Calculate the energy in joules for 10 eV",
            "What is 5 kg at rest mass?",
            "Find the force in newtons",
        ]

        for query in queries:
            result = classifier.classify(query)
            assert result.query_type == QueryType.CALCULATION, f"Failed for: {query}"

    def test_calculate_keyword_triggers(self):
        """'Calculate' keyword triggers CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify(
            "Calculate the force needed to accelerate 10kg at 5m/s^2"
        )

        assert result.query_type == QueryType.CALCULATION
        assert any("calculate" in p for p in result.matched_patterns)

    def test_web_research_query_is_general(self):
        """General research queries stay GENERAL."""
        classifier = QueryClassifier()

        queries = [
            "What is the population of Tokyo?",
            "Who won the 2024 election?",
            "What are the best restaurants in Paris?",
            "Tell me about climate change",
            "What is machine learning?",
        ]

        for query in queries:
            result = classifier.classify(query)
            assert result.query_type == QueryType.GENERAL, f"Failed for: {query}"
            assert result.recommended_tool_choice is None

    def test_confidence_threshold(self):
        """Tool choice only enforced above confidence threshold."""
        # Default threshold is 2
        classifier = QueryClassifier(min_confidence_for_tool_choice=3)

        # Only one keyword match - below threshold
        result = classifier.classify("What is the energy?")
        assert result.query_type == QueryType.CALCULATION
        assert result.recommended_tool_choice is None  # Below threshold

        # Multiple matches - above threshold
        result = classifier.classify("Calculate the kinetic energy in joules")
        assert result.query_type == QueryType.CALCULATION
        assert result.recommended_tool_choice == "python_execute"  # Above threshold

    def test_rhic_query_is_calculation(self):
        """The original RHIC query that failed should be CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify(
            "What is the energy of the Relativistic Heavy Ion Collider (RHIC) "
            "so that the speed of the nucleus X is equal to 0.96c? "
            "Knowing that X is defined as Li with A=6."
        )

        assert result.query_type == QueryType.CALCULATION
        assert result.confidence >= 2
        assert result.recommended_tool_choice == "python_execute"
        # Should match: energy, relativistic, 0.96c (speed of light)
        assert any("energy" in p for p in result.matched_patterns)

    def test_scientific_notation_triggers(self):
        """Scientific notation in query triggers CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify("What is 3e8 meters per second?")

        assert result.query_type == QueryType.CALCULATION
        assert "pattern:scientific_notation" in result.matched_patterns

    def test_math_functions_trigger(self):
        """Math functions like sin, cos, log trigger CALCULATION."""
        classifier = QueryClassifier()

        queries = [
            "What is sin(45)?",
            "Calculate cos(pi/4)",
            "Find log(100)",
            "What is sqrt(256)?",
        ]

        for query in queries:
            result = classifier.classify(query)
            assert result.query_type == QueryType.CALCULATION, f"Failed for: {query}"
            assert "pattern:math_function" in result.matched_patterns

    def test_speed_of_light_triggers(self):
        """Speed of light notation (0.96c) triggers CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify("What happens at 0.96c?")

        assert result.query_type == QueryType.CALCULATION
        assert "unit:c" in result.matched_patterns

    def test_custom_keywords(self):
        """Custom keywords can be provided."""
        classifier = QueryClassifier(
            calculation_keywords={"foobar"},
            min_confidence_for_tool_choice=1,
        )

        result = classifier.classify("Calculate foobar")
        assert result.query_type == QueryType.CALCULATION
        assert result.recommended_tool_choice == "python_execute"

    def test_classification_result_dataclass(self):
        """ClassificationResult dataclass works correctly."""
        result = ClassificationResult(
            query_type=QueryType.CALCULATION,
            confidence=3,
            matched_patterns=["keyword:energy", "unit:joules"],
            recommended_tool_choice="python_execute",
        )

        assert result.query_type == QueryType.CALCULATION
        assert result.confidence == 3
        assert len(result.matched_patterns) == 2
        assert result.recommended_tool_choice == "python_execute"

    def test_empty_query(self):
        """Empty query returns GENERAL."""
        classifier = QueryClassifier()
        result = classifier.classify("")

        assert result.query_type == QueryType.GENERAL
        assert result.confidence == 0

    def test_momentum_calculation(self):
        """Momentum calculations should be CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify("What is the momentum of a 2kg ball moving at 5m/s?")

        assert result.query_type == QueryType.CALCULATION
        assert result.recommended_tool_choice == "python_execute"

    def test_temperature_conversion(self):
        """Temperature conversions should be CALCULATION."""
        classifier = QueryClassifier()
        result = classifier.classify("Convert 100 celsius to fahrenheit")

        assert result.query_type == QueryType.CALCULATION
