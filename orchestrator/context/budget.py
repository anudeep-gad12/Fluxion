"""Token budget tracker for context window management."""

from dataclasses import dataclass


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
