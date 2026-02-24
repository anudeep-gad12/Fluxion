"""Tool call display panel with optional approval prompt."""


from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label

# Tool name to icon mapping
_TOOL_ICONS = {
    "read_file": "[dim]>[/dim]",
    "write_file": "[bold yellow]W[/bold yellow]",
    "edit_file": "[bold cyan]E[/bold cyan]",
    "list_directory": "[dim]D[/dim]",
    "glob": "[dim]G[/dim]",
    "grep": "[dim]S[/dim]",
    "bash": "[bold red]$[/bold red]",
    "web_search": "[dim]?[/dim]",
    "web_extract": "[dim]@[/dim]",
    "python_execute": "[bold green]P[/bold green]",
}


class ToolCallPanel(Vertical):
    """Panel showing a tool call and its result.

    Shows tool name, arguments summary, result, and optional approval prompt.
    """

    DEFAULT_CSS = """
    ToolCallPanel {
        margin: 0 2;
        padding: 0 1;
        border: round $surface-lighten-2;
        height: auto;
        max-height: 15;
    }
    ToolCallPanel .tool-header {
        text-style: bold;
        color: $text;
    }
    ToolCallPanel .tool-args {
        color: $text-muted;
    }
    ToolCallPanel .tool-result {
        color: $success;
    }
    ToolCallPanel .tool-error {
        color: $error;
    }
    ToolCallPanel .tool-approval {
        color: $warning;
        text-style: bold;
    }
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
        self._result_label: Label | None = None

    def compose(self) -> ComposeResult:
        """Compose the tool call panel."""
        icon = _TOOL_ICONS.get(self._tool_name, "[dim]*[/dim]")
        args_summary = self._format_args()

        header = f"{icon} {self._tool_name}"
        if self._step_label:
            header = f"{self._step_label} {header}"

        yield Label(header, classes="tool-header")
        if args_summary:
            yield Label(args_summary, classes="tool-args")
        self._result_label = Label("", classes="tool-result")
        yield self._result_label

    def _format_args(self) -> str:
        """Format arguments for display."""
        if not self._arguments:
            return ""

        parts = []
        for key, value in self._arguments.items():
            if isinstance(value, str) and len(value) > 80:
                value = value[:77] + "..."
            parts.append(f"  {key}={value}")

        return "\n".join(parts[:5])

    def set_result(self, summary: str, success: bool = True) -> None:
        """Set the tool result.

        Args:
            summary: Result summary text.
            success: Whether the tool succeeded.
        """
        if self._result_label:
            self._result_label.update(summary)
            self._result_label.remove_class("tool-result", "tool-error")
            self._result_label.add_class("tool-result" if success else "tool-error")

    def show_approval_prompt(self) -> None:
        """Show the approval prompt."""
        self._needs_approval = True
        if self._result_label:
            self._result_label.update("[y] approve / [n] deny")
            self._result_label.remove_class("tool-result", "tool-error")
            self._result_label.add_class("tool-approval")

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
        if self._result_label:
            if approved:
                self._result_label.update("Approved - executing...")
                self._result_label.remove_class("tool-approval", "tool-error")
                self._result_label.add_class("tool-result")
            else:
                self._result_label.update("Denied by user")
                self._result_label.remove_class("tool-approval", "tool-result")
                self._result_label.add_class("tool-error")
