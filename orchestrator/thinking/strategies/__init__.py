"""Thinking strategies package.

Available strategies:
- DirectStrategy: No explicit thinking, just generate answer directly.
- ChainOfThoughtStrategy: Step-by-step reasoning with [THINK]/[/THINK] tags.
"""

from orchestrator.thinking.strategies.direct import DirectStrategy
from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy

__all__ = [
    "DirectStrategy",
    "ChainOfThoughtStrategy",
]
