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

    Shows tool name with primary arg inline, result, and optional approval prompt.
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
        primary_arg = self._primary_arg()

        header = display_name
        if primary_arg:
            header = f"{display_name}  [dim]{primary_arg}[/dim]"

        yield Label(header, classes="tool-header")
        self._result_label = Label("  ... running", classes="tool-result")
        yield self._result_label

    def _primary_arg(self) -> str:
        """Extract the most informative argument for compact display."""
        if not self._arguments:
            return ""
        for key in _PRIMARY_ARG_KEYS:
            if key in self._arguments:
                val = str(self._arguments[key])
                if len(val) > 80:
                    val = val[:77] + "..."
                return val
        # Fallback: first argument value
        first_val = str(next(iter(self._arguments.values())))
        if len(first_val) > 80:
            first_val = first_val[:77] + "..."
        return first_val

    def set_result(self, summary: str, success: bool = True) -> None:
        """Set the tool result."""
        if self._result_label:
            display = summary[:200] if len(summary) > 200 else summary
            marker = "✓" if success else "✗"
            self._result_label.update(f"{marker} {display}")
            self._result_label.remove_class("tool-result", "tool-error", "tool-approval")
            self._result_label.add_class("tool-result" if success else "tool-error")

    def show_approval_prompt(self) -> None:
        """Show the approval prompt."""
        self._needs_approval = True
        if self._result_label:
            self._result_label.update("⋯ [y] approve  /  [n] deny")
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
                self._result_label.update("  ... executing")
                self._result_label.remove_class("tool-approval", "tool-error")
                self._result_label.add_class("tool-result")
            else:
                self._result_label.update("✗ denied by user")
                self._result_label.remove_class("tool-approval", "tool-result")
                self._result_label.add_class("tool-error")
