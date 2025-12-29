"""Token counting utilities using tiktoken.

Uses cl100k_base encoding which works ~95% accurately for most models
including OpenAI GPT-4, Mistral, and similar architectures.
"""

from typing import TYPE_CHECKING, Optional

import tiktoken

if TYPE_CHECKING:
    from orchestrator.models.base import Message

# Lazy-load encoder for performance
_encoder: Optional[tiktoken.Encoding] = None


def _get_encoder() -> tiktoken.Encoding:
    """Get or create the tiktoken encoder (lazy initialization)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


class TokenCounter:
    """Token counter using tiktoken cl100k_base encoding.

    This provides accurate token counting compatible with most modern LLMs.
    Falls back to character estimation if tiktoken fails.
    """

    ROLE_OVERHEAD = 4  # Approximate tokens for role/message structure
    CHARS_PER_TOKEN_FALLBACK = 4  # Fallback if tiktoken fails

    def count_tokens(self, text: str) -> int:
        """Count tokens in a string using tiktoken.

        Args:
            text: The text to count tokens for.

        Returns:
            Token count.
        """
        if not text:
            return 0
        try:
            encoder = _get_encoder()
            return len(encoder.encode(text))
        except Exception:
            # Fallback to character-based estimation
            return max(1, len(text) // self.CHARS_PER_TOKEN_FALLBACK)

    def estimate_tokens(self, text: str) -> int:
        """Alias for count_tokens (backward compatibility)."""
        return self.count_tokens(text)

    def count_messages(self, messages: list["Message"]) -> int:
        """Count total tokens in a list of messages.

        Args:
            messages: List of Message objects.

        Returns:
            Total token count including role overhead.
        """
        total = 0
        for msg in messages:
            total += self.count_tokens(msg.content) + self.ROLE_OVERHEAD
        return total

    def count_message_dicts(self, messages: list[dict]) -> int:
        """Count total tokens in a list of message dicts.

        Args:
            messages: List of message dicts with 'content' key.

        Returns:
            Total token count including role overhead.
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += self.count_tokens(content) + self.ROLE_OVERHEAD
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
