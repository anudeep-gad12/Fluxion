"""Tool call display panel with optional approval prompt."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label

# Tool name to icon mapping
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


class ToolCallPanel(Vertical):
    """Panel showing a tool call and its result.

    Shows tool name, arguments summary, result, and optional approval prompt.
    Styling is handled by the app.tcss file.
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
        display_name = _TOOL_ICONS.get(self._tool_name, self._tool_name)
        args_summary = self._format_args()

        header = f"{display_name}"
        if self._step_label:
            header = f"[dim]{self._step_label}[/dim]  {header}"

        yield Label(header, classes="tool-header")
        if args_summary:
            yield Label(args_summary, classes="tool-args")
        self._result_label = Label("running...", classes="tool-result")
        yield self._result_label

    def _format_args(self) -> str:
        """Format arguments for display."""
        if not self._arguments:
            return ""

        parts = []
        for key, value in self._arguments.items():
            val_str = str(value)
            if len(val_str) > 80:
                val_str = val_str[:77] + "..."
            parts.append(f"  {key}={val_str}")

        return "\n".join(parts[:5])

    def set_result(self, summary: str, success: bool = True) -> None:
        """Set the tool result."""
        if self._result_label:
            display = summary[:200] if len(summary) > 200 else summary
            self._result_label.update(display)
            self._result_label.remove_class("tool-result", "tool-error", "tool-approval")
            self._result_label.add_class("tool-result" if success else "tool-error")

    def show_approval_prompt(self) -> None:
        """Show the approval prompt."""
        self._needs_approval = True
        if self._result_label:
            self._result_label.update("[y] approve  /  [n] deny")
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
