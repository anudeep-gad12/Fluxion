"""ChatGPT backend provider.

Translates between the standard LLMProvider interface and the ChatGPT
Codex Responses API (chatgpt.com/backend-api/codex/responses).

This allows users with ChatGPT Plus/Pro subscriptions to use OpenAI models
(GPT-5.x, Codex) through the reasoner app at no extra API cost.

Request Translation (Chat Completions -> Codex Responses):
- system messages -> instructions field or developer role
- user/assistant messages -> Responses API input format
- tool calls/results -> function_call / function_call_output items
- tool definitions -> flattened (strip {type: "function", function: {...}} wrapper)

Response Translation (Codex SSE -> Standard):
- response.output_text.delta -> content token callback
- response.reasoning_summary_text.delta -> reasoning token callback
- response.function_call_arguments.done -> tool call emission
- response.completed -> final LLMResponse
"""

import asyncio
import json
import random
import uuid
from typing import Any, Callable, Dict, List, Optional

import httpx

from orchestrator.logging_config import get_logger

from .base import LLMResponse, RetryExhaustedError

logger = get_logger(__name__)


class ChatGPTProvider:
    """Provider for the ChatGPT backend Codex Responses API.

    Uses OAuth access tokens obtained from the ChatGPT login flow to call
    chatgpt.com/backend-api/codex/responses. Translates between the standard
    chat completions format used internally and the Responses API format.
    """

    def __init__(
        self,
        access_token: str,
        account_id: str,
        backend_url: str = "https://chatgpt.com/backend-api",
        default_model: str = "gpt-5.2-codex",
        reasoning_effort: str = "medium",
        timeout: float = 120.0,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        """Initialize the ChatGPT provider.

        Args:
            access_token: OAuth access token from ChatGPT login.
            account_id: ChatGPT account ID extracted from JWT.
            backend_url: Base URL for the ChatGPT backend API.
            default_model: Default model to use for requests.
            reasoning_effort: Default reasoning effort level.
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts for transient errors.
            base_delay: Initial delay for exponential backoff.
            max_delay: Maximum delay cap for backoff.
        """
        self._access_token = access_token
        self._account_id = account_id
        self._backend_url = backend_url.rstrip("/")
        self._default_model = default_model
        self._reasoning_effort = reasoning_effort
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._retryable_statuses = [429, 500, 502, 503, 504]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "Content-Type": "application/json",
        }

        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
        )

    def update_token(self, access_token: str) -> None:
        """Update the access token after a refresh.

        Args:
            access_token: New OAuth access token.
        """
        self._access_token = access_token
        self._client.headers["Authorization"] = f"Bearer {access_token}"

    # =========================================================================
    # Request Translation
    # =========================================================================

    def _translate_messages_to_input(
        self,
        messages: List[Dict[str, Any]],
        instructions: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Translate chat completions messages to Responses API input format.

        Args:
            messages: Standard chat completions message list.
            instructions: Optional system prompt override.

        Returns:
            Tuple of (input_items, instructions_str).
        """
        input_items: List[Dict[str, Any]] = []
        extracted_instructions = instructions

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # System messages become the instructions field
                if not extracted_instructions:
                    extracted_instructions = content
                continue

            elif role == "user":
                input_items.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": content}],
                    }
                )

            elif role == "assistant":
                # Check if this is a tool call message
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                        input_items.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": func.get("name", ""),
                                "arguments": func.get("arguments", "{}"),
                            }
                        )
                elif content:
                    input_items.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": content}],
                        }
                    )

            elif role == "tool":
                call_id = msg.get("tool_call_id") or f"call_{uuid.uuid4().hex[:8]}"
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": content if isinstance(content, str) else json.dumps(content),
                    }
                )

        return input_items, extracted_instructions

    def _translate_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Flatten tool definitions for the Responses API.

        The Responses API expects tools without the {type: "function", function: {...}}
        wrapper used in chat completions.

        Args:
            tools: Standard chat completions tool definitions.

        Returns:
            Flattened tool definitions, or None if no tools.
        """
        if not tools:
            return None

        flattened = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                func = tool["function"]
                flattened.append(
                    {
                        "type": "function",
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {}),
                    }
                )
            else:
                # Already in correct format or unknown format - pass through
                flattened.append(tool)

        return flattened

    def _build_request_payload(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        instructions: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning_effort: Optional[str] = None,
        stream: bool = True,
    ) -> Dict[str, Any]:
        """Build the Codex Responses API request payload.

        Args:
            messages: Standard chat completions messages.
            model: Model name/ID.
            instructions: System prompt.
            tools: Tool definitions.
            reasoning_effort: Reasoning effort level.
            stream: Whether to stream the response.

        Returns:
            Request payload dict for the Codex Responses API.
        """
        input_items, extracted_instructions = self._translate_messages_to_input(
            messages, instructions
        )

        payload: Dict[str, Any] = {
            "model": self._default_model,
            "input": input_items,
            "stream": stream,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "reasoning": {
                "effort": reasoning_effort or self._reasoning_effort,
                "summary": "auto",
            },
        }

        if extracted_instructions:
            payload["instructions"] = extracted_instructions

        translated_tools = self._translate_tools(tools)
        if translated_tools:
            payload["tools"] = translated_tools

        return payload

    # =========================================================================
    # Response Translation
    # =========================================================================

    def _parse_sse_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a single SSE event from the Codex Responses API.

        Returns a dict with possible keys:
        - content_delta: str - text content delta
        - reasoning_delta: str - reasoning summary delta
        - tool_call_args_delta: dict with call_id, delta
        - tool_call_complete: dict with full tool call
        - response_id: str - response ID
        - usage: dict - token usage
        - done: bool - stream complete

        Args:
            data: Parsed JSON from SSE data line.

        Returns:
            Dict with parsed event data.
        """
        result: Dict[str, Any] = {}
        event_type = data.get("type", "")

        # Content text deltas
        if event_type == "response.output_text.delta":
            result["content_delta"] = data.get("delta", "")

        # Reasoning summary deltas
        elif event_type == "response.reasoning_summary_text.delta":
            result["reasoning_delta"] = data.get("delta", "")

        # Function call argument deltas
        elif event_type == "response.function_call_arguments.delta":
            call_id = (
                data.get("call_id")
                or data.get("item_id")
                or f"call_{uuid.uuid4().hex[:8]}"
            )
            result["tool_call_args_delta"] = {
                "call_id": call_id,
                "delta": data.get("delta", ""),
            }

        # Function call complete
        elif event_type == "response.function_call_arguments.done":
            call_id = (
                data.get("call_id")
                or data.get("item_id")
                or f"call_{uuid.uuid4().hex[:8]}"
            )
            result["tool_call_complete"] = {
                "call_id": call_id,
                "name": data.get("name", ""),
                "arguments": data.get("arguments", "{}"),
            }

        # Response created - capture ID
        elif event_type == "response.created":
            response = data.get("response", {})
            result["response_id"] = response.get("id")

        # Response completed - final state
        elif event_type == "response.completed":
            response = data.get("response", {})
            result["response_id"] = response.get("id")
            result["done"] = True

            # Extract usage from completed response
            usage = response.get("usage", {})
            if usage:
                result["usage"] = {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }

            # Extract any output text from the completed response
            output = response.get("output", [])
            for item in output:
                if item.get("type") == "message":
                    for content_block in item.get("content", []):
                        if content_block.get("type") == "output_text":
                            result["final_text"] = content_block.get("text", "")

        return result

    # =========================================================================
    # LLMProvider Protocol Implementation
    # =========================================================================

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
        """Complete a conversation (non-streaming).

        Consumes the full SSE stream and returns the accumulated response.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            instructions: System prompt.
            tools: Tool definitions.
            max_tokens: Ignored (not supported by Codex API).
            temperature: Ignored (not supported by Codex API).
            reasoning_effort: Reasoning effort level.
            stream: Ignored (always uses SSE internally).
            previous_response_id: Not used for ChatGPT backend.
            **kwargs: Additional parameters (ignored).

        Returns:
            Normalized LLMResponse.
        """
        # Build non-streaming request (consume SSE internally)
        full_content: List[str] = []
        full_reasoning: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        # Maps item_id -> {call_id, name} from output_item events
        item_id_map: Dict[str, Dict[str, str]] = {}
        usage: Dict[str, int] = {}
        response_id: Optional[str] = None

        payload = self._build_request_payload(
            messages=messages,
            model=model,
            instructions=instructions,
            tools=tools,
            reasoning_effort=reasoning_effort,
            stream=True,  # Always stream from backend, accumulate locally
        )

        url = f"{self._backend_url}/codex/responses"

        response = await self._request_with_retry(url, payload, stream=True)

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

            # Capture item_id -> (call_id, name) from output_item events
            evt_type = data.get("type", "")
            if evt_type in ("response.output_item.added", "response.output_item.done"):
                item = data.get("item", {})
                if isinstance(item, dict) and item.get("type") == "function_call":
                    fc_item_id = item.get("id", "")
                    if fc_item_id:
                        item_id_map[fc_item_id] = {
                            "call_id": item.get("call_id", "") or fc_item_id,
                            "name": item.get("name", ""),
                        }

            parsed = self._parse_sse_event(data)

            if parsed.get("content_delta"):
                full_content.append(parsed["content_delta"])
            if parsed.get("reasoning_delta"):
                full_reasoning.append(parsed["reasoning_delta"])
            if parsed.get("response_id"):
                response_id = parsed["response_id"]
            if parsed.get("usage"):
                usage = parsed["usage"]
            if parsed.get("tool_call_complete"):
                tc = parsed["tool_call_complete"]
                raw_id = tc["call_id"]  # Actually item_id
                mapped = item_id_map.get(raw_id, {})
                tc_call_id = mapped.get("call_id", raw_id)
                tc_name = tc["name"] or mapped.get("name", "")
                tool_calls.append(
                    {
                        "id": tc_call_id,
                        "type": "function",
                        "function": {
                            "name": tc_name,
                            "arguments": tc["arguments"],
                        },
                    }
                )

        await response.aclose()

        return LLMResponse(
            text="".join(full_content),
            tool_calls=tool_calls if tool_calls else None,
            reasoning="".join(full_reasoning) if full_reasoning else None,
            response_id=response_id,
            raw={},
            endpoint_used=url,
            usage=usage,
            finish_reason="stop",
        )

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
        """Stream a completion with callbacks for tokens.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            on_token: Callback for each content token.
            on_reasoning: Callback for reasoning tokens.
            instructions: System prompt.
            tools: Tool definitions.
            tool_choice: Ignored (not supported by Codex API).
            max_tokens: Ignored.
            temperature: Ignored.
            reasoning_effort: Reasoning effort level.
            previous_response_id: Not used for ChatGPT backend.
            **kwargs: Additional parameters (ignored).

        Returns:
            Final LLMResponse after streaming completes.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._do_streaming(
                    messages=messages,
                    model=model,
                    on_token=on_token,
                    on_reasoning=on_reasoning,
                    instructions=instructions,
                    tools=tools,
                    reasoning_effort=reasoning_effort,
                )
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.HTTPStatusError) as e:
                is_http_err = isinstance(e, httpx.HTTPStatusError)
                if is_http_err and e.response.status_code not in self._retryable_statuses:
                    raise
                last_error = e
                if attempt < self._max_retries:
                    delay = min(self._base_delay * (2**attempt), self._max_delay)
                    jitter = delay * random.uniform(0.1, 0.3)
                    total_delay = delay + jitter
                    logger.warning(
                        "ChatGPT streaming failed, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": self._max_retries,
                            "delay_seconds": round(total_delay, 2),
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(total_delay)

        raise RetryExhaustedError(
            f"ChatGPT streaming failed after {self._max_retries} retries: {last_error}"
        )

    async def _do_streaming(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        on_token: Callable[[str], None],
        on_reasoning: Optional[Callable[[str], None]],
        instructions: Optional[str],
        tools: Optional[List[Dict[str, Any]]],
        reasoning_effort: Optional[str],
    ) -> LLMResponse:
        """Execute the actual streaming request.

        Args:
            messages: List of message dicts.
            model: Model name/ID.
            on_token: Content token callback.
            on_reasoning: Reasoning token callback.
            instructions: System prompt.
            tools: Tool definitions.
            reasoning_effort: Reasoning effort level.

        Returns:
            LLMResponse after streaming completes.
        """
        full_content: List[str] = []
        full_reasoning: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        tool_call_accumulators: Dict[str, Dict[str, Any]] = {}  # item_id -> accumulator
        # Maps item_id -> {call_id, name} from output_item.added events
        # Delta events use item_id, but we need the real call_id and name
        item_id_map: Dict[str, Dict[str, str]] = {}
        usage: Dict[str, int] = {}
        response_id: Optional[str] = None
        finish_reason = "stop"

        payload = self._build_request_payload(
            messages=messages,
            model=model,
            instructions=instructions,
            tools=tools,
            reasoning_effort=reasoning_effort,
            stream=True,
        )

        url = f"{self._backend_url}/codex/responses"

        logger.info(
            "ChatGPT streaming request",
            extra={
                "url": url,
                "model": self._default_model,
                "input_items": len(payload.get("input", [])),
                "has_tools": bool(tools),
            },
        )

        async with self._client.stream("POST", url, json=payload) as response:
            if response.status_code >= 400:
                error_body = await response.aread()
                logger.error(
                    "ChatGPT API error",
                    extra={
                        "status": response.status_code,
                        "body": error_body.decode()[:2000],
                    },
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

                # Track function call metadata from output_item events
                evt_type = data.get("type", "")
                if evt_type in (
                    "response.output_item.added",
                    "response.output_item.done",
                ):
                    item = data.get("item", {})
                    if isinstance(item, dict) and item.get("type") == "function_call":
                        # Map item.id -> real call_id + name
                        # Delta events reference item_id which = item.id
                        fc_item_id = item.get("id", "")
                        fc_call_id = item.get("call_id", "")
                        fc_name = item.get("name", "")
                        if fc_item_id:
                            item_id_map[fc_item_id] = {
                                "call_id": fc_call_id or fc_item_id,
                                "name": fc_name,
                            }

                parsed = self._parse_sse_event(data)

                # Content deltas
                if parsed.get("content_delta"):
                    delta = parsed["content_delta"]
                    full_content.append(delta)
                    on_token(delta)

                # Reasoning deltas
                if parsed.get("reasoning_delta") and on_reasoning:
                    delta = parsed["reasoning_delta"]
                    full_reasoning.append(delta)
                    on_reasoning(delta)

                # Tool call argument deltas - accumulate
                if parsed.get("tool_call_args_delta"):
                    tc_delta = parsed["tool_call_args_delta"]
                    call_id = tc_delta["call_id"]
                    if call_id not in tool_call_accumulators:
                        tool_call_accumulators[call_id] = {
                            "call_id": call_id,
                            "name": "",
                            "arguments_parts": [],
                        }
                    tool_call_accumulators[call_id]["arguments_parts"].append(tc_delta["delta"])

                # Tool call complete
                if parsed.get("tool_call_complete"):
                    tc = parsed["tool_call_complete"]
                    raw_id = tc["call_id"]  # This is actually item_id
                    # Resolve real call_id and name from item_id_map
                    mapped = item_id_map.get(raw_id, {})
                    tc_call_id = mapped.get("call_id", raw_id)
                    tc_name = tc["name"] or mapped.get("name", "")
                    tool_calls.append(
                        {
                            "id": tc_call_id,
                            "type": "function",
                            "function": {
                                "name": tc_name,
                                "arguments": tc["arguments"],
                            },
                        }
                    )
                    # Remove from accumulators since we have the complete version
                    tool_call_accumulators.pop(raw_id, None)
                    finish_reason = "tool_calls"

                # Response metadata
                if parsed.get("response_id"):
                    response_id = parsed["response_id"]
                if parsed.get("usage"):
                    usage = parsed["usage"]

        # Finalize any remaining accumulated tool calls
        for call_id, acc in tool_call_accumulators.items():
            if acc["name"] and acc["arguments_parts"]:
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": acc["name"],
                            "arguments": "".join(acc["arguments_parts"]),
                        },
                    }
                )

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

    async def health_check(self) -> bool:
        """Check if the provider is healthy by verifying token validity.

        Returns:
            True if the token is valid, False otherwise.
        """
        try:
            # Simple check - try to access backend with current token
            response = await self._client.get(
                f"{self._backend_url}/me",
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Clean up provider resources."""
        await self._client.aclose()

    # =========================================================================
    # HTTP Request Helpers
    # =========================================================================

    async def _request_with_retry(
        self,
        url: str,
        payload: Dict[str, Any],
        stream: bool = False,
    ) -> httpx.Response:
        """Make request with exponential backoff + jitter.

        Args:
            url: Request URL.
            payload: Request payload.
            stream: Whether to return a streaming response.

        Returns:
            HTTP response.

        Raises:
            RetryExhaustedError: If all retries are exhausted.
        """
        last_error: Optional[str] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                if stream:
                    response = await self._client.send(
                        self._client.build_request("POST", url, json=payload),
                        stream=True,
                    )
                else:
                    response = await self._client.post(url, json=payload)

                if response.status_code not in self._retryable_statuses:
                    return response

                last_error = f"HTTP {response.status_code}"
                if stream:
                    await response.aclose()
                logger.warning(
                    "ChatGPT retryable HTTP status",
                    extra={
                        "status_code": response.status_code,
                        "attempt": attempt,
                    },
                )

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                logger.warning("ChatGPT request timeout", extra={"attempt": attempt})
            except httpx.ConnectError as e:
                last_error = f"Connect error: {e}"
                logger.warning("ChatGPT connection error", extra={"attempt": attempt})

            if attempt < self._max_retries:
                delay = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
                jitter = delay * random.uniform(0.1, 0.3)
                await asyncio.sleep(delay + jitter)

        raise RetryExhaustedError(
            f"ChatGPT: max retries ({self._max_retries}) exceeded. Last: {last_error}"
        )
