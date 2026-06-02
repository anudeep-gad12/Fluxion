"""Persistence and resolution for unified runtime reasoning settings."""

from __future__ import annotations

from typing import Any, Optional

from orchestrator.config import ChatConfig, get_chat_config
from orchestrator.reasoning_controls import (
    ReasoningCapabilities,
    ReasoningSettings,
    infer_provider_family,
    resolve_reasoning_capabilities,
)
from orchestrator.storage.db import get_db
from orchestrator.storage.repositories.app_settings_repo import AppSettingsRepo

SETTINGS_KEY = "reasoning_settings"
LEGACY_STATIC_MAX_OUTPUT_TOKEN_DEFAULTS = {2048}


def default_reasoning_settings(config: Optional[ChatConfig] = None) -> ReasoningSettings:
    """Build default runtime settings from YAML config."""
    cfg = config or get_chat_config()
    defaults = cfg.reasoning_controls.model_dump()
    if defaults.get("reasoning_effort") is None:
        defaults["reasoning_effort"] = cfg.model.reasoning_effort
    return ReasoningSettings(**defaults)


def _should_migrate_legacy_max_output_default(
    settings: ReasoningSettings,
    cfg: ChatConfig,
) -> bool:
    """Detect the old static 2048-token default and migrate it to auto/model-max.

    This avoids carrying an old global default across models while preserving
    user-customized caps.
    """
    if settings.max_output_tokens not in LEGACY_STATIC_MAX_OUTPUT_TOKEN_DEFAULTS:
        return False

    default_settings = default_reasoning_settings(cfg)
    return settings.model_copy(update={"max_output_tokens": None}) == default_settings


async def get_runtime_reasoning_settings(
    *,
    config: Optional[ChatConfig] = None,
) -> tuple[ReasoningSettings, Optional[str], str]:
    """Get runtime reasoning settings, initializing from config if absent."""
    cfg = config or get_chat_config()
    db = await get_db()
    repo = AppSettingsRepo(db)
    row = await repo.get(SETTINGS_KEY)
    if row:
        settings = ReasoningSettings(**row["value"])
        if _should_migrate_legacy_max_output_default(settings, cfg):
            settings = settings.model_copy(update={"max_output_tokens": None})
            stored = await repo.put(SETTINGS_KEY, settings.model_dump())
            return settings, stored["updated_at"], "database_migrated"
        return settings, row["updated_at"], "database"

    settings = default_reasoning_settings(cfg)
    stored = await repo.put(SETTINGS_KEY, settings.model_dump())
    return settings, stored["updated_at"], "config_default"


async def update_runtime_reasoning_settings(
    settings: ReasoningSettings,
) -> tuple[ReasoningSettings, Optional[str]]:
    """Persist runtime reasoning settings globally."""
    db = await get_db()
    repo = AppSettingsRepo(db)
    stored = await repo.put(SETTINGS_KEY, settings.model_dump())
    return settings, stored["updated_at"]


def get_reasoning_capabilities_for_target(
    *,
    provider_name: Optional[str] = None,
    base_url: Optional[str] = None,
    provider_obj: Any = None,
    supports_reasoning: bool = False,
) -> ReasoningCapabilities:
    """Resolve provider-aware capabilities for the active target."""
    provider_family = infer_provider_family(
        provider_name=provider_name,
        base_url=base_url,
        provider_obj=provider_obj,
    )
    return resolve_reasoning_capabilities(
        provider_family,
        supports_reasoning=supports_reasoning,
    )
