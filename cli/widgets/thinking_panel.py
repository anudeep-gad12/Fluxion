"""Inline thinking/reasoning indicator."""

from textual.widgets import Static


class ThinkingPanel(Static):
    """Inline thinking indicator — shows truncated reasoning on one dim line.

    Renders as: ∴ some reasoning text here…
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._buffer = ""

    def append_token(self, token: str) -> None:
        """Append a thinking token."""
        self._buffer += token
        # Show last ~100 chars, single line
        display = self._buffer.replace("\n", " ").strip()
        if len(display) > 100:
            display = "…" + display[-100:]
        self.update(f"∴ {display}")

    def clear_content(self) -> None:
        """Clear thinking content."""
        self._buffer = ""
        self.update("")
