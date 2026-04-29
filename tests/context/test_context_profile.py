from types import SimpleNamespace

from orchestrator.context.context_profile import resolve_model_context_profile


def test_resolve_context_profile_from_provider_override():
    provider = SimpleNamespace(
        _context_window=200000,
        _max_output_tokens=32000,
        _supports_tools=True,
        _supports_reasoning=True,
        _context_profile_source="custom",
        _context_profile_provider_name="custom-cloud",
        _context_profile_model_id="custom-model",
        _context_profile_display_name="Custom Model",
        _input_cost_per_million=1.0,
        _cached_input_cost_per_million=0.5,
        _output_cost_per_million=4.0,
    )

    profile = resolve_model_context_profile(model_name="custom-model", provider_override=provider)

    assert profile.source == "custom"
    assert profile.provider_name == "custom-cloud"
    assert profile.context_window == 200000
    assert profile.max_output_tokens == 32000
    assert profile.effective_input_budget == 168000
    assert profile.pricing["output_cost_per_million"] == 4.0


def test_resolve_context_profile_config_fallback():
    config = SimpleNamespace(
        provider=SimpleNamespace(name="fallback-provider"),
        model=SimpleNamespace(name="fallback-model", reasoning_effort=None),
        context=SimpleNamespace(max_tokens=100000, reserve_for_response=16000),
    )

    profile = resolve_model_context_profile(model_name=None, config=config)

    assert profile.source == "config_fallback"
    assert profile.provider_name == "fallback-provider"
    assert profile.model_id == "fallback-model"
    assert profile.effective_input_budget == 84000
