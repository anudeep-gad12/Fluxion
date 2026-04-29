"""Tests for coding-agent intent classification."""

from orchestrator.agent.intent import AgentIntent, classify_agent_intent


def test_conversational_acknowledgements():
    for text in ["thanks", "okay", "cool", "looks good", "woah love these changes cool stuff"]:
        assert classify_agent_intent(text) == AgentIntent.CONVERSATIONAL


def test_actionable_workspace_requests():
    for text in [
        "fix the failing test",
        "add a new route",
        "edit ui/src/App.tsx",
        "debug this error",
        "run the build",
    ]:
        assert classify_agent_intent(text) == AgentIntent.ACTIONABLE_WORKSPACE


def test_read_only_workspace_requests():
    for text in [
        "inspect ui/src/App.tsx",
        "why does the route fail in orchestrator/app.py",
        "review the auth flow",
    ]:
        assert classify_agent_intent(text) == AgentIntent.READ_ONLY_WORKSPACE


def test_ambiguous_turns_do_not_force_tools():
    assert classify_agent_intent("that part feels weird") == AgentIntent.AMBIGUOUS
