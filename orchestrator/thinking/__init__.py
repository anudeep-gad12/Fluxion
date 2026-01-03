"""Thinking module - pluggable reasoning strategies.

This module provides a flexible architecture for different thinking/reasoning
strategies that can be swapped in and out without changing the chat engine.

Available strategies:
- DirectStrategy: Uses model's native reasoning (works with gpt-oss models)
"""

from orchestrator.thinking.base import (
    StreamParser,
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
)
from orchestrator.thinking.orchestrator import ThinkingOrchestrator
from orchestrator.thinking.strategies.direct import DirectStrategy

__all__ = [
    # Base classes
    "StreamParser",
    "ThinkingResult",
    "ThinkingStep",
    "ThinkingStrategy",
    # Orchestrator
    "ThinkingOrchestrator",
    # Strategies
    "DirectStrategy",
]
