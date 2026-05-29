"""Runtime path helpers for source and packaged Fluxion builds."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _env_flag(name: str) -> bool:
    """Return True when an environment flag is enabled."""
    return os.environ.get(name, "false").lower() in {"1", "true", "yes", "on"}


def is_packaged_app() -> bool:
    """Return True when running as the local packaged desktop app."""
    return _env_flag("FLUXION_PACKAGED") or _bundle_root() is not None


def is_static_serving_enabled() -> bool:
    """Return True when the backend should serve the built frontend."""
    return _env_flag("SERVE_STATIC")


def is_hosted_production() -> bool:
    """Return True for hosted production, not the local packaged app."""
    return is_static_serving_enabled() and not is_packaged_app()


def app_version() -> str:
    """Return the runtime app version."""
    return os.environ.get("FLUXION_APP_VERSION", "0.1.1")


def build_id() -> str:
    """Return the runtime build identifier."""
    return os.environ.get("FLUXION_BUILD_ID", "source")


def _bundle_root() -> Path | None:
    """Return PyInstaller's extraction root when running from a bundle."""
    root = getattr(sys, "_MEIPASS", None)
    if not root:
        return None
    return Path(root)


def chat_config_path() -> Path:
    """Resolve the chat configuration path."""
    override = os.environ.get("FLUXION_CONFIG_PATH")
    if override:
        return Path(override)

    bundle_root = _bundle_root()
    if bundle_root:
        return bundle_root / "orchestrator" / "chat_config.yaml"

    return Path(__file__).parent / "chat_config.yaml"


def schema_path() -> Path:
    """Resolve the SQLite schema path."""
    override = os.environ.get("FLUXION_SCHEMA_PATH")
    if override:
        return Path(override)

    bundle_root = _bundle_root()
    if bundle_root:
        return bundle_root / "orchestrator" / "storage" / "schema.sql"

    return Path(__file__).parent / "storage" / "schema.sql"


def static_dir() -> Path:
    """Resolve the built frontend asset directory."""
    override = os.environ.get("FLUXION_STATIC_DIR")
    if override:
        return Path(override)

    bundle_root = _bundle_root()
    if bundle_root:
        return bundle_root / "ui" / "dist"

    return Path(__file__).parent.parent / "ui" / "dist"


def ui_build_info() -> dict[str, str]:
    """Return build metadata written by the UI Vite bundle step."""
    stamp_path = static_dir() / "ui-build.json"
    if not stamp_path.is_file():
        return {}
    try:
        payload = json.loads(stamp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    built_at = payload.get("builtAt")
    if isinstance(built_at, str) and built_at.strip():
        return {"built_at": built_at.strip()}
    return {}
