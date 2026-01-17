> **DEPRECATED**: This document is kept for historical reference. For current documentation, see:
> - [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
> - [COMPONENTS.md](./COMPONENTS.md) - Component documentation
> - [DATA_MODELS.md](./DATA_MODELS.md) - Data models
> - [DATA_FLOW.md](./DATA_FLOW.md) - Data flow diagrams
> - [API_REFERENCE.md](./API_REFERENCE.md) - API documentation

---

# System Design: Agent Layer Integration

## How It Builds on Existing Architecture

The new agent layer is **an extension, not a replacement**. It sits on top of your existing components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          NEW: AGENT LAYER                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  AgentExecutor  │  Tools  │  Memory  │  Guardrails  │  Checkpoints  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                      EXISTING: ORCHESTRATION LAYER                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ChatEngine  │  ThinkingOrchestrator  │  StreamParser  │  TraceRepo  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                       EXISTING: PROVIDER LAYER                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  OpenAICompatProvider  │  Retry/Backoff  │  Dual Endpoint Support   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│                        EXISTING: STORAGE LAYER                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  SQLite (aiosqlite)  │  conversations  │  runs  │  trace_events     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stack

### Existing (Unchanged)
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Backend Framework** | FastAPI | Async HTTP server |
| **Database** | SQLite + aiosqlite | Async persistence |
| **Config** | Pydantic + YAML | Type-safe configuration |
| **LLM Provider** | httpx + OpenAI-compat | API communication |
| **Frontend** | React 18 + Vite + TS | UI |
| **State Management** | Zustand | Frontend state |
| **Streaming** | SSE (EventSource) | Real-time updates |

### New Additions
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Checkpoint Store** | SQLite (new table) | Agent state persistence |
| **Memory: Short-Term** | In-memory dict | Recent context |
| **Memory: Long-Term** | SQLite + embeddings | Pattern storage |
| **Memory: Entity** | SQLite | Knowledge graph |
| **Tool Execution** | Docker (optional) | Safe code execution |
| **Embeddings** | OpenAI/local | Semantic search |

---

## Integration Points

### 1. AgentExecutor → ChatEngine

The `AgentExecutor` **wraps** `ChatEngine` for LLM calls:

```python
# orchestrator/agent/executor.py

class AgentExecutor:
    def __init__(
        self,
        chat_engine: ChatEngine,  # REUSE existing engine
        tools: list[BaseTool],
        memory: MemorySystem,
        checkpoint_store: CheckpointStore,
    ):
        self.engine = chat_engine
        self.tools = {t.name: t for t in tools}
        self.memory = memory
        self.checkpoints = checkpoint_store

    async def _reason(self, state: AgentState, context: str) -> AgentAction:
        """Use ChatEngine for reasoning."""

        # Build prompt with context and available tools
        prompt = self._build_agent_prompt(state, context)

        # Call existing ChatEngine (handles streaming, tracing, etc.)
        result = await self.engine.chat(
            conversation_id=state.conversation_id,
            message=prompt,
            run_id=f"{state.run_id}:step:{state.current_step}",
            reasoning_effort=state.reasoning_effort,  # Pass through
            event_callback=self._wrap_callback(state),
        )

        # Parse response into AgentAction
        return self._parse_action(result.response)
```

### 2. Checkpoint Store → Existing Schema

New table extends existing schema:

```sql
-- Add to schema.sql

CREATE TABLE IF NOT EXISTS agent_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step INTEGER NOT NULL,
    created_at TEXT NOT NULL,

    -- Full state snapshot
    state_json TEXT NOT NULL,

    -- Indexing
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id, step)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON agent_checkpoints(run_id, step);
```

### 3. Memory → Existing Database

Memory tables alongside existing tables:

```sql
-- Short-term: In-memory only (no table needed)

-- Long-term memory (successful patterns)
CREATE TABLE IF NOT EXISTS agent_memory_long_term (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,

    -- Pattern data
    goal_embedding BLOB,          -- Vector embedding of goal
    goal_text TEXT NOT NULL,
    action_type TEXT NOT NULL,    -- tool name or "finish"
    action_input TEXT,            -- JSON
    observation TEXT,             -- Result
    quality_score REAL,           -- 0.0 - 1.0

    -- Metadata
    run_id TEXT,
    conversation_id TEXT
);

-- Entity memory (knowledge graph)
CREATE TABLE IF NOT EXISTS agent_memory_entities (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- Entity data
    name TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,    -- person, project, concept, etc.
    description TEXT,
    metadata_json TEXT,

    -- Relationships stored separately
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS agent_memory_relationships (
    id TEXT PRIMARY KEY,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    metadata_json TEXT,

    FOREIGN KEY(source_entity) REFERENCES agent_memory_entities(name),
    FOREIGN KEY(target_entity) REFERENCES agent_memory_entities(name)
);
```

### 4. Tools → Trace Events

Tool executions recorded as trace events:

```python
# When tool executes, record in existing trace_events table

await trace_repo.add_trace_event(
    run_id=state.run_id,
    event_type="tool_call",        # New event type
    content={
        "tool": action.tool,
        "input": action.input,
    },
    actor=f"tool:{action.tool}",
    event_status="pending",
    step_number=state.current_step,
)

# After execution
await trace_repo.add_trace_event(
    run_id=state.run_id,
    event_type="tool_response",    # New event type
    content={
        "output": observation.content,
        "success": observation.success,
    },
    actor=f"tool:{action.tool}",
    event_status="success" if observation.success else "error",
    parent_event_id=tool_call_event_id,
    step_number=state.current_step,
    duration_ms=observation.duration_ms,
)
```

---

## Data Flow

### Single Step Execution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT STEP FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. BUILD CONTEXT                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Memory.build_context(state)                                         │  │
│   │    ├── ShortTermMemory.get_recent(limit=10)                         │  │
│   │    ├── LongTermMemory.search(goal, limit=3)                         │  │
│   │    └── EntityMemory.get_relevant(goal)                              │  │
│   │  ──────────────────────────────────▶ context: str                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   2. REASON (via ChatEngine)                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  AgentExecutor._reason(state, context)                               │  │
│   │    │                                                                 │  │
│   │    ▼                                                                 │  │
│   │  ChatEngine.chat(prompt, reasoning_effort=state.reasoning_effort)   │  │
│   │    │                                                                 │  │
│   │    ├── ThinkingOrchestrator.get_strategy("direct")                  │  │
│   │    ├── strategy.think(messages, model_call)                         │  │
│   │    │     └── OpenAICompatProvider.complete_streaming()              │  │
│   │    │           └── /v1/responses (gpt-oss-120b)                     │  │
│   │    │                 ├── reasoning: "Let me think..."              │  │
│   │    │                 └── output: "I'll use the code_exec tool..."  │  │
│   │    └── TraceRepo.add_trace_event(llm_request, llm_response)         │  │
│   │  ──────────────────────────────────▶ AgentAction                    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   3. CHECK ACTION TYPE                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  if action.type == "finish":                                         │  │
│   │      return AgentResult(success=True, output=action.output)          │  │
│   │  elif action.requires_approval:                                      │  │
│   │      checkpoint and pause                                            │  │
│   │  else:                                                               │  │
│   │      continue to execution                                           │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   4. EXECUTE TOOL                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  tool = self.tools[action.tool]                                      │  │
│   │  TraceRepo.add_trace_event(tool_call, pending)                       │  │
│   │                                                                      │  │
│   │  try:                                                                │  │
│   │      observation = await tool.execute(action.input)                  │  │
│   │      TraceRepo.add_trace_event(tool_response, success)               │  │
│   │  except Exception as e:                                              │  │
│   │      TraceRepo.add_trace_event(tool_response, error)                 │  │
│   │      observation = Observation(error=str(e))                         │  │
│   │  ──────────────────────────────────▶ Observation                    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   5. VALIDATE (Guardrails)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  result = await guardrails.validate(observation, context)            │  │
│   │                                                                      │  │
│   │  if not result.valid:                                                │  │
│   │      # Try to fix with LLM (Cursor pattern)                         │  │
│   │      for attempt in range(max_fix_attempts):                        │  │
│   │          observation = await guardrails.fix_with_feedback(          │  │
│   │              llm, observation, result.errors                         │  │
│   │          )                                                           │  │
│   │          result = await guardrails.validate(observation, context)   │  │
│   │          if result.valid:                                            │  │
│   │              break                                                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   6. UPDATE STATE                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  state.actions.append(action)                                        │  │
│   │  state.observations.append(observation)                              │  │
│   │  state.current_step += 1                                             │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   7. CHECKPOINT                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  checkpoint_id = await checkpoints.save(state)                       │  │
│   │  # Now state is persisted - can resume from crash                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   8. SAVE TO MEMORY                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  await memory.save_step(state, action, observation)                  │  │
│   │    ├── short_term.save(run_id, action, observation)                 │  │
│   │    ├── if observation.success:                                       │  │
│   │    │     long_term.save_pattern(goal, action, observation)          │  │
│   │    └── entity.save(extracted_entities)                              │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   9. EMIT EVENT (for SSE streaming)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  event_callback({                                                    │  │
│   │      "type": "AGENT_STEP",                                          │  │
│   │      "run_id": state.run_id,                                         │  │
│   │      "step": state.current_step,                                     │  │
│   │      "action": action.to_dict(),                                     │  │
│   │      "observation": observation.to_dict(),                           │  │
│   │  })                                                                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                      │                                      │
│                                      ▼                                      │
│   10. LOOP OR FINISH                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  if state.current_step < state.max_steps:                            │  │
│   │      continue loop (go to step 1)                                    │  │
│   │  else:                                                               │  │
│   │      return AgentResult(success=False, error="Max steps reached")   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Core Entities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA MODEL                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   EXISTING TABLES                                                           │
│   ═══════════════                                                           │
│                                                                             │
│   ┌───────────────────┐       ┌───────────────────┐                        │
│   │   conversations   │       │       runs        │                        │
│   ├───────────────────┤       ├───────────────────┤                        │
│   │ conversation_id PK│◀──────│ conversation_id FK│                        │
│   │ title             │       │ run_id PK         │                        │
│   │ summary           │       │ user_message      │                        │
│   │ created_at        │       │ final_answer      │                        │
│   │ status            │       │ status            │                        │
│   │ metadata_json     │       │ usage_stats       │                        │
│   └───────────────────┘       │ last_response_id  │                        │
│                               └─────────┬─────────┘                        │
│                                         │                                   │
│                                         ▼                                   │
│                               ┌───────────────────┐                        │
│                               │   trace_events    │                        │
│                               ├───────────────────┤                        │
│                               │ id PK             │                        │
│                               │ run_id FK         │                        │
│                               │ seq (ordered)     │                        │
│                               │ event_type        │◀── llm_request         │
│                               │ event_status      │    llm_response        │
│                               │ actor             │    tool_call (NEW)     │
│                               │ content_json      │    tool_response (NEW) │
│                               │ parent_event_id   │    checkpoint (NEW)    │
│                               │ step_number       │                        │
│                               │ duration_ms       │                        │
│                               └───────────────────┘                        │
│                                                                             │
│   NEW TABLES                                                                │
│   ══════════                                                                │
│                                                                             │
│   ┌───────────────────┐                                                    │
│   │ agent_checkpoints │                                                    │
│   ├───────────────────┤                                                    │
│   │ checkpoint_id PK  │                                                    │
│   │ run_id FK         │──────▶ runs.run_id                                │
│   │ step              │                                                    │
│   │ created_at        │                                                    │
│   │ state_json        │◀── Full AgentState snapshot                       │
│   └───────────────────┘                                                    │
│                                                                             │
│   ┌───────────────────────┐                                                │
│   │ agent_memory_long_term│                                                │
│   ├───────────────────────┤                                                │
│   │ id PK                 │                                                │
│   │ goal_embedding BLOB   │◀── Vector for semantic search                 │
│   │ goal_text             │                                                │
│   │ action_type           │                                                │
│   │ action_input JSON     │                                                │
│   │ observation           │                                                │
│   │ quality_score         │                                                │
│   │ run_id                │                                                │
│   │ conversation_id       │                                                │
│   └───────────────────────┘                                                │
│                                                                             │
│   ┌───────────────────────┐     ┌─────────────────────────┐               │
│   │ agent_memory_entities │     │ agent_memory_relationships│              │
│   ├───────────────────────┤     ├─────────────────────────┤               │
│   │ id PK                 │◀────│ source_entity FK        │               │
│   │ name UNIQUE           │◀────│ target_entity FK        │               │
│   │ entity_type           │     │ relationship_type       │               │
│   │ description           │     │ metadata_json           │               │
│   │ metadata_json         │     └─────────────────────────┘               │
│   └───────────────────────┘                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### AgentState Schema

```python
@dataclass
class AgentState:
    """Serialized to JSON in agent_checkpoints.state_json"""

    # Identity
    run_id: str                    # UUID, links to runs table
    conversation_id: str           # Links to conversations table

    # Execution control
    current_step: int              # 0, 1, 2, ...
    max_steps: int                 # Default 25
    status: str                    # running | paused | completed | failed

    # Task
    goal: str                      # Original user request
    plan: list[str] | None         # Optional multi-step plan
    reasoning_effort: str          # low | medium | high

    # History (serialized)
    messages: list[dict]           # [{"role": "user", "content": "..."}]
    actions: list[dict]            # [{"type": "tool", "tool": "code_exec", ...}]
    observations: list[dict]       # [{"content": "...", "success": true}]

    # Checkpoint metadata
    checkpoint_id: str
    checkpoint_ts: str             # ISO 8601
```

---

## API Design

### New Endpoints

```python
# orchestrator/routes/agent.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    conversation_id: str
    goal: str
    reasoning_effort: str = "medium"  # low | medium | high
    max_steps: int = 25


class ResumeRequest(BaseModel):
    checkpoint_id: str
    approval: dict | None = None  # For paused runs needing approval


@router.post("/run")
async def run_agent(request: AgentRunRequest):
    """Start a new agent run."""
    executor = get_agent_executor()
    state = AgentState(
        run_id=str(uuid4()),
        conversation_id=request.conversation_id,
        goal=request.goal,
        reasoning_effort=request.reasoning_effort,
        max_steps=request.max_steps,
        status="running",
        current_step=0,
    )

    # Start async task
    task_id = start_agent_task(executor, state)

    return {
        "run_id": state.run_id,
        "stream_url": f"/api/agent/{state.run_id}/stream",
    }


@router.post("/resume")
async def resume_agent(request: ResumeRequest):
    """Resume from checkpoint."""
    checkpoints = get_checkpoint_store()
    state = await checkpoints.load(request.checkpoint_id)

    if request.approval:
        # Handle approval for paused run
        state.status = "running"

    executor = get_agent_executor()
    task_id = start_agent_task(executor, state)

    return {
        "run_id": state.run_id,
        "resumed_from_step": state.current_step,
        "stream_url": f"/api/agent/{state.run_id}/stream",
    }


@router.get("/{run_id}/checkpoints")
async def list_checkpoints(run_id: str):
    """List all checkpoints for a run."""
    checkpoints = get_checkpoint_store()
    return await checkpoints.list_checkpoints(run_id)


@router.get("/{run_id}/state")
async def get_state(run_id: str):
    """Get current agent state."""
    checkpoints = get_checkpoint_store()
    checkpoints_list = await checkpoints.list_checkpoints(run_id)
    if not checkpoints_list:
        raise HTTPException(404, "No checkpoints found")

    latest = checkpoints_list[0]  # Sorted by step DESC
    state = await checkpoints.load(latest.id)
    return state.to_dict()


@router.post("/{run_id}/cancel")
async def cancel_agent(run_id: str):
    """Cancel running agent."""
    cancel_agent_task(run_id)
    return {"cancelled": True}


@router.get("/{run_id}/stream")
async def stream_agent(run_id: str):
    """SSE stream for agent events."""
    return EventSourceResponse(agent_event_generator(run_id))
```

### Event Types (SSE)

```typescript
// New event types for agent runs

interface AgentStepEvent {
    type: "AGENT_STEP";
    run_id: string;
    step: number;
    action: {
        type: "tool" | "finish";
        tool?: string;
        input?: any;
        output?: string;
    };
    observation?: {
        content: string;
        success: boolean;
        duration_ms: number;
    };
}

interface AgentPausedEvent {
    type: "AGENT_PAUSED";
    run_id: string;
    step: number;
    reason: "approval_required" | "human_input_needed";
    pending_action: AgentAction;
    checkpoint_id: string;
}

interface AgentCompletedEvent {
    type: "AGENT_COMPLETED";
    run_id: string;
    total_steps: number;
    output: string;
    success: boolean;
}

interface AgentErrorEvent {
    type: "AGENT_ERROR";
    run_id: string;
    step: number;
    error: string;
    checkpoint_id: string;  // Can resume from here
}
```

---

## File Structure (Final)

```
orchestrator/
├── agent/                          # NEW: Agent layer
│   ├── __init__.py
│   ├── state.py                    # AgentState, AgentAction, Observation
│   ├── executor.py                 # AgentExecutor (main loop)
│   ├── checkpoint.py               # CheckpointStore
│   └── result.py                   # AgentResult
│
├── tools/                          # NEW: Tool implementations
│   ├── __init__.py
│   ├── base.py                     # BaseTool, ToolResult
│   ├── registry.py                 # ToolRegistry
│   ├── code_exec.py                # CodeExecutionTool
│   ├── file_ops.py                 # FileReadTool, FileWriteTool
│   ├── search.py                   # CodebaseSearchTool
│   └── web.py                      # WebFetchTool
│
├── memory/                         # NEW: Memory system
│   ├── __init__.py
│   ├── system.py                   # MemorySystem (aggregator)
│   ├── short_term.py               # ShortTermMemory (in-memory)
│   ├── long_term.py                # LongTermMemory (SQLite + vectors)
│   └── entity.py                   # EntityMemory (knowledge graph)
│
├── guardrails/                     # NEW: Validation
│   ├── __init__.py
│   ├── system.py                   # GuardrailSystem
│   └── validators/
│       ├── __init__.py
│       ├── json.py                 # JSONValidator
│       ├── code.py                 # CodeLintValidator
│       └── schema.py               # SchemaValidator
│
├── engine/                         # EXISTING (unchanged)
│   └── chat_engine.py              # ChatEngine
│
├── thinking/                       # EXISTING (unchanged)
│   ├── orchestrator.py             # ThinkingOrchestrator
│   ├── base.py                     # StreamParser
│   └── strategies/
│       └── direct.py               # DirectStrategy
│
├── providers/                      # EXISTING (unchanged)
│   ├── base.py                     # LLMProvider protocol
│   └── openai_compat.py            # OpenAICompatProvider
│
├── storage/                        # EXISTING (extended)
│   ├── db.py                       # Database (add migrations)
│   ├── schema.sql                  # Schema (add new tables)
│   └── repositories/
│       ├── conversation_repo.py    # ConversationRepo
│       ├── trace_repo.py           # TraceRepo
│       └── checkpoint_repo.py      # NEW: CheckpointRepo
│
├── routes/                         # EXISTING (extended)
│   ├── runs.py                     # Existing run endpoints
│   ├── conversations.py            # Existing conversation endpoints
│   └── agent.py                    # NEW: Agent endpoints
│
├── config.py                       # EXISTING (extended)
├── chat_config.yaml                # EXISTING (extended)
└── app.py                          # EXISTING (add agent routes)
```

---

## Configuration Extensions

```yaml
# chat_config.yaml additions

# Existing config unchanged...

# NEW: Agent configuration
agent:
  enabled: true
  max_steps: 25
  max_retries: 3
  default_reasoning_effort: "medium"

  checkpoint:
    enabled: true
    store: "sqlite"
    # Future: "redis" | "postgres"

  memory:
    short_term:
      enabled: true
      max_items: 100
    long_term:
      enabled: true
      embedding_model: "text-embedding-3-small"
      max_patterns: 1000
    entity:
      enabled: false  # Enable in Phase 3

  guardrails:
    enabled: true
    max_fix_attempts: 3
    validators:
      - json
      - code_lint

  tools:
    code_execution:
      enabled: true
      docker_image: "python:3.11-slim"
      timeout: 30
      sandbox: true
    file_operations:
      enabled: true
      allowed_paths:
        - "./workspace"
        - "/tmp/agent"
    web_fetch:
      enabled: true
      timeout: 10
      max_size_mb: 5
    codebase_search:
      enabled: true
      max_results: 10
```

---

## Summary

| Aspect | Approach |
|--------|----------|
| **Integration** | Agent layer wraps existing ChatEngine, TraceRepo |
| **State** | AgentState checkpoint in SQLite, compatible with existing schema |
| **Tools** | New module, recorded as trace_events |
| **Memory** | New tables, same database |
| **API** | New routes, same FastAPI app |
| **Streaming** | Same SSE pattern, new event types |
| **Config** | Extended YAML, same Pydantic validation |

The agent layer is **additive** - it doesn't break or modify existing functionality. You can still use `ChatEngine` directly for simple chat, and use `AgentExecutor` when you need multi-step tool-using agents.

---

## UI/UX Design

### User Input Flow

The UI offers two modes: **Chat** (existing) and **Agent** (new). Users toggle between them.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MESSAGE INPUT AREA                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  ┌────────────┐ ┌────────────┐                                      │  │
│   │  │  💬 Chat   │ │  🤖 Agent  │   ← Mode Toggle (segmented control)  │  │
│   │  └────────────┘ └────────────┘                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                                                                     │  │
│   │  "Help me refactor the auth module to use JWT tokens"               │  │
│   │                                                                     │  │
│   │                           ┌─────────────────┐   ┌────────┐          │  │
│   │  Effort: [Low|Med|High]   │ Max Steps: [25] │   │  Send  │          │  │
│   │                           └─────────────────┘   └────────┘          │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Agent Mode Options (shown when Agent selected):                           │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  ☑ Require approval for file writes                                 │  │
│   │  ☑ Require approval for code execution                              │  │
│   │  ☐ Auto-approve read-only operations                                │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Execution Display

When agent mode is active, the UI shows a **step-by-step timeline** of the agent's work:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT RUN VIEW                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User: "Help me refactor the auth module to use JWT tokens"                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  🤖 Agent Run (run_abc123)                     Status: ● Running    │  │
│   │  Goal: Refactor auth module to use JWT                              │  │
│   │  Progress: Step 3 of 25 max                    [Cancel]             │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─ Step 1 ───────────────────────────────────────── ✓ Complete ────────┐ │
│   │                                                                       │ │
│   │  💭 Reasoning (click to expand)                                      │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐│ │
│   │  │ I need to understand the current auth implementation first.     ││ │
│   │  │ Let me search for auth-related files...                         ││ │
│   │  └─────────────────────────────────────────────────────────────────┘│ │
│   │                                                                       │ │
│   │  🔧 Tool: codebase_search                                            │ │
│   │  Input: {"query": "auth login authentication", "file_types": ["py"]}│ │
│   │                                                                       │ │
│   │  📤 Result: Found 5 files                                  [Details]│ │
│   │  • orchestrator/auth/handlers.py                                    │ │
│   │  • orchestrator/auth/middleware.py                                  │ │
│   │  • orchestrator/auth/models.py                                      │ │
│   │  Duration: 234ms                                                     │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌─ Step 2 ───────────────────────────────────────── ✓ Complete ────────┐ │
│   │                                                                       │ │
│   │  💭 Reasoning                                                        │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐│ │
│   │  │ Found the auth module. Let me read the main handler to          ││ │
│   │  │ understand how authentication currently works...                 ││ │
│   │  └─────────────────────────────────────────────────────────────────┘│ │
│   │                                                                       │ │
│   │  🔧 Tool: file_read                                                  │ │
│   │  Input: {"path": "orchestrator/auth/handlers.py"}                   │ │
│   │                                                                       │ │
│   │  📤 Result: Read 156 lines                                 [Details]│ │
│   │  Duration: 45ms                                                      │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌─ Step 3 ───────────────────────────────────────── ⏳ Running ────────┐ │
│   │                                                                       │ │
│   │  💭 Reasoning                                                        │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐│ │
│   │  │ Now I understand the structure. I'll create a new JWT utility   ││ │
│   │  │ module and update the handler to use it...                      ││ │
│   │  │ ▌ (streaming...)                                                ││ │
│   │  └─────────────────────────────────────────────────────────────────┘│ │
│   │                                                                       │ │
│   │  🔧 Tool: file_write                                    ⏸ Pending   │ │
│   │  Input: {"path": "orchestrator/auth/jwt_utils.py", ...}             │ │
│   │                                                                       │ │
│   │  ⚠️ APPROVAL REQUIRED                                                │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐│ │
│   │  │  This action will create a new file.                            ││ │
│   │  │  Path: orchestrator/auth/jwt_utils.py                           ││ │
│   │  │                                                                  ││ │
│   │  │  [View Diff]  [Approve ✓]  [Reject ✗]  [Edit & Approve]         ││ │
│   │  └─────────────────────────────────────────────────────────────────┘│ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Human-in-the-Loop Approval Dialog

When agent requires approval, show a modal with full context:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ⚠️ APPROVAL REQUIRED                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   The agent wants to execute: file_write                                    │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Agent's Reasoning:                                                  │  │
│   │  ────────────────────────────────────────────────────────────────── │  │
│   │  "I'm creating a new JWT utility module that will handle token      │  │
│   │   generation and validation. This follows the pattern used in       │  │
│   │   the existing codebase with separate utility modules."             │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   📁 File: orchestrator/auth/jwt_utils.py (NEW)                            │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  + """JWT token utilities."""                                        │  │
│   │  +                                                                   │  │
│   │  + import jwt                                                        │  │
│   │  + from datetime import datetime, timedelta                          │  │
│   │  + from orchestrator.config import get_config                        │  │
│   │  +                                                                   │  │
│   │  + def generate_token(user_id: str, expires_in: int = 3600) -> str: │  │
│   │  +     """Generate a JWT token for a user."""                        │  │
│   │  +     config = get_config()                                         │  │
│   │  +     payload = {                                                   │  │
│   │  +         "sub": user_id,                                           │  │
│   │  +         "exp": datetime.utcnow() + timedelta(seconds=expires_in), │  │
│   │  +         "iat": datetime.utcnow(),                                 │  │
│   │  +     }                                                             │  │
│   │  +     return jwt.encode(payload, config.jwt_secret, algorithm="HS256")│
│   │  │                                                  [Show full file] │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Feedback (optional):                                                │  │
│   │  ┌───────────────────────────────────────────────────────────────┐  │  │
│   │  │                                                               │  │  │
│   │  └───────────────────────────────────────────────────────────────┘  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌────────────────┐  ┌────────────────┐  ┌─────────────────────────────┐  │
│   │    Approve ✓   │  │    Reject ✗    │  │   Edit & Approve (opens     │  │
│   │                │  │                │  │   inline editor)            │  │
│   └────────────────┘  └────────────────┘  └─────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Detail Panel (Right Sidebar)

When clicking on a tool call, show detailed information:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TOOL CALL DETAILS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Tool: codebase_search                                                     │
│   Step: 1 of 3                                                              │
│   Status: ✓ Success                                                         │
│   Duration: 234ms                                                           │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────    │
│                                                                             │
│   Input:                                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  {                                                                   │  │
│   │    "query": "auth login authentication",                             │  │
│   │    "file_types": ["py"],                                             │  │
│   │    "max_results": 10                                                 │  │
│   │  }                                                                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Output:                                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  {                                                                   │  │
│   │    "files": [                                                        │  │
│   │      {                                                               │  │
│   │        "path": "orchestrator/auth/handlers.py",                      │  │
│   │        "matches": 12,                                                │  │
│   │        "preview": "def login_user(credentials)..."                   │  │
│   │      },                                                              │  │
│   │      {                                                               │  │
│   │        "path": "orchestrator/auth/middleware.py",                    │  │
│   │        "matches": 8,                                                 │  │
│   │        "preview": "class AuthMiddleware..."                          │  │
│   │      }                                                               │  │
│   │    ],                                                                │  │
│   │    "total_matches": 34                                               │  │
│   │  }                                                                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────    │
│                                                                             │
│   Trace Event: evt_abc123                                                   │
│   Checkpoint: chk_xyz789                                                    │
│                                                                             │
│   [View in Trace Timeline]  [Replay from Here]                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Completion View

When agent finishes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT COMPLETED                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  🎉 Agent Run Complete                         Status: ✓ Success    │  │
│   │  Goal: Refactor auth module to use JWT                              │  │
│   │  Steps: 7 total                                Duration: 45.2s      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Summary:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  I've successfully refactored the auth module to use JWT tokens.    │  │
│   │                                                                     │  │
│   │  Changes made:                                                      │  │
│   │  • Created orchestrator/auth/jwt_utils.py with token utilities      │  │
│   │  • Updated orchestrator/auth/handlers.py to use JWT                 │  │
│   │  • Added JWT_SECRET to config schema                                │  │
│   │  • Updated tests in tests/auth/test_handlers.py                     │  │
│   │                                                                     │  │
│   │  Next steps you might consider:                                     │  │
│   │  • Set JWT_SECRET in your environment                               │  │
│   │  • Run tests: pytest tests/auth/                                    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌── Files Modified ────────────────────────────────────────────────────┐ │
│   │  + orchestrator/auth/jwt_utils.py (new, 45 lines)                   │ │
│   │  ~ orchestrator/auth/handlers.py (+12, -8)                          │ │
│   │  ~ orchestrator/config.py (+3, -0)                                  │ │
│   │  ~ tests/auth/test_handlers.py (+28, -5)                            │ │
│   │                                                    [View All Diffs] │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   ┌── Timeline (collapsed) ────────────────────────────────── [Expand] ──┐ │
│   │  Step 1: codebase_search → Found 5 files                    234ms   │ │
│   │  Step 2: file_read → handlers.py                             45ms   │ │
│   │  Step 3: file_write → jwt_utils.py                         1.2s    │ │
│   │  Step 4: file_read → handlers.py                             42ms   │ │
│   │  Step 5: file_write → handlers.py                          890ms   │ │
│   │  Step 6: file_read → test_handlers.py                        38ms   │ │
│   │  Step 7: file_write → test_handlers.py                     650ms   │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│   [Start New Agent Run]  [Continue Conversation]                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## UI Components (New)

### File Structure

```
ui/src/
├── components/
│   ├── agent/                          # NEW: Agent-specific components
│   │   ├── AgentModeToggle.tsx         # Chat/Agent mode selector
│   │   ├── AgentRunView.tsx            # Main agent execution display
│   │   ├── ExecutionStep.tsx           # Single step in timeline
│   │   ├── ToolCallCard.tsx            # Tool call display
│   │   ├── ApprovalDialog.tsx          # Human-in-the-loop modal
│   │   ├── AgentCompletionView.tsx     # Final summary
│   │   ├── ReasoningBlock.tsx          # Expandable reasoning display
│   │   └── FileChangePreview.tsx       # Diff viewer for file changes
│   │
│   ├── ConversationView.tsx            # MODIFIED: Add agent mode support
│   └── ... (existing components)
│
├── hooks/
│   ├── useStore.ts                     # MODIFIED: Add agent state
│   └── useAgentStream.ts               # NEW: SSE subscription for agent events
│
└── api/
    └── client.ts                       # MODIFIED: Add agent endpoints
```

### Zustand Store Extensions

```typescript
// ui/src/hooks/useStore.ts

interface AgentStep {
    step: number;
    reasoning: string;
    action: {
        type: 'tool' | 'finish';
        tool?: string;
        input?: unknown;
        output?: string;
    };
    observation?: {
        content: string;
        success: boolean;
        duration_ms: number;
    };
    status: 'pending' | 'running' | 'completed' | 'error';
}

interface AgentRun {
    run_id: string;
    goal: string;
    status: 'running' | 'paused' | 'completed' | 'failed';
    steps: AgentStep[];
    current_step: number;
    max_steps: number;
    pending_approval?: {
        action: AgentAction;
        checkpoint_id: string;
    };
}

interface AppState {
    // Existing state...
    conversations: Conversation[];
    runs: Run[];
    events: TraceEvent[];

    // NEW: Agent state
    mode: 'chat' | 'agent';
    agentRuns: Record<string, AgentRun>;  // run_id -> AgentRun
    activeAgentRunId: string | null;

    // NEW: Agent actions
    setMode: (mode: 'chat' | 'agent') => void;
    startAgentRun: (conversationId: string, goal: string, options: AgentOptions) => Promise<string>;
    handleAgentEvent: (event: AgentEvent) => void;
    approveAction: (runId: string, checkpointId: string, feedback?: string) => Promise<void>;
    rejectAction: (runId: string, checkpointId: string, reason: string) => Promise<void>;
    cancelAgentRun: (runId: string) => Promise<void>;
    resumeAgentRun: (runId: string, checkpointId: string) => Promise<void>;
}
```

### SSE Event Handler

```typescript
// ui/src/hooks/useAgentStream.ts

import { useEffect } from 'react';
import { useStore } from './useStore';

export function useAgentStream(runId: string | null) {
    const handleAgentEvent = useStore(state => state.handleAgentEvent);

    useEffect(() => {
        if (!runId) return;

        const eventSource = new EventSource(`/api/agent/${runId}/stream`);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleAgentEvent(data);
        };

        eventSource.addEventListener('AGENT_STEP', (event) => {
            const step = JSON.parse((event as MessageEvent).data);
            handleAgentEvent({ type: 'AGENT_STEP', ...step });
        });

        eventSource.addEventListener('AGENT_PAUSED', (event) => {
            const pause = JSON.parse((event as MessageEvent).data);
            handleAgentEvent({ type: 'AGENT_PAUSED', ...pause });
        });

        eventSource.addEventListener('AGENT_COMPLETED', (event) => {
            const completion = JSON.parse((event as MessageEvent).data);
            handleAgentEvent({ type: 'AGENT_COMPLETED', ...completion });
        });

        eventSource.addEventListener('AGENT_ERROR', (event) => {
            const error = JSON.parse((event as MessageEvent).data);
            handleAgentEvent({ type: 'AGENT_ERROR', ...error });
        });

        eventSource.onerror = () => {
            console.error('Agent stream connection lost');
            eventSource.close();
        };

        return () => {
            eventSource.close();
        };
    }, [runId, handleAgentEvent]);
}
```

### API Client Extensions

```typescript
// ui/src/api/client.ts

// Existing methods...

// NEW: Agent endpoints
export const agentApi = {
    async startRun(
        conversationId: string,
        goal: string,
        options: {
            reasoning_effort?: 'low' | 'medium' | 'high';
            max_steps?: number;
        }
    ): Promise<{ run_id: string; stream_url: string }> {
        const response = await fetch('/api/agent/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation_id: conversationId,
                goal,
                ...options,
            }),
        });
        return response.json();
    },

    async resume(
        checkpointId: string,
        approval?: { approved: boolean; feedback?: string }
    ): Promise<{ run_id: string; resumed_from_step: number }> {
        const response = await fetch('/api/agent/resume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                checkpoint_id: checkpointId,
                approval,
            }),
        });
        return response.json();
    },

    async cancel(runId: string): Promise<void> {
        await fetch(`/api/agent/${runId}/cancel`, { method: 'POST' });
    },

    async getState(runId: string): Promise<AgentState> {
        const response = await fetch(`/api/agent/${runId}/state`);
        return response.json();
    },

    async listCheckpoints(runId: string): Promise<Checkpoint[]> {
        const response = await fetch(`/api/agent/${runId}/checkpoints`);
        return response.json();
    },
};
```

---

## User Journey Example

### 1. User enters Agent Mode

```
User clicks [🤖 Agent] toggle
→ UI shows agent-specific options (max_steps, approval settings)
→ Zustand: setMode('agent')
```

### 2. User submits goal

```
User types: "Refactor auth to use JWT"
User clicks [Send]
→ API: POST /api/agent/run { goal, conversation_id, options }
→ Response: { run_id, stream_url }
→ Zustand: startAgentRun() creates AgentRun in store
→ useAgentStream(run_id) subscribes to SSE
```

### 3. Agent executes steps

```
SSE: AGENT_STEP { step: 1, reasoning: "...", action: { tool: "search" }, observation: {...} }
→ Zustand: handleAgentEvent() updates agentRuns[run_id].steps
→ UI: ExecutionStep renders with reasoning + tool call + result
```

### 4. Approval required

```
SSE: AGENT_PAUSED { step: 3, reason: "approval_required", pending_action: {...} }
→ Zustand: sets pending_approval on AgentRun
→ UI: ApprovalDialog modal opens
→ User reviews diff, clicks [Approve]
→ API: POST /api/agent/resume { checkpoint_id, approval: { approved: true } }
→ Agent continues
```

### 5. Agent completes

```
SSE: AGENT_COMPLETED { total_steps: 7, output: "...", success: true }
→ Zustand: updates AgentRun.status = 'completed'
→ UI: AgentCompletionView shows summary + file changes
→ User can click [Start New Agent Run] or [Continue Conversation]
```
