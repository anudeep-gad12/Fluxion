"""Tool call display panel with optional approval prompt."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

# Tool name to display name mapping
_TOOL_ICONS = {
    "read_file": "Read",
    "write_file": "Write",
    "edit_file": "Edit",
    "list_directory": "List",
    "glob": "Glob",
    "grep": "Grep",
    "bash": "Bash",
    "web_search": "Search",
    "web_extract": "Extract",
    "python_execute": "Python",
}

# Keys to extract as the primary argument for compact display
_PRIMARY_ARG_KEYS = [
    "path", "file_path", "filepath",
    "command", "cmd",
    "query", "search", "q",
    "pattern", "glob", "regex",
    "url",
    "directory", "dir",
]


class ToolCallPanel(Vertical):
    """Panel showing a tool call and its result.

    Renders as:
        ⏺ Tool(primary_arg)
          ⎿  ✓ result summary
    """

    class ApprovalResponse(Message):
        """User responded to approval prompt."""

        def __init__(self, run_id: str, tool_call_id: str, approved: bool) -> None:
            super().__init__()
            self.run_id = run_id
            self.tool_call_id = tool_call_id
            self.approved = approved

    def __init__(
        self,
        tool_name: str,
        arguments: dict,
        step_label: str = "",
        run_id: str = "",
        tool_call_id: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._arguments = arguments
        self._step_label = step_label
        self._run_id = run_id
        self._tool_call_id = tool_call_id
        self._needs_approval = False
        self._result_widget: Static | None = None

    def compose(self) -> ComposeResult:
        """Compose the tool call panel."""
        display_name = _TOOL_ICONS.get(self._tool_name, self._tool_name)
        primary_arg = self._primary_arg()

        if primary_arg:
            header = f"[bold $primary]⏺[/bold $primary] {display_name}([dim]{primary_arg}[/dim])"
        else:
            header = f"[bold $primary]⏺[/bold $primary] {display_name}()"

        yield Static(header, classes="tool-header")
        self._result_widget = Static("  ⎿  [dim]Running…[/dim]", classes="tool-result")
        yield self._result_widget

    def _primary_arg(self) -> str:
        """Extract the most informative argument for compact display."""
        if not self._arguments:
            return ""
        for key in _PRIMARY_ARG_KEYS:
            if key in self._arguments:
                val = str(self._arguments[key])
                if len(val) > 60:
                    val = val[:57] + "..."
                return val
        # Fallback: first argument value
        first_val = str(next(iter(self._arguments.values())))
        if len(first_val) > 60:
            first_val = first_val[:57] + "..."
        return first_val

    def set_result(self, summary: str, success: bool = True) -> None:
        """Set the tool result."""
        if self._result_widget:
            display = summary[:120] if len(summary) > 120 else summary
            if success:
                self._result_widget.update(f"  ⎿  [green]✓ {display}[/green]")
                self._result_widget.remove_class("tool-error", "tool-approval")
                self._result_widget.add_class("tool-result")
            else:
                self._result_widget.update(f"  ⎿  [red]✗ {display}[/red]")
                self._result_widget.remove_class("tool-result", "tool-approval")
                self._result_widget.add_class("tool-error")

    def show_approval_prompt(self) -> None:
        """Show the approval prompt."""
        self._needs_approval = True
        if self._result_widget:
            self._result_widget.update(
                "  ⎿  [bold yellow]Allow? [y] approve · [n] deny[/bold yellow]"
            )
            self._result_widget.remove_class("tool-result", "tool-error")
            self._result_widget.add_class("tool-approval")

    @property
    def needs_approval(self) -> bool:
        """Whether this panel is waiting for approval."""
        return self._needs_approval

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def tool_call_id(self) -> str:
        return self._tool_call_id

    def resolve_approval(self, approved: bool) -> None:
        """Mark approval as resolved."""
        self._needs_approval = False
        if self._result_widget:
            if approved:
                self._result_widget.update("  ⎿  [dim]Running…[/dim]")
                self._result_widget.remove_class("tool-approval", "tool-error")
                self._result_widget.add_class("tool-result")
            else:
                self._result_widget.update("  ⎿  [red]✗ Denied[/red]")
                self._result_widget.remove_class("tool-approval", "tool-result")
                self._result_widget.add_class("tool-error")
