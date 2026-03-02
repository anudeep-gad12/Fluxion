"""User and assistant message display widget."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class MessageBubble(Vertical):
    """A single message bubble (user, assistant, or system).

    Claude Code style:
    - User messages: highlighted background with purple left border
    - Assistant messages: empty shells for StreamingMarkdown
    - System messages: dim with ❋ prefix
    """

    def __init__(self, role: str, content: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._role = role
        self._content = content
        self.add_class(role)

    def compose(self) -> ComposeResult:
        """Compose the message bubble."""
        if self._role == "user" and self._content:
            yield Static(self._content, classes="user-message")
        elif self._role == "system" and self._content:
            yield Static(
                f"[dim]❋ {self._content}[/dim]",
                classes="system-message",
            )
