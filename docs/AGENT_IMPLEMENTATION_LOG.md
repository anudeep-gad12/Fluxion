# Agent Implementation Log

> **Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.

---

## Current Status

- **Current Phase:** 5 (Agent Engine - COMPLETED)
- **Current Branch:** `feature/agent-phase-5-engine`
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

**Phase 6: API Layer** is next. To start:

```bash
# 1. Create branch from test
git checkout test
git checkout -b feature/agent-phase-6-api

# 2. Implement:
#    - orchestrator/routes/agent.py (FastAPI routes)
#    - Update orchestrator/app.py to include agent routes
#    - SSE streaming endpoint
#    - Write tests for API endpoints

# 3. Test
uv run pytest tests/routes/ -v       # Unit tests
uv run pytest                         # Full suite
./scripts/sanity_test.sh --debug      # E2E tests

# 4. Update this log with results
# 5. Merge to test branch
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

### Phase 6: API Layer - NOT STARTED
- **Branch:** `feature/agent-phase-6-api`
- **Status:** Pending
- **Files to Create:**
  - `orchestrator/routes/agent.py`
  - Update `orchestrator/app.py`
- **Exit Criteria:** curl can start run and stream SSE events

### Phase 7: Frontend - NOT STARTED
- **Branch:** `feature/agent-phase-7-frontend`
- **Status:** Pending
- **Files to Create:**
  - `ui/src/types/agent.ts`
  - `ui/src/hooks/useAgentSSE.ts`
  - `ui/src/components/AgentThinkingPanel.tsx`
  - `ui/src/components/ToolCallCard.tsx`
  - `ui/src/components/CitationInline.tsx`
  - `ui/src/components/AnswerWithCitations.tsx`
- **Exit Criteria:** Full user flow works in browser

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
