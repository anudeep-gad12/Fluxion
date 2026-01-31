# Components

Detailed documentation of every component in the Reasoner system.

## Table of Contents

1. [Backend Components](#backend-components)
   - [Application Layer](#application-layer)
   - [Engine Layer](#engine-layer)
   - [Provider Layer](#provider-layer)
   - [Thinking Layer](#thinking-layer)
   - [Reporting Layer](#reporting-layer)
   - [Agent Layer](#agent-layer)
   - [Storage Layer](#storage-layer)
   - [Routes Layer](#routes-layer)
   - [Utilities](#utilities)
2. [Frontend Components](#frontend-components)
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
| `SecurityHeadersMiddleware` | Middleware | Security headers (X-Frame-Options, etc.) |
| `RateLimitMiddleware` | Middleware | IP-based rate limiting for demo mode |

**Endpoints**:
- `GET /api/health` - Health check
- `GET /api/config` - Current configuration

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
2. If `query` provided (and classification enabled), classifies query to select appropriate system prompt
3. Creates provider (with chain if configured)
4. Creates tool registry (limited to `python_execute` for calculation queries)
5. Creates repositories (AgentRepo, TraceRepo)
6. Returns configured AgentEngine

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
- `COMPLETE` - Done
- `ERROR` - Failed

**Transitions**:
- `start()` - INIT → PLANNING
- `call_tools()` - PLANNING → TOOL_CALLING
- `synthesize()` - * → SYNTHESIZING
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

### `orchestrator/agent/tools/base.py`

**Purpose**: Base tool protocol.

**Protocol: `BaseTool`**

```python
class BaseTool(Protocol):
    name: str
    schema: dict  # {name, description, parameters}

    async def execute(self, **kwargs) -> ToolResult: ...
```

**Dataclass: `ToolResult`**

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Execution success |
| `output` | str | Result content |
| `error` | str | Error message |

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
- `agent_tool_calls` - Tool execution records
- `agent_citations` - Evidence sources
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

---

## Routes Layer

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

**Purpose**: Agent run endpoints with SSE streaming.

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/agent/runs` | Create agent run |
| `GET` | `/api/agent/runs/{id}` | Get status |
| `GET` | `/api/agent/runs/{id}/trace` | Full trace |
| `GET` | `/api/agent/runs/{id}/stream` | SSE stream |
| `POST` | `/api/agent/runs/{id}/cancel` | Cancel agent |

**Event Type Mapping**:
```python
_EVENT_TYPE_MAP = {
    "agent_started": "agent_state",
    "step_started": "step_start",
    "thinking": "thinking",
    "tool_start": "tool_start",
    "tool_result": "tool_result",
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

**Features**:
- Collapsible sidebar (200-500px)
- Drag-to-resize handle
- Detail panel toggle
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
- **Research Mode** - Agent with tools

**Features**:
- Mode toggle in input form
- Reasoning effort selector (chat mode)
- Message history display
- Stop/cancel button while generating
- Auto-scroll to latest

**State**:
- Uses `useSSE` for chat streaming
- Uses `useAgentSSE` for research streaming
- Lazy conversation creation on first message

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
- Collapsible header
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
- Collapsible steps
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

**Purpose**: Agent mode SSE streaming.

**Features**:
- Resumption via `sinceSeq`
- Event type processing
- Agent state updates

**Event Handlers**:
- `agent_state` → Update state
- `step_start` → Create step
- `thinking` → Append buffer
- `tool_start` → Create tool call
- `tool_result` → Update tool call
- `answer` → Append answer buffer

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
| `subscribeToAgentRun()` | Agent mode SSE with resumption |

**Retry**: GET requests use `withRetry()` (3 retries, exponential backoff)

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Data Flow](DATA_FLOW.md) - Request lifecycle and streaming
- [API Reference](API_REFERENCE.md) - Complete API documentation
