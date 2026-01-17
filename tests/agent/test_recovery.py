"""Tests for agent recovery helpers."""

import pytest
from unittest.mock import MagicMock

from orchestrator.agent.recovery import (
    RecoveryAction,
    build_recovery_messages,
    create_idempotency_key,
    determine_recovery_actions,
    get_cached_tool_result,
    should_retry_tool,
)
from orchestrator.agent.state_machine import RecoveryContext


class TestShouldRetryTool:
    """Tests for should_retry_tool function."""

    def test_idempotent_tool_running_retried(self):
        """Idempotent tools can be retried even if interrupted mid-execution."""
        registry = MagicMock()
        registry.is_idempotent.return_value = True

        assert should_retry_tool("web_search", "running", registry) is True
        registry.is_idempotent.assert_called_with("web_search")

    def test_idempotent_tool_pending_retried(self):
        """Idempotent tools in pending state can be retried."""
        registry = MagicMock()
        registry.is_idempotent.return_value = True

        assert should_retry_tool("web_extract", "pending", registry) is True

    def test_idempotent_tool_interrupted_retried(self):
        """Idempotent tools in interrupted state can be retried."""
        registry = MagicMock()
        registry.is_idempotent.return_value = True

        assert should_retry_tool("web_search", "interrupted", registry) is True

    def test_non_idempotent_pending_retried(self):
        """Non-idempotent tools in pending state (never started) can be retried."""
        registry = MagicMock()
        registry.is_idempotent.return_value = False

        assert should_retry_tool("python_execute", "pending", registry) is True

    def test_non_idempotent_running_not_retried(self):
        """Non-idempotent tools in running state should NOT be retried."""
        registry = MagicMock()
        registry.is_idempotent.return_value = False

        assert should_retry_tool("python_execute", "running", registry) is False

    def test_non_idempotent_interrupted_not_retried(self):
        """Non-idempotent tools in interrupted state should NOT be retried."""
        registry = MagicMock()
        registry.is_idempotent.return_value = False

        assert should_retry_tool("python_execute", "interrupted", registry) is False


class TestBuildRecoveryMessages:
    """Tests for build_recovery_messages function."""

    def test_no_hints_returns_original(self):
        """When no hints, returns original messages unchanged."""
        ctx = RecoveryContext(
            needs_recovery=False,
            interrupted_tool_calls=[],
            hints=[],
            last_completed_step=0,
        )
        messages = [{"role": "system", "content": "You are helpful."}]

        result = build_recovery_messages(ctx, messages)

        assert result == messages
        # Should be same reference since no modification needed
        assert result is messages

    def test_hints_inserted_after_system(self):
        """Hints are inserted after the system message."""
        hint = {"role": "system", "content": "Recovery hint", "_recovery_hint": True}
        ctx = RecoveryContext(
            needs_recovery=True,
            interrupted_tool_calls=[],
            hints=[hint],
            last_completed_step=1,
        )
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ]

        result = build_recovery_messages(ctx, messages)

        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "System prompt"
        assert result[1]["content"] == "Recovery hint"
        assert result[2]["role"] == "user"

    def test_multiple_hints_inserted_in_order(self):
        """Multiple hints are inserted in order after system message."""
        hints = [
            {"role": "system", "content": "Hint 1"},
            {"role": "system", "content": "Hint 2"},
        ]
        ctx = RecoveryContext(
            needs_recovery=True,
            interrupted_tool_calls=[],
            hints=hints,
            last_completed_step=1,
        )
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Query"},
        ]

        result = build_recovery_messages(ctx, messages)

        assert len(result) == 4
        assert result[1]["content"] == "Hint 1"
        assert result[2]["content"] == "Hint 2"

    def test_does_not_mutate_original(self):
        """Original messages list is not mutated."""
        hint = {"role": "system", "content": "Hint"}
        ctx = RecoveryContext(
            needs_recovery=True,
            interrupted_tool_calls=[],
            hints=[hint],
            last_completed_step=0,
        )
        original = [{"role": "system", "content": "System"}]
        messages_before = list(original)

        result = build_recovery_messages(ctx, original)

        assert original == messages_before
        assert result is not original

    def test_hints_inserted_at_start_if_no_system(self):
        """If no system message, hints are inserted at the beginning."""
        hint = {"role": "system", "content": "Hint"}
        ctx = RecoveryContext(
            needs_recovery=True,
            interrupted_tool_calls=[],
            hints=[hint],
            last_completed_step=0,
        )
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        result = build_recovery_messages(ctx, messages)

        assert len(result) == 3
        assert result[0]["content"] == "Hint"
        assert result[1]["role"] == "user"


class TestGetCachedToolResult:
    """Tests for get_cached_tool_result function."""

    def test_returns_result_for_successful_call(self):
        """Returns cached result for successful tool call."""
        tool_calls = [
            {
                "id": "tc-1",
                "status": "success",
                "result_summary": "Found 5 results",
            }
        ]

        result = get_cached_tool_result("tc-1", tool_calls)

        assert result is not None
        assert result["result_summary"] == "Found 5 results"
        assert result["tool_call_id"] == "tc-1"

    def test_returns_none_for_failed_call(self):
        """Returns None for failed tool call."""
        tool_calls = [
            {
                "id": "tc-1",
                "status": "error",
                "result_summary": None,
                "error_message": "API error",
            }
        ]

        result = get_cached_tool_result("tc-1", tool_calls)

        assert result is None

    def test_returns_none_for_running_call(self):
        """Returns None for tool call still in running state."""
        tool_calls = [
            {
                "id": "tc-1",
                "status": "running",
            }
        ]

        result = get_cached_tool_result("tc-1", tool_calls)

        assert result is None

    def test_returns_none_for_nonexistent_id(self):
        """Returns None when tool call ID not found."""
        tool_calls = [
            {"id": "tc-1", "status": "success"},
        ]

        result = get_cached_tool_result("tc-999", tool_calls)

        assert result is None

    def test_handles_empty_tool_calls(self):
        """Returns None for empty tool calls list."""
        result = get_cached_tool_result("tc-1", [])

        assert result is None

    def test_handles_missing_result_summary(self):
        """Handles successful call with missing result_summary gracefully."""
        tool_calls = [
            {"id": "tc-1", "status": "success"},
        ]

        result = get_cached_tool_result("tc-1", tool_calls)

        assert result is not None
        assert result["result_summary"] == ""


class TestCreateIdempotencyKey:
    """Tests for create_idempotency_key function."""

    def test_key_format(self):
        """Key follows expected format."""
        key = create_idempotency_key("run-123", 2, "web_search", "abc123")

        assert key == "run-123:2:web_search:abc123"

    def test_different_runs_different_keys(self):
        """Different run IDs produce different keys."""
        key1 = create_idempotency_key("run-1", 1, "web_search", "hash")
        key2 = create_idempotency_key("run-2", 1, "web_search", "hash")

        assert key1 != key2

    def test_different_steps_different_keys(self):
        """Different step numbers produce different keys."""
        key1 = create_idempotency_key("run-1", 1, "web_search", "hash")
        key2 = create_idempotency_key("run-1", 2, "web_search", "hash")

        assert key1 != key2

    def test_different_tools_different_keys(self):
        """Different tool names produce different keys."""
        key1 = create_idempotency_key("run-1", 1, "web_search", "hash")
        key2 = create_idempotency_key("run-1", 1, "web_extract", "hash")

        assert key1 != key2

    def test_different_args_different_keys(self):
        """Different argument hashes produce different keys."""
        key1 = create_idempotency_key("run-1", 1, "web_search", "aaa")
        key2 = create_idempotency_key("run-1", 1, "web_search", "bbb")

        assert key1 != key2

    def test_same_inputs_same_key(self):
        """Same inputs produce the same key."""
        key1 = create_idempotency_key("run-1", 1, "web_search", "hash")
        key2 = create_idempotency_key("run-1", 1, "web_search", "hash")

        assert key1 == key2


class TestDetermineRecoveryActions:
    """Tests for determine_recovery_actions function."""

    def test_idempotent_tool_gets_retry_action(self):
        """Idempotent tool in running state gets retry action."""
        registry = MagicMock()
        registry.is_idempotent.return_value = True

        interrupted = [
            {"id": "tc-1", "tool_name": "web_search", "status": "running"},
        ]

        actions = determine_recovery_actions(interrupted, registry)

        assert len(actions) == 1
        assert actions[0].action == "retry"
        assert actions[0].tool_call_id == "tc-1"
        assert actions[0].tool_name == "web_search"

    def test_non_idempotent_running_gets_hint_action(self):
        """Non-idempotent tool in running state gets inject_hint action."""
        registry = MagicMock()
        registry.is_idempotent.return_value = False

        interrupted = [
            {"id": "tc-1", "tool_name": "python_execute", "status": "running"},
        ]

        actions = determine_recovery_actions(interrupted, registry)

        assert len(actions) == 1
        assert actions[0].action == "inject_hint"
        assert actions[0].hint_message is not None
        assert "python_execute" in actions[0].hint_message["content"]
        assert actions[0].hint_message["_recovery_hint"] is True

    def test_non_idempotent_pending_gets_retry_action(self):
        """Non-idempotent tool in pending state gets retry action."""
        registry = MagicMock()
        registry.is_idempotent.return_value = False

        interrupted = [
            {"id": "tc-1", "tool_name": "python_execute", "status": "pending"},
        ]

        actions = determine_recovery_actions(interrupted, registry)

        assert len(actions) == 1
        assert actions[0].action == "retry"

    def test_multiple_tools_mixed_actions(self):
        """Multiple interrupted tools get appropriate actions."""
        registry = MagicMock()

        def is_idempotent(name):
            return name != "python_execute"

        registry.is_idempotent.side_effect = is_idempotent

        interrupted = [
            {"id": "tc-1", "tool_name": "web_search", "status": "running"},
            {"id": "tc-2", "tool_name": "python_execute", "status": "running"},
        ]

        actions = determine_recovery_actions(interrupted, registry)

        assert len(actions) == 2
        assert actions[0].action == "retry"  # web_search is idempotent
        assert actions[1].action == "inject_hint"  # python_execute is not

    def test_empty_list_returns_empty(self):
        """Empty interrupted list returns empty actions."""
        registry = MagicMock()

        actions = determine_recovery_actions([], registry)

        assert actions == []


class TestRecoveryAction:
    """Tests for RecoveryAction dataclass."""

    def test_create_retry_action(self):
        """Can create a retry action."""
        action = RecoveryAction(
            tool_call_id="tc-1",
            tool_name="web_search",
            action="retry",
        )

        assert action.tool_call_id == "tc-1"
        assert action.tool_name == "web_search"
        assert action.action == "retry"
        assert action.cached_result is None
        assert action.hint_message is None

    def test_create_hint_action(self):
        """Can create a hint injection action."""
        hint = {"role": "system", "content": "Hint"}
        action = RecoveryAction(
            tool_call_id="tc-1",
            tool_name="python_execute",
            action="inject_hint",
            hint_message=hint,
        )

        assert action.action == "inject_hint"
        assert action.hint_message == hint

    def test_create_skip_action_with_cache(self):
        """Can create a skip action with cached result."""
        cached = {"result_summary": "cached"}
        action = RecoveryAction(
            tool_call_id="tc-1",
            tool_name="web_search",
            action="skip",
            cached_result=cached,
        )

        assert action.action == "skip"
        assert action.cached_result == cached
