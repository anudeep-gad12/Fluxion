"""User and assistant message display widget."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Markdown, Static


class MessageBubble(Vertical):
    """A single message bubble (user or assistant).

    User messages are styled differently from assistant messages.
    """

    DEFAULT_CSS = """
    MessageBubble {
        margin: 0 1;
        padding: 0 1;
    }
    MessageBubble .message-role {
        color: $text-muted;
        text-style: bold;
        margin-bottom: 0;
    }
    MessageBubble.user .message-role {
        color: $success;
    }
    MessageBubble.assistant .message-role {
        color: $primary;
    }
    """

    def __init__(self, role: str, content: str = "", **kwargs) -> None:
        """Initialize message bubble.

        Args:
            role: "user" or "assistant".
            content: Message text content.
        """
        super().__init__(**kwargs)
        self._role = role
        self._content = content
        self.add_class(role)

    def compose(self) -> ComposeResult:
        """Compose the message bubble."""
        role_label = "You" if self._role == "user" else "Assistant"
        yield Label(f"{role_label}:", classes="message-role")
        if self._role == "user":
            yield Static(self._content, classes="message-content")
        else:
            yield Markdown(self._content, classes="message-content")
