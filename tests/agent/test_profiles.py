"""Tests for agent profile system."""

import pytest

from orchestrator.agent.profile import (
    AgentProfile,
    PROFILES,
    get_profile,
    RESEARCH_SYSTEM_PROMPT,
    CODING_SYSTEM_PROMPT,
)


class TestGetProfile:
    """Test profile resolution."""

    def test_get_research_profile(self):
        profile = get_profile("research")
        assert profile.name == "research"
        assert profile.display_name == "Web Research"
        assert profile.context_strategy == "research"

    def test_get_coding_profile(self):
        profile = get_profile("coding")
        assert profile.name == "coding"
        assert profile.display_name == "Coding Assistant"
        assert profile.context_strategy == "coding"

    def test_invalid_profile_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown profile 'nonexistent'"):
            get_profile("nonexistent")

    def test_invalid_profile_lists_valid_names(self):
        with pytest.raises(ValueError, match="coding, research"):
            get_profile("invalid")

    def test_full_profile_no_longer_exists(self):
        """The full profile has been removed (dead code)."""
        assert "full" not in PROFILES
        with pytest.raises(ValueError):
            get_profile("full")


class TestProfileToolSets:
    """Test that each profile has valid tool_sets."""

    def test_research_tool_sets(self):
        profile = get_profile("research")
        assert profile.tool_sets == ["web", "python"]
        assert "filesystem" not in profile.tool_sets

    def test_coding_tool_sets(self):
        profile = get_profile("coding")
        assert "filesystem" in profile.tool_sets
        assert "web" in profile.tool_sets
        assert "python" in profile.tool_sets


class TestProfileSystemPrompts:
    """Test system prompt templates."""

    def test_research_prompt_has_slots(self):
        profile = get_profile("research")
        assert "{date_context}" in profile.system_prompt_template
        assert "{project_context}" in profile.system_prompt_template

    def test_coding_prompt_has_slots(self):
        profile = get_profile("coding")
        assert "{date_context}" in profile.system_prompt_template
        assert "{project_context}" in profile.system_prompt_template

    def test_research_prompt_no_three_tools_claim(self):
        """The old 'ONLY three tools' claim should not be in research prompt."""
        assert "ONLY three tools" not in RESEARCH_SYSTEM_PROMPT

    def test_coding_prompt_mentions_filesystem(self):
        assert "read_file" in CODING_SYSTEM_PROMPT
        assert "edit_file" in CODING_SYSTEM_PROMPT
        assert "grep" in CODING_SYSTEM_PROMPT

    def test_coding_prompt_warns_about_remote_sandbox(self):
        """Coding prompt should warn that python_execute is remote."""
        assert "remote sandbox" in CODING_SYSTEM_PROMPT

    def test_research_prompt_has_stopping_criteria(self):
        """Research prompt includes stopping criteria."""
        assert "STOPPING CRITERIA" in RESEARCH_SYSTEM_PROMPT
        assert "FINAL ANSWER" in RESEARCH_SYSTEM_PROMPT

    def test_research_prompt_has_quality_rules(self):
        """Research prompt includes quality rules."""
        assert "QUALITY RULES" in RESEARCH_SYSTEM_PROMPT
        assert "Do NOT search for the same topic twice" in RESEARCH_SYSTEM_PROMPT

    def test_coding_prompt_has_stopping_criteria(self):
        """Coding prompt includes stopping criteria."""
        assert "STOPPING CRITERIA" in CODING_SYSTEM_PROMPT
        assert "FINAL ANSWER" in CODING_SYSTEM_PROMPT

    def test_coding_prompt_has_quality_rules(self):
        """Coding prompt includes quality rules."""
        assert "QUALITY RULES" in CODING_SYSTEM_PROMPT
        assert "Do NOT glob or list_directory the entire project" in CODING_SYSTEM_PROMPT
        assert "Do NOT re-read files" in CODING_SYSTEM_PROMPT


class TestProfilePlanStepTypes:
    """Test plan step types per profile."""

    def test_research_step_types(self):
        profile = get_profile("research")
        assert "search" in profile.plan_step_types
        assert "synthesize" in profile.plan_step_types
        assert "implement" not in profile.plan_step_types

    def test_coding_step_types(self):
        profile = get_profile("coding")
        assert "read" in profile.plan_step_types
        assert "implement" in profile.plan_step_types
        assert "test" in profile.plan_step_types
        assert "debug" in profile.plan_step_types
        assert "synthesize" in profile.plan_step_types


class TestProfileFindingsTools:
    """Test findings tools configuration."""

    def test_research_findings_tools(self):
        profile = get_profile("research")
        assert "web_search" in profile.findings_tools
        assert "web_extract" in profile.findings_tools
        assert "python_execute" in profile.findings_tools
        # Should NOT include filesystem tools
        assert "read_file" not in profile.findings_tools

    def test_coding_findings_tools(self):
        profile = get_profile("coding")
        # Should include filesystem tools
        assert "read_file" in profile.findings_tools
        assert "grep" in profile.findings_tools
        assert "glob" in profile.findings_tools
        # Should also include web tools
        assert "web_search" in profile.findings_tools


class TestProfilePlanningPrompts:
    """Test planning prompt templates."""

    def test_research_planning_prompt(self):
        profile = get_profile("research")
        assert "{query}" in profile.planning_prompt_template
        assert "{max_steps}" in profile.planning_prompt_template

    def test_coding_planning_prompt(self):
        profile = get_profile("coding")
        assert "{query}" in profile.planning_prompt_template
        assert "{project_context}" in profile.planning_prompt_template

    def test_research_planning_has_anti_redundancy(self):
        """Research planning prompt includes anti-redundancy guidelines."""
        profile = get_profile("research")
        assert "NEVER plan steps that overlap" in profile.planning_prompt_template
        assert "Each step must produce NEW information" in profile.planning_prompt_template

    def test_coding_planning_has_anti_redundancy(self):
        """Coding planning prompt includes anti-redundancy guidelines."""
        profile = get_profile("coding")
        assert "NEVER plan steps that overlap" in profile.planning_prompt_template
        assert "Each step must produce NEW information" in profile.planning_prompt_template


class TestProfileDefaults:
    """Test profile default values."""

    def test_research_max_steps(self):
        profile = get_profile("research")
        assert profile.max_steps == 10

    def test_coding_max_steps(self):
        profile = get_profile("coding")
        assert profile.max_steps == 15

    def test_all_profiles_have_max_plan_steps(self):
        for name in PROFILES:
            profile = get_profile(name)
            assert profile.max_plan_steps == 5


class TestBackwardCompat:
    """Test backward compatibility with filesystem_enabled flag."""

    def test_filesystem_enabled_maps_to_coding(self):
        """When filesystem_enabled=True, factory should use coding profile."""
        # This test validates the mapping logic described in the plan.
        # The actual mapping is in factory.py, but we verify the profile exists.
        profile = get_profile("coding")
        assert "filesystem" in profile.tool_sets

    def test_filesystem_disabled_maps_to_research(self):
        """When filesystem_enabled=False (default), should use research profile."""
        profile = get_profile("research")
        assert "filesystem" not in profile.tool_sets
