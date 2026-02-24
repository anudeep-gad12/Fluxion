"""Textual App subclass for the Reasoner CLI."""

from pathlib import Path

from textual.app import App

from .api_client import APIClient
from .config import CLIConfig
from .screens.chat_screen import ChatScreen


class ReasonerApp(App):
    """Reasoner CLI — Textual TUI coding assistant.

    A terminal-based coding assistant powered by the Reasoner agent engine.
    """

    TITLE = "Reasoner CLI"
    SUB_TITLE = "coding assistant"

    CSS_PATH = str(Path(__file__).parent / "css" / "app.tcss")

    BINDINGS = [
        ("ctrl+d", "quit", "Exit"),
    ]

    def __init__(self, config: CLIConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._api_client = APIClient(config)

    async def on_mount(self) -> None:
        """Mount the main chat screen."""
        screen = ChatScreen(
            config=self._config,
            api_client=self._api_client,
        )
        await self.push_screen(screen)

    async def on_unmount(self) -> None:
        """Clean up on exit."""
        await self._api_client.close()
