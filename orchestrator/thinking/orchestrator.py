"""Thinking orchestrator - routes to appropriate thinking strategy.

This module provides the ThinkingOrchestrator class that manages
different thinking strategies and routes requests to the appropriate one.
"""

from typing import Dict, Optional, Type

from orchestrator.thinking.base import ThinkingStrategy
from orchestrator.thinking.strategies.direct import DirectStrategy
from orchestrator.thinking.strategies.cot import ChainOfThoughtStrategy
from orchestrator.thinking.strategies.auto import AutoStrategy
from orchestrator.thinking.strategies.self_consistency import SelfConsistencyStrategy
from orchestrator.thinking.strategies.self_reflection import SelfReflectionStrategy
from orchestrator.thinking.strategies.chain_of_draft import ChainOfDraftStrategy
from orchestrator.thinking.strategies.car import CARStrategy


class ThinkingOrchestrator:
    """Routes to appropriate thinking strategy based on configuration.

    The orchestrator maintains a registry of available strategies and
    can instantiate them with the appropriate configuration.

    Available strategies:
        - direct: No thinking, just generate answer (fastest)
        - cot: Chain-of-Thought with Mistral native [THINK]/[/THINK] tags (+17% on reasoning)
        - auto: Auto-detect complexity and route to appropriate strategy
        - self_consistency: Multiple paths + voting (+12-18% accuracy)
        - self_reflection: Critique and revise loop (+4-6% accuracy)
        - chain_of_draft: Minimal drafts per step (80% token reduction)

    Example:
        orchestrator = ThinkingOrchestrator(default_strategy="auto")
        strategy = orchestrator.get_strategy("cot")
        result = await strategy.think(messages, model_call)
    """

    # Default strategies registry
    _default_strategies: Dict[str, Type[ThinkingStrategy]] = {
        "direct": DirectStrategy,
        "cot": ChainOfThoughtStrategy,
        "auto": AutoStrategy,
        "car": CARStrategy,
        "self_consistency": SelfConsistencyStrategy,
        "self_reflection": SelfReflectionStrategy,
        "chain_of_draft": ChainOfDraftStrategy,
        # Aliases
        "chain_of_thought": ChainOfThoughtStrategy,
        "vote": SelfConsistencyStrategy,
        "refine": SelfReflectionStrategy,
        "cod": ChainOfDraftStrategy,
        "draft": ChainOfDraftStrategy,
        "adaptive": CARStrategy,
    }

    def __init__(self, default_strategy: str = "direct"):
        """Initialize the orchestrator.

        Args:
            default_strategy: Name of the default strategy to use
                             when no strategy is specified.
        """
        self.default_strategy = default_strategy
        # Copy the default strategies so each instance can have its own registry
        self._strategies: Dict[str, Type[ThinkingStrategy]] = dict(
            self._default_strategies
        )

    def get_strategy(
        self, name: Optional[str] = None, **kwargs
    ) -> ThinkingStrategy:
        """Get a strategy instance by name.

        Args:
            name: Strategy name. If None, uses the default strategy.
            **kwargs: Additional arguments to pass to the strategy constructor.

        Returns:
            ThinkingStrategy instance.

        Raises:
            ValueError: If the strategy name is not registered.
        """
        strategy_name = name or self.default_strategy

        if strategy_name not in self._strategies:
            available = ", ".join(sorted(self._strategies.keys()))
            raise ValueError(
                f"Unknown strategy: {strategy_name!r}. "
                f"Available strategies: {available}"
            )

        strategy_cls = self._strategies[strategy_name]

        # Instantiate with kwargs if provided
        if kwargs:
            return strategy_cls(**kwargs)
        return strategy_cls()

    def register_strategy(
        self, name: str, strategy_cls: Type[ThinkingStrategy]
    ) -> None:
        """Register a new thinking strategy.

        This allows adding custom strategies at runtime.

        Args:
            name: Name to register the strategy under.
            strategy_cls: Strategy class (must inherit from ThinkingStrategy).

        Raises:
            TypeError: If strategy_cls is not a subclass of ThinkingStrategy.
        """
        if not issubclass(strategy_cls, ThinkingStrategy):
            raise TypeError(
                f"Strategy must be a subclass of ThinkingStrategy, "
                f"got {strategy_cls.__name__}"
            )
        self._strategies[name] = strategy_cls

    def list_strategies(self) -> list[str]:
        """List all available strategy names.

        Returns:
            List of registered strategy names.
        """
        return sorted(self._strategies.keys())

    def has_strategy(self, name: str) -> bool:
        """Check if a strategy is registered.

        Args:
            name: Strategy name to check.

        Returns:
            True if the strategy is registered, False otherwise.
        """
        return name in self._strategies
