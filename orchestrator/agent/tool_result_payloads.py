"""Display payload helpers for tool results.

Tool implementations can return rich result_data for model replay and trace
storage. Browser events need a smaller display-oriented shape: raw unified
diff text for file writes/edits and structured stdout/stderr for bash.
"""

from __future__ import annotations

import json
from typing import Any, Optional

MAX_DISPLAY_CHARS = 10000


def parse_stored_result_detail(result_detail: Optional[str]) -> Any:
    """Parse a persisted result_detail value back into its original payload."""
    if not result_detail:
        return None
    try:
        return json.loads(result_detail)
    except (TypeError, ValueError):
        return result_detail


def display_result_data(tool_name: str, result_data: Any) -> Optional[str]:
    """Return browser-displayable result_data for write/edit tools."""
    if tool_name not in {"write_file", "edit_file", "apply_patch"} or result_data is None:
        return None

    diff: Any
    if isinstance(result_data, dict):
        diff = result_data.get("diff") or result_data.get("preview")
    else:
        diff = result_data

    if diff is None:
        return None

    text = str(diff)
    if not text:
        return None
    return text[:MAX_DISPLAY_CHARS]


def bash_output_from_result_data(result_data: Any) -> Optional[dict[str, Any]]:
    """Return browser-displayable command output from a tool result payload."""
    if not isinstance(result_data, dict):
        return None

    return {
        "stdout": str(result_data.get("stdout", ""))[:MAX_DISPLAY_CHARS],
        "stderr": str(result_data.get("stderr", ""))[:MAX_DISPLAY_CHARS],
        "exit_code": result_data.get("exit_code"),
        "truncated": bool(result_data.get("truncated") or result_data.get("timed_out")),
    }
