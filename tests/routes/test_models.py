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


@pytest.fixture(autouse=True)
def reset_active_model():
    """Reset active model state between tests."""
    models_module._active_model = None
    models_module._active_model_name = None
    yield
    models_module._active_model = None
    models_module._active_model_name = None


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
    assert data["supports_reasoning"] is True


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
