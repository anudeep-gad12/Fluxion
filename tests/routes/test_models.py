"""Tests for model management routes.

Integration tests for GET /api/models and POST /api/models/select.
Uses mock provider creation to avoid real API calls.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.app import app
import orchestrator.routes.models as models_module
from orchestrator.storage.db import get_db


@pytest.fixture(autouse=True)
def reset_active_model():
    """Reset active model state between tests."""
    models_module._active_model = None
    models_module._active_model_name = None
    yield
    models_module._active_model = None
    models_module._active_model_name = None


@pytest.fixture(autouse=True)
async def reset_provider_keys():
    for env_name in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY"):
        os.environ.pop(env_name, None)
    db = await get_db()
    await db.conn.execute("DELETE FROM app_settings WHERE setting_key = 'provider_api_keys'")
    await db.conn.commit()
    yield
    for env_name in ("OPENROUTER_API_KEY", "DEEPINFRA_API_KEY", "FIREWORKS_API_KEY"):
        os.environ.pop(env_name, None)
    await db.conn.execute("DELETE FROM app_settings WHERE setting_key = 'provider_api_keys'")
    await db.conn.commit()


@pytest.mark.asyncio
async def test_list_models_returns_grouped_presets():
    """GET /api/models returns presets grouped by provider."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/models")

    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "openrouter" in data["providers"]
    assert "deepinfra" in data["providers"]
    assert "fireworks" in data["providers"]
    assert "local" in data["providers"]
    assert "active_model" in data
    assert "active_model_id" in data


@pytest.mark.asyncio
async def test_list_models_provider_structure():
    """Each provider in GET /api/models has models, available, and api_key_env."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/models")

    data = response.json()
    for provider_name, info in data["providers"].items():
        assert "models" in info
        assert "available" in info
        assert "api_key_env" in info


@pytest.mark.asyncio
@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-or-key"})
async def test_select_model_creates_provider_override():
    """POST /api/models/select sets the provider override."""
    mock_provider = MagicMock()

    with patch(
        "orchestrator.routes.models.create_provider_for_model"
    ) as mock_create:
        from orchestrator.models.registry import ResolvedModel

        resolved = ResolvedModel(
            model_id="qwen/qwen3-72b",
            display_name="Qwen 3 72B",
            provider_name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
            endpoint="chat_completions",
            context_window=131072,
            max_output_tokens=16384,
            temperature=0.7,
            reasoning_effort="medium",
            supports_tools=True,
        )
        mock_create.return_value = (mock_provider, resolved)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/models/select", json={"model": "qwen3-72b"}
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_id"] == "qwen/qwen3-72b"
    assert data["display_name"] == "Qwen 3 72B"
    assert data["provider"] == "openrouter"
    assert data["context_window"] == 131072
    assert data["max_output_tokens"] == 16384
    assert data["effective_input_budget"] == 114688
    assert data["source"] == "registry"


@pytest.mark.asyncio
@patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
async def test_select_model_returns_metadata():
    """Response includes model_id, provider, context_window."""
    mock_provider = MagicMock()

    with patch(
        "orchestrator.routes.models.create_provider_for_model"
    ) as mock_create:
        from orchestrator.models.registry import ResolvedModel

        resolved = ResolvedModel(
            model_id="deepseek/deepseek-r1",
            display_name="DeepSeek R1",
            provider_name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
            endpoint="chat_completions",
            context_window=163840,
            max_output_tokens=16384,
            temperature=0.7,
            reasoning_effort="high",
            supports_tools=True,
        )
        mock_create.return_value = (mock_provider, resolved)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/models/select", json={"model": "deepseek-r1"}
            )

    data = response.json()
    assert data["model_id"] == "deepseek/deepseek-r1"
    assert data["provider"] == "openrouter"
    assert data["context_window"] == 163840
    assert data["max_output_tokens"] == 16384
    assert data["effective_input_budget"] == 147456
    assert data["supports_reasoning"] is True
    assert data["source"] == "registry"


@pytest.mark.asyncio
async def test_select_invalid_model_no_key_returns_error():
    """Selecting a model without API key returns 400 with helpful message."""
    with patch(
        "orchestrator.routes.models.create_provider_for_model",
        side_effect=ValueError("No API key found for deepinfra. Set DEEPINFRA_API_KEY environment variable."),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/models/select", json={"model": "deepinfra:some-model"}
            )

    assert response.status_code == 400
    assert "API key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_select_model_updates_active_state():
    """After selecting, GET /api/models shows the active model."""
    mock_provider = MagicMock()

    with patch(
        "orchestrator.routes.models.create_provider_for_model"
    ) as mock_create:
        from orchestrator.models.registry import ResolvedModel

        resolved = ResolvedModel(
            model_id="qwen/qwen3-72b",
            display_name="Qwen 3 72B",
            provider_name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
            endpoint="chat_completions",
            context_window=131072,
            max_output_tokens=16384,
            temperature=0.7,
            reasoning_effort=None,
            supports_tools=True,
        )
        mock_create.return_value = (mock_provider, resolved)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/api/models/select", json={"model": "qwen3-72b"})
            response = await client.get("/api/models")

    data = response.json()
    assert data["active_model"] == "qwen3-72b"
    assert data["active_model_id"] == "qwen/qwen3-72b"


@pytest.mark.asyncio
async def test_start_local_model_sets_provider_default_model():
    """Local model start should pin the provider default model to the loaded local model."""
    with patch("orchestrator.routes.models.local_models.start", return_value=True), patch(
        "orchestrator.routes.models.local_models.status",
        return_value={
            "model_name": "Qwen3.6-35B-A3B-Q4_K_M",
            "model_path": "/models/qwen.gguf",
            "model_type": "gguf",
        },
    ), patch("orchestrator.routes.models.set_provider_override") as mock_set_provider:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/models/local/start", json={"model_path": "/models/qwen.gguf", "ctx_size": 65536}
            )

    assert response.status_code == 200
    provider = mock_set_provider.call_args.args[0]
    assert provider._default_model == "Qwen3.6-35B-A3B-Q4_K_M"
    assert provider._context_profile_model_id == "Qwen3.6-35B-A3B-Q4_K_M"
    assert provider._context_profile_display_name == "Qwen3.6-35B-A3B-Q4_K_M"


@pytest.mark.asyncio
async def test_model_status_includes_context_profile_fields():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/models/status")

    assert response.status_code == 200
    data = response.json()
    assert data["context_window"] > 0
    assert data["max_output_tokens"] > 0
    assert data["effective_input_budget"] == data["context_window"] - data["max_output_tokens"]
    assert "provider_family" in data
    assert "reasoning_capabilities" in data
    assert "source" in data


@pytest.mark.asyncio
async def test_get_reasoning_settings_returns_capabilities():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/models/reasoning-settings")

    assert response.status_code == 200
    data = response.json()
    assert "settings" in data
    assert "capabilities" in data
    assert "provider_family" in data
    assert "max_output_tokens" in data["settings"]
    assert "reasoning_effort" in data["capabilities"]


@pytest.mark.asyncio
async def test_put_reasoning_settings_persists_round_trip():
    payload = {
        "settings": {
            "max_output_tokens": 2048,
            "reasoning_effort": "low",
            "reasoning_summary": None,
            "reasoning_enabled": True,
            "reasoning_max_tokens": 512,
            "reasoning_exclude": False,
            "fireworks_reasoning_mode": "effort",
            "fireworks_thinking_type": "enabled",
            "fireworks_thinking_budget_tokens": None,
            "fireworks_reasoning_history": None,
        }
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put("/api/models/reasoning-settings", json=payload)
        assert response.status_code == 200
        second = await client.get("/api/models/reasoning-settings")

    data = second.json()
    assert data["settings"]["max_output_tokens"] == 2048
    assert data["settings"]["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_provider_keys_round_trip_masks_secret():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        save_response = await client.put(
            "/api/models/provider-keys/openrouter",
            json={"api_key": "sk-test-openrouter"},
        )
        list_response = await client.get("/api/models/provider-keys")

    assert save_response.status_code == 200
    save_data = save_response.json()
    assert save_data["provider"] == "openrouter"
    assert save_data["has_key"] is True
    assert save_data["source"] == "database"
    assert "api_key" not in save_data

    listed = {item["provider"]: item for item in list_response.json()["providers"]}
    assert listed["openrouter"]["has_key"] is True
    assert listed["openrouter"]["source"] == "database"
    assert "api_key" not in listed["openrouter"]


@pytest.mark.asyncio
async def test_list_models_availability_uses_persisted_provider_keys():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        before = await client.get("/api/models")
        await client.put(
            "/api/models/provider-keys/fireworks",
            json={"api_key": "fw-test-key"},
        )
        after = await client.get("/api/models")

    assert before.status_code == 200
    assert after.status_code == 200
    assert before.json()["providers"]["fireworks"]["available"] is False
    assert after.json()["providers"]["fireworks"]["available"] is True


@pytest.mark.asyncio
async def test_delete_provider_key_falls_back_to_environment():
    os.environ["DEEPINFRA_API_KEY"] = "env-deepinfra-key"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.put(
            "/api/models/provider-keys/deepinfra",
            json={"api_key": "db-deepinfra-key"},
        )
        response = await client.delete("/api/models/provider-keys/deepinfra")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "deepinfra"
    assert data["has_key"] is True
    assert data["source"] == "environment"
