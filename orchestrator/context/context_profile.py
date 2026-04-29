"""Normalized model context profile resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ModelContextProfile:
    """Normalized active-model context profile used across the app."""

    provider_name: str
    model_id: str
    display_name: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_reasoning: bool
    pricing: dict[str, Optional[float]]
    source: str

    @property
    def effective_input_budget(self) -> int:
        return max(1, self.context_window - self.max_output_tokens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "effective_input_budget": self.effective_input_budget,
            "supports_tools": self.supports_tools,
            "supports_reasoning": self.supports_reasoning,
            "pricing": self.pricing,
            "source": self.source,
        }


def _pricing_dict(
    input_cost: Optional[float],
    cached_input_cost: Optional[float],
    output_cost: Optional[float],
) -> dict[str, Optional[float]]:
    return {
        "input_cost_per_million": input_cost,
        "cached_input_cost_per_million": cached_input_cost,
        "output_cost_per_million": output_cost,
    }


def profile_from_resolved_model(resolved_model: Any, source: str = "registry") -> ModelContextProfile:
    return ModelContextProfile(
        provider_name=str(getattr(resolved_model, "provider_name", "unknown")),
        model_id=str(getattr(resolved_model, "model_id", "unknown")),
        display_name=str(getattr(resolved_model, "display_name", getattr(resolved_model, "model_id", "unknown"))),
        context_window=max(1, int(getattr(resolved_model, "context_window", 32768))),
        max_output_tokens=max(1, int(getattr(resolved_model, "max_output_tokens", 8192))),
        supports_tools=bool(getattr(resolved_model, "supports_tools", True)),
        supports_reasoning=bool(getattr(resolved_model, "reasoning_effort", None)),
        pricing=_pricing_dict(
            getattr(resolved_model, "input_cost_per_million", None),
            getattr(resolved_model, "cached_input_cost_per_million", None),
            getattr(resolved_model, "output_cost_per_million", None),
        ),
        source=source,
    )


def profile_from_provider(
    provider: Any,
    *,
    fallback_model_id: Optional[str] = None,
    fallback_display_name: Optional[str] = None,
    fallback_provider_name: Optional[str] = None,
    source: str,
) -> ModelContextProfile:
    model_id = str(
        getattr(provider, "_context_profile_model_id", None)
        or fallback_model_id
        or getattr(provider, "_default_model", None)
        or "unknown"
    )
    display_name = str(
        getattr(provider, "_context_profile_display_name", None)
        or fallback_display_name
        or model_id
    )
    provider_name = str(
        getattr(provider, "_context_profile_provider_name", None)
        or fallback_provider_name
        or "custom"
    )
    context_window = max(1, int(getattr(provider, "_context_window", 32768) or 32768))
    max_output_tokens = max(1, int(getattr(provider, "_max_output_tokens", 8192) or 8192))
    supports_reasoning_attr = getattr(provider, "_supports_reasoning", None)
    supports_reasoning = bool(
        supports_reasoning_attr if supports_reasoning_attr is not None else getattr(provider, "_reasoning_request_param", None)
    )
    supports_tools_attr = getattr(provider, "_supports_tools", None)
    supports_tools = bool(True if supports_tools_attr is None else supports_tools_attr)

    return ModelContextProfile(
        provider_name=provider_name,
        model_id=model_id,
        display_name=display_name,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        supports_tools=supports_tools,
        supports_reasoning=supports_reasoning,
        pricing=_pricing_dict(
            getattr(provider, "_input_cost_per_million", None),
            getattr(provider, "_cached_input_cost_per_million", None),
            getattr(provider, "_output_cost_per_million", None),
        ),
        source=source,
    )


def resolve_model_context_profile(
    *,
    model_name: Optional[str],
    provider_override: Any = None,
    resolved_model: Any = None,
    config: Any = None,
) -> ModelContextProfile:
    """Resolve a normalized context profile from registry/custom/local/config."""
    if resolved_model is not None:
        return profile_from_resolved_model(resolved_model, source="registry")

    if provider_override is not None and hasattr(provider_override, "_context_window"):
        source = str(getattr(provider_override, "_context_profile_source", None) or "custom")
        return profile_from_provider(
            provider_override,
            fallback_model_id=model_name,
            fallback_display_name=model_name,
            fallback_provider_name=getattr(provider_override, "_provider_name", None),
            source=source,
        )

    if model_name:
        try:
            from orchestrator.models.registry import ModelRegistry, _ALIAS_INDEX, _MODEL_ID_INDEX

            lower_name = model_name.strip().lower()
            if lower_name in _ALIAS_INDEX or lower_name in _MODEL_ID_INDEX:
                return profile_from_resolved_model(ModelRegistry.resolve(model_name), source="registry")
        except Exception:
            pass

    cfg = config
    if cfg is None:
        from orchestrator.config import get_chat_config

        cfg = get_chat_config()

    return ModelContextProfile(
        provider_name=getattr(getattr(cfg, "provider", None), "name", None) or "config",
        model_id=model_name or getattr(getattr(cfg, "model", None), "name", "unknown"),
        display_name=model_name or getattr(getattr(cfg, "model", None), "name", "unknown"),
        context_window=max(32768, int(getattr(getattr(cfg, "context", None), "max_tokens", 32768) or 32768)),
        max_output_tokens=max(1, int(getattr(getattr(cfg, "context", None), "reserve_for_response", 8192) or 8192)),
        supports_tools=True,
        supports_reasoning=bool(getattr(getattr(cfg, "model", None), "reasoning_effort", None)),
        pricing=_pricing_dict(None, None, None),
        source="config_fallback",
    )
