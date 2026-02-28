"""Request builders for different API endpoints."""

import json
from typing import Any, Dict, List, Optional


def _transform_messages_for_responses_api(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform chat-format messages to responses API format.

    The responses API uses a different format for input items:
    - User messages: {"role": "user", "content": "..."}
    - Assistant messages without tools: {"role": "assistant", "content": "..."}
    - Assistant messages with tool calls: Split into content + function_call items
    - Tool results: {"type": "function_call_output", "call_id": "...", "output": "..."}

    Args:
        messages: List of message dicts in chat format.

    Returns:
        List of message dicts in responses API format.
    """
    result = []

    for msg in messages:
        role = msg.get("role")

        if role == "tool":
            # Transform tool result to function_call_output format
            result.append({
                "type": "function_call_output",
                "call_id": msg.get("tool_call_id"),
                "output": msg.get("content", ""),
            })

        elif role == "assistant" and msg.get("tool_calls"):
            # Assistant message with tool calls needs special handling
            # First add the text content (if any) as assistant message
            content = msg.get("content")
            if content:
                result.append({"role": "assistant", "content": content})

            # Then add each tool call as a function_call item
            for tool_call in (msg.get("tool_calls") or []):
                func = tool_call.get("function", {})
                arguments = func.get("arguments", "{}")
                # arguments might be a dict or string
                if isinstance(arguments, dict):
                    arguments = json.dumps(arguments)
                result.append({
                    "type": "function_call",
                    "call_id": tool_call.get("id"),
                    "name": func.get("name"),
                    "arguments": arguments,
                })

        else:
            # User/assistant messages (without tools) stay the same
            result.append(msg)

    return result


def build_responses_request(
    messages: List[Dict[str, Any]],
    model: str,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
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
        tool_choice: Tool selection behavior. Options:
            - None or "auto": Model decides (default)
            - "required": Model MUST call a tool
            - "tool_name": Force specific tool (e.g., "python_execute")
        reasoning_effort: Native reasoning effort ("low", "medium", "high").
        max_output_tokens: Maximum tokens (responses API uses this, not max_tokens).
        stream: Whether to stream the response.
        previous_response_id: Response ID from previous call for stateful mode.

    Returns:
        Request payload dict for /v1/responses.
    """
    # Transform messages to responses API format
    transformed_messages = _transform_messages_for_responses_api(messages)

    payload: Dict[str, Any] = {
        "model": model,
        "input": transformed_messages,  # responses API uses 'input' not 'messages'
        "stream": stream,
    }

    # System prompt as instructions (stateless mode)
    if instructions:
        payload["instructions"] = instructions

    if max_output_tokens:
        payload["max_output_tokens"] = max_output_tokens

    if tools:
        # Transform tools to responses API format (flat structure, not nested under "function")
        # OpenAI format: {"type": "function", "name": "...", "description": "...", "parameters": {...}}
        transformed_tools = []
        for t in tools:
            func = t.get("function", t)
            transformed_tools.append({
                "type": "function",
                "name": func.get("name"),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            })
        payload["tools"] = transformed_tools

        # Add tool_choice to force tool usage when specified
        # OpenAI responses API format:
        # - "auto": Model decides (default)
        # - "required": Model MUST call at least one tool
        # - {"type": "function", "name": "..."}: Force specific tool
        if tool_choice:
            if tool_choice in ("auto", "none", "required"):
                payload["tool_choice"] = tool_choice
            else:
                # Specific tool name - use OpenAI format
                payload["tool_choice"] = {
                    "type": "function",
                    "name": tool_choice,
                }

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
    tool_choice: Optional[str] = None,
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
        tool_choice: Tool selection behavior. Options:
            - None or "auto": Model decides (default)
            - "required": Model MUST call a tool
            - "tool_name": Force specific tool (e.g., "python_execute")
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        stream: Whether to stream the response.
        **kwargs: Additional parameters (seed, top_p, etc.).

    Returns:
        Request payload dict for /v1/chat/completions.

    Note:
        reasoning_effort is NOT supported by chat/completions and is ignored.
    """
    # Strip internal metadata fields that strict APIs (e.g. Mistral) reject
    _internal_keys = {"_plan", "_step", "_pruned", "_llm_summary"}
    clean_messages = [
        {k: v for k, v in msg.items() if k not in _internal_keys}
        for msg in messages
    ]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": clean_messages,
        "stream": stream,
    }

    if tools:
        payload["tools"] = tools
        # Handle tool_choice
        # Note: LM Studio doesn't support {"type": "function", "function": {"name": ...}} format
        # So we convert specific tool names to "required" which forces the model to call a tool
        if tool_choice:
            if tool_choice in ("auto", "none", "required"):
                payload["tool_choice"] = tool_choice
            else:
                # It's a tool name - but LM Studio doesn't support forcing specific tools
                # Use "required" instead which forces ANY tool call
                payload["tool_choice"] = "required"
        else:
            payload["tool_choice"] = "auto"

    # OpenAI reasoning models (gpt-5*, o1*, o3*, o4*) use max_completion_tokens
    # and don't support temperature parameter
    _is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))

    if max_tokens:
        if _is_reasoning:
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens

    if temperature is not None and not _is_reasoning:
        payload["temperature"] = temperature

    # Add optional parameters if provided
    for key in ["seed", "top_p", "frequency_penalty", "presence_penalty"]:
        if key in kwargs and kwargs[key] is not None:
            payload[key] = kwargs[key]

    # OpenRouter reasoning control (passed through from caller)
    if "reasoning" in kwargs and kwargs["reasoning"] is not None:
        payload["reasoning"] = kwargs["reasoning"]

    return payload
