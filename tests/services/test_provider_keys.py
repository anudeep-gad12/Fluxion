"""Tests for provider API key helpers."""

from types import SimpleNamespace

import pytest

from orchestrator.services.provider_keys import resolve_parallel_api_key
from orchestrator.services.grok_auth import get_grok_access_token_sync, get_grok_auth_status


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
