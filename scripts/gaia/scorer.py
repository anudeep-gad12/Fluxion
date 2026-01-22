"""GAIA Answer Scorer.

Implements the official GAIA quasi exact match scoring methodology
from the arXiv paper (https://arxiv.org/abs/2311.12983).

Answer types:
- String: case-insensitive, whitespace-normalized comparison
- Number: parsed as float with tolerance comparison
- List: comma-separated items compared as sets
"""

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx


class AnswerType(Enum):
    """Type of GAIA answer."""
    STRING = "string"
    NUMBER = "number"
    LIST = "list"


@dataclass
class ScoreResult:
    """Result of scoring an answer.

    Attributes:
        task_id: Question identifier.
        correct: Whether answer is correct.
        score: Score value (0.0 or 1.0).
        match_type: How the match was determined.
        expected: Ground truth answer.
        actual: Predicted answer.
        answer_type: Detected answer type.
        notes: Additional scoring notes.
    """
    task_id: str
    correct: bool
    score: float
    match_type: str
    expected: str
    actual: Optional[str]
    answer_type: AnswerType
    notes: Optional[str] = None


def detect_answer_type(answer: str) -> AnswerType:
    """Detect the type of a GAIA answer.

    Args:
        answer: The answer string to analyze.

    Returns:
        AnswerType indicating string, number, or list.
    """
    answer = answer.strip()

    # Check for list (comma-separated values)
    if "," in answer:
        # Could be a list or a number with comma as thousands separator
        # GAIA uses comma for lists, not thousands separators
        parts = [p.strip() for p in answer.split(",")]
        if len(parts) > 1 and all(p for p in parts):
            return AnswerType.LIST

    # Check for number
    # Handle various number formats: integers, decimals, negative, scientific
    number_pattern = r"^-?\d+\.?\d*(?:[eE][+-]?\d+)?$"
    if re.match(number_pattern, answer):
        return AnswerType.NUMBER

    # Default to string
    return AnswerType.STRING


def normalize_string(s: str) -> str:
    """Normalize a string answer for comparison.

    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse multiple whitespace to single space
    - Remove trailing punctuation

    Args:
        s: String to normalize.

    Returns:
        Normalized string.
    """
    # Lowercase and strip
    s = s.lower().strip()

    # Collapse multiple whitespace
    s = re.sub(r"\s+", " ", s)

    # Remove trailing punctuation (but preserve internal)
    s = re.sub(r"[.!?]+$", "", s)

    return s


def normalize_number(s: str) -> Optional[float]:
    """Parse a string as a number.

    Handles integers, decimals, negative numbers, and scientific notation.

    Args:
        s: String to parse.

    Returns:
        Float value, or None if parsing fails.
    """
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return None


def normalize_list(s: str) -> set:
    """Normalize a comma-separated list for comparison.

    - Split by comma
    - Normalize each item
    - Return as set (order-independent)

    Args:
        s: Comma-separated string.

    Returns:
        Set of normalized items.
    """
    items = [normalize_string(item) for item in s.split(",")]
    return {item for item in items if item}


def numbers_equal(a: float, b: float, tolerance: float = 0.001) -> bool:
    """Compare two numbers with relative and absolute tolerance.

    Args:
        a: First number.
        b: Second number.
        tolerance: Relative tolerance (default 0.1%).

    Returns:
        True if numbers are equal within tolerance.
    """
    if a == b:
        return True

    # For very small numbers, use absolute tolerance
    abs_tolerance = 0.001
    if abs(a) < abs_tolerance and abs(b) < abs_tolerance:
        return abs(a - b) < abs_tolerance

    # Use relative tolerance for larger numbers
    max_val = max(abs(a), abs(b))
    if max_val == 0:
        return True

    relative_diff = abs(a - b) / max_val
    return relative_diff < tolerance


def normalize_answer(answer: str, answer_type: Optional[AnswerType] = None) -> str:
    """Normalize an answer based on its type.

    Args:
        answer: Answer string to normalize.
        answer_type: Type of answer. If None, auto-detected.

    Returns:
        Normalized answer string.
    """
    if answer_type is None:
        answer_type = detect_answer_type(answer)

    if answer_type == AnswerType.NUMBER:
        num = normalize_number(answer)
        if num is not None:
            # Normalize number representation
            if num == int(num):
                return str(int(num))
            return str(num)
        return normalize_string(answer)

    elif answer_type == AnswerType.LIST:
        items = sorted(normalize_list(answer))
        return ", ".join(items)

    else:
        return normalize_string(answer)


def score_answer(
    predicted: Optional[str],
    ground_truth: str,
    task_id: str = "",
) -> ScoreResult:
    """Score a predicted answer against ground truth.

    Uses the official GAIA quasi exact match methodology:
    - String: case-insensitive, whitespace-normalized
    - Number: parsed as float with 0.1% tolerance
    - List: order-independent set comparison

    Args:
        predicted: Model's predicted answer (may be None if failed).
        ground_truth: Ground truth answer.
        task_id: Question identifier for the result.

    Returns:
        ScoreResult with match details.
    """
    # Handle missing prediction
    if predicted is None or predicted.strip() == "":
        return ScoreResult(
            task_id=task_id,
            correct=False,
            score=0.0,
            match_type="missing",
            expected=ground_truth,
            actual=predicted,
            answer_type=detect_answer_type(ground_truth),
            notes="No answer provided",
        )

    # Detect answer type from ground truth
    answer_type = detect_answer_type(ground_truth)

    # Score based on type
    if answer_type == AnswerType.NUMBER:
        gt_num = normalize_number(ground_truth)
        pred_num = normalize_number(predicted)

        if gt_num is not None and pred_num is not None:
            is_equal = numbers_equal(pred_num, gt_num)
            return ScoreResult(
                task_id=task_id,
                correct=is_equal,
                score=1.0 if is_equal else 0.0,
                match_type="numeric" if is_equal else "numeric_mismatch",
                expected=ground_truth,
                actual=predicted,
                answer_type=answer_type,
                notes=f"Compared as numbers: {pred_num} vs {gt_num}",
            )

        # Fall back to string comparison if number parsing fails
        answer_type = AnswerType.STRING

    if answer_type == AnswerType.LIST:
        gt_set = normalize_list(ground_truth)
        pred_set = normalize_list(predicted)

        is_equal = gt_set == pred_set
        return ScoreResult(
            task_id=task_id,
            correct=is_equal,
            score=1.0 if is_equal else 0.0,
            match_type="list" if is_equal else "list_mismatch",
            expected=ground_truth,
            actual=predicted,
            answer_type=answer_type,
            notes=f"Compared as sets: {pred_set} vs {gt_set}",
        )

    # String comparison
    gt_norm = normalize_string(ground_truth)
    pred_norm = normalize_string(predicted)

    is_equal = gt_norm == pred_norm
    return ScoreResult(
        task_id=task_id,
        correct=is_equal,
        score=1.0 if is_equal else 0.0,
        match_type="string" if is_equal else "string_mismatch",
        expected=ground_truth,
        actual=predicted,
        answer_type=AnswerType.STRING,
        notes=f"Compared as strings: '{pred_norm}' vs '{gt_norm}'",
    )


async def extract_answer_with_llm(
    response: str,
    question: str,
    api_url: str = "http://127.0.0.1:9000",
    timeout: float = 30.0,
) -> str:
    """Use LLM to extract the final answer from a verbose response.

    This is more robust than pattern matching as it can handle any format
    the agent outputs (markdown, citations, verbose explanations, etc.).

    Args:
        response: Full model response text.
        question: The original question (for context).
        api_url: API server URL.
        timeout: Request timeout in seconds.

    Returns:
        Extracted answer string.
    """
    if not response:
        return ""

    # Build extraction prompt
    extraction_prompt = f"""Extract ONLY the final answer value from this response.

Rules:
- Return JUST the answer (number, word, or short phrase)
- NO explanations, NO "The answer is..."
- Numbers: just digits (e.g., "17" not "17 hours" or "seventeen")
- Names: just the name (e.g., "Paris" not "The answer is Paris")
- Lists: comma-separated (e.g., "a, b, c")
- Convert written numbers to digits (e.g., "three" -> "3")
- If no clear answer found, return: UNKNOWN

Question: {question}

Response: {response[:2000]}

Answer:"""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            # Create a temporary conversation for extraction
            conv_response = await client.post(
                f"{api_url}/api/conversations",
                json={"title": "GAIA Answer Extraction"},
            )

            if conv_response.status_code != 200:
                # Fallback to basic extraction
                return extract_final_answer(response)

            conv_data = conv_response.json()
            conversation_id = conv_data.get("conversation_id")

            if not conversation_id:
                return extract_final_answer(response)

            # Create chat run for extraction
            run_response = await client.post(
                f"{api_url}/api/conversations/{conversation_id}/runs",
                json={"message": extraction_prompt},
            )

            if run_response.status_code != 200:
                return extract_final_answer(response)

            run_data = run_response.json()
            run_id = run_data.get("run_id")

            if not run_id:
                return extract_final_answer(response)

            # Poll for completion
            poll_interval = 0.5
            max_polls = int(timeout / poll_interval)

            for _ in range(max_polls):
                status_response = await client.get(
                    f"{api_url}/api/runs/{run_id}"
                )

                if status_response.status_code != 200:
                    await asyncio.sleep(poll_interval)
                    continue

                status_data = status_response.json()
                status = status_data.get("status")

                if status == "succeeded":
                    extracted = status_data.get("final_answer", "")
                    # Clean up the extracted answer
                    extracted = extracted.strip()
                    # Remove any quotes
                    extracted = extracted.strip('"\'')
                    # If extraction failed, fallback
                    if not extracted or extracted == "UNKNOWN":
                        return extract_final_answer(response)
                    return extracted

                elif status == "failed":
                    return extract_final_answer(response)

                await asyncio.sleep(poll_interval)

            # Timeout - fallback
            return extract_final_answer(response)

    except Exception:
        # Any error - fallback to basic extraction
        return extract_final_answer(response)


def extract_final_answer(response: str) -> str:
    """Extract final answer from a model response (basic pattern matching).

    GAIA expects short answers. This function attempts to extract
    just the answer portion from potentially verbose responses.

    Args:
        response: Full model response text.

    Returns:
        Extracted answer string.
    """
    if not response:
        return ""

    response = response.strip()

    # Look for common answer patterns
    patterns = [
        r"(?:the )?(?:final )?answer is[:\s]+(.+?)(?:\.|$)",
        r"(?:answer|result)[:\s]+(.+?)(?:\.|$)",
        r"^(.+?)$",  # First line as fallback
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
        if match:
            answer = match.group(1).strip()
            # If answer is very short (typical for GAIA), use it
            if len(answer) < 100:
                return answer

    # If no pattern matched or answer too long, return first line
    first_line = response.split("\n")[0].strip()
    if len(first_line) < 200:
        return first_line

    # Last resort: return truncated response
    return response[:100]
