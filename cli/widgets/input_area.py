"""Multi-line input area with Enter to submit."""

from textual.binding import Binding
from textual.message import Message
from textual.widgets import TextArea


class InputArea(TextArea):
    """Multi-line input area for user messages.

    Enter submits the message.
    Shift+Enter or Ctrl+J inserts a newline.
    """

    BINDINGS = [
        Binding("enter", "submit", "Send", show=False),
    ]

    class Submitted(Message):
        """Fired when the user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs) -> None:
        super().__init__(
            language=None,
            theme="monokai",
            show_line_numbers=False,
            **kwargs,
        )

    def action_submit(self) -> None:
        """Submit the current text."""
        text = self.text.strip()
        if text:
            self.post_message(self.Submitted(text))
            self.clear()

    def _on_key(self, event) -> None:
        """Handle key events for newline insertion."""
        # Shift+Enter or Ctrl+J inserts a newline
        if event.key == "shift+enter" or event.key == "ctrl+j":
            self.insert("\n")
            event.prevent_default()
            event.stop()
