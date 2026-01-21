"""Unit tests for GAIA answer scorer.

Tests the quasi exact match scoring methodology.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gaia.scorer import (
    AnswerType,
    detect_answer_type,
    normalize_string,
    normalize_number,
    normalize_list,
    normalize_answer,
    numbers_equal,
    score_answer,
    extract_final_answer,
)


class TestDetectAnswerType:
    """Tests for detect_answer_type function."""

    def test_detect_string(self):
        """Detects plain string answers."""
        assert detect_answer_type("Paris") == AnswerType.STRING
        assert detect_answer_type("hello world") == AnswerType.STRING
        assert detect_answer_type("Yes") == AnswerType.STRING

    def test_detect_number_integer(self):
        """Detects integer numbers."""
        assert detect_answer_type("42") == AnswerType.NUMBER
        assert detect_answer_type("0") == AnswerType.NUMBER
        assert detect_answer_type("-5") == AnswerType.NUMBER

    def test_detect_number_decimal(self):
        """Detects decimal numbers."""
        assert detect_answer_type("3.14") == AnswerType.NUMBER
        assert detect_answer_type("0.5") == AnswerType.NUMBER
        assert detect_answer_type("-2.5") == AnswerType.NUMBER

    def test_detect_number_scientific(self):
        """Detects scientific notation."""
        assert detect_answer_type("1e10") == AnswerType.NUMBER
        assert detect_answer_type("3.14e-5") == AnswerType.NUMBER

    def test_detect_list(self):
        """Detects comma-separated lists."""
        assert detect_answer_type("a, b, c") == AnswerType.LIST
        assert detect_answer_type("Paris, London, Tokyo") == AnswerType.LIST
        assert detect_answer_type("1, 2, 3") == AnswerType.LIST


class TestNormalizeString:
    """Tests for normalize_string function."""

    def test_lowercase(self):
        """Converts to lowercase."""
        assert normalize_string("PARIS") == "paris"
        assert normalize_string("ParIs") == "paris"

    def test_strip_whitespace(self):
        """Strips leading/trailing whitespace."""
        assert normalize_string("  paris  ") == "paris"
        assert normalize_string("\tparis\n") == "paris"

    def test_collapse_whitespace(self):
        """Collapses multiple whitespace."""
        assert normalize_string("hello   world") == "hello world"
        assert normalize_string("a  b  c") == "a b c"

    def test_remove_trailing_punctuation(self):
        """Removes trailing punctuation."""
        assert normalize_string("paris.") == "paris"
        assert normalize_string("yes!") == "yes"
        assert normalize_string("answer?") == "answer"

    def test_preserve_internal_punctuation(self):
        """Preserves internal punctuation."""
        assert normalize_string("u.s.a") == "u.s.a"
        assert normalize_string("isn't") == "isn't"


class TestNormalizeNumber:
    """Tests for normalize_number function."""

    def test_integer(self):
        """Parses integers."""
        assert normalize_number("42") == 42.0
        assert normalize_number("-5") == -5.0

    def test_decimal(self):
        """Parses decimals."""
        assert normalize_number("3.14") == 3.14
        assert normalize_number("0.5") == 0.5

    def test_scientific(self):
        """Parses scientific notation."""
        assert normalize_number("1e10") == 1e10
        assert normalize_number("3.14e-5") == 3.14e-5

    def test_whitespace(self):
        """Handles whitespace."""
        assert normalize_number("  42  ") == 42.0

    def test_invalid(self):
        """Returns None for invalid input."""
        assert normalize_number("abc") is None
        assert normalize_number("") is None


class TestNormalizeList:
    """Tests for normalize_list function."""

    def test_basic_list(self):
        """Normalizes basic lists."""
        assert normalize_list("a, b, c") == {"a", "b", "c"}

    def test_whitespace(self):
        """Handles whitespace in items."""
        assert normalize_list("  a  ,  b  ,  c  ") == {"a", "b", "c"}

    def test_case_insensitive(self):
        """Normalizes case in items."""
        assert normalize_list("Paris, LONDON, tokyo") == {"paris", "london", "tokyo"}

    def test_empty_items(self):
        """Filters empty items."""
        assert normalize_list("a, , b") == {"a", "b"}


class TestNumbersEqual:
    """Tests for numbers_equal function."""

    def test_exact_equal(self):
        """Equal numbers match."""
        assert numbers_equal(42.0, 42.0) is True
        assert numbers_equal(3.14, 3.14) is True

    def test_within_tolerance(self):
        """Numbers within tolerance match."""
        assert numbers_equal(3.14, 3.141) is True
        assert numbers_equal(100.0, 100.05) is True

    def test_outside_tolerance(self):
        """Numbers outside tolerance don't match."""
        assert numbers_equal(3.14, 3.2) is False
        assert numbers_equal(100.0, 101.0) is False

    def test_zero(self):
        """Handles zero correctly."""
        assert numbers_equal(0.0, 0.0) is True
        assert numbers_equal(0.0, 0.0001) is True
        assert numbers_equal(0.0, 1.0) is False


class TestNormalizeAnswer:
    """Tests for normalize_answer function."""

    def test_auto_detect_string(self):
        """Auto-detects and normalizes strings."""
        assert normalize_answer("PARIS") == "paris"

    def test_auto_detect_number(self):
        """Auto-detects and normalizes numbers."""
        assert normalize_answer("42.0") == "42"
        assert normalize_answer("3.14") == "3.14"

    def test_auto_detect_list(self):
        """Auto-detects and normalizes lists."""
        # Lists are sorted for consistent comparison
        assert normalize_answer("c, b, a") == "a, b, c"

    def test_explicit_type(self):
        """Respects explicit type."""
        assert normalize_answer("42", AnswerType.STRING) == "42"


class TestScoreAnswer:
    """Tests for score_answer function."""

    def test_exact_string_match(self):
        """Scores exact string matches."""
        result = score_answer("Paris", "Paris", task_id="test1")
        assert result.correct is True
        assert result.score == 1.0
        assert result.match_type == "string"

    def test_case_insensitive_match(self):
        """Scores case-insensitive string matches."""
        result = score_answer("paris", "Paris", task_id="test2")
        assert result.correct is True

    def test_whitespace_normalized_match(self):
        """Scores whitespace-normalized matches."""
        result = score_answer("  paris  ", "Paris", task_id="test3")
        assert result.correct is True

    def test_punctuation_normalized_match(self):
        """Scores punctuation-normalized matches."""
        result = score_answer("Paris.", "Paris", task_id="test4")
        assert result.correct is True

    def test_string_mismatch(self):
        """Scores string mismatches."""
        result = score_answer("London", "Paris", task_id="test5")
        assert result.correct is False
        assert result.score == 0.0
        assert result.match_type == "string_mismatch"

    def test_numeric_match(self):
        """Scores numeric matches."""
        result = score_answer("3.140", "3.14", task_id="test6")
        assert result.correct is True
        assert result.match_type == "numeric"

    def test_numeric_tolerance(self):
        """Scores numeric matches with tolerance."""
        result = score_answer("3.141", "3.14", task_id="test7")
        assert result.correct is True

    def test_numeric_mismatch(self):
        """Scores numeric mismatches."""
        result = score_answer("4.0", "3.14", task_id="test8")
        assert result.correct is False

    def test_list_match_same_order(self):
        """Scores list matches with same order."""
        result = score_answer("a, b, c", "a, b, c", task_id="test9")
        assert result.correct is True
        assert result.match_type == "list"

    def test_list_match_different_order(self):
        """Scores list matches with different order."""
        result = score_answer("c, b, a", "a, b, c", task_id="test10")
        assert result.correct is True

    def test_list_mismatch(self):
        """Scores list mismatches."""
        result = score_answer("a, b, d", "a, b, c", task_id="test11")
        assert result.correct is False

    def test_missing_prediction(self):
        """Handles missing predictions."""
        result = score_answer(None, "Paris", task_id="test12")
        assert result.correct is False
        assert result.match_type == "missing"

    def test_empty_prediction(self):
        """Handles empty predictions."""
        result = score_answer("", "Paris", task_id="test13")
        assert result.correct is False
        assert result.match_type == "missing"


class TestExtractFinalAnswer:
    """Tests for extract_final_answer function."""

    def test_short_answer(self):
        """Extracts short answers directly."""
        assert extract_final_answer("Paris") == "Paris"

    def test_answer_pattern(self):
        """Extracts from 'answer is' pattern."""
        assert extract_final_answer("The answer is Paris.") == "Paris"
        assert extract_final_answer("The final answer is 42") == "42"

    def test_multiline(self):
        """Extracts first line from multiline."""
        response = "Paris\nThis is the capital of France."
        assert extract_final_answer(response) == "Paris"

    def test_empty(self):
        """Handles empty input."""
        assert extract_final_answer("") == ""
        assert extract_final_answer(None) == ""
