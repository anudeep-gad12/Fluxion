"""Bottom status bar — Claude Code style."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusBar(Horizontal):
    """Bottom status bar for the TUI.

    Layout: ▸▸ mode · provider/model · activity     tokens · context
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
        provider_text = (
            f"{self._provider}/{self._model}" if self._model else self._provider
        )
        yield Static(
            f"▸▸ {self._mode} · {provider_text}",
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
        yield Static(
            "esc stop · ctrl+n new · ctrl+m model",
            classes="status-item status-hints",
            id="status-hints",
        )

    def _refresh_provider_text(self) -> None:
        """Refresh the combined mode/provider display."""
        provider_text = (
            f"{self._provider}/{self._model}" if self._model else self._provider
        )
        self.query_one("#status-provider", Static).update(
            f"▸▸ {self._mode} · {provider_text}"
        )

    def set_mode(self, mode: str) -> None:
        """Update mode display."""
        self._mode = mode
        self._refresh_provider_text()

    def set_provider(self, provider: str) -> None:
        """Update provider display."""
        self._provider = provider
        self._refresh_provider_text()

    def set_model(self, model_name: str) -> None:
        """Update model display name."""
        self._model = model_name
        self._refresh_provider_text()

    def set_step(self, text: str) -> None:
        """Update step/activity display."""
        self._step_text = text
        sep = self.query_one("#sep-2", Static)
        activity = self.query_one("#status-activity", Static)
        if text:
            sep.update(" · ")
            activity.update(text)
        else:
            sep.update("")
            activity.update("")

    def set_busy(self, busy: bool) -> None:
        """Show or hide the static 'working...' indicator."""
        if busy and not self._is_busy:
            self._is_busy = True
            self.query_one("#sep-2", Static).update(" · ")
            self.query_one("#status-activity", Static).update("working…")
        elif not busy and self._is_busy:
            self._is_busy = False
            self.query_one("#sep-2", Static).update("")
            self.query_one("#status-activity", Static).update("")

    def set_context_usage(self, used: int, total: int) -> None:
        """Show context window utilization."""
        self._update_context_display(used, total)

    def set_context_live(
        self, context_tokens: int, context_max: int, total_tokens_used: int
    ) -> None:
        """Update live context/token display during a run."""
        self._update_context_display(context_tokens, context_max)

    def _update_context_display(self, used: int, total: int) -> None:
        """Update the context info display."""
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

        text = f"[{color}]{_fmt(used)} tokens · ctx {int(pct)}%[/{color}]"

        try:
            self.query_one("#status-context", Static).update(text)
        except Exception:
            pass

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        self._connected = connected
