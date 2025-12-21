"""OpenAI-compatible model client for llama.cpp and similar servers."""

import time
from typing import Any, Optional, TYPE_CHECKING

import httpx

from orchestrator.models.base import Message, ModelResponse

if TYPE_CHECKING:
    from orchestrator.config import ModelConfig


class OpenAICompatClient:
    """Client for OpenAI-compatible API endpoints (llama.cpp, vLLM, etc.)."""

    def __init__(
        self,
        endpoint: str,
        model: str = "default",
        timeout: float = 120.0,
        config: Optional["ModelConfig"] = None,
    ):
        """Initialize the client.

        Args:
            endpoint: Base URL of the API (e.g., http://127.0.0.1:8001)
            model: Model name to use in requests
            timeout: Request timeout in seconds
            config: Model configuration for generation parameters
        """
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._config = config
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def endpoint(self) -> str:
        """Get the model endpoint URL."""
        return self._endpoint

    async def complete(
        self,
        messages: list[Message],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
        stop: Optional[list[str]] = None,
    ) -> ModelResponse:
        """Complete a conversation using the OpenAI-compatible API.

        Args:
            messages: Conversation history
            max_tokens: Maximum tokens to generate (uses config default if None)
            temperature: Sampling temperature (uses config default if None)
            json_mode: Request JSON output
            stop: Stop sequences

        Returns:
            Model response
        """
        # Use config defaults if not specified
        if max_tokens is None:
            max_tokens = self._config.max_tokens if self._config else 4096
        if temperature is None:
            temperature = self._config.temperature if self._config else 0.7

        # Build request payload
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if stop:
            payload["stop"] = stop

        # Add seed for reproducibility if configured
        if self._config and self._config.seed is not None:
            payload["seed"] = self._config.seed

        # Add optional parameters from config
        if self._config:
            if self._config.top_p is not None:
                payload["top_p"] = self._config.top_p
            if self._config.frequency_penalty is not None:
                payload["frequency_penalty"] = self._config.frequency_penalty
            if self._config.presence_penalty is not None:
                payload["presence_penalty"] = self._config.presence_penalty

        # Note: json_mode (response_format) is not supported by all models/servers
        # We rely on the system prompt to request JSON output instead
        # if json_mode:
        #     payload["response_format"] = {"type": "json_object"}

        # Make request
        start_time = time.perf_counter()
        try:
            response = await self._client.post(
                f"{self._endpoint}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ModelError(
                f"HTTP error from {self._endpoint}: {e.response.status_code}",
                endpoint=self._endpoint,
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise ModelError(
                f"Request error to {self._endpoint}: {str(e)}",
                endpoint=self._endpoint,
            ) from e

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Parse response
        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return ModelResponse(
            content=message.get("content", ""),
            raw=data,
            finish_reason=choice.get("finish_reason", "unknown"),
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            latency_ms=latency_ms,
        )

    async def health_check(self) -> bool:
        """Check if the model endpoint is healthy."""
        try:
            response = await self._client.get(
                f"{self._endpoint}/v1/models",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "OpenAICompatClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class ModelError(Exception):
    """Error from model API."""

    def __init__(
        self,
        message: str,
        endpoint: str,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code


class ModelManager:
    """Manages model clients for different roles."""

    def __init__(self) -> None:
        self._clients: dict[str, OpenAICompatClient] = {}

    def get_client(
        self,
        endpoint: str,
        model: str = "default",
        config: Optional["ModelConfig"] = None,
    ) -> OpenAICompatClient:
        """Get or create a client for an endpoint.

        Args:
            endpoint: Base URL of the API
            model: Model name to use
            config: Model configuration for generation parameters

        Returns:
            OpenAI-compatible client instance
        """
        # Create cache key including config hash for different configs
        config_key = ""
        if config:
            config_key = f":{config.temperature}:{config.seed}"
        cache_key = f"{endpoint}{config_key}"

        if cache_key not in self._clients:
            self._clients[cache_key] = OpenAICompatClient(endpoint, model, config=config)
        return self._clients[cache_key]

    async def close_all(self) -> None:
        """Close all clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


# Singleton instance
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """Get the model manager singleton."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
