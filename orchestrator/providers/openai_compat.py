"""OpenAI-compatible LLM provider.

Supports both /v1/responses and /v1/chat/completions endpoints
with automatic fallback and endpoint caching.
"""

import asyncio
import json
import random
import time
from typing import Any, Callable, ClassVar, Dict, List, Optional

import httpx

from orchestrator.logging_config import get_logger, set_component

from .base import LLMResponse, ProviderError, RetryExhaustedError, ToolFallbackError
from .request_builders import build_chat_completions_request, build_responses_request
from .response_parsers import parse_chat_result, parse_responses_result, parse_streaming_delta

logger = get_logger(__name__)


def normalize_base_url(url: str) -> str:
    """Strip trailing /v1 and / to get host-root.

    Args:
        url: The base URL to normalize.

    Returns:
        Normalized URL without trailing /v1 or /.
    """
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def _is_gpt_oss_model(model: str) -> bool:
    """Check if model is gpt-oss (requires /v1/responses for tools).

    Args:
        model: Model name/ID.

    Returns:
        True if this is a gpt-oss model.
    """
    return model.startswith("openai/gpt-oss")


class OpenAICompatProvider:
    """Provider for any OpenAI-compatible API.

    Supports LM Studio, vLLM, Ollama, OpenAI, Azure OpenAI, etc.

    Features:
    - Dual endpoint support (/v1/responses and /v1/chat/completions)
    - Automatic fallback on 404/405
    - Endpoint caching per base_url
    - Exponential backoff with jitter
    - Model-based tool fallback policy
    """

    # Cache: base_url -> supports_responses (bool)
    _endpoint_cache: ClassVar[Dict[str, bool]] = {}

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        endpoint: str = "responses",
        fallback_on_404: bool = True,
        fail_on_tool_fallback: bool = True,
        timeout: float = 120.0,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_statuses: Optional[List[int]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize the provider.

        Args:
            base_url: Base URL of the API (will be normalized).
            api_key: API key for authentication (optional for local servers).
            endpoint: Endpoint preference ("responses", "chat_completions", "auto").
            fallback_on_404: If True, fall back to chat_completions on 404/405.
            fail_on_tool_fallback: If True (default), raise ToolFallbackError when
                tools are requested but /v1/responses is unavailable. gpt-oss models
                ALWAYS require /v1/responses for tools regardless of this setting.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            base_delay: Initial delay for exponential backoff.
            max_delay: Maximum delay cap for backoff.
            retryable_statuses: HTTP status codes to retry on.
            extra_headers: Additional headers to include in requests.
        """
        self._base_url = normalize_base_url(base_url)
        self._api_key = api_key
        self._endpoint = endpoint
        self._fallback_on_404 = fallback_on_404
        self._fail_on_tool_fallback = fail_on_tool_fallback
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retryable_statuses = retryable_statuses or [429, 500, 502, 503, 504]

        # Build headers
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
        )

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an endpoint.

        Handles base URLs that already contain /v1/openai (e.g., DeepInfra).
        For such URLs, we append /chat/completions instead of /v1/chat/completions.

        Args:
            endpoint: Endpoint path (e.g., "chat/completions", "responses", "models")

        Returns:
            Full URL for the endpoint.
        """
        base = self._base_url.rstrip("/")

        # If base_url ends with /v1/openai or /openai, don't add /v1 prefix
        if base.endswith("/v1/openai") or base.endswith("/openai"):
            return f"{base}/{endpoint}"
        else:
            return f"{base}/v1/{endpoint}"

    async def close(self) -> None:
        """Clean up provider resources."""
        await self._client.aclose()

    async def health_check(self) -> bool:
        """Check if the provider is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = await self._client.get(
                self._build_url("models"),
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = False,
        previous_response_id: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete a conversation.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            instructions: System prompt.
            tools: Tool definitions.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            reasoning_effort: Native reasoning effort.
            stream: Whether to stream (False for this method).
            previous_response_id: Response ID from previous call for stateful mode.
            **kwargs: Additional parameters.

        Returns:
            Normalized LLMResponse.
        """
        endpoint_type = await self._resolve_endpoint()

        # Build request
        if endpoint_type == "responses":
            payload = build_responses_request(
                messages=messages,
                model=model,
                instructions=instructions,
                tools=tools,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_tokens,
                stream=False,
                previous_response_id=previous_response_id,
            )
            url = self._build_url("responses")
        else:
            payload = build_chat_completions_request(
                messages=messages,
                model=model,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
                **kwargs,
            )
            url = self._build_url("chat/completions")

        # Make request with retry
        response = await self._request_with_retry(url, payload)

        # Handle fallback
        if response.status_code in (404, 405) and self._fallback_on_404:
            if endpoint_type == "responses":
                response, url = await self._handle_fallback(
                    messages, model, tools, max_tokens, temperature, stream=False, **kwargs
                )

        response.raise_for_status()

        # Parse response
        raw = response.json()
        if "/responses" in url:
            return parse_responses_result(raw, url)
        else:
            return parse_chat_result(raw, url)

    async def complete_streaming(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        on_token: Callable[[str], None],
        on_reasoning: Optional[Callable[[str], None]] = None,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        previous_response_id: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Stream a completion with retry on network errors.

        Retries on transient network errors (RemoteProtocolError, ReadError)
        with exponential backoff. HTTP errors are handled separately.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            on_token: Callback for content tokens.
            on_reasoning: Callback for reasoning tokens.
            instructions: System prompt.
            tools: Tool definitions.
            tool_choice: Tool selection behavior (auto, required, or tool_name).
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            reasoning_effort: Native reasoning effort.
            previous_response_id: Response ID from previous call for stateful mode.
            **kwargs: Additional parameters.

        Returns:
            Final LLMResponse after streaming.

        Raises:
            RetryExhaustedError: If streaming fails after all retry attempts.
        """
        endpoint_type = await self._resolve_endpoint()

        # Note: responses API doesn't support tool_choice parameter
        # We pass it to build_responses_request but it will be ignored there
        # The system prompt handles tool guidance instead

        # Build request (done once, outside retry loop)
        if endpoint_type == "responses":
            payload = build_responses_request(
                messages=messages,
                model=model,
                instructions=instructions,
                tools=tools,
                tool_choice=tool_choice,
                reasoning_effort=reasoning_effort,
                max_output_tokens=max_tokens,
                stream=True,
                previous_response_id=previous_response_id,
            )
            url = self._build_url("responses")
        else:
            payload = build_chat_completions_request(
                messages=messages,
                model=model,
                tools=tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                **kwargs,
            )
            url = self._build_url("chat/completions")

        # Retry loop for network errors (RemoteProtocolError, ReadError)
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._do_streaming(
                    url=url,
                    payload=payload,
                    endpoint_type=endpoint_type,
                    on_token=on_token,
                    on_reasoning=on_reasoning,
                    messages=messages,
                    model=model,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
            except (httpx.RemoteProtocolError, httpx.ReadError) as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = min(self._base_delay * (2 ** attempt), self._max_delay)
                    jitter = delay * random.uniform(0.1, 0.3)
                    total_delay = delay + jitter
                    logger.warning(
                        "Streaming failed due to network error, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self._max_retries,
                            "delay_seconds": round(total_delay, 2),
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(total_delay)
                else:
                    logger.error(
                        "Streaming failed after all retries",
                        extra={
                            "attempts": attempt + 1,
                            "error": str(e),
                        },
                    )

        raise RetryExhaustedError(
            f"Streaming failed after {self._max_retries} retries: {last_error}"
        )

    async def _do_streaming(
        self,
        url: str,
        payload: Dict[str, Any],
        endpoint_type: str,
        on_token: Callable[[str], None],
        on_reasoning: Optional[Callable[[str], None]],
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute the actual streaming request.

        This method contains the streaming logic extracted from complete_streaming
        to enable retry wrapping in the parent method.

        Args:
            url: Request URL.
            payload: Request payload.
            endpoint_type: "responses" or "chat_completions".
            on_token: Callback for content tokens.
            on_reasoning: Callback for reasoning tokens.
            messages: Original messages (for fallback).
            model: Model name (for fallback).
            tools: Tool definitions (for fallback).
            max_tokens: Maximum tokens (for fallback).
            temperature: Sampling temperature (for fallback).
            **kwargs: Additional parameters (for fallback).

        Returns:
            LLMResponse after streaming completes.

        Raises:
            httpx.RemoteProtocolError: On network-level streaming errors.
            httpx.ReadError: On read errors during streaming.
            httpx.HTTPStatusError: On HTTP errors (except 404/405 with fallback).
        """
        full_content: List[str] = []
        full_reasoning: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        finish_reason = "stop"
        usage: Dict[str, int] = {}
        response_id: Optional[str] = None

        try:
            async with self._client.stream("POST", url, json=payload) as response:
                # Check for fallback needed
                if response.status_code in (404, 405) and self._fallback_on_404:
                    if endpoint_type == "responses":
                        # Need to close this stream and retry with fallback
                        pass
                    else:
                        response.raise_for_status()
                elif response.status_code >= 400:
                    response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Capture response_id from streaming events (responses API)
                    if "/responses" in url and response_id is None:
                        if "id" in data:
                            response_id = data["id"]
                        elif data.get("type") == "response.created":
                            response_id = data.get("response", {}).get("id")
                        elif data.get("type") == "response.completed":
                            response_id = data.get("response", {}).get("id")

                    # Parse based on endpoint type
                    if "/responses" in url:
                        delta = parse_streaming_delta(data, "responses")
                    else:
                        choices = data.get("choices", [{}])
                        if choices:
                            choice_delta = choices[0].get("delta", {})
                            delta = parse_streaming_delta(choice_delta, "chat_completions")
                            finish_reason = choices[0].get("finish_reason") or finish_reason
                        else:
                            delta = {"content": None, "reasoning": None, "tool_call": None}

                    # Emit callbacks
                    if delta["content"]:
                        full_content.append(delta["content"])
                        on_token(delta["content"])

                    if delta["reasoning"] and on_reasoning:
                        full_reasoning.append(delta["reasoning"])
                        on_reasoning(delta["reasoning"])

                    # Collect completed tool calls (LM Studio or DeepInfra format)
                    if delta.get("tool_call_complete"):
                        tool_calls.append(delta["tool_call_complete"])
                        logger.debug(
                            "Streaming tool call complete",
                            extra={"tool_name": delta["tool_call_complete"]["function"]["name"]}
                        )
                    # Handle multiple complete tool calls (e.g., DeepInfra)
                    if delta.get("tool_calls_complete"):
                        for tc in delta["tool_calls_complete"]:
                            tool_calls.append(tc)
                            logger.debug(
                                "Streaming tool call complete (batch)",
                                extra={"tool_name": tc["function"]["name"]}
                            )

                    # Track usage if present
                    if "usage" in data:
                        usage = data["usage"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 405) and self._fallback_on_404 and endpoint_type == "responses":
                # Fallback to chat_completions
                return await self._streaming_fallback(
                    messages, model, on_token, on_reasoning,
                    tools, max_tokens, temperature, **kwargs
                )
            raise

        return LLMResponse(
            text="".join(full_content),
            tool_calls=tool_calls if tool_calls else None,
            reasoning="".join(full_reasoning) if full_reasoning else None,
            response_id=response_id,
            raw={},
            endpoint_used=url,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def _resolve_endpoint(self) -> str:
        """Resolve which endpoint to use.

        Returns:
            "responses" or "chat_completions".
        """
        if self._endpoint == "auto":
            return await self._detect_endpoint_support()
        return self._endpoint

    async def _detect_endpoint_support(self) -> str:
        """Probe /v1/responses to check support, cache result.

        Endpoint detection logic:
        - 404/405: unsupported (route doesn't exist)
        - 400/401/403: supported (route exists, request/auth wrong)
        - Network failure: unsupported (can't reach)
        - Any other status: supported

        Returns:
            "responses" or "chat_completions".
        """
        if self._base_url in self._endpoint_cache:
            return "responses" if self._endpoint_cache[self._base_url] else "chat_completions"

        # Probe with minimal request
        try:
            response = await self._client.post(
                self._build_url("responses"),
                json={"model": "probe", "input": []},
                timeout=5.0,
            )
            # Only 404/405 means unsupported; 400/401/403 means route exists
            supports = response.status_code not in (404, 405)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
            # Network failure = can't determine, assume unsupported
            supports = False

        self._endpoint_cache[self._base_url] = supports
        logger.info(
            "Endpoint detection complete",
            extra={"base_url": self._base_url, "supports_responses": supports}
        )
        return "responses" if supports else "chat_completions"

    async def _handle_fallback(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        stream: bool = False,
        **kwargs: Any,
    ) -> tuple[httpx.Response, str]:
        """Handle fallback from /v1/responses to /v1/chat/completions.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            tools: Tool definitions.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            stream: Whether to stream.
            **kwargs: Additional parameters.

        Returns:
            Tuple of (response, url).

        Raises:
            ToolFallbackError: If gpt-oss model with tools can't use responses.
        """
        # Tool fallback policy
        if tools:
            if _is_gpt_oss_model(model):
                # gpt-oss REQUIRES /v1/responses for tool use - ALWAYS hard fail
                raise ToolFallbackError(
                    f"Model {model} requires /v1/responses for tool use. "
                    f"Server does not support /v1/responses."
                )
            # Non-gpt-oss models: check fail_on_tool_fallback config
            if self._fail_on_tool_fallback:
                raise ToolFallbackError(
                    "Tools require /v1/responses endpoint but server does not support it. "
                    "Set fail_on_tool_fallback=False to allow fallback to chat_completions."
                )

        # Fall back to chat/completions
        payload = build_chat_completions_request(
            messages=messages,
            model=model,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=stream,
            **kwargs,
        )
        url = self._build_url("chat/completions")
        response = await self._request_with_retry(url, payload)

        # Cache that this base_url doesn't support responses
        self._endpoint_cache[self._base_url] = False

        return response, url

    async def _streaming_fallback(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        on_token: Callable[[str], None],
        on_reasoning: Optional[Callable[[str], None]],
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: Optional[int],
        temperature: Optional[float],
        **kwargs: Any,
    ) -> LLMResponse:
        """Fallback to chat_completions for streaming.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            on_token: Token callback.
            on_reasoning: Reasoning callback.
            tools: Tool definitions.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.
            **kwargs: Additional parameters.

        Returns:
            Final LLMResponse.
        """
        # Check tool fallback policy
        if tools:
            if _is_gpt_oss_model(model):
                # gpt-oss REQUIRES /v1/responses for tool use - ALWAYS hard fail
                raise ToolFallbackError(
                    f"Model {model} requires /v1/responses for tool use. "
                    f"Server does not support /v1/responses."
                )
            # Non-gpt-oss models: check fail_on_tool_fallback config
            if self._fail_on_tool_fallback:
                raise ToolFallbackError(
                    "Tools require /v1/responses endpoint but server does not support it. "
                    "Set fail_on_tool_fallback=False to allow fallback to chat_completions."
                )

        payload = build_chat_completions_request(
            messages=messages,
            model=model,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            **kwargs,
        )
        url = self._build_url("chat/completions")

        # Cache that this base_url doesn't support responses
        self._endpoint_cache[self._base_url] = False

        full_content: List[str] = []
        full_reasoning: List[str] = []
        finish_reason = "stop"
        usage: Dict[str, int] = {}

        async with self._client.stream("POST", url, json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = data.get("choices", [{}])
                if choices:
                    choice_delta = choices[0].get("delta", {})
                    delta = parse_streaming_delta(choice_delta, "chat_completions")
                    finish_reason = choices[0].get("finish_reason") or finish_reason

                    if delta["content"]:
                        full_content.append(delta["content"])
                        on_token(delta["content"])

                    if delta["reasoning"] and on_reasoning:
                        full_reasoning.append(delta["reasoning"])
                        on_reasoning(delta["reasoning"])

                if "usage" in data:
                    usage = data["usage"]

        return LLMResponse(
            text="".join(full_content),
            tool_calls=None,
            reasoning="".join(full_reasoning) if full_reasoning else None,
            raw={},
            endpoint_used=url,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def _request_with_retry(self, url: str, payload: Dict[str, Any]) -> httpx.Response:
        """Make request with exponential backoff + jitter.

        Retries on:
        - HTTP status codes in retryable_statuses (429, 500, 502, 503, 504)
        - Timeout exceptions
        - Connection errors
        - Read errors

        Args:
            url: Request URL.
            payload: Request payload.

        Returns:
            HTTP response.

        Raises:
            RetryExhaustedError: If all retries are exhausted.
        """
        last_error: Optional[str] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.post(url, json=payload)

                # Success or non-retryable error (including 404/405 for fallback handling)
                if response.status_code not in self._retryable_statuses:
                    return response

                last_error = f"HTTP {response.status_code}"
                logger.warning(
                    "Retryable HTTP status",
                    extra={"status_code": response.status_code, "attempt": attempt, "max_retries": self._max_retries}
                )

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                logger.warning(
                    "Request timeout",
                    extra={"attempt": attempt, "error": str(e)}
                )
            except httpx.ConnectError as e:
                last_error = f"Connect error: {e}"
                logger.warning(
                    "Connection error",
                    extra={"attempt": attempt, "error": str(e)}
                )
            except httpx.ReadError as e:
                last_error = f"Read error: {e}"
                logger.warning(
                    "Read error",
                    extra={"attempt": attempt, "error": str(e)}
                )

            # Calculate delay with exponential backoff + jitter
            if attempt < self._max_retries:
                delay = min(
                    self._base_delay * (2 ** (attempt - 1)),
                    self._max_delay,
                )
                jitter = delay * random.uniform(0.1, 0.3)
                total_delay = delay + jitter
                logger.info(
                    "Retrying request",
                    extra={
                        "delay_seconds": round(total_delay, 2),
                        "attempt": attempt,
                        "max_retries": self._max_retries,
                    }
                )
                await asyncio.sleep(total_delay)

        raise RetryExhaustedError(
            f"Max retries ({self._max_retries}) exceeded. Last error: {last_error}"
        )
