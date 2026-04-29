"""Provider-aware reasoning settings and capability resolution."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


ReasoningEffortValue = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
ReasoningSummaryValue = Literal["auto", "concise", "detailed"]
FireworksReasoningMode = Literal["effort", "thinking"]
FireworksThinkingType = Literal["enabled"]
FireworksReasoningHistoryValue = Literal["discarded", "preserved"]
FIREWORKS_MIN_THINKING_BUDGET_TOKENS = 1024
FIREWORKS_DEFAULT_THINKING_BUDGET_TOKENS = FIREWORKS_MIN_THINKING_BUDGET_TOKENS


class ReasoningSettings(BaseModel):
    """Unified runtime reasoning settings used across chat and agent runs."""

    max_output_tokens: Optional[int] = None
    reasoning_effort: Optional[ReasoningEffortValue] = None
    reasoning_summary: Optional[ReasoningSummaryValue] = None
    reasoning_enabled: Optional[bool] = None
    reasoning_max_tokens: Optional[int] = None
    reasoning_exclude: Optional[bool] = None
    fireworks_reasoning_mode: FireworksReasoningMode = "effort"
    fireworks_thinking_type: FireworksThinkingType = "enabled"
    fireworks_thinking_budget_tokens: Optional[int] = None
    fireworks_reasoning_history: Optional[FireworksReasoningHistoryValue] = None

    @model_validator(mode="after")
    def validate_fireworks_budget(self) -> "ReasoningSettings":
        """Validate Fireworks-specific thinking controls."""
        if (
            self.fireworks_reasoning_mode == "thinking"
            and self.fireworks_thinking_budget_tokens is None
        ):
            self.fireworks_thinking_budget_tokens = FIREWORKS_DEFAULT_THINKING_BUDGET_TOKENS
        if (
            self.fireworks_reasoning_mode == "thinking"
            and self.fireworks_thinking_budget_tokens is not None
            and self.fireworks_thinking_budget_tokens < 1024
        ):
            self.fireworks_thinking_budget_tokens = FIREWORKS_MIN_THINKING_BUDGET_TOKENS
        return self


class ReasoningControlCapability(BaseModel):
    """Capability metadata for a single UI control."""

    supported: bool
    reason: Optional[str] = None
    options: list[str] = Field(default_factory=list)


class ReasoningCapabilities(BaseModel):
    """Capability matrix for the active provider/model."""

    provider_family: str
    max_output_tokens: ReasoningControlCapability
    reasoning_effort: ReasoningControlCapability
    reasoning_summary: ReasoningControlCapability
    reasoning_enabled: ReasoningControlCapability
    reasoning_max_tokens: ReasoningControlCapability
    reasoning_exclude: ReasoningControlCapability
    fireworks_reasoning_mode: ReasoningControlCapability
    fireworks_thinking_budget_tokens: ReasoningControlCapability
    fireworks_reasoning_history: ReasoningControlCapability


class ReasoningSettingsResponse(BaseModel):
    """API response for global reasoning settings."""

    settings: ReasoningSettings
    capabilities: ReasoningCapabilities
    provider_family: str
    model_name: Optional[str] = None
    updated_at: Optional[str] = None
    source: str = "database"


def infer_provider_family(
    *,
    provider_name: Optional[str] = None,
    base_url: Optional[str] = None,
    provider_obj: Any = None,
) -> str:
    """Infer a normalized provider family string."""
    attr_family = getattr(provider_obj, "_reasoning_provider_family", None)
    if attr_family:
        return str(attr_family)

    for candidate in (
        provider_name,
        getattr(provider_obj, "_context_profile_provider_name", None),
    ):
        if not candidate:
            continue
        normalized = str(candidate).lower()
        if normalized in {"openrouter", "deepinfra", "fireworks", "chatgpt", "local"}:
            return normalized

    url = (base_url or getattr(provider_obj, "_base_url", "") or "").lower()
    if "openrouter.ai" in url:
        return "openrouter"
    if "deepinfra.com" in url:
        return "deepinfra"
    if "fireworks.ai" in url:
        return "fireworks"
    if "chatgpt.com" in url:
        return "chatgpt"
    if "localhost" in url or "127.0.0.1" in url:
        return "local"
    return "generic"


def resolve_reasoning_capabilities(
    provider_family: str,
    *,
    supports_reasoning: bool = False,
) -> ReasoningCapabilities:
    """Resolve UI capabilities for the active provider family."""
    unsupported = ReasoningControlCapability(supported=False, reason="Unsupported by active provider/model")
    max_output_tokens = ReasoningControlCapability(supported=True)
    reasoning_effort = ReasoningControlCapability(
        supported=False,
        reason="Active provider/model does not expose reasoning effort",
    )

    reasoning_summary = unsupported
    reasoning_enabled = unsupported
    reasoning_max_tokens = unsupported
    reasoning_exclude = unsupported
    fireworks_reasoning_mode = unsupported
    fireworks_thinking_budget_tokens = unsupported
    fireworks_reasoning_history = unsupported

    if provider_family == "openrouter":
        if supports_reasoning:
            reasoning_effort = ReasoningControlCapability(
                supported=True, options=["none", "minimal", "low", "medium", "high", "xhigh"]
            )
        reasoning_enabled = ReasoningControlCapability(supported=True, options=["true", "false"])
        reasoning_max_tokens = ReasoningControlCapability(supported=True)
        reasoning_exclude = ReasoningControlCapability(supported=True, options=["true", "false"])
    elif provider_family == "deepinfra":
        if supports_reasoning:
            reasoning_effort = ReasoningControlCapability(
                supported=True, options=["none", "low", "medium", "high"]
            )
        reasoning_enabled = ReasoningControlCapability(supported=True, options=["true", "false"])
    elif provider_family in {"openai", "chatgpt"}:
        if supports_reasoning:
            reasoning_effort = ReasoningControlCapability(
                supported=True, options=["minimal", "low", "medium", "high"]
            )
        reasoning_summary = ReasoningControlCapability(
            supported=True, options=["auto", "concise", "detailed"]
        )
    elif provider_family == "fireworks":
        if supports_reasoning:
            reasoning_effort = ReasoningControlCapability(
                supported=True, options=["low", "medium", "high"]
            )
        fireworks_reasoning_mode = ReasoningControlCapability(
            supported=True, options=["effort", "thinking"]
        )
        fireworks_thinking_budget_tokens = ReasoningControlCapability(
            supported=True,
            reason="Applies only when Fireworks reasoning mode is set to thinking",
        )
        fireworks_reasoning_history = ReasoningControlCapability(
            supported=True, options=["discarded", "preserved"]
        )

    return ReasoningCapabilities(
        provider_family=provider_family,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
        reasoning_summary=reasoning_summary,
        reasoning_enabled=reasoning_enabled,
        reasoning_max_tokens=reasoning_max_tokens,
        reasoning_exclude=reasoning_exclude,
        fireworks_reasoning_mode=fireworks_reasoning_mode,
        fireworks_thinking_budget_tokens=fireworks_thinking_budget_tokens,
        fireworks_reasoning_history=fireworks_reasoning_history,
    )


def apply_reasoning_settings(
    settings: ReasoningSettings,
    *,
    provider_family: str,
    supports_reasoning: bool,
) -> dict[str, Any]:
    """Convert unified reasoning settings into provider-specific request kwargs."""
    kwargs: dict[str, Any] = {}

    if settings.max_output_tokens is not None:
        kwargs["max_tokens"] = settings.max_output_tokens

    if not supports_reasoning:
        return kwargs

    if provider_family in {"openai", "chatgpt"}:
        reasoning: dict[str, Any] = {}
        if settings.reasoning_effort:
            reasoning["effort"] = settings.reasoning_effort
        if settings.reasoning_summary:
            reasoning["summary"] = settings.reasoning_summary
        if reasoning:
            kwargs["reasoning"] = reasoning
        return kwargs

    if provider_family == "openrouter":
        reasoning = {}
        if settings.reasoning_effort and settings.reasoning_max_tokens is None:
            reasoning["effort"] = settings.reasoning_effort
        if settings.reasoning_enabled is not None:
            reasoning["enabled"] = settings.reasoning_enabled
        if settings.reasoning_max_tokens is not None:
            reasoning["max_tokens"] = settings.reasoning_max_tokens
        if settings.reasoning_exclude is not None:
            reasoning["exclude"] = settings.reasoning_exclude
        if reasoning:
            kwargs["reasoning"] = reasoning
        return kwargs

    if provider_family == "deepinfra":
        if settings.reasoning_effort:
            kwargs["reasoning_effort"] = settings.reasoning_effort
        reasoning = {}
        if settings.reasoning_enabled is not None:
            reasoning["enabled"] = settings.reasoning_enabled
        if settings.reasoning_effort:
            reasoning["effort"] = settings.reasoning_effort
        if reasoning:
            kwargs["reasoning"] = reasoning
        return kwargs

    if provider_family == "fireworks":
        if settings.fireworks_reasoning_mode == "thinking":
            kwargs["thinking"] = {
                "type": settings.fireworks_thinking_type,
            }
            if settings.fireworks_thinking_budget_tokens is not None:
                kwargs["thinking"]["budget_tokens"] = settings.fireworks_thinking_budget_tokens
        elif settings.reasoning_effort in {"low", "medium", "high"}:
            kwargs["reasoning_effort"] = settings.reasoning_effort

        if settings.fireworks_reasoning_history:
            kwargs["reasoning_history"] = settings.fireworks_reasoning_history
        return kwargs

    if settings.reasoning_effort:
        kwargs["reasoning_effort"] = settings.reasoning_effort
        kwargs["reasoning"] = {"effort": settings.reasoning_effort}
    return kwargs
