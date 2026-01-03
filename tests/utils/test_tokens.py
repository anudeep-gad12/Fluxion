"""Tests for token counting utilities."""

import pytest
from orchestrator.utils.tokens import TokenCounter, get_token_counter


class TestTokenCounter:
    """Tests for TokenCounter class."""

    @pytest.fixture
    def counter(self):
        """Create a TokenCounter instance."""
        return TokenCounter()

    def test_count_empty_string(self, counter):
        """Empty string returns 0 tokens."""
        assert counter.count_tokens("") == 0

    def test_count_simple_text(self, counter):
        """Simple text returns reasonable token count."""
        # "Hello world" is typically 2 tokens
        count = counter.count_tokens("Hello world")
        assert count >= 2
        assert count <= 4  # Allow some variance

    def test_count_longer_text(self, counter):
        """Longer text scales appropriately."""
        short_count = counter.count_tokens("Hello")
        long_count = counter.count_tokens("Hello world, how are you doing today?")

        assert long_count > short_count

    def test_count_special_characters(self, counter):
        """Special characters are tokenized."""
        count = counter.count_tokens("Hello! How are you? I'm fine.")
        assert count > 0

    def test_count_unicode(self, counter):
        """Unicode text is tokenized."""
        count = counter.count_tokens("こんにちは世界")  # Japanese: Hello world
        assert count > 0

    def test_count_code(self, counter):
        """Code is tokenized."""
        code = "def hello():\n    print('Hello, world!')"
        count = counter.count_tokens(code)
        assert count > 5

    def test_estimate_tokens_alias(self, counter):
        """estimate_tokens is alias for count_tokens."""
        text = "Hello world"
        assert counter.estimate_tokens(text) == counter.count_tokens(text)

    def test_count_message_dicts_empty_list(self, counter):
        """Empty message list returns 0."""
        assert counter.count_message_dicts([]) == 0

    def test_count_message_dicts_single_message(self, counter):
        """Single message includes overhead."""
        messages = [{"role": "user", "content": "Hello"}]
        count = counter.count_message_dicts(messages)

        # Should include ROLE_OVERHEAD (4 tokens) plus content tokens
        content_count = counter.count_tokens("Hello")
        assert count == content_count + TokenCounter.ROLE_OVERHEAD

    def test_count_message_dicts_multiple_messages(self, counter):
        """Multiple messages accumulate correctly."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        count = counter.count_message_dicts(messages)

        # Should be sum of all content tokens plus overhead per message
        expected_overhead = TokenCounter.ROLE_OVERHEAD * 3
        assert count >= expected_overhead

    def test_count_message_dicts_handles_missing_content(self, counter):
        """Missing content key is handled."""
        messages = [{"role": "user"}]  # No content key
        count = counter.count_message_dicts(messages)

        # Should just be the overhead
        assert count == TokenCounter.ROLE_OVERHEAD


class TestGetTokenCounter:
    """Tests for get_token_counter singleton."""

    def test_returns_token_counter(self):
        """Returns a TokenCounter instance."""
        counter = get_token_counter()
        assert isinstance(counter, TokenCounter)

    def test_returns_same_instance(self):
        """Returns the same instance (singleton)."""
        counter1 = get_token_counter()
        counter2 = get_token_counter()
        assert counter1 is counter2

    def test_instance_is_functional(self):
        """Singleton instance works correctly."""
        counter = get_token_counter()
        count = counter.count_tokens("Hello world")
        assert count > 0
