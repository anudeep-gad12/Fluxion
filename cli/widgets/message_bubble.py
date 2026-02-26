"""User and assistant message display widget."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class MessageBubble(Vertical):
    """A single message bubble (user, assistant, or system).

    User messages render as `❯ content` with no border.
    Assistant messages are empty shells — StreamingMarkdown is mounted externally.
    System messages render inline as dim italic text.
    """

    def __init__(self, role: str, content: str = "", **kwargs) -> None:
        """Initialize message bubble.

        Args:
            role: "user", "assistant", or "system".
            content: Message text content.
        """
        super().__init__(**kwargs)
        self._role = role
        self._content = content
        self.add_class(role)

    def compose(self) -> ComposeResult:
        """Compose the message bubble."""
        if self._role == "user" and self._content:
            yield Static(f"[dim]❯[/dim] {self._content}", classes="user-message")
        elif self._role == "system" and self._content:
            yield Static(
                f"[dim italic]{self._content}[/dim italic]",
                classes="system-message",
            )
