"""Tests for provider API key helpers."""

from types import SimpleNamespace

import pytest

from orchestrator.services.provider_keys import resolve_parallel_api_key


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
