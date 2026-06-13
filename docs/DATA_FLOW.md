# Data Flow

Current request, streaming, workspace, model, and desktop-terminal flows for Fluxion.

## Table of Contents

1. [Chat Mode Flow](#chat-mode-flow)
2. [Coding Agent Flow](#coding-agent-flow)
3. [Plan Mode Flow](#plan-mode-flow)
4. [Tool Approval Flow](#tool-approval-flow)
5. [Context Pipeline](#context-pipeline)
6. [SSE Streaming Protocol](#sse-streaming-protocol)
7. [Workspace and Rewind Flow](#workspace-and-rewind-flow)
8. [Desktop Terminal and Browser Flow](#desktop-terminal-and-browser-flow)
9. [Model and Provider Flow](#model-and-provider-flow)
10. [Auth Flows](#auth-flows)
11. [Database Write Patterns](#database-write-patterns)

---

## Chat Mode Flow

```text
UI composer
  -> POST /api/conversations/{id}/runs or POST /api/runs
  -> routes/runs.py resolves session/provider/model/reasoning settings
  -> ChatEngine builds system + budgeted conversation history + image attachments
  -> provider.complete_streaming()
  -> trace_events + run_events persisted
  -> GET /api/runs/{run_id}/stream emits tokens/thinking/final status
  -> runs.final_answer/status/usage_stats updated
```

Notes:
- If no conversation exists, the backend can create one and auto-title it from the first user message.
- Chat mode uses `orchestrator/engine/chat_engine.py`, not the coding-agent tool loop.
- Provider payload shape is selected by `orchestrator/providers/request_builders.py` for chat completions vs Responses-compatible providers.

## Coding Agent Flow

```text
UI/desktop task
  -> POST /api/agent/runs
  -> resolve/create conversation and immutable workspace_path
  -> resolve provider/model/context profile + runtime reasoning settings
  -> build coding system prompt + project context + coding_session replay
  -> model emits final text or tool calls
  -> canonicalize tool names and parse native/function/XML variants
  -> approval gate if tool permission requires it
  -> execute tools, persist step/tool_call/run_event/artifact rows
  -> append replayable coding_session_entries
  -> repeat until final assistant text, cancel, failure, or max_steps
```

Agent runs are capability-driven. `capabilities.web/filesystem/bash/python` decide which tools are registered for that run. `permission_policy` (`strict`, `relaxed`, `yolo`) decides which `confirm`/`dangerous` tools block for approval.

Completion gating is structured around tool calls and observed evidence. A no-tool assistant response can be accepted as final; missing expected evidence is traced for debugging instead of forcing synthetic continuation loops.

## Plan Mode Flow

```text
Plan request with collaboration_mode=plan
  -> agent creates .fluxion/plans/<plan_run_id>.md
  -> update_plan_doc tool mutates the durable plan file
  -> plan_doc_updated SSE/artifact events update the HUD
  -> final plan is rendered for approval
  -> POST /plan/approve starts/links implementation run
  -> POST /plan/reject records rejection and ends planning run
  -> implementation run appends progress journal entries to the approved plan
```

Plan Mode is a collaboration mode, not the removed old research-planner profile. It uses normal agent persistence plus plan-specific APIs and artifacts.

## Tool Approval Flow

```text
model tool call
  -> ToolSchema.permission_level: auto | confirm | dangerous
  -> policy decision from strict/relaxed/yolo
  -> if approval required: persist pending tool_call + emit tool_approval_required
  -> UI approves/denies POST /api/agent/runs/{run_id}/approve|deny/{tool_call_id}
  -> backend records approval_decision/policy/decided_at
  -> execute or mark denied
```

Read-only tools such as `read_file`, `grep`, `glob`, `list_directory`, artifact reads, and web tools usually auto-run. File mutation and shell tools require confirmation or dangerous-tool allowance depending on policy.

## Context Pipeline

```text
ModelContextProfile
  -> context window, max output, pricing, tool/reasoning/vision support
CodingSessionContextBuilder
  -> replayable coding_session_entries + neutral coding_sessions metadata
Project context
  -> environment, rules, structure, dependencies, git state, cwd
Agent prompt builder
  -> system + project + replay + latest user + available tools
Compaction
  -> when effective input budget threshold is crossed, write visible compaction checkpoint
```

`context_usage` in status/SSE payloads describes the current assembled provider prompt. `stored_context` describes replayable persisted context for future coding turns and drives the composer footer ctx meter.

## SSE Streaming Protocol

SSE events are appended to in-memory `_event_history[run_id]` and persisted in `run_events`. Each SSE subscriber has its own cursor, so reconnects and multiple clients do not steal events from one another.

Common chat events:
- token / thinking token deltas
- completion/failure/interruption terminal events
- persisted `_STREAM_END` fallback for interrupted inactive runs

Common agent events:
- `agent_start`, `step_start`, `llm_request`, `llm_response`
- `tool_call`, `tool_result`, `tool_approval_required`
- `assistant_update`, `system_event`, `plan_doc_updated`
- `agent_complete`, `agent_error`, `_STREAM_END`

Clients reconnect with `since_seq` and the per-run stream token returned by `POST /api/agent/runs`.

## Workspace and Rewind Flow

```text
New Workspace in desktop UI
  -> native Tauri folder picker when available, web fallback otherwise
  -> draft workspace stored client-side until first message
  -> first send creates conversation with workspace_path
  -> workspace_path is immutable for that conversation
  -> backend best-effort ensures .fluxion/ in workspace .gitignore
```

Workspace file search uses `/api/workspaces/search-files` for `@file` mentions and excludes hidden/ignored/generated paths including `.fluxion` scratch artifacts.

Rewind flow:
1. Before each workspace run, `conversation_rewind_checkpoints` captures active transcript seq and `coding_sessions.state_json`.
2. Rewind marks abandoned `runs` and `coding_session_entries` with `rewound_at`/`rewind_group_id` instead of deleting them.
3. Normal conversation APIs and context builders read only the active branch.
4. The selected prior prompt is returned to the composer for editing/resubmission.

## Desktop Terminal and Browser Flow

Terminal sessions:
```text
UI opens terminal tab
  -> GET/POST /api/terminal/conversations/{id}/sessions
  -> services/browser_terminal.py starts PTY in workspace cwd
  -> WebSocket /api/terminal/conversations/{id}/ws?session_id=...
  -> input/resize/output/replay/status messages flow over WS
  -> metadata persisted in terminal_sessions; PTY process remains in memory
```

Draft terminal sessions use `/api/terminal/draft/...` and attach to the created conversation with `/api/terminal/draft/attach/{conversation_id}` after the first message.

Desktop browser tabs are Tauri child WebViews controlled by the desktop shell. They hide while app dialogs/menus are open so native web content does not cover model/settings pickers. Browser tabs are capped by `terminal.max_browser_tabs_per_conversation`.

## Model and Provider Flow

```text
Model picker / API
  -> /api/models lists registry providers and availability
  -> provider keys are stored in app_settings via /api/models/provider-keys
  -> /api/models/select resolves aliases/provider prefixes to ResolvedModel
  -> explicit provider selections fail if credentials are missing
  -> runs preserve X-Provider/X-Model routing through continuations
```

Local model flow:
```text
GET /api/models/local scans LM Studio folders
POST /api/models/local/start
  -> GGUF: launch llama-server on :8080 with local defaults
  -> MLX: launch mlx_lm.server when model type is supported
  -> set provider override in providers/factory.py
POST /api/models/local/stop clears override and stops process
```

Runtime reasoning settings are global persisted app settings merged with active provider/model capabilities. Request builders send only provider-supported reasoning fields.

## Auth Flows

ChatGPT/Codex OAuth:
```text
GET /api/auth/chatgpt/login
  -> PKCE verifier/challenge + browser auth URL
GET /api/auth/chatgpt/callback
  -> exchange code, persist tokens in chatgpt_tokens
GET /api/auth/chatgpt/status/export
POST /api/auth/chatgpt/restore/logout/cancel/refresh
```

Grok OAuth:
```text
POST /api/auth/grok/login
  -> starts Grok auth helper flow
POST /api/auth/grok/code
  -> accepts fallback browser code when needed
GET /api/auth/grok/status
POST /api/auth/grok/cancel/logout
```

## Database Write Patterns

- `runs` is the parent record for chat and agent turns.
- `trace_events` stores granular backend/model/tool timeline events.
- `run_events` stores replayable SSE payloads.
- `agent_steps`, `agent_tool_calls`, and `agent_citations` store agent execution detail.
- `run_artifacts` stores metadata for large command/web outputs saved under `.fluxion/runs/<run_id>/`.
- `coding_sessions` and `coding_session_entries` store durable coding continuity.
- `terminal_sessions` stores PTY metadata only; live PTY handles stay in memory.
- `app_settings` stores provider keys and runtime settings as JSON.
