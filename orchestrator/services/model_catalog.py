"""Provider model catalog assembly.

Combines Fluxion's curated presets with best-effort live provider model lists
so the UI can show a polished selector without becoming dependent on a network
fetch for basic model switching.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from orchestrator.models.registry import ModelRegistry, PROVIDERS

_CACHE_TTL_SECONDS = 300
_catalog_cache: dict[str, tuple[float, list[dict[str, Any]], Optional[str]]] = {}

VISIBLE_MODEL_IDS_BY_PROVIDER: dict[str, set[str]] = {
    # OpenAI API: GPT-5 text/reasoning models only.
    "openai": {
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.2-codex",
        "gpt-5.2",
        "gpt-5.1-codex",
    },
    # ChatGPT/Codex OAuth: GPT-5 Codex family only.
    "chatgpt": {
        "gpt-5.3-codex",
        "gpt-5.2-codex",
    },
    # Grok OAuth/subscription: separate from xAI API-key models.
    "grok": {
        "grok-build",
    },
    # xAI direct: language/coding models only; no Imagine/voice/image-only APIs.
    "xai": {
        "grok-4.3",
        "grok-build-0.1",
    },
    # OpenRouter: compact curated set mixing popular frontier, coding, cheap, and free text models.
    "openrouter": {
        "anthropic/claude-opus-4.8",
        "deepseek/deepseek-r1",
        "deepseek/deepseek-r1-0528",
        "deepseek/deepseek-v3-0324",
        "google/gemini-3.5-flash",
        "google/gemini-3.1-flash-lite",
        "inclusionai/ring-2.6-1t",
        "mistralai/mistral-medium-3-5",
        "openrouter/owl-alpha",
        "qwen/qwen3.7-max",
        "qwen/qwen3-235b-a22b",
        "stepfun/step-3.7-flash",
        "x-ai/grok-4.3",
        "x-ai/grok-build-0.1",
    },
    # Hosted OSS providers: recent language models with known costs.
    "deepinfra": {
        "Qwen/Qwen3.6-35B-A3B",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-V3.1-Terminus",
        "openai/gpt-oss-120b",
        "stepfun-ai/Step-3.5-Flash",
        "zai-org/GLM-5.1",
    },
    "fireworks": {
        "accounts/fireworks/models/deepseek-v4-flash",
        "accounts/fireworks/models/deepseek-v4-pro",
        "accounts/fireworks/models/glm-5p1",
        "accounts/fireworks/models/gpt-oss-120b",
        "accounts/fireworks/models/gpt-oss-20b",
        "accounts/fireworks/models/kimi-k2p6",
        "accounts/fireworks/models/minimax-m2p7",
        "accounts/fireworks/models/qwen3p6-plus",
    },
}


def _cost_per_million(raw: Any) -> Optional[float]:
    """Convert OpenRouter per-token string pricing to per-million display value."""
    try:
        if raw in (None, ""):
            return None
        return round(float(raw) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def _is_visible(provider_name: str, model: dict[str, Any]) -> bool:
    """Return whether a model should be shown in the polished picker."""
    allowed = VISIBLE_MODEL_IDS_BY_PROVIDER.get(provider_name)
    if not allowed:
        return True
    return str(model.get("model_id") or "") in allowed


def _merge_models(
    curated: list[dict[str, Any]],
    live: list[dict[str, Any]],
    *,
    provider_name: str,
) -> list[dict[str, Any]]:
    """Merge live models into curated presets, preserving curated metadata."""
    visible_curated = [m for m in curated if _is_visible(provider_name, m)]
    visible_live = [m for m in live if _is_visible(provider_name, m)]
    merged: dict[str, dict[str, Any]] = {m["model_id"]: {**m} for m in visible_curated}
    for live_model in visible_live:
        model_id = live_model.get("model_id")
        if not model_id:
            continue
        if model_id in merged:
            next_model = {**live_model, **merged[model_id]}
            next_model["source"] = "curated+live"
            merged[model_id] = next_model
        else:
            merged[model_id] = live_model

    return sorted(
        merged.values(),
        key=lambda item: (
            0 if item.get("recommended") else 1,
            str(item.get("category") or "general"),
            str(item.get("display_name") or item.get("model_id") or "").lower(),
        ),
    )


async def _fetch_openrouter_models() -> tuple[list[dict[str, Any]], Optional[str]]:
    """Fetch OpenRouter model metadata."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            data = response.json().get("data") or []
    except Exception as exc:  # pragma: no cover - exact network failure varies
        return [], str(exc)

    models: list[dict[str, Any]] = []
    for item in data:
        supported = item.get("supported_parameters") or []
        pricing = item.get("pricing") or {}
        top_provider = item.get("top_provider") or {}
        architecture = item.get("architecture") or {}
        modalities = architecture.get("input_modalities") or []
        context_window = item.get("context_length") or top_provider.get("context_length") or 32768
        max_output = top_provider.get("max_completion_tokens") or 8192
        models.append(
            {
                "model_id": item.get("id"),
                "display_name": item.get("name") or item.get("id"),
                "aliases": [],
                "context_window": int(context_window or 32768),
                "max_output_tokens": int(max_output or 8192),
                "supports_tools": "tools" in supported,
                "supports_reasoning": "reasoning" in supported or "include_reasoning" in supported,
                "supports_vision": "image" in modalities,
                "input_cost_per_million": _cost_per_million(pricing.get("prompt")),
                "cached_input_cost_per_million": _cost_per_million(pricing.get("input_cache_read")),
                "output_cost_per_million": _cost_per_million(pricing.get("completion")),
                "recommended": False,
                "category": "live",
                "source": "live",
                "supported_parameters": supported,
            }
        )
    return models, None


async def _fetch_openai_or_xai_models(provider_name: str, api_key: Optional[str]) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Fetch OpenAI-compatible /models list for OpenAI or xAI."""
    if not api_key:
        return [], None

    provider = PROVIDERS[provider_name]
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            response = await client.get(f"{provider.base_url.rstrip('/')}/models")
            response.raise_for_status()
            data = response.json().get("data") or []
    except Exception as exc:  # pragma: no cover - exact network failure varies
        return [], str(exc)

    models: list[dict[str, Any]] = []
    for item in data:
        model_id = item.get("id")
        if not model_id:
            continue
        lower_model_id = model_id.lower()
        supports_reasoning = any(token in lower_model_id for token in ("gpt-5", "grok-4", "grok-build"))
        models.append(
            {
                "model_id": model_id,
                "display_name": model_id,
                "aliases": [],
                "context_window": 32768,
                "max_output_tokens": 8192,
                "supports_tools": True,
                "supports_reasoning": supports_reasoning,
                "supports_vision": any(token in lower_model_id for token in ("gpt-5", "grok")),
                "input_cost_per_million": None,
                "cached_input_cost_per_million": None,
                "output_cost_per_million": None,
                "recommended": False,
                "category": "live",
                "source": "live",
            }
        )
    return models, None


async def _get_live_models(provider_name: str, api_key: Optional[str]) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Return cached live provider models."""
    now = time.time()
    cached = _catalog_cache.get(provider_name)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1], cached[2]

    if provider_name == "openrouter":
        models, error = await _fetch_openrouter_models()
    elif provider_name in {"openai", "xai"}:
        models, error = await _fetch_openai_or_xai_models(provider_name, api_key)
    else:
        models, error = [], None

    _catalog_cache[provider_name] = (now, models, error)
    return models, error


async def list_model_catalog(
    *,
    chatgpt_status: Optional[dict[str, Any]] = None,
    grok_status: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Return provider-grouped model catalog with account metadata."""
    grouped = ModelRegistry.list_models()

    live_targets = []
    for provider_name in ("openai", "xai", "openrouter"):
        provider_info = grouped.get(provider_name)
        if provider_info and provider_info.get("available"):
            live_targets.append((provider_name, provider_info))

    live_results = await asyncio.gather(
        *[
            _get_live_models(
                provider_name,
                ModelRegistry._get_api_key(PROVIDERS[provider_name]),  # noqa: SLF001 - registry helper
            )
            for provider_name, _info in live_targets
        ],
        return_exceptions=True,
    )

    for (provider_name, provider_info), result in zip(live_targets, live_results):
        live_models: list[dict[str, Any]] = []
        catalog_error: Optional[str] = None
        if isinstance(result, Exception):
            catalog_error = str(result)
        else:
            live_models, catalog_error = result
        provider_info["models"] = _merge_models(
            provider_info["models"],
            live_models,
            provider_name=provider_name,
        )
        provider_info["catalog_source"] = "curated+live" if live_models else "curated"
        provider_info["catalog_error"] = catalog_error

    if "chatgpt" in grouped:
        status = chatgpt_status or {"enabled": True, "authenticated": False}
        grouped["chatgpt"]["available"] = bool(status.get("authenticated"))
        grouped["chatgpt"]["auth"] = {
            "enabled": bool(status.get("enabled", True)),
            "authenticated": bool(status.get("authenticated")),
            "account_id": status.get("account_id"),
            "expires_at": status.get("expires_at"),
            "login_url": "/api/auth/chatgpt/login",
            "logout_url": "/api/auth/chatgpt/logout",
        }
        grouped["chatgpt"]["catalog_source"] = "curated"
        grouped["chatgpt"]["catalog_error"] = None

    if "grok" in grouped:
        status = grok_status or {"enabled": True, "authenticated": False}
        grouped["grok"]["available"] = bool(status.get("authenticated"))
        grouped["grok"]["auth"] = {
            "enabled": bool(status.get("enabled", True)),
            "authenticated": bool(status.get("authenticated")),
            "account_id": status.get("account_id"),
            "expires_at": status.get("expires_at"),
            "login_url": "/api/auth/grok/login",
            "logout_url": "/api/auth/grok/logout",
            "login_running": bool(status.get("login_running")),
            "last_error": status.get("last_error"),
        }
        grouped["grok"]["catalog_source"] = "curated"
        grouped["grok"]["catalog_error"] = None

    for provider_info in grouped.values():
        provider_info.setdefault("catalog_source", "curated")
        provider_info.setdefault("catalog_error", None)

    for provider_name, provider_info in grouped.items():
        provider_info["models"] = [
            model for model in provider_info.get("models", []) if _is_visible(provider_name, model)
        ]

    return grouped
