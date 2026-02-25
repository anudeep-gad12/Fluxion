"""Scrollable conversation message list."""

from textual.containers import VerticalScroll


class MessageList(VerticalScroll):
    """Scrollable container for conversation messages.

    Auto-scrolls to bottom when new messages are added.
    Styling is handled by the app.tcss file.
    """

    def scroll_to_bottom(self) -> None:
        """Scroll to the latest message."""
        self.scroll_end(animate=False)
