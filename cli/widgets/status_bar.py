"""Bottom status bar showing mode, provider, model, and step info."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class StatusBar(Horizontal):
    """Bottom status bar for the TUI.

    Shows: mode | provider/model | step info | connection status
    """

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    StatusBar .status-item {
        margin: 0 1;
        color: $text-muted;
    }
    StatusBar .status-mode {
        color: $primary;
        text-style: bold;
    }
    StatusBar .status-provider {
        color: $text;
    }
    StatusBar .status-step {
        color: $warning;
    }
    StatusBar .status-connection {
        color: $success;
    }
    StatusBar .status-disconnected {
        color: $error;
    }
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

    def compose(self) -> ComposeResult:
        """Compose the status bar."""
        yield Static(self._mode, classes="status-item status-mode", id="status-mode")
        provider_text = f"{self._provider}/{self._model}" if self._model else self._provider
        yield Static(provider_text, classes="status-item status-provider", id="status-provider")
        yield Static("", classes="status-item status-step", id="status-step")
        yield Static(
            "connected" if self._connected else "disconnected",
            classes=(
                "status-item "
                + ("status-connection" if self._connected else "status-disconnected")
            ),
            id="status-connection",
        )

    def set_mode(self, mode: str) -> None:
        """Update mode display."""
        self._mode = mode
        mode_widget = self.query_one("#status-mode", Static)
        mode_widget.update(mode)

    def set_step(self, text: str) -> None:
        """Update step display."""
        self._step_text = text
        step_widget = self.query_one("#status-step", Static)
        step_widget.update(text)

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        self._connected = connected
        conn_widget = self.query_one("#status-connection", Static)
        conn_widget.update("connected" if connected else "disconnected")
        conn_widget.remove_class("status-connection", "status-disconnected")
        conn_widget.add_class("status-connection" if connected else "status-disconnected")
