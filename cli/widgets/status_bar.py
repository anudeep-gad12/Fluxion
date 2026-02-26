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
        yield Static("", classes="status-item status-context", id="status-context")
        yield Static(" · ", classes="status-item status-separator")
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
        """Show context window utilization (final, after run completes)."""
        self._update_context_display(used, total)

    def set_context_live(
        self, context_tokens: int, context_max: int, total_tokens_used: int
    ) -> None:
        """Update live context/token display during a run."""
        self._update_context_display(context_tokens, context_max, total_tokens_used)

    def _update_context_display(
        self, used: int, total: int, total_tokens_used: int = 0
    ) -> None:
        """Update the context info display."""
        if total <= 0:
            return
        pct = used / total * 100

        # Format token counts as compact strings (e.g. 12.5k, 250k)
        def _fmt(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.0f}k"
            return str(n)

        if pct > 80:
            color = "yellow"
        elif pct > 50:
            color = "dim"
        else:
            color = "dim"

        parts = f"[{color}]{_fmt(used)}/{_fmt(total)}[/{color}]"
        if total_tokens_used:
            parts += f" [dim]· {_fmt(total_tokens_used)} used[/dim]"

        try:
            self.query_one("#status-context", Static).update(f" {parts} ")
        except Exception:
            pass

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        self._connected = connected
        conn = self.query_one("#status-connection", Static)
        conn.update(" ● " if connected else " ○ ")
        conn.remove_class("status-connection", "status-disconnected")
        conn.add_class("status-connection" if connected else "status-disconnected")
