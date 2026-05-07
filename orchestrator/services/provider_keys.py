"""Persistence and runtime application of provider API keys."""

from __future__ import annotations

import os
from typing import Any

from orchestrator.models.registry import PROVIDERS
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.app_settings_repo import AppSettingsRepo

SETTINGS_KEY = "provider_api_keys"
SUPPORTED_PROVIDERS = tuple(
    provider_name for provider_name in ("openrouter", "deepinfra", "fireworks")
)
_runtime_env_fallbacks = {
    provider: os.environ.get(PROVIDERS[provider].api_key_env)
    for provider in SUPPORTED_PROVIDERS
}


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider '{provider}'")
    return normalized


async def get_persisted_provider_keys() -> dict[str, str]:
    """Return stored provider API keys."""
    db = await get_db()
    repo = AppSettingsRepo(db)
    row = await repo.get(SETTINGS_KEY)
    if not row:
        return {}

    value = row.get("value") or {}
    if not isinstance(value, dict):
        return {}

    result: dict[str, str] = {}
    for provider, api_key in value.items():
        if provider in SUPPORTED_PROVIDERS and isinstance(api_key, str) and api_key.strip():
            result[provider] = api_key.strip()
    return result


async def _store_provider_keys(keys: dict[str, str]) -> None:
    db = await get_db()
    repo = AppSettingsRepo(db)
    await repo.put(SETTINGS_KEY, keys)


def _apply_provider_key_to_env(provider: str, api_key: str) -> None:
    env_name = PROVIDERS[provider].api_key_env
    if env_name:
        os.environ[env_name] = api_key


def _clear_provider_key_from_env(provider: str) -> None:
    env_name = PROVIDERS[provider].api_key_env
    if env_name:
        original = _runtime_env_fallbacks.get(provider)
        if original:
            os.environ[env_name] = original
        else:
            os.environ.pop(env_name, None)


async def set_provider_api_key(provider: str, api_key: str) -> None:
    """Persist and activate a provider API key."""
    normalized = _normalize_provider(provider)
    trimmed = api_key.strip()
    if not trimmed:
        raise ValueError("API key cannot be empty")

    keys = await get_persisted_provider_keys()
    env_name = PROVIDERS[normalized].api_key_env
    if env_name and normalized not in keys:
        _runtime_env_fallbacks[normalized] = os.environ.get(env_name)
    keys[normalized] = trimmed
    await _store_provider_keys(keys)
    _apply_provider_key_to_env(normalized, trimmed)


async def clear_provider_api_key(provider: str) -> bool:
    """Delete a persisted provider API key.

    Returns True if a stored key was removed.
    """
    normalized = _normalize_provider(provider)
    keys = await get_persisted_provider_keys()
    removed = normalized in keys
    keys.pop(normalized, None)
    await _store_provider_keys(keys)
    _clear_provider_key_from_env(normalized)
    return removed


async def apply_persisted_provider_keys_to_environment() -> None:
    """Load persisted keys into process environment on startup."""
    keys = await get_persisted_provider_keys()
    for provider, api_key in keys.items():
        _apply_provider_key_to_env(provider, api_key)


async def get_provider_key_statuses() -> list[dict[str, Any]]:
    """Return provider key availability metadata without exposing secrets."""
    persisted = await get_persisted_provider_keys()
    statuses: list[dict[str, Any]] = []
    for provider in SUPPORTED_PROVIDERS:
        provider_def = PROVIDERS[provider]
        env_name = provider_def.api_key_env
        if provider in persisted:
            source = "database"
            has_key = True
        elif env_name and os.environ.get(env_name):
            source = "environment"
            has_key = True
        else:
            source = "none"
            has_key = False
        statuses.append(
            {
                "provider": provider,
                "api_key_env": env_name,
                "has_key": has_key,
                "source": source,
            }
        )
    return statuses
