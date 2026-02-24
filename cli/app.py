"""Textual App subclass for the Reasoner CLI."""

from textual.app import App
from textual.theme import Theme

from .api_client import APIClient
from .config import CLIConfig
from .screens.chat_screen import ChatScreen

# Monochrome zinc theme matching the web UI's austere aesthetic
REASONER_THEME = Theme(
    name="reasoner",
    primary="#e4e4e7",       # zinc-200
    secondary="#a1a1aa",     # zinc-400
    accent="#d4d4d8",        # zinc-300
    warning="#a1a1aa",       # zinc-400
    error="#f87171",         # red-400 (only color used)
    success="#a1a1aa",       # zinc-400
    background="#0a0a0b",    # Near-black with slight blue tint
    surface="#0f0f11",       # Neutral dark
    panel="#18181b",         # zinc-900
)


class ReasonerApp(App):
    """Reasoner CLI — Textual TUI coding assistant."""

    CSS_PATH = "css/app.tcss"

    BINDINGS = [
        ("ctrl+c", "quit", "Exit"),
        ("ctrl+d", "quit", "Exit"),
    ]

    def __init__(self, config: CLIConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._api_client = APIClient(config)

    def on_mount(self) -> None:
        """Register custom theme and push main screen."""
        self.register_theme(REASONER_THEME)
        self.theme = "reasoner"
        mode = self._config.mode
        provider = self._config.provider
        model = self._config.model
        title_parts = [f"Reasoner [{mode}]"]
        if provider and provider != "default":
            label = f"{provider}/{model}" if model else provider
            title_parts.append(label)
        self.title = "  ".join(title_parts)

    async def on_ready(self) -> None:
        """Push the chat screen after app is ready."""
        screen = ChatScreen(
            config=self._config,
            api_client=self._api_client,
        )
        await self.push_screen(screen)

    async def action_quit(self) -> None:
        """Clean up and exit."""
        await self._api_client.close()
        self.exit()
