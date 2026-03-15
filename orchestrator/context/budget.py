"""Token budget tracker for context window management."""

from dataclasses import dataclass
from typing import Optional

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)


def context_params_for_model(
    model_name: Optional[str],
    config_max_tokens: int,
    config_reserve: int,
) -> tuple[int, int]:
    """Resolve context parameters from the model registry.

    Looks up the model's context_window and max_output_tokens from the
    registry. Falls back to config values if the model is not found.

    Args:
        model_name: Model name/alias to look up (may be None).
        config_max_tokens: Fallback max_tokens from chat_config.yaml.
        config_reserve: Fallback reserve_for_response from chat_config.yaml.

    Returns:
        Tuple of (max_context_tokens, reserve_for_response).
    """
    if model_name:
        try:
            from orchestrator.models.registry import ModelRegistry
            resolved = ModelRegistry.resolve(model_name)
            max_ctx = resolved.context_window
            reserve = resolved.max_output_tokens
            logger.info(
                "Context params resolved from model registry",
                extra={
                    "model": model_name,
                    "context_window": max_ctx,
                    "max_output_tokens": reserve,
                },
            )
            return max_ctx, reserve
        except Exception:
            logger.debug(
                "Model not found in registry, using config defaults",
                extra={"model": model_name},
            )

    # Fallback to config values with a sensible floor
    max_ctx = max(config_max_tokens, 32768)
    return max_ctx, config_reserve


@dataclass
class ContextBudget:
    """Tracks token allocation across context window components.

    Provides a full accounting of how the context budget is spent:
    system prompt, plan, current query, and conversation history.
    """

    max_tokens: int  # 100000 from config
    reserve_for_response: int  # 4096 from config
    system_prompt_tokens: int = 0
    plan_tokens: int = 0
    current_query_tokens: int = 0
    history_tokens: int = 0

    @property
    def available_for_history(self) -> int:
        """Tokens remaining for conversation history."""
        return (
            self.max_tokens
            - self.reserve_for_response
            - self.system_prompt_tokens
            - self.plan_tokens
            - self.current_query_tokens
        )

    @property
    def total_used(self) -> int:
        """Total tokens consumed across all components."""
        return (
            self.system_prompt_tokens
            + self.plan_tokens
            + self.current_query_tokens
            + self.history_tokens
        )

    @property
    def utilization_pct(self) -> float:
        """Percentage of max_tokens currently used."""
        if self.max_tokens <= 0:
            return 0.0
        return (self.total_used / self.max_tokens) * 100
