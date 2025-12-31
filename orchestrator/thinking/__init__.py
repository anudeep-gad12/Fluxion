"""Thinking module - pluggable reasoning strategies.

This module provides a flexible architecture for different thinking/reasoning
strategies that can be swapped in and out without changing the chat engine.

Uses [THINK]/[/THINK] token format for thinking separation.

Available strategies:
- DirectStrategy: No explicit thinking, just generate answer directly
- ChainOfThoughtStrategy: Step-by-step reasoning with [THINK]/[/THINK] tags
"""

from orchestrator.thinking.base import (
    StreamParser,
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
    strip_thinking_tags,
)
from orchestrator.thinking.orchestrator import ThinkingOrchestrator
from orchestrator.thinking.strategies.direct import DirectStrategy
from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy

__all__ = [
    # Base classes
    "StreamParser",
    "ThinkingResult",
    "ThinkingStep",
    "ThinkingStrategy",
    "strip_thinking_tags",
    # Orchestrator
    "ThinkingOrchestrator",
    # Strategies
    "DirectStrategy",
    "ChainOfThoughtStrategy",
]
