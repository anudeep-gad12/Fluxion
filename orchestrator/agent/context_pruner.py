"""Minimal token estimator shared by the agent engine."""

from typing import Any, Dict, List


class ContextPruner:
    """Compatibility wrapper around the shared token counter.

    The old step-aware pruning/summarization pipeline is gone; prompt reduction is
    handled directly in AgentEngine. This class now only keeps the small surface
    the engine still uses: config-like init fields and token estimation.
    """

    def __init__(self, keep_full_steps: int = 10, max_python_output_chars: int = 500) -> None:
        self._keep_full_steps = keep_full_steps
        self._max_python_chars = max_python_output_chars

    @property
    def keep_full_steps(self) -> int:
        return self._keep_full_steps

    @property
    def max_python_chars(self) -> int:
        return self._max_python_chars

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        from orchestrator.utils.tokens import get_token_counter
        return get_token_counter().count_message_dicts(messages)
