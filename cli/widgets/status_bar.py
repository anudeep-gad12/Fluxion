"""Bottom status bar showing mode, provider, model, and step info."""

import random

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widgets import Static

_THINKING_PHRASES = [
    "thinking...",
    "pondering...",
    "brewing ideas...",
    "connecting dots...",
    "crunching...",
    "reasoning...",
    "cooking up...",
    "digging in...",
    "on it...",
    "working...",
    "processing...",
    "analyzing...",
    "contemplating...",
    "computing...",
    "figuring out...",
    "brainstorming...",
    "sifting through...",
    "wrapping head...",
    "assembling...",
    "piecing together...",
]


class StatusBar(Horizontal):
    """Bottom status bar for the TUI.

    Shows: mode | provider/model | activity | connection status.
    Cycling activity phrases while agent is running.
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
        self._phrase_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Compose the status bar."""
        yield Static(
            f" {self._mode} ",
            classes="status-item status-mode",
            id="status-mode",
        )
        provider_text = (
            f"{self._provider}/{self._model}" if self._model else self._provider
        )
        yield Static(
            f" {provider_text} ",
            classes="status-item status-provider",
            id="status-provider",
        )
        yield Static("", classes="status-item status-activity", id="status-activity")
        yield Static(
            " connected " if self._connected else " disconnected ",
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
        """Start or stop the cycling activity phrases."""
        if busy and not self._is_busy:
            self._is_busy = True
            self._cycle_phrase()
            self._phrase_timer = self.set_interval(2.0, self._cycle_phrase)
        elif not busy and self._is_busy:
            self._is_busy = False
            if self._phrase_timer:
                self._phrase_timer.stop()
                self._phrase_timer = None
            self.query_one("#status-activity", Static).update("")

    def _cycle_phrase(self) -> None:
        """Pick a random thinking phrase."""
        phrase = random.choice(_THINKING_PHRASES)
        self.query_one("#status-activity", Static).update(f" {phrase} ")

    def set_connected(self, connected: bool) -> None:
        """Update connection status."""
        self._connected = connected
        conn = self.query_one("#status-connection", Static)
        conn.update(" connected " if connected else " disconnected ")
        conn.remove_class("status-connection", "status-disconnected")
        conn.add_class("status-connection" if connected else "status-disconnected")
