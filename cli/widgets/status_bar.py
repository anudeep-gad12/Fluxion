"""Bottom status bar showing mode, provider, step info, and connection."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusBar(Horizontal):
    """Bottom status bar for the TUI.

    Shows: mode · provider · Step N/M · ●
    Static "working…" when busy, no rotating phrases.
    """

    def __init__(
        self,
        mode: str = "agent",
        provider: str = "default",
        model: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._mode = mode
        self._provider = provider
        self._model = model
        self._step_text = ""
        self._connected = False
        self._is_busy = False

    def compose(self) -> ComposeResult:
        """Compose the status bar."""
        yield Static(
            f" {self._mode} ",
            classes="status-item status-mode",
            id="status-mode",
        )
        yield Static(" · ", classes="status-item status-separator")
        provider_text = (
            f"{self._provider}/{self._model}" if self._model else self._provider
        )
        yield Static(
            f" {provider_text} ",
            classes="status-item status-provider",
            id="status-provider",
        )
        yield Static(" · ", classes="status-item status-separator")
        yield Static("", classes="status-item status-activity", id="status-activity")
        yield Static("", classes="status-spacer")
        yield Static(
            " ○ " if not self._connected else " ● ",
            classes="status-item "
            + ("status-connection" if self._connected else "status-disconnected"),
            id="status-connection",
        )

    def set_mode(self, mode: str) -> None:
        """Update mode display."""
        self._mode = mode
        self.query_one("#status-mode", Static).update(f" {mode} ")

    def set_step(self, text: str) -> None:
        """Update step/activity display."""
        self._step_text = text
        activity = self.query_one("#status-activity", Static)
        activity.update(f" {text} " if text else "")

    def set_busy(self, busy: bool) -> None:
        """Show or hide the static 'working…' indicator."""
        if busy and not self._is_busy:
            self._is_busy = True
            self.query_one("#status-activity", Static).update(" working… ")
        elif not busy and self._is_busy:
            self._is_busy = False
            self.query_one("#status-activity", Static).update("")

    def set_context_usage(self, used: int, total: int) -> None:
        """Show context window utilization in the activity area."""
        pct = (used / total * 100) if total > 0 else 0
        color = "yellow" if pct > 80 else "dim"
        self.query_one("#status-activity", Static).update(
            f" [{color}]ctx {pct:.0f}%[/{color}] "
        )

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        self._connected = connected
        conn = self.query_one("#status-connection", Static)
        conn.update(" ● " if connected else " ○ ")
        conn.remove_class("status-connection", "status-disconnected")
        conn.add_class("status-connection" if connected else "status-disconnected")
