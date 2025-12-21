"""Token counting utilities.

Provides fast token estimation without external dependencies.
Uses character-based approximation (~4 chars per token) which is
reasonably accurate for most LLMs.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.models.base import Message


class TokenCounter:
    """Token counter with character-based estimation.

    Uses the rule of thumb that ~4 characters = 1 token for most LLMs.
    This is fast and doesn't require external dependencies like tiktoken.
    """

    CHARS_PER_TOKEN = 4  # Approximate characters per token
    ROLE_OVERHEAD = 4  # Approximate tokens for role/message structure

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a string.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def count_messages(self, messages: list["Message"]) -> int:
        """Count total tokens in a list of messages.

        Args:
            messages: List of Message objects.

        Returns:
            Total estimated token count including role overhead.
        """
        total = 0
        for msg in messages:
            total += self.estimate_tokens(msg.content) + self.ROLE_OVERHEAD
        return total

    def count_message_dicts(self, messages: list[dict]) -> int:
        """Count total tokens in a list of message dicts.

        Args:
            messages: List of message dicts with 'content' key.

        Returns:
            Total estimated token count including role overhead.
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self.estimate_tokens(content) + self.ROLE_OVERHEAD
        return total

    def fits_in_context(
        self,
        messages: list["Message"],
        max_tokens: int,
        reserve: int = 0,
    ) -> bool:
        """Check if messages fit within context limit.

        Args:
            messages: List of Message objects.
            max_tokens: Maximum context tokens allowed.
            reserve: Tokens to reserve (e.g., for response).

        Returns:
            True if messages fit, False otherwise.
        """
        used = self.count_messages(messages)
        return used <= (max_tokens - reserve)


# Singleton instance for convenience
_token_counter: TokenCounter | None = None


def get_token_counter() -> TokenCounter:
    """Get the singleton TokenCounter instance."""
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter()
    return _token_counter
