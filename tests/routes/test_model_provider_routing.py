"""Model provider routing regressions."""

from orchestrator.routes import agent_runs, runs


def test_agent_registry_selection_preserves_grok_provider():
    assert agent_runs._registry_selection("grok", "grok-build") == "grok:grok-build"  # noqa: SLF001


def test_chat_registry_selection_preserves_grok_provider():
    assert runs._registry_selection("grok", "grok-build") == "grok:grok-build"  # noqa: SLF001


def test_registry_selection_preserves_other_providers():
    assert runs._registry_selection("fireworks", "accounts/fireworks/models/kimi-k2p6") == (  # noqa: SLF001
        "fireworks:accounts/fireworks/models/kimi-k2p6"
    )
    assert agent_runs._registry_selection("openrouter", "qwen/qwen3-72b") == (  # noqa: SLF001
        "openrouter:qwen/qwen3-72b"
    )


def test_registry_selection_does_not_double_prefix():
    assert runs._registry_selection("grok", "grok:grok-build") == "grok:grok-build"  # noqa: SLF001
