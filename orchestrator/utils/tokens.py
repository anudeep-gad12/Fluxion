"""Token counting utilities using tiktoken.

Uses o200k_harmony encoding which is the tokenizer for gpt-oss models.
This provides accurate token counting for gpt-oss-20b and gpt-oss-120b.
"""

from typing import Any, Optional

import tiktoken

# Lazy-load encoder for performance
_encoder: Optional[tiktoken.Encoding] = None


def _get_encoder() -> tiktoken.Encoding:
    """Get or create the tiktoken encoder (lazy initialization)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("o200k_harmony")
    return _encoder


class TokenCounter:
    """Token counter using tiktoken o200k_harmony encoding.

    This provides accurate token counting for gpt-oss models.
    Falls back to character estimation if tiktoken fails.
    """

    ROLE_OVERHEAD = 4  # Approximate tokens for role/message structure
    CHARS_PER_TOKEN_FALLBACK = 4  # Fallback if tiktoken fails

    def count_tokens(self, text: Any) -> int:
        """Count tokens in a string using tiktoken.

        Args:
            text: The text to count tokens for.

        Returns:
            Token count.
        """
        if not text:
            return 0
        if isinstance(text, list):
            total = 0
            for item in text:
                if not isinstance(item, dict):
                    total += self.count_tokens(str(item))
                    continue
                if item.get("type") == "text":
                    total += self.count_tokens(str(item.get("text") or ""))
                elif item.get("type") == "image_url":
                    total += 1024
                else:
                    total += self.count_tokens(str(item))
            return total
        if not isinstance(text, str):
            text = str(text)
        try:
            encoder = _get_encoder()
            return len(encoder.encode(text))
        except Exception:
            # Fallback to character-based estimation
            return max(1, len(text) // self.CHARS_PER_TOKEN_FALLBACK)

    def estimate_tokens(self, text: str) -> int:
        """Alias for count_tokens (backward compatibility)."""
        return self.count_tokens(text)

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


# Singleton instance for convenience
_token_counter: TokenCounter | None = None


def get_token_counter() -> TokenCounter:
    """Get the singleton TokenCounter instance."""
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter()
    return _token_counter
