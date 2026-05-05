"""Token-aware conversation history builder."""

from typing import Any, Optional

from orchestrator.context.budget import ContextBudget
from orchestrator.utils.tokens import TokenCounter


class HistoryBuilder:
    """Builds conversation history within a token budget.

    Algorithm:
    1. Count tokens for system_prompt + plan + current_query
    2. Calculate available_for_history
    3. Iterate runs newest-to-oldest
    4. For each run: use turn_summary if available, else raw user_message + final_answer
    5. Add pairs until budget exhausted
    6. Reverse to chronological order
    7. Return (messages, budget)
    """

    # Per-message overhead for role/structure tokens
    MSG_OVERHEAD = 4

    def __init__(
        self,
        token_counter: TokenCounter,
        max_context_tokens: int = 100000,
        reserve_for_response: int = 4096,
    ) -> None:
        self._counter = token_counter
        self._max_context_tokens = max_context_tokens
        self._reserve_for_response = reserve_for_response

    def build_history_messages(
        self,
        prior_runs: list[dict[str, Any]],
        system_prompt: str,
        current_query: str,
        plan_text: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], ContextBudget]:
        """Build history within token budget.

        Args:
            prior_runs: Previous runs (any order — will be sorted internally).
            system_prompt: System prompt text.
            current_query: Current user message.
            plan_text: Optional plan text to account for in budget.

        Returns:
            Tuple of (messages list, ContextBudget accounting).
        """
        budget = ContextBudget(
            max_tokens=self._max_context_tokens,
            reserve_for_response=self._reserve_for_response,
        )

        # Count fixed costs
        budget.system_prompt_tokens = (
            self._counter.count_tokens(system_prompt) + self.MSG_OVERHEAD
        )
        budget.current_query_tokens = (
            self._counter.count_tokens(current_query) + self.MSG_OVERHEAD
        )
        if plan_text:
            budget.plan_tokens = (
                self._counter.count_tokens(plan_text) + self.MSG_OVERHEAD
            )

        available = budget.available_for_history

        # Sort runs newest-first for priority inclusion
        sorted_runs = sorted(
            prior_runs, key=lambda r: r.get("created_at", ""), reverse=True
        )

        # Collect history pairs newest-first, respecting budget
        history_pairs: list[tuple[dict, dict]] = []
        tokens_used = 0

        for run in sorted_runs:
            user_msg = run.get("user_message")
            final_answer = run.get("final_answer")

            # Skip incomplete runs
            if not final_answer:
                continue

            # Skip the same query we're about to send
            if user_msg == current_query:
                continue

            turn_summary = run.get("turn_summary")

            if turn_summary:
                # Use compact summary as assistant message.
                # Keep the outcome first. For legacy summaries, strip the
                # leading "Q: ..." prefix because the user message is already
                # in its own role:user message.
                assistant_text = turn_summary
                if assistant_text.startswith("Q: "):
                    # Remove everything up to " | A: " or " | Tools: "
                    for sep in (" | A: ", " | Findings: ", " | Tools: "):
                        idx = assistant_text.find(sep)
                        if idx != -1:
                            assistant_text = assistant_text[idx + len(sep):]
                            break
                elif " | User asked: " in assistant_text:
                    assistant_text = assistant_text.split(" | User asked: ", 1)[0]

                pair_tokens = (
                    self._counter.count_tokens(user_msg or "") + self.MSG_OVERHEAD
                    + self._counter.count_tokens(assistant_text) + self.MSG_OVERHEAD
                )
                if tokens_used + pair_tokens > available:
                    break
                tokens_used += pair_tokens
                history_pairs.append((
                    {"role": "user", "content": user_msg or ""},
                    {"role": "assistant", "content": assistant_text},
                ))
            else:
                # Legacy fallback: raw user_message + final_answer
                if not user_msg:
                    continue
                pair_tokens = (
                    self._counter.count_tokens(user_msg) + self.MSG_OVERHEAD
                    + self._counter.count_tokens(final_answer) + self.MSG_OVERHEAD
                )
                if tokens_used + pair_tokens > available:
                    break
                tokens_used += pair_tokens
                history_pairs.append((
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": final_answer},
                ))

        budget.history_tokens = tokens_used

        # Build final messages: system + history (chronological) + current query
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Reverse to chronological (oldest first)
        for user_dict, assistant_dict in reversed(history_pairs):
            messages.append(user_dict)
            messages.append(assistant_dict)

        # Current query last
        messages.append({"role": "user", "content": current_query})

        return messages, budget
