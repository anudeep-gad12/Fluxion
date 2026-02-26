"""Bottom status bar showing mode, provider, tokens, and connection."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusBar(Horizontal):
    """Bottom status bar for the TUI.

    Layout: ● mode · provider · activity    tokens_used · context_pct
    All items in one line, right-aligned token info via spacer.
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
            " ○ " if not self._connected else " ● ",
            classes="status-item "
            + ("status-connection" if self._connected else "status-disconnected"),
            id="status-connection",
        )
        yield Static(
            f" {self._mode} ",
            classes="status-item status-mode",
            id="status-mode",
        )
        yield Static(" · ", classes="status-item status-separator", id="sep-1")
        provider_text = (
            f"{self._provider}/{self._model}" if self._model else self._provider
        )
        yield Static(
            f" {provider_text} ",
            classes="status-item status-provider",
            id="status-provider",
        )
        yield Static(
            "",
            classes="status-item status-separator",
            id="sep-2",
        )
        yield Static("", classes="status-item status-activity", id="status-activity")
        yield Static("", classes="status-spacer")
        yield Static("", classes="status-item status-context", id="status-context")

    def set_mode(self, mode: str) -> None:
        """Update mode display."""
        self._mode = mode
        self.query_one("#status-mode", Static).update(f" {mode} ")

    def set_provider(self, provider: str) -> None:
        """Update provider display."""
        self._provider = provider
        provider_text = (
            f"{self._provider}/{self._model}" if self._model else self._provider
        )
        self.query_one("#status-provider", Static).update(f" {provider_text} ")

    def set_step(self, text: str) -> None:
        """Update step/activity display."""
        self._step_text = text
        sep = self.query_one("#sep-2", Static)
        activity = self.query_one("#status-activity", Static)
        if text:
            sep.update(" · ")
            activity.update(f" {text} ")
        else:
            sep.update("")
            activity.update("")

    def set_busy(self, busy: bool) -> None:
        """Show or hide the static 'working...' indicator."""
        if busy and not self._is_busy:
            self._is_busy = True
            self.query_one("#sep-2", Static).update(" · ")
            self.query_one("#status-activity", Static).update(" working… ")
        elif not busy and self._is_busy:
            self._is_busy = False
            self.query_one("#sep-2", Static).update("")
            self.query_one("#status-activity", Static).update("")

    def set_context_usage(self, used: int, total: int) -> None:
        """Show context window utilization (final, after run completes).

        Args:
            used: Current context window tokens (system+history+query).
            total: Max context window size.
        """
        self._update_context_display(used, total)

    def set_context_live(
        self, context_tokens: int, context_max: int, total_tokens_used: int
    ) -> None:
        """Update live context/token display during a run.

        Args:
            context_tokens: Current context window fill (tokens in messages).
            context_max: Max context window size.
            total_tokens_used: Ignored (cumulative API billing, not useful to show).
        """
        self._update_context_display(context_tokens, context_max)

    def _update_context_display(self, used: int, total: int) -> None:
        """Update the context info display.

        Shows context window fill as percentage, e.g. "ctx 15% (14.8k)".
        """
        if total <= 0:
            return

        def _fmt(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.1f}k"
            return str(n)

        pct = used / total * 100
        if pct > 80:
            color = "yellow"
        else:
            color = "dim"

        text = f"[{color}]ctx {int(pct)}% ({_fmt(used)})[/{color}]"

        try:
            self.query_one("#status-context", Static).update(f" {text} ")
        except Exception:
            pass

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        self._connected = connected
        conn = self.query_one("#status-connection", Static)
        conn.update(" ● " if connected else " ○ ")
        conn.remove_class("status-connection", "status-disconnected")
        conn.add_class("status-connection" if connected else "status-disconnected")
