"""GAIA Dataset Loader.

Loads the GAIA benchmark dataset from HuggingFace. Requires access
to the gated dataset (https://huggingface.co/datasets/gaia-benchmark/GAIA).

Usage:
    questions = await load_gaia_dataset(level=1, split="validation")
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:
    from datasets import load_dataset
    from huggingface_hub import snapshot_download
    HAS_DATASETS = True
except ImportError:
    HAS_DATASETS = False


@dataclass
class GAIAQuestion:
    """A single GAIA benchmark question.

    Attributes:
        task_id: Unique identifier for the question.
        question: The question text.
        level: Difficulty level (1, 2, or 3).
        final_answer: Ground truth answer (None for test split).
        file_name: Name of associated file if any.
        file_path: Path to associated file if any.
        has_attachment: Whether question has file attachments.
    """
    task_id: str
    question: str
    level: int
    final_answer: Optional[str]
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    has_attachment: bool = False


def load_gaia_dataset(
    level: int = 1,
    split: str = "validation",
    hf_token: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    skip_attachments: bool = True,
) -> List[GAIAQuestion]:
    """Load GAIA dataset from HuggingFace.

    Args:
        level: GAIA difficulty level (1, 2, or 3).
        split: Dataset split ("validation" or "test").
        hf_token: HuggingFace API token. If None, uses HF_TOKEN env var.
        cache_dir: Local directory for caching. If None, uses default.
        skip_attachments: If True, skip questions with file attachments.

    Returns:
        List of GAIAQuestion objects.

    Raises:
        ImportError: If datasets library not installed.
        ValueError: If invalid level or split provided.
        EnvironmentError: If HF_TOKEN not set for gated dataset.
    """
    if not HAS_DATASETS:
        raise ImportError(
            "datasets library required. Install with: uv sync --extra benchmark"
        )

    if level not in (1, 2, 3):
        raise ValueError(f"Invalid level: {level}. Must be 1, 2, or 3.")

    if split not in ("validation", "test"):
        raise ValueError(f"Invalid split: {split}. Must be 'validation' or 'test'.")

    # Get HuggingFace token (check multiple common env var names)
    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE")
    if not token:
        raise EnvironmentError(
            "HF_TOKEN or HUGGING_FACE environment variable required for gated GAIA dataset. "
            "Get token from https://huggingface.co/settings/tokens"
        )

    # Load dataset from HuggingFace
    # Config format: "2023_level{N}" where N is 1, 2, or 3
    config_name = f"2023_level{level}"

    try:
        dataset = load_dataset(
            "gaia-benchmark/GAIA",
            config_name,
            split=split,
            token=token,
            cache_dir=str(cache_dir) if cache_dir else None,
        )
    except Exception as e:
        # Provide helpful error message
        if "gated" in str(e).lower() or "access" in str(e).lower():
            raise EnvironmentError(
                "Access denied to GAIA dataset. "
                "Request access at https://huggingface.co/datasets/gaia-benchmark/GAIA"
            ) from e
        raise

    # Convert to GAIAQuestion objects
    questions: List[GAIAQuestion] = []

    for row in dataset:
        task_id = row.get("task_id", "")
        question_text = row.get("Question", "")
        level_val = row.get("Level", level)
        final_answer = row.get("Final answer")
        file_name = row.get("file_name")
        file_path = row.get("file_path")

        has_attachment = bool(file_name and file_name.strip())

        # Skip questions with attachments if requested
        if skip_attachments and has_attachment:
            continue

        questions.append(
            GAIAQuestion(
                task_id=task_id,
                question=question_text,
                level=int(level_val) if level_val else level,
                final_answer=final_answer if final_answer else None,
                file_name=file_name,
                file_path=file_path,
                has_attachment=has_attachment,
            )
        )

    return questions


def get_dataset_stats(
    level: int = 1,
    split: str = "validation",
    hf_token: Optional[str] = None,
) -> dict:
    """Get statistics about the GAIA dataset.

    Args:
        level: GAIA difficulty level (1, 2, or 3).
        split: Dataset split ("validation" or "test").
        hf_token: HuggingFace API token.

    Returns:
        Dictionary with dataset statistics.
    """
    # Load all questions (including with attachments)
    all_questions = load_gaia_dataset(
        level=level,
        split=split,
        hf_token=hf_token,
        skip_attachments=False,
    )

    with_attachments = sum(1 for q in all_questions if q.has_attachment)
    without_attachments = len(all_questions) - with_attachments

    return {
        "level": level,
        "split": split,
        "total_questions": len(all_questions),
        "with_attachments": with_attachments,
        "without_attachments": without_attachments,
    }
