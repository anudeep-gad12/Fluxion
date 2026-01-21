"""GAIA Results Aggregation and Output.

Aggregates evaluation results and outputs them as JSON.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loader import GAIAQuestion
from .scorer import ScoreResult


@dataclass
class QuestionResult:
    """Result for a single question.

    Attributes:
        task_id: Question identifier.
        question: Question text (truncated).
        expected: Ground truth answer.
        agent_answer: Answer from agent mode (if run).
        chat_answer: Answer from chat mode (if run).
        agent_correct: Whether agent answer is correct.
        chat_correct: Whether chat answer is correct.
        agent_steps: Number of agent steps taken.
        agent_time_ms: Agent execution time in milliseconds.
        chat_time_ms: Chat execution time in milliseconds.
        error: Error message if execution failed.
    """
    task_id: str
    question: str
    expected: str
    agent_answer: Optional[str] = None
    chat_answer: Optional[str] = None
    agent_correct: Optional[bool] = None
    chat_correct: Optional[bool] = None
    agent_steps: Optional[int] = None
    agent_time_ms: Optional[int] = None
    chat_time_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class EvaluationSummary:
    """Summary statistics for evaluation.

    Attributes:
        total_questions: Total questions evaluated.
        agent_correct: Number correct in agent mode.
        agent_accuracy: Agent accuracy percentage.
        chat_correct: Number correct in chat mode.
        chat_accuracy: Chat accuracy percentage.
        delta: Difference (agent - chat) accuracy.
        agent_avg_steps: Average agent steps.
        agent_avg_time_ms: Average agent time.
        chat_avg_time_ms: Average chat time.
        errors: Number of failed evaluations.
    """
    total_questions: int = 0
    agent_correct: int = 0
    agent_accuracy: float = 0.0
    chat_correct: int = 0
    chat_accuracy: float = 0.0
    delta: float = 0.0
    agent_avg_steps: float = 0.0
    agent_avg_time_ms: float = 0.0
    chat_avg_time_ms: float = 0.0
    errors: int = 0


@dataclass
class EvaluationMetadata:
    """Metadata about the evaluation run.

    Attributes:
        timestamp: When evaluation was run.
        level: GAIA difficulty level.
        split: Dataset split (validation/test).
        model_name: Model used for evaluation.
        max_steps: Maximum agent steps allowed.
        modes_run: Which modes were evaluated.
    """
    timestamp: str = ""
    level: int = 1
    split: str = "validation"
    model_name: str = ""
    max_steps: int = 10
    modes_run: List[str] = field(default_factory=list)


@dataclass
class EvaluationResults:
    """Complete evaluation results.

    Attributes:
        metadata: Evaluation run metadata.
        summary: Summary statistics.
        results: Per-question results.
    """
    metadata: EvaluationMetadata
    summary: EvaluationSummary
    results: List[QuestionResult]


def aggregate_results(
    questions: List[GAIAQuestion],
    agent_scores: Optional[List[ScoreResult]] = None,
    chat_scores: Optional[List[ScoreResult]] = None,
    agent_times: Optional[List[int]] = None,
    chat_times: Optional[List[int]] = None,
    agent_steps: Optional[List[int]] = None,
    agent_answers: Optional[List[Optional[str]]] = None,
    chat_answers: Optional[List[Optional[str]]] = None,
    level: int = 1,
    split: str = "validation",
    model_name: str = "",
    max_steps: int = 10,
) -> EvaluationResults:
    """Aggregate evaluation results.

    Args:
        questions: List of GAIA questions evaluated.
        agent_scores: Score results from agent mode (if run).
        chat_scores: Score results from chat mode (if run).
        agent_times: Execution times for agent mode.
        chat_times: Execution times for chat mode.
        agent_steps: Step counts for agent mode.
        agent_answers: Raw answers from agent mode.
        chat_answers: Raw answers from chat mode.
        level: GAIA difficulty level.
        split: Dataset split.
        model_name: Model used.
        max_steps: Max agent steps.

    Returns:
        EvaluationResults with aggregated data.
    """
    # Determine which modes were run
    modes_run = []
    if agent_scores is not None:
        modes_run.append("agent")
    if chat_scores is not None:
        modes_run.append("chat")

    # Build metadata
    metadata = EvaluationMetadata(
        timestamp=datetime.now(timezone.utc).isoformat(),
        level=level,
        split=split,
        model_name=model_name,
        max_steps=max_steps,
        modes_run=modes_run,
    )

    # Build per-question results
    results: List[QuestionResult] = []

    for i, question in enumerate(questions):
        result = QuestionResult(
            task_id=question.task_id,
            question=question.question[:200] + "..." if len(question.question) > 200 else question.question,
            expected=question.final_answer or "",
        )

        if agent_scores and i < len(agent_scores):
            result.agent_correct = agent_scores[i].correct
            result.agent_answer = agent_answers[i] if agent_answers and i < len(agent_answers) else None

        if chat_scores and i < len(chat_scores):
            result.chat_correct = chat_scores[i].correct
            result.chat_answer = chat_answers[i] if chat_answers and i < len(chat_answers) else None

        if agent_times and i < len(agent_times):
            result.agent_time_ms = agent_times[i]

        if chat_times and i < len(chat_times):
            result.chat_time_ms = chat_times[i]

        if agent_steps and i < len(agent_steps):
            result.agent_steps = agent_steps[i]

        results.append(result)

    # Calculate summary statistics
    summary = EvaluationSummary(total_questions=len(questions))

    if agent_scores:
        summary.agent_correct = sum(1 for s in agent_scores if s.correct)
        summary.agent_accuracy = summary.agent_correct / len(questions) if questions else 0.0

    if chat_scores:
        summary.chat_correct = sum(1 for s in chat_scores if s.correct)
        summary.chat_accuracy = summary.chat_correct / len(questions) if questions else 0.0

    if agent_scores and chat_scores:
        summary.delta = summary.agent_accuracy - summary.chat_accuracy

    if agent_steps:
        valid_steps = [s for s in agent_steps if s is not None]
        summary.agent_avg_steps = sum(valid_steps) / len(valid_steps) if valid_steps else 0.0

    if agent_times:
        valid_times = [t for t in agent_times if t is not None]
        summary.agent_avg_time_ms = sum(valid_times) / len(valid_times) if valid_times else 0.0

    if chat_times:
        valid_times = [t for t in chat_times if t is not None]
        summary.chat_avg_time_ms = sum(valid_times) / len(valid_times) if valid_times else 0.0

    # Count errors
    summary.errors = sum(1 for r in results if r.error is not None)

    return EvaluationResults(
        metadata=metadata,
        summary=summary,
        results=results,
    )


def save_results(results: EvaluationResults, output_path: Path) -> None:
    """Save evaluation results to JSON file.

    Args:
        results: Evaluation results to save.
        output_path: Path to output JSON file.
    """
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict for JSON serialization
    data = {
        "metadata": asdict(results.metadata),
        "summary": asdict(results.summary),
        "results": [asdict(r) for r in results.results],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_results(input_path: Path) -> EvaluationResults:
    """Load evaluation results from JSON file.

    Args:
        input_path: Path to input JSON file.

    Returns:
        EvaluationResults object.
    """
    with open(input_path) as f:
        data = json.load(f)

    metadata = EvaluationMetadata(**data["metadata"])
    summary = EvaluationSummary(**data["summary"])
    results = [QuestionResult(**r) for r in data["results"]]

    return EvaluationResults(
        metadata=metadata,
        summary=summary,
        results=results,
    )


def format_summary(results: EvaluationResults) -> str:
    """Format results summary for console output.

    Args:
        results: Evaluation results.

    Returns:
        Formatted summary string.
    """
    lines = [
        "",
        "=" * 60,
        f"GAIA Benchmark Results - Level {results.metadata.level}",
        "=" * 60,
        "",
    ]

    summary = results.summary

    if "agent" in results.metadata.modes_run:
        lines.extend([
            f"Agent Mode:",
            f"  Accuracy: {summary.agent_correct}/{summary.total_questions} ({summary.agent_accuracy:.1%})",
            f"  Avg Steps: {summary.agent_avg_steps:.1f}",
            f"  Avg Time: {summary.agent_avg_time_ms/1000:.1f}s",
            "",
        ])

    if "chat" in results.metadata.modes_run:
        lines.extend([
            f"Chat Mode:",
            f"  Accuracy: {summary.chat_correct}/{summary.total_questions} ({summary.chat_accuracy:.1%})",
            f"  Avg Time: {summary.chat_avg_time_ms/1000:.1f}s",
            "",
        ])

    if "agent" in results.metadata.modes_run and "chat" in results.metadata.modes_run:
        delta_str = f"+{summary.delta:.1%}" if summary.delta >= 0 else f"{summary.delta:.1%}"
        lines.extend([
            f"Comparison:",
            f"  Agent vs Chat Delta: {delta_str}",
            "",
        ])

    lines.append("=" * 60)

    return "\n".join(lines)


def generate_markdown_report(results: EvaluationResults) -> str:
    """Generate a detailed markdown report of evaluation results.

    Args:
        results: Evaluation results.

    Returns:
        Markdown formatted report string.
    """
    lines = [
        f"# GAIA Benchmark Report - Level {results.metadata.level}",
        "",
        f"**Date:** {results.metadata.timestamp}",
        f"**Model:** {results.metadata.model_name}",
        f"**Split:** {results.metadata.split}",
        f"**Max Steps:** {results.metadata.max_steps}",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]

    summary = results.summary

    if "agent" in results.metadata.modes_run:
        lines.extend([
            "### Agent Mode",
            f"- **Accuracy:** {summary.agent_correct}/{summary.total_questions} ({summary.agent_accuracy:.1%})",
            f"- **Avg Steps:** {summary.agent_avg_steps:.1f}",
            f"- **Avg Time:** {summary.agent_avg_time_ms/1000:.1f}s",
            "",
        ])

    if "chat" in results.metadata.modes_run:
        lines.extend([
            "### Chat Mode",
            f"- **Accuracy:** {summary.chat_correct}/{summary.total_questions} ({summary.chat_accuracy:.1%})",
            f"- **Avg Time:** {summary.chat_avg_time_ms/1000:.1f}s",
            "",
        ])

    if "agent" in results.metadata.modes_run and "chat" in results.metadata.modes_run:
        delta_str = f"+{summary.delta:.1%}" if summary.delta >= 0 else f"{summary.delta:.1%}"
        lines.extend([
            "### Comparison",
            f"- **Agent vs Chat Delta:** {delta_str}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## Detailed Results",
        "",
    ])

    # Separate correct and incorrect
    correct_results = []
    incorrect_results = []

    for r in results.results:
        # Determine if correct based on agent or chat mode
        is_correct = r.agent_correct if r.agent_correct is not None else r.chat_correct
        if is_correct:
            correct_results.append(r)
        else:
            incorrect_results.append(r)

    # Incorrect section first (more important for debugging)
    if incorrect_results:
        lines.extend([
            f"### Incorrect ({len(incorrect_results)})",
            "",
        ])
        for i, r in enumerate(incorrect_results, 1):
            lines.extend([
                f"#### {i}. {r.task_id}",
                "",
                f"**Question:** {r.question}",
                "",
                f"**Expected:** `{r.expected}`",
                "",
            ])
            if r.agent_answer is not None:
                lines.append(f"**Agent Answer:** `{r.agent_answer}`")
            if r.chat_answer is not None:
                lines.append(f"**Chat Answer:** `{r.chat_answer}`")
            if r.agent_time_ms:
                lines.append(f"**Time:** {r.agent_time_ms/1000:.1f}s")
            if r.agent_steps:
                lines.append(f"**Steps:** {r.agent_steps}")
            if r.error:
                lines.append(f"**Error:** {r.error}")
            lines.extend(["", "---", ""])

    # Correct section
    if correct_results:
        lines.extend([
            f"### Correct ({len(correct_results)})",
            "",
        ])
        for i, r in enumerate(correct_results, 1):
            lines.extend([
                f"#### {i}. {r.task_id}",
                "",
                f"**Question:** {r.question}",
                "",
                f"**Expected:** `{r.expected}`",
                "",
            ])
            if r.agent_answer is not None:
                lines.append(f"**Agent Answer:** `{r.agent_answer}`")
            if r.chat_answer is not None:
                lines.append(f"**Chat Answer:** `{r.chat_answer}`")
            if r.agent_time_ms:
                lines.append(f"**Time:** {r.agent_time_ms/1000:.1f}s")
            if r.agent_steps:
                lines.append(f"**Steps:** {r.agent_steps}")
            lines.extend(["", "---", ""])

    return "\n".join(lines)


def save_markdown_report(results: EvaluationResults, output_path: Path) -> None:
    """Save evaluation results as a markdown report.

    Args:
        results: Evaluation results to save.
        output_path: Path to output markdown file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = generate_markdown_report(results)
    with open(output_path, "w") as f:
        f.write(report)
