"""Main chat/agent screen — the primary interaction surface."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Header, Static

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
        self._current_bubble: MessageBubble | None = None
        self._pending_approval: ToolCallPanel | None = None
        self._is_running = False
        self._current_step = 0
        self._chatgpt_available = False
        self._cancel_requested = False

    def compose(self) -> ComposeResult:
        """Compose the chat screen layout."""
        yield Header(show_clock=False)
        yield MessageList(id="message-list")
        with Vertical(id="input-container"):
            yield InputArea(id="input-area")
            yield StatusBar(
                mode=self._config.mode,
                provider=self._config.provider,
                model=self._config.model or "",
            )

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

        # Check saved ChatGPT auth in background
        if connected:
            self.run_worker(self._check_chatgpt_auth())

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
        self._cancel_requested = False
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

            # Add assistant bubble — children (thinking, tools, answer) mount inside it
            message_list = self.query_one(MessageList)
            bubble = MessageBubble("assistant", "")
            message_list.mount(bubble)
            self._current_bubble = bubble

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
                # Stop consuming if run was cancelled locally
                if self._cancel_requested:
                    break

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
            if not self._cancel_requested:
                self.post_message(AgentErrorEvent({"error": str(exc)}))

    def on_step_start_event(self, event: StepStartEvent) -> None:
        """Handle step start — update status bar with step and context info."""
        step = event.data.get("step_number", 0)
        self._current_step = step

        status_bar = self.query_one(StatusBar)
        status_bar.set_step(f"Step {step}")

        # Update live context/token display
        context_tokens = event.data.get("context_tokens", 0)
        context_max = event.data.get("context_max", 0)
        total_tokens_used = event.data.get("total_tokens_used", 0)
        if context_max > 0:
            status_bar.set_context_live(
                context_tokens, context_max, total_tokens_used
            )

    def on_thinking_event(self, event: ThinkingEvent) -> None:
        """Handle thinking token — mount inside current assistant bubble."""
        content = event.data.get("content", "")
        if not content or not self._current_bubble:
            return

        # Append to existing ThinkingPanel if it's the last child, else create new
        children = self._current_bubble.children
        if children and isinstance(children[-1], ThinkingPanel):
            panel = children[-1]
        else:
            panel = ThinkingPanel()
            self._current_bubble.mount(panel)

        panel.append_token(content)

    def on_tool_start_event(self, event: ToolStartEvent) -> None:
        """Handle tool start — mount inside current assistant bubble."""
        if not self._current_bubble:
            return

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

        self._current_bubble.mount(panel)
        message_list = self.query_one(MessageList)
        message_list.scroll_to_bottom()

    def on_tool_approval_required_event(
        self, event: ToolApprovalRequiredEvent
    ) -> None:
        """Handle tool approval request — switch input area to approval mode."""
        tool_call_id = event.data.get("tool_call_id", "")
        tool_name = event.data.get("tool_name", "unknown")
        diff_preview = event.data.get("diff_preview")

        # Find the matching tool panel
        try:
            panel = self.query_one(f"#tool-{tool_call_id}", ToolCallPanel)
        except Exception:
            # Panel not mounted yet or ID mismatch — create a fallback
            panel = None

        if panel:
            if diff_preview:
                panel._diff_preview = diff_preview
            panel.show_approval_prompt()
            self._pending_approval = panel

            # Switch input area to approval mode with full tool details
            input_area = self.query_one(InputArea)
            try:
                tool_display = panel.get_full_arguments_display()
            except Exception:
                tool_display = f"Approve {tool_name}?"
            input_area.enter_approval_mode(tool_display)
        else:
            # Fallback: still ask for approval even without the panel
            self._pending_approval_ids = (
                self._current_run_id or "",
                tool_call_id,
            )
            input_area = self.query_one(InputArea)
            input_area.enter_approval_mode(f"Approve {tool_name}?")

        status_bar = self.query_one(StatusBar)
        status_bar.set_step("Enter approve · [n] deny")

        message_list = self.query_one(MessageList)
        message_list.scroll_to_bottom()

    def on_input_area_approval_decision(
        self, event: InputArea.ApprovalDecision
    ) -> None:
        """Handle approval decision from input area."""
        # Restore input area
        input_area = self.query_one(InputArea)
        input_area.exit_approval_mode()
        input_area.focus()

        status_bar = self.query_one(StatusBar)
        status_bar.set_step("")

        # Primary path: panel-based approval
        if self._pending_approval and self._current_run_id:
            panel = self._pending_approval
            self._pending_approval = None
            panel.resolve_approval(event.approved)

            if event.approved:
                self.run_worker(self._approve_tool(panel.run_id, panel.tool_call_id))
            else:
                self.run_worker(self._deny_tool(panel.run_id, panel.tool_call_id))
            return

        # Fallback path: panel wasn't found, use stored IDs
        fallback = getattr(self, "_pending_approval_ids", None)
        if fallback and self._current_run_id:
            run_id, tool_call_id = fallback
            self._pending_approval_ids = None
            if event.approved:
                self.run_worker(self._approve_tool(run_id, tool_call_id))
            else:
                self.run_worker(self._deny_tool(run_id, tool_call_id))

    async def _approve_tool(self, run_id: str, tool_call_id: str) -> None:
        """Send tool approval to the API."""
        try:
            await self._api_client.approve_tool(run_id, tool_call_id)
        except Exception as exc:
            self._add_system_message(f"Approval failed: {exc}")
            await self._force_reset_run(run_id)

    async def _deny_tool(self, run_id: str, tool_call_id: str) -> None:
        """Send tool denial to the API."""
        try:
            await self._api_client.deny_tool(run_id, tool_call_id)
        except Exception as exc:
            self._add_system_message(f"Denial failed: {exc}")
            await self._force_reset_run(run_id)

    async def _force_reset_run(self, run_id: str) -> None:
        """Force-cancel and reset all run state after an unrecoverable failure."""
        self._cancel_requested = True

        try:
            await self._api_client.cancel_run(run_id)
        except Exception:
            pass

        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None
        self._current_bubble = None
        self._current_step = 0

        input_area = self.query_one(InputArea)
        input_area.exit_approval_mode()

        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(False)
        status_bar.set_step("")

        input_area.focus()

    def on_tool_result_event(self, event: ToolResultEvent) -> None:
        """Handle tool result."""
        tool_call_id = event.data.get("tool_call_id", "")
        result_summary = event.data.get("result_summary", "")
        success = event.data.get("success", True)
        result_data = event.data.get("result_data")

        try:
            panel = self.query_one(f"#tool-{tool_call_id}", ToolCallPanel)
            panel.set_result(result_summary, success, result_data=result_data)
        except Exception:
            pass

        message_list = self.query_one(MessageList)
        message_list.scroll_to_bottom()

    def on_answer_token_event(self, event: AnswerTokenEvent) -> None:
        """Handle answer token (streaming response)."""
        content = event.data.get("content", "")
        if not content:
            return

        # Create StreamingMarkdown on first answer token
        if not self._streaming_md and self._current_bubble:
            self._streaming_md = StreamingMarkdown()
            self._current_bubble.mount(self._streaming_md)

        if self._streaming_md:
            self._streaming_md.append_token(content)
            message_list = self.query_one(MessageList)
            message_list.scroll_to_bottom()

    def on_agent_complete_event(self, event: AgentCompleteEvent) -> None:
        """Handle agent completion."""
        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None
        self._current_bubble = None
        self._current_step = 0

        # Restore input area if it was in approval mode
        input_area = self.query_one(InputArea)
        input_area.exit_approval_mode()

        # Restore hint text
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
        input_area.focus()

    def on_agent_error_event(self, event: AgentErrorEvent) -> None:
        """Handle agent error."""
        error = event.data.get("error", "Unknown error")
        self._add_system_message(f"Error: {error}")

        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None
        self._current_bubble = None
        self._current_step = 0

        # Restore input area if it was in approval mode
        input_area = self.query_one(InputArea)
        input_area.exit_approval_mode()

        # Restore hint text
        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(False)
        status_bar.set_step("")

        input_area.focus()

    def on_agent_state_event(self, event: AgentStateEvent) -> None:
        """Handle agent state change."""
        state = event.data.get("state", "")
        if state:
            status_bar = self.query_one(StatusBar)
            status_bar.set_step(state)

    async def action_cancel_run(self) -> None:
        """Cancel the current agent run (Esc key)."""
        input_area = self.query_one(InputArea)

        # If in approval mode, deny the pending tool first
        if input_area.approval_mode:
            input_area.exit_approval_mode()
            if self._pending_approval:
                panel = self._pending_approval
                self._pending_approval = None
                panel.resolve_approval(False)
                # Fire-and-forget deny — we're cancelling the whole run anyway
                try:
                    await self._api_client.deny_tool(panel.run_id, panel.tool_call_id)
                except Exception:
                    pass
            # Fall through to cancel the run (don't return)

        if not self._is_running or not self._current_run_id:
            input_area.focus()
            return

        run_id = self._current_run_id

        # Signal the SSE consumer to stop
        self._cancel_requested = True

        # Reset state immediately so UI is responsive
        self._is_running = False
        self._current_run_id = None
        self._pending_approval = None
        self._streaming_md = None
        self._current_bubble = None
        self._current_step = 0

        status_bar = self.query_one(StatusBar)
        status_bar.set_busy(False)
        status_bar.set_step("")

        input_area.focus()

        try:
            await self._api_client.cancel_run(run_id)
            self._add_system_message("Run cancelled.")
        except Exception as exc:
            self._add_system_message(f"Cancel failed: {exc}")

    def action_new_conversation(self) -> None:
        """Start a new conversation."""
        self._conversation_id = None
        message_list = self.query_one(MessageList)
        message_list.remove_children()
        self._add_system_message("New conversation started.")
        self.query_one(InputArea).focus()

    async def _handle_slash_command(self, command: str) -> None:
        """Handle slash commands (/login, /logout, /status, /switch, /help)."""
        parts = command.strip().split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/login":
            await self._cmd_login()
        elif cmd == "/logout":
            await self._cmd_logout()
        elif cmd == "/status":
            await self._cmd_status()
        elif cmd == "/switch":
            await self._cmd_switch(args)
        elif cmd == "/help":
            self._add_system_message(
                "Commands: `/login` · `/logout` · `/status` · `/switch [provider]` · `/help`\n\n"
                "Keys: Enter send · Shift+Enter newline · Esc stop · Ctrl+N new · Ctrl+C exit"
            )
        else:
            self._add_system_message(f"Unknown command: `{command}`. Type `/help` for commands.")

    async def _cmd_login(self) -> None:
        """Handle /login — start ChatGPT OAuth flow."""
        from ..auth import backup_tokens, login

        self._add_system_message("Opening browser for ChatGPT login...")

        session_id = await login(self._config.api_url, self._config.session_id)
        if session_id:
            self._config.save_cli_session(session_id)
            self._api_client.set_session(session_id)
            self._chatgpt_available = True
            self._add_system_message("Logged in to ChatGPT. Provider switched to chatgpt.")

            # Backup tokens so they survive DB wipes
            await backup_tokens(self._config.api_url, session_id)

            # Update status bar
            status_bar = self.query_one(StatusBar)
            status_bar.set_provider(f"chatgpt")
        else:
            self._add_system_message("Login timed out or failed. Try `/login` again.")

    async def _cmd_logout(self) -> None:
        """Handle /logout — clear ChatGPT session."""
        self._config.clear_cli_session()
        self._chatgpt_available = False

        # Switch back to default if currently on chatgpt
        if self._config.provider == "chatgpt":
            self._config.provider = "default"
            self._api_client.set_provider("default")
            self._config.save_provider_preference("default")

        self._add_system_message("Logged out. Switched back to default provider.")

        status_bar = self.query_one(StatusBar)
        status_bar.set_provider("default")

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

    async def _cmd_switch(self, args: str) -> None:
        """Handle /switch — toggle between providers."""
        target = args.strip().lower() if args else ""

        if not target:
            current = self._config.provider
            lines = [f"Current provider: {current}"]
            lines.append("Available: default (DeepInfra), chatgpt")
            if self._chatgpt_available:
                lines.append("ChatGPT: authenticated")
            else:
                lines.append("ChatGPT: not logged in — run `/login` first")
            self._add_system_message("\n".join(lines))
            return

        if target == "chatgpt":
            if not self._chatgpt_available:
                self._add_system_message("Not logged into ChatGPT. Run `/login` first.")
                return
            self._config.provider = "chatgpt"
            self._api_client.set_provider("chatgpt")
            self._config.save_provider_preference("chatgpt")
            self._add_system_message("Switched to ChatGPT.")
        elif target in ("default", "deepinfra"):
            self._config.provider = "default"
            self._api_client.set_provider("default")
            self._config.save_provider_preference("default")
            self._add_system_message("Switched to default (DeepInfra).")
        else:
            self._add_system_message(f"Unknown provider: {target}. Use: default, chatgpt")
            return

        # Update status bar
        status_bar = self.query_one(StatusBar)
        status_bar.set_provider(self._config.provider)

    async def _check_chatgpt_auth(self) -> None:
        """Check saved ChatGPT auth on startup.

        If a saved session exists, validates it against the backend.
        If expired, tries to restore from local backup file.
        Updates _chatgpt_available and the status bar accordingly.
        """
        if not self._config.session_id:
            return

        from ..auth import check_auth, try_restore

        auth = await check_auth(self._config.api_url, self._config.session_id)
        if auth.get("authenticated"):
            self._chatgpt_available = True
            status_bar = self.query_one(StatusBar)
            status_bar.set_provider(f"{self._config.provider}")
            return

        # Try restore from backup
        restored = await try_restore(self._config.api_url, self._config.session_id)
        if restored:
            self._chatgpt_available = True
        else:
            # Backup expired too — clear stale session
            self._config.clear_cli_session()

    def _add_system_message(self, text: str) -> None:
        """Add a system/info message to the message list."""
        message_list = self.query_one(MessageList)
        message_list.mount(MessageBubble("system", text))
        message_list.scroll_to_bottom()
