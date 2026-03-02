"""Model picker modal for selecting LLM models from the registry."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static


class ModelPickerModal(ModalScreen[str | None]):
    """Modal screen for selecting a model from the registry.

    Shows models grouped by provider with availability indicators.
    Returns the selected model string or None if cancelled.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    ModelPickerModal {
        align: center middle;
    }

    #model-picker-container {
        width: 60;
        max-height: 80%;
        border: tall $surface-lighten-2;
        background: $surface;
        padding: 1 2;
    }

    #model-picker-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .provider-header {
        text-style: bold;
        margin-top: 1;
        color: $text;
    }

    .provider-unavailable {
        color: $text-muted;
        text-style: italic;
    }

    .model-item {
        padding: 0 1;
    }

    .model-active {
        text-style: bold;
        color: $success;
    }

    #model-picker-hint {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    ListView {
        height: auto;
        max-height: 24;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem:hover {
        background: $panel;
    }
    """

    def __init__(
        self,
        providers: dict | None = None,
        active_model_id: str | None = None,
        local_files: list | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._providers = providers or {}
        self._active_model_id = active_model_id
        self._local_files = local_files or []

    def compose(self) -> ComposeResult:
        with Vertical(id="model-picker-container"):
            yield Static("Select Model", id="model-picker-title")
            yield VerticalScroll(id="model-picker-scroll")
            yield Static("[Enter] Select  [Esc] Cancel", id="model-picker-hint")

    async def on_mount(self) -> None:
        """Build the model list from provider data."""
        scroll = self.query_one("#model-picker-scroll", VerticalScroll)

        items: list[ListItem] = []
        for provider_name, info in self._providers.items():
            available = info.get("available", False)
            models = info.get("models", [])
            api_key_env = info.get("api_key_env", "")

            # Provider header
            if available or provider_name == "local":
                header_text = f"{provider_name.upper()}  [green]key set[/green]"
            else:
                header_text = f"{provider_name.upper()}  [dim]Set {api_key_env}[/dim]"

            items.append(ListItem(Label(header_text), disabled=True))

            if not models:
                items.append(
                    ListItem(Label("[dim]  No models[/dim]"), disabled=True)
                )
                continue

            if not available and provider_name != "local":
                items.append(
                    ListItem(
                        Label(f"[dim]  Set {api_key_env} to enable[/dim]"),
                        disabled=True,
                    )
                )
                continue

            for model in models:
                model_id = model.get("model_id", "")
                display = model.get("display_name", model_id)
                aliases = model.get("aliases", [])
                ctx = model.get("context_window", 0)

                alias = aliases[0] if aliases else model_id

                is_active = model_id == self._active_model_id
                marker = "[green]>[/green] " if is_active else "  "
                ctx_str = f"{ctx // 1024}k" if ctx >= 1024 else str(ctx)

                item_label = f"{marker}{display} [dim]({ctx_str})[/dim]"
                item = ListItem(Label(item_label))
                item._alias = alias
                items.append(item)

        # Add local GGUF files under LOCAL header
        if self._local_files:
            items.append(
                ListItem(Label("LOCAL  [green]scanned[/green]"), disabled=True)
            )
            for lf in self._local_files:
                name = lf.get("name", "unknown")
                size = lf.get("size_display", "")
                path = lf.get("path", "")
                size_str = f" [dim]({size})[/dim]" if size else ""
                item = ListItem(Label(f"  {name}{size_str}"))
                item._alias = f"local:{path}"
                items.append(item)

        list_view = ListView(*items, id="model-list")
        await scroll.mount(list_view)
        list_view.focus()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection."""
        alias = getattr(event.item, "_alias", None)
        if alias:
            self.dismiss(alias)

    def action_cancel(self) -> None:
        """Cancel model selection."""
        self.dismiss(None)
