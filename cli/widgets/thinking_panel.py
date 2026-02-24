"""Collapsible thinking/reasoning display panel."""

from textual.app import ComposeResult
from textual.widgets import Collapsible, Static


class ThinkingPanel(Collapsible):
    """Collapsible panel for displaying reasoning/thinking text.

    Starts collapsed; user can expand to see the model's reasoning.
    Styling is handled by the app.tcss file.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(title="[thinking]", collapsed=True, **kwargs)
        self._buffer = ""
        self._content_widget: Static | None = None

    def compose(self) -> ComposeResult:
        """Compose the thinking panel."""
        self._content_widget = Static("", classes="thinking-content")
        yield self._content_widget

    def append_token(self, token: str) -> None:
        """Append a thinking token."""
        self._buffer += token
        if self._content_widget:
            # Show last 500 chars to keep it manageable
            display = (
                self._buffer[-500:]
                if len(self._buffer) > 500
                else self._buffer
            )
            self._content_widget.update(display)

    def clear_content(self) -> None:
        """Clear thinking content."""
        self._buffer = ""
        if self._content_widget:
            self._content_widget.update("")
