"""Thinking strategies package.

Available strategies:
- DirectStrategy: No explicit thinking, just generate answer directly.
- CARStrategy: Certainty-based Adaptive Routing using perplexity.

Future strategies:
- ChainOfThoughtStrategy: Step-by-step reasoning.
- VoteStrategy: Generate N candidates, majority vote.
- SolveVerifyStrategy: Generate + verify candidates.
"""

from orchestrator.thinking.strategies.direct import DirectStrategy
from orchestrator.thinking.strategies.car import CARStrategy

__all__ = [
    "DirectStrategy",
    "CARStrategy",
]
