"""Response parsers for different API endpoints."""

import json
from typing import Any, Dict, List, Optional

from .base import LLMResponse


def parse_responses_result(raw: Dict[str, Any], endpoint: str) -> LLMResponse:
    """Normalize /v1/responses output to LLMResponse.

    Args:
        raw: Raw JSON response from /v1/responses endpoint.
        endpoint: The endpoint URL used (for tracking).

    Returns:
        Normalized LLMResponse.
    """
    # Responses API returns output as list of content blocks
    output = raw.get("output", [])

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    reasoning: Optional[str] = None

    for item in output:
        item_type = item.get("type")

        if item_type == "message":
            content = item.get("content", [])
            for block in content:
                block_type = block.get("type")
                # Handle both OpenAI format ("text") and LM Studio format ("output_text")
                if block_type in ("text", "output_text"):
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    # Convert to OpenAI tool_calls format for consistency
                    tool_calls.append({
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })

        elif item_type == "reasoning":
            # Extract reasoning from different formats:
            # 1. OpenAI format: summary.text
            # 2. LM Studio format: content[].type == "reasoning_text"
            summary = item.get("summary", {})
            if isinstance(summary, dict) and summary.get("text"):
                reasoning = summary.get("text", "")
            elif isinstance(summary, str) and summary:
                reasoning = summary
            else:
                # LM Studio format: content array with reasoning_text blocks
                content = item.get("content", [])
                reasoning_parts = []
                for block in content:
                    if block.get("type") == "reasoning_text":
                        reasoning_parts.append(block.get("text", ""))
                if reasoning_parts:
                    reasoning = "".join(reasoning_parts)

    return LLMResponse(
        text="".join(text_parts),
        tool_calls=tool_calls if tool_calls else None,
        reasoning=reasoning,
        response_id=raw.get("id"),  # Extract response ID for stateful mode
        raw=raw,
        endpoint_used=endpoint,
        usage=raw.get("usage", {}),
        finish_reason=raw.get("stop_reason", "stop"),
    )


def parse_chat_result(raw: Dict[str, Any], endpoint: str) -> LLMResponse:
    """Normalize /v1/chat/completions output to LLMResponse.

    Args:
        raw: Raw JSON response from /v1/chat/completions endpoint.
        endpoint: The endpoint URL used (for tracking).

    Returns:
        Normalized LLMResponse.
    """
    choices = raw.get("choices", [{}])
    if not choices:
        return LLMResponse(
            text="",
            raw=raw,
            endpoint_used=endpoint,
            finish_reason="error",
        )

    choice = choices[0]
    message = choice.get("message", {})

    # Handle different reasoning field names (gpt-oss uses 'reasoning' or 'reasoning_content')
    reasoning = message.get("reasoning") or message.get("reasoning_content")

    return LLMResponse(
        text=message.get("content", "") or "",
        tool_calls=message.get("tool_calls"),
        reasoning=reasoning,
        raw=raw,
        endpoint_used=endpoint,
        usage=raw.get("usage", {}),
        finish_reason=choice.get("finish_reason", "stop"),
    )


def parse_streaming_delta(
    delta: Dict[str, Any], endpoint_type: str
) -> Dict[str, Optional[str]]:
    """Parse a streaming delta chunk.

    Args:
        delta: The delta dict from a streaming response.
        endpoint_type: "responses" or "chat_completions".

    Returns:
        Dict with 'content', 'reasoning', and 'tool_call' keys.
    """
    result: Dict[str, Optional[str]] = {
        "content": None,
        "reasoning": None,
        "tool_call": None,
    }

    if endpoint_type == "responses":
        # Responses API streaming format
        delta_type = delta.get("type")

        # OpenAI format
        if delta_type == "content_block_delta":
            block_delta = delta.get("delta", {})
            if block_delta.get("type") == "text_delta":
                result["content"] = block_delta.get("text")
        elif delta_type == "reasoning_delta":
            result["reasoning"] = delta.get("delta", {}).get("text")

        # LM Studio format: response.output_text.delta, response.reasoning_text.delta
        elif delta_type == "response.output_text.delta":
            result["content"] = delta.get("delta")
        elif delta_type == "response.reasoning_text.delta":
            result["reasoning"] = delta.get("delta")

    else:
        # Chat completions streaming format
        content = delta.get("content")
        if content:
            result["content"] = content

        # gpt-oss native reasoning (LM Studio returns this separately)
        reasoning = delta.get("reasoning") or delta.get("reasoning_content")
        if reasoning:
            result["reasoning"] = reasoning

        # Tool call deltas (accumulated separately)
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            result["tool_call"] = json.dumps(tool_calls)

    return result
