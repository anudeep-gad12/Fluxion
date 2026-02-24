"""Scrollable conversation message list."""

from textual.containers import VerticalScroll


class MessageList(VerticalScroll):
    """Scrollable container for conversation messages.

    Auto-scrolls to bottom when new messages are added.
    """

    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
        scrollbar-size: 1 1;
    }
    """

    def watch_scroll_y(self, value: float) -> None:
        """Keep scrolled to bottom on new content."""
        pass

    def scroll_to_bottom(self) -> None:
        """Scroll to the latest message."""
        self.scroll_end(animate=False)
