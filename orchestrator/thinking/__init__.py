"""Thinking module - pluggable reasoning strategies.

This module provides a flexible architecture for different thinking/reasoning
strategies that can be swapped in and out without changing the chat engine.

Uses Mistral native [THINK]/[/THINK] token format for thinking separation.

Available strategies:
- DirectStrategy: No explicit thinking, just generate answer directly
- ChainOfThoughtStrategy: Step-by-step reasoning with [THINK]/[/THINK] tags
- AutoStrategy: Auto-detect complexity and route to appropriate strategy
- SelfConsistencyStrategy: Generate N candidates, majority vote (+12-18% accuracy)
- SelfReflectionStrategy: Critique and revise loop (+4-6% accuracy)
- ChainOfDraftStrategy: Minimal drafts per step (80% token reduction)
"""

from orchestrator.thinking.base import (
    StreamParser,
    ThinkingResult,
    ThinkingStep,
    ThinkingStrategy,
    strip_thinking_tags,
)
from orchestrator.thinking.complexity import ComplexityDetector, ComplexityResult
from orchestrator.thinking.orchestrator import ThinkingOrchestrator
from orchestrator.thinking.strategies.direct import DirectStrategy
from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy
from orchestrator.thinking.strategies.auto import AutoStrategy
from orchestrator.thinking.strategies.self_consistency import SelfConsistencyStrategy
from orchestrator.thinking.strategies.self_reflection import SelfReflectionStrategy
from orchestrator.thinking.strategies.chain_of_draft import ChainOfDraftStrategy

__all__ = [
    # Base classes
    "StreamParser",
    "ThinkingResult",
    "ThinkingStep",
    "ThinkingStrategy",
    "strip_thinking_tags",
    # Complexity detection
    "ComplexityDetector",
    "ComplexityResult",
    # Orchestrator
    "ThinkingOrchestrator",
    # Strategies
    "DirectStrategy",
    "ChainOfThoughtStrategy",
    "AutoStrategy",
    "SelfConsistencyStrategy",
    "SelfReflectionStrategy",
    "ChainOfDraftStrategy",
]
