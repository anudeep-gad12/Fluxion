"""Multi-line input area with Enter to submit."""

from textual.message import Message
from textual.widgets import TextArea


class InputArea(TextArea):
    """Multi-line input area for user messages.

    Enter submits the message.
    Shift+Enter inserts a newline.
    """

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

    def _on_key(self, event) -> None:
        """Route Enter vs Shift+Enter."""
        if event.key == "shift+enter":
            # Let TextArea handle it as a normal newline
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
