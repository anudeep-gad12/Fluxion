"""Thinking orchestrator - routes to appropriate thinking strategy.

This module provides the ThinkingOrchestrator class that manages
different thinking strategies and routes requests to the appropriate one.
"""

from typing import Dict, Optional, Type

from orchestrator.thinking.base import ThinkingStrategy
from orchestrator.thinking.strategies.direct import DirectStrategy


class ThinkingOrchestrator:
    """Routes to appropriate thinking strategy based on configuration.

    The orchestrator maintains a registry of available strategies and
    can instantiate them with the appropriate configuration.

    Example:
        orchestrator = ThinkingOrchestrator(default_strategy="direct")
        strategy = orchestrator.get_strategy("vote", n_candidates=3)
        result = await strategy.think(messages, model_call)
    """

    # Default strategies registry
    _default_strategies: Dict[str, Type[ThinkingStrategy]] = {
        "direct": DirectStrategy,
        # Future strategies will be added here:
        # "cot": ChainOfThoughtStrategy,
        # "vote": VoteStrategy,
        # "solve_verify": SolveVerifyStrategy,
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
