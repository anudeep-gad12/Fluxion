"""Textual App subclass for the Reasoner CLI."""

from textual.app import App
from textual.theme import Theme

from .api_client import APIClient
from .config import CLIConfig
from .screens.chat_screen import ChatScreen

# Monochrome-plus-two: zinc base with functional accent colors
REASONER_THEME = Theme(
    name="reasoner",
    primary="#60a5fa",       # blue-400 — tools, accents, focus
    secondary="#a1a1aa",     # zinc-400
    accent="#60a5fa",        # blue-400 — links, interactive
    warning="#d97706",       # amber-600 — approval prompts
    error="#f87171",         # red-400 — errors
    success="#4ade80",       # green-400 — tool success
    background="#09090b",    # zinc-950
    surface="#18181b",       # zinc-900 — card backgrounds
    panel="#27272a",         # zinc-800 — raised panels
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
