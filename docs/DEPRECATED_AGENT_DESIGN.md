> **DEPRECATED**: This document is kept for historical reference. For current documentation, see:
> - [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
> - [COMPONENTS.md](./COMPONENTS.md) - Component documentation
> - [DATA_MODELS.md](./DATA_MODELS.md) - Data models
> - [DATA_FLOW.md](./DATA_FLOW.md) - Data flow diagrams
> - [API_REFERENCE.md](./API_REFERENCE.md) - API documentation

---

# Hybrid Agent Architecture Design

## Overview

This document outlines an agent architecture combining the best patterns from LangChain, LangGraph, Dust, CrewAI, AutoGen, and Cursor - optimized for **gpt-oss-120b** reasoning model.

## Core Principles

1. **Reasoning-First**: Leverage gpt-oss-120b's native CoT with adjustable effort levels
2. **Checkpoint Durability**: Persist state at every step (LangGraph pattern)
3. **Tool Abstraction**: Clean separation of reasoning and execution (LangChain pattern)
4. **Validation Loops**: Self-correction via output validation (Cursor pattern)
5. **Multi-Level Memory**: Short-term + Long-term + Entity memory (CrewAI pattern)
6. **Event-Driven**: Typed messages with clear context (AutoGen pattern)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT ORCHESTRATOR                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         EXECUTION LOOP                               │   │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │   │
│  │  │  PLAN    │──▶│  REASON  │──▶│  EXECUTE │──▶│ VALIDATE │        │   │
│  │  │(optional)│   │(gpt-oss) │   │  (tools) │   │(guardrail)│        │   │
│  │  └──────────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘        │   │
│  │       │              │              │              │               │   │
│  │       │              ▼              ▼              ▼               │   │
│  │       │         ┌─────────────────────────────────────┐           │   │
│  │       │         │           CHECKPOINT                 │           │   │
│  │       │         │  (persist state after each step)     │           │   │
│  │       │         └─────────────────────────────────────┘           │   │
│  │       │                          │                                 │   │
│  │       │         ┌────────────────┴────────────────┐               │   │
│  │       │         ▼                                 ▼               │   │
│  │       │    ┌──────────┐                    ┌──────────┐           │   │
│  │       └───▶│  FINISH  │                    │  RETRY   │───────┐   │   │
│  │            │ (output) │                    │ (loop)   │       │   │   │
│  │            └──────────┘                    └──────────┘       │   │   │
│  │                 ▲                                             │   │   │
│  │                 └─────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         TOOL REGISTRY                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │  Code    │ │  Search  │ │  File    │ │  Web     │ │  Custom  │  │   │
│  │  │ Execute  │ │ Codebase │ │  R/W     │ │  Fetch   │ │  Tools   │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         MEMORY SYSTEM                                │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │   │
│  │  │ Short-Term   │ │ Long-Term    │ │ Entity       │                 │   │
│  │  │ (context)    │ │ (patterns)   │ │ (knowledge)  │                 │   │
│  │  │ [In-Memory]  │ │ [SQLite]     │ │ [SQLite]     │                 │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. Agent State (Checkpointable)

```python
@dataclass
class AgentState:
    """Full agent state - serializable for checkpointing."""

    # Identity
    run_id: str
    conversation_id: str

    # Execution
    current_step: int
    max_steps: int
    status: Literal["running", "paused", "completed", "failed"]

    # Reasoning
    goal: str
    plan: list[str] | None
    reasoning_effort: Literal["low", "medium", "high"]

    # History
    messages: list[Message]
    actions: list[AgentAction]
    observations: list[Observation]

    # Checkpointing
    checkpoint_id: str
    checkpoint_ts: datetime

    def to_checkpoint(self) -> dict:
        """Serialize for persistence."""
        return asdict(self)

    @classmethod
    def from_checkpoint(cls, data: dict) -> "AgentState":
        """Restore from persistence."""
        return cls(**data)
```

### 2. Tool Abstraction (LangChain-inspired)

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class BaseTool(ABC):
    """Base tool interface - all tools implement this."""

    name: str
    description: str
    args_schema: type[BaseModel]  # Pydantic model for args

    # Execution config
    timeout: float = 60.0
    retry_on_error: bool = False
    requires_approval: bool = False  # Human-in-loop

    @abstractmethod
    async def execute(self, args: BaseModel) -> ToolResult:
        """Execute the tool with validated args."""
        pass

    def get_schema(self) -> dict:
        """Generate JSON schema for LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_schema.model_json_schema()
        }
```

### 3. Execution Loop (Dust + LangGraph inspired)

```python
class AgentExecutor:
    """Main execution loop with checkpointing."""

    def __init__(
        self,
        llm: LLMProvider,
        tools: list[BaseTool],
        memory: MemorySystem,
        checkpoint_store: CheckpointStore,
        max_steps: int = 25,
        max_retries: int = 3,
    ):
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.memory = memory
        self.checkpoints = checkpoint_store
        self.max_steps = max_steps
        self.max_retries = max_retries

    async def run(
        self,
        goal: str,
        state: AgentState | None = None,
        on_step: Callable[[AgentStep], None] | None = None,
    ) -> AgentResult:
        """Execute agent loop with checkpointing."""

        # Resume from checkpoint or create new state
        if state is None:
            state = AgentState(
                run_id=str(uuid4()),
                goal=goal,
                current_step=0,
                max_steps=self.max_steps,
                status="running",
                reasoning_effort=self._determine_effort(goal),
            )

        while state.current_step < state.max_steps:
            try:
                # 1. BUILD CONTEXT (with memory)
                context = await self._build_context(state)

                # 2. REASON (call gpt-oss with appropriate effort)
                action = await self._reason(state, context)

                # 3. CHECK FOR FINISH
                if action.type == "finish":
                    state.status = "completed"
                    await self._checkpoint(state)
                    return AgentResult(
                        success=True,
                        output=action.output,
                        state=state,
                    )

                # 4. CHECK FOR HUMAN APPROVAL (if required)
                if action.requires_approval:
                    state.status = "paused"
                    await self._checkpoint(state)
                    return AgentResult(
                        success=False,
                        needs_approval=True,
                        pending_action=action,
                        state=state,
                    )

                # 5. EXECUTE TOOL
                observation = await self._execute_tool(action)

                # 6. VALIDATE OUTPUT (guardrail)
                if not await self._validate(observation):
                    observation = await self._handle_validation_failure(
                        state, action, observation
                    )

                # 7. UPDATE STATE
                state.actions.append(action)
                state.observations.append(observation)
                state.current_step += 1

                # 8. CHECKPOINT
                await self._checkpoint(state)

                # 9. EMIT STEP EVENT
                if on_step:
                    on_step(AgentStep(
                        step=state.current_step,
                        action=action,
                        observation=observation,
                    ))

                # 10. UPDATE MEMORY
                await self.memory.save_step(state, action, observation)

            except Exception as e:
                state.status = "failed"
                await self._checkpoint(state)
                raise AgentError(f"Step {state.current_step} failed: {e}", state)

        # Max steps reached
        state.status = "completed"
        return AgentResult(
            success=False,
            error="Max steps reached",
            state=state,
        )

    def _determine_effort(self, goal: str) -> str:
        """Determine reasoning effort based on goal complexity."""
        # Simple heuristic - can be made smarter
        complexity_indicators = [
            "analyze", "compare", "evaluate", "design",
            "architect", "optimize", "debug", "refactor"
        ]
        goal_lower = goal.lower()
        matches = sum(1 for ind in complexity_indicators if ind in goal_lower)

        if matches >= 2:
            return "high"
        elif matches >= 1:
            return "medium"
        return "low"
```

### 4. Memory System (CrewAI-inspired)

```python
class MemorySystem:
    """Multi-level memory system."""

    def __init__(
        self,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        entity: EntityMemory,
    ):
        self.short_term = short_term
        self.long_term = long_term
        self.entity = entity

    async def build_context(self, state: AgentState) -> str:
        """Build context from all memory sources."""
        context_parts = []

        # Short-term: Recent conversation/actions
        recent = await self.short_term.get_recent(state.run_id, limit=10)
        if recent:
            context_parts.append(f"Recent context:\n{recent}")

        # Long-term: Similar past experiences
        similar = await self.long_term.search(state.goal, limit=3)
        if similar:
            context_parts.append(f"Relevant past experiences:\n{similar}")

        # Entity: Known facts/entities
        entities = await self.entity.get_relevant(state.goal)
        if entities:
            context_parts.append(f"Known information:\n{entities}")

        return "\n\n".join(context_parts)

    async def save_step(
        self,
        state: AgentState,
        action: AgentAction,
        observation: Observation,
    ):
        """Save step to memory systems."""
        # Short-term: Always save
        await self.short_term.save(state.run_id, action, observation)

        # Long-term: Save successful patterns
        if observation.success:
            await self.long_term.save_pattern(
                goal=state.goal,
                action=action,
                observation=observation,
                quality=observation.quality_score,
            )

        # Entity: Extract and save entities
        entities = await self._extract_entities(observation)
        for entity in entities:
            await self.entity.save(entity)
```

### 5. Checkpoint Store (LangGraph-inspired)

```python
class CheckpointStore:
    """Persistent checkpoint storage."""

    def __init__(self, db_path: str = "var/checkpoints.sqlite"):
        self.db_path = db_path

    async def save(self, state: AgentState) -> str:
        """Save checkpoint, return checkpoint_id."""
        checkpoint_id = f"{state.run_id}:{state.current_step}:{uuid4().hex[:8]}"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO checkpoints (
                    checkpoint_id, run_id, step, state_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                checkpoint_id,
                state.run_id,
                state.current_step,
                json.dumps(state.to_checkpoint()),
                datetime.utcnow().isoformat(),
            ))
            await db.commit()

        return checkpoint_id

    async def load(self, checkpoint_id: str) -> AgentState:
        """Load state from checkpoint."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT state_json FROM checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise CheckpointNotFound(checkpoint_id)

            return AgentState.from_checkpoint(json.loads(row[0]))

    async def list_checkpoints(self, run_id: str) -> list[CheckpointInfo]:
        """List all checkpoints for a run."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT checkpoint_id, step, created_at
                FROM checkpoints
                WHERE run_id = ?
                ORDER BY step DESC
            """, (run_id,))
            rows = await cursor.fetchall()

            return [
                CheckpointInfo(id=r[0], step=r[1], created_at=r[2])
                for r in rows
            ]
```

### 6. Validation/Guardrails (Cursor-inspired)

```python
class GuardrailSystem:
    """Output validation with retry capability."""

    def __init__(
        self,
        validators: list[Validator],
        max_retries: int = 3,
    ):
        self.validators = validators
        self.max_retries = max_retries

    async def validate(
        self,
        observation: Observation,
        context: ValidationContext,
    ) -> ValidationResult:
        """Run all validators on observation."""
        errors = []

        for validator in self.validators:
            result = await validator.validate(observation, context)
            if not result.valid:
                errors.append(result.error)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )

    async def fix_with_feedback(
        self,
        llm: LLMProvider,
        observation: Observation,
        errors: list[str],
    ) -> Observation:
        """Ask LLM to fix based on validation errors."""
        prompt = f"""
The previous output had validation errors:
{chr(10).join(f'- {e}' for e in errors)}

Original output:
{observation.content}

Please fix the output to address these errors.
"""
        # Use low reasoning effort for fixes
        response = await llm.complete(
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="low",
        )

        return Observation(
            content=response.content,
            source="validation_fix",
        )


# Example validators
class JSONValidator(Validator):
    """Validates output is valid JSON."""

    async def validate(self, obs: Observation, ctx: ValidationContext) -> ValidatorResult:
        if ctx.expected_format != "json":
            return ValidatorResult(valid=True)

        try:
            json.loads(obs.content)
            return ValidatorResult(valid=True)
        except json.JSONDecodeError as e:
            return ValidatorResult(valid=False, error=f"Invalid JSON: {e}")


class CodeLintValidator(Validator):
    """Validates code output passes linting."""

    async def validate(self, obs: Observation, ctx: ValidationContext) -> ValidatorResult:
        if ctx.content_type != "code":
            return ValidatorResult(valid=True)

        # Run appropriate linter based on language
        linter = self._get_linter(ctx.language)
        result = await linter.check(obs.content)

        if result.errors:
            return ValidatorResult(
                valid=False,
                error=f"Lint errors: {result.errors}"
            )
        return ValidatorResult(valid=True)
```

### 7. gpt-oss-120b Integration

```python
class ReasoningModelProvider(LLMProvider):
    """Provider optimized for gpt-oss reasoning models."""

    async def complete(
        self,
        messages: list[dict],
        reasoning_effort: str = "medium",
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Complete with reasoning effort control."""

        # Build request for /v1/responses endpoint
        request = {
            "model": self.model_name,
            "input": messages,
            "reasoning": {
                "effort": reasoning_effort,  # low | medium | high
            },
        }

        # Add tools if provided
        if tools:
            request["tools"] = [
                {"type": "function", "function": t}
                for t in tools
            ]

        # Make request with retry
        response = await self._request_with_retry(request)

        return LLMResponse(
            content=response["output"][0]["content"],
            reasoning=response.get("reasoning", {}).get("content"),
            tool_calls=self._parse_tool_calls(response),
            usage=response.get("usage", {}),
        )

    async def complete_streaming(
        self,
        messages: list[dict],
        on_token: Callable[[str], None],
        on_reasoning: Callable[[str], None],
        **kwargs,
    ) -> LLMResponse:
        """Streaming with separate reasoning callback."""
        # ... streaming implementation
        pass
```

---

## File Structure

```
orchestrator/
├── agent/
│   ├── __init__.py
│   ├── state.py           # AgentState, AgentAction, Observation
│   ├── executor.py        # AgentExecutor main loop
│   ├── checkpoint.py      # CheckpointStore
│   └── result.py          # AgentResult, AgentStep
├── tools/
│   ├── __init__.py
│   ├── base.py            # BaseTool, ToolResult
│   ├── registry.py        # ToolRegistry
│   ├── code_exec.py       # CodeExecutionTool
│   ├── file_ops.py        # FileReadTool, FileWriteTool
│   ├── search.py          # CodebaseSearchTool
│   └── web.py             # WebFetchTool
├── memory/
│   ├── __init__.py
│   ├── system.py          # MemorySystem
│   ├── short_term.py      # ShortTermMemory
│   ├── long_term.py       # LongTermMemory
│   └── entity.py          # EntityMemory
├── guardrails/
│   ├── __init__.py
│   ├── system.py          # GuardrailSystem
│   └── validators/
│       ├── json.py
│       ├── code.py
│       └── schema.py
└── providers/
    └── reasoning.py       # ReasoningModelProvider
```

---

## Implementation Priority

### Phase 1: Core Loop (MVP)
1. `AgentState` dataclass
2. `BaseTool` abstraction
3. `AgentExecutor` basic loop
4. `CheckpointStore` SQLite implementation
5. Integration with existing `ChatEngine`

### Phase 2: Tools
1. `CodeExecutionTool` (safe Docker execution)
2. `FileReadTool` / `FileWriteTool`
3. `CodebaseSearchTool` (grep/semantic)
4. `WebFetchTool`

### Phase 3: Memory
1. `ShortTermMemory` (in-memory + Redis)
2. `LongTermMemory` (SQLite + embeddings)
3. `EntityMemory` (knowledge graph)

### Phase 4: Guardrails
1. `JSONValidator`
2. `CodeLintValidator`
3. `SchemaValidator`
4. Feedback loop integration

### Phase 5: Advanced
1. Human-in-the-loop approval flows
2. Multi-agent orchestration
3. Parallel tool execution
4. Advanced planning strategies

---

## Configuration

```yaml
# chat_config.yaml additions

agent:
  max_steps: 25
  max_retries: 3
  default_reasoning_effort: "medium"

  checkpoint:
    enabled: true
    store: "sqlite"  # sqlite | redis | postgres
    path: "var/checkpoints.sqlite"

  memory:
    short_term:
      enabled: true
      max_items: 100
    long_term:
      enabled: true
      embedding_model: "text-embedding-3-small"
    entity:
      enabled: false  # Phase 3

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
    file_operations:
      enabled: true
      allowed_paths: ["./workspace"]
    web_fetch:
      enabled: true
      timeout: 10
```

---

## API Extensions

```python
# New endpoints for agent operations

# Resume from checkpoint
POST /api/agent/resume
{
    "checkpoint_id": "run-123:step-5:abc123",
    "approval": {  # Optional - for paused runs
        "approved": true,
        "modified_action": null
    }
}

# List checkpoints
GET /api/agent/checkpoints/{run_id}

# Get agent state
GET /api/agent/state/{run_id}

# Cancel running agent
POST /api/agent/cancel/{run_id}
```

---

## Sources & Inspiration

| Pattern | Source | Implementation |
|---------|--------|----------------|
| Checkpoint/Resume | LangGraph | `CheckpointStore` |
| Tool Abstraction | LangChain | `BaseTool` |
| Execution Loop | Dust (Temporal) | `AgentExecutor` |
| Multi-Level Memory | CrewAI | `MemorySystem` |
| Typed Messages | AutoGen | `AgentState`, `AgentAction` |
| Validation Loop | Cursor | `GuardrailSystem` |
| Reasoning Effort | gpt-oss-120b | `reasoning_effort` param |
