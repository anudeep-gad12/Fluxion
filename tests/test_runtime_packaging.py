"""Tests for packaged runtime path and launcher behavior."""

from __future__ import annotations

import plistlib
from pathlib import Path

from orchestrator import launcher
from orchestrator.runtime_paths import chat_config_path, schema_path, static_dir
from orchestrator.storage.db import Database


def test_runtime_path_overrides(monkeypatch, tmp_path):
    """Packaged env overrides should win over source paths."""
    config = tmp_path / "chat_config.yaml"
    schema = tmp_path / "schema.sql"
    static = tmp_path / "dist"
    monkeypatch.setenv("FLUXION_CONFIG_PATH", str(config))
    monkeypatch.setenv("FLUXION_SCHEMA_PATH", str(schema))
    monkeypatch.setenv("FLUXION_STATIC_DIR", str(static))

    assert chat_config_path() == config
    assert schema_path() == schema
    assert static_dir() == static


def test_start_service_requires_launch_agent_flag(monkeypatch, tmp_path):
    """Tauri/desktop builds should not install LaunchAgents unless explicitly enabled."""
    monkeypatch.delenv("FLUXION_USE_LAUNCH_AGENT", raising=False)
    paths = launcher.get_service_paths()

    try:
        launcher.start_service(paths)
    except RuntimeError as exc:
        assert "LaunchAgent mode is disabled" in str(exc)
    else:
        raise AssertionError("start_service should require FLUXION_USE_LAUNCH_AGENT")


def test_launch_agent_plist_uses_persistent_data_paths(monkeypatch, tmp_path):
    """LaunchAgent should run the app wrapper and store DB/logs outside the app."""
    monkeypatch.setenv("FLUXION_USE_LAUNCH_AGENT", "true")
    home = tmp_path / "home"
    app = tmp_path / "Fluxion.app"
    launcher_path = app / "Contents" / "MacOS" / "Fluxion"
    data = tmp_path / "data"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("FLUXION_APP_BUNDLE", str(app))
    monkeypatch.setenv("FLUXION_LAUNCHER_PATH", str(launcher_path))
    monkeypatch.setenv("FLUXION_DATA_DIR", str(data))
    monkeypatch.setenv("FLUXION_APP_VERSION", "9.9.9")
    monkeypatch.setenv("FLUXION_BUILD_ID", "abc123")

    paths = launcher.get_service_paths()
    launcher.write_launch_agent(paths)

    with paths.launch_agent.open("rb") as handle:
        plist = plistlib.load(handle)

    assert plist["ProgramArguments"] == [str(launcher_path), "serve"]
    env = plist["EnvironmentVariables"]
    assert env["DATABASE_PATH"] == str(data / "var" / "traces.sqlite")
    assert env["LOG_DIR"] == str(data / "logs")
    assert env["FLUXION_STATIC_DIR"] == str(app / "Contents" / "Resources" / "ui" / "dist")
    assert env["FLUXION_APP_VERSION"] == "9.9.9"
    assert env["FLUXION_BUILD_ID"] == "abc123"
    assert str(app) not in env["DATABASE_PATH"]
    assert launcher.launch_agent_matches(paths)


def test_packaged_database_backup_once(monkeypatch, tmp_path):
    """Packaged starts should make one SQLite backup per app version."""
    db_path = tmp_path / "traces.sqlite"
    db_path.write_bytes(b"sqlite-data")
    monkeypatch.setenv("FLUXION_PACKAGED", "true")
    monkeypatch.setenv("FLUXION_APP_VERSION", "1.2.3")

    db = Database(db_path)
    db._backup_database_file_once()
    backups = [
        path
        for path in tmp_path.glob("traces.sqlite.backup-[0-9]*")
        if not path.name.endswith(".done")
    ]
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"sqlite-data"
    assert (tmp_path / "traces.sqlite.backup-1.2.3.done").exists()

    db._backup_database_file_once()
    current_backups = [
        path
        for path in tmp_path.glob("traces.sqlite.backup-[0-9]*")
        if not path.name.endswith(".done")
    ]
    assert current_backups == backups


def test_packaged_health_requires_matching_build(monkeypatch, tmp_path):
    """Launcher health checks should reject stale or source services on the same port."""
    app = tmp_path / "Fluxion.app"
    monkeypatch.setenv("FLUXION_APP_BUNDLE", str(app))
    monkeypatch.setenv("FLUXION_APP_VERSION", "2.0.0")
    monkeypatch.setenv("FLUXION_BUILD_ID", "build-a")
    paths = launcher.get_service_paths()

    monkeypatch.setattr(
        launcher,
        "_read_health_metadata",
        lambda: {
            "status": "ok",
            "app": "Fluxion",
            "packaged": True,
            "version": "2.0.0",
            "build_id": "build-a",
        },
    )
    assert launcher.health_ok(paths)

    monkeypatch.setattr(
        launcher,
        "_read_health_metadata",
        lambda: {
            "status": "ok",
            "app": "Fluxion",
            "packaged": True,
            "version": "2.0.0",
            "build_id": "old-build",
        },
    )
    assert not launcher.health_ok(paths)

    monkeypatch.setattr(
        launcher,
        "_read_health_metadata",
        lambda: {
            "status": "ok",
            "app": "Fluxion",
            "packaged": False,
            "version": "2.0.0",
            "build_id": "build-a",
        },
    )
    assert not launcher.health_ok(paths)


def test_packaged_wait_for_health_reports_wrong_port_service(monkeypatch, tmp_path):
    """A random service on port 9000 should fail fast with a clear error."""
    app = tmp_path / "Fluxion.app"
    monkeypatch.setenv("FLUXION_APP_BUNDLE", str(app))
    paths = launcher.get_service_paths()
    monkeypatch.setattr(launcher, "_read_health_metadata", lambda: {"status": "ok"})

    try:
        launcher.wait_for_health(timeout_seconds=0.1, paths=paths)
    except RuntimeError as exc:
        assert "already serving something else" in str(exc)
    else:
        raise AssertionError("wait_for_health should reject non-Fluxion health payloads")


def test_packaged_wait_for_health_allows_stale_fluxion_to_exit(monkeypatch, tmp_path):
    """A stale Fluxion service should not fail before the new service can start."""
    app = tmp_path / "Fluxion.app"
    monkeypatch.setenv("FLUXION_APP_BUNDLE", str(app))
    monkeypatch.setenv("FLUXION_APP_VERSION", "2.0.0")
    monkeypatch.setenv("FLUXION_BUILD_ID", "new")
    paths = launcher.get_service_paths()
    payloads = iter(
        [
            {
                "status": "ok",
                "app": "Fluxion",
                "packaged": True,
                "version": "2.0.0",
                "build_id": "old",
            },
            {
                "status": "ok",
                "app": "Fluxion",
                "packaged": True,
                "version": "2.0.0",
                "build_id": "new",
            },
        ]
    )
    monkeypatch.setattr(launcher, "_read_health_metadata", lambda: next(payloads))

    launcher.wait_for_health(timeout_seconds=1.0, paths=paths)
