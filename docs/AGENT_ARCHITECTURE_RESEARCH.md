# Agent Architecture Research: A Deep Technical Analysis

**Frameworks Analyzed:** LangChain, LangGraph, Dust, CrewAI, AutoGen, Cursor

**Date:** January 2026

---

## Executive Summary

This document provides a comprehensive analysis of six leading AI agent frameworks, examining their architectural patterns, durability mechanisms, and production readiness. The research focuses on understanding what makes agents reliable, durable, and effective at scale.

### Key Findings

| Framework | Core Pattern | Durability Mechanism | Best For |
|-----------|-------------|---------------------|----------|
| **LangChain** | Chain/Executor loop | Retry + Fallback | Rapid prototyping, tool composition |
| **LangGraph** | Graph-based state machine | Checkpoint persistence | Complex workflows, human-in-loop |
| **Dust** | Temporal workflows | External orchestration | Enterprise scale (10M+ activities/day) |
| **CrewAI** | Role-based crews | Multi-level memory | Collaborative multi-agent tasks |
| **AutoGen** | Actor model (pub/sub) | State save/load | Distributed agents, cross-language |
| **Cursor** | Multi-model delegation | Lint feedback loops | IDE-integrated coding agents |

### Universal Patterns for Durable Agents

1. **Explicit State Tracking** - All durable frameworks maintain explicit intermediate state
2. **Checkpoint/Resume** - Ability to persist and restore execution state
3. **Retry with Backoff** - Exponential backoff + jitter for transient failures
4. **Validation Loops** - Self-correction via linting, guardrails, or model feedback
5. **Tool Abstraction** - Clean separation between reasoning and action execution

---

## Table of Contents

1. [LangChain Architecture](#1-langchain-architecture)
2. [LangGraph Architecture](#2-langgraph-architecture)
3. [Dust Architecture](#3-dust-architecture)
4. [CrewAI Architecture](#4-crewai-architecture)
5. [AutoGen Architecture](#5-autogen-architecture)
6. [Cursor Architecture](#6-cursor-architecture)
7. [Comparative Analysis](#7-comparative-analysis)
8. [Recommendations](#8-recommendations)

---

## 1. LangChain Architecture

**Repository:** https://github.com/langchain-ai/langchain

### Core Abstractions

LangChain's agent architecture is built on three core schema types:

```
┌─────────────────────────────────────────────────────┐
│                 AgentExecutor Loop                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│   ┌─────────┐    ┌─────────────┐    ┌──────────┐  │
│   │  Agent  │───▶│ AgentAction │───▶│  Tool    │  │
│   │  (LLM)  │    │  (request)  │    │(execute) │  │
│   └────┬────┘    └─────────────┘    └────┬─────┘  │
│        │                                  │        │
│        │         ┌─────────────┐          │        │
│        │◀────────│ AgentStep   │◀─────────│        │
│        │         │(observation)│          │        │
│        │         └─────────────┘          │        │
│        │                                           │
│        ▼                                           │
│   ┌─────────────┐                                  │
│   │ AgentFinish │                                  │
│   │  (output)   │                                  │
│   └─────────────┘                                  │
└─────────────────────────────────────────────────────┘
```

**Key Files:**
- `libs/core/langchain_core/agents.py` - Core schema definitions
- `libs/langchain/langchain_classic/agents/agent.py` - AgentExecutor implementation
- `libs/core/langchain_core/tools/base.py` - Tool abstractions

### Agent Types

```python
# AgentAction - Request to execute a tool
class AgentAction:
    tool: str           # Tool name to execute
    tool_input: str | dict  # Parameters
    log: str            # Reasoning trace (auditing)

# AgentFinish - Final output when done
class AgentFinish:
    return_values: dict  # Final outputs
    log: str            # Full LLM prediction

# AgentStep - Tool execution result
class AgentStep:
    action: AgentAction
    observation: Any    # Tool result
```

### Execution Flow (AgentExecutor)

```python
class AgentExecutor:
    agent: BaseSingleActionAgent | BaseMultiActionAgent
    tools: Sequence[BaseTool]
    max_iterations: int = 15
    max_execution_time: float | None = None
    handle_parsing_errors: bool | str | Callable = False

    def _call(self, inputs, run_manager=None):
        intermediate_steps = []
        iterations = 0

        while self._should_continue(iterations, time_elapsed):
            # 1. PLAN: Call agent to decide next action
            output = self.agent.plan(intermediate_steps, **inputs)

            # 2. CHECK: If AgentFinish, we're done
            if isinstance(output, AgentFinish):
                return self._return(output, intermediate_steps)

            # 3. EXECUTE: Run the tool
            observation = self._execute_tool(output)

            # 4. ACCUMULATE: Add to history
            intermediate_steps.append((output, observation))

            iterations += 1
```

### Durability Mechanisms

**1. Retry Policy**
```python
# libs/core/langchain_core/runnables/retry.py
class RunnableRetry:
    retry_exception_types: tuple[type[BaseException], ...]
    wait_exponential_jitter: bool = True
    max_attempt_number: int = 3

# Usage: runnable.with_retry(max_attempt_number=3)
```

**2. Fallback Chain**
```python
# libs/core/langchain_core/runnables/fallbacks.py
class RunnableWithFallbacks:
    runnable: Runnable
    fallbacks: Sequence[Runnable]

# Usage: model.with_fallbacks([backup_model])
```

**3. Intermediate Steps Tracking**
- All actions and observations stored in `intermediate_steps`
- Enables checkpoint and resume patterns
- Serializable for persistence

### Tool Abstraction

```python
class BaseTool(ABC):
    name: str
    description: str
    args_schema: type[BaseModel]  # Pydantic model
    return_direct: bool = False

    def run(self, tool_input, verbose=False, callbacks=None) -> str:
        # Callback integration for tracing
        # Error handling
        return self._run(tool_input)
```

### Runnable Interface (Composability)

```python
class Runnable(ABC):
    def invoke(self, input, config=None) -> Output: ...
    async def ainvoke(self, input, config=None) -> Output: ...
    def batch(self, inputs, config=None) -> list[Output]: ...
    def stream(self, input, config=None) -> Iterator[Output]: ...

    # Composition
    def __or__(self, other) -> RunnableSequence:  # pipe operator
        return RunnableSequence(self, other)
```

---

## 2. LangGraph Architecture

**Repository:** https://github.com/langchain-ai/langgraph

### Core Concept: Graphs Over Chains

LangGraph replaces linear chains with directed graphs, enabling:
- Cycles (iterative reasoning)
- Conditional branching
- Persistent checkpoints
- Human-in-the-loop interrupts

```
┌────────────────────────────────────────────────────────────┐
│                    StateGraph Execution                     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   ┌──────────┐      ┌──────────┐      ┌──────────┐       │
│   │  START   │─────▶│  Node A  │─────▶│  Node B  │       │
│   └──────────┘      └────┬─────┘      └────┬─────┘       │
│                          │                  │             │
│                          ▼                  ▼             │
│                    ┌──────────┐      ┌──────────┐        │
│                    │  Node C  │◀────▶│  Node D  │        │
│                    └────┬─────┘      └────┬─────┘        │
│                          │                  │             │
│                          ▼                  │             │
│   ┌──────────┐      ┌──────────┐            │             │
│   │   END    │◀─────│  Node E  │◀───────────┘             │
│   └──────────┘      └──────────┘                          │
│                                                            │
│   State flows through Channels ────────────────────────▶   │
└────────────────────────────────────────────────────────────┘
```

**Key Files:**
- `libs/langgraph/langgraph/graph/state.py` - StateGraph definition
- `libs/langgraph/langgraph/pregel/main.py` - Pregel execution engine
- `libs/checkpoint/langgraph/checkpoint/base/__init__.py` - Checkpoint system

### Checkpoint System (Durability)

```python
class Checkpoint(TypedDict):
    v: int                              # Format version (currently 4)
    id: str                             # Unique checkpoint ID
    ts: str                             # ISO 8601 timestamp
    channel_values: dict[str, Any]      # State snapshot
    channel_versions: dict[str, str]    # Version per channel
    versions_seen: dict[str, dict]      # Node version tracking
```

**Durability Modes:**
- `"sync"` - Persist before next step (highest durability)
- `"async"` - Persist during next step (balanced)
- `"exit"` - Persist on completion only (best performance)

**Checkpoint Savers:**
- `MemorySaver` - In-memory (development)
- `SqliteSaver` - SQLite persistence
- `PostgresSaver` - PostgreSQL for production

### Pregel Execution Engine

```
┌────────────────────────────────────────────────────────────┐
│                    Pregel Execution Loop                    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   1. Load Checkpoint (if resuming)                         │
│      └── Restore channel_values and version metadata       │
│                                                            │
│   2. Prepare Next Tasks                                    │
│      └── Check channel versions, determine triggered nodes │
│                                                            │
│   3. Execute Tasks (potentially parallel)                  │
│      └── Apply retry policies, run node logic              │
│                                                            │
│   4. Apply Writes (atomic)                                 │
│      └── Update channel values and versions                │
│                                                            │
│   5. Create Checkpoint (based on durability mode)          │
│      └── Serialize state via BaseCheckpointSaver           │
│                                                            │
│   6. Check Interrupts (if configured)                      │
│      └── Pause for human review if needed                  │
│                                                            │
│   7. Repeat until END node reached                         │
└────────────────────────────────────────────────────────────┘
```

### Human-in-the-Loop

```python
# Interrupt from within a node
def interrupt(value: Any) -> Any:
    """Pause graph execution, communicate value to client"""
    raise GraphInterrupt(value)

# Resume with Command
class Command:
    graph: str | None      # Target graph
    update: Any | None     # State updates
    resume: Any | None     # Resume values
    goto: str | Send       # Next node(s)

# Configuration
interrupt_before=["approval_node"]  # Pause before node
interrupt_after=["tool_node"]       # Pause after node
```

### Channel-Based State

```python
class BaseChannel(ABC):
    @abstractmethod
    def update(self, values: Sequence[Value]) -> bool: ...

    @abstractmethod
    def get(self) -> Value: ...

    @abstractmethod
    def checkpoint(self) -> Value | None: ...

# Built-in channels
class LastValue(BaseChannel): ...      # Keep last value
class Accumulator(BaseChannel): ...    # Append values
class BinaryOperatorChannel: ...       # Custom reducers
```

---

## 3. Dust Architecture

**Repository:** https://github.com/dust-tt/dust

### Core Concept: Temporal Workflows

Dust delegates all durability to Temporal.io, enabling:
- 10M+ activities per day
- Automatic retry and failure recovery
- Cross-worker execution
- Real-time observability

```
┌────────────────────────────────────────────────────────────┐
│                    Dust Agent Loop                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   Temporal Workflow: agentLoopWorkflow                     │
│   ┌────────────────────────────────────────────────────┐   │
│   │                                                    │   │
│   │   ┌─────────┐    ┌──────────────┐    ┌─────────┐  │   │
│   │   │  Start  │───▶│ Run Model &  │───▶│ Execute │  │   │
│   │   │         │    │ Create Actions│    │ Tools   │  │   │
│   │   └─────────┘    └──────────────┘    └────┬────┘  │   │
│   │                                           │       │   │
│   │        ┌──────────────────────────────────┘       │   │
│   │        │                                          │   │
│   │        ▼                                          │   │
│   │   ┌─────────────┐    ┌─────────────┐             │   │
│   │   │ Check Loop  │───▶│  Finalize   │             │   │
│   │   │ Continuation│    │  Activity   │             │   │
│   │   └─────────────┘    └─────────────┘             │   │
│   │         │                                         │   │
│   │         └────────▶ (loop if more steps)          │   │
│   │                                                    │   │
│   └────────────────────────────────────────────────────┘   │
│                                                            │
│   Connector Workflows (Slack, Notion, GitHub, etc.)        │
│   ┌────────────────────────────────────────────────────┐   │
│   │  syncChannel ──▶ syncThread ──▶ garbageCollector   │   │
│   └────────────────────────────────────────────────────┘   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Key Files:**
- `front/temporal/agent_loop/workflows.ts` - Main agent workflow
- `front/temporal/agent_loop/activities/` - Tool execution activities
- `connectors/src/connectors/interface.ts` - Connector abstraction

### Agent Loop Workflow

```typescript
// front/temporal/agent_loop/workflows.ts
export async function agentLoopWorkflow(args: AgentLoopArgs): Promise<void> {
  // Handle cancellation signals
  const cancelReceived = Trigger<void>();
  setHandler(cancelAgentLoopSignal, () => cancelReceived.trigger());

  let currentStep = args.startStep ?? 0;

  while (currentStep < MAX_STEPS_USE_PER_RUN_LIMIT) {
    // 1. Run model and create actions (10 min timeout)
    const modelResult = await runModelAndCreateActionsWrapper({...});

    // 2. Execute tools (dynamic timeout based on tool)
    const toolResults = await executeTools(modelResult.actions);

    // 3. Check for approval-required tools
    if (toolResults.shouldPauseAgentLoop) {
      break; // External system will resume
    }

    currentStep++;
  }

  // Non-cancellable finalization
  await CancellationScope.nonCancellable(async () => {
    await finalizeAgentLoopActivity(args);
  });
}
```

### Activity Timeouts

```typescript
const activityOptions = {
  modelInference: {
    startToCloseTimeout: '10 minutes',
    heartbeatTimeout: '60 seconds',
    retry: { maximumAttempts: 10 }
  },
  toolExecution: {
    startToCloseTimeout: 'dynamic + 1 minute',
    heartbeatTimeout: '60 seconds',
    retry: { maximumAttempts: 1 }  // Most tools non-idempotent
  },
  finalization: {
    startToCloseTimeout: '1 minute'
  }
};
```

### Connector System

```typescript
// connectors/src/connectors/interface.ts
abstract class BaseConnectorManager<T> {
  abstract get provider(): ConnectorProvider;
  abstract sync(params: { fromTs: number | null }): Promise<Result<string>>;
  abstract stop(): Promise<Result>;
  abstract resume(): Promise<Result>;
  abstract retrievePermissions(params): Promise<Result<ContentNode[]>>;
}

// Supported connectors
const CONNECTORS = [
  'slack', 'notion', 'confluence', 'github',
  'google_drive', 'microsoft', 'snowflake',
  'bigquery', 'salesforce', 'zendesk', 'intercom'
];
```

### MCP Tool Integration

```typescript
// Tools from Model Context Protocol servers
interface MCPToolConfiguration {
  name: string;
  description: string;
  inputSchema: JSONSchema;
}

// Internal servers
const INTERNAL_MCP_SERVERS = [
  'data_sources_file_system',  // search, find, cat, list
  'web_browser',               // web search, summarization
  'agent_memory',              // read/write agent memories
  'agent_router',              // route to sub-agents
];
```

---

## 4. CrewAI Architecture

**Repository:** https://github.com/crewAIInc/crewAI

### Core Concept: Role-Based Collaboration

CrewAI emphasizes role-based agents working as a "crew":
- Each agent has a role, goal, and backstory
- Crews orchestrate multi-agent collaboration
- Flows enable complex workflow patterns

```
┌────────────────────────────────────────────────────────────┐
│                    CrewAI Architecture                      │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   ┌─────────────────────────────────────────────────────┐  │
│   │                      CREW                            │  │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐             │  │
│   │  │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  (roles)    │  │
│   │  │Researcher│  │ Writer  │  │Reviewer │             │  │
│   │  └────┬────┘  └────┬────┘  └────┬────┘             │  │
│   │       │            │            │                   │  │
│   │       ▼            ▼            ▼                   │  │
│   │  ┌─────────────────────────────────────────────┐   │  │
│   │  │              PROCESS                         │   │  │
│   │  │   Sequential: Task1 ──▶ Task2 ──▶ Task3     │   │  │
│   │  │   Hierarchical: Manager delegates to agents  │   │  │
│   │  └─────────────────────────────────────────────┘   │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                            │
│   ┌─────────────────────────────────────────────────────┐  │
│   │                  MEMORY SYSTEM                       │  │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │  │
│   │  │Short-Term│ │Long-Term │ │ Entity   │ │External│ │  │
│   │  │ Memory   │ │ Memory   │ │ Memory   │ │ Memory │ │  │
│   │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Key Files:**
- `lib/crewai/src/crewai/agent/core.py` - Agent implementation
- `lib/crewai/src/crewai/crew.py` - Crew orchestration
- `lib/crewai/src/crewai/memory/` - Memory systems
- `lib/crewai/src/crewai/flow/flow.py` - Flow orchestration

### Agent Definition

```python
# lib/crewai/src/crewai/agent/core.py
class Agent(BaseModel):
    role: str               # "Senior Research Analyst"
    goal: str               # "Uncover cutting-edge developments"
    backstory: str          # Personality and context
    llm: BaseLLM
    tools: list[BaseTool]
    allow_delegation: bool = False
    max_iter: int = 25
    max_execution_time: int | None = None
    memory: bool = False
    reasoning: bool = False  # Chain-of-thought
    guardrail: Callable | None = None
```

### Crew Orchestration

```python
# lib/crewai/src/crewai/crew.py
class Crew(BaseModel):
    agents: list[Agent]
    tasks: list[Task]
    process: Process = Process.sequential
    manager_agent: Agent | None = None  # For hierarchical
    memory: bool = False

    def kickoff(self, inputs: dict = None) -> CrewOutput:
        if self.process == Process.sequential:
            return self._run_sequential_process()
        else:
            return self._run_hierarchical_process()

    def _run_sequential_process(self):
        context = ""
        for task in self.tasks:
            result = task.agent.execute_task(task, context)
            context += f"\n{result}"
        return CrewOutput(...)
```

### Multi-Level Memory System

```python
# Short-Term Memory (immediate context)
class ShortTermMemory(Memory):
    storage: RAGStorage  # Vector-based retrieval

    def save(self, item: ShortTermMemoryItem):
        self.storage.add(item.text, item.metadata)

    def search(self, query: str, limit: int) -> list[str]:
        return self.storage.query(query, limit)

# Long-Term Memory (cross-run patterns)
class LongTermMemory(Memory):
    storage: LTMSQLiteStorage

    def save(self, item: LongTermMemoryItem):
        # Store with quality score
        self.storage.save(
            task=item.task,
            expected_output=item.expected_output,
            quality=item.quality
        )

# Entity Memory (knowledge graph)
class EntityMemory(Memory):
    storage: EntitySQLiteStorage

    def save(self, item: EntityMemoryItem):
        self.storage.add_entity(item.name, item.type, item.description)
        for rel in item.relationships:
            self.storage.add_relationship(item.name, rel.target, rel.type)

# Contextual Memory (aggregates all sources)
class ContextualMemory:
    stm: ShortTermMemory
    ltm: LongTermMemory
    entity: EntityMemory
    external: ExternalMemory

    def build_context_for_task(self, task: Task) -> str:
        context = []
        context.extend(self.stm.search(task.description))
        context.extend(self.ltm.search(task.description))
        context.extend(self.entity.search(task.description))
        return "\n".join(context)
```

### Flow Orchestration

```python
# lib/crewai/src/crewai/flow/flow.py
class Flow(BaseModel):
    state: FlowState

    @start()
    def begin(self):
        # Entry point
        return "initial_data"

    @listen("begin")
    def process(self, data):
        # Triggered after begin completes
        return process_data(data)

    @router(routes=["success", "failure"])
    def decide(self, result):
        # Conditional routing
        if result.valid:
            return "success"
        return "failure"

    @listen("success")
    def complete(self, data):
        return final_result(data)
```

---

## 5. AutoGen Architecture

**Repository:** https://github.com/microsoft/autogen

### Core Concept: Actor Model with Pub/Sub

AutoGen uses an event-driven architecture based on CloudEvents:
- Agents are actors with message handlers
- Topics enable publish-subscribe patterns
- Supports distributed execution via gRPC

```
┌────────────────────────────────────────────────────────────┐
│                    AutoGen Layered Architecture             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   ┌──────────────────────────────────────────────────────┐ │
│   │              EXTENSIONS (autogen-ext)                 │ │
│   │  Models │ Agents │ Tools │ Memory │ Code Executors   │ │
│   └──────────────────────────────────────────────────────┘ │
│                            │                               │
│   ┌──────────────────────────────────────────────────────┐ │
│   │              AGENTCHAT (autogen-agentchat)           │ │
│   │  ChatAgent │ Teams │ GroupChat │ Conversations       │ │
│   └──────────────────────────────────────────────────────┘ │
│                            │                               │
│   ┌──────────────────────────────────────────────────────┐ │
│   │                CORE (autogen-core)                    │ │
│   │  BaseAgent │ Runtime │ Topics │ Subscriptions        │ │
│   │  Message Handlers │ Routed Agent │ Tool Agent        │ │
│   └──────────────────────────────────────────────────────┘ │
│                                                            │
│   Event Flow:                                              │
│   ┌─────────┐  publish   ┌─────────┐  route   ┌─────────┐ │
│   │ Agent A │───────────▶│  Topic  │─────────▶│ Agent B │ │
│   └─────────┘            └─────────┘          └─────────┘ │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Key Files:**
- `python/packages/autogen-core/src/autogen_core/_base_agent.py`
- `python/packages/autogen-core/src/autogen_core/_single_threaded_agent_runtime.py`
- `python/packages/autogen-agentchat/src/autogen_agentchat/agents/_base_chat_agent.py`

### Agent Protocol

```python
# autogen-core/_agent.py
@runtime_checkable
class Agent(Protocol):
    @property
    def id(self) -> AgentId: ...

    async def on_message(self, message: Any, ctx: MessageContext) -> Any: ...
    async def save_state(self) -> Mapping[str, Any]: ...
    async def load_state(self, state: Mapping[str, Any]) -> None: ...
```

### Message Routing

```python
# autogen-core/_routed_agent.py
class RoutedAgent(BaseAgent):
    @message_handler
    async def handle_text(self, message: TextMessage, ctx: MessageContext) -> Response:
        # Handles TextMessage type
        ...

    @message_handler(match=lambda msg, ctx: msg.priority == 'high')
    async def handle_urgent(self, message: Any, ctx: MessageContext) -> Response:
        # Custom matching logic
        ...

    @event
    async def on_event(self, message: EventType, ctx: MessageContext) -> None:
        # Fire-and-forget event handler
        ...

    @rpc
    async def handle_rpc(self, message: Request, ctx: MessageContext) -> Response:
        # Request-response pattern
        ...
```

### Topic & Subscription System

```python
# Topics use CloudEvents format
class TopicId:
    type: str    # "com.example.user.created"
    source: str  # "user-service"

# Subscriptions route topics to agents
class TypeSubscription(Subscription):
    def is_match(self, topic_id: TopicId) -> bool:
        return topic_id.type == self._topic_type

    def map_to_agent(self, topic_id: TopicId) -> AgentId:
        return AgentId(type=self._agent_type, key=topic_id.source)
```

### Runtime Implementation

```python
# Single-threaded runtime (standalone)
class SingleThreadedAgentRuntime:
    async def send_message(self, message, recipient: AgentId) -> Any:
        """Direct message (RPC-style)"""
        envelope = SendMessageEnvelope(message, sender, recipient, future)
        self._queue.put(envelope)
        return await future

    async def publish_message(self, message, topic_id: TopicId) -> None:
        """Broadcast to subscribers"""
        envelope = PublishMessageEnvelope(message, topic_id)
        self._queue.put(envelope)

    async def register_factory(self, type: str, factory: Callable) -> AgentType:
        """Register agent factory for lazy instantiation"""
        self._agent_factories[type] = factory
```

### Distributed Runtime (gRPC)

```protobuf
// protos/agent_worker.proto
service AgentRpc {
    rpc OpenChannel(stream Message) returns (stream Message);
    rpc RegisterAgent(RegisterAgentTypeRequest) returns (RegisterAgentTypeResponse);
    rpc AddSubscription(AddSubscriptionRequest) returns (AddSubscriptionResponse);
}
```

---

## 6. Cursor Architecture

**Source:** Web research (closed source)

### Core Concept: Multi-Model Delegation

Cursor uses specialized models for different tasks:
- Primary agent (Claude 3.5 Sonnet) for reasoning
- Apply model for file modifications
- Search models for code retrieval

```
┌────────────────────────────────────────────────────────────┐
│                    Cursor Agent Architecture                │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   User Request                                             │
│        │                                                   │
│        ▼                                                   │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              PRIMARY AGENT (Claude 3.5)             │  │
│   │  ┌───────────────────────────────────────────────┐  │  │
│   │  │  Reasoning + Tool Selection                   │  │  │
│   │  │  "One sentence explanation...why this tool"   │  │  │
│   │  └───────────────────────────────────────────────┘  │  │
│   └─────────────────────────────────────────────────────┘  │
│        │                                                   │
│        ├─────────────────┬─────────────────┐              │
│        ▼                 ▼                 ▼              │
│   ┌─────────┐      ┌──────────┐      ┌──────────┐        │
│   │ Search  │      │  Apply   │      │ Execute  │        │
│   │ Models  │      │  Model   │      │ Terminal │        │
│   └─────────┘      └──────────┘      └──────────┘        │
│        │                 │                 │              │
│        ▼                 ▼                 ▼              │
│   ┌─────────────────────────────────────────────────────┐  │
│   │              LINT FEEDBACK LOOP                      │  │
│   │  Linter Output ──▶ Agent ──▶ Fix ──▶ Repeat         │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Tool Categories

```
Search/Retrieval:
  - codebase_search  (semantic vector search)
  - grep_search      (pattern matching)
  - file_search      (find files)
  - web_search       (external info)
  - read_file        (file contents)

Modification:
  - write_file       (semantic diffs with comments)

Execution:
  - run_command      (terminal commands)

Self-Correction:
  - reapply          (retry with expensive model)
```

### Apply Model Pattern

```
┌─────────────────────────────────────────────────────────┐
│                Apply Model Architecture                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   1. Primary Agent produces semantic diff:              │
│      "// ... existing code ..."                         │
│      "// INSERT: new validation logic"                  │
│      "function validate(input) { ... }"                 │
│                                                         │
│   2. Apply Model (cheaper/faster):                      │
│      - Parses semantic comments                         │
│      - Reconstructs full file                           │
│      - Fixes syntax issues                              │
│                                                         │
│   3. Lint Validation:                                   │
│      - Run linter on result                             │
│      - If errors, send to Primary Agent                 │
│      - Max 3 retry iterations                           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Context Management

```
1. User-Provided Context
   - @file, @folder syntax for explicit attachment
   - Passed via <attached-files> blocks

2. Semantic Indexing
   - Codebase embedded in vector store
   - Reranking model filters by relevance
   - Optimal context without manual search

3. Prompt Caching
   - Static system prompts (no personalization)
   - Full Anthropic prompt caching benefits
   - Reduced latency and cost per tool call
```

### Prompt Engineering Patterns

```
- XML/Markdown hybrid formatting
- Explicit identity: "powered by Claude 3.5 Sonnet"
- Positive constraints: "Refrain from apologizing"
- Bounded iteration: "DO NOT loop more than 3 times"
- Root-cause focus: "Address root cause instead of symptoms"
- File size limits: "Keep files under 500 lines"
- Read-before-edit: "you MUST read contents before editing"
```

---

## 7. Comparative Analysis

### Durability Mechanisms

| Framework | Primary Mechanism | Persistence | Recovery |
|-----------|------------------|-------------|----------|
| LangChain | Retry + Fallback | In-memory steps | Manual checkpoint |
| LangGraph | Checkpoint system | SQLite/Postgres | Automatic resume |
| Dust | Temporal workflows | Temporal server | Workflow restart |
| CrewAI | Memory systems | SQLite/Vector DB | Context recall |
| AutoGen | State save/load | Custom | Manual restore |
| Cursor | Lint feedback | Session-based | User intervention |

### Multi-Agent Support

| Framework | Pattern | Communication | Coordination |
|-----------|---------|---------------|--------------|
| LangChain | Sequential | Chain output | Executor |
| LangGraph | Graph nodes | Channels | Pregel engine |
| Dust | Embedded tools | Activity calls | Temporal |
| CrewAI | Role-based crews | Task context | Process manager |
| AutoGen | Actor model | Pub/Sub topics | Runtime |
| Cursor | Single agent | N/A | N/A |

### Human-in-the-Loop

| Framework | Mechanism | Resume Support | Approval Workflow |
|-----------|-----------|----------------|-------------------|
| LangChain | Callbacks | Manual | Custom |
| LangGraph | interrupt() | Command-based | Built-in |
| Dust | Deferred events | Workflow signal | MCP approval |
| CrewAI | human_input flag | Task retry | Guardrails |
| AutoGen | Configurable | Message-based | Custom |
| Cursor | User prompts | Continue button | Tool-level |

### Performance Characteristics

| Framework | Execution Speed | Memory Footprint | Scalability |
|-----------|----------------|------------------|-------------|
| LangChain | Moderate | Low | Vertical |
| LangGraph | Moderate | Medium | Checkpoint-based |
| Dust | High (Temporal) | Low (workers) | Horizontal |
| CrewAI | Fast (5.76x*) | Medium | Vertical |
| AutoGen | Variable | Medium | Distributed |
| Cursor | Fast (250 tok/s) | Low | N/A |

*CrewAI claims 5.76x faster than LangGraph in certain benchmarks

---

## 8. Recommendations

### When to Use Each Framework

**LangChain**
- Rapid prototyping and experimentation
- Simple tool-calling agents
- When you need extensive integrations
- Learning agent development

**LangGraph**
- Complex multi-step workflows
- Human-in-the-loop requirements
- Production systems needing checkpoints
- Cyclic reasoning patterns

**Dust**
- Enterprise-scale deployments
- When Temporal infrastructure is available
- Multi-connector data ingestion
- 24/7 autonomous agents

**CrewAI**
- Collaborative multi-agent scenarios
- Role-based task decomposition
- When memory across runs matters
- Team simulation use cases

**AutoGen**
- Distributed agent systems
- Cross-language requirements (.NET + Python)
- Pub/sub event-driven architectures
- Research and experimentation

**Cursor**
- IDE-integrated coding agents
- File modification workflows
- When lint validation is critical
- Developer productivity tools

### Architecture Best Practices

1. **Explicit State Management**
   - Always track intermediate steps
   - Use typed state schemas
   - Persist state for long-running agents

2. **Checkpoint Early, Checkpoint Often**
   - Save state before risky operations
   - Enable resume from any step
   - Version your checkpoint format

3. **Retry with Intelligence**
   - Exponential backoff with jitter
   - Different strategies per operation type
   - Know when NOT to retry (non-idempotent)

4. **Validation Loops**
   - Use linters for code changes
   - Implement guardrails for outputs
   - Limit iteration counts

5. **Tool Abstraction**
   - Separate reasoning from execution
   - Make tools composable
   - Document tool contracts clearly

6. **Observability**
   - Trace all agent decisions
   - Log tool calls and results
   - Monitor resource usage

---

## Sources

- [LangChain GitHub](https://github.com/langchain-ai/langchain)
- [LangGraph GitHub](https://github.com/langchain-ai/langgraph)
- [Dust GitHub](https://github.com/dust-tt/dust)
- [CrewAI GitHub](https://github.com/crewAIInc/crewAI)
- [AutoGen GitHub](https://github.com/microsoft/autogen)
- [Temporal + Dust Blog](https://temporal.io/blog/how-dust-builds-agentic-ai-temporal)
- [How Cursor AI IDE Works](https://blog.sshh.io/p/how-cursor-ai-ide-works)
- [Cursor Features](https://cursor.com/features)
- [AutoGen Architecture Docs](https://microsoft.github.io/autogen/stable/index.html)
