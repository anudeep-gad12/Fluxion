"""Live-updating markdown widget for streaming responses."""

from textual.widgets import Markdown


class StreamingMarkdown(Markdown):
    """Markdown widget that supports incremental token appending.

    Used for rendering the assistant's streaming response.
    Styling is handled by the app.tcss file.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._buffer = ""

    def append_token(self, token: str) -> None:
        """Append a token to the streaming buffer and re-render."""
        self._buffer += token
        self.update(self._buffer)

    def set_content(self, content: str) -> None:
        """Set the full content, replacing the buffer."""
        self._buffer = content
        self.update(self._buffer)

    def clear_content(self) -> None:
        """Clear the buffer and display."""
        self._buffer = ""
        self.update("")

    @property
    def content(self) -> str:
        """Get the current buffer content."""
        return self._buffer
