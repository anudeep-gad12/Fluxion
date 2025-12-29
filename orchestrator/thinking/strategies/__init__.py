"""Thinking strategies package.

Available strategies:
- DirectStrategy: No explicit thinking, just generate answer directly.

Future strategies:
- ChainOfThoughtStrategy: Step-by-step reasoning.
- VoteStrategy: Generate N candidates, majority vote.
- SolveVerifyStrategy: Generate + verify candidates.
"""

from orchestrator.thinking.strategies.direct import DirectStrategy

__all__ = [
    "DirectStrategy",
]
