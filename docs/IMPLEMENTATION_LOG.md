# Implementation Log

> Track all features, fixes, and changes. Claude Code updates this after each commit.
> Read this file first when resuming work.

---

## Current Work

| Branch | Description | Status | Started |
|--------|-------------|--------|---------|
| feature/remove-intent-routing | Removed coding-turn intent routing, restored model-driven coding loop tool choice, simplified working memory to durable continuation state, canonicalized assistant tool-call replay from parsed args only, prevented malformed/missing-arg tool calls from being replayed into later provider requests, and added unit/integration regressions for praise follow-ups plus invalid tool-call recovery | done | 2026-04-29 |
| feature/agent-context-continuity | Agent context continuity hardening — added coding-turn intent routing so praise/thanks/status follow-ups are conversational instead of forced into tool calls, expanded structured working memory with prior outcomes/files/validation/open tasks/raw evidence, changed turn summaries to foreground assistant outcomes before tool metadata, preserved durable state through compaction, and guarded length-only reasoning truncation with no-tools synthesis | done | 2026-04-29 |
| test | Agent repeated-thinking prompt fix — changed working-memory rendering and agent prompts to frame each LLM step as a continuation of the same run, explicitly discouraging repeated “the user wants…” restarts and repeated plan re-derivation between tool calls | done | 2026-04-29 |
| test | Fireworks multimodal system-message fix — normalized agent provider calls to merge working-memory/recovery system blocks into one leading system message so strict Fireworks vision models like Qwen3.6 Plus no longer reject image follow-up requests with “System message must be at the beginning” | done | 2026-04-29 |
| test | Fireworks MiniMax M2.7 preset — added `accounts/fireworks/models/minimax-m2p7` with Fireworks model-card aliases, 196608 context, serverless pricing, function/tool support, vision capability metadata, and registry tests so `minimax-m2.7` is selectable from the Fireworks provider | done | 2026-04-29 |
| test | Fireworks Qwen3.6 Plus preset — added `accounts/fireworks/models/qwen3p6-plus` with Fireworks model-card aliases, serverless pricing, function/tool support, vision capability metadata, and registry tests so `qwen3.6plus` is selectable from the Fireworks provider | done | 2026-04-29 |
| test | Vision tool gating fix — hid the workspace `view_image` tool and its prompt instruction when the active model does not support vision, preventing text-only Fireworks models like GLM-5 from calling image inspection and then failing on image payloads | done | 2026-04-29 |
| test | Fireworks reasoning budget save fix — budget-based Fireworks reasoning now defaults missing thinking-token budgets to Fireworks' documented 1024-token minimum and clamps lower values in both the UI and backend so saving the modal no longer fails when the budget is blank or too small | done | 2026-04-29 |
| test | Vision image input support — added pasted screenshot attachments in the browser composer, workspace `view_image` tooling so the agent can visually inspect local image files directly, OpenAI-compatible multimodal message formatting for chat + agent runs, provider/model `supports_vision` capability metadata with DeepInfra/OpenRouter/Fireworks vision presets, UI blocking for text-only models, and tests for data-URL validation plus chat/responses image payloads | done | 2026-04-29 |
| test | Provider-specific reasoning control fix — corrected chat/completions payload wiring so DeepInfra/Fireworks top-level `reasoning_effort`, Fireworks `thinking.budget_tokens`, and OpenRouter `reasoning.max_tokens` are actually sent, narrowed capability options per provider, and simplified the UI to show only max output, reasoning effort, and provider-supported thinking-token budget controls | done | 2026-04-29 |
| feature/browser-coding-agent | Coding prompt rewrite - replaced the browser coding agent system prompt with a tighter Fluxion prompt that keeps the browser/workspace/tool constraints but explicitly suppresses repeated self-summary, over-narrated intermediary thinking, and trivial retry loops | done | 2026-04-29 |
| feature/browser-coding-agent | Fluxion branding pass — renamed the visible browser/app branding from Reasoner to Fluxion in the UI header, FastAPI app title/logging, README, and core docs without changing internal command names, config paths, localStorage keys, or project rules directory semantics | done | 2026-04-29 |
| feature/browser-coding-agent | Integrated browser terminal — added a per-conversation persistent PTY terminal for desktop agent mode with backend terminal session metadata + websocket I/O, a collapsible/resizable pane in the main window, xterm-based local shell UI, restart/clear/collapse controls, and route tests covering session creation, websocket command execution, and restart behavior | done | 2026-04-28 |
| feature/browser-coding-agent | Agent prompt-history refactor — stopped normal agent cross-turn replay from restoring serialized `agent_state`, switched agent prompt assembly to use summary-based scaffold + injected structured working memory while keeping exact file/tool transcript available for the full duration of a single run, preserved full tool outputs in traces/DB, and added tests covering summary-only cross-turn history, working-memory folding, per-run raw-context retention, and allowed same-run file rereads | done | 2026-04-27 |
| feature/browser-coding-agent | Workspace `@file` mentions — added agent-composer autocomplete backed by a new read-only workspace file-search API so typing `@` in an active workspace suggests matching relative file paths, excludes hidden/ignored directories, and inserts the selected path into the prompt without auto-attaching file contents | done | 2026-04-27 |
| feature/browser-coding-agent | Fireworks GLM-5 registry preset — added `accounts/fireworks/models/glm-5` with Fireworks model-card pricing/context metadata, explicit Fireworks aliases, and registry tests so it shows up alongside the other Fireworks presets instead of only the existing DeepInfra GLM-5 entry | done | 2026-04-27 |
| feature/browser-coding-agent | Unified runtime reasoning controls — added one global backend-persisted reasoning settings object for chat + agent runs, exposed provider-aware capability/status APIs and a browser settings panel, wired OpenAI/OpenRouter/DeepInfra/Fireworks-specific request fields including OpenRouter reasoning max tokens and Fireworks thinking budget/history, and snapshot the effective reasoning config into run metadata | done | 2026-04-27 |
| feature/browser-coding-agent | Bash live-output timeout fix — bash tool now defaults to a longer timeout (300s, max 1800s), preserves partial stdout/stderr on timeout so the agent can see startup logs instead of only a bare timeout, and includes explicit `timed_out` metadata in prompt-history formatting to reduce blind retries on long-running commands like `npm run dev` | done | 2026-04-27 |
| feature/browser-coding-agent | Relaxed permission policy wiring fix — traced approvals still firing in relaxed mode to the factory route path dropping `permission_policy`, then passed it through route → factory → engine so the new per-tool relaxed policy actually takes effect at runtime | done | 2026-04-25 |
| feature/browser-coding-agent | Docs refresh — incrementally updated the source-of-truth docs to document model context profiles, 90%-threshold conversation compaction, bounded prompt-history tool outputs, browser-agent permission behavior, and live SSE/context telemetry without replacing the existing detailed docs | done | 2026-04-27 |
| feature/browser-coding-agent | Context-window-aware conversation compaction + tool-output budgeting — added a normalized backend context profile across registry/custom/local/config sources, switched agent prompt assembly to 90%-threshold visible compaction with persisted summary messages and no historical reasoning rehydration, standardized per-tool prompt-history caps, surfaced context profile/usage/compaction telemetry through model status + agent status/trace/SSE, and updated the browser UI to show live window/reserve/used/remaining plus visible compaction events | done | 2026-04-27 |
| feature/browser-coding-agent | Relaxed permission policy hardening — made relaxed mode tool-wise instead of blanket, auto-allowing read-only filesystem/web tools, requiring approval for write/edit mutations, and classifying bash commands so read-only commands auto-run while mutating, destructive, and outside-workspace commands require approval | done | 2026-04-25 |
| feature/browser-coding-agent | Agent activity timeline polish — made per-step thinking blocks collapsible, kept tool call output always visible, restyled the activity stream into a dot-line-dot timeline, added animated agenting/llming/tooling status words, and extended auto-scroll so live step/tool updates keep following the latest activity | done | 2026-04-25 |
| feature/browser-coding-agent | Browser agent SSE stuck fix — fixed UI getting stuck when EventSource disconnected mid-run by reconnecting with the latest SSE sequence, de-duping replayed events to avoid duplicate streamed text, and keeping token buffering to reduce render pressure during long agent outputs | done | 2026-04-25 |
| feature/browser-coding-agent | Fireworks request compatibility fix — traced latest failed run to Fireworks rejecting the OpenRouter-style `reasoning` request field, added provider/model metadata to only send reasoning params to providers that accept them, and suppressed misleading `$0` cost on zero-token failed runs | done | 2026-04-25 |
| feature/browser-coding-agent | Fireworks auth failure fix — traced conversation `4159afc2-6412-46fc-bb97-e4f8ac79281f` to an unauthenticated Fireworks request, added provider-specific env fallback for Fireworks/DeepInfra keys, made known-model resolution surface missing API key errors instead of falling through to cryptic 401s, and updated dev provider switching to pass `FIREWORKS_API_KEY` through `LLM_API_KEY` | done | 2026-04-25 |
| feature/browser-coding-agent | Usage/cost visibility + Fireworks default — added visible provider token/cost cards in the browser agent UI, clarified estimated context usage, added Fireworks provider/model presets with Kimi K2.6 as default, wired Fireworks pricing including cached-input rates, requested streaming usage where supported, and fixed custom cloud providers so cost is n/a unless pricing is configured instead of incorrectly showing $0 | done | 2026-04-25 |
| feature/browser-coding-agent | Single-agent hardening batch 1 — fixed test rate-limit leakage, added durable SSE event replay from DB, normalized token usage/cost plumbing, split bash stdout/stderr output, added edit failure candidate hints, and added custom OpenAI-compatible provider selection in browser model picker | done | 2026-04-25 |
| feature/browser-coding-agent | Browser coding tool polish — write_file now refuses accidental overwrites unless allow_overwrite=true, coding prompt strongly routes existing-file changes through edit_file, and browser diffs render side-by-side before/after columns | done | 2026-04-24 |
| feature/browser-coding-agent | Agent activity UI flattening — replaced boxed Step 1/2/3 panel with continuous inline activity stream and animated loader for active thinking/tool phases | done | 2026-04-24 |
| feature/browser-coding-agent | Browser tool diff UI — write_file now returns unified diffs for new files and overwrites; approval/result cards render red/green diffs for edit/write/create operations | done | 2026-04-24 |
| feature/browser-coding-agent | Browser-first coding agent foundation — agent mode sends workspace/capability/permission config, browser approval UI handles tool approval events, capability-based backend tool registry enables filesystem/bash without CLI/TUI product coupling, coding prompt rewritten for browser workspace use | done | 2026-04-24 |
| test | Pause/resume agent runs, mid-run steering messages, per-session message limits, conversation history fix | done | 2026-03-19 |
| feature/arch-context-prompts | Architecture + fixes: (1) model-aware context from registry, (2) live context accounting per step, (3) richer turn summaries, (4) disable planning LLM call, (5) system prompts rewrite (autonomy, self-correction, recency), (6) provider API key fix — factory uses registry key not LLM_API_KEY, (7) default model fallback via config.model.name, (8) GLM-5 added to registry, (9) model picker shows all registry models always visible, (10) model select disabled in prod/staging, (11) rate limit bypass fix — X-Forwarded-For only trusted behind proxy, (12) only resolve known registry presets — unknown models use config provider | done | 2026-03-15 |
| feature/ui-tier1-improvements | UI Tier 1 — 5 features: (1) syntax-highlighted code blocks with Prism + language labels, (2) visual message differentiation with avatars/status colors, (3) message actions (copy/retry) on hover, (4) agent progress bar with elapsed timer/token counter/state labels, (5) streaming UX: shimmer skeleton, thinking timer, scroll-to-bottom pill | done | 2026-03-15 |
| test | Docs refresh — README rewrite (CLI, model registry, profiles, 14 tools, ChatGPT OAuth, context mgmt), ARCHITECTURE.md (missing dirs/routes), API_REFERENCE.md (model registry endpoints), COMPONENTS.md (model registry + context mgmt sections) | done | 2026-03-11 |
| test | Model registry + TUI picker — multi-provider model registry (OpenRouter, DeepInfra, local), hot-swap via API, Ctrl+M model picker in TUI, model persistence | done | 2026-03-01 |
| test | GAIA scorer fixes — multi-phase answer extraction, numeric fallback in scorer, increased timeouts for local inference (CLI 300→1800s, extraction 30→120s) | done | 2026-03-01 |
| test | UI thinking sanitization — frontend `sanitizeThinking()` utility strips tool_call/function_call/tool_use XML from thinking panel, model-agnostic | done | 2026-03-01 |
| test | OpenRouter/Qwen support — reasoning/content separation, `reasoning_details` array parsing, `reasoning` param for OpenRouter, XML tool call parsing from reasoning | done | 2026-03-01 |
| test | Local model support — GGUF scanning, llama-server lifecycle management, model picker UI, provider override system, /api/models/* endpoints | done | 2026-03-01 |
| test | CLI resilience — approval 404 detection (server restart), SSE connection loss recovery, "executing tool…" feedback, dev.sh reload scope limit | done | 2026-02-26 |
| test | Persistent ChatGPT auth — token backup/restore, auto-check on startup, /switch command, system messages, token display fixes | done | 2026-02-26 |
| test | Agent UX fixes — cross-turn message context (full messages, not just summaries), write_file diff preview, denial recovery guidance, Enter-to-approve keybind | done | 2026-02-26 |
| test | Context pruning fix — KEEP_FULL_STEPS 2→10, smart filesystem tool pruning (read_file/grep/glob head+tail), provider-aware context budget (250k for GPT-5.2), parallel read-only tool execution | done | 2026-02-26 |
| test | Docs overhaul — update all 6 docs to match current codebase (CLI, tools, profiles, context, approval flow) | done | 2026-02-25 |
| test | System prompt overhaul — HOW TO THINK guidelines, removed synthesis nudge, force-synthesis rewrite, max_steps bump (25/30), industry research | done | 2026-02-25 |
| test | CLI expandable panels + input area approval flow | done | 2026-02-25 |
| test | Agent quality guardrails — stopping criteria, redundancy detection, synthesis nudging; removed dead `full` profile | done | 2026-02-25 |
| test | Context management system — token-aware history, turn summaries, context usage in SSE/UI/CLI | done | 2026-02-25 |
| test | CLI terminal UI redesign — Claude Code style (⏺/⎿ markers, no borders/chrome) | done | 2026-02-25 |
| test | Observability gaps fix — approval audit, result_detail, SSE persistence, file tracking | done | 2026-02-24 |
| feature/chatgpt-oauth | ChatGPT OAuth integration — use ChatGPT Plus/Pro subscription as provider | in progress | 2026-02-23 |
| feature/cli-terminal-theme | CLI terminal theme — black & white monochrome | done | 2026-02-22 |
| docs/update-stale-docs | Update stale docs: BENCHMARKS, DATA_MODELS, ARCHITECTURE | done | 2026-02-14 |
| fix/owner-token-api-client | Wire owner token into API client for full owner access | done | 2026-02-10 |
| feature/benchmarks-page-polish | Benchmarks page reorder and content polish | done | 2026-02-07 |
| feature/session-scoping | Cookie-based session isolation for demo mode | done | 2026-02-03 |
| feature/sse-stream-token | SSE stream token auth for agent runs | done | 2026-02-01 |
| feature/security-hardening | Security hardening: error leakage, CSP header, console log cleanup | done | 2026-02-01 |
| feature/ui-polish | UI polish, label updates, benchmark trace fixes, deployment fixes | done | 2026-02-01 |
| test | GPT-5-mini GAIA benchmark + reasoning model support | done | 2026-01-31 |
| feature/mobile-responsive | Mobile-responsive design | done | 2026-01-27 |
| feature/update-favicon | Custom neural network favicon | done | 2026-01-26 |
| feature/reorder-mode-buttons | Reorder mode buttons and rename to Agent mode | done | 2026-01-26 |
| feature/improve-mode-shortcuts | Simpler keyboard shortcuts for mode switching | done | 2026-01-26 |
| feature/sse-auto-reconnect | SSE auto-reconnect on page reload | done | 2026-01-26 |
| feature/benchmarks-page | Benchmarks page with GAIA results | done | 2026-01-26 |
| feature/block-new-convo-during-run | Block new convo during active run | done | 2026-01-26 |
| feature/demo-mode | Demo mode (rate limiting + sidebar) | done | 2026-01-26 |
| feature/preset-question-chips | Demo preset questions | done | 2026-01-23 |
| feature/gaia-benchmark | GAIA Benchmark Evaluation | done | 2026-01-21 |
| feature/agent-planning | Agent Planning Step | done | 2026-01-20 |

### 2026-03-19: Pause/Resume Agent Runs

**Branch:** `test`
**Status:** done

**Description:**
Agent runs can now be paused and resumed between steps. Backend uses asyncio signals (pause_signal/resume_signal) to block the agent loop. State machine uses AgentState.PAUSED (previously unused).

**Changes:**
- `orchestrator/routes/agent_runs.py` — New `POST /api/agent/runs/{id}/pause` and `POST /api/agent/runs/{id}/resume` endpoints
- `orchestrator/agent/agent_engine.py` — Check `pause_signal` between steps; block if cleared, resume when set
- `orchestrator/agent/state_machine.py` — `AgentState.PAUSED` transitions wired in
- SSE events: `paused`, `resumed` emitted on state changes
- Frontend: `[pause]` button (amber) during active run, `[resume]` + `[stop]` when paused; progress panel shows "Paused" state with amber bar

### 2026-03-19: Mid-Run Steering Messages

**Branch:** `test`
**Status:** done

**Description:**
Users can inject steering messages into active agent runs. Messages are queued and injected as user-role messages before the next LLM call.

**Changes:**
- `orchestrator/routes/agent_runs.py` — New `POST /api/agent/runs/{id}/steer` endpoint; in-memory `_steer_queues` dict
- `orchestrator/agent/agent_engine.py` — `_inject_steer_messages()` drains queue before each LLM call
- SSE event: `steer` (steer_injected) emitted on injection
- Frontend: textarea stays enabled during active runs with "Steer the agent..." placeholder; send button shows "steer" in amber; queued message chips above textarea; injected messages shown in step panel as amber "you: <message>" blocks

### 2026-03-19: Per-Session Message Limits

**Branch:** `test`
**Status:** done

**Description:**
Configurable per-session message limits for demo deployments. Session-based counting via DB, not IP-based. Owner bypasses all limits.

**Changes:**
- `orchestrator/routes/agent_runs.py` (or `app.py`) — New `GET /api/usage` endpoint returning `{limit, used, remaining}`
- `orchestrator/config.py` — `demo.message_limit` config (default 10, `DEMO_MESSAGE_LIMIT` env var)
- Frontend: "X left" counter near input, disabled input at limit, 429 toast handling

### 2026-03-19: Conversation History Fix

**Branch:** `test`
**Status:** done

**Description:**
Fixed assistant response not being appended to messages for cross-turn context. Was missing for 1-step runs (no tool calls), causing two consecutive user messages in history. Also stripped `Q:` prefix from turn summary in history builder.

**Changes:**
- `orchestrator/agent/agent_engine.py` — Append assistant response to messages after synthesis
- `orchestrator/context/history_builder.py` — Strip `Q:` prefix from turn summary entries

---

### 2026-03-01: Model Registry + TUI Model Picker

**Branch:** `test`
**Status:** done

**Description:**
Multi-provider model registry with ~25 presets (OpenRouter, DeepInfra, local). Hot-swap models without restart via `POST /api/models/select`. TUI model picker modal (Ctrl+M or `/model`). Model preference persistence across sessions.

**Changes:**

1. **Model registry** (new):
   - `orchestrator/models/__init__.py` — Package init
   - `orchestrator/models/registry.py` — `ProviderDef`, `ModelPreset`, `ResolvedModel` dataclasses; `PROVIDERS` dict (OpenRouter, DeepInfra, local); ~25 model presets; `ModelRegistry.resolve()` (alias/prefix/fallback); `ModelRegistry.list_models()` (grouped by provider with availability)

2. **Backend wiring**:
   - `orchestrator/providers/factory.py` — Added `create_provider_for_model()` using registry
   - `orchestrator/routes/models.py` — `GET /api/models` (list grouped presets), `POST /api/models/select` (hot-swap), `get_active_model()` for engine integration
   - `orchestrator/schemas.py` — `SelectModelRequest`
   - `orchestrator/agent/factory.py` — Uses active model metadata for context_window, temperature, reasoning_effort
   - `orchestrator/routes/agent_runs.py` — Passes `model_name=model_override` to `create_agent_engine()`
   - `orchestrator/routes/runs.py` — Model registry resolution in `_get_provider_for_session()`
   - `orchestrator/engine/chat_engine.py` — `model_name` override parameter

3. **TUI model picker**:
   - `cli/widgets/model_picker.py` — `ModelPickerModal` (ModalScreen with ListView, grouped by provider)
   - `cli/screens/chat_screen.py` — Ctrl+M binding, `/model` slash command, startup model activation
   - `cli/widgets/status_bar.py` — `set_model()` method
   - `cli/api_client.py` — `get_models()`, `select_model()`, `set_model()`
   - `cli/config.py` — `save_model_preference()`, `load_model_preference()`
   - `cli/__main__.py` — `REASONER_MODEL` env var, persisted model on startup

4. **Tests** (24 new):
   - `tests/models/test_registry.py` — 18 unit tests (aliases, provider detection, fallback, list)
   - `tests/routes/test_models.py` — 6 integration tests (list, select, error handling, state)

### 2026-03-01: Local Model Support, OpenRouter/Qwen, GAIA Scorer

**Branch:** `test`
**Status:** done

**Changes:**

1. **Local model support** (`adacb00`):
   - `orchestrator/services/local_models.py` — GGUF scanning across `~/.lmstudio/models`, `~/models`, `~/.cache/huggingface`, `~/.cache/lm-studio/models`; llama-server lifecycle (start/stop/health); port 8080 default; 100k ctx_size default
   - `orchestrator/routes/models.py` — `/api/models/local` (GET scan), `/api/models/local/start` (POST), `/api/models/local/stop` (POST), `/api/models/status` (GET)
   - `orchestrator/providers/factory.py` — Runtime provider override via `get_provider_override()`/`set_provider_override()` for switching between cloud and local
   - `orchestrator/schemas.py` — `LocalModelSchema`, `StartModelRequest`, `ModelStatusResponse`
   - `ui/src/components/ConversationView.tsx` — Model picker dropdown with scan/start/stop controls
   - `ui/src/api/client.ts` — `fetchLocalModels()`, `startLocalModel()`, `stopLocalModel()`, `getModelStatus()`

2. **OpenRouter/Qwen reasoning support** (`a4d7bfb`):
   - `orchestrator/providers/openai_compat.py` — OpenRouter detection via base_url, sends `reasoning: {"effort": "medium"}` param
   - `orchestrator/providers/response_parsers.py` — Parse `reasoning_details` array (OpenRouter format), `reasoning_content` field (standard format)
   - `orchestrator/providers/request_builders.py` — Include `reasoning` param in request body for OpenRouter

3. **Frontend thinking sanitization** (`640aee2`):
   - `ui/src/lib/utils.ts` — `sanitizeThinking()` strips `<tool_call>`, `<function_call>`, `<tool_use>`, Harmony-style `◁tool_call▷` from reasoning display
   - `ui/src/components/ThinkingPanel.tsx` — Uses shared sanitizer
   - `ui/src/components/AgentStepsPanel.tsx` — Uses shared sanitizer for live and historical thinking

4. **GAIA benchmark improvements** (`8437dee`):
   - `scripts/gaia/scorer.py` — Multi-phase `extract_final_answer()` (bold numbers, answer declarations, last-paragraph extraction); `_extract_number_from_text()` helper; numeric fallback in `score_answer()`; extraction timeout 30→120s
   - `scripts/gaia/__main__.py` — CLI defaults: max-steps 10→25, timeout 300→1800s

### 2026-02-25: Documentation Overhaul — All 6 Docs Updated

**Branch:** `test`
**Status:** done

**Description:**
Comprehensive docs update after major sprint. Audit found docs ~50% stale — ARCHITECTURE.md and COMPONENTS.md worst (missing CLI, 8 agent tools, profiles, context management). Updated all 6 documentation files (1,310 insertions, 89 deletions).

**Files changed:**
- `docs/ARCHITECTURE.md` — Added CLI/TUI system section, agent profiles, filesystem tools table (10 tools), context management pipeline, ChatGPT provider, updated directory tree and ER diagram
- `docs/COMPONENTS.md` — Added all 7 filesystem tool docs, CLI widgets/screens/events, profile.py, context.py, approval endpoints, CLI API client
- `docs/DATA_MODELS.md` — Added run_events + run_artifacts tables, approval columns on agent_tool_calls, updated_at columns, turn_summary, updated ER diagram and Pydantic models
- `docs/DATA_FLOW.md` — Added CLI data flow sequence diagram, tool approval flow decision tree, context pipeline diagram
- `docs/API_REFERENCE.md` — Added approve/deny tool endpoints, updated create run request/response schemas, tool_approval_required SSE event
- `docs/WORKFLOW.md` — Added CLI commands tables, updated co-author to Opus 4.6

**Tests:** 820 passed, 15 failed (pre-existing, unrelated to doc changes)

---

### 2026-02-24: CLI UI Polish + ChatGPT OAuth in CLI + Sanity Test Fixes

**Branch:** `test`
**Status:** done

**Description:**
Three areas of work: (1) CLI visual hierarchy overhaul — monochrome-plus-two design with functional accent colors, (2) ChatGPT OAuth wired into CLI via `/login` command, (3) sanity test fixes for profile agent tests.

**CLI UI Polish:**
- Monochrome-plus-two theme: zinc base + blue (#60a5fa) tools/accents, green (#4ade80) success, amber (#d97706) warnings
- Border-left colors differentiate message types (gray user, blue assistant, blue tools, dim thinking)
- Compact tool call panels: single-line header with primary arg inline
- Status bar: pipe separators, spacer, green/red connection dot
- Welcome card: structured key-value layout with border
- Turn separators, blue focus ring, streaming markdown inside assistant bubble

**ChatGPT OAuth in CLI:**
- `/login` command opens browser for OAuth, polls for completion, saves session to `~/.config/reasoner/cli_session`
- `/logout`, `/status`, `/help` slash commands
- `cli_session` query param on `/login` and `/status` endpoints so tokens link to CLI session (not browser's)
- `X-CLI-Session` header on API requests for token lookup
- Fixed OAuth redirect_uri: local requests use whitelisted `localhost:1455` URI (was sending `localhost:9000` causing OpenAI "unknown_error")
- Callback server uses SO_REUSEADDR to reclaim port from stale processes

**CLI Local Python Execution:**
- CLI sends `python_provider: "local"` — bypasses Daytona sandboxes (meant for web UI isolation)
- New param threaded through schema → route → factory → registry

**Sanity Test Fixes:**
- Sections 7a/7b/7c/9: bash brace expansion was eating Python dict `{...}` in `$(python3 -c "...{...}...")`. Replaced with `jq -n` for JSON construction.
- Score: 65/69 → 82/83

**Files changed:**
- `cli/app.py`, `cli/css/app.tcss`, `cli/screens/chat_screen.py`, `cli/widgets/` (6 widgets)
- `cli/auth.py`, `cli/config.py`, `cli/api_client.py`
- `orchestrator/routes/auth.py`, `orchestrator/routes/agent_runs.py`
- `orchestrator/agent/factory.py`, `orchestrator/agent/tools/registry.py`
- `orchestrator/schemas.py`, `scripts/sanity_test.sh`

---

### 2026-02-24: Observability Gaps Fix

**Branch:** `test`
**Status:** done

**Description:**
Closed 5 observability data gaps identified in audit. All changes are additive (new columns, new tables) — nothing breaks existing functionality. Both web UI agent mode and CLI TUI mode benefit since they share the same backend pipeline.

**What was fixed:**
1. **Tool approval audit trail** — Record every approval decision (approved/denied/auto/timeout) with policy and timestamp on `agent_tool_calls`.
2. **Full tool results** — Store up to 10k chars of `result_detail` for write/edit/bash tools (previously only ~300-500 char summary).
3. **SSE event persistence** — Fire-and-forget persist every SSE event to `run_events` table. Survives the 5-minute in-memory cleanup.
4. **File change tracking** — New `run_artifacts` table records every file write/edit/command per run, linked to tool call.
5. **Timestamps** — Added `updated_at` columns to `conversations` and `agent_steps`.

**Changes:**
- `orchestrator/storage/schema.sql` — Added 4 columns to `agent_tool_calls` (approval_decision, approval_policy, approval_decided_at, result_detail), `updated_at` to conversations/agent_steps, new `run_events` and `run_artifacts` tables with indexes.
- `orchestrator/storage/db.py` — Migrations 6-9: column additions + table creation for existing databases.
- `orchestrator/storage/repositories/agent_repo.py` — Extended `update_tool_call()` with 4 new params. Added `create_run_event()`, `get_run_events()`, `create_run_artifact()`, `get_run_artifacts()`.
- `orchestrator/agent/state_machine.py` — Added `record_approval()` method, `result_detail` param to `complete_tool_call()`.
- `orchestrator/agent/agent_engine.py` — Records approval decisions after callback returns (approved/denied) and for auto-approved tools. Captures `result_detail` for write tools. Creates `run_artifacts` for file changes.
- `orchestrator/routes/agent_runs.py` — Added `_persist_run_event()` fire-and-forget helper. Wired into `event_callback`. Added timeout warning log. Exposed artifacts in trace endpoint.
- `orchestrator/schemas.py` — Added `RunArtifactResponse`, extended `AgentToolCallResponse` with approval/result_detail fields, added `artifacts` to `AgentRunTraceResponse`.
- `tests/storage/test_observability.py` — 17 new tests covering all new columns, tables, and CRUD operations.
- `tests/agent/test_agent_engine.py` — Updated mock fixtures for `record_approval` and `create_run_artifact`.
- `tests/agent/test_agent_integration.py` — Updated mock fixtures for `record_approval` and `create_run_artifact`.

### 2026-02-23: ChatGPT OAuth Integration

**Branch:** `test`
**Status:** in progress

**Description:**
Users with ChatGPT Plus/Pro subscriptions can now use OpenAI models (GPT-5.x, Codex) through the app at no extra API cost. Implements a native `ChatGPTProvider` that translates between the existing OpenAI-compatible interface and the ChatGPT backend Codex Responses API (`chatgpt.com/backend-api/codex/responses`). Includes full OAuth 2.0 PKCE login flow via `auth.openai.com`, per-user provider routing, and frontend UI for login/provider switching.

**Changes:**
- `orchestrator/providers/chatgpt.py` — New `ChatGPTProvider` implementing `LLMProvider` protocol. Translates messages to Responses API input format (system→instructions, user→input_text, assistant→output_text, tool_calls→function_call, tool_results→function_call_output). Parses SSE events back to standard `LLMResponse`. Supports both streaming and non-streaming modes with retry logic.
- `orchestrator/routes/auth.py` — OAuth PKCE endpoints: login (generates code_verifier/challenge, redirects to OpenAI), callback (exchanges code for tokens, extracts account_id from JWT, stores tokens), status, logout, refresh. Auto-refreshes tokens within 5-minute expiry buffer.
- `orchestrator/storage/db.py` — Migration 5: `chatgpt_tokens` table for per-session OAuth token storage. Added `_create_table_if_not_exists()` helper.
- `orchestrator/app.py` — Registered auth router. Updated CSP for OAuth popup inline script.
- `orchestrator/providers/factory.py` — Added `create_chatgpt_provider(tokens, chatgpt_config)` function.
- `orchestrator/providers/__init__.py` — Exported `ChatGPTProvider`, `create_chatgpt_provider`.
- `orchestrator/config.py` — Added `ChatGPTConfig` Pydantic model with OAuth endpoints, client_id, default_model, reasoning_effort.
- `orchestrator/chat_config.yaml` — Added `chatgpt:` config section with env var support.
- `orchestrator/engine/chat_engine.py` — Accepts optional `provider` parameter for override.
- `orchestrator/routes/runs.py` — Added `_get_provider_for_session()` helper; chat routes check X-Provider header and create ChatGPT provider when requested.
- `orchestrator/routes/agent_runs.py` — Agent task accepts session_id/provider_preference; creates ChatGPT provider override in background task.
- `orchestrator/agent/factory.py` — Accepts `provider_override` parameter.
- `ui/src/hooks/useChatGPTAuth.ts` — React hook for OAuth state management (popup login, postMessage, status polling, provider persistence in localStorage).
- `ui/src/api/client.ts` — Added X-Provider header from localStorage preference.
- `ui/src/components/ConversationView.tsx` — Auth button, provider toggle dropdown, status indicators in both empty-state and active-conversation toolbars.
- `tests/providers/test_chatgpt.py` — 21 tests: request translation, response translation, headers, conversation roundtrip.
- `tests/routes/test_auth.py` — 7 tests: PKCE generation, JWT account_id extraction.

**Files changed:** 17 (8 new, 9 modified)
**Tests:** 28/28 passed (new tests); full suite pre-existing failures only

---

### 2026-02-22: Fix Agent Streaming Jumbled Text & Send Button Lock

**Branch:** `test`
**Status:** done

**Description:**
Fixed two issues: (1) Agent mode thinking text appeared jumbled/scrambled during streaming but correct after reload. Root cause: double EventSource connections — `handleSubmit` subscribed to SSE, then `navigate()` triggered `loadConversation` which subscribed again, causing events to be split or duplicated between connections. (2) Send button was not properly disabled during active agent runs because it only checked local `isSubmitting` state (resets on mount) instead of global `hasActiveRun`.

**Changes:**
- `orchestrator/routes/agent_runs.py` — Replaced shared `asyncio.Queue` with cursor-based pub/sub (append-only history + `asyncio.Event` notify). Each SSE generator tracks its own read cursor so multiple clients can't steal events.
- `orchestrator/agent/agent_engine.py` — Removed local `sanitize_token()`, pass raw reasoning tokens through (matching chat mode behavior).
- `ui/src/hooks/useAgentSSE.ts` — Added `connectionIdRef` guard to drop events from stale EventSource connections.
- `ui/src/components/ConversationView.tsx` — Deferred `navigate()` to after `subscribeAgent()` with `subscribedRunRef` guard to prevent double subscription. Added `hasActiveRun` checks to textarea disabled state, send button disabled state, and `handleSubmit` guard. Status text shows "waiting for active run..." during runs.
- `ui/src/components/AgentStepsPanel.tsx` — Added `stripHarmonyTags()` utility, switched live streaming thinking to `<pre>` for raw token display.

**Files changed:** 5
**Tests:** Sanity test (54/54 passed)

---

### 2026-02-22: CLI-ify Chat Interface — ASCII Markers & Text Buttons

**Branch:** `test`
**Status:** done

**Description:**
Replaced Lucide SVG icons with ASCII/text equivalents across all chat interface components for an authentic terminal feel. Removed Card/Badge wrappers from tool calls, replaced spinners with `[loading...]` text, and converted all buttons to `[text]` format.

**Changes:**
- `ui/src/components/ToolCallCard.tsx` — Rewrote: command-output style with `✓`/`✗`/`→` markers, removed Card/Badge/icons, `[+more]`/`[-less]` expand
- `ui/src/components/AgentStepsPanel.tsx` — `▶`/`▼` expand, `→`/`✓`/`○` step markers, `[running...]`/`[initializing...]` text, removed all Lucide icons
- `ui/src/components/ThinkingPanel.tsx` — `▶`/`▼` expand, `[thinking...]`/`[streaming...]` text, removed Brain/Loader2/Chevron icons
- `ui/src/components/AgentRunMessage.tsx` — `[^C stop]`, `[details]`, plain text stats, removed Eye/Square/Clock/Zap icons
- `ui/src/components/ConversationView.tsx` — `[loading...]` text, `[details]` text button, removed Eye/Loader2 usage
- `ui/src/components/AnswerMarkdown.tsx` — `cp`/`✓` text copy button, removed Copy/Check icons

**Files changed:** 6
**Tests:** Build check + visual verification

---

### 2026-02-22: Dark Theme for BenchmarksPage & TracesModal

**Branch:** `test`
**Status:** done

**Description:**
Extended CLI terminal dark theme to BenchmarksPage and TracesModal. Removed `.theme-light` CSS override that was isolating BenchmarksPage from the dark theme. Converted all amber/emerald/blue/indigo/slate colors to zinc monochrome palette.

**Changes:**
- `ui/src/index.css` — Removed `.theme-light` class and its scrollbar overrides (40 lines deleted)
- `ui/src/components/BenchmarksPage.tsx` — Dark background, zinc hero cards, dark scatter chart (zinc-300 dots for "our" systems, zinc-600 for others, dark grid/tooltip), dark comparison tables, dark about section, dark mobile views
- `ui/src/components/TracesModal.tsx` — Dark container with border, zinc error/status colors, dark summary grid, dark trace buttons

**Files changed:** 3
**Tests:** Build check + visual verification

---

### 2026-02-22: CLI Terminal Theme — Black & White Monochrome

**Branch:** `feature/cli-terminal-theme`
**Status:** done

**Description:**
Restyled entire chat UI from light bubbly design to black-and-white CLI/terminal theme. Zero functionality changes — only CSS variables, Tailwind classes, and visual presentation changed.

**Changes:**
- `ui/src/index.css` — CSS variables to zinc dark palette, body font to IBM Plex Mono, markdown styles to zinc, scrollbar to 4px dark, KaTeX color inherit
- `ui/tailwind.config.js` — Added fontFamily.mono with IBM Plex Mono stack
- 5 UI primitives (`button`, `badge`, `card`, `textarea`, `dialog`) — square corners, remove shadows, dark backgrounds
- `ui/src/App.tsx` — Remove gradients, dark sidebar, `fluxion>` title, dark Toaster
- `ui/src/components/ConversationView.tsx` — Chat bubbles to flat `>` prompts, dark input, remove emojis, zinc colors
- `ui/src/components/ConversationList.tsx` — Dark cards, zinc selection colors
- `ui/src/components/ThinkingPanel.tsx` — Dark container, `[thinking]` label, zinc colors
- `ui/src/components/AnswerMarkdown.tsx` — Dark code blocks, zinc inline code
- `ui/src/components/AgentRunMessage.tsx` — `$` prompt prefix, `[research]`/`[agent]` labels, remove Globe/Badge imports
- `ui/src/components/AgentStepsPanel.tsx` — Dark container, `[progress]` label, zinc timeline
- `ui/src/components/ToolCallCard.tsx` — All-zinc STATUS_CONFIG, dark code blocks
- `ui/src/components/AnswerWithCitations.tsx` — Dark citations, `[N]` text format
- `ui/src/components/CitationInline.tsx` — Dark tooltips, zinc text
- `ui/src/components/DetailPanel.tsx` — Dark panel, dark JSON blocks, zinc headers

**Files changed:** 18 (index.css, tailwind.config.js, 5 UI primitives, App.tsx, 10 components)
**Tests:** Visual verification only (no backend changes, no new tests needed)

---

### 2026-02-14: Documentation Audit & Update

**Branch:** `docs/update-stale-docs`
**Status:** done

**Description:**
Audited all 9 docs against the codebase. 6 were up to date; 3 needed fixes.

**Changes:**
- `docs/BENCHMARKS.md`: Added GPT-5-mini results (50.4% overall, ~#15 rank), restructured to show both models side-by-side, updated leaderboard comparison table and key observations
- `docs/DATA_MODELS.md`: Added `session_id` column to conversations and runs table definitions and ERD diagram (Migration 4 from session scoping feature)
- `docs/ARCHITECTURE.md`: Added `SessionMiddleware` to middleware list, added `session_id` to database schema overview diagram, added new "Session Isolation (Demo Mode)" section documenting cookie-based sessions, owner bypass, and security properties
- `docs/IMPLEMENTATION_LOG.md`: Added this entry

---

### 2026-02-10: Owner Token Wired into API Client

**Branch:** `fix/owner-token-api-client` → merging to `test`
**Status:** done

**Description:**
Fixed a bug where the frontend stored the owner token in localStorage (from `?owner=` URL param) but never sent it on subsequent API calls. The backend treated the owner as a regular session user, so they could only see their own conversations instead of all conversations.

**Changes:**
- `ui/src/api/client.ts`:
  - Added `getOwnerToken()` helper to read from `localStorage`
  - `fetchJson()` now attaches `X-Owner-Token` header on all API requests when token is present
  - `subscribeToRun()` SSE connection appends `?owner=` query param (EventSource doesn't support headers)
  - `subscribeToAgentRun()` SSE connection appends `?owner=` query param
- `docs/IMPLEMENTATION_LOG.md`: Added this entry

**Tests:** TypeScript type check passed, production build succeeded. Sanity test 55/55 passed. 650/658 pytest passed (8 pre-existing failures unrelated).

**Security follow-up:**
- `orchestrator/app.py`: Redact `owner=` query param in `RequestLoggingMiddleware` before writing to logs. Confirmed 0 raw secret occurrences in `logs/app.log` after fix.

---

### 2026-02-07: Benchmarks Page Polish

**Branch:** `feature/benchmarks-page-polish` → merging to `test`
**Status:** done

**Description:**
Reordered and polished the benchmarks page for better first impressions. Results now come first, context second.

**Changes:**
- `ui/src/components/BenchmarksPage.tsx`:
  - Replaced "Two Models Tested" hero card (giant "2" stat) with "Leaderboard Rank ~15" — more impressive
  - Moved Results by Level, Accuracy vs Cost chart, and Leaderboard above the About sections
  - Collapsed two full-width About cards (Agent + GAIA) into a compact side-by-side grid
  - Rewrote Takeaways to be less jargony — added cost context ("most systems cost $100-2800"), clearer language

**Section order before:**
Hero Stats → About Agent → About GAIA → Results → Chart → Leaderboard → Takeaways

**Section order after:**
Hero Stats → Results → Chart → Leaderboard → About (compact) → Takeaways

**Tests:** TypeScript type check passed, production build succeeded.

---

### 2026-02-03: Cookie-Based Session Scoping

**Branch:** `feature/session-scoping` → merging to `test`
**Status:** done

**Description:**
Session isolation for demo mode. Each demo user gets a unique session cookie, and can only see their own conversations/runs. Owner can bypass via `?owner=<secret>` query param or `X-Owner-Token` header.

**Changes:**
- `orchestrator/middleware/session.py` (new) — SessionMiddleware that mints `demo_session` cookie (30-day TTL), sets `request.state.session_id` and `request.state.is_owner`
- `orchestrator/storage/db.py` — Migration 4: Add `session_id` column to `conversations` and `runs` tables
- `orchestrator/storage/repositories/conversation_repo.py` — Add `session_id` param to `create()`, session filtering to `list()`, new `get_with_session_check()` method
- `orchestrator/storage/repositories/trace_repo.py` — Add `session_id` param to `create_run()`, session filtering to `list_runs()`, new `get_run_with_session_check()` method
- `orchestrator/routes/conversations.py` — All endpoints extract session context and verify ownership
- `orchestrator/routes/runs.py` — All endpoints verify session ownership, in-memory `_run_sessions` dict for SSE validation
- `orchestrator/routes/agent_runs.py` — All endpoints verify session ownership, in-memory `_run_sessions` dict
- `orchestrator/app.py` — Register SessionMiddleware
- `orchestrator/engine/chat_engine.py` — Accept and pass `session_id` to trace creation
- `scripts/sanity_test.sh` — Use cookie jar for session persistence, read LLM config from env vars (config endpoint no longer exposes sensitive settings)

**Security Design:**
- Unknown conversation_id → 404 (no existence leak)
- Known ID, wrong session → 404 (same as unknown)
- NULL session_id in DB → Owner-only (legacy data)
- Each curl request without cookie → different session (isolated)

**Tests:** Sanity test 55/55 passed, pytest 650/658 passed (8 pre-existing failures unrelated).

### Follow-up: Security Hardening (2026-02-04)

**Commits:**
- `56f5add` - fix(security): disable OpenAPI docs in production
- `c94b567` - fix(security): remove config snapshot from /api/config endpoint

**Security Fixes:**
1. **OpenAPI docs disabled in production**: `/docs`, `/redoc`, `/openapi.json` now return SPA fallback when `SERVE_STATIC=true` (Railway/production)
2. **Config endpoint sanitized**: `/api/config` only returns `{"demo":{"enabled":true}}` - no model, provider, or key exposure

**Production Verification (isitfrontier.live):**
All 16 security checks passed:
- OpenAPI docs blocked (returns SPA HTML)
- Session isolation working (404 on cross-session access)
- Cookie security: HttpOnly, Secure, SameSite=lax
- Security headers: CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- SQL injection protected (parameterized queries)
- Error messages sanitized (no stack traces leaked)

---

### 2026-02-01: SSE Stream Token Auth

**Branch:** `feature/sse-stream-token` → merged to `test`
**Status:** done

**Description:**
Per-run stream token auth for agent SSE endpoints. Prevents unauthorized replay/hijack of SSE streams even if run_id is known.

**Changes:**
- `orchestrator/routes/agent_runs.py` — Generate `secrets.token_urlsafe(16)` per run, store in `_run_tokens` dict, validate on stream endpoint (403 if mismatch), clean up on completion/error
- `orchestrator/schemas.py` — Add `stream_token: str` field to `CreateAgentRunResponse`
- `ui/src/types/agent.ts` — Add `stream_token` to `CreateAgentRunResponse` interface
- `ui/src/api/client.ts` — Add `streamToken` param to `subscribeToAgentRun()`, build URL with URLSearchParams
- `ui/src/hooks/useAgentSSE.ts` — Accept and forward stream token, store in ref for reconnect, clean up localStorage on complete/error
- `ui/src/components/ConversationView.tsx` — Store token in localStorage on create, read on reconnect
- `tests/routes/test_agent_runs.py` — Update `test_returns_run_id_and_stream_url` for new response format, clear `_run_tokens` in fixtures

**Tests:** 652 passed, 6 pre-existing failures unrelated to changes.

### Follow-up fixes (same session, committed directly to `test`):

**`24a4ba3` fix(sse): fix reconnection 403 and prevent useSSE auto-sub for agent runs**
- `orchestrator/routes/agent_runs.py` — Lenient token validation: allow empty token as fallback (reject only if a non-empty token is provided but wrong)
- `ui/src/components/ConversationView.tsx` — Split `activeRunId` into `activeChatRunId` (for `useSSE` auto-subscribe, chat-only) and `activeRunId` (for UI tracking, all run types). Prevents `useSSE` from auto-subscribing to agent runs, which caused spurious 403s on reconnect.

**`d0ba8fd` fix(sse): replay event history on agent SSE reconnect**
- `orchestrator/routes/agent_runs.py` — Remove `since_seq > 0` gate on history replay so reconnecting clients (with `since_seq=0`) receive past events. Use list snapshot of `_event_history` to avoid concurrent modification during async yields. Add dedup in Phase 2 (`if event_seq > seq`) to skip already-replayed events in the live queue.

---

### 2026-02-01: Security Hardening

**Branch:** `feature/security-hardening` → merged to `test`
**Status:** done

**Description:**
Security audit findings — safe, non-breaking fixes only.

**Changes:**
- `orchestrator/routes/conversations.py` — Replace `detail=str(e)` with generic "Internal server error", use structured logger instead of print/traceback
- `orchestrator/routes/runs.py` — Same fix in two SSE error handlers (chat run error paths)
- `orchestrator/app.py` — Add `Content-Security-Policy` header to `SecurityHeadersMiddleware`
- `ui/src/hooks/useSSE.ts` — Remove debug `console.log` lines (were logging all SSE events in production)
- `ui/src/components/ConversationView.tsx` — Remove auto-reconnect `console.log` lines

**Tests:** 652 passed, 6 pre-existing failures unrelated to changes.

---

### 2026-02-01: UI Polish, Label Updates, Benchmark & Deployment Fixes

**Branch:** `feature/ui-polish` → merged to `test`
**Status:** done

**Description:**
Visual/UX improvements, terminology updates, benchmark trace filtering, and deployment fixes.

**UI Polish (initial):**
- `ui/src/components/ConversationView.tsx` — Auto-scroll during streaming (watches streaming text length, scrolls when near bottom); textarea auto-resize (expands as you type, max 200px, resets on submit); mode button labels on desktop; toast error notifications for failed runs/aborts
- `ui/src/components/AnswerMarkdown.tsx` — Code block copy button (hover-reveal, click-to-copy with checkmark feedback)
- `ui/src/components/ThinkingPanel.tsx` — Animated expand/collapse using CSS grid transition (200ms ease-out)
- `ui/src/components/AgentStepsPanel.tsx` — Same animated expand/collapse
- `ui/src/App.tsx` — Added `<Toaster>` from sonner for toast notifications
- `ui/src/index.css` — Custom thin scrollbars (6px, slate-colored); `.collapsible-content` CSS utility for grid-row animation
- `ui/package.json` — Added `sonner` dependency for toast notifications

**Label & Branding Updates:**
- `ui/src/components/ConversationView.tsx` — Mode button label changed from "Research" to "Agent" (both input areas)
- `ui/src/App.tsx` — Removed "Local AI Chat" subtitle from sidebar header (just shows "Fluxion" now)

**Benchmark Fixes:**
- `ui/src/components/TracesModal.tsx` — Added filter to exclude Mistral traces from comparison modal (`!trace.model.toLowerCase().includes('mistral')`)
- `orchestrator/routes/benchmarks.py` — Fixed deployed benchmarks showing "No evaluation traces found". Root cause: `.gitignore` excludes `gaia_results/` except `gaia_results/best_runs/`, but the API only searched the root directory. Added `_collect_trace_files()` and `_find_trace_file()` helpers to search both `gaia_results/` and `gaia_results/best_runs/` with filename deduplication.

**Deployment Fix (Railway):**
- Fixed 403 Forbidden from DeepInfra on both staging and production. Root cause: Railway had `DEEPINFRA_API_KEY` env var set but config uses `${LLM_API_KEY:-}` which defaults to empty. Set `LLM_API_KEY` on both Railway environments.

---

### 2026-01-31: GPT-5-mini GAIA Benchmark + Reasoning Model Support

**Branch:** `test`
**Status:** done

**Description:**
Ran GPT-5-mini (OpenAI) against the full GAIA benchmark validation set (127 questions, no file attachments) and added reasoning model compatibility to the provider layer. Conducted comprehensive analysis of results including cost modeling, error categorization, and root cause analysis.

**Key Results:**
- **GPT-5-mini**: 50.4% overall (L1: 66.7%, L2: 45.5%, L3: 31.6%) at $8.27 total
- **vs gpt-oss-120b**: +4.7% accuracy improvement, 2.1x cost increase
- **Cost efficiency**: $0.065/question — 10-100x cheaper than typical frontier agent systems

**Code Changes:**
- `orchestrator/providers/request_builders.py` — Added reasoning model detection for OpenAI models (gpt-5*, o1*, o3*, o4*): uses `max_completion_tokens` instead of `max_tokens`, skips `temperature` parameter
- `orchestrator/chat_config.yaml` — Updated config comments for reasoning model compatibility

**Analysis (in `gaia_results/best_runs/SUMMARY.md`):**
- Overlap analysis: Oracle best-of-2 reaches 59.1% (75/127)
- Error categorization: 79% wrong answers, 11% close-but-wrong, 6% incomplete, 3% null
- Step efficiency: Correct answers avg 5.9 steps, wrong avg 9.7 steps; hitting max steps = 80% likely wrong
- Root cause: 55% model-level failures, 25% scaffold-fixable (answer format + content access), 20% hard retrieval
- Context pruning tested and found net negative — pruned summaries lose facts the model needs, causing re-fetches

---

### 2026-01-27: Mobile-Responsive Design

**Branch:** `feature/mobile-responsive`
**Status:** done

**Description:**
Made the entire Fluxion chat application mobile-friendly with progressive enhancement from 320px phones to 1920px+ desktops. Implemented responsive breakpoints, touch-optimized interfaces, and mobile-specific layouts while preserving all existing functionality.

**Key Changes:**
- **App Layout**: Hamburger menu and drawer navigation for mobile (respects demo mode restrictions)
- **Three-panel adaptation**: Sidebar becomes drawer on mobile, detail panel becomes bottom sheet
- **Touch optimization**: 44px minimum tap targets throughout (iOS guideline)
- **Chat interface**: Responsive chat bubbles (95% → 70% from mobile → desktop), vertical input stacking
- **Mode toggles**: Show labels on mobile ("Research", "Chat"), icon-only on desktop
- **Benchmarks tables**: Convert to cards on mobile, horizontal scroll on tablets
- **Responsive breakpoints**: base (0px), sm (640px), md (768px), lg (1024px)

**Implementation Details:**

**Phase 1: Critical Components**
1. **App.tsx** - Mobile navigation system
   - Added mobile detection state (< 768px)
   - Hamburger menu with demo mode integration
   - Sidebar as drawer overlay (80vw width, slide-in animation, backdrop)
   - Fixed header on mobile (h-14, z-40)
   - Preserved all existing demo mode logic

2. **ConversationView.tsx** - Responsive chat interface
   - Chat bubbles: `max-w-[95%] sm:max-w-[85%] md:max-w-[80%] lg:max-w-[70%]`
   - Input area: `flex-col` on mobile, `sm:flex-row` on desktop
   - Mode toggles: Reduced from h-11 to h-9 (36px) for better space utilization
   - Textarea: Increased from 2 to 3 rows for improved typing experience
   - Keyboard shortcuts hidden on mobile (`hidden md:inline`)
   - Responsive padding: `px-3 sm:px-4 md:px-6`

3. **DetailPanel.tsx** - Bottom sheet modal
   - Mobile: Bottom sheet (85vh, slides up, drag handle)
   - Desktop: Right sidebar (400px, slides in from right)
   - Floating button repositioned (bottom-40 on mobile to avoid input overlap)
   - Fixed scrolling issue by converting to flexbox layout
   - Responsive controls with flex-wrap

**Phase 2: Major Components**
4. **BenchmarksPage.tsx** - Data visualization
   - Hero cards: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`
   - Tables → Cards on mobile with all data preserved
   - Tablets: horizontal scroll with `min-w-[600px]`
   - Desktop: full table view
   - Responsive text: `text-3xl sm:text-4xl`

5. **ConversationList.tsx** - Touch-friendly sidebar
   - Touch targets: `h-9 w-9` on mobile, `h-8 w-8` on desktop
   - Card min-height: 60px on mobile for easier tapping
   - Checkboxes: `h-5 w-5` on mobile for better visibility
   - Text truncation increased: 36 → 50 characters

6. **AgentRunMessage.tsx** - Responsive messages
   - Same responsive bubble widths as ConversationView
   - Responsive padding on message containers
   - Stats hidden on very small screens with `hidden sm:flex`

**Mobile UX Refinements (Post-Initial Implementation):**
- Removed duplicate "Fluxion" branding from mobile header
- Added New Chat button to mobile header (right-aligned, disabled during active run)
- Reduced button heights from h-11 (44px) to h-9 (36px) to maximize typing space
- Removed text labels from mode toggle buttons on mobile (icon-only for space)
- Increased Trace button spacing from bottom-20 to bottom-40 (160px) to prevent overlap
- Enhanced textarea: 3 rows + flex-1 for better mobile typing experience
- Fixed DetailPanel scroll by converting to flexbox (header/controls flex-shrink-0, content flex-1)
- **Fixed input area visibility on mobile devices**: Applied mobile fixes that were initially missing from the empty state view, then increased bottom padding from `pb-6` (24px) to `pb-20` (80px) to properly clear mobile browser UI elements (address bar, navigation) which can be 50-80px tall. Added `overflow-y-auto` and `min-h-0` to middle content section to enable scrolling on shorter devices. This ensures all input buttons and help text are fully visible on all mobile devices.

**Breakpoint Strategy:**
- **Base (0-639px)**: Mobile portrait - full-width layouts, vertical stacking, 44px touch targets
- **sm: (640px+)**: Mobile landscape - horizontal layouts begin, 2-column grids
- **md: (768px+)**: Tablets portrait - collapsible sidebar appears, table horizontal scroll
- **lg: (1024px+)**: Desktop - three-column layout, full tables, resizable sidebar

**Files Modified:**
- `ui/src/App.tsx` - Layout system, hamburger menu, drawer navigation
- `ui/src/components/ConversationView.tsx` - Responsive chat, input stacking, touch targets
- `ui/src/components/DetailPanel.tsx` - Bottom sheet modal for mobile
- `ui/src/components/BenchmarksPage.tsx` - Table-to-card transformation
- `ui/src/components/ConversationList.tsx` - Touch target optimization
- `ui/src/components/AgentRunMessage.tsx` - Responsive message bubbles

**Testing:**
- Manually tested at 320px, 375px, 640px, 768px, 1024px viewports
- Verified touch targets meet 44px minimum (iOS guideline)
- Confirmed no horizontal scroll at any breakpoint
- Validated desktop layout unchanged
- Development server running on http://localhost:3000

**Result:**
Fully responsive application supporting phones (320px+), tablets (768px+), and desktops (1024px+). Desktop experience remains exactly as-is per requirement. All existing functionality preserved including demo mode restrictions and sidebar behavior.

---

### 2026-01-26: Custom Neural Network Favicon

**Branch:** `feature/update-favicon`
**Status:** done

**Description:**
Replaced the default Vite favicon with a custom-designed neural network icon that better represents the AI reasoning agent application.

**Design:**
- **Visual**: Neural network with connected nodes representing AI agent reasoning
- **Color scheme**: Indigo blue gradient background (#4F46E5) matching the app's brand color
- **Style**: Clean, modern SVG with glowing center node and semi-transparent connections
- **Symbolism**: Network topology represents multi-step reasoning and connected thoughts

**Implementation:**
- Created `ui/public/favicon.svg` with custom neural network design
- Updated `ui/index.html` to reference `/favicon.svg` instead of `/vite.svg`
- SVG format ensures crisp display at all sizes (browser tabs, bookmarks, etc.)

**Technical details:**
- 100x100 viewBox with rounded corners (rx="20")
- 6 nodes of varying sizes representing reasoning steps
- 7 connection lines with varying opacity for depth
- Center node highlighted with glow effect for focus

**Files Modified:**
- `ui/public/favicon.svg` - New neural network icon (created)
- `ui/index.html` - Updated favicon reference

**Benefits:**
- Professional appearance distinct from default Vite branding
- Visual identity aligned with AI/reasoning theme
- Recognizable in browser tabs and bookmarks
- Scalable SVG format for all display sizes

### 2026-01-26: Reorder Mode Buttons and Rename to Agent Mode

**Branch:** `feature/reorder-mode-buttons`
**Status:** done

**Changes:**
1. **Button order**: Swapped so Agent mode (Globe icon) appears first, Chat mode second
2. **Terminology**: Renamed "Research Assistant" -> "Agent Mode" and "Research mode" -> "Agent mode" throughout
3. **Keyboard shortcuts**: Updated to match visual order
   - Cmd+1 now switches to Agent mode (was Chat)
   - Cmd+2 now switches to Chat mode (was Agent)
4. **Placeholder text**: "Research a topic..." -> "Ask agent to research..."
5. **Button titles**: "Research mode" -> "Agent mode"

**Implementation:**
- Updated button order in both input areas (empty state and conversation view)
- Changed keyboard shortcut handlers to match new order
- Updated all help text to reflect new shortcuts
- Renamed header from "Research Assistant" to "Agent Mode"
- Updated status messages and placeholders

**Files Modified:**
- `ui/src/components/ConversationView.tsx` - Button order, naming, shortcuts

**Benefits:**
- Agent mode is now the primary/first option (main use case)
- Clearer terminology - "Agent" is more descriptive than "Research"
- Visual order matches keyboard shortcut order (1 = first button, 2 = second)
- More intuitive for users - main feature comes first

**Testing:**
- TypeScript compilation: passed
- Build: passed
- Manual test: Verify button order, press Cmd+1 (Agent), Cmd+2 (Chat)

### 2026-01-26: Simpler Keyboard Shortcuts for Mode Switching

**Branch:** `feature/improve-mode-shortcuts`
**Status:** done

**Problem:**
The keyboard shortcuts for switching between Chat and Research modes required 3 keys (Cmd+Shift+R, Cmd+Shift+C), which was clumsy and hard to remember. The help text was also cramped and unclear.

**Solution:**
Simplified to 2-key shortcuts using numbers:
- **Cmd/Ctrl+1** for Chat mode (was Cmd+Shift+C)
- **Cmd/Ctrl+2** for Research mode (was Cmd+Shift+R)

**Implementation:**
- Updated `handleKeyDown()` in ConversationView to check for `'1'` and `'2'` keys with Cmd/Ctrl
- Improved help text readability:
  - Before: `⌘/Ctrl+Enter send · ⌘/Ctrl+Shift+R agent · ⌘/Ctrl+Shift+C chat`
  - After: `Press ⌘/Ctrl+Enter to send · ⌘/Ctrl+1 for Chat · ⌘/Ctrl+2 for Research`
- Changed text structure to use proper English ("Press ... to" and "... for")

**Files Modified:**
- `ui/src/components/ConversationView.tsx` - Keyboard shortcuts + help text

**Benefits:**
- Faster mode switching (only 2 keys instead of 3)
- Numbers are more intuitive than letter combinations
- Easier to remember (1 = first mode, 2 = second mode)
- Clearer help text with better readability

**Testing:**
- TypeScript compilation: passed
- Build: passed
- Manual test: Press Cmd+1 (Chat), Cmd+2 (Research) in textarea

### 2026-01-26: SSE Auto-Reconnect on Page Reload

**Branch:** `feature/sse-auto-reconnect`
**Status:** testing

**Problem:**
When user reloads the page during an active run (agent or chat), the frontend loses its SSE connection and in-memory state. After reload, the UI shows status="running" but receives no updates until another reload is performed.

**Solution:**
Automatically reconnect to SSE streams on page load for any runs with status='running'.

**Implementation:**
- Modified `ConversationView.tsx` `loadConversation()` useEffect
- After loading conversation + runs from API, check for runs with `status === 'running'`
- For agent runs: call `subscribeAgent(run_id, 0)` to reconnect with sinceSeq=0
  - sinceSeq=0 tells backend to replay all events from `_event_history` (kept for 5 minutes)
- For chat runs: call `subscribe(run_id)` to reconnect
- Added debug console.log messages: `[Auto-reconnect] Reconnecting to <mode> run: <id>`
- Updated dependency array to include `subscribe` and `subscribeAgent` callbacks

**Backend Support:**
Backend already supports resumption via:
- `since_seq` query parameter in `/api/agent/runs/{id}/stream`
- `_event_history` dict stores all events for 5 minutes
- SSE endpoint replays missed events before streaming live events

**Files Modified:**
- `ui/src/components/ConversationView.tsx` - Added auto-reconnect logic

**Testing:**
- TypeScript compilation: passed
- Build: passed
- Manual test required:
  1. Start agent run with complex query
  2. Reload page while run is active (before completion)
  3. Verify console shows auto-reconnect message
  4. Verify UI shows all previous events + continues receiving new events
  5. No second reload needed

**Benefits:**
- Seamless UX: user can reload page anytime without losing connection
- Event replay: no data loss, all events from start replayed
- Works for both agent and chat modes

### 2026-01-26: Benchmarks Page with GAIA Results

**Branch:** `feature/benchmarks-page`
**Status:** done

**Description:**
Added a dedicated benchmarks page displaying GAIA benchmark results with a professional leaderboard-style layout, plus a modal to browse full evaluation traces.

**Features:**
- Hero stats cards showing:
  - Level 1 rank (#11 of 32 systems)
  - Cost efficiency (~$5 vs $100-500+ for frontier models)
  - Overall rank (#18 using open-weight model)
- Results table by difficulty level (L1: 64.3%, L2: 37.9%, L3: 31.6%)
- Comparison table with top systems from HAL Princeton leaderboard
- Key observations highlighting cost efficiency and open-weight model performance
- Note: Questions with file attachments were excluded from evaluation
- **Traces Modal** (2026-01-26): View full evaluation runs for each difficulty level
  - Filters to show only full evaluation runs (≥19 questions) to exclude test runs
  - Shows best accuracy run for L1 (42Q, 64.3%), L2 (66Q, 37.9%), L3 (19Q, 31.6%)
  - Shows metadata: level, model, timestamp, questions, correct answers, accuracy
  - Detail view with ALL question results, expected vs actual answers, timing per question
  - Color-coded correct/incorrect results

**Navigation:**
- "Benchmarks" chip with arrow in ConversationView header (both empty state and conversation view)
- Dedicated /benchmarks route with scrollable content
- "View traces" link in Key Observations section opens traces modal

**API Endpoints:**
- `GET /api/benchmarks/traces` - List all available trace files with metadata
- `GET /api/benchmarks/traces/{filename}` - Fetch full trace data for a specific run

**Files Created:**
- `ui/src/components/BenchmarksPage.tsx` - Full benchmarks page component
- `ui/src/components/TracesModal.tsx` - Modal for browsing evaluation traces
- `orchestrator/routes/benchmarks.py` - Benchmarks API routes

**Files Modified:**
- `ui/src/App.tsx` - Added /benchmarks route, imported BenchmarksPage
- `ui/src/components/ConversationView.tsx` - Added benchmarks chip in header
- `ui/src/components/ui/dialog.tsx` - Updated to allow custom sizing for trace modal
- `orchestrator/app.py` - Added benchmarks router

**Data Source:**
Rankings from [HAL Princeton GAIA Leaderboard](https://hal.cs.princeton.edu/gaia) (January 2026)
Traces from `gaia_results/*.json` (58 evaluation runs)

### 2026-01-26: Block New Conversation During Active Run

**Branch:** `feature/block-new-convo-during-run`
**Status:** done

**Problem:**
During GAIA benchmark runs with 8x concurrency, the SSE event queue would overflow causing `QueueFull` errors. While these didn't affect actual results (answers still computed), it degraded UX.

**Solution:**
Block creating new conversations from UI when there's an active run (agent or chat). API still allows creation so scripts/curl can run benchmarks.

**Implementation:**
- Added `useHasActiveRun` selector to check if any agent run is active or chat is streaming
- Modified `ConversationView.tsx` to block submit when creating new conversation + active run exists
- Modified `App.tsx` and `ConversationList.tsx` to block "New" buttons
- Visual feedback: disabled button + "Waiting for active run" message + tooltip on hover

**Improvements (2026-01-26):**
1. **Tooltip visibility fix**: Wrapped disabled buttons in `<span>` elements so tooltips show even when button is disabled (browsers often block tooltips on disabled elements)
2. **Reload persistence**: `useHasActiveRun` now also checks `runsByConversation` for runs with `status === 'running'` from backend data, surviving page reloads

**Files Modified:**
- `ui/src/hooks/useStore.ts` - Added `useHasActiveRun` selector with backend run check
- `ui/src/components/ConversationView.tsx` - Added blocking logic, tooltip wrapper
- `ui/src/App.tsx` - Block "New" button in collapsed sidebar strip, tooltip wrapper
- `ui/src/components/ConversationList.tsx` - Block "New" button in sidebar header, tooltip wrapper

**Testing:**
- TypeScript compilation: passed
- Manual: verified button disabled during active run
- Manual: tooltip shows on hover even when disabled
- Manual: blocking persists after page reload during active run

---

### 2026-01-26: Demo Mode with Rate Limiting and Sidebar Lock

**Branch:** `feature/demo-mode`
**Status:** done

**Description:**
Added demo mode features to make the app showcase-ready without authentication:
1. Rate limiting to prevent abuse
2. Sidebar locked for demo visitors (owner can unlock)

**Rate Limiting:**
- 10 agent runs per hour per IP (expensive - web search + multiple LLM calls)
- 30 chat runs per hour per IP (cheaper - single LLM call)
- In-memory tracking with sliding time window
- Whitelist localhost IPs by default
- Returns 429 with retry info when limit exceeded

**Sidebar Lock:**
- Sidebar collapsed by default in demo mode
- Owner unlocks via secret URL param: `?owner=<32+ char secret>`
- Token stored in localStorage (persists across sessions)
- New Chat button always visible in collapsed strip
- Expand button hidden for non-owners in demo mode

**Configuration:**
```yaml
demo:
  enabled: ${DEMO_MODE:-false}
  owner_secret: ${DEMO_OWNER_SECRET:-}
  rate_limit:
    max_agent_runs_per_hour: 10
    max_chat_runs_per_hour: 30
    window_seconds: 3600
  whitelist_ips:
    - "127.0.0.1"
    - "::1"
```

**Files Created:**
- `orchestrator/middleware/rate_limit.py` - Rate limiting middleware
- `tests/middleware/test_rate_limit.py` - Rate limit tests (10 tests)

**Files Modified:**
- `orchestrator/chat_config.yaml` - Added demo config section
- `orchestrator/config.py` - Added DemoConfig, RateLimitConfig models
- `orchestrator/app.py` - Registered middleware, updated /api/config
- `ui/src/App.tsx` - Sidebar logic, owner detection, New Chat button

**Tests:** 655 passed, 3 pre-existing failures unrelated to changes

---

### 2026-01-23: Preset Question Chips for Demo

**Branch:** `feature/preset-question-chips`
**Status:** done

**Description:**
Added preset question chips to the chat UI empty state to showcase multi-step agentic research capabilities. Selected 4 questions from successful GAIA benchmark runs that demonstrate different agentic skills.

**Questions Selected:**
1. **Dragon diet paper** - Academic paper research (find specific value in Leicester paper)
2. **Polish Raymond actor** - Cross-cultural entertainment research (multi-hop)
3. **1977 Yankees stats** - Sports data lookup with cross-referencing
4. **NASA award trail** - Multi-hop reference chain (article → paper → award ID)

**Files Modified:**
- `ui/src/components/ConversationView.tsx` - Added PRESET_QUESTIONS array and chip UI

**Features:**
- Chips appear above text input on empty conversation view
- Clicking a chip populates the input with the question
- Automatically switches to research mode
- Sparkles icon with "Try these examples" label

**Tests:** UI build succeeds, 645/648 tests pass (3 unrelated failures)

---

### 2026-01-22: Local Ministral 14B Reasoning Model Support

**Branch:** `feature/gaia-benchmark`
**Status:** done

**Description:**
Fixed multiple issues to support local llama-server with Ministral-3-14B-Reasoning model. Mistral models require strict user/assistant message alternation which exposed several bugs.

**Fixes:**
1. **URL building** - Fixed double `/v1` in URL when base_url already contains `/v1`
2. **Plan injection** - Changed from creating second system message to appending to existing system message (Mistral rejects multiple system messages)
3. **Conversation history** - Skip incomplete runs (no assistant response) and duplicate queries to maintain strict alternation

**Files Modified:**
- `orchestrator/providers/openai_compat.py` - Fixed `_build_url()` for URLs ending with `/v1`
- `orchestrator/agent/agent_engine.py` - Fixed `_inject_plan_into_messages()` to append plan to system message
- `orchestrator/agent/agent_engine.py` - Fixed `_build_initial_messages()` to skip incomplete runs
- `orchestrator/chat_config.yaml` - Added env var support for model name (`${LLM_MODEL:-...}`)

**Usage:**
```bash
./dev.sh provider local  # Creates .env.provider with llama-server settings
# Start llama-server with Ministral model on port 8080
./dev.sh start
```

**Tests:** Manual API tests successful with math query (python_execute) and factual query

---

### 2026-01-22: Agent System Prompt Enhancement

**Branch:** `test`
**Status:** done

**Description:**
Enhanced DEFAULT_SYSTEM_PROMPT with research-based verification protocols to improve GAIA benchmark accuracy (currently ~36%). Based on findings documented in `docs/AGENT_REASONING_RESEARCH.md`.

**Changes:**
Added three new protocols to agent system prompt:
1. **SEARCH & VERIFICATION PROTOCOL** - Multiple searches, source authority hierarchy, cross-verification
2. **MANDATORY PYTHON PROTOCOL** - Never compute mentally, always use python_execute
3. **SELF-CHECK BEFORE FINAL ANSWER** - Evidence verification, confusion check

**Files Modified:**
- `orchestrator/agent/agent_engine.py` - Enhanced DEFAULT_SYSTEM_PROMPT (lines 161-210)
- Added deprecation comment for CALCULATION_SYSTEM_PROMPT

**Tests:** All 45 agent tests pass (`uv run pytest tests/agent/test_agent_engine.py -v`)

**Trace Verification:** Existing traces show no errors

---

### 2026-01-22: GAIA max_steps and Extraction Prompt Improvements

**Branch:** `feature/gaia-benchmark`
**Status:** done

**Description:**
Based on analysis of benchmark failures (46/127 = 36.2% accuracy), two improvements to the GAIA benchmark runner:
1. Increased default max_steps from 10 to 15 for complex questions
2. Improved LLM answer extraction prompt for better answer parsing

**Root Cause Analysis:**
- ~18 questions failed due to needing more steps than 10
- ~12 questions had verbose answers that weren't properly extracted
- Level 2/3 questions require more reasoning steps for multi-hop queries

**Files Modified:**
- `scripts/gaia/runner.py` - `max_steps: int = 15` (was 10)
- `scripts/gaia/scorer.py` - Improved extraction prompt with:
  - More explicit formatting rules
  - Truncate response to 2000 chars
  - Examples for names, numbers, lists

**Tests:** All 54 GAIA tests pass (`uv run pytest tests/gaia/ -v`)

---

### 2026-01-22: GAIA API & Empty Args Filtering Fixes

**Branch:** `feature/gaia-benchmark`
**Status:** done

**Description:**
Two fixes to improve GAIA benchmark evaluation:
1. Extended empty args filtering to cover all streaming tool call paths
2. Added `total_steps` field to agent run status API response

**Fixes:**
1. **Empty args filtering**: Extended validation to `tool_call_complete` and `tool_calls_complete`
   paths in streaming response parsing. Previously only covered the accumulator finalization path.
2. **API total_steps**: GAIA runner was looking for `total_steps` but API only returned `current_step`.
   Added `total_steps` to `AgentRunStatusResponse` - returns step count when run is complete.

**Files Modified:**
- `orchestrator/providers/openai_compat.py` - Filter empty args in all streaming paths
- `orchestrator/schemas.py` - Added `total_steps` field to AgentRunStatusResponse
- `orchestrator/routes/agent_runs.py` - Return total_steps when run completes

---

### 2026-01-22: GAIA Timeout Fix & Model Tool Hallucination Fix

**Branch:** `feature/gaia-benchmark`
**Status:** done

**Description:**
Fixed two issues causing GAIA benchmark failures:
1. Timeout too short (300s) - runs completing at ~286s avg were timing out
2. Model hallucinating `web_find` tool - calling non-existent tool instead of reading extracted content

**Fixes:**
1. **GAIA timeout**: Increased from 300s to 600s (10 minutes) for complex questions
2. **System prompt**: Updated to explicitly state ONLY 3 tools exist and to READ extracted content directly

**Root Cause Analysis (web_find):**
- Model extracts page content via web_extract
- Model reads content, finds data (e.g., "State of Qatar")
- Model wants to "verify" or "find end of table" → calls imaginary `web_find` tool
- Not a context pruning issue - model HAS the content but tries to delegate search

**Files Modified:**
- `scripts/gaia/runner.py` - Timeout 300s → 600s
- `orchestrator/agent/agent_engine.py` - System prompts now emphasize:
  - "ONLY three tools available (no others exist)"
  - "After web_extract, READ the content directly, don't try to search within it"

---

### 2026-01-22: GAIA Full Benchmark Results & Empty Args Fix

**Branch:** `feature/gaia-benchmark`
**Status:** done

**Description:**
Ran full GAIA benchmark (127 questions without attachments) overnight using gpt-oss-120b.
Fixed streaming tool call accumulator bug that was causing 45% of python_execute calls to fail.

**Benchmark Results (127 questions, gpt-oss-120b):**
| Level | Correct | Total | Accuracy |
|-------|---------|-------|----------|
| 1 | 27 | 42 | 64.3% |
| 2 | 18 | 66 | 27.3% |
| 3 | 5 | 19 | 26.3% |
| **Total** | **50** | **127** | **39.4%** |

**Failure Analysis:**
- 31 timeouts (24.4%) - questions taking >300s
- 70 python_execute errors from empty arguments (45% of all python_execute calls)
- 12 web_find errors (model calling non-existent tool)

**Root Cause:**
Streaming tool call accumulator in provider emitted tool calls even when no argument
chunks were received. The check was `if acc["id"] and acc["name"]:` but didn't verify
`arguments_parts` had content. Result: empty `{}` arguments passed to agent.

**Fix:**
- Added `and acc["arguments_parts"]` check before emitting streaming tool calls
- Logs warning when skipping incomplete tool calls
- Prevents wasting agent steps on tool calls that will definitely fail

**Files Modified:**
- `orchestrator/providers/openai_compat.py` - Skip streaming tool calls with empty args

---

### 2026-01-21: Fix empty tool arguments validation

**Branch:** `feature/gaia-benchmark`
**Status:** done

**Description:**
Added validation for required tool arguments before execution. The model sometimes
emits tool calls without required arguments (e.g., `python_execute` with `{}`).
The previous error "missing 1 required positional argument: 'code'" was unclear.

**Fix:**
- Validate required arguments from tool schema before calling execute()
- Return clear error: "Missing required argument(s): 'code'. The python_execute tool requires these parameters."
- Model can now understand what's missing and retry with proper arguments

**Impact:**
- Ping-pong riddle: Changed from INCORRECT (100) to CORRECT (3)
- Model recovers faster from empty argument errors

**Files Modified:**
- `orchestrator/agent/agent_engine.py` - Added required args validation
- `dev.sh` - Fixed deepinfra provider to use gpt-oss-120b (was incorrectly set to 20b)

---

### 2026-01-21: GAIA Benchmark Evaluation Setup

**Branch:** `feature/gaia-benchmark`
**Status:** in-progress

**Description:**
Set up GAIA benchmark evaluation to compare Agent mode vs Chat mode performance.
GAIA is a benchmark for General AI Assistants with 450+ questions requiring
multi-step reasoning, tool use, and web browsing.

**Features:**
- Load GAIA dataset from HuggingFace (gated, requires HF_TOKEN)
- Official GAIA quasi exact match scoring (string/number/list normalization)
- Compare Agent mode (planning + tools) vs Chat mode (simple LLM)
- JSON output with per-question results and summary statistics
- Markdown report generation with detailed failure analysis
- Parallel execution with semaphore-based concurrency control
- CLI interface: `python -m scripts.gaia --level 1 --compare -c 5`

**Files Created:**
- `scripts/gaia/__init__.py` - Package exports
- `scripts/gaia/loader.py` - GAIA dataset loader from HuggingFace
- `scripts/gaia/scorer.py` - Quasi exact match scoring (string/number/list)
- `scripts/gaia/results.py` - JSON/Markdown report generation
- `scripts/gaia/runner.py` - Main evaluation runner with parallel execution
- `scripts/gaia/__main__.py` - CLI entry point
- `tests/gaia/__init__.py` - Test package
- `tests/gaia/test_scorer.py` - 44 scoring unit tests
- `tests/gaia/test_loader.py` - 10 loader unit tests

**Files Modified:**
- `pyproject.toml` - Added `benchmark` optional dependency group

**Tests:**
- Unit: 48 passed, 6 skipped (require datasets library)
- Full suite: 639 passed, 3 failed (pre-existing)

**Usage:**
```bash
# Install benchmark deps
uv sync --extra benchmark

# Run evaluation
HF_TOKEN=xxx python -m scripts.gaia --level 1 --mode agent
HF_TOKEN=xxx python -m scripts.gaia --level 1 --compare
HF_TOKEN=xxx python -m scripts.gaia --level 1 -n 10 -c 5  # 10 questions, 5 parallel
```

**Initial Benchmark Results (10 questions per level, with extra prompt):**
| Level | Accuracy | Notes |
|-------|----------|-------|
| 1 | 40% (4/10) | Multi-step reasoning |
| 2 | 40% (4/10) | Tool usage required |
| 3 | 30% (3/10) | Complex reasoning |

**Fix: Removed extra prompt instructions (2026-01-21)**
- Removed `gaia_instruction` that was appended to questions
- GAIA benchmark should test raw agent capability, not with hints
- Questions now sent as-is to agent/chat endpoints

**Enhancement: LLM-based answer extraction (2026-01-21)**
- Added `extract_answer_with_llm()` to extract clean answers from verbose responses
- Agent outputs verbose text (e.g., `**17**【2】`) but LLM extracts just `17`
- Extraction is fair: doesn't see ground truth, just cleans format
- Improved Level 1 accuracy: 40% → 60% (10 questions)

---

### 2026-01-21: Agent Planning - max_plan_steps Wiring

**Branch:** `feature/agent-planning`
**Status:** done

**Description:**
Wired up the `max_plan_steps` config setting which was previously unused. The planner now respects this config value when generating plans.

**Changes:**
- Added `max_plan_steps` parameter to `Planner.__init__()` and `AgentEngine.__init__()`
- Updated `PLANNING_PROMPT` to use `{max_steps}` placeholder instead of hardcoded values
- Added `plan_injected` trace event for debugging (shows messages before/after, plan preview)
- Factory now reads `max_plan_steps` from config and passes through to engine
- Added 2 new unit tests for max_plan_steps behavior

**Files Modified:**
- `orchestrator/agent/planner.py` - max_plan_steps param, dynamic prompt
- `orchestrator/agent/agent_engine.py` - max_plan_steps param, plan_injected trace
- `orchestrator/agent/factory.py` - Read and pass max_plan_steps config

**Tests:**
- Unit: 22 tests (all pass)
- Sanity: 73/73 passed

---

### 2026-01-20: Agent Planning Step

**Branch:** `feature/agent-planning`
**Status:** done

**Description:**
Add explicit planning step to the agent loop that creates structured research plans BEFORE executing tools. The planner LLM naturally scales plan complexity based on query:
- Simple queries: 1 step
- Moderate research: 2-3 steps
- Complex analysis: 3-5 steps

**Changes:**

*Planner Module:*
- Created `orchestrator/agent/planner.py` with:
  - `PlanStep` dataclass with step_number, step_type, description, expected_tool, status
  - `ResearchPlan` dataclass with query_analysis, approach, steps, estimated_complexity
  - `Planner` class that calls LLM to generate plans
- Low temperature (0.3) for deterministic plans
- JSON parsing with fallback for markdown code blocks

*Agent Engine Integration:*
- Added `planning_enabled` parameter to `AgentEngine.__init__`
- Added `_create_plan()` method that calls Planner and emits trace events
- Added `_inject_plan_into_messages()` to add plan as system message
- Added `_update_plan_progress()` to track which plan steps are complete
- Planning step runs after `_build_initial_messages()`, before main loop
- Plan stored as trace event (`plan_created`) visible in Debug Trace panel

*Configuration:*
- Added `agent_planning` section to `chat_config.yaml`:
  - `enabled: true` - Enable/disable planning
  - `max_plan_steps: 5` - Maximum steps in a plan

**Files Created:**
- `orchestrator/agent/planner.py` - Planner class and data structures
- `tests/agent/test_planner.py` - 22 unit tests

**Files Modified:**
- `orchestrator/agent/agent_engine.py` - Planning integration (+200 lines)
- `orchestrator/agent/factory.py` - Pass planning config (+8 lines)
- `orchestrator/chat_config.yaml` - Add agent_planning section (+13 lines)

**Tests:**
- Unit: 22 new (all pass)
- Sanity: 73/73 passed

**Commits:**
- `992ab90` - feat(agent): add planning step before execution loop

---

### 2026-01-19: Agent Improvements

**Branch:** `test`
**Status:** done

**Description:**
Multiple improvements to agent quality and observability:
1. Findings accumulator for better forced synthesis
2. Conversational system prompt for fuller reasoning
3. Token counting with correct tokenizer (o200k_harmony)
4. Duration and token display in answer UI
5. Warm/engaging tone for system prompts

**Changes:**

*Findings Accumulator:*
- Added `_findings` list and `_current_query` to `AgentEngine.__init__`
- Added `_extract_finding_from_result()` method to extract key findings from tool results
- Integrated findings extraction after successful tool execution
- Enhanced forced synthesis prompt to include accumulated findings

*Conversational System Prompt:*
- Rewrote `DEFAULT_SYSTEM_PROMPT` from bullet-point imperative style to flowing conversational paragraphs
- Added warm/engaging tone guidance to agent and chat prompts

*Token Counting & Display:*
- Fixed tokenizer to use `o200k_harmony` (correct for gpt-oss models)
- Added `total_tokens` field to `AgentResult` with accumulation across LLM calls
- Token counts now shown in trace events via API
- UI displays duration (clock icon) and tokens (zap icon) in answer footer

**Files Modified:**
- `orchestrator/agent/agent_engine.py` - Findings, prompts, token tracking
- `orchestrator/utils/tokens.py` - Switch to o200k_harmony tokenizer
- `orchestrator/routes/agent_runs.py` - Include total_tokens in SSE complete
- `orchestrator/chat_config.yaml` - Warm tone for chat prompt
- `ui/src/components/AgentRunMessage.tsx` - Duration/tokens display
- `ui/src/hooks/useAgentSSE.ts` - Handle timing_ms and total_tokens
- `ui/src/types/agent.ts` - Add stats to CompleteEvent and AgentUIState
- `tests/agent/test_agent_engine.py` - 9 new tests for findings accumulator

**Tests:**
- Unit: 45 passed (agent_engine tests)
- UI build: success

**Commits:**
- `0da257e` - Conversational prompt + findings accumulator
- `2d72b54` - o200k_harmony tokenizer fix
- `9a36ddf` - Token counts in trace events
- `a6d8d96` - Duration and token display in answer UI

---

## Session Quick Resume

1. Read this log (you're doing it)
2. Check current branch: `git status`
3. Run validation: `./scripts/validate.sh`
4. Look at "Current Work" above
5. After work, update this log

---

## Completed

### 2026-01-19: Fix Agent Forced Synthesis for Reasoning Models

**Branch:** `fix/agent-forced-synthesis-empty` (merged to `test`)
**Status:** done

**Problem:**
Agent runs that hit max_steps would trigger forced synthesis, but the model (gpt-oss-20b) would produce empty content with all output going to `reasoning_content`. The agent would complete with `answer_length: 0`.

**Root Cause:**
1. Forced synthesis LLM call wasn't traced, making debugging difficult
2. Reasoning models put chain-of-thought in `reasoning_content` and may not output to `content`
3. Token limit was too low for reasoning models
4. 20b model produced poor synthesis quality

**Solution:**
- Added trace events for forced synthesis LLM request/response
- Increased synthesis token limit from 4096 to 8192
- Added reasoning content fallback when text is empty
- Clean JSON tool call patterns from reasoning before using as answer
- Stronger synthesis prompt to prevent tool call attempts
- Updated default model to `openai/gpt-oss-120b` for better quality

**Files Changed:**
- `orchestrator/agent/agent_engine.py` - Synthesis tracing, fallback logic
- `orchestrator/chat_config.yaml` - Model updated to 120b
- `orchestrator/config.py` - Model default updated to 120b

**Verification:**
```
# Before (20b): answer_length: 260, reasoning fallback with JSON artifacts
# After (120b): answer_length: 6236, proper text output with comparison table
```

---

### 2026-01-19: Keyboard Shortcuts for Mode Switching

**Branch:** `feature/keyboard-shortcuts-mode-toggle` (merged to `test`)
**Status:** done

**Changes:**
- Default mode changed from 'chat' to 'research' (agent mode)
- Added keyboard shortcuts for mode switching:
  - `Cmd/Ctrl + Shift + R` - Switch to Research/Agent mode
  - `Cmd/Ctrl + Shift + C` - Switch to Chat mode
- Updated help text to display all available shortcuts

**Files Changed:**
- `ui/src/components/ConversationView.tsx`

**Tests:**
- UI build: success (no TypeScript errors)

---

### 2026-01-19: Fix LLM Summarization Token Limit for Reasoning Models

**Branch:** `test` (direct fix)
**Status:** done

**Problem:**
LLM summarization was generating empty summaries (llm_summaries: 0). Investigation showed:
- LLM was being called correctly (logs showed provider type, content chars)
- LLM returned `LLMResponse` with `text: ''` (empty string)
- Raw response showed `finish_reason: 'length'` with reasoning in `reasoning_content`
- The gpt-oss-20b reasoning model generates reasoning tokens FIRST, exhausting the 150 token limit before producing actual content

**Root Cause:**
`MAX_SUMMARY_TOKENS` was set to 150, which is insufficient for reasoning models that generate chain-of-thought reasoning before producing output. The model would fill reasoning_content, hit the token limit, and return empty content.

**Solution:**
Increased `MAX_SUMMARY_TOKENS` from 150 to 400 in `orchestrator/agent/context_pruner.py`.

**Verification:**
```
# Before fix:
{"text_attr":"''", "finish_reason": "length", "reasoning_content": "We need to..."}

# After fix (400 tokens):
{"text_attr":"'France's population is about 68 million people...'"}

# Pruning stats now show LLM summaries:
{"summarized":4,"llm_summaries":2,"current_step":5}
```

**Tests:**
- Unit: 36 passed
- Sanity: 71/71 passed

---

### 2026-01-18: LLM-based Smart Context Summarization

**Branch:** `feature/llm-context-summarization` (merged to `test`)
**Status:** merged

**Description:**
Add query-aware LLM summarization for context pruning. Instead of simple char-count summaries like `[Extracted - 20000 chars]`, the pruner now uses an LLM to extract key facts relevant to the user's query. This improves answer quality for multi-step agent queries while maintaining token efficiency.

**Problem:**
- Context pruner used dumb summaries: `[Tool result - 5000 chars]`
- Lost important data from earlier steps in multi-step runs
- No awareness of what information is relevant to the query
- Risk of low-quality answers when key facts are pruned away

**Solution:**
- Added `SummarizerProvider` protocol for LLM providers
- Added `set_llm(provider, model, query)` to configure LLM summarization
- Added `prune_async()` for async LLM-based pruning
- Added `_summarize_tool_result_llm()` with caching
- Prompt extracts only query-relevant facts in 2-3 sentences
- Falls back to basic summarization on error or for short content (<500 chars)
- Skips LLM for python_execute (keep head/tail instead)

**Files Modified:**
- `orchestrator/agent/context_pruner.py` - Added LLM summarization (+221 lines)
- `orchestrator/agent/agent_engine.py` - Use prune_async with query context (+7 lines)

**Files Updated:**
- `tests/agent/test_context_pruner.py` - 11 new tests for LLM summarization
- `scripts/sanity_test.sh` - 3 complex multi-step agent queries added

**Tests:**
- Unit: 36 passed (11 new for LLM summarization)
- Full suite: 561 passed, 2 failed (pre-existing in test_response_parsers.py)
- Sanity: 71/71 passed (including new multi-step queries)

**Verification:**
```
# Log output during multi-step research query:
[06435] INFO: Pruned context messages (smart)

# Tests verify:
- LLM called for content > 500 chars
- Caching prevents duplicate LLM calls
- Fallback to basic on LLM error
- Python output keeps head/tail pattern
```

---

### 2026-01-18: SSE Event Queue Overflow Fix

**Branch:** `feature/queue-overflow-fix` (merged to `test`)
**Status:** merged

**Description:**
Fix SSE event queue overflow that caused streaming tokens to be silently dropped during long agent responses. The queue was filling up during web searches with lots of content, causing choppy/incomplete streaming to the UI.

**Problem:**
- Event queue had maxsize=100, too small for long agent responses
- runs.py silently dropped events (`except QueueFull: pass`)
- Sanity test showed 200+ "Event queue full" warnings during web search
- UI experienced choppy streaming (final answer still worked via DB polling)

**Fix:**
- Increased queue size from 100 to 1000 in all three locations
- Added `logger.warning("Event queue full")` in runs.py (agent_runs.py already had it)

**Files Modified:**
- `orchestrator/routes/runs.py` - Queue size 100→1000, added logging (2 locations)
- `orchestrator/routes/agent_runs.py` - Queue size 100→1000

**Files Updated:**
- `tests/routes/test_runs.py` - 3 new tests for queue configuration

**Tests:**
- Unit: 3 new (all pass)
- Full suite: 548 passed, 2 failed (pre-existing)

**Verification:**
```
# Before: ~200 "Event queue full" warnings during web search
# After: Queue can hold 10x more events

uv run pytest tests/routes/test_runs.py -v
7 passed (3 queue tests + 4 cleanup tests)
```

---

### 2026-01-18: ChatEngine HTTP Connection Cleanup

**Branch:** `feature/chatengine-cleanup` (merged to `test`)
**Status:** merged

**Description:**
Fix resource leak where ChatEngine (and its underlying httpx.AsyncClient) was never closed after chat completion. Each chat request creates a new ChatEngine with an HTTP client, but `engine.close()` was never called, leading to connection leaks.

**Problem:**
- `orchestrator/routes/runs.py` creates a ChatEngine for each run
- ChatEngine creates an OpenAICompatProvider with an httpx.AsyncClient
- Neither `engine.close()` nor `provider.close()` was called after chat completion
- HTTP connections would accumulate until server restart

**Fix:**
Added `finally` block to call `await engine.close()` in both `run_chat()` functions:
- `create_conversation_run` (line 139-141)
- `create_run` (line 208-210)

**Files Created:**
- `tests/routes/__init__.py` - Test package init
- `tests/routes/test_runs.py` - 4 tests for ChatEngine cleanup

**Files Modified:**
- `orchestrator/routes/runs.py` - Added `finally: await engine.close()` in both run_chat functions

**Tests:**
- Unit: 4 new (all pass)
- Full suite: 545 passed, 2 failed (pre-existing)

**Verification:**
```
uv run pytest tests/routes/test_runs.py -v
4 passed in 0.32s

# Tests verify:
# 1. engine.close() called on success
# 2. engine.close() called on error
# 3. Provider's httpx client is closed
# 4. ChatEngine.close() calls provider.close()
```

---

### 2026-01-18: Orphaned Run Cleanup on Startup

**Branch:** `feature/orphan-run-cleanup` (merged to `test`)
**Status:** merged

**Description:**
Fix runtime durability issue where runs, tool_calls, and steps stuck in active states after server crash/restart would remain orphaned forever. On server startup, the system now:
- Marks runs with status='running' as 'failed'
- Marks tool_calls with status='running'/'pending' as 'interrupted'
- Marks steps with state='tool_calling'/'planning' as 'error'

**Problem:**
- Server crashes mid-run → data stuck in active states forever
- UI shows spinner indefinitely for orphaned runs
- No way to recover without manual DB intervention
- Found 6 orphaned runs, 43 orphaned tool_calls, 14 orphaned steps

**Files Created:**
- `tests/test_app_lifespan.py` - 4 tests for orphaned data cleanup

**Files Modified:**
- `orchestrator/app.py` - Added comprehensive orphaned data cleanup in lifespan startup

**Tests:**
- Unit: 4 new (all pass)
- Full suite: 540 passed, 2 failed (pre-existing)

**Verification:**
```
# Complex multi-run test with 3 concurrent agent queries
# Server killed mid-execution

# After restart with fix:
grep -i "orphan" logs/app.log | tail -1 | jq .
{
  "message": "Cleaned up orphaned data on startup",
  "orphaned_runs": 0,
  "orphaned_tool_calls": 43,
  "orphaned_steps": 14
}

# Verify no orphaned data remains:
sqlite3 var/traces.sqlite "SELECT COUNT(*) FROM agent_tool_calls WHERE status IN ('running', 'pending');"
0
sqlite3 var/traces.sqlite "SELECT COUNT(*) FROM agent_steps WHERE state IN ('tool_calling', 'planning');"
0
```

---

### 2026-01-18: Production Deployment (Railway + Daytona)

**Branch:** `feature/production-deployment`
**Status:** ready-for-review

**Description:**
Production deployment configuration for Railway PaaS with Daytona sandbox for secure Python execution. Includes configurable CORS, Railway-compatible logging, static file serving, and environment-based configuration.

**Files Created:**
- `orchestrator/agent/tools/python_daytona.py` - Daytona sandbox tool (~90ms startup)
- `tests/agent/tools/test_python_daytona.py` - 22 tests for Daytona tool
- `railway.toml` - Railway deployment configuration
- `.env.production.example` - Production environment template

**Files Modified:**
- `orchestrator/app.py` - CORS configuration, security headers, static file serving, logging setup
- `orchestrator/config.py` - DATABASE_PATH env var support for Railway volumes
- `orchestrator/logging_config.py` - RailwayStreamHandler for proper log level routing
- `orchestrator/agent/tools/registry.py` - PYTHON_PROVIDER env var support (daytona/local)
- `pyproject.toml` - Added daytona-sdk, python-dotenv dependencies

**Tests:**
- Unit: 22 new (all pass)
- Full suite: 537 passed, 2 failed (pre-existing)

**Environment Variables:**
| Variable | Purpose |
|----------|---------|
| CORS_ORIGINS | Allowed origins (comma-separated) |
| DATABASE_PATH | SQLite path (for Railway volume) |
| LOG_LEVEL | INFO, DEBUG, WARNING, ERROR |
| LOG_TO_FILE | Enable file logging |
| SERVE_STATIC | Serve frontend from API |
| PYTHON_PROVIDER | daytona or local |
| DAYTONA_API_KEY | Daytona sandbox API key |

**Railway Setup:**
1. Create Railway project from GitHub
2. Add volume mounted at /data
3. Set env vars from .env.production.example
4. Deploy (uses railway.toml)

**Verification:**
```
uv run pytest -v
537 passed, 2 failed (pre-existing issues in test_response_parsers.py)
22/22 Daytona tool tests passed
```

---

### 2026-01-17: Development Workflow System

**Branch:** `main` (direct commit)
**Status:** Completed

**Description:**
Created a development workflow system for Claude Code to maintain context across sessions. Includes validation script, implementation log, workflow guide, and session start reference.

**Files Created:**
- `scripts/validate.sh` - Combined trace/log/test validation
- `docs/IMPLEMENTATION_LOG.md` - This file
- `docs/WORKFLOW.md` - Development process guide

**Files Modified:**
- `.claude/CLAUDE.md` - Added session start section

**Tests:**
- validate.sh tested: all checks pass
- No new unit tests (documentation/tooling only)

**Verification:**
```
./scripts/validate.sh
=== Trace Validation ===
No failed runs in last 24h
Runs (24h): 3 total, 3 succeeded

=== Log Validation ===
No ERROR entries

=== Validation Summary ===
All checks passed
```

---

## Entry Template

```markdown
### YYYY-MM-DD: Feature Name

**Branch:** `feature/xxx`
**Status:** in-progress | testing | merged

**Description:**
[What does this feature do?]

**Files Created:**
- `path/to/file.py` - [Purpose]

**Files Modified:**
- `path/to/file.py` - [What changed]

**Tests:**
- Unit: [X] new, [pass/fail]
- E2E: [pass/fail]

**Issues Found/Fixed:**
- [Issue description and resolution]

**Verification:**
\`\`\`
Run ID: xxx
Status: succeeded
\`\`\`
```

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Features this session | 8 |
| Total tests added | 53 |
| PRs to main | 2 |
