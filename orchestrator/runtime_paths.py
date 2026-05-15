"""Runtime path helpers for source and packaged Fluxion builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


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
