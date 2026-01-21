"""GAIA Benchmark Evaluation Package.

This package provides tools for evaluating the reasoner agent against
the GAIA benchmark (General AI Assistants benchmark).

Usage:
    python -m scripts.gaia --level 1 --mode agent
    python -m scripts.gaia --level 1 --compare
"""

from .loader import GAIAQuestion, load_gaia_dataset
from .scorer import score_answer, normalize_answer
from .results import EvaluationResults, aggregate_results, save_results

__all__ = [
    "GAIAQuestion",
    "load_gaia_dataset",
    "score_answer",
    "normalize_answer",
    "EvaluationResults",
    "aggregate_results",
    "save_results",
]
