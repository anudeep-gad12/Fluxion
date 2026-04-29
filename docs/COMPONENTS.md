# Components

Detailed documentation of every component in the Fluxion system.

## Table of Contents

1. [Backend Components](#backend-components)
   - [Application Layer](#application-layer)
   - [Engine Layer](#engine-layer)
   - [Provider Layer](#provider-layer)
   - [Thinking Layer](#thinking-layer)
   - [Reporting Layer](#reporting-layer)
   - [Agent Layer](#agent-layer)
   - [Model Registry](#model-registry)
   - [Context Management](#context-management)
   - [Storage Layer](#storage-layer)
   - [Routes Layer](#routes-layer)
   - [Utilities](#utilities)
2. [CLI/TUI Components](#clitui-components)
   - [Entry Point & App](#entry-point--app)
   - [Screens](#screens)
   - [Widgets](#widgets)
   - [Events](#events)
   - [CLI API Client](#cli-api-client)
   - [CLI Configuration](#cli-configuration)
3. [Frontend Components](#frontend-components)
   - [Core Components](#core-components)
   - [Message Components](#message-components)
   - [Agent Components](#agent-components)
   - [UI Primitives](#ui-primitives)
   - [Hooks](#hooks)
   - [API Client](#api-client)

---

# Backend Components

## Application Layer

### `orchestrator/app.py`

**Purpose**: FastAPI application entry point with middleware, routing, and lifecycle management.

**Key Elements**:

| Element | Type | Description |
|---------|------|-------------|
| `app` | FastAPI | Main application instance |
| `lifespan` | async context manager | Startup/shutdown lifecycle |
| `RequestLoggingMiddleware` | Middleware | Request ID correlation, timing |
| `SecurityHeadersMiddleware` | Middleware | Security headers (X-Frame-Options, X-Content-Type-Options, CSP, etc.) |
| `RateLimitMiddleware` | Middleware | IP-based rate limiting for demo mode |

**Endpoints**:
- `GET /api/health` - Health check
- `GET /api/config` - Current configuration
- `GET /api/usage` - Per-session message usage `{limit, used, remaining}`

**Lifespan Events**:
```python
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    config = load_config()
    await get_db().initialize()
    await cleanup_orphaned_data()  # Clean up runs/steps from crashes
    yield
    # Shutdown
    await cleanup()
```

**Orphaned Data Cleanup** (on startup):
- Marks runs with `status='running'` as `'failed'`
- Marks tool_calls with `status='running'/'pending'` as `'interrupted'`
- Marks steps with `state='tool_calling'/'planning'` as `'error'`
- Prevents UI showing spinners for orphaned runs after server restart

### `orchestrator/config.py`

**Purpose**: Configuration loading and validation from `chat_config.yaml`.

**Key Classes**:

| Class | Description |
|-------|-------------|
| `ProviderConfig` | LLM endpoint settings, retry policy |
| `ChatModelConfig` | Model parameters (temp, max_tokens) |
| `ChatContextConfig` | Conversation history limits |
| `ThinkingConfig` | Thinking strategy settings |
| `DemoConfig` | Demo mode settings (rate limiting, sidebar lock) |
| `RateLimitConfig` | Rate limiting thresholds for demo mode |
| `ChatConfig` | Root config combining all |

**Key Functions**:
- `load_config()` - Load and validate from YAML
- `_resolve_env_vars()` - Resolve `${VAR:-default}` syntax

**Environment Variable Resolution**:
```python
# Syntax
${VAR}          # Required, error if not set
${VAR:-default} # Optional with default
```

### `orchestrator/schemas.py`

**Purpose**: Pydantic models for API request/response validation.

**Request Models**:
- `CreateConversationRequest`
- `CreateConversationRunRequest`
- `CreateRunRequest`
- `CreateAgentRunRequest`

**Response Models**:
- `ConversationResponse`, `ConversationDetailResponse`
- `RunResponse`, `RunListResponse`
- `EventResponse`
- `TraceEventResponse`, `RunTimelineResponse`
- `AgentStepResponse`, `AgentToolCallResponse`, `AgentCitationResponse`
- `AgentRunStatusResponse`, `AgentRunTraceResponse`

### `orchestrator/logging_config.py`

**Purpose**: Structured JSON logging with request correlation.

**Features**:
- JSON formatted logs
- Request ID via contextvars
- Secret redaction (API keys, passwords)
- Dual output: console + file rotation

---

## Middleware Layer

### `orchestrator/middleware/rate_limit.py`

**Purpose**: IP-based rate limiting middleware for demo mode deployments.

**Classes**:

**`InMemoryRateLimiter`**
- Tracks requests per IP per endpoint type
- Sliding window algorithm
- Returns (allowed, remaining, reset_seconds)

**`RateLimitMiddleware`**
- Only active when `demo.enabled=true` in config
- Limits POST requests to expensive endpoints:
  - `/api/agent/runs` → 10/hour (agent runs)
  - `/api/runs` → 30/hour (chat runs)
  - `/api/conversations/{id}/runs` → 30/hour (chat runs)
- Returns 429 with retry info when limit exceeded
- Adds X-RateLimit-* headers to responses
- Whitelists localhost IPs by default

**Key Function**:
- `get_client_ip(request)` - Extracts client IP from X-Forwarded-For, X-Real-IP, or direct connection

**Configuration** (via `chat_config.yaml`):
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

### `orchestrator/middleware/session.py`

**Purpose**: Cookie-based session isolation for demo mode user separation.

**Classes**:

**`SessionMiddleware`**
- Only active when `demo.enabled=true` in config
- Mints `demo_session` cookie (UUID, 30-day TTL) for new visitors
- Sets `request.state.session_id` and `request.state.is_owner` for route handlers
- Owner detection via `?owner=<secret>` query param or `X-Owner-Token` header
- Cookie attributes: HttpOnly, Secure (in production), SameSite=lax

**Session Isolation Logic**:
- Each user gets unique session ID stored in cookie
- Conversations and runs are tagged with `session_id` at creation
- List endpoints filter by session (non-owners only see their own data)
- Direct access endpoints return 404 for wrong session (no existence leak)
- NULL `session_id` in DB = owner-only (legacy data protection)

**Key Functions**:
- `_is_secure_context()` - Detects HTTPS for Secure cookie flag
- `_set_session_cookie()` - Sets cookie with all security attributes
- `_check_owner()` - Validates owner secret from query param or header

**Security Design**:
| Scenario | Behavior |
|----------|----------|
| Unknown conversation_id | 404 |
| Known ID, wrong session | 404 (same as unknown) |
| NULL session_id in DB | Owner-only |
| Forged cookie | Gets different session |

---

## Engine Layer

### `orchestrator/engine/chat_engine.py`

**Purpose**: Core chat orchestration - the heart of the system.

**Class: `ChatEngine`**

**Constructor**:
```python
def __init__(self, config: ChatConfig, trace_repo: TraceRepo):
    self.config = config
    self.trace_repo = trace_repo
    self.provider = create_provider(config.provider, config.model)
    self.thinking_orchestrator = ThinkingOrchestrator()
```

**Key Methods**:

| Method | Description |
|--------|-------------|
| `chat()` | Main entry point - process message and return result |
| `_build_messages()` | Build message list from history |
| `_call_model_streaming()` | Streaming model call with token callbacks |

**`chat()` Flow**:
1. Verify conversation exists
2. Load prior runs from database
3. Build message list (system + history + user)
4. Create run record (status=running)
5. Execute thinking strategy
6. Record trace events
7. Update run (final_answer, status=succeeded)
8. Return `ChatResult`

**`_call_model_streaming()` Details**:
- Wraps `LLMProvider.complete_streaming()`
- Uses `StreamParser` to separate thinking/answer tokens
- Routes tokens to appropriate SSE events
- Handles native reasoning (gpt-oss) via `on_reasoning` callback

---

## Provider Layer

### `orchestrator/providers/base.py`

**Purpose**: Provider protocol definition and shared types.

**Protocol: `LLMProvider`**

```python
class LLMProvider(Protocol):
    async def complete(messages, max_tokens, temperature, tools, ...) -> LLMResponse
    async def complete_streaming(messages, on_token, on_reasoning, ...) -> LLMResponse
    async def health_check() -> bool
    async def close() -> None
```

**Dataclass: `LLMResponse`**

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Generated content |
| `tool_calls` | List[Dict] | Function calls |
| `reasoning` | str | Native reasoning (gpt-oss) |
| `response_id` | str | For stateful mode |
| `endpoint_used` | str | Which endpoint was used |
| `usage` | Dict | Token counts |
| `finish_reason` | str | Stop reason |

### `orchestrator/providers/openai_compat.py`

**Purpose**: OpenAI-compatible provider supporting LM Studio, vLLM, Ollama, etc.

**Class: `OpenAICompatProvider`**

**Features**:
- Dual endpoint support (`/v1/responses`, `/v1/chat/completions`)
- Automatic fallback on 404/405
- Exponential backoff retry
- Streaming with token callbacks
- Native reasoning support

**Key Methods**:

| Method | Description |
|--------|-------------|
| `complete()` | Non-streaming completion |
| `complete_streaming()` | Streaming with callbacks |
| `_resolve_endpoint()` | Auto-detect supported endpoint |
| `_request_with_retry()` | Retry with exponential backoff |
| `_do_streaming()` | SSE stream processing |

**Endpoint Resolution**:
```
1. If endpoint="responses", try /v1/responses
2. If 404/405 and fallback_on_404=true, use /v1/chat/completions
3. Cache result for session
```

### `orchestrator/providers/chain.py`

**Purpose**: Multi-provider failover with circuit breakers.

**Class: `ProviderChain`**

**Implements**: `LLMProvider` protocol

**Behavior**:
1. Sort providers by priority (lower = first)
2. For each provider:
   - Check circuit breaker state
   - If OPEN, skip to next
   - If CLOSED/HALF_OPEN, attempt request
   - Record success/failure
3. If all fail, raise `AllProvidersFailedError`

### `orchestrator/providers/circuit_breaker.py`

**Purpose**: Circuit breaker pattern implementation.

**Class: `CircuitBreaker`**

**States**:
- `CLOSED` - Healthy, requests flow through
- `OPEN` - Unhealthy, requests rejected
- `HALF_OPEN` - Testing, limited requests allowed

**Configuration**:
- `failure_threshold`: 5 failures to open
- `recovery_timeout_seconds`: 30s
- `success_threshold`: 2 to close

### `orchestrator/providers/chatgpt.py`

**Purpose**: ChatGPT OAuth provider translating to Codex Responses API.

**Class: `ChatGPTProvider`**

**Features**:
- OAuth access token from CLI `/login` flow
- Translates chat completions format → Codex Responses API (`chatgpt.com/backend-api/codex/responses`)
- Request translation: system → instructions, tools → flattened format
- Response translation: `output_text.delta` → content, `reasoning_summary_text.delta` → reasoning, `function_call` → tool calls
- Token refresh via `update_token()`
- Exponential backoff retry (3 max)

**Key Methods**:

| Method | Description |
|--------|-------------|
| `complete()` | Non-streaming completion via Codex API |
| `complete_streaming()` | Streaming with delta translation |
| `update_token(token)` | Refresh OAuth access token |
| `health_check()` | Validate token is still valid |

**Models**: gpt-5.2-codex, o4-mini, gpt-4o, o3

### `orchestrator/providers/factory.py`

**Purpose**: Create provider instances based on config.

**Function: `create_provider()`**

```python
def create_provider(provider_config, model_config) -> LLMProvider:
    if provider_config.chain_config.enabled:
        return ProviderChain(...)
    else:
        return OpenAICompatProvider(...)
```

### `orchestrator/providers/request_builders.py`

**Purpose**: Build request payloads for different endpoints.

**Functions**:
- `build_responses_request()` - For `/v1/responses`
- `build_chat_completions_request()` - For `/v1/chat/completions`

**Transformations**:
- Convert chat roles to response API format
- Handle tool definitions
- Include reasoning_effort for gpt-oss
- **Reasoning model detection**: Models starting with `gpt-5`, `o1`, `o3`, `o4` automatically use `max_completion_tokens` (instead of `max_tokens`) and skip the `temperature` parameter, per OpenAI API requirements

### `orchestrator/providers/response_parsers.py`

**Purpose**: Parse responses from different endpoints.

**Functions**:
- `parse_responses_result()` - Parse `/v1/responses`
- `parse_chat_result()` - Parse `/v1/chat/completions`
- `parse_streaming_delta()` - Parse SSE delta events

---

## Thinking Layer

### `orchestrator/thinking/base.py`

**Purpose**: Base classes and stream parsing for thinking strategies.

**Class: `StreamParser`**

**Purpose**: Separate thinking from answer tokens in real-time.

**Detects**:
- `[THINK]...[/THINK]` tags
- `<think>...</think>` tags
- Harmony format: `<|channel|>final<|message|>`
- Native reasoning: `[THINK_NATIVE]` marker

**Method: `feed(token)`**:
```python
def feed(self, token: str) -> Tuple[Optional[str], Optional[str]]:
    # Returns (thinking_token, answer_token)
    # Only one will be non-None at a time
```

**Dataclass: `ThinkingStep`**

| Field | Description |
|-------|-------------|
| `seq` | Step sequence number |
| `step_type` | "reasoning", "critique", etc. |
| `raw_content` | Full unfiltered output |
| `ui_summary` | Clean summary for UI |
| `ui_status` | "thinking", "done" |
| `tokens` | Token counts |
| `timing_ms` | Execution time |

**Dataclass: `ThinkingResult`**

| Field | Description |
|-------|-------------|
| `steps` | List of ThinkingStep |
| `final_answer` | Generated response |
| `thinking_summary` | For UI display |
| `thinking_tokens` | Tokens used for thinking |
| `answer_tokens` | Tokens used for answer |

**ABC: `ThinkingStrategy`**

```python
class ThinkingStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def think(self, messages, model_call, event_callback) -> ThinkingResult: ...
```

### `orchestrator/thinking/orchestrator.py`

**Purpose**: Strategy registry and routing.

**Class: `ThinkingOrchestrator`**

**Registered Strategies**:
```python
_default_strategies = {
    "direct": DirectStrategy,
}
```

**Methods**:

| Method | Description |
|--------|-------------|
| `get_strategy(name, **kwargs)` | Get strategy instance by name (uses default if None) |
| `register_strategy(name, cls)` | Register a custom strategy at runtime |
| `list_strategies()` | List all registered strategy names |
| `has_strategy(name)` | Check if a strategy is registered |

**Extending with Custom Strategies**:

To add a custom thinking strategy:

1. Create a class inheriting from `ThinkingStrategy`:
```python
from orchestrator.thinking.base import ThinkingStrategy

class MyCustomStrategy(ThinkingStrategy):
    async def think(self, messages, model_call):
        # Custom reasoning logic
        ...
        return ThinkingResult(final_answer=..., thinking_summary=...)
```

2. Register the strategy:
```python
orchestrator = ThinkingOrchestrator()
orchestrator.register_strategy("my_custom", MyCustomStrategy)
strategy = orchestrator.get_strategy("my_custom")
```

**Error Handling**:
- Raises `ValueError` if strategy name not found
- Raises `TypeError` if registered class doesn't inherit from `ThinkingStrategy`

---

### `orchestrator/thinking/strategies/direct.py`

**Purpose**: Single model call with no explicit thinking.

**Class: `DirectStrategy`**

**Behavior**:
1. Single `model_call(messages)`
2. Capture native reasoning if available
3. Return response as `final_answer`
4. Use reasoning as `thinking_summary`

**Use Case**: Fast responses, gpt-oss models with native reasoning.

---

## Reporting Layer

### `orchestrator/reporting/report_builder.py`

**Purpose**: Generate human-readable reports from run traces.

**Class: `ReportBuilder`**

**Constructor**:
```python
def __init__(self, format: str = "markdown") -> None:
    self._format = format
    self._sections: list[dict[str, Any]] = []
```

**Methods**:

| Method | Description |
|--------|-------------|
| `add_summary(run_id, status)` | Add a summary section to the report |
| `build()` | Generate final report as string |
| `build_timeline(events)` | Build structured timeline from events |

**Usage**:
```python
builder = ReportBuilder(format="markdown")
builder.add_summary(run_id="run_001", status="succeeded")
report = builder.build()
# Returns: "# Chat Report\n\n**Run ID**: run_001\n**Status**: succeeded\n"
```

**Used By**: `/api/runs/{run_id}/report` endpoint for generating markdown reports.

---

## Agent Layer

### `orchestrator/agent/factory.py`

**Purpose**: Factory for creating fully configured AgentEngine instances with all dependencies.

**Key Function**:

```python
async def create_agent_engine(
    model_name: Optional[str] = None,
    max_steps: Optional[int] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    system_prompt: Optional[str] = None,
    query: Optional[str] = None,
) -> AgentEngine
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | str | config | Override model name |
| `max_steps` | int | 10 | Maximum agent steps |
| `max_tokens` | int | config | Override max tokens |
| `temperature` | float | config | Override temperature |
| `system_prompt` | str | None | Override system prompt |
| `query` | str | None | User query for classification |

**Behavior**:
1. Loads configuration from `chat_config.yaml`
2. Resolves profile from `profile_name` (or `filesystem_enabled` flag)
3. If `query` provided (and classification enabled), classifies query to select appropriate system prompt
4. Resolves model from registry **only for known presets** (alias or model_id match); unknown models fall through to `config.provider` (reads `LLM_BASE_URL` + `LLM_API_KEY`)
5. Creates provider: override > registry-resolved model > config defaults (with chain if configured)
6. Creates tool registry from profile, repositories (AgentRepo, TraceRepo)
7. Gathers context via profile's context strategy
8. Returns configured AgentEngine with `planning_enabled=False` (disabled: extra LLM call adds latency/cost with no benefit)

**Query Classification**:
- Uses `QueryClassifier` to detect query type (calculation, research, general)
- For high-confidence calculation queries, only provides `python_execute` tool
- Forces code-based solutions for math problems

**Usage**:
```python
engine = await create_agent_engine(query="What is 15% of 847?")
result = await engine.run(run_id, query)
```

---

### `orchestrator/agent/agent_engine.py`

**Purpose**: Agent loop with tool calling and synthesis.

**Class: `AgentEngine`**

**Constructor Dependencies**:
- `LLMProvider` - For model calls
- `ToolRegistry` - Available tools
- `AgentRepo` - Persistence
- `TraceRepo` - Tracing

**Key Methods**:

| Method | Description |
|--------|-------------|
| `run()` | Main agent loop |
| `_execute_step()` | Single step execution |
| `_execute_tool()` | Tool execution with idempotency |
| `_synthesize()` | Generate final answer |
| `_force_synthesis()` | Synthesize when hitting max steps |
| `_extract_finding_from_result()` | Extract key findings from tool results |
| `_create_plan()` | Generate research plan before execution |
| `_inject_plan_into_messages()` | Append plan to system message |
| `_check_pause()` | Block if pause_signal is cleared; resume on resume_signal |
| `_inject_steer_messages()` | Drain steer queue and inject as user-role messages |

**Agent Execution Flow**:
```python
# 1. Planning Step (optional, if enabled)
if planning_enabled:
    plan = await planner.create_plan(query)
    messages = _inject_plan_into_messages(messages, plan)

# 2. Main Agent Loop
while not (synthesis or step >= max_steps):
    1. Prune context with LLM summarization (query-aware)
    2. Call LLM with tool schemas
    3. Parse response:
       - tool_calls → execute tools
       - synthesize decision → break loop
    4. Extract findings from tool results
    5. Update plan progress tracking
    6. Track token usage
    7. Record step in database
    8. Emit SSE events
```

**Message Alternation** (for Mistral compatibility):
- Plan is appended to system message content, not added as separate message
- Incomplete runs (no assistant response) are skipped from history
- Duplicate user queries are filtered out

**Findings Accumulator**:
- `_findings` list tracks key findings from tool results
- Extracts query-relevant facts from web_search/web_extract
- Included in forced synthesis prompt when hitting max steps
- Improves answer quality for complex multi-step queries

**Token Tracking**:
- `_total_tokens` accumulates tokens from all LLM calls
- Includes planning steps, tool calling, and synthesis
- Returned in `AgentResult.total_tokens`
- Displayed in UI footer with duration

**Crash Recovery**:
- Idempotency keys for tool calls
- State reconstruction from database
- Execution attempt tracking

### `orchestrator/agent/state_machine.py`

**Purpose**: Agent state management.

**Class: `AgentStateMachine`**

**States**:
- `INIT` - Starting
- `PLANNING` - Deciding next action
- `TOOL_CALLING` - Executing tools
- `SYNTHESIZING` - Generating answer
- `PAUSED` - Blocked between steps (via pause_signal)
- `COMPLETE` - Done
- `ERROR` - Failed

**Transitions**:
- `start()` - INIT → PLANNING
- `call_tools()` - PLANNING → TOOL_CALLING
- `synthesize()` - * → SYNTHESIZING
- `pause()` - STEP_LOOP → PAUSED (blocks on pause_signal)
- `resume()` - PAUSED → STEP_LOOP (unblocks via resume_signal)
- `complete()` - SYNTHESIZING → COMPLETE
- `error()` - * → ERROR

### `orchestrator/agent/context_pruner.py`

**Purpose**: Manage context within token budget with LLM-based smart summarization.

**Class: `ContextPruner`**

**Key Methods**:
- `prune()` - Synchronous pruning (basic truncation)
- `prune_async()` - Async pruning with LLM summarization
- `set_llm(provider, model, query)` - Configure LLM for smart summaries

**Strategy**:
1. Calculate current token usage
2. If over budget, summarize oldest tool results
3. Use LLM to extract query-relevant facts (content > 500 chars)
4. Cache summaries to prevent duplicate LLM calls
5. Fall back to basic truncation on error
6. Python output keeps head/tail pattern (not LLM summarized)

**Configuration**:
- `MAX_SUMMARY_TOKENS = 400` - Token limit for summary LLM calls
- `keep_full_steps` - Number of recent steps to keep detailed (default: 2)

### `orchestrator/agent/query_classifier.py`

**Purpose**: Classify query type for tool selection.

**Class: `QueryClassifier`**

**Categories**:
- `GENERAL` - General questions
- `CALCULATION` - Math/computation
- `WEB_RESEARCH` - Web search needed

**Method**: Keyword-based classification (not LLM).

### `orchestrator/agent/planner.py`

**Purpose**: Generate research plans before agent execution.

**Class: `Planner`**

**Constructor**:
```python
def __init__(
    self,
    provider: LLMProvider,
    model_name: str,
    max_plan_steps: int = 5,
) -> None
```

**Key Methods**:

| Method | Description |
|--------|-------------|
| `create_plan(query)` | Generate a ResearchPlan for the query |
| `_parse_plan_response()` | Extract structured plan from LLM response |

**Planning Prompt**:
- Analyzes query complexity
- Suggests tool usage per step
- Limits steps to `max_plan_steps`
- Returns structured plan with analysis and steps

**Dataclass: `ResearchPlan`**

| Field | Type | Description |
|-------|------|-------------|
| `analysis` | str | Brief analysis of the query |
| `approach` | str | High-level approach description |
| `steps` | list[PlanStep] | Ordered list of execution steps |

**Dataclass: `PlanStep`**

| Field | Type | Description |
|-------|------|-------------|
| `number` | int | Step number (1-indexed) |
| `description` | str | What to do in this step |
| `tool_hint` | str | Suggested tool (web_search, python_execute, etc.) |

**Plan Injection**:
The plan is appended to the system message content (not as a separate message) to maintain strict user/assistant message alternation required by models like Mistral.

### `orchestrator/agent/recovery.py`

**Purpose**: Crash recovery support.

**Functions**:
- `rebuild_state_from_db()` - Reconstruct agent state
- `create_idempotency_key()` - Hash for tool call dedup
- `build_recovery_messages()` - Resume context

### `orchestrator/agent/profile.py`

**Purpose**: Agent profile definitions with tool sets, system prompts, and context strategies.

**Dataclass: `AgentProfile`**

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | `"research"` or `"coding"` |
| `display_name` | str | UI label |
| `system_prompt_template` | str | With `{date_context}` and `{project_context}` slots |
| `tool_sets` | list[str] | `["web", "python", "filesystem"]` |
| `context_strategy` | str | `"research"` or `"coding"` |
| `planning_prompt_template` | str | Profile-specific planner prompt |
| `plan_step_types` | list[str] | Valid step types per profile |
| `max_steps` | int | Agent step limit |
| `max_plan_steps` | int | Planner step limit |
| `findings_tools` | list[str] | Tools producing findings for synthesis |

**Built-in Profiles**:

| Profile | Tool Sets | Context | Step Types | Max Steps |
|---------|-----------|---------|------------|-----------|
| `research` | web, python | Date + cutoff | search, extract, calculate, synthesize | 25 |
| `coding` | web, python, filesystem | 5-layer project context | read, implement, test, debug, synthesize | 30 |

**System Prompt Structure** (both profiles):
- UNDERSTAND INTENT section
- STEP BACK WHEN STUCK rule
- STAY ON TASK directive
- TOOLS section (profile-specific tool list)
- RULES section (quality guardrails)
- STOPPING CRITERIA (when to synthesize)

### `orchestrator/agent/context.py`

**Purpose**: Context strategies that inject profile-specific information into the system prompt.

**Class: `ResearchContextStrategy`**
- Returns current date + knowledge cutoff message

**Class: `CodingContextStrategy`**
- Gathers 5-layer project context concurrently via asyncio:
  1. **Environment**: OS, Python version, Node version
  2. **Project rules**: `.reasoner/rules.md`, `CLAUDE.md`, or `AGENTS.md`
  3. **Structure**: File tree (max 3 levels, 60 entries) + dependencies (pyproject.toml, package.json)
  4. **Git state**: Branch, status (short), last 3 commits
  5. **Working directory**: Path for context
- Token budget: ~400 tokens total across all layers
- Subprocess timeout: 5 seconds per command
- Graceful fallback if any command fails

### `orchestrator/agent/tools/base.py`

**Purpose**: Base tool protocol and shared types.

**Protocol: `BaseTool`**

```python
class BaseTool(Protocol):
    name: str
    schema: ToolSchema

    async def execute(self, **kwargs) -> ToolResult: ...
    async def health_check(self) -> bool: ...
    async def close(self) -> None: ...
```

**Dataclass: `ToolResult`**

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Execution success |
| `summary` | str | 1-line summary for DB storage |
| `result_data` | str | Full result (in-memory only, not persisted) |
| `error` | str | Error message |
| `duration_ms` | int | Execution duration |
| `metadata` | dict | Tool-specific metadata |

**Dataclass: `ToolSchema`**

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Tool identifier |
| `description` | str | Human-readable description |
| `parameters` | dict | JSON Schema for arguments |
| `is_idempotent` | bool | Safe to retry |
| `permission_level` | str | `"auto"`, `"confirm"`, or `"dangerous"` |

**Exception Classes**:
- `ToolError` — Base exception
- `ToolTimeoutError` — Execution timeout
- `ToolExecutionError` — Runtime failure

### `orchestrator/agent/tools/registry.py`

**Purpose**: Tool registration and management.

**Class: `ToolRegistry`**

**Methods**:
- `register(tool)` - Add tool to registry
- `get(name)` - Get tool by name
- `get_schemas()` - OpenAI function schemas for LLM
- `initialize()` - Setup all tools
- `cleanup()` - Cleanup resources

### `orchestrator/agent/tools/web_search.py`

**Purpose**: Web search via Parallel.ai.

**Class: `WebSearchTool`**

**Schema**:
```python
{
    "name": "web_search",
    "description": "Search the web for information",
    "parameters": {
        "query": {"type": "string", "description": "Search query"}
    }
}
```

**Registration**: Requires `PARALLEL_API_KEY` to be set.

### `orchestrator/agent/tools/web_extract.py`

**Purpose**: Content extraction from URLs.

**Class: `WebExtractTool`**

**Schema**:
```python
{
    "name": "web_extract",
    "description": "Extract content from a URL",
    "parameters": {
        "url": {"type": "string", "description": "URL to extract from"}
    }
}
```

**Registration**: Requires `PARALLEL_API_KEY` to be set.

### `orchestrator/agent/tools/python_local.py`

**Purpose**: Local Python code execution (default provider).

**Class: `LocalPythonTool`**

**Schema**:
```python
{
    "name": "python_execute",
    "description": "Execute Python code",
    "parameters": {
        "code": {"type": "string", "description": "Python code to execute"}
    }
}
```

**Features**:
- Subprocess execution via `python3 -c`
- Configurable timeout (default 30s)
- Stdout/stderr capture
- No API key required

**Registration**: Used when `PYTHON_PROVIDER=local` (default).

### `orchestrator/agent/tools/python_daytona.py`

**Purpose**: Secure Python execution in Daytona cloud sandbox.

**Class: `DaytonaPythonTool`**

**Features**:
- Secure isolated execution via Daytona SDK
- ~90ms startup time
- Same schema as `LocalPythonTool`
- Ideal for production deployments (Railway, etc.)

**Registration**: Used when `PYTHON_PROVIDER=daytona`. Requires `DAYTONA_API_KEY`.

### `orchestrator/agent/tools/python_sandbox.py`

**Purpose**: Python execution in E2B sandbox (deprecated).

**Class: `PythonSandboxTool`**

**Note**: This tool exists but is not registered. Use `LocalPythonTool` or `DaytonaPythonTool` instead.

### `orchestrator/agent/tools/bash_tool.py`

**Purpose**: Shell command execution with persistent working directory.

**Class: `BashTool`**

**Permission**: `dangerous` (always requires approval unless yolo mode)

**Schema**:
```python
{
    "name": "bash",
    "parameters": {
        "command": {"type": "string", "description": "Shell command to execute"},
        "timeout": {"type": "integer", "description": "Timeout in seconds (max 600)"}
    }
}
```

**Features**:
- Persistent working directory across calls
- Configurable timeout (default 120s, max 600s)
- Output truncated at 30,000 chars
- Returns exit code, stdout, stderr in metadata

### `orchestrator/agent/tools/read_file.py`

**Purpose**: File reading with line numbers and pagination.

**Class: `ReadFileTool`**

**Permission**: `auto` (read-only, no approval needed)

**Schema**:
```python
{
    "name": "read_file",
    "parameters": {
        "file_path": {"type": "string"},
        "offset": {"type": "integer", "description": "Start line (1-based)"},
        "limit": {"type": "integer", "description": "Max lines (default 2000)"}
    }
}
```

**Features**:
- 1-based line numbering (cat -n style)
- Binary file detection (rejects null bytes)
- Long line truncation at 2000 chars
- Path resolution relative to working_dir

### `orchestrator/agent/tools/write_file.py`

**Purpose**: File creation or overwrite.

**Class: `WriteFileTool`**

**Permission**: `confirm` (requires approval in strict/relaxed modes)

**Schema**:
```python
{
    "name": "write_file",
    "parameters": {
        "file_path": {"type": "string"},
        "content": {"type": "string"}
    }
}
```

**Features**:
- Auto-creates parent directories
- Path validation within working directory

### `orchestrator/agent/tools/edit_file.py`

**Purpose**: Exact string find-and-replace editing.

**Class: `EditFileTool`**

**Permission**: `confirm` (requires approval in strict/relaxed modes)

**Schema**:
```python
{
    "name": "edit_file",
    "parameters": {
        "file_path": {"type": "string"},
        "old_string": {"type": "string", "description": "Exact text to find"},
        "new_string": {"type": "string", "description": "Replacement text"}
    }
}
```

**Features**:
- `old_string` must appear exactly once (prevents ambiguous edits)
- Diff-style summary of changes
- No regex — exact match only for reliability

### `orchestrator/agent/tools/glob_tool.py`

**Purpose**: File pattern matching.

**Class: `GlobTool`**

**Permission**: `auto` (read-only)

**Schema**:
```python
{
    "name": "glob",
    "parameters": {
        "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')"},
        "path": {"type": "string", "description": "Directory to search in"}
    }
}
```

**Features**:
- Results sorted by modification time (most recent first)
- Skips: `.git`, `__pycache__`, `node_modules`, `.venv`, `.env`, `.tox`, `.mypy_cache`
- Max 1000 results with truncation indicator
- Relative path display

### `orchestrator/agent/tools/grep_tool.py`

**Purpose**: Regex content search across files.

**Class: `GrepTool`**

**Permission**: `auto` (read-only)

**Schema**:
```python
{
    "name": "grep",
    "parameters": {
        "pattern": {"type": "string", "description": "Regex pattern"},
        "path": {"type": "string", "description": "File or directory to search"},
        "glob": {"type": "string", "description": "File filter (e.g., '*.py')"},
        "context": {"type": "integer", "description": "Context lines before/after"}
    }
}
```

**Features**:
- Uses `ripgrep` (`rg`) if available, falls back to Python `re` module
- File glob filtering
- Configurable context lines
- Max results (default 50)
- Skips binary files

### `orchestrator/agent/tools/list_directory.py`

**Purpose**: Tree-style directory listing.

**Class: `ListDirectoryTool`**

**Permission**: `auto` (read-only)

**Schema**:
```python
{
    "name": "list_directory",
    "parameters": {
        "path": {"type": "string", "description": "Directory to list"},
        "recursive": {"type": "boolean", "description": "Include subdirectories"},
        "max_depth": {"type": "integer", "description": "Max depth (default 3)"}
    }
}
```

**Features**:
- Tree connectors (├──, └──, │)
- File sizes formatted as B/KB/MB/GB
- Respects `.gitignore` patterns
- Max 500 entries with truncation

---

## Model Registry

### `orchestrator/models/registry.py`

**Purpose**: Multi-provider model registry for resolving model strings to full provider configurations.

**Key Classes**:

| Class | Description |
|-------|-------------|
| `ProviderDef` | Definition of an LLM provider endpoint (name, base_url, api_key_env, endpoint) |
| `ModelPreset` | Known model with configuration (model_id, display_name, provider, aliases, context_window, etc.) |
| `ResolvedModel` | Fully resolved configuration ready for provider creation |
| `ModelRegistry` | Registry with resolve() and list_models() methods |

**Provider Registry** (`PROVIDERS` dict):

| Provider | Base URL | API Key Env |
|----------|----------|-------------|
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| `deepinfra` | `https://api.deepinfra.com/v1/openai` | `DEEPINFRA_API_KEY` |
| `fireworks` | `https://api.fireworks.ai/inference/v1` | `FIREWORKS_API_KEY` |
| `local` | `http://localhost:8080/v1` | (none) |

**Model Resolution** (`ModelRegistry.resolve()`):
1. Exact alias match (e.g., `"qwen3-72b"` → preset)
2. Provider prefix (e.g., `"deepinfra:meta-llama/..."`)
3. Unknown model fallback with auto-provider detection

**Key Methods**:
- `resolve(model_str)` — Resolve alias/prefix to `ResolvedModel`
- `list_models()` — List all presets grouped by provider with availability

---

## Context Management

### `orchestrator/context/budget.py`

**Purpose**: Token budget tracking for context window management.

**Key Function**: `context_params_for_model(model_name, config_max_tokens, config_reserve) -> tuple[int, int]`
- Resolves context parameters from the model registry (context_window, max_output_tokens)
- Only resolves known presets (alias or model_id match in registry indexes)
- Falls back to config values if model is not found; applies a 32768 floor on max_tokens

**Key Class**: `ContextBudget` (dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `max_tokens` | int | Total context budget (e.g. 100000) |
| `reserve_for_response` | int | Tokens reserved for model output (e.g. 4096) |
| `system_prompt_tokens` | int | Tokens consumed by system prompt |
| `plan_tokens` | int | Tokens consumed by planning |
| `current_query_tokens` | int | Tokens consumed by current user query |
| `history_tokens` | int | Tokens consumed by conversation history |

**Properties**:
- `available_for_history` — Tokens remaining for history (max - reserve - system - plan - query)
- `total_used` — Sum of all component token counts
- `utilization_pct` — Percentage of max_tokens currently used

### `orchestrator/context/context_profile.py`

**Purpose**: Resolve one normalized active-model context profile across registry models, custom OpenAI-compatible providers, local runtimes, and config fallback.

**Key Dataclass**: `ModelContextProfile`
- `provider_name`
- `model_id`
- `display_name`
- `context_window`
- `max_output_tokens`
- `effective_input_budget`
- `supports_tools`
- `supports_reasoning`
- `pricing`
- `source`

**Key Function**: `resolve_model_context_profile(...)`
- Registry source → known preset metadata
- Custom source → provider override metadata
- Local source → running llama/MLX provider metadata
- Config fallback → `chat_config.yaml` values when no richer source exists

### `orchestrator/context/history_builder.py`

**Purpose**: Budget-aware conversation history construction.

**Key Class**: `HistoryBuilder`
- Loads conversation turns within token budget
- Prefers full messages; falls back to turn summaries when over budget
- Respects `max_messages` config limit

### `orchestrator/context/turn_summary.py`

**Purpose**: Compact turn summaries for efficient context use.

**Key Dataclass**: `TurnSummary`

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | str | Associated run ID |
| `mode` | str | `"chat"` or `"agent"` |
| `query_brief` | str | First ~120 chars of user query |
| `answer_brief` | str | First ~200-300 chars of final answer |
| `tools_used` | list[str] | Deduplicated tool names |
| `files_touched` | list[str] | File paths from run artifacts |
| `key_findings` | str | Extracted findings (see below) |
| `token_cost` | int | Tokens this summary occupies |

- `to_context_string()` — Compact `Q: ... | Tools: ... | Findings: ... | A: ...` format

**Key Class**: `TurnSummarizer`
- Generates compact context strings (50-150 tokens) at run completion
- `summarize_agent_run(run, tool_calls, artifacts)` — Full agent summary
- `summarize_chat_run(user_message, final_answer)` — Lightweight chat summary
- `key_findings` extracted from top 3 result summaries of high-value tools (`web_search`, `web_extract`, `read_file`, `grep`); does not rehydrate historical thinking into future prompt context
- Used by HistoryBuilder when full messages exceed budget

**Current Agent Context Note**:
- chat history still uses `HistoryBuilder` / `turn_summary`
- agent cross-turn continuation now primarily uses persisted `runs.agent_state`
- agent prompt assembly uses bounded tool-result formatting plus threshold-based compaction in `AgentEngine`

---

## Storage Layer

### `orchestrator/storage/db.py`

**Purpose**: Async SQLite database wrapper.

**Class: `Database`**

**Pattern**: Singleton via `get_db()`

**Methods**:
- `initialize()` - Create schema, run migrations
- `execute()` - Execute SQL
- `fetchone()`, `fetchall()` - Query methods
- `close()` - Close connection

**Schema Location**: `schema.sql`

### `orchestrator/storage/schema.sql`

**Purpose**: Database schema definition.

**Tables**:
- `conversations` - Conversation metadata
- `runs` - Chat/agent runs
- `trace_events` - Granular event timeline
- `agent_steps` - Agent step tracking
- `agent_tool_calls` - Tool execution records (includes approval fields)
- `agent_citations` - Evidence sources
- `run_events` - Persisted SSE events (survives in-memory cleanup)
- `run_artifacts` - File change tracking (writes, edits, commands)
- `eval_runs` - Benchmark execution sessions
- `eval_samples` - Individual evaluation samples

### `orchestrator/storage/repositories/conversation_repo.py`

**Purpose**: Conversation data access.

**Class: `ConversationRepo`**

**Methods**:
- `create()` - New conversation
- `get(id)` - Get by ID
- `list(status, limit, offset)` - List with filters
- `update(id, title, summary, status)` - Update fields
- `delete(id)` - Delete with cascade

### `orchestrator/storage/repositories/trace_repo.py`

**Purpose**: Runs and trace events data access.

**Class: `TraceRepo`**

**Key Methods**:

| Method | Description |
|--------|-------------|
| `create_run()` | New run record |
| `update_run()` | Update final_answer, status |
| `get_run()` | Get run with deserialized fields |
| `list_runs()` | List runs with filters |
| `add_trace_event()` | Add event with atomic seq |
| `get_trace_events()` | Get timeline for run |
| `get_latest_response_id()` | For stateful mode |

**Sequence Locking**:
```python
async with self._seq_lock:
    max_seq = await self.get_max_seq(run_id)
    await self.insert(run_id, max_seq + 1, ...)
```

### `orchestrator/storage/repositories/agent_repo.py`

**Purpose**: Agent-specific data access.

**Class: `AgentRepo`**

**Methods**:
- `create_step()`, `update_step()` - Step lifecycle
- `add_tool_call()`, `update_tool_call()` - Tool tracking
- `add_citation()`, `get_citations()` - Evidence management
- `get_agent_trace()` - Full trace assembly

### `orchestrator/storage/repositories/terminal_repo.py`

**Purpose**: Browser-terminal metadata persistence.

**Methods**:
- `get_by_conversation()` / `get_by_session_id()` — Metadata lookup
- `upsert()` — Create or replace the current session metadata for a conversation
- `mark_status()` / `touch()` — Status, size, and last-activity updates
- `delete()` — Remove persisted metadata

---

## Routes Layer

### `orchestrator/routes/models.py`

**Purpose**: Model registry and local model management — preset listing, hot-swap, GGUF scanning, llama-server lifecycle.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/models` | List all registry presets (grouped by provider) |
| `POST` | `/api/models/select` | Hot-swap active model via registry |
| `GET` | `/api/models/status` | Current provider info (local vs cloud) |
| `GET` | `/api/models/local` | Scan disk for GGUF models |
| `POST` | `/api/models/local/start` | Start llama-server, switch to local provider |
| `POST` | `/api/models/local/stop` | Stop llama-server, revert to cloud |

**Module State**:
- `_active_model: Optional[ResolvedModel]` — Currently selected registry model
- `_active_model_name: Optional[str]` — Alias used for selection
- `get_active_model()` / `get_active_model_name()` — Accessors for engine integration

**Dependencies**: `orchestrator/models/registry.py` for model resolution, `orchestrator/services/local_models.py` for server management, `orchestrator/providers/factory.py` for provider creation and override.

---

### `orchestrator/routes/terminal.py`

**Purpose**: Browser terminal API — persistent PTY session lifecycle + websocket attach for desktop agent mode.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/terminal/conversations/{conversation_id}/session` | Get terminal metadata + replay buffer |
| `POST` | `/api/terminal/conversations/{conversation_id}/session` | Create or reattach a live terminal session |
| `POST` | `/api/terminal/conversations/{conversation_id}/session/restart` | Restart shell rooted at current workspace |
| `POST` | `/api/terminal/conversations/{conversation_id}/session/close` | Close terminal session |
| `WS` | `/api/terminal/conversations/{conversation_id}/ws` | Interactive PTY I/O (`input`, `resize`, `output`, `exit`) |

**Dependencies**: `ConversationRepo` for session/owner checks, `TerminalSessionManager` for live PTY state, `_resolve_workspace_path()` for workspace validation.

### `orchestrator/services/browser_terminal.py`

**Purpose**: PTY-backed terminal manager for the browser UI.

**Key Elements**:
- `TerminalSession` — Live PTY process, bounded replay buffer, websocket subscriber queues
- `TerminalSessionManager` — Per-conversation live session map + restart/close logic
- `get_terminal_manager()` — Singleton accessor

**Behavior**:
- Starts shell in the selected workspace on first open
- Keeps one persistent live shell per conversation
- Stores only lightweight metadata in SQLite; PTY handles stay in memory
- Returns `status="stale"` when metadata exists but the live PTY died (for example after server restart)

---

### `orchestrator/services/local_models.py`

**Purpose**: GGUF model discovery and llama-server process management.

**Key Elements**:

| Element | Type | Description |
|---------|------|-------------|
| `MODEL_DIRS` | List[Path] | Directories to scan for .gguf files |
| `LLAMA_PORT` | int | Default port (8080) |
| `LocalModel` | dataclass | Model metadata (path, name, size) |
| `scan_models()` | function | Scans all MODEL_DIRS for .gguf files |
| `start()` | async function | Starts llama-server with `--jinja` flag, waits for health |
| `stop()` | async function | Graceful SIGTERM shutdown |
| `is_running()` | async function | Health check via HTTP GET |
| `status()` | function | Returns current model name and running state |

---

### `orchestrator/routes/benchmarks.py`

**Purpose**: Benchmarks API for serving GAIA evaluation traces.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/benchmarks/traces` | List all trace metadata (sorted by timestamp) |
| `GET` | `/api/benchmarks/traces/{filename}` | Get full trace data for a specific run |

**Key Constants**:

| Constant | Description |
|----------|-------------|
| `GAIA_RESULTS_DIR` | Root `gaia_results/` directory |
| `BEST_RUNS_DIR` | `gaia_results/best_runs/` subdirectory |

**Helper Functions**:
- `_collect_trace_files()` — Collects JSON files from both root and `best_runs/` directories with filename deduplication (root takes priority). Handles deployed environments where only `best_runs/` is available.
- `_find_trace_file(filename)` — Locates a specific trace file, checking root first then `best_runs/`.

**Security**: Path traversal protection on `GET /traces/{filename}` (rejects `/`, `\`, and `.` prefixes).

---

### `orchestrator/routes/conversations.py`

**Purpose**: Conversation CRUD endpoints.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/conversations` | Create conversation |
| `GET` | `/api/conversations` | List conversations |
| `GET` | `/api/conversations/{id}` | Get with runs |
| `PATCH` | `/api/conversations/{id}` | Update fields |
| `DELETE` | `/api/conversations/{id}` | Delete cascade |
| `GET` | `/api/conversations/{id}/traces` | All trace events |

### `orchestrator/routes/runs.py`

**Purpose**: Chat run endpoints with SSE streaming.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/conversations/{id}/runs` | Create run (returns stream URL) |
| `POST` | `/api/runs` | Standalone run |
| `GET` | `/api/runs` | List runs |
| `GET` | `/api/runs/{id}` | Get run details |
| `GET` | `/api/runs/{id}/stream` | SSE stream |
| `GET` | `/api/runs/{id}/events` | Get events with sequence filtering |
| `GET` | `/api/runs/{id}/report` | Get markdown report |
| `GET` | `/api/runs/{id}/thinking` | Get thinking trace (detail levels: user, internal, full) |
| `GET` | `/api/runs/{id}/timeline` | Trace timeline |
| `POST` | `/api/runs/{id}/abort` | Cancel run |

**SSE Implementation**:
- Background task pushes to `asyncio.Queue`
- `EventSourceResponse` streams from queue
- In-memory tracking (`_active_runs`)

### `orchestrator/routes/agent_runs.py`

**Purpose**: Agent run endpoints with SSE streaming and tool approval.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/agent/runs` | Create agent run |
| `GET` | `/api/agent/runs/{id}` | Get status |
| `GET` | `/api/agent/runs/{id}/trace` | Full trace |
| `GET` | `/api/agent/runs/{id}/stream` | SSE stream |
| `POST` | `/api/agent/runs/{id}/approve/{tool_call_id}` | Approve pending tool |
| `POST` | `/api/agent/runs/{id}/deny/{tool_call_id}` | Deny pending tool |
| `POST` | `/api/agent/runs/{id}/pause` | Pause agent between steps |
| `POST` | `/api/agent/runs/{id}/resume` | Resume a paused agent |
| `POST` | `/api/agent/runs/{id}/steer` | Inject a steering message into the run |
| `POST` | `/api/agent/runs/{id}/cancel` | Cancel agent |

**Tool Approval Flow**:
- In-memory `_approval_queues`: `Dict[run_id, Dict[tool_call_id, asyncio.Future[bool]]]`
- Agent engine creates a Future when a tool needs approval, emits `tool_approval_required` SSE event
- `/approve` resolves the Future with `True`, `/deny` resolves with `False`
- Approval timeout: 5 minutes (tool is denied if no response)
- `relaxed` policy is tool-aware, not blanket: read-only filesystem/web tools auto-run, write/edit operations still require approval, and bash commands are classified before auto-approval

**Pause/Resume Flow**:
- Agent checks `pause_signal` (asyncio.Event) between steps
- `/pause` clears the signal, causing the agent loop to block; emits `paused` SSE event
- `/resume` sets the signal, unblocking the loop; emits `resumed` SSE event
- State machine transitions to `AgentState.PAUSED` while blocked

**Steer Queue**:
- In-memory `_steer_queues`: `Dict[run_id, List[str]]`
- `/steer` appends a message to the queue; emits `steer` (steer_injected) SSE event
- Before each LLM call, queued messages are injected as user-role messages into the conversation
- Messages are cleared from the queue after injection

**SSE Stream Token Auth**:
- Each `POST /api/agent/runs` generates a per-run `secrets.token_urlsafe(16)` stored in `_run_tokens`
- Stream endpoint validates token: rejects if a non-empty token is provided but doesn't match
- Omitting the token is allowed as a fallback for reconnection before localStorage is restored
- Token is cleaned up on run completion, error, or history cleanup

**Event History & Reconnection**:
- `_event_history` stores all SSE events per run for replay on reconnect
- On reconnect, server replays history snapshot then streams live events with dedup

**Event Type Mapping**:
```python
_EVENT_TYPE_MAP = {
    "agent_started": "agent_state",
    "step_started": "step_start",
    "thinking": "thinking",
    "tool_start": "tool_start",
    "tool_approval_required": "tool_approval_required",
    "tool_result": "tool_result",
    "usage_update": "usage_update",
    "conversation_compacted": "conversation_compacted",
    "answer_token": "answer",
    "agent_complete": "complete",
}
```

---

## Utilities

### `orchestrator/utils/tokens.py`

**Purpose**: Token counting utilities.

**Functions**:
- `count_tokens(text)` - Count tokens in text
- `count_message_tokens(messages)` - Count tokens in message list

**Encoding**: `cl100k_base` (cached)

### `orchestrator/utils/sanitize.py`

**Purpose**: Response sanitization.

**Functions**:
- `sanitize_response(text)` - Remove Harmony tokens, clean output
- `clean_function_output(text)` - Clean tool call output

### `orchestrator/utils/harmony_parser.py`

**Purpose**: Parse gpt-oss Harmony format.

**Functions**:
- `parse_harmony_response(text)` - Extract channels from Harmony format

---

# CLI/TUI Components

Built with the [Textual](https://textual.textualize.io/) framework. Always uses the `coding` profile.

## Entry Point & App

### `cli/__main__.py`

**Purpose**: Click CLI entry point.

**Command**: `reasoner` (installed via pyproject.toml `[project.scripts]`)

**Options**:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--api-url` | str | `http://localhost:9000` | Backend API URL |
| `--provider` | choice | `default` | `default` or `chatgpt` |
| `--model` | str | None | Override model name |
| `--mode` | choice | `agent` | `chat` or `agent` |
| `--permission` | choice | `relaxed` | `strict`, `relaxed`, or `yolo` |
| `--working-dir` | path | cwd | Filesystem root for tools |
| `--max-steps` | int | 25 | Max agent steps |
| `--local` | flag | False | Interactive local model picker |

### `cli/app.py`

**Purpose**: Textual App subclass with custom theme.

**Class: `ReasonerApp(App)`**

**Features**:
- Custom "reasoner" theme (zinc-based with functional accent colors)
- Color palette: primary `#60a5fa` (blue), accent colors, warning/error
- Title displays mode + provider/model info
- Mounts `ChatScreen` as the main screen

## Screens

### `cli/screens/chat_screen.py`

**Purpose**: Main UI surface handling all user interaction and SSE event consumption.

**Class: `ChatScreen(Screen)`**

**Bindings**:
- `Escape` — Stop current run
- `Ctrl+N` — New conversation

**State**:

| Property | Type | Description |
|----------|------|-------------|
| `_current_run_id` | str | Active agent run |
| `_current_stream_token` | str | SSE auth token |
| `_conversation_id` | str | Multi-turn context |
| `_is_running` | bool | Run state flag |
| `_current_step` | int | Step counter |
| `_pending_approval` | ToolCallPanel | Panel awaiting approval |
| `_chatgpt_available` | bool | Whether ChatGPT auth is valid |
| `_cancel_requested` | bool | Signals SSE consumer to stop |

**Message Handlers** (SSE → Widget):

| Handler | Trigger | Action |
|---------|---------|--------|
| `on_input_area_submitted` | User submits text | Create agent run, subscribe SSE |
| `on_step_start_event` | New step | Update StatusBar step counter |
| `on_thinking_event` | Thinking token | ThinkingPanel.append_token() |
| `on_tool_start_event` | Tool starting | Create ToolCallPanel |
| `on_tool_approval_required_event` | Approval needed | Switch InputArea to approval mode |
| `on_tool_result_event` | Tool finished | ToolCallPanel.set_result() |
| `on_answer_token_event` | Answer token | StreamingMarkdown.append_token() |
| `on_agent_complete_event` | Run done | Finalize, show context usage |
| `on_agent_error_event` | Error | Display error message |

**Slash Commands**: `/login`, `/logout`, `/status`, `/switch [provider]`, `/help`

**Approval Flow**:
1. `ToolApprovalRequiredEvent` received → stores `_pending_approval` reference
2. InputArea switches to approval mode (read-only, shows full tool args + diff preview for write/edit)
3. User presses Enter (approve) or `n` (deny)
4. StatusBar shows "executing tool…" after approval
5. Calls `POST /api/agent/runs/{id}/approve/{tool_call_id}` or `/deny/`
6. On 404 (server restarted): shows clear message, calls `_force_reset_run()`
7. Restores normal input mode

**SSE Resilience**: The `_consume_events` worker detects connection loss (closed/disconnect/reset/refused/eof) and posts a clear error message instead of a raw exception. The `_cancel_requested` flag lets the cancel action break out of the SSE loop immediately.

**Startup**: On mount, `_check_chatgpt_auth()` validates saved session against backend; if expired, attempts restore from `~/.config/reasoner/chatgpt_auth.json` backup.

## Widgets

### `cli/widgets/input_area.py`

**Purpose**: Multi-line text input with approval mode.

**Class: `InputArea(TextArea)`**

**Modes**:
- **Normal**: Enter to submit, Shift+Enter for newline
- **Approval**: Read-only display of full tool arguments, captures `y`/`n` key responses

**Messages**:
- `Submitted(value: str)` — User submitted text
- `ApprovalDecision(approved: bool)` — User approved or denied a tool

### `cli/widgets/thinking_panel.py`

**Purpose**: Expandable display of model reasoning tokens.

**Class: `ThinkingPanel`**

**Features**:
- **Collapsed**: Shows last ~100 chars on single line with ∴ symbol
- **Expanded**: Full thinking text
- Click to toggle expand/collapse
- `append_token(token)` for streaming accumulation

### `cli/widgets/tool_call_panel.py`

**Purpose**: Expandable tool call display with approval support.

**Class: `ToolCallPanel`**

**Features**:
- **Collapsed**: `▸ ToolName(primary_arg)` — primary argument extraction (path, command, query, etc.)
- **Expanded**: `▾ ToolName` with full key-value argument pairs
- Tool icon mapping per tool name
- Result display with success/error status

**Key Methods**:
- `show_approval_prompt()` — Display approval UI
- `set_result(success, summary, error, duration_ms)` — Update with execution result
- `resolve_approval(approved)` — Mark approval decision

**Properties**: `run_id`, `tool_call_id`

### `cli/widgets/streaming_markdown.py`

**Purpose**: Markdown rendering with streaming token updates.

**Class: `StreamingMarkdown`**

- `append_token(token)` — Accumulate and re-render

### `cli/widgets/message_bubble.py`

**Purpose**: Container for user, assistant, and system messages.

**Class: `MessageBubble`**

- Roles: `user` (renders content), `assistant` (empty shell for children), `system` (dim italic info text)
- Children (assistant only): ThinkingPanel, ToolCallPanel, StreamingMarkdown

### `cli/widgets/message_list.py`

**Purpose**: Scrollable container for all message bubbles.

**Class: `MessageList`**

- Auto-scroll to bottom on new content

### `cli/widgets/status_bar.py`

**Purpose**: Status information display.

**Class: `StatusBar`**

**Displays**: connection dot (left), mode/provider/model, activity/step, context window fill % (right)

**Context Display**: Shows `ctx 15% (14.8k)` — context window fill percentage with abbreviated token count. Turns yellow at >80% fill. Dropped cumulative API token count (was misleading — input tokens recounted every call).

**Methods**:
- `set_busy(is_busy)` — Show/hide spinner
- `set_step(text)` — Update activity text (step count, "executing tool…", etc.)
- `set_context_live(used, total, _)` — Update context fill during run
- `set_context_usage(tokens_used, tokens_max)` — Show final context usage
- `set_connected(connected)` — Connection indicator dot
- `set_provider(provider)` — Update provider display

### `cli/widgets/agent_progress.py`

**Purpose**: Agent progress indicator widget.

**Class: `AgentProgress`**

## Events

### `cli/events.py`

**Purpose**: Textual message classes that bridge SSE events to widget updates.

**Base Class**: `AgentEvent(Message)` — all events inherit from this

| Event Class | Fields | Description |
|-------------|--------|-------------|
| `StepStartEvent` | step_number, steps_remaining | New agent step |
| `ThinkingEvent` | content | Reasoning token chunk |
| `ToolStartEvent` | tool_call_id, tool_name, arguments | Tool execution starting |
| `ToolApprovalRequiredEvent` | tool_call_id, tool_name, arguments | Approval needed before execution |
| `ToolResultEvent` | tool_call_id, success, result_summary, error_message, duration_ms | Tool completion |
| `AnswerTokenEvent` | content | Final answer token chunk |
| `AgentCompleteEvent` | success, final_answer, citations, total_steps, timing_ms, total_tokens, context_usage | Run finished |
| `AgentErrorEvent` | error, step | Error occurred |
| `AgentStateEvent` | state, current_step, max_steps | State transition |
| `HeartbeatEvent` | — | SSE keepalive |

## CLI API Client

### `cli/api_client.py`

**Purpose**: HTTP + SSE client for backend communication.

**Class: `APIClient`**

**Methods**:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `create_agent_run(query, conversation_id)` | POST /api/agent/runs | Start an agent run |
| `stream_agent_events(run_id, token, since_seq)` | GET /api/agent/runs/{id}/stream | SSE event stream |
| `approve_tool(run_id, tool_call_id)` | POST /api/agent/runs/{id}/approve/{tc_id} | Approve pending tool |
| `deny_tool(run_id, tool_call_id)` | POST /api/agent/runs/{id}/deny/{tc_id} | Deny pending tool |
| `cancel_run(run_id)` | POST /api/agent/runs/{id}/cancel | Cancel active run |
| `health_check()` | GET /api/health | Check backend connectivity |
| `set_session(session_id)` | — | Set CLI session + switch to chatgpt provider |
| `set_provider(provider)` | — | Switch provider mid-session (updates X-Provider header) |

**Headers**: `X-Provider`, `X-Model`, `X-CLI-Session`

## CLI Configuration

### `cli/config.py`

**Purpose**: CLI configuration with session persistence.

**Class: `CLIConfig`**

**Properties**:
- `api_url`, `provider`, `model`, `mode`, `permission`, `working_dir`, `max_steps`
- `session_cookie` — Demo session persistence
- `session_id` — CLI session for ChatGPT OAuth
- `profile` — Always `"coding"` for CLI

**Methods**:
- `from_args()` — Create from Click CLI flags (loads saved provider preference if `--provider` not explicitly set)
- `save_session()` — Persist to `~/.config/reasoner/config.json`
- `save_cli_session()` — Persist CLI session ID
- `clear_cli_session()` — Clear on logout
- `save_provider_preference(provider)` — Persist provider choice to `~/.config/reasoner/provider`

### `cli/auth.py`

**Purpose**: ChatGPT OAuth PKCE authentication flow with token persistence.

**Functions**:
- `login(api_url, existing_session)` — Reuses valid session if provided, otherwise opens browser for OAuth
- `check_auth(api_url, session_id)` — Validate authentication status
- `backup_tokens(api_url, session_id)` — Export and save tokens to `~/.config/reasoner/chatgpt_auth.json`
- `try_restore(api_url, session_id)` — Restore tokens from backup file via refresh token

---

# Frontend Components

## Core Components

### `ui/src/App.tsx`

**Purpose**: Main application layout and routing.

**Layout**:
```
┌─────────────────────────────────────────────────────────┐
│ Sidebar (collapsible)  │  Main Content  │  Detail Panel │
│ - ConversationList     │  - Routes      │  (debug)      │
│ - Resize handle        │                │               │
└─────────────────────────────────────────────────────────┘
```

**Routes**:
- `/` → Redirect to `/conversations`
- `/conversations` → New conversation view
- `/conversations/:id` → Conversation view
- `/benchmarks` → Benchmarks page with GAIA results

**Features**:
- Collapsible sidebar (200-500px)
- Drag-to-resize handle
- Detail panel toggle
- Toast notifications via `<Toaster>` (sonner)
- **Demo Mode Support**:
  - Sidebar locked (collapsed) for non-owners in demo mode
  - Owner detection via URL param `?owner=<secret>`
  - Secret stored in localStorage (`reasoner_owner_token`)
  - New Chat button always visible in collapsed strip
  - Expand button hidden for non-owners in demo mode

**Demo Mode Flow**:
1. Backend sets `demo.enabled=true` in config
2. Frontend fetches `/api/config` to detect demo mode
3. If `?owner=<secret>` in URL:
   - Store secret in localStorage
   - Clean URL (remove param)
   - Enable sidebar controls
4. Non-owners see collapsed sidebar with only New Chat button

### `ui/src/components/ConversationView.tsx`

**Purpose**: Main chat interface for both chat and research modes.

**Modes**:
- **Chat Mode** - Normal conversational chat
- **Agent Mode** - Agent with tools (web search, code execution)

**Features**:
- Mode toggle in input form (labels: "Agent" / "Chat")
- Global reasoning settings button
- Message history display
- Stop/cancel button while generating
- Auto-scroll during streaming (watches text length, scrolls when near bottom)
- Textarea auto-resize (expands as you type, max 200px, resets on submit)
- Toast error notifications for failed runs/aborts (via sonner)
- Preset question chips on empty state
- Benchmarks navigation chip in header
- Desktop agent-mode terminal toggle; embeds a collapsible, resizable terminal pane above the composer
- Terminal pane is conversation-scoped and preserves shell state across collapse/reopen and conversation switches

**State**:
- Uses `useSSE` for chat streaming (only auto-subscribes to `activeChatRunId`, not agent runs)
- Uses `useAgentSSE` for research streaming (with stream token from localStorage)
- Lazy conversation creation on first message
- Stores stream tokens in `localStorage` on agent run creation for page reload recovery
- `subscribedRunRef` tracks run IDs already subscribed in `handleSubmit()` to prevent `loadConversation()` from opening a duplicate SSE connection
- Defers `navigate()` until after `subscribeAgent()` so the subscription guard is set before the URL change triggers `loadConversation`
- `hasActiveRun` disables textarea for new messages but enables mid-run steering
- During active agent runs, textarea shows "Steer the agent..." placeholder and send button displays "steer" in amber
- Queued steer message chips appear above textarea and are cleared after injection
- Usage counter shows "X left" when message limits are enabled; input disabled at limit with 429 toast handling

### `ui/src/components/IntegratedTerminal.tsx`

**Purpose**: Desktop browser terminal pane for agent mode.

**Features**:
- xterm-based terminal surface
- Collapsible and vertically resizable bottom pane
- Per-conversation session attach/reconnect
- Restart, clear, and collapse controls
- Workspace-change warning when the conversation workspace path no longer matches the running shell session

**Integration**:
- Calls `/api/terminal/...` endpoints to create/restart metadata-backed PTY sessions
- Uses websocket attach endpoint for live terminal I/O
- Persists pane open state per conversation and pane height in localStorage

### `ui/src/components/ConversationList.tsx`

**Purpose**: Sidebar list of conversations.

**Features**:
- List conversations on mount
- Single delete per item
- Multi-select mode with bulk delete
- Delete confirmation modal
- Navigation on click

**State**:
- `isSelectMode` - Multi-select active
- `selectedIds` - Selected conversation IDs
- `deleteModalOpen` - Confirmation modal

### `ui/src/components/DetailPanel.tsx`

**Purpose**: Debug trace viewer panel.

**Features**:
- Toggle "Full Trace" vs "Selected Event"
- Toggle "All Runs" vs "Single Run"
- Toggle "All Events" vs "User-Facing"
- Copy JSON to clipboard
- Groups events by run

**Data Source**: `/api/runs/{id}/timeline` and `/api/conversations/{id}/traces`

---

## Message Components

### `RunMessage` (internal to ConversationView)

**Purpose**: Display single chat run (user + response).

**Elements**:
- User message bubble (blue)
- AI response bubble (white)
- ThinkingPanel (collapsible)
- Streaming text with cursor animation
- Status badge
- "Details" button

### `ui/src/components/AnswerMarkdown.tsx`

**Purpose**: Markdown rendering with LaTeX support.

**Features**:
- GitHub Flavored Markdown (tables, etc.)
- Math: inline ($...$) and block ($$...$$)
- LaTeX via KaTeX
- Thinking tag stripping
- JSON response unwrapping
- Code block copy button (hover-reveal, click-to-copy with checkmark feedback)

**Plugins**:
- `remark-gfm`
- `remark-math`
- `rehype-katex`

**Exports**:
- `AnswerMarkdown` - Component
- `extractAnswer()` - Utility function

### `ui/src/components/ThinkingPanel.tsx`

**Purpose**: Collapsible thinking/reasoning display.

**Features**:
- Animated expand/collapse using CSS grid transition (200ms ease-out, `.collapsible-content` class)
- Step count display
- Streaming indicator
- Preview when collapsed
- Thinking steps with status

**Styling**: Slate background, indigo icons

---

## Agent Components

### `ui/src/components/AgentRunMessage.tsx`

**Purpose**: Display complete agent run with stats.

**Elements**:
- User query bubble (indigo)
- "Research Agent" badge
- Progress indicator (step N/M)
- AgentStepsPanel
- AnswerWithCitations
- Status badge and actions
- **Stats display** (when complete):
  - Duration with Clock icon (formatted: ms, s, or Xm Ys)
  - Total tokens with Zap icon (with thousands separator)

**Actions**:
- "Stop" while running
- "Details" when complete

**Helper Functions**:
- `formatDuration(ms)`: Converts milliseconds to human-readable duration
- `formatTokens(tokens)`: Formats token count with locale-aware thousands separator

### `ui/src/components/AgentStepsPanel.tsx`

**Purpose**: Timeline of agent steps.

**Features**:
- Animated collapsible steps (CSS grid transition, 200ms ease-out)
- Status icons (pending/running/complete/error)
- Step number and decision
- Inline thinking for current step
- ToolCallCard per tool
- Auto-expand current step

**State**: `expandedSteps` Set

### `ui/src/components/ToolCallCard.tsx`

**Purpose**: Visual card for tool execution.

**Elements**:
- Tool icon (search/file/code)
- Tool name
- Status badge with icon
- Duration display
- Arguments (formatted)
- Result summary (expandable)
- Error message

**Styling**: Status-specific background colors

### `ui/src/components/AnswerWithCitations.tsx`

**Purpose**: Final answer with citations.

**Features**:
- Parse [N] citation markers
- Replace with CitationInline
- Sources list (max 3, expandable)
- Click to open source
- Streaming with cursor

### `ui/src/components/CitationInline.tsx`

**Purpose**: Inline citation badge with tooltip.

**Features**:
- Small [N] badge
- Hover tooltip with:
  - Title
  - Snippet preview
  - Source hostname
- Click opens URL

---

## Benchmarks Components

### `ui/src/components/BenchmarksPage.tsx`

**Purpose**: Dedicated benchmarks page displaying GAIA evaluation results.

**Features**:
- Hero stats cards (Level 1 rank, cost efficiency, overall rank)
- Results table by difficulty level with accuracy percentages
- Comparison table with top systems from HAL Princeton leaderboard
- Key observations/takeaways section
- Responsive: tables convert to cards on mobile
- Link to TracesModal for browsing full evaluation traces

### `ui/src/components/TracesModal.tsx`

**Purpose**: Modal for browsing GAIA evaluation trace results.

**Features**:
- Loads traces from `/api/benchmarks/traces` API endpoint
- Filters to show only full evaluation runs (≥19 questions)
- Filters out deprecated models (Mistral)
- Groups best traces by model + level, sorted by accuracy
- Shows metadata: level, model, timestamp, questions, correct answers, accuracy
- Detail view with ALL question results, expected vs actual answers, timing
- Color-coded correct/incorrect results
- GPT-5-mini traces sorted first

**Data Source**: `GET /api/benchmarks/traces` and `GET /api/benchmarks/traces/{filename}`

---

## UI Primitives

### `ui/src/components/ui/button.tsx`

**Variants**: default, destructive, outline, ghost, secondary
**Sizes**: sm, md, lg

### `ui/src/components/ui/card.tsx`

**Components**: Card, CardHeader, CardContent, CardTitle, CardDescription

### `ui/src/components/ui/badge.tsx`

**Variants**: default, secondary, destructive, outline

### `ui/src/components/ui/input.tsx`

Text input with focus styling.

### `ui/src/components/ui/textarea.tsx`

Multi-line input.

### `ui/src/components/ui/dialog.tsx`

Modal dialog, exports `ConfirmDialog`.

### `ui/src/components/ui/scroll-area.tsx`

Scrollable container (Radix wrapper).

### `ui/src/components/ui/separator.tsx`

Horizontal/vertical divider.

### `ui/src/components/ui/skeleton.tsx`

Loading placeholder.

---

## Hooks

### `ui/src/hooks/useStore.ts`

**Purpose**: Zustand store for all application state.

**State Sections**:
- Conversations
- Runs by conversation
- Events by run
- Streaming state
- Agent state
- UI state
- Connection state

**Selector Hooks**:
- `useSelectedConversation()`
- `useConversationRuns(id)`
- `useSelectedRun()`
- `useRunEvents(id)`
- `useAgentRunState(id)`
- `useHasActiveRun()` - Checks if any run is active (agent state, streaming, or backend 'running' status)

### `ui/src/hooks/useSSE.ts`

**Purpose**: Chat mode SSE streaming.

**Behavior**:
1. Subscribe when `runId` changes
2. Route `TOKEN` → `streamingText`
3. Route `THINKING_TOKEN` → `streamingThinking`
4. Clear on complete/error
5. Unsubscribe on unmount

### `ui/src/hooks/useAgentSSE.ts`

**Purpose**: Agent mode SSE streaming with token-authenticated reconnection.

**Features**:
- Resumption via `sinceSeq`
- Per-run stream token forwarding (stored in `streamTokenRef`)
- `localStorage` persistence for stream tokens (key: `stream_token:{runId}`)
- Token cleanup from localStorage on complete/error
- Reconnection support via `reconnect()` method
- `connectionIdRef` guard: each `subscribe()` call increments a counter; event handlers capture the current value and drop events where it doesn't match `connectionIdRef.current` (prevents stale EventSource callbacks from corrupting state on reconnect or React StrictMode double-mount)

**Event Handlers**:
- `agent_state` → Update state
- `step_start` → Save current thinking to previous step, create new step, clear thinking buffer
- `thinking` → Append to `thinkingBuffer`
- `tool_start` → Create tool call
- `tool_result` → Update tool call
- `answer` → Append to `answerBuffer`

### `ui/src/hooks/useAgentRunDetails.ts`

**Purpose**: Load agent trace from stream or API.

**Logic**:
- If streaming: return store state
- If not: fetch from API, transform to `AgentUIState`

---

## API Client

### `ui/src/api/client.ts`

**Purpose**: REST and SSE API client.

**Base URL**: `/api` (proxied to port 9000)

**REST Functions**:

| Function | Endpoint |
|----------|----------|
| `createConversation()` | POST /conversations |
| `listConversations()` | GET /conversations |
| `getConversation()` | GET /conversations/{id} |
| `deleteConversation()` | DELETE /conversations/{id} |
| `createConversationRun()` | POST /conversations/{id}/runs |
| `getRun()` | GET /runs/{id} |
| `getRunTimeline()` | GET /runs/{id}/timeline |
| `abortRun()` | POST /runs/{id}/abort |
| `createAgentRun()` | POST /agent/runs |
| `getAgentRunStatus()` | GET /agent/runs/{id} |
| `getAgentRunTrace()` | GET /agent/runs/{id}/trace |
| `cancelAgentRun()` | POST /agent/runs/{id}/cancel |

**SSE Functions**:

| Function | Description |
|----------|-------------|
| `subscribeToRun()` | Chat mode SSE subscription |
| `subscribeToAgentRun()` | Agent mode SSE with resumption and stream token auth |
| `fetchLocalModels()` | GET /models/local — scan for GGUF models |
| `startLocalModel()` | POST /models/local/start — start llama-server |
| `stopLocalModel()` | POST /models/local/stop — stop and revert |
| `getModelStatus()` | GET /models/status — current provider info |

**Retry**: GET requests use `withRetry()` (3 retries, exponential backoff)

---

### `ui/src/lib/utils.ts`

**Purpose**: Shared utilities for the frontend.

**Key Functions**:

| Function | Description |
|----------|-------------|
| `cn()` | Tailwind class merger (clsx + tailwind-merge) |
| `sanitizeThinking()` | Strips tool call XML from reasoning/thinking text for display |

**`sanitizeThinking()`** handles multiple formats model-agnostically:
- `<tool_call>...</tool_call>` — standard XML tool calls
- `<function_call>...</function_call>` — function call format
- `<tool_use>...</tool_use>` — Anthropic-style
- `◁tool_call▷...◁/tool_call▷` — Harmony/DeepSeek style
- `[THINK]`/`</think>` — think tags
- Incomplete/streaming tags (unclosed at end of buffer)

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [API Reference](API_REFERENCE.md) - Complete API documentation
