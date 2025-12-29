"""Thinking module - pluggable reasoning strategies.

This module provides a flexible architecture for different thinking/reasoning
strategies that can be swapped in and out without changing the chat engine.

Available strategies:
- DirectStrategy: No explicit thinking, just generate answer directly
- ChainOfThoughtStrategy: Step-by-step reasoning (future)
- VoteStrategy: Generate N candidates, majority vote (future)
- SolveVerifyStrategy: Generate + verify candidates (future)
"""

from orchestrator.thinking.base import (
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
)
from orchestrator.thinking.orchestrator import ThinkingOrchestrator
from orchestrator.thinking.strategies.direct import DirectStrategy

__all__ = [
    "ThinkingResult",
    "ThinkingStep",
    "ThinkingStrategy",
    "ThinkingOrchestrator",
    "DirectStrategy",
]
