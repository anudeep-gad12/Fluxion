"""Tool call display panel with optional approval prompt and click-to-expand."""

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

    Click the header to expand/collapse full arguments.

    Collapsed: ▸ Tool(primary_arg)
    Expanded:  ▾ Tool
                 key: value
                 key: value
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
        diff_preview: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._arguments = arguments
        self._step_label = step_label
        self._run_id = run_id
        self._tool_call_id = tool_call_id
        self._diff_preview = diff_preview
        self._needs_approval = False
        self._expanded = False
        self._result_widget: Static | None = None
        self._header_widget: Static | None = None
        self._details_widget: Static | None = None
        self._result_text = ""
        self._result_success = True

    def compose(self) -> ComposeResult:
        """Compose the tool call panel."""
        header = self._build_header_text()
        self._header_widget = Static(header, classes="tool-header")
        yield self._header_widget
        self._details_widget = Static("", classes="tool-details")
        yield self._details_widget
        self._result_widget = Static("  ⎿  [dim]Running…[/dim]", classes="tool-result")
        yield self._result_widget

    def _build_header_text(self) -> str:
        """Build the header text with expand/collapse indicator."""
        display_name = _TOOL_ICONS.get(self._tool_name, self._tool_name)
        if self._expanded:
            return f"[bold $primary]▾[/bold $primary] {display_name}"
        else:
            primary_arg = self._primary_arg()
            if primary_arg:
                return f"[bold $primary]▸[/bold $primary] {display_name}([dim]{primary_arg}[/dim])"
            else:
                return f"[bold $primary]▸[/bold $primary] {display_name}()"

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

    def get_full_arguments_display(self) -> str:
        """Return formatted full arguments for display.

        Used by the input area approval flow and expanded view.
        For write_file with a diff preview, shows the diff instead of raw content.
        """
        display_name = _TOOL_ICONS.get(self._tool_name, self._tool_name)
        lines = [f"⏺ {display_name} — approve this tool call?\n"]
        if not self._arguments:
            lines.append("  (no arguments)")
            return "\n".join(lines)

        # For write_file with diff preview, show diff instead of raw content
        if self._tool_name == "write_file" and self._diff_preview:
            file_path = self._arguments.get("file_path", "")
            lines.append(f"file_path: {file_path}\n")
            lines.append("changes:")
            for dline in self._diff_preview.split("\n"):
                lines.append(f"  {dline}")
            return "\n".join(lines)

        for key, value in self._arguments.items():
            val_str = str(value)
            if "\n" in val_str:
                lines.append(f"{key}:")
                for vline in val_str.split("\n"):
                    lines.append(f"  {vline}")
            else:
                lines.append(f"{key}: {val_str}")
        return "\n".join(lines)

    def _get_details_markup(self) -> str:
        """Return Rich markup for the details section."""
        if not self._arguments:
            return "  [dim](no arguments)[/dim]"
        lines = []
        for key, value in self._arguments.items():
            val_str = str(value)
            if "\n" in val_str:
                lines.append(f"  [dim]{key}:[/dim]")
                for vline in val_str.split("\n"):
                    lines.append(f"    {vline}")
            else:
                lines.append(f"  [dim]{key}:[/dim] {val_str}")
        return "\n".join(lines)

    def on_click(self) -> None:
        """Toggle expanded/collapsed state on click."""
        self._expanded = not self._expanded
        if self._expanded:
            self.add_class("expanded")
            if self._header_widget:
                self._header_widget.update(self._build_header_text())
            if self._details_widget:
                self._details_widget.update(self._get_details_markup())
            # Show full result when expanded
            if self._result_widget and self._result_text:
                self._update_result_display(self._result_text, self._result_success)
        else:
            self.remove_class("expanded")
            if self._header_widget:
                self._header_widget.update(self._build_header_text())
            if self._details_widget:
                self._details_widget.update("")
            # Truncate result when collapsed
            if self._result_widget and self._result_text:
                self._update_result_display(self._result_text, self._result_success)

    def _update_result_display(self, summary: str, success: bool) -> None:
        """Update result widget with appropriate truncation."""
        if not self._result_widget:
            return
        display = summary if self._expanded else (summary[:120] if len(summary) > 120 else summary)
        if success:
            self._result_widget.update(f"  ⎿  [green]✓ {display}[/green]")
        else:
            self._result_widget.update(f"  ⎿  [red]✗ {display}[/red]")

    def set_result(self, summary: str, success: bool = True) -> None:
        """Set the tool result."""
        self._result_text = summary
        self._result_success = success
        if self._result_widget:
            self._update_result_display(summary, success)
            if success:
                self._result_widget.remove_class("tool-error", "tool-approval")
                self._result_widget.add_class("tool-result")
            else:
                self._result_widget.remove_class("tool-result", "tool-approval")
                self._result_widget.add_class("tool-error")

    def show_approval_prompt(self) -> None:
        """Show the approval prompt."""
        self._needs_approval = True
        if self._result_widget:
            self._result_widget.update(
                "  ⎿  [bold yellow]Allow? Enter approve · [n] deny[/bold yellow]"
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
