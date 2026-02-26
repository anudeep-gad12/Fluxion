"""Multi-line input area with Enter to submit and approval mode."""

from textual.message import Message
from textual.widgets import TextArea


class InputArea(TextArea):
    """Multi-line input area for user messages.

    Enter submits the message.
    Shift+Enter inserts a newline.

    Approval mode: replaces input with read-only tool details,
    responds to y/n keys for approve/deny.
    """

    class Submitted(Message):
        """Fired when the user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class ApprovalDecision(Message):
        """User decided on tool approval."""

        def __init__(self, approved: bool) -> None:
            super().__init__()
            self.approved = approved

    def __init__(self, **kwargs) -> None:
        super().__init__(
            language=None,
            theme="vscode_dark",
            show_line_numbers=False,
            **kwargs,
        )
        self._approval_mode = False

    @property
    def approval_mode(self) -> bool:
        """Whether the input area is in approval mode."""
        return self._approval_mode

    def enter_approval_mode(self, tool_display: str) -> None:
        """Switch input to approval mode showing tool details."""
        self._approval_mode = True
        self.text = tool_display
        self.read_only = True
        self.add_class("approval-mode")

    def exit_approval_mode(self) -> None:
        """Restore normal input mode."""
        if not self._approval_mode:
            return
        self._approval_mode = False
        self.read_only = False
        self.text = ""
        self.remove_class("approval-mode")

    def _on_key(self, event) -> None:
        """Route keys based on mode."""
        if self._approval_mode:
            if event.key in ("enter", "y"):
                event.prevent_default()
                event.stop()
                self.post_message(self.ApprovalDecision(approved=True))
            elif event.key == "n":
                event.prevent_default()
                event.stop()
                self.post_message(self.ApprovalDecision(approved=False))
            elif event.key == "escape":
                # Let escape bubble up to chat screen for cancel
                return
            else:
                # Block all other keys in approval mode
                event.prevent_default()
                event.stop()
            return

        # Normal mode: Enter submits, Shift+Enter inserts newline
        if event.key == "shift+enter":
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
