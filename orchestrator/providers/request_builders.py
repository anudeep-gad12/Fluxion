"""Request builders for different API endpoints."""

import json
from typing import Any, Dict, List, Optional


def build_responses_request(
    messages: List[Dict[str, Any]],
    model: str,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    reasoning_effort: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    stream: bool = True,
    previous_response_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build /v1/responses request payload.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        model: Model name/ID.
        instructions: System prompt (separate from messages in responses API).
        tools: Tool definitions for function calling.
        reasoning_effort: Native reasoning effort ("low", "medium", "high").
        max_output_tokens: Maximum tokens (responses API uses this, not max_tokens).
        stream: Whether to stream the response.
        previous_response_id: Response ID from previous call for stateful mode.

    Returns:
        Request payload dict for /v1/responses.
    """
    payload: Dict[str, Any] = {
        "model": model,
        "input": messages,  # responses API uses 'input' not 'messages'
        "stream": stream,
    }

    # System prompt as instructions (stateless mode)
    if instructions:
        payload["instructions"] = instructions

    if max_output_tokens:
        payload["max_output_tokens"] = max_output_tokens

    if tools:
        # Transform tools to responses API format
        payload["tools"] = [
            {"type": "function", "function": t.get("function", t)}
            for t in tools
        ]

    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}

    # Stateful mode: chain to previous response
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id

    return payload


def build_chat_completions_request(
    messages: List[Dict[str, Any]],
    model: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stream: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Build /v1/chat/completions request payload.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        model: Model name/ID.
        tools: Tool definitions for function calling.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        stream: Whether to stream the response.
        **kwargs: Additional parameters (seed, top_p, etc.).

    Returns:
        Request payload dict for /v1/chat/completions.

    Note:
        reasoning_effort is NOT supported by chat/completions and is ignored.
    """
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    if max_tokens:
        payload["max_tokens"] = max_tokens

    if temperature is not None:
        payload["temperature"] = temperature

    # Add optional parameters if provided
    for key in ["seed", "top_p", "frequency_penalty", "presence_penalty"]:
        if key in kwargs and kwargs[key] is not None:
            payload[key] = kwargs[key]

    return payload
