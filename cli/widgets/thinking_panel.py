"""Inline thinking/reasoning indicator with click-to-expand."""

from textual.widgets import Static


class ThinkingPanel(Static):
    """Inline thinking indicator — click to expand/collapse.

    Collapsed: ∴ last ~100 chars (single line)
    Expanded:  ∴ full text with preserved newlines
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._buffer = ""
        self._expanded = False

    def append_token(self, token: str) -> None:
        """Append a thinking token."""
        self._buffer += token
        self._render_display()

    def _render_display(self) -> None:
        """Render the display based on expanded/collapsed state."""
        if not self._buffer:
            self.update("")
            return

        if self._expanded:
            # Full text with preserved newlines
            self.update(f"∴ {self._buffer.strip()}")
        else:
            # Single line, last ~100 chars
            display = self._buffer.replace("\n", " ").strip()
            if len(display) > 100:
                display = "…" + display[-100:]
            self.update(f"∴ {display}")

    def on_click(self) -> None:
        """Toggle expanded/collapsed state."""
        self._expanded = not self._expanded
        if self._expanded:
            self.add_class("expanded")
        else:
            self.remove_class("expanded")
        self._render_display()

    def clear_content(self) -> None:
        """Clear thinking content."""
        self._buffer = ""
        self._expanded = False
        self.remove_class("expanded")
        self.update("")
