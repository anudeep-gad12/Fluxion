"""Tests for context gathering strategies."""

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.agent.context import (
    CodingContextStrategy,
    FullContextStrategy,
    ResearchContextStrategy,
    get_context_strategy,
    _truncate,
    _run_cmd,
)


class TestGetContextStrategy:
    """Test strategy resolution."""

    def test_get_research_strategy(self):
        strategy = get_context_strategy("research")
        assert isinstance(strategy, ResearchContextStrategy)

    def test_get_coding_strategy(self):
        strategy = get_context_strategy("coding")
        assert isinstance(strategy, CodingContextStrategy)

    def test_get_full_strategy(self):
        strategy = get_context_strategy("full")
        assert isinstance(strategy, FullContextStrategy)

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown context strategy"):
            get_context_strategy("invalid")


class TestTruncate:
    """Test text truncation helper."""

    def test_short_text_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_long_text_truncated(self):
        result = _truncate("a" * 100, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        text = "a" * 50
        assert _truncate(text, 50) == text


class TestResearchContextStrategy:
    """Test ResearchContextStrategy."""

    @pytest.mark.asyncio
    async def test_returns_date_and_cutoff(self):
        strategy = ResearchContextStrategy()
        result = await strategy.gather()
        today = date.today()
        assert today.strftime("%B %d, %Y") in result
        assert "knowledge cutoff" in result.lower()

    @pytest.mark.asyncio
    async def test_ignores_working_dir(self):
        strategy = ResearchContextStrategy()
        result1 = await strategy.gather()
        result2 = await strategy.gather("/some/dir")
        assert result1 == result2


class TestCodingContextStrategy:
    """Test CodingContextStrategy."""

    @pytest.mark.asyncio
    async def test_gather_returns_project_context_header(self):
        strategy = CodingContextStrategy()
        result = await strategy.gather("/tmp")
        assert "PROJECT CONTEXT" in result

    @pytest.mark.asyncio
    async def test_gather_includes_working_dir(self):
        strategy = CodingContextStrategy()
        result = await strategy.gather("/tmp/myproject")
        assert "/tmp/myproject" in result

    @pytest.mark.asyncio
    async def test_gather_environment(self):
        strategy = CodingContextStrategy()
        result = await strategy._gather_environment()
        assert "OS:" in result

    @pytest.mark.asyncio
    async def test_load_rules_missing_file(self, tmp_path):
        """No rules file → returns None."""
        strategy = CodingContextStrategy()
        result = await strategy._load_rules(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_load_rules_reasoner_rules(self, tmp_path):
        """Finds .reasoner/rules.md."""
        rules_dir = tmp_path / ".reasoner"
        rules_dir.mkdir()
        rules_file = rules_dir / "rules.md"
        rules_file.write_text("# My Rules\nAlways use type hints.")

        strategy = CodingContextStrategy()
        result = await strategy._load_rules(str(tmp_path))
        assert result is not None
        assert "My Rules" in result

    @pytest.mark.asyncio
    async def test_load_rules_claude_md(self, tmp_path):
        """Falls back to CLAUDE.md."""
        claude_file = tmp_path / "CLAUDE.md"
        claude_file.write_text("# Claude Rules\nBe helpful.")

        strategy = CodingContextStrategy()
        result = await strategy._load_rules(str(tmp_path))
        assert result is not None
        assert "Claude Rules" in result

    @pytest.mark.asyncio
    async def test_load_rules_agents_md(self, tmp_path):
        """Falls back to AGENTS.md."""
        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("# Agent Instructions")

        strategy = CodingContextStrategy()
        result = await strategy._load_rules(str(tmp_path))
        assert result is not None
        assert "Agent Instructions" in result

    @pytest.mark.asyncio
    async def test_load_rules_priority_order(self, tmp_path):
        """.reasoner/rules.md takes priority over CLAUDE.md."""
        rules_dir = tmp_path / ".reasoner"
        rules_dir.mkdir()
        (rules_dir / "rules.md").write_text("Reasoner rules")
        (tmp_path / "CLAUDE.md").write_text("Claude rules")

        strategy = CodingContextStrategy()
        result = await strategy._load_rules(str(tmp_path))
        assert "Reasoner rules" in result

    @pytest.mark.asyncio
    async def test_load_rules_truncates_long_content(self, tmp_path):
        """Long rules files get truncated."""
        rules_dir = tmp_path / ".reasoner"
        rules_dir.mkdir()
        (rules_dir / "rules.md").write_text("x" * 5000)

        strategy = CodingContextStrategy()
        result = await strategy._load_rules(str(tmp_path))
        assert result is not None
        assert len(result) <= 2000  # _RULES_CAP
        assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_gather_runtime_state_non_git(self, tmp_path):
        """Non-git directory returns None."""
        strategy = CodingContextStrategy()
        result = await strategy._gather_runtime_state(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_gather_project_structure(self, tmp_path):
        """Creates files and checks structure output."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "test.py").write_text("import pytest")

        strategy = CodingContextStrategy()
        result = await strategy._gather_project_structure(str(tmp_path))
        assert result is not None
        assert "Files:" in result


class TestFullContextStrategy:
    """Test FullContextStrategy."""

    @pytest.mark.asyncio
    async def test_combines_research_and_coding(self):
        strategy = FullContextStrategy()
        result = await strategy.gather("/tmp")
        # Should have date context from research
        today = date.today()
        assert today.strftime("%B %d, %Y") in result
        # Should have project context from coding
        assert "PROJECT CONTEXT" in result


class TestRunCmd:
    """Test subprocess helper."""

    @pytest.mark.asyncio
    async def test_successful_command(self):
        result = await _run_cmd("echo", "hello")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_failed_command(self):
        result = await _run_cmd("false")
        assert result is None

    @pytest.mark.asyncio
    async def test_nonexistent_command(self):
        result = await _run_cmd("nonexistent_command_xyz")
        assert result is None
