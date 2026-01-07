# Agent Implementation Log

> **Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.

---

## Current Status

- **Current Phase:** 7 (Frontend - COMPLETED)
- **Current Branch:** `feature/agent-phase-7-frontend`
- **Last Updated:** 2026-01-04
- **Blockers:** None

---

## Quick Resume for New Chat

1. Read this log first
2. Read the plan file: `.claude/plans/curried-munching-thunder.md`
3. Checkout the current branch (see above)
4. Look at "Next Steps" below
5. After work, update this log with what you built

---

## Next Steps

**Phase 8: Production** is next. To start:

```bash
# 1. Create branch from test
git checkout test
git checkout -b feature/agent-phase-8-production

# 2. Implement:
#    - Production deployment configuration
#    - Error monitoring and logging
#    - Performance optimization
#    - Crash recovery verification

# 3. Test
./scripts/sanity_test.sh --debug      # E2E tests
# Manual testing in production-like environment

# 4. Update this log with results
# 5. Merge to main for production release
```

---

## Phase Progress

### Phase 1: Data Layer - COMPLETED
- **Branch:** `feature/agent-phase-1-data-layer`
- **Status:** COMPLETED (2026-01-04)
- **Files Created/Modified:**
  - `orchestrator/storage/schema.sql` - Added 3 agent tables (agent_steps, agent_tool_calls, agent_citations)
  - `orchestrator/storage/db.py` - Added migrations for runs table (agent_state, current_step, max_steps, updated_at)
  - `orchestrator/schemas.py` - Added 9 Pydantic models (AgentStepState, AgentToolCallStatus, AgentStepResponse, AgentToolCallResponse, AgentCitationResponse, CreateAgentRunRequest, CreateAgentRunResponse, AgentRunStatusResponse, AgentRunTraceResponse)
  - `orchestrator/storage/repositories/agent_repo.py` - Full CRUD operations for all agent tables
  - `tests/storage/test_agent_repo.py` - 19 comprehensive unit tests
  - `.env` - Created with PARALLEL_API_KEY and E2B_API_KEY
- **Exit Criteria:** ✓ All 206 tests pass (19 new agent tests + 187 existing)
- **Notes:**
  - SQLite BOOLEAN returns 1/0, tests use `== True` not `is True`
  - Agent tables use ON DELETE CASCADE for foreign keys
  - idempotency_key enables crash recovery for tool calls

### Phase 2: Provider Chain - COMPLETED
- **Branch:** `feature/agent-phase-2-provider-chain`
- **Status:** COMPLETED (2026-01-04)
- **Files Created:**
  - `orchestrator/providers/circuit_breaker.py` - CircuitBreaker state machine (closed/open/half-open)
  - `orchestrator/providers/chain.py` - ProviderChain with failover support
  - `tests/providers/test_circuit_breaker.py` - 16 unit tests
  - `tests/providers/test_provider_chain.py` - 19 unit tests
- **Files Modified:**
  - `orchestrator/config.py` - Added CircuitBreakerConfig, ChainedProviderConfig, ProviderChainConfig
  - `orchestrator/chat_config.yaml` - Added provider_chain section (disabled by default)
  - `orchestrator/providers/factory.py` - Updated create_provider() for chain support
  - `orchestrator/providers/__init__.py` - Added new exports
  - `orchestrator/engine/chat_engine.py` - Pass chain_config to create_provider()
- **Exit Criteria:** ✓ All 241 tests pass (35 new + 206 existing), ✓ Chain disabled by default (backward compat)
- **Notes:**
  - Circuit breaker per provider for independent health tracking
  - Failover at connection time only (no mid-stream)
  - Chain disabled by default for backward compatibility

### Phase 3: Tool Layer - COMPLETED
- **Branch:** `feature/agent-phase-3-tools`
- **Status:** COMPLETED (2026-01-04)
- **Files Created:**
  - `orchestrator/agent/tools/base.py` - BaseTool protocol, ToolResult, ToolSchema dataclasses
  - `orchestrator/agent/tools/registry.py` - ToolRegistry with OpenAI schema generation
  - `orchestrator/agent/tools/web_search.py` - Parallel.ai Search API integration
  - `orchestrator/agent/tools/web_extract.py` - Parallel.ai Extract API integration
  - `orchestrator/agent/tools/python_sandbox.py` - E2B sandbox with session cleanup
  - `orchestrator/agent/__init__.py` - Package exports
  - `tests/agent/tools/test_base.py` - 15 unit tests
  - `tests/agent/tools/test_registry.py` - 16 unit tests
  - `tests/agent/tools/test_web_search.py` - 26 unit tests
  - `tests/agent/tools/test_web_extract.py` - 23 unit tests
  - `tests/agent/tools/test_python_sandbox.py` - 19 unit tests
- **Files Modified:**
  - `orchestrator/config.py` - Added ParallelConfig, E2BConfig, SandboxConfig
  - `orchestrator/chat_config.yaml` - Added parallel and sandbox sections
  - `pyproject.toml` - Added e2b-code-interpreter dependency
- **Exit Criteria:** ✓ All 340 tests pass (99 new + 241 existing), ✓ Each tool works in isolation
- **Notes:**
  - Protocol-based design following LLMProvider pattern
  - result_summary (1-line) stored in DB, result_data in-memory only
  - is_idempotent flag for crash recovery (web_search/web_extract: True, python_execute: False)
  - E2B session cleanup on startup for zombie sessions

### Phase 4: Context Pruner + State Machine - COMPLETED
- **Branch:** `feature/agent-phase-4-pruner-state`
- **Status:** COMPLETED (2026-01-04)
- **Files Created:**
  - `orchestrator/agent/context_pruner.py` - ContextPruner with step-aware message pruning
  - `orchestrator/agent/state_machine.py` - AgentStateMachine with crash recovery
  - `tests/agent/test_context_pruner.py` - 23 unit tests
  - `tests/agent/test_state_machine.py` - 36 unit tests
- **Files Modified:**
  - `orchestrator/agent/__init__.py` - Added exports for new modules
- **Exit Criteria:** ✓ All 399 tests pass (59 new + 340 existing), ✓ Pruner summarizes old tool results, ✓ State transitions validated
- **Notes:**
  - ContextPruner keeps last 2 steps detailed, summarizes older ones to 1-line
  - AgentStateMachine validates state transitions (PLANNING → TOOL_CALLING → SYNTHESIZING → COMPLETE)
  - Recovery hints injected for non-idempotent tools (python_execute) on crash
  - Idempotency key support for crash recovery

### Phase 5: Agent Engine - COMPLETED
- **Branch:** `feature/agent-phase-5-engine`
- **Status:** COMPLETED (2026-01-04)
- **Files Created:**
  - `orchestrator/agent/recovery.py` - Recovery helpers (should_retry_tool, build_recovery_messages, create_idempotency_key)
  - `orchestrator/agent/agent_engine.py` - AgentEngine class with full orchestration loop
  - `tests/agent/test_recovery.py` - 31 unit tests
  - `tests/agent/test_agent_engine.py` - 36 unit tests
  - `tests/agent/test_agent_integration.py` - 5 integration tests (including exit criteria)
- **Files Modified:**
  - `orchestrator/agent/__init__.py` - Added exports for new modules
- **Exit Criteria:** ✓ All 471 tests pass (72 new + 399 existing), ✓ Agent answers "What is the population of Tokyo?"
- **Notes:**
  - AgentEngine orchestrates: state machine, tool registry, context pruner, LLM provider
  - SSE event emission (agent_started, step_started, thinking, tool_start, tool_result, synthesizing, agent_complete, agent_error)
  - Recovery helper functions for crash scenarios
  - Idempotency key creation for tool call deduplication
  - Harmony format thinking extraction (<think>...</think>)
  - Citation storage from web_search and web_extract results
  - Force synthesis when max_steps reached

### Phase 6: API Layer - COMPLETED
- **Branch:** `feature/agent-phase-6-api`
- **Status:** COMPLETED (2026-01-04)
- **Files Created:**
  - `orchestrator/agent/factory.py` - AgentEngine factory function
  - `orchestrator/routes/agent_runs.py` - 5 REST endpoints with SSE streaming
  - `tests/routes/__init__.py` - Routes test package
  - `tests/routes/test_agent_runs.py` - 15 unit tests
  - `tests/integration/test_agent_e2e.py` - 6 E2E tests
- **Files Modified:**
  - `orchestrator/app.py` - Added agent_runs router
  - `orchestrator/agent/__init__.py` - Added create_agent_engine export
- **Exit Criteria:** ✓ All 492 tests pass (21 new + 471 existing)
- **Notes:**
  - SSE streaming with resumption support (since_seq parameter)
  - Event translation layer (engine events → SSE events)
  - Ephemeral conversation creation for standalone agent runs
  - Cancellation support with abort signals
  - Full trace endpoint with steps, tool calls, and citations

### Phase 7: Frontend - COMPLETED
- **Branch:** `feature/agent-phase-7-frontend`
- **Status:** COMPLETED (2026-01-04)
- **Files Created:**
  - `ui/src/types/agent.ts` - TypeScript types for agent (AgentStep, AgentToolCall, AgentCitation, AgentSSEEvent, AgentUIState)
  - `ui/src/hooks/useAgentSSE.ts` - SSE streaming hook for agent events
  - `ui/src/components/ToolCallCard.tsx` - Tool call visualization with status
  - `ui/src/components/CitationInline.tsx` - Clickable inline citations with tooltips
  - `ui/src/components/AnswerWithCitations.tsx` - Answer with inline [N] citation rendering
  - `ui/src/components/AgentStepsPanel.tsx` - Collapsible research progress panel
  - `ui/src/components/AgentRunMessage.tsx` - Full agent run display
- **Files Modified:**
  - `ui/src/api/client.ts` - Added agent API functions (createAgentRun, getAgentRunStatus, getAgentRunTrace, cancelAgentRun, subscribeToAgentRun)
  - `ui/src/hooks/useStore.ts` - Added agent state slice with 9 actions
  - `ui/src/components/ConversationView.tsx` - Integrated mode toggle and agent rendering
- **Exit Criteria:** ✓ Build succeeds, ✓ Mode toggle works, ✓ Agent components render correctly
- **Notes:**
  - Chat/Research toggle button in message input area
  - Purple/indigo theme for agent runs (vs blue for chat)
  - Real-time streaming of steps, tool calls, thinking
  - Clickable citations with hover tooltips
  - Cancellation support

### Phase 8: Production - NOT STARTED
- **Branch:** `feature/agent-phase-8-production`
- **Status:** Pending
- **Exit Criteria:** Deployed with crash recovery verified

---

## Key Documents

| Document | Purpose |
|----------|---------|
| `.claude/plans/lazy-purring-nygaard.md` | Full design, architecture, code samples |
| `docs/AGENT_MASTER_REFERENCE.md` | Quick reference (schema, API, fixes) |
| `docs/AGENT_SYSTEM_DESIGN.md` | Detailed system design |
| This file | Live implementation progress |

---

## Git Workflow

### Branch Strategy
```
main (production-ready)
  └── test (integration branch - all phases merge here first)
        └── feature/agent-phase-X-xxx (feature branches)
```

### Workflow Steps
```bash
# 1. Start from test branch
git checkout test

# 2. Create feature branch
git checkout -b feature/agent-phase-X-xxx

# 3. Implement + test (iterative)
uv run pytest tests/xxx/ -v       # Unit tests
uv run pytest                      # Full suite
./scripts/sanity_test.sh --debug   # E2E tests (if server running)

# 4. Commit when tests pass
git add .
git commit -m "feat(agent): Phase X - [Component Name] complete"

# 5. Merge to test branch
git checkout test
git merge feature/agent-phase-X-xxx

# 6. Run E2E tests on test branch
./scripts/sanity_test.sh --debug

# 7. Update this implementation log
```

---

## Testing Workflow (MANDATORY)

### For Every Phase:
1. Write unit tests for each new component
2. Run unit tests after each file
3. Fix any failures before moving to next file
4. Run full test suite: `uv run pytest`
5. Run E2E tests: `./scripts/sanity_test.sh --debug` (requires server)
6. Fix any E2E failures before considering phase complete
7. Update this log with test results

---

## Critical Fixes to Remember

1. **E2B not Docker** - Railway/Fly.io can't run Docker
2. **Context Pruner** - Summarize old tool results to prevent 128k blowout
3. **DeepInfra primary** - 40% cheaper than Together AI
4. **Hint injection** - For python_execute crash recovery
5. **No result_raw** - Store only summaries to prevent WAL bloat
6. **Session cleanup** - Clean E2B sessions on startup

---

## Completed Work

### Phase 1: Data Layer (2026-01-04)

**Summary:** Built the database foundation for the web research agent with full CRUD operations, crash recovery support, and comprehensive tests.

**Files Created:**
1. `orchestrator/storage/repositories/agent_repo.py` - 450+ lines of async CRUD operations
2. `tests/storage/test_agent_repo.py` - 19 comprehensive unit tests

**Files Modified:**
1. `orchestrator/storage/schema.sql` - Added agent_steps, agent_tool_calls, agent_citations tables
2. `orchestrator/storage/db.py` - Added migrations for runs table agent columns
3. `orchestrator/schemas.py` - Added 9 Pydantic models for agent API

**Database Schema Added:**
```sql
-- agent_steps: state machine steps (planning, tool_calling, synthesizing, complete, error)
-- agent_tool_calls: tool executions with idempotency_key for crash recovery
-- agent_citations: evidence sources with used_in_answer tracking
```

**Key Features:**
- Idempotency keys for crash recovery
- Full JSON serialization for complex tool arguments
- Status tracking (pending, running, success, error, timeout, interrupted)
- Cascade delete support

**Test Coverage:** 19 new tests, all passing

### Phase 2: Provider Chain (2026-01-04)

**Summary:** Implemented resilient provider chain with circuit breaker pattern for automatic failover between LLM providers.

**Files Created:**
1. `orchestrator/providers/circuit_breaker.py` - State machine (closed/open/half-open) for provider health
2. `orchestrator/providers/chain.py` - ProviderChain implementing LLMProvider protocol with failover
3. `tests/providers/test_circuit_breaker.py` - 16 comprehensive unit tests
4. `tests/providers/test_provider_chain.py` - 19 comprehensive unit tests

**Files Modified:**
1. `orchestrator/config.py` - Added CircuitBreakerConfig, ChainedProviderConfig, ProviderChainConfig
2. `orchestrator/chat_config.yaml` - Added provider_chain section (disabled by default)
3. `orchestrator/providers/factory.py` - Updated create_provider() to support chain config
4. `orchestrator/providers/__init__.py` - Exported new types
5. `orchestrator/engine/chat_engine.py` - Pass chain_config to factory

**Key Design Decisions:**
- Circuit breaker per provider (not per chain) for independent health tracking
- Keep existing retry logic + add circuit breaker on top
- Failover at connection time only (no mid-stream failover)
- Chain disabled by default for backward compatibility

**Test Coverage:** 35 new tests (16 circuit breaker + 19 provider chain), all 241 tests passing

### Phase 3: Tool Layer (2026-01-04)

**Summary:** Built the complete tool layer for the web research agent with three tools (web_search, web_extract, python_execute), a tool registry, and comprehensive test coverage.

**Files Created:**
1. `orchestrator/agent/tools/base.py` - BaseTool protocol, ToolResult, ToolSchema, exception classes
2. `orchestrator/agent/tools/registry.py` - ToolRegistry with OpenAI function schema generation
3. `orchestrator/agent/tools/web_search.py` - Parallel.ai Search API with retry logic
4. `orchestrator/agent/tools/web_extract.py` - Parallel.ai Extract API with partial success handling
5. `orchestrator/agent/tools/python_sandbox.py` - E2B sandbox with session cleanup
6. `orchestrator/agent/__init__.py` - Package exports
7. `tests/agent/tools/test_*.py` - 99 comprehensive unit tests

**Files Modified:**
1. `orchestrator/config.py` - Added ParallelSearchConfig, ParallelExtractConfig, ParallelConfig, E2BConfig, SandboxConfig
2. `orchestrator/chat_config.yaml` - Added parallel and sandbox configuration sections
3. `pyproject.toml` - Added e2b-code-interpreter dependency

**Key Features:**
- Protocol-based design following LLMProvider pattern
- `result_summary` (1-line) for DB storage, `result_data` for in-memory use (prevents WAL bloat)
- `is_idempotent` flag for crash recovery logic
- E2B session cleanup on startup for zombie sessions
- Exponential backoff with jitter for HTTP retries
- Partial success handling for web_extract (some URLs may fail)

**Tool Specifications:**
| Tool | Idempotent | API | Timeout |
|------|------------|-----|---------|
| web_search | Yes | Parallel.ai /search | 15s |
| web_extract | Yes | Parallel.ai /extract | 30s |
| python_execute | **No** | E2B sandbox | 30s |

**Test Coverage:** 99 new tests, all 340 tests passing

### Phase 4: Context Pruner + State Machine (2026-01-04)

**Summary:** Built context management and state machine for the web research agent with token blowout prevention and crash recovery support.

**Files Created:**
1. `orchestrator/agent/context_pruner.py` - ContextPruner class with step-aware message pruning
2. `orchestrator/agent/state_machine.py` - AgentStateMachine with state transition validation and crash recovery
3. `tests/agent/test_context_pruner.py` - 23 comprehensive unit tests
4. `tests/agent/test_state_machine.py` - 36 comprehensive unit tests

**Files Modified:**
1. `orchestrator/agent/__init__.py` - Added exports for ContextPruner, PruneStats, AgentState, AgentStateMachine, RecoveryContext, StepResult, and exceptions

**Key Features:**
- **ContextPruner**: Prevents 128k token context blowout by summarizing old tool results
  - Keeps last 2 steps detailed (configurable)
  - Summarizes `web_search` as `[Search results - X chars]`
  - Summarizes `web_extract` as `[Extracted content - X chars]`
  - Keeps first/last 200 chars for long `python_execute` output
  - Provides token estimation and pruning statistics

- **AgentStateMachine**: Manages agent execution state and transitions
  - State transitions: PLANNING → TOOL_CALLING → SYNTHESIZING → COMPLETE
  - Validates transitions (prevents invalid state changes)
  - Enforces max_steps limit
  - Crash recovery with hint injection for non-idempotent tools
  - Idempotency key support for tool call deduplication

**State Diagram:**
```
PLANNING → TOOL_CALLING → PLANNING (loop)
                       → SYNTHESIZING → COMPLETE
         → SYNTHESIZING → COMPLETE
         → ERROR
```

**Test Coverage:** 59 new tests (23 context pruner + 36 state machine), all 399 tests passing

### Phase 5: Agent Engine (2026-01-04)

**Summary:** Built the core agent orchestration engine that ties together all Phase 1-4 components to execute web research queries with tool calling.

**Files Created:**
1. `orchestrator/agent/recovery.py` - Recovery helpers for crash scenarios
2. `orchestrator/agent/agent_engine.py` - AgentEngine class with full orchestration loop
3. `tests/agent/test_recovery.py` - 31 comprehensive unit tests
4. `tests/agent/test_agent_engine.py` - 36 comprehensive unit tests
5. `tests/agent/test_agent_integration.py` - 5 integration tests (including exit criteria)

**Files Modified:**
1. `orchestrator/agent/__init__.py` - Added exports for recovery and agent_engine modules

**Key Features:**
- **AgentEngine**: Main orchestration class
  - Executes agent loop: LLM call → tool parsing → tool execution → state recording
  - Integrates with AgentStateMachine, ToolRegistry, ContextPruner, and LLMProvider
  - SSE event emission for UI streaming
  - Crash recovery with hint injection
  - Force synthesis when max_steps reached

- **Recovery Module**: Helper functions
  - `should_retry_tool()` - Determines if tool call can be safely retried
  - `build_recovery_messages()` - Injects recovery hints into message context
  - `create_idempotency_key()` - Creates unique keys for tool call deduplication
  - `determine_recovery_actions()` - Analyzes interrupted tool calls

- **SSE Event Types:**
  - `agent_started`, `step_started`, `thinking`, `tool_start`, `tool_result`
  - `synthesizing`, `answer_token`, `agent_complete`, `agent_error`

- **AgentResult Dataclass:**
  - `success`, `final_answer`, `citations`, `total_steps`, `timing_ms`, `error_message`

**Exit Criteria Verified:**
- ✓ Agent answers "What is the population of Tokyo?" (integration test)
- ✓ Tool execution with search and synthesis
- ✓ Multi-step agent behavior (search → extract → synthesize)
- ✓ Crash recovery with hint injection
- ✓ Error handling for tool failures

**Test Coverage:** 72 new tests (31 recovery + 36 agent_engine + 5 integration), all 471 tests passing

### Phase 6: API Layer (2026-01-04)

**Summary:** Built the REST API layer for the web research agent with 5 endpoints, SSE streaming with resumption support, and comprehensive tests.

**Files Created:**
1. `orchestrator/agent/factory.py` - Factory function for creating configured AgentEngine instances
2. `orchestrator/routes/agent_runs.py` - 5 REST endpoints with SSE streaming
3. `tests/routes/__init__.py` - Routes test package
4. `tests/routes/test_agent_runs.py` - 15 comprehensive unit tests
5. `tests/integration/test_agent_e2e.py` - 6 E2E tests

**Files Modified:**
1. `orchestrator/app.py` - Added agent_runs router import and registration
2. `orchestrator/agent/__init__.py` - Added create_agent_engine export

**Key Features:**
- **REST Endpoints:**
  - `POST /api/agent/runs` - Start new agent run
  - `GET /api/agent/runs/{id}` - Get run status
  - `GET /api/agent/runs/{id}/stream` - SSE event stream
  - `POST /api/agent/runs/{id}/cancel` - Cancel active run
  - `GET /api/agent/runs/{id}/trace` - Full execution trace

- **SSE Streaming:**
  - Event translation layer (engine events → SSE events)
  - Stream resumption via `since_seq` parameter
  - Event history storage for reconnection
  - 30-second heartbeat keep-alive
  - Proper client disconnect handling

- **Factory Function:**
  - Creates AgentEngine with all dependencies
  - Provider chain integration
  - Tool registry with configured tools
  - Configuration overrides support

**Exit Criteria Verified:**
- ✓ curl can start run and stream SSE events
- ✓ All 5 endpoints functional
- ✓ SSE streaming with event types
- ✓ Cancellation support
- ✓ Trace endpoint returns steps, tool calls, citations

**Test Coverage:** 21 new tests (15 route + 6 E2E), all 492 tests passing

### Phase 7: Frontend (2026-01-04)

**Summary:** Built the complete frontend integration for the web research agent with mode toggle, real-time streaming, and citation rendering.

**Files Created:**
1. `ui/src/types/agent.ts` - TypeScript types mirroring backend schemas
2. `ui/src/hooks/useAgentSSE.ts` - Agent SSE streaming hook with state management
3. `ui/src/components/ToolCallCard.tsx` - Tool call visualization with status badges
4. `ui/src/components/CitationInline.tsx` - Inline citation with hover tooltip
5. `ui/src/components/AnswerWithCitations.tsx` - Answer rendering with [N] citation parsing
6. `ui/src/components/AgentStepsPanel.tsx` - Collapsible research progress display
7. `ui/src/components/AgentRunMessage.tsx` - Full agent run message component

**Files Modified:**
1. `ui/src/api/client.ts` - Added 5 agent API functions + SSE subscription
2. `ui/src/hooks/useStore.ts` - Added agent state slice with 9 actions and selector
3. `ui/src/components/ConversationView.tsx` - Mode toggle, agent run rendering, stop handling

**Key Features:**
- **Mode Toggle**: Chat/Research buttons to switch modes
- **Real-time Streaming**: Steps, tool calls, thinking displayed as they happen
- **Tool Visualization**: Cards showing tool name, arguments, status, duration
- **Citation Rendering**: Clickable [N] badges with hover tooltips showing title/snippet
- **Purple/Indigo Theme**: Visual distinction for agent runs vs regular chat
- **Cancellation**: Stop button with proper cleanup

**Build Status:** ✓ pnpm build succeeds (703KB bundle)

---

## Post-Phase 7: Bug Fixes (2026-01-05)

### Summary

After Phase 7 completion, several integration issues were discovered when testing the agent with LM Studio and the Parallel.ai API. This section documents the errors encountered and their fixes.

### Branch: `fix/lm-studio-tool-call-format`

---

### Error 1: LM Studio Responses API Format Mismatch

**Symptom:** Tool calls not being parsed from LM Studio responses. Raw protocol tokens like `<|channel|>commentary to=web_search` appearing in UI.

**Root Cause:** LM Studio's `/v1/responses` endpoint uses a different format than OpenAI:
- LM Studio returns `function_call` as top-level output item (not nested `tool_use`)
- Tool results need `function_call_output` format
- Tool schema needs flat structure (not nested under `"function"`)

**Files Modified:**
- `orchestrator/providers/response_parsers.py` - Handle `function_call` type in output items
- `orchestrator/providers/request_builders.py` - Transform messages/tools for responses API
- `orchestrator/providers/openai_compat.py` - Collect streaming tool calls

**Fix Commit:** `91d8932`

---

### Error 2: Parallel.ai API Parameter Changes

**Symptom:** Web search returning 422 error: `"Either 'objective' or 'search_queries' must be provided"`

**Root Cause:** Parallel.ai API updated their `/v1beta/search` endpoint:
- Changed `query` parameter to `objective`
- Changed `num_results` to `max_results`
- Requires `parallel-beta: search-extract-2025-10-10` header

**Files Modified:**
- `orchestrator/agent/tools/web_search.py` - Updated parameters and added header
- `tests/agent/tools/test_web_search.py` - Updated test assertions

**Fix Commit:** `91d8932`

---

### Error 3: `.env` File Not Loading (Tools Not Registering)

**Symptom:** Agent returning "Unknown tool: web_search" even though tool was called. Logs showed `"AgentEngine created", "tools": []` (empty array).

**Root Cause:** `python-dotenv`'s `load_dotenv()` was never called in `app.py`. The `PARALLEL_API_KEY` environment variable wasn't loaded from `.env`, so `parallel_config.api_key` was `None`, and tools weren't registered.

**Evidence from logs:**
```json
// Before fix (bad):
{"AgentEngine created", "tools": []}

// After fix (good):
{"AgentEngine created", "tools": ["web_search", "web_extract", "python_execute"]}
```

**Files Modified:**
- `orchestrator/app.py` - Added `from dotenv import load_dotenv` and `load_dotenv()` at top

**Fix Commit:** `6649bcc`

---

### Error 4: web_extract API Response Parsing Wrong

**Symptom:** All `web_extract` calls returning `"Extracted 0/1 URLs successfully"` even though API returned 200 OK with valid data.

**Root Cause:** Code expected `{"extractions": [...]}` but Parallel.ai API returns `{"results": [...], "errors": [...]}`:

| Expected (wrong) | Actual API Response |
|------------------|---------------------|
| `extractions` | `results` |
| `success: true/false` | Success in `results`, failures in `errors` |
| `content` | `excerpts` array or `full_content` |

**Files Modified:**
- `orchestrator/agent/tools/web_extract.py` - Parse `results`/`errors` instead of `extractions`
- `tests/agent/tools/test_web_extract.py` - Updated all mock responses to match API format

**Fix Commit:** `7f84a23`

---

### Error 5: E2B Sandbox API Key Parameter Error

**Symptom:** `python_execute` tool failing with error:
```
SandboxBase.__init__() got an unexpected keyword argument 'api_key'
```

**Root Cause:** E2B SDK v2.9.0 changed the API. The `Sandbox()` constructor no longer accepts `api_key` directly - it must be passed via `Sandbox.create()`:

| Wrong (constructor) | Correct (factory method) |
|---------------------|--------------------------|
| `Sandbox(api_key=...)` | `Sandbox.create(api_key=...)` |

The `Sandbox.__init__()` accepts only `**opts: Unpack[SandboxOpts]` which doesn't include `api_key`.
The `Sandbox.create()` accepts `**opts: Unpack[ApiParams]` which does include `api_key`.

**Files Modified:**
- `orchestrator/agent/tools/python_sandbox.py` - Changed `Sandbox(...)` to `Sandbox.create(...)` in `execute()` and `health_check()` methods
- `tests/agent/tools/test_python_sandbox.py` - Updated mocks to use `mock_sandbox_class.create.return_value` instead of `return_value=mock_sandbox`

**Fix Commit:** `202d1d5`

---

### Summary of All Fix Commits

| Commit | Description |
|--------|-------------|
| `91d8932` | LM Studio responses API format + Parallel.ai API param updates |
| `4a9e969` | Don't cache failed tool results + improve system prompt |
| `6649bcc` | Load `.env` file on startup for API keys |
| `7f84a23` | Parse Parallel.ai extract API response correctly |
| `202d1d5` | Fix E2B Sandbox.create() API for SDK v2.9.0 |

---

### Verification

After all fixes:
1. ✓ Tools register on startup: `["web_search", "web_extract", "python_execute"]`
2. ✓ `web_search` returns real results: `"Found 4 results for 'current weather in Japan'"`
3. ✓ `web_extract` parses content correctly from API
4. ✓ Failed tool results not cached (re-executed on retry)
5. ✓ System prompt encourages tool use

---

## Feature Enhancement: Agent Trace Events (2026-01-05)

### Summary

Added trace event recording to agent mode so the Debug Trace panel shows agent execution details. Previously, clicking "Details" on agent runs showed "No traces found" because agent mode wrote to separate tables (`agent_steps`, `agent_tool_calls`) but not to the `trace_events` table that the UI reads from.

### Branch: `feature/agent-traces`

### Problem

- Chat mode writes to `trace_events` table → DetailPanel reads via `/api/runs/{run_id}/timeline`
- Agent mode wrote to `agent_steps`, `agent_tool_calls`, `agent_citations` but NOT to `trace_events`
- Result: Debug Trace panel showed empty for agent runs

### Solution

Added trace event instrumentation to `agent_engine.py` at 8 key execution points, writing to the existing `trace_events` table. No UI changes needed.

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/agent/factory.py` | Create TraceRepo instance, pass to AgentEngine |
| `orchestrator/agent/agent_engine.py` | Add trace_repo parameter, `_add_trace_event()` helper, 8 instrumentation points |

### Events Recorded

| Event Type | When | Content |
|------------|------|---------|
| `agent_start` | Run begins | query (truncated), max_steps |
| `step_start` | Step begins | step_number, steps_remaining |
| `llm_request` | Before LLM call | model, messages_count, tools_count |
| `llm_response` | After LLM response | text_length, tool_calls_count, thinking_text |
| `tool_call` | Before tool execution | tool_name, arguments, tool_call_id |
| `tool_result` | After tool completes | tool_name, success, result_summary, duration_ms |
| `synthesis` | When synthesizing | step_number |
| `agent_complete` | Run finishes | success, total_steps, answer_length, citations_count |
| `agent_error` | On failure | error_message, total_steps |

### Test Results

- ✓ All 502 tests pass (230 agent tests + others)
- ✓ No breaking changes - trace_repo is optional parameter

### Verification

To verify:
1. Start server: `just dev`
2. Switch to Research mode in UI
3. Submit a query
4. Click "Details" button on the response
5. Debug Trace panel should show events with step numbers and thinking content

---

## Bug Fix: Streaming Retry for Network Errors (2026-01-05)

### Summary

Fixed agent requests breaking mid-stream due to network-level errors from upstream LLM providers (e.g., Parallel.ai). Error: `"peer closed connection without sending complete message body (incomplete chunked read)"`.

### Branch: `fix/agent-streaming-retry`

### Problem

- Traces showed `llm_request (pending)` with no `llm_response` - stream died mid-request
- `complete_streaming()` caught `httpx.HTTPStatusError` but not `httpx.RemoteProtocolError`
- When provider closed connection mid-stream, exception bubbled up uncaught
- Provider chain couldn't failover after streaming started (by design)

### Root Cause

Network errors during streaming (`response.aiter_lines()`) raised `httpx.RemoteProtocolError` which wasn't handled, causing immediate run failure.

### Solution

Added retry logic to `complete_streaming()` for transient network errors:
1. Extracted streaming body to `_do_streaming()` method
2. Wrapped in retry loop catching `httpx.RemoteProtocolError` and `httpx.ReadError`
3. Uses existing backoff config (`_max_retries`, `_base_delay`, `_max_delay`)

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/providers/openai_compat.py` | Extract `_do_streaming()`, add retry loop in `complete_streaming()` |

### Test Results

- ✓ All 502 tests pass
- ✓ Provider-specific tests pass: `tests/providers/test_openai_compat.py` (6 tests)

### Fix Commit: `00f6626`

---

## Bug Fix: E2B Sandbox Retry for Port Errors (2026-01-05)

### Summary

Fixed `python_execute` tool failures caused by transient E2B sandbox errors ("sandbox is running but port is not open", code 502).

### Branch: `fix/agent-python-retry-and-thinking-ui`

### Problem

- `python_execute` failing with E2B error: `{"message":"The sandbox is running but port is not open","port":49999,"code":502}`
- This is a transient error - sandbox created but port connectivity not established in time

### Root Cause

Per [E2B docs](https://e2b.dev/docs/troubleshooting/templates/49999-port-not-open):
- The `base` template doesn't start the Jupyter kernel on port 49999
- Must use `code-interpreter` template which runs `/root/.jupyter/start-up.sh`

### Solution

1. Changed E2B template from `"base"` to `"code-interpreter"`
2. Added retry logic in `execute()` method with exponential backoff (3 retries: 2s, 4s, 8s)

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/chat_config.yaml` | Change template from "base" to "code-interpreter" |
| `orchestrator/config.py` | Update default template to "code-interpreter" |
| `orchestrator/agent/tools/python_sandbox.py` | Add retry loop with exponential backoff |

---

## Bug Fix: Thinking UI Persistence After Refresh (2026-01-05)

### Summary

Fixed agent thinking/steps UI not displaying after page refresh. Previously only showed during streaming because state was in-memory only.

### Branch: `fix/agent-python-retry-and-thinking-ui`

### Problem

- `AgentRunMessage` uses `useAgentRunState()` which reads from Zustand (in-memory)
- After refresh, Zustand store empty → `agentState` undefined → no AgentStepsPanel rendered
- Backend stores data in `/api/agent/runs/{id}/trace` but UI didn't load it for historical runs
- Also found: Backend schema mismatch (route used wrong field names)

### Solution

1. Created `useAgentRunDetails` hook to load historical state from API
2. Fixed backend schema mismatch (`step_id` → `id`, `thinking_content` → `thinking_text`, `tool_call_id` → `id`, `citation_id` → `id`)
3. Updated `AgentRunMessage` to use new hook

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/routes/agent_runs.py` | Fix schema field name mismatches in trace endpoint |
| `ui/src/hooks/useAgentRunDetails.ts` | NEW: Load historical agent state from API |
| `ui/src/components/AgentRunMessage.tsx` | Use useAgentRunDetails hook |

### Test Results

- ✓ All 502 tests pass
- ✓ TypeScript compiles clean

---

## Bug Fix: E2B Sandbox Secured Access Error (2026-01-05)

### Summary

Fixed `python_execute` failing with "Template is not compatible with secured access" error.

### Problem

- E2B SDK v2.0.0+ enables secured access by default
- `code-interpreter` template uses older envd version that doesn't support secured access
- Error: `400: Template is not compatible with secured access`

### Solution

Added `secure=False` to `Sandbox.create()` call to disable secured access for the legacy template.

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/agent/tools/python_sandbox.py` | Add `secure=False` to Sandbox.create() |

---

## Bug Fix: Agent Conversation Context Missing (2026-01-05)

### Summary

Fixed agent losing context between follow-up questions. The agent would say "I don't have context on previous questions" even within the same conversation.

### Problem

- `conversation_id` passed to `AgentEngine.run()` but never used
- `_build_initial_messages()` only built `[system, current_query]` - no history
- ChatEngine correctly loads history but AgentEngine didn't follow this pattern

### Solution

1. Made `_build_initial_messages()` async and added `conversation_id` parameter
2. Load prior runs using `self._trace_repo.list_runs_for_conversation(conversation_id)`
3. Build message history (user/assistant pairs) before current query
4. Limit to last 10 runs to prevent context overflow

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/agent/agent_engine.py` | Load conversation history in `_build_initial_messages()` |

---

## Bug Fix: E2B Sandbox Port Not Ready (2026-01-05)

### Summary

Fixed `python_execute` timing out because port 49999 (Jupyter kernel) wasn't ready after sandbox creation.

### Problem

- Sandbox created successfully but `run_code` fails with "port is not open" (code 502)
- Previous retry logic recreated entire sandbox on each retry, hitting same cold-start issue
- Jupyter kernel in `code-interpreter` template needs warmup time

### Solution

1. Added 2-second warmup delay after sandbox creation
2. Retry `run_code` on the SAME sandbox instead of recreating (3 retries with 2s, 4s, 6s delays)
3. Only recreate sandbox if kernel completely fails (2 sandbox retries with 3s, 6s delays)
4. Separated sandbox creation retries from code execution retries

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/agent/tools/python_sandbox.py` | Two-tier retry: run_code retries on same sandbox, then sandbox recreation |

---

## Enhancement: Thinking Text Markdown Rendering (2026-01-05)

### Summary

Added markdown + LaTeX rendering to agent thinking text in the steps panel.

### Problem

- Thinking text displayed as raw text
- LaTeX formulas like `\(E = mc^2\)` not rendered
- Markdown formatting (bold, lists, code) not processed

### Solution

Reused existing `AnswerMarkdown` component (which handles ReactMarkdown + KaTeX + remark-math) for thinking text in `AgentStepsPanel.tsx`.

### Files Modified

| File | Changes |
|------|---------|
| `ui/src/components/AgentStepsPanel.tsx` | Render thinking text with `AnswerMarkdown` component |

---

## Feature: Query Classification for Tool Usage (2026-01-05)

### Summary

Added keyword-based query classification to improve tool usage for physics/math calculations. The agent was skipping `python_execute` for calculations and answering directly (often incorrectly). This feature detects calculation-heavy queries and enforces tool usage via the `tool_choice` parameter.

### Branch: `feature/query-classification`

### Problem

- gpt-oss model skipped `python_execute` for physics/math calculations
- Example: Relativistic energy calculation (RHIC collider) answered in 1 step without using code
- System prompt was web-research focused ("ALWAYS use web_search first")
- Tool description too generic ("Use for calculations")
- No mechanism to enforce tool usage for calculation queries

### Solution

1. **Query Classifier Module** - Keyword-based detection of physics/math queries
2. **Calculation-Aware System Prompt** - Stronger guidance for python_execute
3. **Tool Choice Enforcement** - Use `tool_choice` parameter on first step
4. **Improved Tool Description** - Made python_execute more compelling

### Files Created

| File | Purpose |
|------|---------|
| `orchestrator/agent/query_classifier.py` | QueryClassifier with keyword/unit detection and confidence scoring |
| `tests/agent/test_query_classifier.py` | 15 unit tests covering all classification scenarios |

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/agent/agent_engine.py` | Added `CALCULATION_SYSTEM_PROMPT`, `get_system_prompt_for_query_type()`, `tool_choice` parameter |
| `orchestrator/agent/factory.py` | Integrate classifier, pass `query` param, get tool_choice recommendation |
| `orchestrator/routes/agent_runs.py` | Pass query to `create_agent_engine()` |
| `orchestrator/providers/request_builders.py` | Add `tool_choice` to both request builders |
| `orchestrator/providers/base.py` | Add `tool_choice` to protocol |
| `orchestrator/providers/openai_compat.py` | Pass `tool_choice` to builders |
| `orchestrator/agent/tools/python_sandbox.py` | Improved tool description with physics examples |
| `orchestrator/chat_config.yaml` | Added `query_classification` config section |

### Key Components

**QueryClassifier:**
- Detects physics keywords: calculate, compute, energy, kinetic, momentum, velocity, force, etc.
- Detects physics units: joule, eV, keV, MeV, GeV, TeV, kg, m/s, etc.
- Allows simple arithmetic ("5+3", "what is 2*4") without tool enforcement
- Confidence = number of matched patterns
- Returns `tool_choice="python_execute"` when confidence ≥ threshold (default: 2)

**Tool Choice:**
- Only applied on first step (allows normal flow after)
- Converts tool name to OpenAI format: `{"type": "function", "name": "tool_name"}`
- Falls through to `auto` after first step

**Calculation System Prompt:**
```
CRITICAL INSTRUCTIONS FOR CALCULATIONS:
1. For ANY physics or mathematical calculation, you MUST use python_execute
2. NEVER compute physics formulas mentally or in text - always use Python code
3. Even "simple" physics (kinetic energy, velocity) MUST use python_execute
4. Only answer directly for trivial arithmetic like "2+2" or "5*3"
```

### Configuration

```yaml
query_classification:
  enabled: true
  min_confidence_for_enforcement: 2
```

### Test Results

- ✓ All 517 tests pass (15 new classifier tests + 502 existing)
- ✓ Sanity test passes (32/32)

### Example

Query: "What is the kinetic energy of a gold ion traveling at 99.7% the speed of light?"

Before:
- Classified as general query
- Model answers directly without code
- Often incorrect for relativistic calculations

After:
- Classified as CALCULATION (confidence: 4, patterns: `keyword:energy`, `keyword:kinetic`, `keyword:velocity`, `unit:c`)
- `tool_choice="python_execute"` forces first step to use code
- Model uses Python with relativistic kinetic energy formula

---

## Bug Fix: tool_choice Not Supported on Responses API (2026-01-05)

### Summary

Fixed agent runs failing with `400 Bad Request` when `tool_choice` was set and using the `/v1/responses` endpoint. LM Studio's responses API doesn't support the `tool_choice` parameter.

### Problem

- Query classification correctly detected calculation queries
- `tool_choice="python_execute"` was set
- Request to `/v1/responses` with `tool_choice` returned 400 Bad Request
- All calculation queries failed immediately

### Root Cause

LM Studio's `/v1/responses` endpoint doesn't support the `tool_choice` parameter. When we included `tool_choice` in the payload, it returned a 400 error.

### Solution

Force the `chat_completions` endpoint when `tool_choice` is set, since chat completions API does support `tool_choice`.

### Files Modified

| File | Changes |
|------|---------|
| `orchestrator/providers/openai_compat.py` | Force `chat_completions` endpoint when `tool_choice` is set |

### Code Change

```python
endpoint_type = await self._resolve_endpoint()

# Force chat_completions when tool_choice is set (responses API doesn't support it)
if tool_choice and endpoint_type == "responses":
    endpoint_type = "chat_completions"
```

### Test Results

- ✓ All 517 tests pass
- ✓ Sanity test passes (33/33)
- ✓ Python sandbox test now succeeds for calculation queries

---

## Bug Fix: Agent Thinking Not Shown After Step Completion (2026-01-07)

### Summary

Fixed agent thinking/reasoning not displaying for completed steps during streaming. The thinking was saved to the database but wasn't shown in the UI until page refresh.

### Branch: `fix/agent-thinking-persistence`

### Problem

- During streaming, thinking content accumulates in `thinkingBuffer` (a single buffer for the current step)
- When a new step starts, `thinkingBuffer` is cleared for the new step
- The previous step's `thinking_text` property was never populated in the streaming state
- UI only showed `step.thinking_text` for non-current steps, which was empty during streaming
- After page refresh, historical data loaded correctly from API

### Root Cause

The SSE stream doesn't include a `step_complete` event with `thinking_text`. The backend saves it to the database, but the frontend only receives `thinking` tokens that go into `thinkingBuffer`. When a new step starts, the buffer is cleared without saving to the step object.

### Solution

Frontend-only fix: Save `thinkingBuffer` to the step's `thinking_text` on step transitions.

### Files Modified

| File | Changes |
|------|---------|
| `ui/src/hooks/useStore.ts` | Added `updateAgentStep` action to update step properties |
| `ui/src/hooks/useAgentSSE.ts` | Save thinking to previous step on `step_start`, save final step on `handleComplete` |
| `ui/src/components/AgentStepsPanel.tsx` | Fixed display logic: live thinking for active step, historical for all completed |

### Key Changes

**useStore.ts:**
```typescript
updateAgentStep: (runId, stepNumber, updates) =>
  set((state) => {
    const current = state.agentRunState[runId];
    if (!current) return state;
    return {
      agentRunState: {
        ...state.agentRunState,
        [runId]: {
          ...current,
          steps: current.steps.map((s) =>
            s.step_number === stepNumber ? { ...s, ...updates } : s
          ),
        },
      },
    };
  }),
```

**useAgentSSE.ts (step_start handler):**
```typescript
// Save current thinking to previous step before starting new step
if (currentState && currentState.currentStep > 0 && currentState.thinkingBuffer) {
  updateAgentStep(id, currentState.currentStep, {
    thinking_text: currentState.thinkingBuffer,
    state: 'complete',
  });
}
```

**AgentStepsPanel.tsx:**
```tsx
{/* Live thinking for active current step */}
{isCurrentStep && isActive && thinkingBuffer && (...)}

{/* Historical thinking for completed steps (including current when not active) */}
{!(isCurrentStep && isActive) && step.thinking_text && (...)}
```

### Test Results

- ✓ Build succeeds: `pnpm build`
- ✓ All 245 agent tests pass
- ✓ 515 tests pass total (2 pre-existing failures in response parser tests)

---

## Bug Fix: Historical Agent Steps Not Expanding (2026-01-07)

### Summary

Fixed agent steps not expanding to show thinking text and tool calls when viewing historical (completed) runs after page refresh.

### Problem

1. **Steps collapsed by default** - Only the last step auto-expanded for historical runs
2. **Tool calls not matching steps** - DB uses UUIDs for `step_id`, but frontend expected `step-{number}` format

### Root Cause

```javascript
// OLD: Only expands current step
const isStepExpanded = expandedSteps.has(step.step_number) || isCurrentStep;

// OLD: step_id matching broken for UUIDs
const stepNum = parseInt(tc.step_id.replace('step-', ''), 10); // Returns NaN for UUIDs
```

### Solution

**AgentStepsPanel.tsx:**
```tsx
// Build step_id to step_number mapping (handles both UUID and step-N formats)
const stepIdToNumber: Record<string, number> = {};
steps.forEach((s) => {
  stepIdToNumber[s.id] = s.step_number;              // UUID mapping
  stepIdToNumber[`step-${s.step_number}`] = s.step_number; // step-N mapping
});

// Auto-expand all steps for historical (completed) runs
const isStepExpanded = expandedSteps.has(step.step_number) || isCurrentStep || !isActive;
```

### Files Modified

| File | Changes |
|------|---------|
| `ui/src/components/AgentStepsPanel.tsx` | Fixed step_id mapping and auto-expand for historical runs |

### Test Results

- ✓ Build succeeds: `pnpm build`
