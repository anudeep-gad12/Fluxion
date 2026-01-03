"""Thinking strategies package.

Available strategies:
- DirectStrategy: Uses model's native reasoning (works with gpt-oss models)
"""

from orchestrator.thinking.strategies.direct import DirectStrategy

__all__ = [
    "DirectStrategy",
]
