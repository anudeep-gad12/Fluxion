"""Harmony format parser using official openai-harmony library.

This module provides proper parsing of gpt-oss Harmony format output,
extracting tool calls from the structured format instead of regex hacking.

Usage:
    parser = HarmonyParser()
    tool_calls = parser.parse_tool_calls(model_output_text)
    # Returns list of OpenAI-format tool call dicts
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from openai_harmony import (
    HarmonyEncodingName,
    Role,
    load_harmony_encoding,
)

from orchestrator.logging_config import get_logger

logger = get_logger(__name__)


class HarmonyParser:
    """Parser for gpt-oss Harmony format responses.

    Uses the official openai-harmony library to parse tool calls
    from model output instead of fragile regex patterns.

    The Harmony format uses special tokens like:
    - <|channel|> - marks start of a channel
    - <|message|> - marks message content
    - recipient field - contains the target tool name

    Example input:
        <|channel|>commentary to=python code<|message|>print("hello")

    Parsed output:
        - channel: "commentary"
        - recipient: "python"
        - content: 'print("hello")'
    """

    # Map of Harmony recipients to our tool names
    RECIPIENT_TO_TOOL: Dict[str, str] = {
        "python": "exec_command",
        "python_execute": "exec_command",
        "web_search": "web_search",
        "web_extract": "web_extract",
    }

    def __init__(self) -> None:
        """Initialize the Harmony parser with the gpt-oss encoding."""
        self._encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

    def parse_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse tool calls from Harmony format text.

        Args:
            text: Raw model output that may contain Harmony format tool calls.

        Returns:
            List of tool call dicts in OpenAI format, or None if no tool calls found.
            Each dict has: id, type, function: {name, arguments}
        """
        if not text:
            return None

        # Extract Harmony portion - the library expects clean token sequences
        # Model often outputs preamble text before the <|channel|> token
        harmony_text = text
        channel_idx = text.find("<|channel|>")
        if channel_idx > 0:
            harmony_text = text[channel_idx:]
            logger.debug(
                "Extracted Harmony portion from text",
                extra={"original_len": len(text), "harmony_len": len(harmony_text)},
            )

        try:
            # Encode text with special tokens allowed
            tokens = self._encoding.encode(harmony_text, allowed_special="all")

            # Parse messages from tokens (non-strict to handle malformed output)
            messages = self._encoding.parse_messages_from_completion_tokens(
                tokens, role=Role.ASSISTANT, strict=False
            )

            tool_calls: List[Dict[str, Any]] = []

            for msg in messages:
                # Check if this message is a tool call
                # Tool calls have a recipient (the target tool name)
                recipient = msg.recipient
                if not recipient:
                    continue

                # Map recipient to our tool name
                tool_name = self.RECIPIENT_TO_TOOL.get(recipient)
                if not tool_name:
                    logger.debug(
                        "Unknown Harmony recipient",
                        extra={"recipient": recipient},
                    )
                    continue

                # Extract content (the code or arguments)
                content_text = ""
                if msg.content:  # Guard against None content
                    for content in msg.content:
                        # TextContent has a .text attribute
                        if hasattr(content, "text"):
                            content_text += content.text

                if not content_text.strip():
                    continue

                # Build tool call in OpenAI format
                if tool_name == "exec_command" and recipient in {"python", "python_execute"}:
                    code = content_text.strip()
                    delimiter = "PYTHON"
                    while delimiter in code:
                        delimiter += "_END"
                    arguments = json.dumps({
                        "cmd": f"python3 - <<'{delimiter}'\n{code}\n{delimiter}"
                    })
                elif tool_name == "web_search":
                    # Try to parse as JSON first, otherwise treat as query
                    try:
                        args = json.loads(content_text.strip())
                        arguments = json.dumps(args)
                    except json.JSONDecodeError:
                        arguments = json.dumps({"query": content_text.strip()})
                elif tool_name == "web_extract":
                    try:
                        args = json.loads(content_text.strip())
                        arguments = json.dumps(args)
                    except json.JSONDecodeError:
                        arguments = json.dumps({"url": content_text.strip()})
                else:
                    arguments = json.dumps({"input": content_text.strip()})

                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                })

                logger.info(
                    "Parsed tool call from Harmony format",
                    extra={
                        "tool_name": tool_name,
                        "channel": msg.channel,
                        "recipient": recipient,
                        "content_length": len(content_text),
                    },
                )

            return tool_calls if tool_calls else None

        except Exception as e:
            logger.warning(
                "Failed to parse Harmony format",
                extra={"error": str(e), "text_preview": text[:200]},
            )
            return None


# Singleton instance for reuse
_parser: Optional[HarmonyParser] = None


def get_harmony_parser() -> HarmonyParser:
    """Get singleton HarmonyParser instance.

    Returns:
        HarmonyParser instance.
    """
    global _parser
    if _parser is None:
        _parser = HarmonyParser()
    return _parser


def parse_harmony_tool_calls(text: str) -> Optional[List[Dict[str, Any]]]:
    """Convenience function to parse tool calls from Harmony format.

    Args:
        text: Raw model output text.

    Returns:
        List of tool call dicts in OpenAI format, or None if no tool calls.
    """
    return get_harmony_parser().parse_tool_calls(text)
