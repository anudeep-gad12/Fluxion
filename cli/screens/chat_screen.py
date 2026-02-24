"""Main chat/agent screen — the primary interaction surface."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..api_client import APIClient
from ..config import CLIConfig
from ..events import (
    AgentCompleteEvent,
    AgentErrorEvent,
    AgentStateEvent,
    AnswerTokenEvent,
    HeartbeatEvent,
    StepStartEvent,
    ThinkingEvent,
    ToolApprovalRequiredEvent,
    ToolResultEvent,
    ToolStartEvent,
)
from ..widgets.agent_progress import AgentProgress
from ..widgets.input_area import InputArea
from ..widgets.message_bubble import MessageBubble
from ..widgets.message_list import MessageList
from ..widgets.status_bar import StatusBar
from ..widgets.streaming_markdown import StreamingMarkdown
from ..widgets.thinking_panel import ThinkingPanel
from ..widgets.tool_call_panel import ToolCallPanel


class ChatScreen(Screen):
    """Main chat screen with message list, input area, and status bar."""

    BINDINGS = [
        Binding("escape", "cancel_run", "Stop", show=True),
        Binding("ctrl+n", "new_conversation", "New", show=True),
        Binding("y", "approve_tool", "Approve", show=False),
        Binding("n", "deny_tool", "Deny", show=False),
    ]

    def __init__(
        self,
        config: CLIConfig,
        api_client: APIClient,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._api_client = api_client
        self._current_run_id: str | None = None
        self._current_stream_token: str | None = None
        self._conversation_id: str | None = None
        self._streaming_md: StreamingMarkdown | None = None
        self._pending_approval: ToolCallPanel | None = None
        self._is_running = False

    def compose(self) -> ComposeResult:
        """Compose the chat screen layout."""
        yield Header(show_clock=False)
        yield AgentProgress(id="agent-progress")
        yield MessageList(id="message-list")
        with Vertical(id="input-container"):
            yield InputArea(id="input-area")
            yield Static(
                "Enter to send · Shift+Enter newline · Esc stop · Ctrl+C exit",
                id="input-hint",
            )
        yield StatusBar(
            mode=self._config.mode,
            provider=self._config.provider,
            model=self._config.model or "",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Check backend connection and show welcome on mount."""
        connected = await self._api_client.health_check()
        status_bar = self.query_one(StatusBar)
        status_bar.set_connected(connected)

        if not connected:
            self._add_system_message(
                f"Cannot connect to backend at {self._config.api_url}. "
                "Start the server with `just dev` or `./dev.sh start`."
            )
        else:
            # Show welcome message
            message_list = self.query_one(MessageList)
            welcome = Static(id="welcome")
            welcome.update(
                "[bold #a78bfa]Reasoner CLI[/bold #a78bfa]\n\n"
                f"Mode: [bold]{self._config.mode}[/bold]  ·  "
                f"Provider: [bold]{self._config.provider}[/bold]\n"
                "Working dir: "
                f"[dim]{self._config.working_dir}[/dim]\n\n"
                "[dim]Ask me anything. I can read, write, and search "
                "your codebase.[/dim]"
            )
            message_list.mount(welcome)

        # Focus input
        self.query_one(InputArea).focus()

    async def on_input_area_submitted(self, event: InputArea.Submitted) -> None:
        """Handle user message submission."""
        if self._is_running:
            return

        query = event.value
        if not query:
            return

        # Remove welcome message if present
        try:
            welcome = self.query_one("#welcome")
            welcome.remove()
        except Exception:
            pass

        # Add user message
        message_list = self.query_one(MessageList)
        message_list.mount(MessageBubble("user", query))
        message_list.scroll_to_bottom()

        # Start agent run
        await self._start_run(query)

    async def _start_run(self, query: str) -> None:
        """Start an agent run and begin streaming events."""
        self._is_running = True

        try:
            result = await self._api_client.create_agent_run(
                query=query,
                conversation_id=self._conversation_id,
            )

            self._current_run_id = result["run_id"]
            self._current_stream_token = result.get("stream_token", "")

            # Add assistant label before streaming content
            message_list = self.query_one(MessageList)
            message_list.mount(
                MessageBubble("assistant", ""),
            )

            # Create streaming markdown for the response
            self._streaming_md = StreamingMarkdown()
            message_list.mount(self._streaming_md)

            # Start SSE consumer as a worker
            self.run_worker(self._consume_events(), exclusive=True)

        except Exception as exc:
            self._is_running = False
            self._add_system_message(f"Error: {exc}")

    async def _consume_events(self) -> None:
        """Consume SSE events and update the UI."""
        if not self._current_run_id or not self._current_stream_token:
            return

        try:
            async for event in self._api_client.stream_agent_events(
                self._current_run_id, self._current_stream_token
            ):
                event_type = event.get("event", "")
                data = event.get("data", {})

                if event_type == "step_start":
                    self.post_message(StepStartEvent(data))
                elif event_type == "thinking":
                    self.post_message(ThinkingEvent(data))
                elif event_type == "tool_start":
                    self.post_message(ToolStartEvent(data))
                elif event_type == "tool_approval_required":
                    self.post_message(ToolApprovalRequiredEvent(data))
                elif event_type == "tool_result":
                    self.post_message(ToolResultEvent(data))
                elif event_type == "answer":
                    self.post_message(AnswerTokenEvent(data))
                elif event_type == "complete":
                    self.post_message(AgentCompleteEvent(data))
                    break
                elif event_type == "error":
                    self.post_message(AgentErrorEvent(data))
                    break
                elif event_type == "agent_state":
                    self.post_message(AgentStateEvent(data))
                elif event_type == "heartbeat":
                    self.post_message(HeartbeatEvent(data))
                elif event_type == "cancelled":
                    break

        except Exception as exc:
            self.post_message(AgentErrorEvent({"error": str(exc)}))

    def on_step_start_event(self, event: StepStartEvent) -> None:
        """Handle step start."""
        step = event.data.get("step_number", 0)
        max_steps = event.data.get("max_steps", 0)
        progress = self.query_one(AgentProgress)
        progress.update_step(step, max_steps)

        status_bar = self.query_one(StatusBar)
        if max_steps:
            status_bar.set_step(f"Step {step}/{max_steps}")
        else:
            status_bar.set_step(f"Step {step}")

    def on_thinking_event(self, event: ThinkingEvent) -> None:
        """Handle thinking token."""
        content = event.data.get("content", "")
        if not content:
            return

        # Find or create thinking panel
        message_list = self.query_one(MessageList)
        thinking_panels = message_list.query(ThinkingPanel)
        if thinking_panels:
            panel = thinking_panels.last()
        else:
            panel = ThinkingPanel()
            message_list.mount(panel)

        panel.append_token(content)

    def on_tool_start_event(self, event: ToolStartEvent) -> None:
        """Handle tool start."""
        tool_name = event.data.get("tool_name", "unknown")
        arguments = event.data.get("arguments", {})
        tool_call_id = event.data.get("tool_call_id", "")
        step = self.query_one(AgentProgress)._current_step

        panel = ToolCallPanel(
            tool_name=tool_name,
            arguments=arguments,
            step_label=f"Step {step}" if step else "",
            run_id=self._current_run_id or "",
            tool_call_id=tool_call_id,
            id=f"tool-{tool_call_id}" if tool_call_id else None,
        )

        message_list = self.query_one(MessageList)
        message_list.mount(panel)
        message_list.scroll_to_bottom()

    def on_tool_approval_required_event(
        self, event: ToolApprovalRequiredEvent
    ) -> None:
        """Handle tool approval request."""
        tool_call_id = event.data.get("tool_call_id", "")

        try:
            panel = self.query_one(f"#tool-{tool_call_id}", ToolCallPanel)
            panel.show_approval_prompt()
            self._pending_approval = panel
        except Exception:
            pass

        message_list = self.query_one(MessageList)
        message_list.scroll_to_bottom()

    def on_tool_result_event(self, event: ToolResultEvent) -> None:
        """Handle tool result."""
        tool_call_id = event.data.get("tool_call_id", "")
        result_summary = event.data.get("result_summary", "")
        success = event.data.get("success", True)

        try:
            panel = self.query_one(f"#tool-{tool_call_id}", ToolCallPanel)
            panel.set_result(result_summary, success)
        except Exception:
            pass

        message_list = self.query_one(MessageList)
        message_list.scroll_to_bottom()

    def on_answer_token_event(self, event: AnswerTokenEvent) -> None:
        """Handle answer token (streaming response)."""
        # Backend emits "content" field, not "token"
        content = event.data.get("content", "")
        if content and self._streaming_md:
            self._streaming_md.append_token(content)
            message_list = self.query_one(MessageList)
            message_list.scroll_to_bottom()

    def on_agent_complete_event(self, event: AgentCompleteEvent) -> None:
        """Handle agent completion."""
        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None

        progress = self.query_one(AgentProgress)
        progress.reset()

        status_bar = self.query_one(StatusBar)
        status_bar.set_step("")

        # Re-focus input
        self.query_one(InputArea).focus()

    def on_agent_error_event(self, event: AgentErrorEvent) -> None:
        """Handle agent error."""
        error = event.data.get("error", "Unknown error")
        self._add_system_message(f"Error: {error}")

        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None

        progress = self.query_one(AgentProgress)
        progress.reset()

        status_bar = self.query_one(StatusBar)
        status_bar.set_step("")

        self.query_one(InputArea).focus()

    def on_agent_state_event(self, event: AgentStateEvent) -> None:
        """Handle agent state change."""
        state = event.data.get("state", "")
        if state:
            status_bar = self.query_one(StatusBar)
            status_bar.set_step(state)

    async def action_approve_tool(self) -> None:
        """Approve the pending tool call."""
        if self._pending_approval and self._current_run_id:
            panel = self._pending_approval
            self._pending_approval = None
            panel.resolve_approval(True)
            try:
                await self._api_client.approve_tool(
                    panel.run_id, panel.tool_call_id
                )
            except Exception as exc:
                self._add_system_message(f"Approval failed: {exc}")

    async def action_deny_tool(self) -> None:
        """Deny the pending tool call."""
        if self._pending_approval and self._current_run_id:
            panel = self._pending_approval
            self._pending_approval = None
            panel.resolve_approval(False)
            try:
                await self._api_client.deny_tool(
                    panel.run_id, panel.tool_call_id
                )
            except Exception as exc:
                self._add_system_message(f"Denial failed: {exc}")

    async def action_cancel_run(self) -> None:
        """Cancel the current agent run (Esc key)."""
        if not self._is_running or not self._current_run_id:
            return

        try:
            await self._api_client.cancel_run(self._current_run_id)
            self._add_system_message("Run cancelled.")
        except Exception as exc:
            self._add_system_message(f"Cancel failed: {exc}")

        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None

        progress = self.query_one(AgentProgress)
        progress.reset()

        status_bar = self.query_one(StatusBar)
        status_bar.set_step("")

        self.query_one(InputArea).focus()

    def action_new_conversation(self) -> None:
        """Start a new conversation."""
        self._conversation_id = None
        message_list = self.query_one(MessageList)
        message_list.remove_children()
        self._add_system_message("New conversation started.")
        self.query_one(InputArea).focus()

    def _add_system_message(self, text: str) -> None:
        """Add a system/info message to the message list."""
        message_list = self.query_one(MessageList)
        message_list.mount(MessageBubble("assistant", f"*{text}*"))
        message_list.scroll_to_bottom()
