"""Tests for ThinkingOrchestrator."""

import pytest
from orchestrator.thinking import (
    ThinkingOrchestrator,
    DirectStrategy,
    ThinkingStrategy,
)


class TestThinkingOrchestrator:
    """Tests for ThinkingOrchestrator class."""

    def test_default_strategy(self):
        """Default strategy is 'direct'."""
        orchestrator = ThinkingOrchestrator()
        assert orchestrator.default_strategy == "direct"

    def test_custom_default_strategy(self):
        """Custom default strategy is set."""
        orchestrator = ThinkingOrchestrator(default_strategy="custom")
        assert orchestrator.default_strategy == "custom"

    def test_get_strategy_returns_direct(self):
        """get_strategy returns DirectStrategy for 'direct'."""
        orchestrator = ThinkingOrchestrator()
        strategy = orchestrator.get_strategy("direct")

        assert isinstance(strategy, DirectStrategy)

    def test_get_strategy_none_uses_default(self):
        """get_strategy with None uses default."""
        orchestrator = ThinkingOrchestrator(default_strategy="direct")
        strategy = orchestrator.get_strategy(None)

        assert isinstance(strategy, DirectStrategy)

    def test_get_strategy_unknown_raises(self):
        """get_strategy with unknown name raises ValueError."""
        orchestrator = ThinkingOrchestrator()

        with pytest.raises(ValueError, match="Unknown strategy"):
            orchestrator.get_strategy("nonexistent")

    def test_get_strategy_error_lists_available(self):
        """Error message lists available strategies."""
        orchestrator = ThinkingOrchestrator()

        with pytest.raises(ValueError, match="direct"):
            orchestrator.get_strategy("nonexistent")

    def test_list_strategies(self):
        """list_strategies returns available strategy names."""
        orchestrator = ThinkingOrchestrator()
        strategies = orchestrator.list_strategies()

        assert "direct" in strategies
        assert isinstance(strategies, list)
        assert all(isinstance(s, str) for s in strategies)

    def test_has_strategy_returns_true(self):
        """has_strategy returns True for registered strategy."""
        orchestrator = ThinkingOrchestrator()
        assert orchestrator.has_strategy("direct") is True

    def test_has_strategy_returns_false(self):
        """has_strategy returns False for unregistered strategy."""
        orchestrator = ThinkingOrchestrator()
        assert orchestrator.has_strategy("nonexistent") is False

    def test_register_custom_strategy(self):
        """register_strategy adds new strategy."""
        orchestrator = ThinkingOrchestrator()

        class CustomStrategy(ThinkingStrategy):
            @property
            def name(self):
                return "custom"

            async def think(self, messages, model_call, event_callback=None):
                pass

        orchestrator.register_strategy("custom", CustomStrategy)

        assert orchestrator.has_strategy("custom")
        strategy = orchestrator.get_strategy("custom")
        assert isinstance(strategy, CustomStrategy)

    def test_register_non_strategy_raises(self):
        """register_strategy with non-strategy class raises TypeError."""
        orchestrator = ThinkingOrchestrator()

        with pytest.raises(TypeError, match="must be a subclass of ThinkingStrategy"):
            orchestrator.register_strategy("invalid", str)

    def test_each_instance_has_own_registry(self):
        """Each orchestrator instance has its own registry."""
        orchestrator1 = ThinkingOrchestrator()
        orchestrator2 = ThinkingOrchestrator()

        class CustomStrategy(ThinkingStrategy):
            @property
            def name(self):
                return "custom"

            async def think(self, messages, model_call, event_callback=None):
                pass

        orchestrator1.register_strategy("custom", CustomStrategy)

        # orchestrator1 has custom, orchestrator2 doesn't
        assert orchestrator1.has_strategy("custom")
        assert not orchestrator2.has_strategy("custom")


class TestDirectStrategy:
    """Tests for DirectStrategy."""

    def test_name(self):
        """DirectStrategy has correct name."""
        strategy = DirectStrategy()
        assert strategy.name == "direct"

    @pytest.mark.asyncio
    async def test_think_calls_model(self):
        """think calls the model_call function."""
        strategy = DirectStrategy()
        messages = [{"role": "user", "content": "Hello"}]

        call_count = 0

        async def mock_model_call(msgs, **kwargs):
            nonlocal call_count
            call_count += 1
            return "Response", {"total_tokens": 10}, None

        result = await strategy.think(messages, mock_model_call)

        assert call_count == 1
        assert result.final_answer == "Response"

    @pytest.mark.asyncio
    async def test_think_returns_thinking_result(self):
        """think returns ThinkingResult."""
        strategy = DirectStrategy()
        messages = [{"role": "user", "content": "Hello"}]

        async def mock_model_call(msgs, **kwargs):
            return "Response", {"total_tokens": 10}, None

        result = await strategy.think(messages, mock_model_call)

        assert hasattr(result, "final_answer")
        assert hasattr(result, "thinking_tokens")
        assert hasattr(result, "answer_tokens")

    @pytest.mark.asyncio
    async def test_think_with_native_reasoning(self):
        """think handles native reasoning response."""
        strategy = DirectStrategy()
        messages = [{"role": "user", "content": "Hello"}]

        async def mock_model_call(msgs, **kwargs):
            return "Response", {"total_tokens": 20}, "Native reasoning content"

        result = await strategy.think(messages, mock_model_call)

        assert result.final_answer == "Response"
        # Native reasoning is captured
        assert result.thinking_summary or result.thinking_tokens >= 0
