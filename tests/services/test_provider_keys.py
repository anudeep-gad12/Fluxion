"""Tests for provider API key helpers."""

from types import SimpleNamespace

import pytest

from orchestrator.services.provider_keys import resolve_parallel_api_key
from orchestrator.services import grok_auth
from orchestrator.services.grok_auth import (
    get_grok_cli_version_sync,
    get_grok_access_token_sync,
    get_grok_auth_status,
    submit_grok_login_code,
)


class TestResolveParallelApiKey:
    def test_returns_config_key_when_set(self):
        config = SimpleNamespace(
            parallel=SimpleNamespace(api_key="config-key", base_url="https://api.parallel.ai/v1beta")
        )
        assert resolve_parallel_api_key(config) == "config-key"

    def test_falls_back_to_environment_when_config_empty(self, monkeypatch):
        monkeypatch.setenv("PARALLEL_API_KEY", "env-key")
        config = SimpleNamespace(parallel=SimpleNamespace(api_key=None, base_url="https://api.parallel.ai/v1beta"))
        assert resolve_parallel_api_key(config) == "env-key"

    def test_returns_none_when_missing_everywhere(self, monkeypatch):
        monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
        config = SimpleNamespace(parallel=SimpleNamespace(api_key=None, base_url="https://api.parallel.ai/v1beta"))
        assert resolve_parallel_api_key(config) is None

    def test_returns_none_without_parallel_config(self):
        assert resolve_parallel_api_key(SimpleNamespace()) is None


class TestGrokAuth:
    def test_returns_valid_grok_token_from_auth_json(self, tmp_path, monkeypatch):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            """
            {
              "https://auth.x.ai::client": {
                "key": "grok-token",
                "auth_mode": "oidc",
                "expires_at": "2999-01-01T00:00:00Z",
                "oidc_issuer": "https://auth.x.ai"
              }
            }
            """
        )
        monkeypatch.setenv("GROK_AUTH_FILE", str(auth_file))

        assert get_grok_access_token_sync() == "grok-token"

    def test_ignores_expired_grok_token(self, tmp_path, monkeypatch):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            """
            {
              "https://auth.x.ai::client": {
                "key": "expired-token",
                "auth_mode": "oidc",
                "expires_at": "2000-01-01T00:00:00Z",
                "oidc_issuer": "https://auth.x.ai"
              }
            }
            """
        )
        monkeypatch.setenv("GROK_AUTH_FILE", str(auth_file))

        assert get_grok_access_token_sync() is None

    @pytest.mark.asyncio
    async def test_status_exposes_metadata_without_token(self, tmp_path, monkeypatch):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            """
            {
              "https://auth.x.ai::client": {
                "key": "secret-token",
                "auth_mode": "oidc",
                "email": "user@example.com",
                "expires_at": "2999-01-01T00:00:00Z",
                "oidc_issuer": "https://auth.x.ai"
              }
            }
            """
        )
        monkeypatch.setenv("GROK_AUTH_FILE", str(auth_file))

        status = await get_grok_auth_status()
        assert status["authenticated"] is True
        assert status["account_id"] == "user@example.com"
        assert "secret-token" not in str(status)

    @pytest.mark.asyncio
    async def test_submit_grok_login_code_writes_to_active_process_stdin(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GROK_AUTH_FILE", str(tmp_path / "missing-auth.json"))

        class FakeStdin:
            def __init__(self):
                self.writes: list[bytes] = []

            def write(self, data: bytes) -> None:
                self.writes.append(data)

            async def drain(self) -> None:
                return None

        class FakeProcess:
            returncode = None

            def __init__(self):
                self.stdin = FakeStdin()

            async def wait(self):
                self.returncode = 0
                return 0

        process = FakeProcess()
        original_process = grok_auth._login_process  # noqa: SLF001
        original_message = grok_auth._last_login_message  # noqa: SLF001
        try:
            grok_auth._login_process = process  # noqa: SLF001
            result = await submit_grok_login_code("  manual-code  ")
            assert result["status"] == "submitted"
            assert process.stdin.writes == [b"manual-code\n"]
            assert "manual-code" not in str(result)
        finally:
            grok_auth._login_process = original_process  # noqa: SLF001
            grok_auth._last_login_message = original_message  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_submit_grok_login_code_without_active_process(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GROK_AUTH_FILE", str(tmp_path / "missing-auth.json"))

        original_process = grok_auth._login_process  # noqa: SLF001
        try:
            grok_auth._login_process = None  # noqa: SLF001
            result = await submit_grok_login_code("manual-code")
            assert result["status"] == "no_login"
            assert "manual-code" not in str(result)
        finally:
            grok_auth._login_process = original_process  # noqa: SLF001

    def test_grok_cli_version_has_safe_fallback(self, monkeypatch):
        monkeypatch.setattr(grok_auth.shutil, "which", lambda _name: None)
        monkeypatch.setattr(grok_auth, "_cli_version_cache", None)

        assert get_grok_cli_version_sync()
