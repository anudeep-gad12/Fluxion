"""OpenAI-compatible LLM provider.

Supports both /v1/responses and /v1/chat/completions endpoints
with automatic fallback and endpoint caching.
"""

import asyncio
import json
import random
from typing import Any, Callable, ClassVar, Dict, List, Optional

import httpx

from orchestrator.logging_config import get_logger

from .base import LLMResponse, RetryExhaustedError, ToolFallbackError
from .request_builders import build_chat_completions_request, build_responses_request
from .response_parsers import parse_chat_result, parse_responses_result, parse_streaming_delta

logger = get_logger(__name__)


def _format_exception(error: BaseException) -> str:
    """Return a non-empty exception string with type information."""
    error_type = f"{error.__class__.__module__}.{error.__class__.__name__}"
    message = str(error).strip()
    if message:
        return f"{error_type}: {message}"
    return f"{error_type}: {repr(error)}"


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
        default_model: Optional[str] = None,
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
        self._default_model = default_model
        self._shared = False  # If True, close() is a no-op (shared provider override)
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

        Handles base URLs that already contain /v1 (e.g., llama-server, DeepInfra).
        For such URLs, we append /chat/completions directly without adding /v1.

        Args:
            endpoint: Endpoint path (e.g., "chat/completions", "responses", "models")

        Returns:
            Full URL for the endpoint.
        """
        base = self._base_url.rstrip("/")

        # If base_url already ends with /v1, /v1/openai, or /openai, don't add /v1 prefix
        if base.endswith("/v1") or base.endswith("/v1/openai") or base.endswith("/openai"):
            return f"{base}/{endpoint}"
        else:
            return f"{base}/v1/{endpoint}"

    async def close(self) -> None:
        """Clean up provider resources."""
        if self._shared:
            return  # Shared providers are managed externally
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
                reasoning=kwargs.get("reasoning"),
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
                reasoning_effort=reasoning_effort,
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
                    messages,
                    model,
                    tools,
                    max_tokens,
                    temperature,
                    reasoning_effort=reasoning_effort,
                    stream=False,
                    **kwargs,
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
        # Override model name if provider has a default (e.g. local MLX server)
        if self._default_model:
            model = self._default_model

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
                reasoning=kwargs.get("reasoning"),
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
                reasoning_effort=reasoning_effort,
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
                    reasoning_effort=reasoning_effort,
                    **kwargs,
                )
            except (
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.NetworkError,
            ) as e:
                # Only retry HTTP errors with retryable status codes
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code not in self._retryable_statuses:
                    raise
                last_error = e
                error_message = _format_exception(e)
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
                            "error": error_message,
                            "error_type": f"{e.__class__.__module__}.{e.__class__.__name__}",
                            "error_repr": repr(e),
                        },
                    )
                    await asyncio.sleep(total_delay)
                else:
                    logger.error(
                        "Streaming failed after all retries",
                        extra={
                            "attempts": attempt + 1,
                            "error": error_message,
                            "error_type": f"{e.__class__.__module__}.{e.__class__.__name__}",
                            "error_repr": repr(e),
                        },
                    )

        raise RetryExhaustedError(
            f"Streaming failed after {self._max_retries} retries: "
            f"{_format_exception(last_error) if last_error else 'unknown error'}"
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
        reasoning_effort: Optional[str],
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
        # Accumulator for streaming tool calls (index -> {id, name, arguments_parts})
        tool_call_accumulators: Dict[int, Dict[str, Any]] = {}
        finish_reason = "stop"
        usage: Dict[str, int] = {}
        response_id: Optional[str] = None

        def _has_valid_tool_arguments(arguments: Any) -> bool:
            """Return whether tool-call arguments are non-empty valid JSON objects."""
            if isinstance(arguments, dict):
                return bool(arguments)
            if not isinstance(arguments, str):
                return False
            stripped = arguments.strip()
            if not stripped or stripped == "{}":
                return False
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return False
            return isinstance(parsed, dict) and bool(parsed)

        # Debug: Log the request payload
        import json as json_module
        payload_json = json_module.dumps(payload)
        logger.info(
            "Streaming request payload",
            extra={
                "url": url,
                "payload_len": len(payload_json),
                "payload_preview": payload_json[:8000],
            },
        )

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
                    error_body = await response.aread()
                    error_text = error_body.decode(errors="replace")
                    if (
                        response.status_code in (400, 422)
                        and "stream_options" in payload
                        and "stream_options" in error_text
                    ):
                        logger.warning(
                            "Provider rejected stream_options; retrying stream without usage hint",
                            extra={"status": response.status_code, "url": url},
                        )
                        retry_payload = dict(payload)
                        retry_payload.pop("stream_options", None)
                        return await self._do_streaming(
                            url=url,
                            payload=retry_payload,
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
                    logger.error(
                        "API error response",
                        extra={"status": response.status_code, "body": error_text[:2000]},
                    )
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

                            # Log first delta with each field type for diagnostics
                            delta_keys = [k for k in choice_delta if choice_delta[k] is not None]
                            if delta_keys and not any(k in ("role",) for k in delta_keys):
                                interesting = {k: str(choice_delta[k])[:100] for k in delta_keys}
                                logger.debug(
                                    "Streaming delta fields",
                                    extra={"keys": delta_keys, "preview": interesting},
                                )

                            delta = parse_streaming_delta(choice_delta, "chat_completions")
                            new_finish = choices[0].get("finish_reason")
                            if new_finish:
                                finish_reason = new_finish

                            # Accumulate streaming tool calls (llama-server format)
                            # Use `or []` to handle None values (key exists with null)
                            streaming_tool_calls = choice_delta.get("tool_calls") or []
                            for tc in streaming_tool_calls:
                                idx = tc.get("index", 0)
                                if idx not in tool_call_accumulators:
                                    tool_call_accumulators[idx] = {
                                        "id": None,
                                        "name": None,
                                        "arguments_parts": [],
                                    }
                                acc = tool_call_accumulators[idx]
                                # Capture id and name from first chunk
                                if tc.get("id"):
                                    acc["id"] = tc["id"]
                                func = tc.get("function", {})
                                if func.get("name"):
                                    acc["name"] = func["name"]
                                if func.get("arguments"):
                                    acc["arguments_parts"].append(func["arguments"])
                        else:
                            delta = {"content": None, "reasoning": None, "tool_call": None}

                    # Emit callbacks
                    if delta["content"] and delta["reasoning"]:
                        logger.debug(
                            "Chunk has both content and reasoning",
                            extra={
                                "content_preview": str(delta["content"])[:100],
                                "reasoning_preview": str(delta["reasoning"])[:100],
                            },
                        )
                    if delta["content"]:
                        # Ensure content is a string (Mistral can return list of content blocks)
                        raw_content = delta["content"]
                        if isinstance(raw_content, str):
                            content_str = raw_content
                        elif isinstance(raw_content, list):
                            # Extract text from content blocks like [{"type": "text", "text": "..."}]
                            parts = []
                            for block in raw_content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    parts.append(block.get("text", ""))
                                elif isinstance(block, str):
                                    parts.append(block)
                            content_str = "".join(parts)
                        else:
                            content_str = str(raw_content)
                        if content_str:
                            full_content.append(content_str)
                            on_token(content_str)

                    if delta["reasoning"] and on_reasoning:
                        full_reasoning.append(delta["reasoning"])
                        on_reasoning(delta["reasoning"])

                    # Collect completed tool calls (LM Studio or DeepInfra format)
                    # Skip tool calls with empty arguments - they'll just fail
                    if delta.get("tool_call_complete"):
                        tc = delta["tool_call_complete"]
                        args = tc.get("function", {}).get("arguments", "")
                        if _has_valid_tool_arguments(args):
                            tool_calls.append(tc)
                            logger.debug(
                                "Streaming tool call complete",
                                extra={"tool_name": tc["function"]["name"]}
                            )
                        else:
                            logger.warning(
                                "Skipped tool call with invalid arguments",
                                extra={"tool_name": tc.get("function", {}).get("name", "unknown")}
                            )
                    # Handle multiple complete tool calls (e.g., DeepInfra)
                    if delta.get("tool_calls_complete"):
                        for tc in delta["tool_calls_complete"]:
                            args = tc.get("function", {}).get("arguments", "")
                            if _has_valid_tool_arguments(args):
                                tool_calls.append(tc)
                                logger.debug(
                                    "Streaming tool call complete (batch)",
                                    extra={"tool_name": tc["function"]["name"]}
                                )
                            else:
                                logger.warning(
                                    "Skipped tool call with invalid arguments (batch)",
                                    extra={"tool_name": tc.get("function", {}).get("name", "unknown")}
                                )

                    # Track usage if present
                    if "usage" in data:
                        usage = data["usage"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 405) and self._fallback_on_404 and endpoint_type == "responses":
                # Fallback to chat_completions
                return await self._streaming_fallback(
                    messages, model, on_token, on_reasoning,
                    tools, max_tokens, temperature, reasoning_effort, **kwargs
                )
            raise

        # Finalize accumulated streaming tool calls (for llama-server format).
        # Only add tool calls not already captured via tool_calls_complete
        # (DeepInfra sends complete tool calls in a single chunk, which both
        # the accumulator and parse_streaming_delta capture — skip duplicates).
        if tool_call_accumulators:
            existing_ids = {tc.get("id") for tc in tool_calls}
            for idx in sorted(tool_call_accumulators.keys()):
                acc = tool_call_accumulators[idx]
                # Skip incomplete tool calls (missing id, name, or arguments)
                if acc["id"] and acc["name"] and acc["arguments_parts"]:
                    if acc["id"] in existing_ids:
                        logger.debug(
                            "Skipped accumulator tool call already captured",
                            extra={"tool_name": acc["name"], "tool_id": acc["id"]},
                        )
                        continue
                    args_str = "".join(acc["arguments_parts"])
                    if not _has_valid_tool_arguments(args_str):
                        logger.warning(
                            "Skipped streaming tool call with invalid arguments",
                            extra={"tool_name": acc["name"], "tool_id": acc["id"]},
                        )
                        continue
                    tool_calls.append({
                        "id": acc["id"],
                        "type": "function",
                        "function": {
                            "name": acc["name"],
                            "arguments": args_str,
                        },
                    })
                    logger.debug(
                        "Finalized streaming tool call",
                        extra={
                            "tool_name": acc["name"],
                            "arguments_length": len(args_str),
                        }
                    )
                elif acc["id"] and acc["name"]:
                    logger.warning(
                        "Skipped streaming tool call with invalid arguments",
                        extra={"tool_name": acc["name"], "tool_id": acc["id"]},
                    )

        # Drop duplicate tool call IDs (keep first occurrence)
        if tool_calls:
            seen_ids: set[str] = set()
            deduped: list[Dict[str, Any]] = []
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                if tc_id in seen_ids:
                    logger.warning(
                        "Dropped duplicate tool call",
                        extra={"id": tc_id, "tool": tc.get("function", {}).get("name")},
                    )
                    continue
                seen_ids.add(tc_id)
                deduped.append(tc)
            tool_calls = deduped

        final_text = "".join(full_content)
        final_reasoning = "".join(full_reasoning) if full_reasoning else None

        # Log when content duplicates reasoning (API sending thinking in both fields)
        if final_text and final_reasoning and final_text.strip() in final_reasoning:
            logger.warning(
                "API sent content that duplicates reasoning — likely leaked thinking",
                extra={
                    "content_length": len(final_text),
                    "reasoning_length": len(final_reasoning),
                    "content_preview": final_text[:200],
                    "finish_reason": finish_reason,
                },
            )

        return LLMResponse(
            text=final_text,
            tool_calls=tool_calls if tool_calls else None,
            reasoning=final_reasoning,
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
        reasoning_effort: Optional[str] = None,
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
            reasoning_effort=reasoning_effort,
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
        reasoning_effort: Optional[str] = None,
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
            reasoning_effort=reasoning_effort,
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
            if response.status_code >= 400:
                error_body = await response.aread()
                error_text = error_body.decode(errors="replace")
                if (
                    response.status_code in (400, 422)
                    and "stream_options" in payload
                    and "stream_options" in error_text
                ):
                    logger.warning(
                        "Provider rejected stream_options; retrying fallback stream "
                        "without usage hint",
                        extra={"status": response.status_code, "url": url},
                    )
                    retry_payload = dict(payload)
                    retry_payload.pop("stream_options", None)
                    async with self._client.stream(
                        "POST",
                        url,
                        json=retry_payload,
                    ) as retry_response:
                        retry_response.raise_for_status()
                        async for line in retry_response.aiter_lines():
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
                logger.error(
                    "API error response",
                    extra={"status": response.status_code, "body": error_text[:2000]},
                )
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
