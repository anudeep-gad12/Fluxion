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
        self._current_step = 0

    def compose(self) -> ComposeResult:
        """Compose the chat screen layout."""
        yield Header(show_clock=False)
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
                "[bold]reasoner[/bold]\n"
                f"  mode     [bold]{self._config.mode}[/bold]\n"
                f"  provider [bold]{self._config.provider}[/bold]\n"
                f"  cwd      [dim]{self._config.working_dir}[/dim]\n\n"
                "[dim]Type a message to begin.[/dim]"
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

        # Handle slash commands
        if query.startswith("/"):
            await self._handle_slash_command(query)
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
        self._current_step = 0
        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(True)

        try:
            result = await self._api_client.create_agent_run(
                query=query,
                conversation_id=self._conversation_id,
            )

            self._current_run_id = result["run_id"]
            self._current_stream_token = result.get("stream_token", "")

            # Track conversation for message history
            if not self._conversation_id:
                self._conversation_id = result.get("conversation_id")

            # Add assistant bubble and mount streaming markdown inside it
            message_list = self.query_one(MessageList)
            bubble = MessageBubble("assistant", "")
            message_list.mount(bubble)

            self._streaming_md = StreamingMarkdown()
            bubble.mount(self._streaming_md)

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
        """Handle step start — update status bar only."""
        step = event.data.get("step_number", 0)
        max_steps = event.data.get("max_steps", 0)
        self._current_step = step

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

        panel = ToolCallPanel(
            tool_name=tool_name,
            arguments=arguments,
            step_label=f"Step {self._current_step}" if self._current_step else "",
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

        self._show_approval_bindings()
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
        self._current_step = 0
        self._hide_approval_bindings()

        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(False)
        status_bar.set_step("")

        # Show context usage if available
        ctx = event.data.get("context_usage")
        if ctx and ctx.get("max_tokens"):
            status_bar.set_context_usage(
                ctx["total_tokens_used"], ctx["max_tokens"]
            )

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
        self._current_step = 0
        self._hide_approval_bindings()

        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(False)
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
            self._hide_approval_bindings()
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
            self._hide_approval_bindings()
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
        self._current_step = 0

        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(False)
        status_bar.set_step("")

        self.query_one(InputArea).focus()

    def action_new_conversation(self) -> None:
        """Start a new conversation."""
        self._conversation_id = None
        message_list = self.query_one(MessageList)
        message_list.remove_children()
        self._add_system_message("New conversation started.")
        self.query_one(InputArea).focus()

    async def _handle_slash_command(self, command: str) -> None:
        """Handle slash commands (/login, /logout, /status, /help)."""
        cmd = command.strip().lower()

        if cmd == "/login":
            await self._cmd_login()
        elif cmd == "/logout":
            await self._cmd_logout()
        elif cmd == "/status":
            await self._cmd_status()
        elif cmd == "/help":
            self._add_system_message(
                "Commands: `/login` · `/logout` · `/status` · `/help`\n\n"
                "Keys: Enter send · Shift+Enter newline · Esc stop · Ctrl+N new · Ctrl+C exit"
            )
        else:
            self._add_system_message(f"Unknown command: `{command}`. Type `/help` for commands.")

    async def _cmd_login(self) -> None:
        """Handle /login — start ChatGPT OAuth flow."""
        from ..auth import login

        self._add_system_message("Opening browser for ChatGPT login...")

        session_id = await login(self._config.api_url)
        if session_id:
            self._config.save_cli_session(session_id)
            self._api_client.set_session(session_id)
            self._add_system_message("Logged in to ChatGPT. Provider switched to chatgpt.")

            # Update status bar
            status_bar = self.query_one(StatusBar)
            status_bar.set_mode(f"{self._config.mode} · chatgpt")
        else:
            self._add_system_message("Login timed out or failed. Try `/login` again.")

    async def _cmd_logout(self) -> None:
        """Handle /logout — clear ChatGPT session."""
        self._config.clear_cli_session()
        self._add_system_message("Logged out. Switched back to default provider.")

        status_bar = self.query_one(StatusBar)
        status_bar.set_mode(self._config.mode)

    async def _cmd_status(self) -> None:
        """Handle /status — show auth and config status."""
        from ..auth import check_auth

        parts = [
            f"mode: {self._config.mode}",
            f"provider: {self._config.provider}",
        ]

        if self._config.session_id:
            auth = await check_auth(self._config.api_url, self._config.session_id)
            if auth.get("authenticated"):
                model = auth.get("model", "unknown")
                parts.append(f"chatgpt: authenticated (model: {model})")
            else:
                parts.append("chatgpt: session expired — run `/login`")
        else:
            parts.append("chatgpt: not logged in")

        self._add_system_message("\n".join(parts))

    def _show_approval_bindings(self) -> None:
        """Show y/n in footer when tool needs approval."""
        self._bindings.bind("y", "approve_tool", "Approve (y)", show=True)
        self._bindings.bind("n", "deny_tool", "Deny (n)", show=True)
        self.refresh_bindings()

    def _hide_approval_bindings(self) -> None:
        """Hide y/n from footer."""
        self._bindings.bind("y", "approve_tool", "Approve", show=False)
        self._bindings.bind("n", "deny_tool", "Deny", show=False)
        self.refresh_bindings()

    def _add_system_message(self, text: str) -> None:
        """Add a system/info message to the message list."""
        message_list = self.query_one(MessageList)
        message_list.mount(MessageBubble("assistant", f"*{text}*"))
        message_list.scroll_to_bottom()
