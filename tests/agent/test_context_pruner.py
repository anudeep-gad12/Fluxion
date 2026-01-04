"""Tests for ContextPruner."""

import pytest

from orchestrator.agent.context_pruner import ContextPruner, PruneStats


class TestContextPrunerInit:
    """Tests for ContextPruner initialization."""

    def test_default_values(self):
        """Default initialization uses expected values."""
        pruner = ContextPruner()
        assert pruner.keep_full_steps == 2
        assert pruner.max_python_chars == 500

    def test_custom_values(self):
        """Custom values are applied."""
        pruner = ContextPruner(keep_full_steps=3, max_python_output_chars=1000)
        assert pruner.keep_full_steps == 3
        assert pruner.max_python_chars == 1000


class TestContextPrunerPrune:
    """Tests for the prune method."""

    def test_empty_messages_returns_empty(self):
        """Empty input returns empty output."""
        pruner = ContextPruner()
        assert pruner.prune([], current_step=1) == []

    def test_non_tool_messages_unchanged(self):
        """Non-tool messages are not modified."""
        pruner = ContextPruner()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = pruner.prune(messages, current_step=5)
        assert result == messages

    def test_recent_tool_messages_unchanged(self):
        """Tool messages within keep_full_steps are unchanged."""
        pruner = ContextPruner(keep_full_steps=2)
        messages = [
            {
                "role": "tool",
                "content": "Long content that should not be pruned",
                "_step": 4,
                "name": "web_search",
            },
        ]
        result = pruner.prune(messages, current_step=5)
        assert result[0]["content"] == "Long content that should not be pruned"
        assert "_pruned" not in result[0]

    def test_boundary_step_not_pruned(self):
        """Tool message at exact boundary (current - keep_full_steps) is not pruned."""
        pruner = ContextPruner(keep_full_steps=2)
        messages = [
            {
                "role": "tool",
                "content": "Content at boundary",
                "_step": 3,
                "name": "web_search",
            },
        ]
        # current_step=5, keep_full_steps=2, so step 3 is at boundary (5-2=3)
        result = pruner.prune(messages, current_step=5)
        assert result[0]["content"] == "Content at boundary"
        assert "_pruned" not in result[0]

    def test_old_tool_messages_summarized(self):
        """Tool messages older than keep_full_steps are summarized."""
        pruner = ContextPruner(keep_full_steps=2)
        messages = [
            {"role": "tool", "content": "A" * 1000, "_step": 1, "name": "web_search"},
        ]
        result = pruner.prune(messages, current_step=5)
        assert "[Search results - 1000 chars]" in result[0]["content"]
        assert result[0]["_pruned"] is True

    def test_web_extract_summarization(self):
        """web_extract tool is summarized correctly."""
        pruner = ContextPruner(keep_full_steps=1)
        content = "Extracted content " * 100
        messages = [
            {"role": "tool", "content": content, "_step": 1, "name": "web_extract"},
        ]
        result = pruner.prune(messages, current_step=5)
        assert "Extracted content" in result[0]["content"]
        assert f"{len(content)} chars" in result[0]["content"]
        assert result[0]["_pruned"] is True

    def test_web_search_summarization(self):
        """web_search tool is summarized correctly."""
        pruner = ContextPruner(keep_full_steps=1)
        content = "Search results " * 100
        messages = [
            {"role": "tool", "content": content, "_step": 1, "name": "web_search"},
        ]
        result = pruner.prune(messages, current_step=5)
        assert "Search results" in result[0]["content"]
        assert f"{len(content)} chars" in result[0]["content"]

    def test_python_execute_keeps_head_tail(self):
        """python_execute keeps first/last 200 chars for long output."""
        pruner = ContextPruner(keep_full_steps=1, max_python_output_chars=500)
        long_output = "HEAD" + "X" * 600 + "TAIL"
        messages = [
            {
                "role": "tool",
                "content": long_output,
                "_step": 1,
                "name": "python_execute",
            },
        ]
        result = pruner.prune(messages, current_step=5)
        assert "HEAD" in result[0]["content"]
        assert "TAIL" in result[0]["content"]
        assert "..." in result[0]["content"]
        assert result[0]["_pruned"] is True

    def test_python_execute_short_unchanged(self):
        """python_execute under max_chars is unchanged."""
        pruner = ContextPruner(keep_full_steps=1, max_python_output_chars=500)
        messages = [
            {
                "role": "tool",
                "content": "Short output",
                "_step": 1,
                "name": "python_execute",
            },
        ]
        result = pruner.prune(messages, current_step=5)
        assert result[0]["content"] == "Short output"
        assert "_pruned" not in result[0]

    def test_unknown_tool_summarized(self):
        """Unknown tools are summarized with generic message."""
        pruner = ContextPruner(keep_full_steps=1)
        messages = [
            {
                "role": "tool",
                "content": "Some data",
                "_step": 1,
                "name": "unknown_tool",
            },
        ]
        result = pruner.prune(messages, current_step=5)
        assert "Tool result" in result[0]["content"]
        assert "9 chars" in result[0]["content"]

    def test_step_metadata_mapping(self):
        """step_metadata dict is used for step lookup."""
        pruner = ContextPruner(keep_full_steps=1)
        messages = [
            {
                "role": "tool",
                "content": "Data from search",
                "tool_call_id": "tc-1",
                "name": "web_search",
            },
        ]
        step_metadata = {"tc-1": 1}
        result = pruner.prune(messages, current_step=5, step_metadata=step_metadata)
        assert result[0]["_pruned"] is True

    def test_unknown_step_not_pruned(self):
        """Messages without step info are not pruned."""
        pruner = ContextPruner(keep_full_steps=1)
        messages = [
            {"role": "tool", "content": "Data without step", "name": "web_search"},
        ]
        result = pruner.prune(messages, current_step=5)
        assert result[0]["content"] == "Data without step"
        assert "_pruned" not in result[0]

    def test_mixed_messages_selective_pruning(self):
        """Mixed messages are selectively pruned based on step."""
        pruner = ContextPruner(keep_full_steps=2)
        messages = [
            {"role": "user", "content": "Query"},
            {"role": "tool", "content": "A" * 100, "_step": 1, "name": "web_search"},
            {"role": "assistant", "content": "Processing..."},
            {"role": "tool", "content": "B" * 100, "_step": 4, "name": "web_search"},
        ]
        result = pruner.prune(messages, current_step=5)

        # User and assistant messages unchanged
        assert result[0]["content"] == "Query"
        assert result[2]["content"] == "Processing..."

        # Old tool message (step 1) should be pruned
        assert result[1]["_pruned"] is True

        # Recent tool message (step 4) should not be pruned
        assert "_pruned" not in result[3]

    def test_preserves_other_message_fields(self):
        """Pruning preserves other fields in the message."""
        pruner = ContextPruner(keep_full_steps=1)
        messages = [
            {
                "role": "tool",
                "content": "A" * 1000,
                "_step": 1,
                "name": "web_search",
                "tool_call_id": "tc-123",
                "custom_field": "preserved",
            },
        ]
        result = pruner.prune(messages, current_step=5)
        assert result[0]["tool_call_id"] == "tc-123"
        assert result[0]["custom_field"] == "preserved"
        assert result[0]["name"] == "web_search"


class TestContextPrunerPruneWithStats:
    """Tests for prune_with_stats method."""

    def test_returns_stats(self):
        """prune_with_stats returns statistics."""
        pruner = ContextPruner(keep_full_steps=1)
        messages = [
            {"role": "tool", "content": "A" * 1000, "_step": 1, "name": "web_search"},
            {"role": "tool", "content": "B" * 100, "_step": 5, "name": "web_search"},
        ]
        result, stats = pruner.prune_with_stats(messages, current_step=5)
        assert stats.original_messages == 2
        assert stats.pruned_messages == 2
        assert stats.messages_summarized == 1
        assert stats.estimated_tokens_saved > 0

    def test_empty_messages_stats(self):
        """Empty messages returns zero stats."""
        pruner = ContextPruner()
        result, stats = pruner.prune_with_stats([], current_step=1)
        assert stats.original_messages == 0
        assert stats.messages_summarized == 0
        assert stats.estimated_tokens_saved == 0

    def test_no_pruning_zero_saved(self):
        """No pruning means zero tokens saved."""
        pruner = ContextPruner(keep_full_steps=5)
        messages = [
            {"role": "tool", "content": "Data", "_step": 3, "name": "web_search"},
        ]
        result, stats = pruner.prune_with_stats(messages, current_step=5)
        assert stats.messages_summarized == 0
        assert stats.estimated_tokens_saved == 0


class TestContextPrunerEstimateTokens:
    """Tests for token estimation."""

    def test_estimate_tokens_basic(self):
        """Token estimation works for basic messages."""
        pruner = ContextPruner()
        messages = [{"role": "user", "content": "A" * 400}]
        tokens = pruner.estimate_tokens(messages)
        # 400 chars + 10 overhead = 410, / 4 = ~102
        assert tokens > 0
        assert tokens < 200

    def test_estimate_tokens_empty(self):
        """Empty messages returns minimal tokens."""
        pruner = ContextPruner()
        tokens = pruner.estimate_tokens([])
        assert tokens == 0

    def test_estimate_tokens_multiple_messages(self):
        """Multiple messages accumulate tokens."""
        pruner = ContextPruner()
        messages = [
            {"role": "user", "content": "A" * 100},
            {"role": "assistant", "content": "B" * 100},
        ]
        tokens = pruner.estimate_tokens(messages)
        # 200 chars + 20 overhead = 220, / 4 = 55
        assert tokens > 50


class TestPruneStats:
    """Tests for PruneStats dataclass."""

    def test_stats_fields(self):
        """PruneStats has expected fields."""
        stats = PruneStats(
            original_messages=10,
            pruned_messages=10,
            messages_summarized=3,
            estimated_tokens_saved=500,
        )
        assert stats.original_messages == 10
        assert stats.pruned_messages == 10
        assert stats.messages_summarized == 3
        assert stats.estimated_tokens_saved == 500
