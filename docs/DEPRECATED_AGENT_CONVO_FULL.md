> **DEPRECATED**: This document is kept for historical reference. For current documentation, see:
> - [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture
> - [COMPONENTS.md](./COMPONENTS.md) - Component documentation
> - [DATA_MODELS.md](./DATA_MODELS.md) - Data models
> - [DATA_FLOW.md](./DATA_FLOW.md) - Data flow diagrams
> - [API_REFERENCE.md](./API_REFERENCE.md) - API documentation

---

## USER (2026-01-04T07:45:11.279Z)

<ide_opened_file>The user opened the file /Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_ARCHITECTURE_RESEARCH.md in the IDE. This may or may not be related to the current task.</ide_opened_file>

Scope:

Build an agent based on (Web + Python) on top of exisitng repo optimized for web research + verification + computation

UI: 
In thinking view:
  what the model decided (its “thinking” text, in the thinking UI)
  what tools it called, what came back (summaries + evidence snippets, not full pages)
Answer view:
Markdown formatted answer with citations 

The model has access to these tools:
  Web (Parallel): search, extract to view information it doesn't know 
  Python: exec to perform calucations, math and other operations depending upon the task 

Goals: (on how to implement? look up agent architecture research doc if not clear enough at the bottom of doc you'll find resources to dive deep)
Evidence-grounded answers: final answer includes citations to exact extracted snippets.
Durable runs: crash → resume; cancel works; retries are recorded.
Full trace system: Each user message/run has a complete trace of: model requests/responses (raw + tokens + latency), tool calls/results (raw + latency)retries/errors
Thinking UI is a projection of trace events (not a separate narrative generator).

APIs that we're gonna use:
 Parallel Search API (lookup parallel.ai apis) 
 Parallel Extract API
a little more info on parallel: [Search: returns ranked URLs + snippets
Extract: given URL(s) + objective → returns LLM-ready markdown, including JS-heavy pages/PDFs]
Local Python runtime (or sandbox)
model: gpt-oss-120b (look up on this what model uses how to bring things to work around this model) 


Everything we build must be on top of this repo 

Plan both backend and frontend system design with data models, state and data flow for production grade setup 

note: UI must never render full extracted pages by default — only metadata + cited snippets. Full content is backend-only.

Non negotiables
1. Seamlesss monitoring and observability
2. Durability 
3. Trace system that shows everything
4. Answer accuracy
---
## ASSISTANT (2026-01-04T07:45:22.082Z)

<details><summary>Thinking...</summary>

The user wants to build an agent system on top of their existing reasoner repo. This is a significant feature addition that requires careful planning. Let me break down what they're asking for:

1. **Agent Architecture**: Web research + verification + computation agent
2. **Tools**: 
   - Web (Parallel): search and extract APIs from parallel.ai
   - Python: local execution for calculations
3. **UI Requirements**:
   - Thinking view: model decisions, tool calls, results (summaries, not full pages)
   - Answer view: Markdown with citations
4. **Key Goals**:
   - Evidence-grounded answers with citations
   - Durable runs (crash recovery, cancel, retry tracking)
   - Full trace system (model requests/responses, tool calls, retries/errors)
   - Thinking UI as projection of trace events
5. **Model**: gpt-oss-120b (need to research this)
6. **Non-negotiables**: Monitoring/observability, durability, trace system, answer accuracy

They've mentioned looking at an agent architecture research doc. Let me explore:
1. The existing codebase structure
2. The agent architecture research doc they mentioned
3. The parallel.ai APIs
4. The gpt-oss-120b model

I should launch Explore agents in parallel to understand:
1. The existing repo structure (FastAPI backend, React frontend)
2. The agent architecture research document
3. Current data models and patterns

This is Phase 1 - Initial Understanding. I need to explore the codebase and the research doc they mentioned.

</details>
---
## ASSISTANT (2026-01-04T07:45:22.962Z)

I'll help you design an agent system for web research, verification, and computation. Let me first explore the codebase and the research document you mentioned to understand the existing architecture and gather requirements.
---
## ASSISTANT (2026-01-04T07:45:27.244Z)

**Tool Use:** Task
```json
{"description":"Explore existing repo structure","prompt":"Explore the existing reasoner codebase structure comprehensively. I need to understand:\n\n1. The current FastAPI backend architecture in `orchestrator/` - entry points, routing, data models, database schema\n2. The React/Vite frontend in `ui/` - component structure, state management, API integration patterns\n3. Current chat engine implementation and provider patterns\n4. Any existing trace/logging systems\n5. SQLite storage patterns and models\n\nFocus on understanding the architectural patterns so we can build on top of them. Provide file paths and key code patterns.","subagent_type":"Explore"}
```
---
## ASSISTANT (2026-01-04T07:45:30.282Z)

**Tool Use:** Task
```json
{"description":"Read agent research document","prompt":"Read and analyze the agent architecture research document at docs/AGENT_ARCHITECTURE_RESEARCH.md thoroughly. \n\nExtract:\n1. Key architectural patterns recommended\n2. Trace system designs\n3. Tool execution patterns\n4. UI projection approaches\n5. Durability/recovery strategies\n6. Any specific implementation recommendations\n7. Resources and references mentioned at the bottom\n\nProvide a comprehensive summary of the research findings that will inform our implementation.","subagent_type":"Explore"}
```
---
## ASSISTANT (2026-01-04T07:45:35.188Z)

**Tool Use:** Task
```json
{"description":"Research parallel.ai and gpt-oss","prompt":"Research the following APIs and model that we need to integrate:\n\n1. **Parallel.ai APIs**: Look up parallel.ai search and extract APIs. Find:\n   - API endpoints and authentication\n   - Request/response formats\n   - Rate limits and pricing considerations\n   - How to use search (returns ranked URLs + snippets) and extract (URL + objective → markdown)\n\n2. **gpt-oss-120b model**: Research this model:\n   - What is it? (likely an open-source model)\n   - How to access it (API endpoint, provider)\n   - Token limits, context window\n   - Any special considerations for tool use/function calling\n\nUse web search to find current documentation and specifications.","subagent_type":"Explore"}
```
---
## USER (2026-01-04T07:45:55.908Z)


---
## USER (2026-01-04T07:47:15.646Z)


---
## USER (2026-01-04T07:48:58.269Z)


---
## ASSISTANT (2026-01-04T07:49:11.408Z)

<details><summary>Thinking...</summary>

Excellent! I now have comprehensive information from all three exploration agents. Let me summarize what I've learned:

## Existing Codebase:
1. **FastAPI backend** with modular architecture - routes, providers, storage, thinking strategies
2. **React/Vite frontend** with Zustand state management, SSE streaming, 3-pane layout
3. **SQLite storage** with conversations, runs, trace_events tables
4. **Thinking strategies** using strategy pattern (currently DirectStrategy)
5. **Provider abstraction** with OpenAI-compatible implementation
6. **Comprehensive tracing** with trace_events table (llm_request, llm_response, tool_call, etc.)

## Agent Architecture Research Key Takeaways:
1. **5 Universal Patterns**: Explicit state tracking, Checkpoint/Resume, Retry with backoff, Validation loops, Tool abstraction
2. **LangGraph checkpoint pattern** is most relevant for production durability
3. **Explicit state management** is foundation of reliable agents
4. **Trace everything**: decisions, tool calls, results

## Parallel.ai APIs:
- **Search API**: POST to `https://api.parallel.ai/v1beta/search` with x-api-key header
- **Extract API**: POST to `https://api.parallel.ai/v1beta/extract` for URL → markdown extraction
- Pricing: $5/1000 searches, $1/1000 extracts

## gpt-oss-120b Model:
- 117B params MoE, 5.1B active
- 128K context window
- Native function calling, structured outputs, chain-of-thought reasoning
- Can be self-hosted via vLLM or LM Studio
- Uses Harmony Chat Format

Now I need to:
1. Ask the user some clarifying questions
2. Launch a Plan agent to design the implementation
3. Write the final plan

Let me first clarify some questions with the user about their specific requirements.

</details>
---
## ASSISTANT (2026-01-04T07:49:16.296Z)

I've gathered comprehensive information about the codebase, agent architecture research, and the APIs. Let me summarize the key findings and clarify a few things before designing the implementation plan.

## Key Findings

**Existing Architecture:**
- FastAPI backend with modular providers, thinking strategies, and SQLite storage
- React frontend with Zustand state management and SSE streaming
- Existing trace system with `trace_events` table (llm_request, llm_response, tool_call, etc.)
- Provider abstraction supporting OpenAI-compatible endpoints

**Agent Research Highlights:**
- 5 universal patterns: Explicit state, Checkpoint/Resume, Retry with backoff, Validation loops, Tool abstraction
- LangGraph checkpoint pattern is most mature for production durability
- Trace everything: decisions, tool calls, results
- Dual-layer tracing: internal (full observability) + UI (human-friendly summaries)

**APIs & Model:**
- **Parallel Search**: Returns ranked URLs + excerpts ($5/1000 requests)
- **Parallel Extract**: URL → LLM-ready markdown ($1/1000 URLs)
- **gpt-oss-120b**: 117B MoE model, 128K context, native tool calling, vLLM/LM Studio compatible
---
## ASSISTANT (2026-01-04T07:49:25.233Z)

**Tool Use:** AskUserQuestion
```json
{"questions":[{"question":"How should the agent handle Python code execution? Should we use a sandboxed runtime (Docker container) or a local subprocess with restrictions?","header":"Python Runtime","options":[{"label":"Docker sandbox (Recommended)","description":"Secure isolated container. Safer but requires Docker installed."},{"label":"Local subprocess","description":"Direct execution with timeout/restrictions. Simpler but less secure."},{"label":"E2B sandbox (cloud)","description":"Cloud-hosted sandbox via e2b.dev API. Zero local setup but adds latency and cost."}],"multiSelect":false},{"question":"For crash recovery and durable runs, what level of durability do you need?","header":"Durability","options":[{"label":"SQLite checkpoints (Recommended)","description":"Store agent state in SQLite. Can resume after restarts. Works with existing infra."},{"label":"Temporal.io workflows","description":"Enterprise-grade durability. Requires running Temporal server. Best for high-scale production."},{"label":"Redis state store","description":"Fast in-memory with persistence. Good for distributed setups but adds dependency."}],"multiSelect":false},{"question":"Should the agent support multiple runs in parallel (e.g., user sends new query while previous is running)?","header":"Concurrency","options":[{"label":"Sequential only","description":"One active run per conversation. Simpler state management."},{"label":"Parallel runs (Recommended)","description":"Multiple concurrent runs. More complex but better UX for power users."}],"multiSelect":false}]}
```
---
## USER (2026-01-04T07:51:04.513Z)


---
## ASSISTANT (2026-01-04T07:51:14.650Z)

<details><summary>Thinking...</summary>

The user wants me to design for production, so I should make recommendations that are production-grade. They're asking me to make the architectural decisions based on what's best for production. Let me now launch a Plan agent to design the full system with production-grade considerations.

Key decisions I need to make for production:
1. **Python Runtime**: For production, E2B sandbox (cloud) or Docker sandbox would be the right choice. E2B is probably better for production since it's managed and doesn't require Docker on the deployment target.
2. **Durability**: For production, SQLite checkpoints can work well for single-instance deployments. For high-scale production, Temporal.io is the gold standard. But since they're building on an existing repo that uses SQLite, SQLite checkpoints might be the right pragmatic choice that can evolve.
3. **Concurrency**: For production, parallel runs would be better UX.

Let me launch a Plan agent with all the context gathered.

</details>
---
## ASSISTANT (2026-01-04T07:51:15.406Z)

Understood - you want a production-grade design. Let me launch a Plan agent to design the full system architecture with production considerations in mind.
---
## ASSISTANT (2026-01-04T07:51:40.583Z)

**Tool Use:** Task
```json
{"description":"Design agent architecture plan","prompt":"Design a comprehensive implementation plan for building a web research agent on top of an existing FastAPI + React codebase. This is for PRODUCTION deployment.\n\n## Existing Architecture (Build On Top)\n\n**Backend (orchestrator/):**\n- FastAPI app at `orchestrator/app.py` with lifespan hooks, CORS, request logging\n- Routes: `/api/conversations`, `/api/runs` (SSE streaming), `/api/health`\n- Schemas at `orchestrator/schemas.py` - CreateRunRequest/Response, TraceEventResponse\n- Chat engine at `orchestrator/engine/chat_engine.py` - orchestrates thinking strategies\n- Provider abstraction at `orchestrator/providers/` - OpenAI-compatible with retry/backoff\n- Thinking strategies at `orchestrator/thinking/` - strategy pattern, StreamParser\n- SQLite storage at `orchestrator/storage/` with tables: conversations, runs, trace_events\n- Existing trace_events schema: id, run_id, seq (unique ordering), event_type, event_status, actor, content_json, duration_ms\n\n**Frontend (ui/):**\n- React 18.3 + TypeScript + Vite + Tailwind\n- Zustand store at `ui/src/hooks/useStore.ts`\n- SSE streaming at `ui/src/hooks/useSSE.ts` (TOKEN, THINKING_TOKEN events)\n- API client at `ui/src/api/client.ts`\n- 3-pane layout: sidebar (conversations), main (chat), right panel (trace viewer)\n\n## Requirements\n\n**Core Agent Capabilities:**\n1. **Web Tools (Parallel)**: Search API (POST https://api.parallel.ai/v1beta/search) and Extract API (POST https://api.parallel.ai/v1beta/extract)\n2. **Python Execution**: Sandboxed code execution for calculations\n3. **Model**: gpt-oss-120b via OpenAI-compatible API (128K context, native function calling, Harmony format)\n\n**UI Requirements:**\n- Thinking view: Model decisions, tool calls with summaries + cited snippets (NOT full pages)\n- Answer view: Markdown formatted with inline citations to extracted snippets\n\n**Non-Negotiables:**\n1. **Seamless monitoring/observability**: Full trace system showing everything\n2. **Durability**: Crash → resume, cancel works, retries recorded\n3. **Trace system**: Each run has complete trace of model requests/responses (raw + tokens + latency), tool calls/results, retries/errors\n4. **Thinking UI is a projection of trace events** (not separate narrative)\n5. **Answer accuracy**: Evidence-grounded with citations\n\n## Production Considerations\n- Design for cloud deployment\n- Multi-instance scalability \n- Secure code execution (sandboxed)\n- API key management\n- Rate limiting and quotas\n- Error recovery and circuit breakers\n\n## From Agent Architecture Research\nKey patterns to apply:\n1. **Explicit State Tracking**: Track agent state explicitly at each step\n2. **Checkpoint/Resume**: Persist execution state, resume after crash\n3. **Retry with Backoff**: Exponential backoff with jitter for transient failures\n4. **Validation Loops**: Self-correction mechanisms\n5. **Tool Abstraction**: Clean separation between reasoning and action\n\nRecommended approach: LangGraph-style checkpoint pattern with SQLite (matches existing infra) that can evolve to Temporal for enterprise scale.\n\n## Deliverables\n\nDesign a detailed implementation plan covering:\n\n1. **Data Models**: New SQLite tables, Pydantic schemas for agent state, tool calls, citations\n2. **Backend Architecture**:\n   - Agent loop implementation (tool use → model → tool use cycle)\n   - Tool registry and execution\n   - Parallel.ai integration (search + extract)\n   - Python sandbox integration (recommend E2B for production or Docker)\n   - Checkpoint/resume system\n   - Trace event types and recording\n3. **Frontend Architecture**:\n   - Thinking panel redesign for tool calls visualization\n   - Citation system for answer view\n   - Trace event projection to UI\n4. **State Machine**: Agent states (planning, tool_calling, synthesizing, complete, error, cancelled)\n5. **API Design**: New/modified endpoints\n6. **Configuration**: New config sections for parallel.ai, sandbox, agent settings\n7. **File-by-file implementation order with dependencies\n\nBe specific about file paths and code patterns that integrate with the existing architecture.","subagent_type":"Plan"}
```
---
## USER (2026-01-04T07:55:41.771Z)


---
## ASSISTANT (2026-01-04T07:55:49.374Z)

<details><summary>Thinking...</summary>

The Plan agent has provided a comprehensive implementation plan. Now I need to:

1. Review the plan and ensure it aligns with the user's requirements
2. Read some critical files to validate the plan's assumptions
3. Write the final plan to the plan file
4. Call ExitPlanMode

Let me read a few critical files to validate the plan's assumptions about the existing architecture, then write the final plan.

</details>
---
## ASSISTANT (2026-01-04T07:55:50.018Z)

Excellent! The Plan agent has produced a comprehensive design. Let me read a few critical files to validate the approach, then write the final plan.
---
## ASSISTANT (2026-01-04T07:55:50.539Z)

**Tool Use:** Read
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/orchestrator/storage/schema.sql"}
```
---
## ASSISTANT (2026-01-04T07:55:51.126Z)

**Tool Use:** Read
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/orchestrator/routes/runs.py"}
```
---
## ASSISTANT (2026-01-04T07:55:51.578Z)

**Tool Use:** Read
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/orchestrator/providers/base.py"}
```
---
## USER (2026-01-04T07:55:51.599Z)


---
## USER (2026-01-04T07:55:51.602Z)


---
## USER (2026-01-04T07:55:51.602Z)


---
## ASSISTANT (2026-01-04T07:56:01.300Z)

<details><summary>Thinking...</summary>

I've now validated the existing architecture:

1. **schema.sql** - The existing `trace_events` table already has support for `tool_call`, `tool_response` event types, `parent_event_id` linking, `step_number`, etc. This is well-designed for agent use.

2. **runs.py** - The SSE pattern with `_active_runs` dict, `asyncio.Queue`, background tasks, and abort signals is clear. The agent routes should follow this pattern.

3. **base.py** - The `LLMProvider` protocol already supports `tools` parameter for function calling and streaming with `on_token`/`on_reasoning` callbacks. The agent can leverage this directly.

The plan from the Plan agent is solid and aligns well with the existing architecture. Now I'll write the final plan to the plan file.

</details>
---
## ASSISTANT (2026-01-04T07:56:02.443Z)

The existing architecture is well-suited for extending with the agent system. The trace_events table already supports tool_call/tool_response events with step_number and parent linking. Now let me write the final plan.
---
## ASSISTANT (2026-01-04T07:56:54.693Z)

**Tool Use:** Write
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","content":"# Web Research Agent Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent on top of the existing Reasoner repo with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox\n- **Model**: gpt-oss-120b via OpenAI-compatible API\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Architecture Decisions (Production-Grade)\n\n| Concern | Decision | Rationale |\n|---------|----------|-----------|\n| **Python Sandbox** | E2B (cloud) with Docker fallback | E2B is managed, secure, scales. Docker for local dev. |\n| **Durability** | SQLite checkpoints (existing infra) | Matches current stack. Can evolve to Temporal later. |\n| **Concurrency** | Parallel runs supported | Better UX, production expectation |\n| **Multi-instance** | Redis pub/sub for SSE (optional) | Current in-memory queue works for single instance |\n\n---\n\n## Data Model Changes\n\n### New Table: `agent_checkpoints`\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_checkpoints (\n    checkpoint_id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n    state TEXT NOT NULL,           -- planning | tool_calling | synthesizing | complete | error | cancelled\n    step_number INTEGER NOT NULL,\n    messages_json TEXT NOT NULL,\n    tool_calls_pending_json TEXT,\n    tool_results_json TEXT,\n    citations_json TEXT,\n    last_tool_call_id TEXT,\n    error_count INTEGER DEFAULT 0,\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### Extended `runs` Table\n\nAdd column: `mode TEXT` with values `chat` | `agent`\n\n### Citation Schema (Pydantic)\n\n```python\nclass Citation(BaseModel):\n    id: str                # cite_1, cite_2, ...\n    source_url: str\n    title: str\n    snippet: str           # Relevant extracted text (NOT full page)\n    extracted_at: str\n    tool_call_id: str\n```\n\n---\n\n## Backend Architecture\n\n### New Directory: `orchestrator/agent/`\n\n```\norchestrator/agent/\n├── __init__.py\n├── agent_engine.py       # Main agent loop with checkpoint/resume\n├── state_machine.py      # AgentState enum, transitions, AgentContext\n├── checkpoint.py         # CheckpointManager for save/restore\n└── tools/\n    ├── __init__.py\n    ├── base.py           # BaseTool ABC, ToolResult dataclass\n    ├── registry.py       # ToolRegistry with OpenAI format conversion\n    ├── web_search.py     # Parallel.ai Search API integration\n    ├── web_extract.py    # Parallel.ai Extract API integration\n    └── python_sandbox.py # E2B/Docker sandbox execution\n```\n\n### Agent State Machine\n\n```\nSTART → PLANNING ←→ TOOL_CALLING → SYNTHESIZING → COMPLETE\n            ↓            ↓              ↓\n         ERROR ←←←←←←←←←←←←←←←←←←←←←←←←←\n            ↑\n       CANCELLED (from any non-terminal state)\n```\n\n### Agent Loop (agent_engine.py)\n\n1. Initialize or restore context from checkpoint\n2. **PLANNING**: Call model with tool definitions, get tool_calls or direct answer\n3. **TOOL_CALLING**: Execute tools in parallel (max 3 concurrent), collect citations\n4. Loop back to PLANNING with tool results until model synthesizes\n5. **SYNTHESIZING**: Generate final answer with citation references\n6. Checkpoint before each step for crash recovery\n\n### Tool Implementations\n\n**WebSearchTool** (`web_search.py`):\n- POST to `https://api.parallel.ai/v1beta/search`\n- Headers: `x-api-key`, `parallel-beta: search-extract-2025-10-10`\n- Returns: URLs, titles, snippets as citations\n\n**WebExtractTool** (`web_extract.py`):\n- POST to `https://api.parallel.ai/v1beta/extract`\n- Returns: LLM-ready markdown with `excerpts` (NOT full content to UI)\n- Extracts citations from excerpts\n\n**PythonSandboxTool** (`python_sandbox.py`):\n- E2B cloud sandbox (prod) or Docker (dev)\n- Timeout: 30s max, memory limit, network disabled\n- Returns: stdout, stderr, result\n\n---\n\n## API Design\n\n### New Routes: `orchestrator/routes/agent.py`\n\n| Endpoint | Method | Description |\n|----------|--------|-------------|\n| `/api/agent/conversations/{id}/runs` | POST | Create agent research run |\n| `/api/agent/runs/{id}/stream` | GET | SSE stream with agent events |\n| `/api/agent/runs/{id}/resume` | POST | Resume from checkpoint |\n| `/api/agent/runs/{id}/cancel` | POST | Cancel running agent |\n| `/api/agent/runs/{id}/citations` | GET | Get collected citations |\n\n### SSE Event Types\n\n| Event | Description |\n|-------|-------------|\n| `AGENT_STATE` | State transition (planning → tool_calling) |\n| `TOOL_CALL_START` | Tool call initiated with args |\n| `TOOL_CALL_RESULT` | Tool completed with summary (not full content) |\n| `CITATION` | New citation extracted |\n| `THINKING` | Model reasoning tokens |\n| `ANSWER` | Final answer tokens |\n| `COMPLETE` | Run finished |\n\n---\n\n## Frontend Architecture\n\n### New Components\n\n| Component | Purpose |\n|-----------|---------|\n| `AgentThinkingPanel.tsx` | Shows steps, tool calls, state indicator |\n| `ToolCallCard.tsx` | Individual tool call with status, summary |\n| `CitationInline.tsx` | Clickable `[1]` reference with tooltip preview |\n| `AnswerWithCitations.tsx` | Markdown renderer that links `[cite_N]` to citations |\n| `AgentRunMessage.tsx` | Complete agent run display |\n\n### Store Extensions (`useStore.ts`)\n\n```typescript\n// Add to store\nagentSteps: Record<string, AgentStep[]>;      // runId → steps\nagentCitations: Record<string, Citation[]>;   // runId → citations\ncurrentAgentState: Record<string, AgentState>; // runId → state\n```\n\n### New Hook: `useAgentSSE.ts`\n\nHandle agent-specific events:\n- `TOOL_CALL_START` → Add pending tool to current step\n- `TOOL_CALL_RESULT` → Update tool with summary + citations\n- `CITATION` → Append to citations list\n- `THINKING` → Stream to thinking panel\n- `ANSWER` → Stream to answer area\n\n---\n\n## Configuration Changes\n\n### `chat_config.yaml` additions\n\n```yaml\nagent:\n  max_steps: 10\n  step_timeout_ms: 60000\n  tools:\n    max_concurrent: 3\n    default_timeout_ms: 30000\n    max_retries: 2\n\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n  extract:\n    timeout_ms: 30000\n\nsandbox:\n  type: ${SANDBOX_TYPE:-e2b}\n  e2b:\n    api_key: ${E2B_API_KEY:-}\n    timeout_seconds: 30\n  docker:\n    image: \"python:3.11-slim\"\n    memory_limit: \"256m\"\n    network_disabled: true\n```\n\n---\n\n## Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add agent_checkpoints table, runs.mode column\n2. `orchestrator/schemas.py` - Add AgentState, Citation, ToolCall schemas\n3. `orchestrator/storage/repositories/agent_repo.py` - Checkpoint CRUD\n\n### Phase 2: Tool Layer\n4. `orchestrator/agent/tools/base.py` - BaseTool ABC, ToolResult\n5. `orchestrator/agent/tools/registry.py` - ToolRegistry\n6. `orchestrator/agent/tools/web_search.py` - Parallel Search integration\n7. `orchestrator/agent/tools/web_extract.py` - Parallel Extract integration\n8. `orchestrator/agent/tools/python_sandbox.py` - E2B/Docker sandbox\n\n### Phase 3: Agent Core\n9. `orchestrator/agent/state_machine.py` - AgentContext, AgentStateMachine\n10. `orchestrator/agent/checkpoint.py` - CheckpointManager\n11. `orchestrator/agent/agent_engine.py` - Main agent loop\n\n### Phase 4: API Layer\n12. `orchestrator/config.py` - Add AgentConfig, ParallelConfig, SandboxConfig\n13. `orchestrator/chat_config.yaml` - Add new config sections\n14. `orchestrator/routes/agent.py` - Agent API routes\n15. `orchestrator/app.py` - Register agent router\n\n### Phase 5: Frontend Types & API\n16. `ui/src/types/agent.ts` - TypeScript types\n17. `ui/src/api/client.ts` - Add agent API functions\n\n### Phase 6: Frontend State & Streaming\n18. `ui/src/hooks/useStore.ts` - Add agent state slices\n19. `ui/src/hooks/useAgentSSE.ts` - Agent SSE hook\n\n### Phase 7: Frontend Components\n20. `ui/src/components/ToolCallCard.tsx` - Tool call visualization\n21. `ui/src/components/AgentThinkingPanel.tsx` - Thinking panel\n22. `ui/src/components/CitationInline.tsx` - Inline citation\n23. `ui/src/components/AnswerWithCitations.tsx` - Answer renderer\n24. `ui/src/components/AgentRunMessage.tsx` - Complete run display\n25. `ui/src/components/ConversationView.tsx` - Integrate agent mode\n\n---\n\n## Critical Files Reference\n\n| File | Purpose |\n|------|---------|\n| `orchestrator/agent/agent_engine.py` | Core agent loop - most complex |\n| `orchestrator/routes/runs.py` | Reference for SSE pattern |\n| `orchestrator/providers/base.py` | LLMProvider protocol (already has tools support) |\n| `orchestrator/engine/chat_engine.py` | Reference for trace recording |\n| `ui/src/hooks/useSSE.ts` | Reference for frontend SSE |\n\n---\n\n## UI Behavior Notes\n\n1. **Thinking Panel shows**:\n   - Model decisions (reasoning tokens)\n   - Tool calls with status (pending/running/success/error)\n   - Tool result **summaries** and cited snippets only\n\n2. **Answer Panel shows**:\n   - Markdown formatted response\n   - Inline citations as `[1]`, `[2]` etc.\n   - Hover/click reveals snippet + source URL\n\n3. **Full extracted content** stays backend-only (never sent to UI unless explicitly expanded)\n\n---\n\n## Production Checklist\n\n- [ ] E2B API key in environment\n- [ ] Parallel.ai API key in environment\n- [ ] Rate limiting on agent endpoints\n- [ ] Circuit breaker for external APIs\n- [ ] Checkpoint cleanup job (delete old checkpoints)\n- [ ] Metrics/alerts for tool failures\n- [ ] Redis pub/sub for multi-instance (when scaling)\n"}
```
---
## USER (2026-01-04T07:56:55.420Z)


---
## ASSISTANT (2026-01-04T07:57:02.453Z)

<details><summary>Thinking...</summary>

I've written the comprehensive plan. Now I should call ExitPlanMode to indicate that I'm done planning and ready for the user to review and approve.

</details>
---
## ASSISTANT (2026-01-04T07:57:06.763Z)

I've written a comprehensive implementation plan covering:

**Backend**:
- New `agent/` module with tools (Parallel.ai search/extract, Python sandbox), state machine, checkpoint system
- Agent engine with planning → tool_calling → synthesizing loop
- Full trace event recording for every step

**Frontend**:
- AgentThinkingPanel showing tool calls with summaries (not full pages)
- Citation system with inline references and tooltip previews
- SSE streaming for real-time tool execution feedback

**Production Features**:
- E2B cloud sandbox for secure Python execution
- SQLite checkpoints for crash recovery
- Parallel tool execution with circuit breakers
- Full observability through existing trace_events system

The plan builds entirely on your existing patterns (SSE streaming, trace events, provider abstraction) while adding the agent loop and tool execution layer.
---
## ASSISTANT (2026-01-04T07:57:06.802Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent on top of the existing Reasoner repo with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox\n- **Model**: gpt-oss-120b via OpenAI-compatible API\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Architecture Decisions (Production-Grade)\n\n| Concern | Decision | Rationale |\n|---------|----------|-----------|\n| **Python Sandbox** | E2B (cloud) with Docker fallback | E2B is managed, secure, scales. Docker for local dev. |\n| **Durability** | SQLite checkpoints (existing infra) | Matches current stack. Can evolve to Temporal later. |\n| **Concurrency** | Parallel runs supported | Better UX, production expectation |\n| **Multi-instance** | Redis pub/sub for SSE (optional) | Current in-memory queue works for single instance |\n\n---\n\n## Data Model Changes\n\n### New Table: `agent_checkpoints`\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_checkpoints (\n    checkpoint_id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n    state TEXT NOT NULL,           -- planning | tool_calling | synthesizing | complete | error | cancelled\n    step_number INTEGER NOT NULL,\n    messages_json TEXT NOT NULL,\n    tool_calls_pending_json TEXT,\n    tool_results_json TEXT,\n    citations_json TEXT,\n    last_tool_call_id TEXT,\n    error_count INTEGER DEFAULT 0,\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### Extended `runs` Table\n\nAdd column: `mode TEXT` with values `chat` | `agent`\n\n### Citation Schema (Pydantic)\n\n```python\nclass Citation(BaseModel):\n    id: str                # cite_1, cite_2, ...\n    source_url: str\n    title: str\n    snippet: str           # Relevant extracted text (NOT full page)\n    extracted_at: str\n    tool_call_id: str\n```\n\n---\n\n## Backend Architecture\n\n### New Directory: `orchestrator/agent/`\n\n```\norchestrator/agent/\n├── __init__.py\n├── agent_engine.py       # Main agent loop with checkpoint/resume\n├── state_machine.py      # AgentState enum, transitions, AgentContext\n├── checkpoint.py         # CheckpointManager for save/restore\n└── tools/\n    ├── __init__.py\n    ├── base.py           # BaseTool ABC, ToolResult dataclass\n    ├── registry.py       # ToolRegistry with OpenAI format conversion\n    ├── web_search.py     # Parallel.ai Search API integration\n    ├── web_extract.py    # Parallel.ai Extract API integration\n    └── python_sandbox.py # E2B/Docker sandbox execution\n```\n\n### Agent State Machine\n\n```\nSTART → PLANNING ←→ TOOL_CALLING → SYNTHESIZING → COMPLETE\n            ↓            ↓              ↓\n         ERROR ←←←←←←←←←←←←←←←←←←←←←←←←←\n            ↑\n       CANCELLED (from any non-terminal state)\n```\n\n### Agent Loop (agent_engine.py)\n\n1. Initialize or restore context from checkpoint\n2. **PLANNING**: Call model with tool definitions, get tool_calls or direct answer\n3. **TOOL_CALLING**: Execute tools in parallel (max 3 concurrent), collect citations\n4. Loop back to PLANNING with tool results until model synthesizes\n5. **SYNTHESIZING**: Generate final answer with citation references\n6. Checkpoint before each step for crash recovery\n\n### Tool Implementations\n\n**WebSearchTool** (`web_search.py`):\n- POST to `https://api.parallel.ai/v1beta/search`\n- Headers: `x-api-key`, `parallel-beta: search-extract-2025-10-10`\n- Returns: URLs, titles, snippets as citations\n\n**WebExtractTool** (`web_extract.py`):\n- POST to `https://api.parallel.ai/v1beta/extract`\n- Returns: LLM-ready markdown with `excerpts` (NOT full content to UI)\n- Extracts citations from excerpts\n\n**PythonSandboxTool** (`python_sandbox.py`):\n- E2B cloud sandbox (prod) or Docker (dev)\n- Timeout: 30s max, memory limit, network disabled\n- Returns: stdout, stderr, result\n\n---\n\n## API Design\n\n### New Routes: `orchestrator/routes/agent.py`\n\n| Endpoint | Method | Description |\n|----------|--------|-------------|\n| `/api/agent/conversations/{id}/runs` | POST | Create agent research run |\n| `/api/agent/runs/{id}/stream` | GET | SSE stream with agent events |\n| `/api/agent/runs/{id}/resume` | POST | Resume from checkpoint |\n| `/api/agent/runs/{id}/cancel` | POST | Cancel running agent |\n| `/api/agent/runs/{id}/citations` | GET | Get collected citations |\n\n### SSE Event Types\n\n| Event | Description |\n|-------|-------------|\n| `AGENT_STATE` | State transition (planning → tool_calling) |\n| `TOOL_CALL_START` | Tool call initiated with args |\n| `TOOL_CALL_RESULT` | Tool completed with summary (not full content) |\n| `CITATION` | New citation extracted |\n| `THINKING` | Model reasoning tokens |\n| `ANSWER` | Final answer tokens |\n| `COMPLETE` | Run finished |\n\n---\n\n## Frontend Architecture\n\n### New Components\n\n| Component | Purpose |\n|-----------|---------|\n| `AgentThinkingPanel.tsx` | Shows steps, tool calls, state indicator |\n| `ToolCallCard.tsx` | Individual tool call with status, summary |\n| `CitationInline.tsx` | Clickable `[1]` reference with tooltip preview |\n| `AnswerWithCitations.tsx` | Markdown renderer that links `[cite_N]` to citations |\n| `AgentRunMessage.tsx` | Complete agent run display |\n\n### Store Extensions (`useStore.ts`)\n\n```typescript\n// Add to store\nagentSteps: Record<string, AgentStep[]>;      // runId → steps\nagentCitations: Record<string, Citation[]>;   // runId → citations\ncurrentAgentState: Record<string, AgentState>; // runId → state\n```\n\n### New Hook: `useAgentSSE.ts`\n\nHandle agent-specific events:\n- `TOOL_CALL_START` → Add pending tool to current step\n- `TOOL_CALL_RESULT` → Update tool with summary + citations\n- `CITATION` → Append to citations list\n- `THINKING` → Stream to thinking panel\n- `ANSWER` → Stream to answer area\n\n---\n\n## Configuration Changes\n\n### `chat_config.yaml` additions\n\n```yaml\nagent:\n  max_steps: 10\n  step_timeout_ms: 60000\n  tools:\n    max_concurrent: 3\n    default_timeout_ms: 30000\n    max_retries: 2\n\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n  extract:\n    timeout_ms: 30000\n\nsandbox:\n  type: ${SANDBOX_TYPE:-e2b}\n  e2b:\n    api_key: ${E2B_API_KEY:-}\n    timeout_seconds: 30\n  docker:\n    image: \"python:3.11-slim\"\n    memory_limit: \"256m\"\n    network_disabled: true\n```\n\n---\n\n## Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add agent_checkpoints table, runs.mode column\n2. `orchestrator/schemas.py` - Add AgentState, Citation, ToolCall schemas\n3. `orchestrator/storage/repositories/agent_repo.py` - Checkpoint CRUD\n\n### Phase 2: Tool Layer\n4. `orchestrator/agent/tools/base.py` - BaseTool ABC, ToolResult\n5. `orchestrator/agent/tools/registry.py` - ToolRegistry\n6. `orchestrator/agent/tools/web_search.py` - Parallel Search integration\n7. `orchestrator/agent/tools/web_extract.py` - Parallel Extract integration\n8. `orchestrator/agent/tools/python_sandbox.py` - E2B/Docker sandbox\n\n### Phase 3: Agent Core\n9. `orchestrator/agent/state_machine.py` - AgentContext, AgentStateMachine\n10. `orchestrator/agent/checkpoint.py` - CheckpointManager\n11. `orchestrator/agent/agent_engine.py` - Main agent loop\n\n### Phase 4: API Layer\n12. `orchestrator/config.py` - Add AgentConfig, ParallelConfig, SandboxConfig\n13. `orchestrator/chat_config.yaml` - Add new config sections\n14. `orchestrator/routes/agent.py` - Agent API routes\n15. `orchestrator/app.py` - Register agent router\n\n### Phase 5: Frontend Types & API\n16. `ui/src/types/agent.ts` - TypeScript types\n17. `ui/src/api/client.ts` - Add agent API functions\n\n### Phase 6: Frontend State & Streaming\n18. `ui/src/hooks/useStore.ts` - Add agent state slices\n19. `ui/src/hooks/useAgentSSE.ts` - Agent SSE hook\n\n### Phase 7: Frontend Components\n20. `ui/src/components/ToolCallCard.tsx` - Tool call visualization\n21. `ui/src/components/AgentThinkingPanel.tsx` - Thinking panel\n22. `ui/src/components/CitationInline.tsx` - Inline citation\n23. `ui/src/components/AnswerWithCitations.tsx` - Answer renderer\n24. `ui/src/components/AgentRunMessage.tsx` - Complete run display\n25. `ui/src/components/ConversationView.tsx` - Integrate agent mode\n\n---\n\n## Critical Files Reference\n\n| File | Purpose |\n|------|---------|\n| `orchestrator/agent/agent_engine.py` | Core agent loop - most complex |\n| `orchestrator/routes/runs.py` | Reference for SSE pattern |\n| `orchestrator/providers/base.py` | LLMProvider protocol (already has tools support) |\n| `orchestrator/engine/chat_engine.py` | Reference for trace recording |\n| `ui/src/hooks/useSSE.ts` | Reference for frontend SSE |\n\n---\n\n## UI Behavior Notes\n\n1. **Thinking Panel shows**:\n   - Model decisions (reasoning tokens)\n   - Tool calls with status (pending/running/success/error)\n   - Tool result **summaries** and cited snippets only\n\n2. **Answer Panel shows**:\n   - Markdown formatted response\n   - Inline citations as `[1]`, `[2]` etc.\n   - Hover/click reveals snippet + source URL\n\n3. **Full extracted content** stays backend-only (never sent to UI unless explicitly expanded)\n\n---\n\n## Production Checklist\n\n- [ ] E2B API key in environment\n- [ ] Parallel.ai API key in environment\n- [ ] Rate limiting on agent endpoints\n- [ ] Circuit breaker for external APIs\n- [ ] Checkpoint cleanup job (delete old checkpoints)\n- [ ] Metrics/alerts for tool failures\n- [ ] Redis pub/sub for multi-instance (when scaling)\n"}
```
---
## USER (2026-01-04T08:05:05.629Z)


---
## USER (2026-01-04T08:05:05.635Z)

[Request interrupted by user for tool use]
---
## USER (2026-01-04T08:09:39.332Z)

<ide_selection>The user selected the lines 1 to 293 from /Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md:
# Web Research Agent Implementation Plan

## Overview

Build a production-grade web research agent on top of the existing Reasoner repo with:
- **Tools**: Parallel.ai (search/extract) + Python sandbox
- **Model**: gpt-oss-120b via OpenAI-compatible API
- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)
- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers

---

## Architecture Decisions (Production-Grade)

| Concern | Decision | Rationale |
|---------|----------|-----------|
| **Python Sandbox** | E2B (cloud) with Docker fallback | E2B is managed, secure, scales. Docker for local dev. |
| **Durability** | SQLite checkpoints (existing infra) | Matches current stack. Can evolve to Temporal later. |
| **Concurrency** | Parallel runs supported | Better UX, production expectation |
| **Multi-instance** | Redis pub/sub for SSE (optional) | Current in-memory queue works for single instance |

---

## Data Model Changes

### New Table: `agent_checkpoints`

```sql
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL,           -- planning | tool_calling | synthesizing | complete | error | cancelled
    step_number INTEGER NOT NULL,
    messages_json TEXT NOT NULL,
    tool_calls_pending_json TEXT,
    tool_results_json TEXT,
    citations_json TEXT,
    last_tool_call_id TEXT,
    error_count INTEGER DEFAULT 0,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
```

### Extended `runs` Table

Add column: `mode TEXT` with values `chat` | `agent`

### Citation Schema (Pydantic)

```python
class Citation(BaseModel):
    id: str                # cite_1, cite_2, ...
    source_url: str
    title: str
    snippet: str           # Relevant extracted text (NOT full page)
    extracted_at: str
    tool_call_id: str
```

---

## Backend Architecture

### New Directory: `orchestrator/agent/`

```
orchestrator/agent/
├── __init__.py
├── agent_engine.py       # Main agent loop with checkpoint/resume
├── state_machine.py      # AgentState enum, transitions, AgentContext
├── checkpoint.py         # CheckpointManager for save/restore
└── tools/
    ├── __init__.py
    ├── base.py           # BaseTool ABC, ToolResult dataclass
    ├── registry.py       # ToolRegistry with OpenAI format conversion
    ├── web_search.py     # Parallel.ai Search API integration
    ├── web_extract.py    # Parallel.ai Extract API integration
    └── python_sandbox.py # E2B/Docker sandbox execution
```

### Agent State Machine

```
START → PLANNING ←→ TOOL_CALLING → SYNTHESIZING → COMPLETE
            ↓            ↓              ↓
         ERROR ←←←←←←←←←←←←←←←←←←←←←←←←←
            ↑
       CANCELLED (from any non-terminal state)
```

### Agent Loop (agent_engine.py)

1. Initialize or restore context from checkpoint
2. **PLANNING**: Call model with tool definitions, get tool_calls or direct answer
3. **TOOL_CALLING**: Execute tools in parallel (max 3 concurrent), collect citations
4. Loop back to PLANNING with tool results until model synthesizes
5. **SYNTHESIZING**: Generate final answer with citation references
6. Checkpoint before each step for crash recovery

### Tool Implementations

**WebSearchTool** (`web_search.py`):
- POST to `https://api.parallel.ai/v1beta/search`
- Headers: `x-api-key`, `parallel-beta: search-extract-2025-10-10`
- Returns: URLs, titles, snippets as citations

**WebExtractTool** (`web_extract.py`):
- POST to `https://api.parallel.ai/v1beta/extract`
- Returns: LLM-ready markdown with `excerpts` (NOT full content to UI)
- Extracts citations from excerpts

**PythonSandboxTool** (`python_sandbox.py`):
- E2B cloud sandbox (prod) or Docker (dev)
- Timeout: 30s max, memory limit, network disabled
- Returns: stdout, stderr, result

---

## API Design

### New Routes: `orchestrator/routes/agent.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/conversations/{id}/runs` | POST | Create agent research run |
| `/api/agent/runs/{id}/stream` | GET | SSE stream with agent events |
| `/api/agent/runs/{id}/resume` | POST | Resume from checkpoint |
| `/api/agent/runs/{id}/cancel` | POST | Cancel running agent |
| `/api/agent/runs/{id}/citations` | GET | Get collected citations |

### SSE Event Types

| Event | Description |
|-------|-------------|
| `AGENT_STATE` | State transition (planning → tool_calling) |
| `TOOL_CALL_START` | Tool call initiated with args |
| `TOOL_CALL_RESULT` | Tool completed with summary (not full content) |
| `CITATION` | New citation extracted |
| `THINKING` | Model reasoning tokens |
| `ANSWER` | Final answer tokens |
| `COMPLETE` | Run finished |

---

## Frontend Architecture

### New Components

| Component | Purpose |
|-----------|---------|
| `AgentThinkingPanel.tsx` | Shows steps, tool calls, state indicator |
| `ToolCallCard.tsx` | Individual tool call with status, summary |
| `CitationInline.tsx` | Clickable `[1]` reference with tooltip preview |
| `AnswerWithCitations.tsx` | Markdown renderer that links `[cite_N]` to citations |
| `AgentRunMessage.tsx` | Complete agent run display |

### Store Extensions (`useStore.ts`)

```typescript
// Add to store
agentSteps: Record<string, AgentStep[]>;      // runId → steps
agentCitations: Record<string, Citation[]>;   // runId → citations
currentAgentState: Record<string, AgentState>; // runId → state
```

### New Hook: `useAgentSSE.ts`

Handle agent-specific events:
- `TOOL_CALL_START` → Add pending tool to current step
- `TOOL_CALL_RESULT` → Update tool with summary + citations
- `CITATION` → Append to citations list
- `THINKING` → Stream to thinking panel
- `ANSWER` → Stream to answer area

---

## Configuration Changes

### `chat_config.yaml` additions

```yaml
agent:
  max_steps: 10
  step_timeout_ms: 60000
  tools:
    max_concurrent: 3
    default_timeout_ms: 30000
    max_retries: 2

parallel:
  base_url: "https://api.parallel.ai/v1beta"
  api_key: ${PARALLEL_API_KEY}
  search:
    max_results: 10
    timeout_ms: 15000
  extract:
    timeout_ms: 30000

sandbox:
  type: ${SANDBOX_TYPE:-e2b}
  e2b:
    api_key: ${E2B_API_KEY:-}
    timeout_seconds: 30
  docker:
    image: "python:3.11-slim"
    memory_limit: "256m"
    network_disabled: true
```

---

## Implementation Order

### Phase 1: Data Layer
1. `orchestrator/storage/schema.sql` - Add agent_checkpoints table, runs.mode column
2. `orchestrator/schemas.py` - Add AgentState, Citation, ToolCall schemas
3. `orchestrator/storage/repositories/agent_repo.py` - Checkpoint CRUD

### Phase 2: Tool Layer
4. `orchestrator/agent/tools/base.py` - BaseTool ABC, ToolResult
5. `orchestrator/agent/tools/registry.py` - ToolRegistry
6. `orchestrator/agent/tools/web_search.py` - Parallel Search integration
7. `orchestrator/agent/tools/web_extract.py` - Parallel Extract integration
8. `orchestrator/agent/tools/python_sandbox.py` - E2B/Docker sandbox

### Phase 3: Agent Core
9. `orchestrator/agent/state_machine.py` - AgentContext, AgentStateMachine
10. `orchestrator/agent/checkpoint.py` - CheckpointManager
11. `orchestrator/agent/agent_engine.py` - Main agent loop

### Phase 4: API Layer
12. `orchestrator/config.py` - Add AgentConfig, ParallelConfig, SandboxConfig
13. `orchestrator/chat_config.yaml` - Add new config sections
14. `orchestrator/routes/agent.py` - Agent API routes
15. `orchestrator/app.py` - Register agent router

### Phase 5: Frontend Types & API
16. `ui/src/types/agent.ts` - TypeScript types
17. `ui/src/api/client.ts` - Add agent API functions

### Phase 6: Frontend State & Streaming
18. `ui/src/hooks/useStore.ts` - Add agent state slices
19. `ui/src/hooks/useAgentSSE.ts` - Agent SSE hook

### Phase 7: Frontend Components
20. `ui/src/components/ToolCallCard.tsx` - Tool call visualization
21. `ui/src/components/AgentThinkingPanel.tsx` - Thinking panel
22. `ui/src/components/CitationInline.tsx` - Inline citation
23. `ui/src/components/AnswerWithCitations.tsx` - Answer renderer
24. `ui/src/components/AgentRunMessage.tsx` - Complete run display
25. `ui/src/components/ConversationView.tsx` - Integrate agent mode

---

## Critical Files Reference

| File | Purpose |
|------|---------|
| `orchestrator/agent/agent_engine.py` | Core agent loop - most complex |
| `orchestrator/routes/runs.py` | Reference for SSE pattern |
| `orchestrator/providers/base.py` | LLMProvider protocol (already has tools support) |
| `orchestrator/engine/chat_engine.py` | Reference for trace recording |
| `ui/src/hooks/useSSE.ts` | Reference for frontend SSE |

---

## UI Behavior Notes

1. **Thinking Panel shows**:
   - Model decisions (reasoning tokens)
   - Tool calls with status (pending/running/success/error)
   - Tool result **summaries** and cited snippets only

2. **Answer Panel shows**:
   - Markdown formatted response
   - Inline citations as `[1]`, `[2]` etc.
   - Hover/click reveals snippet + source URL

3. **Full extracted content** stays backend-only (never sent to UI unless explicitly expanded)

---

## Production Checklist

- [ ] E2B API key in environment
- [ ] Parallel.ai API key in environment
- [ ] Rate limiting on agent endpoints
- [ ] Circuit breaker for external APIs
- [ ] Checkpoint cleanup job (delete old checkpoints)
- [ ] Metrics/alerts for tool failures
- [ ] Redis pub/sub for multi-instance (when scaling)


This may or may not be related to the current task.</ide_selection>

1. Parallel tool concurrency is nice UX, but it creates: ordering ambiguity, step attribution complexity, more retry edge cases
2. Their checkpoint schema is too “big JSON blob” and will hurt debugging
3. SSE Redis pub/sub is totally out of scope for now 
4. E2B is not currently what im looking for i dont want extra overhead for v1
---
## ASSISTANT (2026-01-04T08:09:48.150Z)

<details><summary>Thinking...</summary>

The user is giving feedback on the plan. Let me address each point:

1. **Parallel tool concurrency** - They want simpler sequential tool execution to avoid ordering/attribution complexity
2. **Checkpoint schema** - Too much JSON blob, need more granular columns for debugging
3. **Redis pub/sub** - Out of scope for v1
4. **E2B** - Too much overhead for v1, they want simpler approach

I should update the plan to:
1. Make tool execution sequential (one at a time)
2. Normalize the checkpoint schema - break out JSON blobs into proper columns/tables
3. Remove Redis pub/sub mention entirely
4. Use local Docker sandbox or simple subprocess for Python execution instead of E2B

Let me revise the plan with these changes.

</details>
---
## ASSISTANT (2026-01-04T08:09:49.428Z)

Good feedback. Let me revise the plan to address these concerns:

1. **Sequential tool execution** - Simpler, deterministic ordering
2. **Normalized checkpoint schema** - Separate tables, not JSON blobs
3. **Remove Redis** - Single instance only for v1
4. **Local Docker/subprocess for Python** - No E2B overhead
---
## ASSISTANT (2026-01-04T08:09:53.813Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Architecture Decisions (Production-Grade)\n\n| Concern | Decision | Rationale |\n|---------|----------|-----------|\n| **Python Sandbox** | E2B (cloud) with Docker fallback | E2B is managed, secure, scales. Docker for local dev. |\n| **Durability** | SQLite checkpoints (existing infra) | Matches current stack. Can evolve to Temporal later. |\n| **Concurrency** | Parallel runs supported | Better UX, production expectation |\n| **Multi-instance** | Redis pub/sub for SSE (optional) | Current in-memory queue works for single instance |","new_string":"## Architecture Decisions (V1)\n\n| Concern | Decision | Rationale |\n|---------|----------|-----------|\n| **Python Sandbox** | Local Docker container | Simple, no external deps. Secure with `--network=none`. |\n| **Durability** | SQLite checkpoints (normalized) | Matches current stack. Granular columns for debugging. |\n| **Tool Execution** | Sequential (one at a time) | Deterministic ordering, simpler step attribution, fewer edge cases |\n| **Multi-instance** | Single instance only | In-memory queue is fine. Scale later if needed. |"}
```
---
## USER (2026-01-04T08:09:53.829Z)


---
## ASSISTANT (2026-01-04T08:10:01.316Z)

<details><summary>Thinking...</summary>

Now I need to update the data model section to normalize the checkpoint schema - break out the JSON blobs into proper columns and possibly separate tables for better debugging.

</details>
---
## ASSISTANT (2026-01-04T08:10:22.056Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Data Model Changes\n\n### New Table: `agent_checkpoints`\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_checkpoints (\n    checkpoint_id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n    state TEXT NOT NULL,           -- planning | tool_calling | synthesizing | complete | error | cancelled\n    step_number INTEGER NOT NULL,\n    messages_json TEXT NOT NULL,\n    tool_calls_pending_json TEXT,\n    tool_results_json TEXT,\n    citations_json TEXT,\n    last_tool_call_id TEXT,\n    error_count INTEGER DEFAULT 0,\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### Extended `runs` Table\n\nAdd column: `mode TEXT` with values `chat` | `agent`\n\n### Citation Schema (Pydantic)\n\n```python\nclass Citation(BaseModel):\n    id: str                # cite_1, cite_2, ...\n    source_url: str\n    title: str\n    snippet: str           # Relevant extracted text (NOT full page)\n    extracted_at: str\n    tool_call_id: str\n```","new_string":"## Data Model Changes\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';  -- 'chat' | 'agent'\nALTER TABLE runs ADD COLUMN agent_state TEXT;          -- planning | tool_calling | synthesizing | complete | error | cancelled\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\n```\n\n### New Table: `agent_steps` (normalized, one row per step)\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Step state\n    state TEXT NOT NULL,           -- planning | tool_calling | synthesizing\n\n    -- Model interaction (when state=planning)\n    model_request_event_id TEXT,   -- FK to trace_events for the LLM call\n    model_response_event_id TEXT,\n    thinking_text TEXT,            -- Model's reasoning for this step\n\n    -- What the model decided\n    decision TEXT NOT NULL,        -- 'call_tool' | 'synthesize' | 'error'\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### New Table: `agent_tool_calls` (one row per tool call)\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,       -- web_search | web_extract | python_execute\n    arguments TEXT NOT NULL,       -- JSON of tool arguments\n\n    -- Execution\n    status TEXT NOT NULL,          -- pending | running | success | error | timeout\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Result (not JSON blob - key fields extracted)\n    result_summary TEXT,           -- Brief summary for UI\n    result_raw TEXT,               -- Full result (backend only)\n    error_message TEXT,\n    retry_count INTEGER DEFAULT 0,\n\n    -- Trace linkage\n    trace_event_id TEXT,           -- FK to trace_events\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n```\n\n### New Table: `agent_citations` (one row per citation)\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,           -- cite_1, cite_2, ...\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Citation data (all indexed, queryable)\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,         -- The relevant extracted text\n\n    -- Usage tracking\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\nCREATE INDEX idx_citations_tool_call ON agent_citations(tool_call_id);\n```\n\n### Checkpoint Recovery\n\nInstead of a separate checkpoint table, recovery uses:\n- `runs.agent_state` + `runs.current_step` for high-level state\n- `agent_steps` to find last completed step\n- `agent_tool_calls` to check for incomplete tool calls\n- Resume = find last successful step, replay from there\n\n### Pydantic Schemas\n\n```python\nclass AgentState(str, Enum):\n    PLANNING = \"planning\"\n    TOOL_CALLING = \"tool_calling\"\n    SYNTHESIZING = \"synthesizing\"\n    COMPLETE = \"complete\"\n    ERROR = \"error\"\n    CANCELLED = \"cancelled\"\n\nclass Citation(BaseModel):\n    id: str\n    source_url: str\n    title: Optional[str]\n    snippet: str\n    tool_call_id: str\n    used_in_answer: bool = False\n\nclass ToolCallStatus(str, Enum):\n    PENDING = \"pending\"\n    RUNNING = \"running\"\n    SUCCESS = \"success\"\n    ERROR = \"error\"\n    TIMEOUT = \"timeout\"\n\nclass ToolCallRecord(BaseModel):\n    id: str\n    tool_name: str\n    arguments: dict\n    status: ToolCallStatus\n    result_summary: Optional[str]\n    error_message: Optional[str]\n    duration_ms: Optional[int]\n    citations: list[Citation] = []\n```"}
```
---
## USER (2026-01-04T08:10:22.074Z)


---
## ASSISTANT (2026-01-04T08:10:31.469Z)

<details><summary>Thinking...</summary>

The user wants it production-grade but without the extra complexity of E2B, Redis, parallel tool execution. Let me update the tool implementation section to reflect:
1. Sequential tool execution (simpler but still robust)
2. Docker sandbox that's properly secured for production
3. Remove E2B references

Let me also update the agent loop section and the config section.

</details>
---
## ASSISTANT (2026-01-04T08:10:32.021Z)

Now let me update the tool and agent loop sections to reflect sequential execution with production-grade Docker sandbox:
---
## ASSISTANT (2026-01-04T08:10:51.107Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Agent Loop (agent_engine.py)\n\n1. Initialize or restore context from checkpoint\n2. **PLANNING**: Call model with tool definitions, get tool_calls or direct answer\n3. **TOOL_CALLING**: Execute tools in parallel (max 3 concurrent), collect citations\n4. Loop back to PLANNING with tool results until model synthesizes\n5. **SYNTHESIZING**: Generate final answer with citation references\n6. Checkpoint before each step for crash recovery\n\n### Tool Implementations\n\n**WebSearchTool** (`web_search.py`):\n- POST to `https://api.parallel.ai/v1beta/search`\n- Headers: `x-api-key`, `parallel-beta: search-extract-2025-10-10`\n- Returns: URLs, titles, snippets as citations\n\n**WebExtractTool** (`web_extract.py`):\n- POST to `https://api.parallel.ai/v1beta/extract`\n- Returns: LLM-ready markdown with `excerpts` (NOT full content to UI)\n- Extracts citations from excerpts\n\n**PythonSandboxTool** (`python_sandbox.py`):\n- E2B cloud sandbox (prod) or Docker (dev)\n- Timeout: 30s max, memory limit, network disabled\n- Returns: stdout, stderr, result","new_string":"### Agent Loop (agent_engine.py)\n\n```\n1. INIT: Load or create run, restore from last step if resuming\n2. LOOP (while step < max_steps):\n   a. Create agent_step record (state=planning)\n   b. PLANNING: Call model with tools + accumulated context\n   c. Record model response in agent_step\n   d. If model returns tool_call:\n      - Create agent_tool_calls record (status=pending)\n      - TOOL_CALLING: Execute tool sequentially\n      - Update agent_tool_calls with result\n      - Extract citations → agent_citations\n      - Loop back to (a) with tool result in context\n   e. If model returns text (no tool_call):\n      - SYNTHESIZING: Model has final answer\n      - Update run with final_answer\n      - Mark used citations\n      - Break loop\n3. COMPLETE: Update run.status, run.agent_state\n```\n\n**Key: Sequential execution** - One tool at a time, deterministic ordering, clear step attribution.\n\n### Tool Implementations\n\n**WebSearchTool** (`web_search.py`):\n- POST to `https://api.parallel.ai/v1beta/search`\n- Headers: `x-api-key`, `parallel-beta: search-extract-2025-10-10`\n- Retry: 3 attempts with exponential backoff (1s, 2s, 4s)\n- Circuit breaker: 5 failures in 60s → open for 30s\n- Returns: URLs, titles, snippets → stored as citations\n\n**WebExtractTool** (`web_extract.py`):\n- POST to `https://api.parallel.ai/v1beta/extract`\n- Request: `{urls: [...], objective: \"...\", excerpts: true, full_content: false}`\n- Returns: `excerpts` array (NOT full page content)\n- Each excerpt becomes a citation with snippet\n\n**PythonSandboxTool** (`python_sandbox.py`):\n- Docker container with production hardening:\n  ```\n  --network=none          # No network access\n  --memory=256m           # Memory limit\n  --cpus=0.5              # CPU limit\n  --read-only             # Read-only filesystem\n  --tmpfs /tmp:size=64m   # Writable temp only\n  --pids-limit=50         # Process limit\n  --security-opt=no-new-privileges\n  ```\n- Timeout: 30s hard limit via `docker stop`\n- Pre-built image with numpy, pandas, sympy, scipy (no pip install)\n- Returns: stdout, stderr, exit_code"}
```
---
## USER (2026-01-04T08:10:51.118Z)


---
## ASSISTANT (2026-01-04T08:10:57.277Z)

<details><summary>Thinking...</summary>

Now I need to update the configuration section to remove E2B and simplify:

</details>
---
## ASSISTANT (2026-01-04T08:11:08.392Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Configuration Changes\n\n### `chat_config.yaml` additions\n\n```yaml\nagent:\n  max_steps: 10\n  step_timeout_ms: 60000\n  tools:\n    max_concurrent: 3\n    default_timeout_ms: 30000\n    max_retries: 2\n\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n  extract:\n    timeout_ms: 30000\n\nsandbox:\n  type: ${SANDBOX_TYPE:-e2b}\n  e2b:\n    api_key: ${E2B_API_KEY:-}\n    timeout_seconds: 30\n  docker:\n    image: \"python:3.11-slim\"\n    memory_limit: \"256m\"\n    network_disabled: true\n```","new_string":"## Configuration Changes\n\n### `chat_config.yaml` additions\n\n```yaml\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 60000\n\n  # Retry/circuit breaker settings\n  retry:\n    max_attempts: 3\n    base_delay_ms: 1000\n    max_delay_ms: 8000\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_ms: 30000\n\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n\nsandbox:\n  docker:\n    image: \"reasoner-sandbox:latest\"  # Pre-built with scipy, numpy, pandas, sympy\n    memory_limit: \"256m\"\n    cpu_limit: \"0.5\"\n    timeout_seconds: 30\n    network_disabled: true\n```\n\n### Environment Variables Required\n\n```bash\nPARALLEL_API_KEY=xxx  # Required for web search/extract\n```"}
```
---
## USER (2026-01-04T08:11:08.402Z)


---
## ASSISTANT (2026-01-04T08:11:13.413Z)

<details><summary>Thinking...</summary>

Now I need to update the implementation order and production checklist to remove E2B/Redis references.

</details>
---
## ASSISTANT (2026-01-04T08:11:36.413Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add agent_checkpoints table, runs.mode column\n2. `orchestrator/schemas.py` - Add AgentState, Citation, ToolCall schemas\n3. `orchestrator/storage/repositories/agent_repo.py` - Checkpoint CRUD\n\n### Phase 2: Tool Layer\n4. `orchestrator/agent/tools/base.py` - BaseTool ABC, ToolResult\n5. `orchestrator/agent/tools/registry.py` - ToolRegistry\n6. `orchestrator/agent/tools/web_search.py` - Parallel Search integration\n7. `orchestrator/agent/tools/web_extract.py` - Parallel Extract integration\n8. `orchestrator/agent/tools/python_sandbox.py` - E2B/Docker sandbox\n\n### Phase 3: Agent Core\n9. `orchestrator/agent/state_machine.py` - AgentContext, AgentStateMachine\n10. `orchestrator/agent/checkpoint.py` - CheckpointManager\n11. `orchestrator/agent/agent_engine.py` - Main agent loop\n\n### Phase 4: API Layer\n12. `orchestrator/config.py` - Add AgentConfig, ParallelConfig, SandboxConfig\n13. `orchestrator/chat_config.yaml` - Add new config sections\n14. `orchestrator/routes/agent.py` - Agent API routes\n15. `orchestrator/app.py` - Register agent router\n\n### Phase 5: Frontend Types & API\n16. `ui/src/types/agent.ts` - TypeScript types\n17. `ui/src/api/client.ts` - Add agent API functions\n\n### Phase 6: Frontend State & Streaming\n18. `ui/src/hooks/useStore.ts` - Add agent state slices\n19. `ui/src/hooks/useAgentSSE.ts` - Agent SSE hook\n\n### Phase 7: Frontend Components\n20. `ui/src/components/ToolCallCard.tsx` - Tool call visualization\n21. `ui/src/components/AgentThinkingPanel.tsx` - Thinking panel\n22. `ui/src/components/CitationInline.tsx` - Inline citation\n23. `ui/src/components/AnswerWithCitations.tsx` - Answer renderer\n24. `ui/src/components/AgentRunMessage.tsx` - Complete run display\n25. `ui/src/components/ConversationView.tsx` - Integrate agent mode","new_string":"## Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add agent tables (agent_steps, agent_tool_calls, agent_citations), extend runs\n2. `orchestrator/schemas.py` - Add AgentState, Citation, ToolCallRecord, ToolCallStatus enums/models\n3. `orchestrator/storage/repositories/agent_repo.py` - AgentRepo with step/tool_call/citation CRUD\n\n### Phase 2: Tool Layer\n4. `orchestrator/agent/tools/base.py` - BaseTool ABC, ToolResult dataclass\n5. `orchestrator/agent/tools/registry.py` - ToolRegistry with OpenAI format\n6. `orchestrator/agent/tools/web_search.py` - Parallel Search with retry/circuit breaker\n7. `orchestrator/agent/tools/web_extract.py` - Parallel Extract with citation extraction\n8. `orchestrator/agent/tools/python_sandbox.py` - Docker sandbox execution\n9. `docker/sandbox/Dockerfile` - Pre-built Python sandbox image\n\n### Phase 3: Agent Core\n10. `orchestrator/agent/state_machine.py` - AgentStateMachine with transitions\n11. `orchestrator/agent/agent_engine.py` - Main sequential agent loop with recovery\n\n### Phase 4: API Layer\n12. `orchestrator/config.py` - Add AgentConfig, ParallelConfig, SandboxConfig\n13. `orchestrator/chat_config.yaml` - Add agent/parallel/sandbox sections\n14. `orchestrator/routes/agent.py` - Agent API routes with SSE\n15. `orchestrator/app.py` - Register agent router\n\n### Phase 5: Frontend Types & API\n16. `ui/src/types/agent.ts` - TypeScript types matching backend\n17. `ui/src/api/client.ts` - Add agent API functions\n\n### Phase 6: Frontend State & Streaming\n18. `ui/src/hooks/useStore.ts` - Add agent state slices\n19. `ui/src/hooks/useAgentSSE.ts` - Agent SSE event handler\n\n### Phase 7: Frontend Components\n20. `ui/src/components/ToolCallCard.tsx` - Tool call with status indicator\n21. `ui/src/components/AgentThinkingPanel.tsx` - Steps + tool calls timeline\n22. `ui/src/components/CitationInline.tsx` - Clickable [1] with tooltip\n23. `ui/src/components/AnswerWithCitations.tsx` - Markdown + citation links\n24. `ui/src/components/AgentRunMessage.tsx` - Full agent run display\n25. `ui/src/components/ConversationView.tsx` - Integrate agent mode toggle"}
```
---
## USER (2026-01-04T08:11:36.425Z)


---
## ASSISTANT (2026-01-04T08:11:41.165Z)

<details><summary>Thinking...</summary>

Now I need to update the production checklist to remove E2B and Redis references:

</details>
---
## ASSISTANT (2026-01-04T08:11:49.041Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Production Checklist\n\n- [ ] E2B API key in environment\n- [ ] Parallel.ai API key in environment\n- [ ] Rate limiting on agent endpoints\n- [ ] Circuit breaker for external APIs\n- [ ] Checkpoint cleanup job (delete old checkpoints)\n- [ ] Metrics/alerts for tool failures\n- [ ] Redis pub/sub for multi-instance (when scaling)","new_string":"## Production Checklist\n\n- [ ] Parallel.ai API key in environment (`PARALLEL_API_KEY`)\n- [ ] Docker sandbox image built and tested (`docker build -t reasoner-sandbox docker/sandbox/`)\n- [ ] Rate limiting on agent endpoints (use existing middleware pattern)\n- [ ] Circuit breaker for Parallel.ai APIs (5 failures → 30s cooldown)\n- [ ] Stale run cleanup job (mark runs stuck >1hr as failed)\n- [ ] Metrics/alerts: tool failure rate, step latency, timeout rate\n- [ ] Log structured events for all tool calls (integrate with existing JSON logging)\n- [ ] Test recovery: kill mid-run, verify resume works"}
```
---
## USER (2026-01-04T08:11:49.050Z)


---
## ASSISTANT (2026-01-04T08:11:55.551Z)

<details><summary>Thinking...</summary>

The plan is now updated with the user's feedback:
1. Sequential tool execution (not parallel)
2. Normalized checkpoint schema with separate tables (agent_steps, agent_tool_calls, agent_citations)
3. Removed Redis pub/sub
4. Docker sandbox only (no E2B)

The plan is now production-grade but simpler. Let me ask if there are any remaining questions or if they're ready to proceed.

</details>
---
## ASSISTANT (2026-01-04T08:12:00.585Z)

I've updated the plan with your feedback:

**Changes made:**
1. **Sequential tool execution** - One tool at a time, deterministic ordering, clear step attribution
2. **Normalized schema** - Separate tables (`agent_steps`, `agent_tool_calls`, `agent_citations`) instead of JSON blobs - each field queryable for debugging
3. **Removed Redis** - Single instance only for v1
4. **Docker sandbox only** - Production-hardened with `--network=none`, memory limits, read-only fs, no E2B dependency

The design is still production-grade with:
- Retry + circuit breaker for Parallel.ai APIs
- Full trace linkage (every tool call → trace_events)
- Crash recovery via normalized tables (not checkpoints)
- Structured logging integration
---
## ASSISTANT (2026-01-04T08:12:03.056Z)

**Tool Use:** AskUserQuestion
```json
{"questions":[{"question":"Any other concerns with the updated plan before we proceed to implementation?","header":"Ready?","options":[{"label":"Looks good, proceed","description":"Start implementation with Phase 1 (Data Layer)"},{"label":"More changes needed","description":"I have additional feedback on the plan"}],"multiSelect":false}]}
```
---
## USER (2026-01-04T08:17:58.813Z)


---
## ASSISTANT (2026-01-04T08:18:04.491Z)

<details><summary>Thinking...</summary>

The user has more changes. I should wait for them to specify what additional changes they need.

</details>
---
## ASSISTANT (2026-01-04T08:18:04.751Z)

What changes would you like me to make to the plan?
---
## USER (2026-01-04T08:18:33.020Z)

<ide_opened_file>The user opened the file /Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md in the IDE. This may or may not be related to the current task.</ide_opened_file>

how does the check pointing work if you've removed
---
## ASSISTANT (2026-01-04T08:18:39.139Z)

<details><summary>Thinking...</summary>

The user is asking about checkpointing - I removed the separate `agent_checkpoints` table and said recovery uses the normalized tables instead. Let me explain how that works more clearly and see if they want me to add a dedicated checkpoint mechanism back.

</details>
---
## ASSISTANT (2026-01-04T08:18:47.189Z)

Good catch. The current plan uses the normalized tables (`agent_steps`, `agent_tool_calls`) as implicit checkpoints rather than explicit snapshots. Here's how it works:

**Current approach (implicit checkpointing):**
```
Recovery = query agent_steps for last step + query agent_tool_calls for incomplete tools
Resume = replay from last successful step
```

**The problem:** If the process crashes mid-step (e.g., after model call but before DB write), we lose that work because there's no atomic checkpoint.

**Two options:**

1. **Keep implicit (current plan)** - Simpler, but:
   - Might redo a model call if crash happens after response but before save
   - Tool calls are idempotent (search/extract), so re-running is safe
   - Python execution is NOT idempotent - could be an issue

2. **Add explicit checkpoints back** - More durable:
   ```sql
   CREATE TABLE agent_checkpoints (
       id TEXT PRIMARY KEY,
       run_id TEXT NOT NULL,
       step_number INTEGER NOT NULL,
       checkpoint_type TEXT NOT NULL,  -- 'pre_model' | 'post_model' | 'pre_tool' | 'post_tool'
       context_snapshot TEXT NOT NULL, -- Messages + tool results so far
       created_at TEXT NOT NULL
   );
   ```
   - Checkpoint before each risky operation
   - Resume = load latest checkpoint, continue from there

Which approach do you prefer for v1?
---
## USER (2026-01-04T08:20:16.577Z)

what happens when i fails
---
## ASSISTANT (2026-01-04T08:20:26.252Z)

<details><summary>Thinking...</summary>

The user is asking about failure scenarios with the implicit checkpointing approach. They want to understand what happens when something fails - whether we lose work, how we recover, etc.

Let me think through the failure scenarios:

1. **Crash after model call, before saving step** - We lose the model response, have to redo the call
2. **Crash during tool execution** - Tool call record exists with status="running", need to handle
3. **Crash after tool result, before saving** - Lose the tool result, have to re-execute
4. **Tool fails (API error, timeout)** - Need retry logic, eventually mark as error

The current implicit approach has gaps. For production-grade durability, we probably need explicit checkpoints at critical points. Let me update the plan with proper failure handling.

</details>
---
## ASSISTANT (2026-01-04T08:20:32.680Z)

Good question. Let me trace through failure scenarios with the current implicit approach:

**Failure scenarios:**

| Crash Point | What's Lost | Recovery Behavior |
|-------------|-------------|-------------------|
| After model call, before step saved | Model response | Re-call model ($$, latency) |
| After step saved, before tool_call record | Nothing | Resume sees step, no pending tool → re-plan |
| During tool execution | Tool result | tool_call.status = "running" → stuck state |
| After tool result, before citations saved | Citations | Re-extract from result_raw (if saved) |

**The "running" stuck state is the real problem.** If process crashes while `status = "running"`, on resume we don't know if:
- Tool never started (safe to retry)
- Tool completed but we crashed before updating (might double-execute)

**For Python execution, this is dangerous** - could run side-effectful code twice.

Let me add explicit checkpointing to handle this properly:
---
## ASSISTANT (2026-01-04T08:20:48.697Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Checkpoint Recovery\n\nInstead of a separate checkpoint table, recovery uses:\n- `runs.agent_state` + `runs.current_step` for high-level state\n- `agent_steps` to find last completed step\n- `agent_tool_calls` to check for incomplete tool calls\n- Resume = find last successful step, replay from there","new_string":"### Checkpoint & Recovery Strategy\n\n**Problem:** Crash during tool execution leaves `status = \"running\"` - we don't know if tool completed or not.\n\n**Solution:** Write-ahead logging pattern with idempotency keys.\n\n```sql\n-- Add to agent_tool_calls\nALTER TABLE agent_tool_calls ADD COLUMN idempotency_key TEXT;  -- UUID generated before execution\nALTER TABLE agent_tool_calls ADD COLUMN execution_attempt INTEGER DEFAULT 1;\n```\n\n**Recovery logic:**\n\n```python\nasync def recover_run(run_id: str) -> RecoveryAction:\n    \"\"\"Determine how to resume a crashed run.\"\"\"\n    run = await get_run(run_id)\n\n    if run.status == \"succeeded\":\n        return RecoveryAction.ALREADY_COMPLETE\n\n    # Find incomplete tool calls\n    stuck_tools = await get_tool_calls(run_id, status=\"running\")\n\n    if stuck_tools:\n        tool = stuck_tools[0]  # Sequential, so max 1\n\n        if tool.tool_name == \"python_execute\":\n            # Python is NOT idempotent - mark as failed, let model decide\n            await update_tool_call(tool.id, status=\"error\",\n                error_message=\"Crashed during execution - cannot safely retry\")\n            return RecoveryAction.CONTINUE_FROM_STEP\n\n        elif tool.tool_name in (\"web_search\", \"web_extract\"):\n            # These ARE idempotent - safe to retry\n            await update_tool_call(tool.id,\n                status=\"pending\",\n                execution_attempt=tool.execution_attempt + 1)\n            return RecoveryAction.RETRY_TOOL\n\n    # No stuck tools - find last complete step and continue\n    last_step = await get_last_complete_step(run_id)\n    return RecoveryAction.CONTINUE_FROM_STEP\n```\n\n**Failure handling by tool type:**\n\n| Tool | Idempotent? | On Crash Recovery |\n|------|-------------|-------------------|\n| `web_search` | Yes | Retry with same query |\n| `web_extract` | Yes | Retry with same URL |\n| `python_execute` | **No** | Mark as error, continue to next step |\n\n**Key invariant:** We always know the state because:\n1. Step record created BEFORE model call\n2. Tool call record created BEFORE execution\n3. Status updated to \"success\"/\"error\" AFTER completion\n4. If status = \"running\" on startup → crashed mid-execution"}
```
---
## USER (2026-01-04T08:20:48.708Z)


---
## ASSISTANT (2026-01-04T08:20:56.999Z)

<details><summary>Thinking...</summary>

I've added proper failure handling. The key insight is:
- Web tools are idempotent → safe to retry
- Python execution is NOT idempotent → mark as error and let model decide what to do next

This is a production-grade approach that handles crashes properly without the complexity of a full checkpoint table.

Let me wait for the user's response to see if they have more concerns.

</details>
---
## ASSISTANT (2026-01-04T08:21:00.738Z)

Summary of the recovery strategy:

1. **Write-ahead pattern**: Create records BEFORE execution, update status AFTER
2. **Idempotency distinction**: Web tools can be safely retried, Python cannot
3. **No separate checkpoint table**: The normalized tables (steps, tool_calls) ARE the checkpoint
4. **Clear recovery path**: `status = "running"` on startup means we crashed → apply appropriate recovery action per tool type

For Python, if we crash mid-execution, we mark it as error and let the model decide whether to retry with modified code or proceed without that result. This is safer than blindly re-executing.

Any other failure scenarios you want me to address?
---
## USER (2026-01-04T08:22:50.817Z)

what you've written works for happy path i want you circle back on the entire plan work on scenario where it fails and prepare a plan based on that scenarios too, you should consider deployment too as for the model we use whoever provides gpt-ss-120b apis with harmony see that too, where should we host frontend and backend how are we handling all queues and streaming there has to be design and plan based on both happy paths and unhappy paths
---
## ASSISTANT (2026-01-04T08:23:03.263Z)

<details><summary>Thinking...</summary>

The user wants a more comprehensive plan that covers:
1. Failure scenarios throughout the entire system (not just tool execution)
2. Deployment considerations
3. Model provider selection for gpt-oss-120b with Harmony format
4. Frontend/backend hosting
5. Queue and streaming architecture
6. Both happy and unhappy paths

This is a significant expansion of the plan. Let me think through:

**Failure Scenarios to Cover:**
1. Model API failures (rate limits, timeouts, errors)
2. Tool execution failures (already covered somewhat)
3. Database failures
4. SSE connection drops
5. Frontend reconnection
6. Process crashes
7. Network partitions
8. Memory exhaustion
9. Deployment failures

**Deployment Considerations:**
1. Where to host backend (Railway, Fly.io, AWS, GCP, etc.)
2. Where to host frontend (Vercel, Cloudflare Pages, etc.)
3. Database (SQLite in prod? Need to consider - maybe Turso for distributed SQLite or Postgres)
4. Docker registry for sandbox image
5. Secrets management
6. CI/CD pipeline

**Model Provider:**
- gpt-oss-120b with Harmony format
- Need to research providers: Together AI, DeepInfra, Groq, vLLM self-hosted, etc.
- Need to handle provider-specific quirks

**Queues and Streaming:**
- Current in-memory queue works for single instance
- For production, need to consider what happens on scale
- SSE reconnection handling
- Message ordering guarantees

Let me create a comprehensive update to the plan.

</details>
---
## ASSISTANT (2026-01-04T08:23:04.571Z)

You're right - I need to think through the entire system holistically including deployment, failure modes, and provider selection. Let me research gpt-oss-120b providers first, then rewrite the plan comprehensively.
---
## ASSISTANT (2026-01-04T08:23:05.400Z)

**Tool Use:** WebSearch
```json
{"query":"gpt-oss-120b API providers Harmony format hosting Together AI DeepInfra 2025"}
```
---
## USER (2026-01-04T08:23:59.001Z)


---
## ASSISTANT (2026-01-04T08:24:07.122Z)

<details><summary>Thinking...</summary>

Good, I have info on providers. Let me now rewrite the plan comprehensively covering:

1. Model provider selection (Together AI, DeepInfra, OpenRouter)
2. Deployment architecture (frontend, backend, database)
3. Failure scenarios throughout the entire system4. Queue and streaming design for production5. Recovery strategies for each failure modeI'll rewrite the entire plan with these sections.

</details>
---
## ASSISTANT (2026-01-04T08:24:08.083Z)

Good research. Now let me rewrite the plan comprehensively with failure scenarios, deployment, and production architecture.
---
## ASSISTANT (2026-01-04T08:26:27.903Z)

**Tool Use:** Write
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","content":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.13 / $0.52 | Low | Yes | Native | 99.5% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: Together AI (Primary) + DeepInfra (Fallback)\n\n**Why Together AI primary:**\n- Native Harmony format support\n- 99.9% SLA with dedicated clusters\n- OpenAI-compatible API (drop-in replacement)\n- Good tool calling support for agents\n\n**Failover strategy:**\n```\nRequest → Together AI\n  ↓ (if 5xx or timeout > 30s)\n  → DeepInfra (fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Docker Sandbox    │               │     │\n│         │              │  │  (Sidecar per pod) │               │     │\n│         │              │  └────────────────────┘               │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | Sidecar Docker | Co-located with API for low latency |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result\n    result_summary TEXT,\n    result_raw TEXT,\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox\nsandbox:\n  docker:\n    image: \"reasoner-sandbox:latest\"\n    memory_limit: \"256m\"\n    cpu_limit: \"0.5\"\n    timeout_seconds: 30\n    network_disabled: true\n```\n\n### Environment Variables\n\n```bash\n# Required\nTOGETHER_API_KEY=xxx      # Primary model provider\nPARALLEL_API_KEY=xxx      # Web search/extract\n\n# Optional (for failover)\nDEEPINFRA_API_KEY=xxx     # Fallback model provider\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add all agent tables\n2. `orchestrator/schemas.py` - Pydantic models for agent\n3. `orchestrator/storage/repositories/agent_repo.py` - CRUD operations\n\n### Phase 2: Provider Chain\n4. `orchestrator/providers/chain.py` - Multi-provider with failover\n5. `orchestrator/providers/circuit_breaker.py` - Circuit breaker implementation\n6. Update `orchestrator/config.py` - Add provider chain config\n\n### Phase 3: Tool Layer\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Parallel Search\n10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract\n11. `orchestrator/agent/tools/python_sandbox.py` - Docker sandbox\n12. `docker/sandbox/Dockerfile` - Sandbox image\n\n### Phase 4: Agent Core\n13. `orchestrator/agent/state_machine.py` - State transitions\n14. `orchestrator/agent/recovery.py` - Crash recovery logic\n15. `orchestrator/agent/agent_engine.py` - Main loop\n\n### Phase 5: API Layer\n16. `orchestrator/routes/agent.py` - Agent endpoints + SSE\n17. `orchestrator/app.py` - Register router, startup recovery\n\n### Phase 6: Frontend\n18. `ui/src/types/agent.ts` - TypeScript types\n19. `ui/src/api/client.ts` - Agent API client\n20. `ui/src/hooks/useStore.ts` - Agent state\n21. `ui/src/hooks/useAgentSSE.ts` - SSE with reconnection\n22. `ui/src/components/AgentThinkingPanel.tsx`\n23. `ui/src/components/ToolCallCard.tsx`\n24. `ui/src/components/CitationInline.tsx`\n25. `ui/src/components/AnswerWithCitations.tsx`\n26. `ui/src/components/ConversationView.tsx` - Integrate agent mode\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] Together AI API key configured\n- [ ] Parallel.ai API key configured\n- [ ] DeepInfra API key configured (fallback)\n- [ ] Docker sandbox image built and pushed\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] Sandbox network isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T08:26:27.963Z)


---
## ASSISTANT (2026-01-04T08:26:40.295Z)

<details><summary>Thinking...</summary>

I've completely rewritten the plan to cover:

1. **Model Provider Selection** - Together AI primary + DeepInfra fallback, with provider chain and circuit breakers

2. **Deployment Architecture** - Full diagram with Vercel (frontend), Railway/Fly.io (backend), Turso (database), and external services

3. **System-Wide Failure Scenarios** - Covering:
   - Model API failures (rate limits, timeouts, 5xx, all providers down)
   - Tool execution failures (per tool type)
   - Database failures
   - SSE/streaming failures with reconnection logic
   - Process crash & recovery with startup scan

4. **Data Model** - Complete with idempotency keys and crash detection fields

5. **Agent Engine Design** - Full loop with error handling, provider failover, tool recovery

6. **SSE Architecture** - Event types, payloads, resumption support

7. **Configuration** - Complete config with providers, agent settings, parallel.ai, sandbox

8. **Implementation Order** - 26 files in 6 phases

9. **Deployment Steps** - Railway, Vercel, Turso commands

10. **Production Checklist** - Pre-launch, monitoring, recovery testing, security

Let me ask if the user is satisfied with this comprehensive plan or has more feedback.

</details>
---
## ASSISTANT (2026-01-04T08:26:44.913Z)

I've completely rewritten the plan to cover both happy and unhappy paths:

**New sections added:**

1. **Model Provider Selection** - Together AI primary + DeepInfra fallback with automatic failover and circuit breakers

2. **Deployment Architecture** - Complete diagram with Vercel (frontend), Railway (backend), Turso (distributed SQLite), Docker sandbox as sidecar

3. **System-Wide Failure Scenarios:**
   - Model API failures (rate limits, timeouts, all providers down)
   - Tool execution failures (per tool type with specific recovery)
   - Database failures
   - SSE/streaming failures with frontend reconnection logic
   - Process crash & startup recovery scan

4. **SSE with Resumption** - `since_seq` parameter for clients to resume from last event after disconnect

5. **Agent Engine** - Full error handling with `RecoverableError` vs `FatalError` distinction

6. **Deployment Steps** - Actual commands for Railway, Vercel, Turso

Any other scenarios you want me to address?
---
## USER (2026-01-04T09:32:58.902Z)

<ide_selection>The user selected the lines 1 to 826 from /Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md:
# Web Research Agent - Production Implementation Plan

## Overview

Build a production-grade web research agent with:
- **Tools**: Parallel.ai (search/extract) + Python sandbox
- **Model**: gpt-oss-120b via Harmony-compatible provider
- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)
- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers

---

## 1. Model Provider Selection

### Provider Comparison

| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |
|----------|----------------------------|---------|--------------|-----------------|-----|
| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |
| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.13 / $0.52 | Low | Yes | Native | 99.5% |
| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |

### Recommendation: Together AI (Primary) + DeepInfra (Fallback)

**Why Together AI primary:**
- Native Harmony format support
- 99.9% SLA with dedicated clusters
- OpenAI-compatible API (drop-in replacement)
- Good tool calling support for agents

**Failover strategy:**
```
Request → Together AI
  ↓ (if 5xx or timeout > 30s)
  → DeepInfra (fallback)
  ↓ (if also fails)
  → Error with retry option
```

### Harmony Format Requirement

gpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.

---

## 2. Deployment Architecture

### Component Deployment

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRODUCTION ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐      ┌──────────────────────────────────────┐     │
│  │   Frontend   │      │            Backend Cluster            │     │
│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │
│  │              │ SSE  │                                       │     │
│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │
│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │
│         │              │  │  :9000  │  │  :9000  │            │     │
│         │              │  └────┬────┘  └────┬────┘            │     │
│         │              │       │            │                  │     │
│         │              │       ▼            ▼                  │     │
│         │              │  ┌────────────────────┐               │     │
│         │              │  │  Shared SQLite DB  │               │     │
│         │              │  │  (Turso / Litestream)              │     │
│         │              │  └────────────────────┘               │     │
│         │              │           │                           │     │
│         │              │           ▼                           │     │
│         │              │  ┌────────────────────┐               │     │
│         │              │  │  Docker Sandbox    │               │     │
│         │              │  │  (Sidecar per pod) │               │     │
│         │              │  └────────────────────┘               │     │
│         │              └──────────────────────────────────────┘     │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    EXTERNAL SERVICES                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │
│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │
│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │
│  │  │              │  │   extract)   │  │              │        │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Hosting Decisions

| Component | Platform | Rationale |
|-----------|----------|-----------|
| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |
| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |
| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |
| **Sandbox** | Sidecar Docker | Co-located with API for low latency |
| **Secrets** | Platform secrets | Railway/Fly built-in secret management |

### Why NOT separate queue service (Redis/RabbitMQ)?

For V1 single-instance:
- In-memory asyncio.Queue is sufficient
- SSE is connection-based, not queue-based
- Complexity not justified for single instance
- Add Redis later when scaling to multi-instance

---

## 3. System-Wide Failure Scenarios

### 3.1 Model API Failures

| Failure | Detection | Recovery | User Experience |
|---------|-----------|----------|-----------------|
| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | "Thinking..." with delay |
| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |
| 5xx error | HTTP status | Retry once, then fallback | Brief delay |
| Invalid response | JSON parse error | Retry with same provider | Retry automatically |
| All providers down | Both fail | Mark run as error, notify user | "Service unavailable, retry later" |

**Implementation:**

```python
class ModelProviderChain:
    """Chain of model providers with automatic failover."""

    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers  # [TogetherAI, DeepInfra]
        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}

    async def complete(self, messages, tools, **kwargs) -> LLMResponse:
        last_error = None

        for provider in self.providers:
            cb = self.circuit_breakers[provider.name]

            if cb.is_open:
                continue  # Skip this provider

            try:
                response = await provider.complete(messages, tools, **kwargs)
                cb.record_success()
                return response
            except RateLimitError as e:
                cb.record_failure()
                last_error = e
                await asyncio.sleep(e.retry_after or 1)
            except (TimeoutError, ServerError) as e:
                cb.record_failure()
                last_error = e
                # Try next provider immediately

        raise AllProvidersFailedError(last_error)
```

### 3.2 Tool Execution Failures

| Tool | Failure | Detection | Recovery |
|------|---------|-----------|----------|
| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |
| **web_search** | Rate limit | 429 | Backoff + retry |
| **web_search** | Timeout | >15s | Retry once |
| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |
| **web_extract** | Rate limit | 429 | Backoff + retry |
| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |
| **python_execute** | OOM | Container killed | Return memory error |
| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |

**Tool Result to Model:**

```python
# On failure, we tell the model what happened so it can adapt
tool_result = {
    "tool_call_id": "call_123",
    "status": "error",
    "error_type": "timeout",
    "error_message": "Execution exceeded 30s limit",
    "suggestion": "Try a simpler computation or break into smaller steps"
}
```

### 3.3 Database Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Connection lost | SQLite exception | Reconnect with backoff |
| Disk full | Write error | Alert, pause new runs |
| Corruption | Integrity check | Restore from backup |
| Lock contention | Timeout | Retry with exponential backoff |

**With Turso (recommended for prod):**
- Automatic replication
- Point-in-time recovery
- No lock contention (distributed)

### 3.4 SSE/Streaming Failures

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Client disconnect | Connection close event | Continue run, discard events |
| Network timeout | No heartbeat received | Client reconnects, resumes from last event |
| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |

**Frontend Reconnection Logic:**

```typescript
function useAgentSSE(runId: string) {
  const [lastEventSeq, setLastEventSeq] = useState(0);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectAttempts = 0;

    const connect = () => {
      // Resume from last seen event
      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;
      eventSource = new EventSource(url);

      eventSource.onmessage = (event) => {
        reconnectAttempts = 0;  // Reset on successful message
        const data = JSON.parse(event.data);
        setLastEventSeq(data.seq);
        // Process event...
      };

      eventSource.onerror = () => {
        eventSource?.close();

        if (reconnectAttempts < 5) {
          reconnectAttempts++;
          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));
        } else {
          // Give up, poll for final state
          pollFinalState(runId);
        }
      };
    };

    connect();
    return () => eventSource?.close();
  }, [runId]);
}
```

### 3.5 Process Crash & Recovery

| Crash Point | State Before Crash | Recovery Action |
|-------------|-------------------|-----------------|
| Before step created | run.current_step = N | Create step N, continue |
| After step, before model call | step exists, no response | Redo model call |
| After model response, before tool record | step has response | Parse response, create tool call |
| During tool execution | tool_call.status = "running" | See tool-specific recovery |
| After tool result, before step complete | tool_call.status = "success" | Mark step complete, continue |

**Startup Recovery Scan:**

```python
async def recover_incomplete_runs():
    """Called on server startup to recover any crashed runs."""

    # Find runs that were in progress when we crashed
    incomplete_runs = await db.execute("""
        SELECT run_id FROM runs
        WHERE mode = 'agent'
        AND status = 'running'
        AND updated_at < datetime('now', '-5 minutes')
    """)

    for run in incomplete_runs:
        try:
            action = await determine_recovery_action(run.run_id)

            if action == RecoveryAction.CONTINUE:
                # Re-queue the run for processing
                asyncio.create_task(resume_agent_run(run.run_id))
            elif action == RecoveryAction.MARK_FAILED:
                await mark_run_failed(run.run_id, "Crashed during execution")
        except Exception as e:
            logger.error(f"Recovery failed for {run.run_id}: {e}")
            await mark_run_failed(run.run_id, f"Recovery failed: {e}")
```

---

## 4. Data Model (Complete)

### Extended `runs` Table

```sql
ALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';
ALTER TABLE runs ADD COLUMN agent_state TEXT;
ALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;
ALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;
ALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection
```

### `agent_steps` Table

```sql
CREATE TABLE IF NOT EXISTS agent_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,

    -- State
    state TEXT NOT NULL,  -- planning | tool_calling | complete | error

    -- Model interaction
    model_request_event_id TEXT,
    model_response_event_id TEXT,
    thinking_text TEXT,

    -- Decision
    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'
    decision_raw TEXT,  -- Raw model output for debugging

    -- Error tracking
    error_message TEXT,
    error_recoverable BOOLEAN DEFAULT TRUE,

    UNIQUE(run_id, step_number),
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
```

### `agent_tool_calls` Table

```sql
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    created_at TEXT NOT NULL,

    -- Tool info
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,

    -- Execution tracking
    status TEXT NOT NULL,  -- pending | running | success | error | timeout
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,

    -- Idempotency & retry
    idempotency_key TEXT NOT NULL,  -- UUID for deduplication
    execution_attempt INTEGER DEFAULT 1,
    max_attempts INTEGER DEFAULT 3,

    -- Result
    result_summary TEXT,
    result_raw TEXT,
    error_message TEXT,
    error_type TEXT,  -- timeout | api_error | parse_error | etc.

    -- Trace linkage
    trace_event_id TEXT,

    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE
);

CREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);
CREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);
```

### `agent_citations` Table

```sql
CREATE TABLE IF NOT EXISTS agent_citations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    created_at TEXT NOT NULL,

    source_url TEXT NOT NULL,
    title TEXT,
    snippet TEXT NOT NULL,

    used_in_answer BOOLEAN DEFAULT FALSE,

    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE
);

CREATE INDEX idx_citations_run ON agent_citations(run_id);
```

---

## 5. Agent Engine Design

### State Machine

```
                         ┌──────────────────────────────────────────────┐
                         │                                              │
     ┌───────────────────┼──────────────────────────────────────────┐   │
     │                   │                                          │   │
     ▼                   │                                          ▼   ▼
┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐
│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│
└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘
                         │                      │
                         │    ┌─────────────────┘
                         │    │
                         ▼    ▼
                    ┌──────────┐
                    │SYNTHESIZE│─────────────────────────────────────────▶
                    └──────────┘
                         │
     ┌───────────────────┼───────────────────────────────────────────────┐
     │                   │                                               │
     │                   ▼                                               │
     │              ┌─────────┐                                          │
     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘
                    └─────────┘
                         │
                         ▼
                    ┌──────────┐
                    │CANCELLED │ (user-initiated only)
                    └──────────┘
```

### Agent Loop with Error Handling

```python
class AgentEngine:
    async def run(self, run_id: str, query: str) -> AgentResult:
        context = await self._init_or_restore(run_id, query)

        try:
            while context.step_number < context.max_steps:
                # Check for cancellation
                if await self._is_cancelled(run_id):
                    return await self._finalize(context, AgentState.CANCELLED)

                # Heartbeat for crash detection
                await self._update_heartbeat(run_id)

                context.step_number += 1
                step = await self._create_step(context)

                try:
                    # PLANNING: Call model
                    response = await self._call_model_with_retry(context)
                    await self._record_model_response(step, response)

                    if response.tool_calls:
                        # TOOL_CALLING
                        for tool_call in response.tool_calls:
                            result = await self._execute_tool_with_recovery(
                                context, step, tool_call
                            )
                            context.add_tool_result(result)
                    else:
                        # SYNTHESIZING: Final answer
                        context.final_answer = response.text
                        await self._mark_citations_used(context)
                        return await self._finalize(context, AgentState.COMPLETE)

                except RecoverableError as e:
                    # Log and continue to next step
                    await self._record_step_error(step, e)
                    context.add_error(e)

                except FatalError as e:
                    # Cannot continue
                    return await self._finalize(context, AgentState.ERROR, str(e))

            # Max steps reached - force synthesis
            return await self._force_synthesis(context)

        except Exception as e:
            logger.exception(f"Unexpected error in agent run {run_id}")
            return await self._finalize(context, AgentState.ERROR, str(e))

    async def _call_model_with_retry(self, context) -> LLMResponse:
        """Call model with provider failover."""
        for attempt in range(3):
            try:
                return await self.provider_chain.complete(
                    messages=context.messages,
                    tools=self.tool_registry.get_openai_tools(),
                    reasoning_effort="medium",
                )
            except RateLimitError as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(e.retry_after or (2 ** attempt))
            except AllProvidersFailedError:
                raise FatalError("All model providers unavailable")

    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:
        """Execute tool with idempotency and recovery."""

        # Create record BEFORE execution (write-ahead)
        tool_record = await self._create_tool_record(step, tool_call)

        try:
            await self._update_tool_status(tool_record.id, "running")

            result = await self.tool_registry.execute(
                tool_call.name,
                tool_call.arguments,
                idempotency_key=tool_record.idempotency_key,
            )

            await self._save_tool_result(tool_record.id, result)

            # Extract and save citations
            if result.citations:
                await self._save_citations(context.run_id, tool_record.id, result.citations)

            return result

        except ToolTimeoutError:
            await self._update_tool_status(tool_record.id, "timeout")
            return ToolResult(
                success=False,
                error="Execution timed out after 30 seconds"
            )
        except ToolError as e:
            await self._update_tool_status(tool_record.id, "error", str(e))

            if tool_record.execution_attempt < tool_record.max_attempts:
                # Retry for idempotent tools
                if tool_call.name in ("web_search", "web_extract"):
                    return await self._retry_tool(context, step, tool_call, tool_record)

            return ToolResult(success=False, error=str(e))
```

---

## 6. SSE & Streaming Architecture

### Event Types

```python
class SSEEventType(str, Enum):
    # State changes
    AGENT_STATE = "agent_state"      # State transition
    STEP_START = "step_start"        # New step beginning
    STEP_COMPLETE = "step_complete"  # Step finished

    # Tool events
    TOOL_START = "tool_start"        # Tool execution starting
    TOOL_PROGRESS = "tool_progress"  # Optional progress update
    TOOL_RESULT = "tool_result"      # Tool completed (summary only)

    # Content streaming
    THINKING = "thinking"            # Model reasoning tokens
    ANSWER = "answer"                # Final answer tokens
    CITATION = "citation"            # Citation added

    # Terminal
    COMPLETE = "complete"            # Run finished successfully
    ERROR = "error"                  # Run failed
    CANCELLED = "cancelled"          # Run was cancelled

    # Connection
    HEARTBEAT = "heartbeat"          # Keep-alive ping
```

### Event Payload Structure

```python
@dataclass
class SSEEvent:
    type: SSEEventType
    seq: int                    # Monotonic sequence number
    timestamp: str              # ISO timestamp
    run_id: str
    data: dict                  # Event-specific payload

    def to_sse(self) -> str:
        return f"event: {self.type.value}\ndata: {json.dumps(self.to_dict())}\n\n"
```

### Streaming Endpoint with Resumption

```python
@router.get("/agent/runs/{run_id}/stream")
async def stream_agent_events(
    run_id: str,
    since_seq: int = Query(0, description="Resume from this sequence number"),
):
    """Stream agent events with resumption support."""

    async def event_generator():
        # First, replay any missed events from DB
        if since_seq > 0:
            missed_events = await get_events_since(run_id, since_seq)
            for event in missed_events:
                yield event.to_sse()

        # Then stream live events
        queue = get_or_create_queue(run_id)
        last_heartbeat = time.time()

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield event.to_sse()

                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):
                    break

            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield SSEEvent(
                    type=SSEEventType.HEARTBEAT,
                    seq=-1,
                    timestamp=datetime.now().isoformat(),
                    run_id=run_id,
                    data={}
                ).to_sse()

    return EventSourceResponse(event_generator())
```

---

## 7. Configuration

### `chat_config.yaml` additions

```yaml
# Model providers with failover
model_providers:
  primary:
    name: together_ai
    base_url: "https://api.together.xyz/v1"
    api_key: ${TOGETHER_API_KEY}
    model: "openai/gpt-oss-120b"
    timeout_ms: 60000
    max_retries: 2
  fallback:
    name: deepinfra
    base_url: "https://api.deepinfra.com/v1/openai"
    api_key: ${DEEPINFRA_API_KEY}
    model: "openai/gpt-oss-120b"
    timeout_ms: 60000
    max_retries: 1

# Agent settings
agent:
  enabled: true
  max_steps: 10
  step_timeout_ms: 120000

  # Recovery settings
  recovery:
    enabled: true
    scan_interval_seconds: 60
    stale_run_threshold_minutes: 30

  # Circuit breaker
  circuit_breaker:
    failure_threshold: 5
    recovery_timeout_seconds: 30

# Parallel.ai
parallel:
  base_url: "https://api.parallel.ai/v1beta"
  api_key: ${PARALLEL_API_KEY}
  search:
    max_results: 10
    timeout_ms: 15000
    max_retries: 3
  extract:
    timeout_ms: 30000
    max_urls_per_request: 5
    max_retries: 3

# Sandbox
sandbox:
  docker:
    image: "reasoner-sandbox:latest"
    memory_limit: "256m"
    cpu_limit: "0.5"
    timeout_seconds: 30
    network_disabled: true
```

### Environment Variables

```bash
# Required
TOGETHER_API_KEY=xxx      # Primary model provider
PARALLEL_API_KEY=xxx      # Web search/extract

# Optional (for failover)
DEEPINFRA_API_KEY=xxx     # Fallback model provider

# Database (if using Turso)
TURSO_DATABASE_URL=xxx
TURSO_AUTH_TOKEN=xxx
```

---

## 8. Implementation Order

### Phase 1: Data Layer
1. `orchestrator/storage/schema.sql` - Add all agent tables
2. `orchestrator/schemas.py` - Pydantic models for agent
3. `orchestrator/storage/repositories/agent_repo.py` - CRUD operations

### Phase 2: Provider Chain
4. `orchestrator/providers/chain.py` - Multi-provider with failover
5. `orchestrator/providers/circuit_breaker.py` - Circuit breaker implementation
6. Update `orchestrator/config.py` - Add provider chain config

### Phase 3: Tool Layer
7. `orchestrator/agent/tools/base.py` - BaseTool ABC
8. `orchestrator/agent/tools/registry.py` - Tool registry
9. `orchestrator/agent/tools/web_search.py` - Parallel Search
10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract
11. `orchestrator/agent/tools/python_sandbox.py` - Docker sandbox
12. `docker/sandbox/Dockerfile` - Sandbox image

### Phase 4: Agent Core
13. `orchestrator/agent/state_machine.py` - State transitions
14. `orchestrator/agent/recovery.py` - Crash recovery logic
15. `orchestrator/agent/agent_engine.py` - Main loop

### Phase 5: API Layer
16. `orchestrator/routes/agent.py` - Agent endpoints + SSE
17. `orchestrator/app.py` - Register router, startup recovery

### Phase 6: Frontend
18. `ui/src/types/agent.ts` - TypeScript types
19. `ui/src/api/client.ts` - Agent API client
20. `ui/src/hooks/useStore.ts` - Agent state
21. `ui/src/hooks/useAgentSSE.ts` - SSE with reconnection
22. `ui/src/components/AgentThinkingPanel.tsx`
23. `ui/src/components/ToolCallCard.tsx`
24. `ui/src/components/CitationInline.tsx`
25. `ui/src/components/AnswerWithCitations.tsx`
26. `ui/src/components/ConversationView.tsx` - Integrate agent mode

---

## 9. Deployment Steps

### Backend (Railway)

```bash
# 1. Create Railway project
railway login
railway init

# 2. Add Dockerfile
# (Uses existing orchestrator setup)

# 3. Set environment variables
railway variables set TOGETHER_API_KEY=xxx
railway variables set PARALLEL_API_KEY=xxx
railway variables set DEEPINFRA_API_KEY=xxx

# 4. Deploy
railway up
```

### Frontend (Vercel)

```bash
# 1. Connect to Vercel
cd ui && vercel

# 2. Set environment variables
vercel env add VITE_API_URL  # Backend URL

# 3. Deploy
vercel --prod
```

### Database (Turso)

```bash
# 1. Create database
turso db create reasoner

# 2. Get credentials
turso db tokens create reasoner

# 3. Set in Railway
railway variables set TURSO_DATABASE_URL=libsql://...
railway variables set TURSO_AUTH_TOKEN=...
```

---

## 10. Production Checklist

### Pre-Launch
- [ ] Together AI API key configured
- [ ] Parallel.ai API key configured
- [ ] DeepInfra API key configured (fallback)
- [ ] Docker sandbox image built and pushed
- [ ] Database migrated with agent tables
- [ ] Environment variables set in Railway/Vercel
- [ ] CORS configured for frontend domain

### Monitoring
- [ ] Structured logging for all tool calls
- [ ] Error alerting configured
- [ ] Latency metrics for model calls
- [ ] Tool failure rate dashboard

### Recovery Testing
- [ ] Kill backend mid-run → verify resume works
- [ ] Simulate model provider failure → verify fallback
- [ ] Simulate tool timeout → verify graceful handling
- [ ] Disconnect SSE client → verify reconnection

### Security
- [ ] API keys not in logs (redaction)
- [ ] Sandbox network isolation verified
- [ ] Rate limiting on agent endpoints
- [ ] Input validation on all endpoints


This may or may not be related to the current task.</ide_selection>

i need you to show me everything in this doc the entire plan not just upgrades on top of exisiting repo in a new md
---
## ASSISTANT (2026-01-04T09:33:07.472Z)

<details><summary>Thinking...</summary>

The user wants me to create a completely standalone plan document that shows the entire system design from scratch - not just the delta/upgrades on top of the existing repo. They want a comprehensive document that could stand alone as a complete architecture reference.

Let me create a new comprehensive document that covers everything end-to-end.

</details>
---
## ASSISTANT (2026-01-04T09:33:08.095Z)

I'll create a complete standalone architecture document that covers the entire system from scratch.
---
## ASSISTANT (2026-01-04T09:41:21.702Z)

**Tool Use:** Write
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md","content":"# Web Research Agent - Complete System Design\n\n## Table of Contents\n\n1. [System Overview](#1-system-overview)\n2. [Architecture Diagram](#2-architecture-diagram)\n3. [Model & Provider Layer](#3-model--provider-layer)\n4. [Tool System](#4-tool-system)\n5. [Agent Engine](#5-agent-engine)\n6. [Data Model](#6-data-model)\n7. [API Design](#7-api-design)\n8. [SSE & Streaming](#8-sse--streaming)\n9. [Frontend Architecture](#9-frontend-architecture)\n10. [Failure Scenarios & Recovery](#10-failure-scenarios--recovery)\n11. [Deployment](#11-deployment)\n12. [Configuration](#12-configuration)\n13. [Observability](#13-observability)\n14. [Security](#14-security)\n15. [Implementation Plan](#15-implementation-plan)\n\n---\n\n## 1. System Overview\n\n### What We're Building\n\nA production-grade web research agent that:\n- Searches the web for information using Parallel.ai APIs\n- Extracts and summarizes content from web pages\n- Executes Python code for calculations and data processing\n- Provides evidence-grounded answers with citations\n- Recovers from crashes and failures gracefully\n- Streams real-time progress to the UI\n\n### Core Capabilities\n\n| Capability | Implementation |\n|------------|----------------|\n| Web Search | Parallel.ai Search API |\n| Content Extraction | Parallel.ai Extract API |\n| Computation | Docker-sandboxed Python |\n| Reasoning | gpt-oss-120b with Harmony format |\n| Streaming | Server-Sent Events (SSE) |\n| Durability | SQLite with write-ahead logging |\n| Recovery | Checkpoint-based crash recovery |\n\n### Non-Negotiables\n\n1. **Evidence-grounded answers** - Every claim backed by citations to source snippets\n2. **Durable runs** - Crash → resume; cancel works; retries are recorded\n3. **Full trace system** - Complete trace of model calls, tool executions, errors\n4. **Thinking UI = trace projection** - Not a separate narrative, but visualization of actual events\n5. **Answer accuracy** - Prioritize correctness over speed\n\n---\n\n## 2. Architecture Diagram\n\n### High-Level System Architecture\n\n```\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                              SYSTEM ARCHITECTURE                                 │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\n┌─────────────────┐         HTTPS/SSE          ┌──────────────────────────────────┐\n│                 │◄──────────────────────────▶│                                  │\n│    FRONTEND     │                            │            BACKEND               │\n│    (Vercel)     │                            │        (Railway/Fly.io)          │\n│                 │                            │                                  │\n│  ┌───────────┐  │                            │  ┌────────────────────────────┐  │\n│  │  React    │  │                            │  │      FastAPI Server        │  │\n│  │  Vite     │  │                            │  │         :9000              │  │\n│  │  Zustand  │  │                            │  └────────────┬───────────────┘  │\n│  │  Tailwind │  │                            │               │                  │\n│  └───────────┘  │                            │               ▼                  │\n│                 │                            │  ┌────────────────────────────┐  │\n│  Components:    │                            │  │      Agent Engine          │  │\n│  • Chat View    │                            │  │  ┌──────────────────────┐  │  │\n│  • Thinking     │                            │  │  │   State Machine      │  │  │\n│    Panel        │                            │  │  │   • PLANNING         │  │  │\n│  • Citations    │                            │  │  │   • TOOL_CALLING     │  │  │\n│  • Tool Cards   │                            │  │  │   • SYNTHESIZING     │  │  │\n│                 │                            │  │  │   • COMPLETE/ERROR   │  │  │\n└─────────────────┘                            │  │  └──────────────────────┘  │  │\n                                               │  │                            │  │\n                                               │  │  ┌──────────────────────┐  │  │\n                                               │  │  │   Tool Registry      │  │  │\n                                               │  │  │   • web_search       │  │  │\n                                               │  │  │   • web_extract      │  │  │\n                                               │  │  │   • python_execute   │  │  │\n                                               │  │  └──────────────────────┘  │  │\n                                               │  │                            │  │\n                                               │  │  ┌──────────────────────┐  │  │\n                                               │  │  │   Provider Chain     │  │  │\n                                               │  │  │   • Together AI      │  │  │\n                                               │  │  │   • DeepInfra        │  │  │\n                                               │  │  │   • Circuit Breaker  │  │  │\n                                               │  │  └──────────────────────┘  │  │\n                                               │  └────────────────────────────┘  │\n                                               │               │                  │\n                                               │               ▼                  │\n                                               │  ┌────────────────────────────┐  │\n                                               │  │        Data Layer          │  │\n                                               │  │  ┌──────────────────────┐  │  │\n                                               │  │  │   SQLite / Turso     │  │  │\n                                               │  │  │   • runs             │  │  │\n                                               │  │  │   • agent_steps      │  │  │\n                                               │  │  │   • agent_tool_calls │  │  │\n                                               │  │  │   • agent_citations  │  │  │\n                                               │  │  │   • trace_events     │  │  │\n                                               │  │  └──────────────────────┘  │  │\n                                               │  └────────────────────────────┘  │\n                                               │               │                  │\n                                               │               ▼                  │\n                                               │  ┌────────────────────────────┐  │\n                                               │  │     Docker Sandbox         │  │\n                                               │  │     (Sidecar Container)    │  │\n                                               │  │     • Python 3.11          │  │\n                                               │  │     • numpy, pandas, etc.  │  │\n                                               │  │     • Network disabled     │  │\n                                               │  └────────────────────────────┘  │\n                                               └──────────────────────────────────┘\n                                                              │\n                                                              ▼\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                            EXTERNAL SERVICES                                     │\n│                                                                                  │\n│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐      │\n│  │    Together AI      │  │    Parallel.ai      │  │     DeepInfra       │      │\n│  │                     │  │                     │  │                     │      │\n│  │  Model: gpt-oss-    │  │  • Search API       │  │  Model: gpt-oss-    │      │\n│  │         120b        │  │  • Extract API      │  │         120b        │      │\n│  │                     │  │                     │  │                     │      │\n│  │  Features:          │  │  Features:          │  │  Features:          │      │\n│  │  • Harmony format   │  │  • Ranked URLs      │  │  • Harmony format   │      │\n│  │  • Tool calling     │  │  • Snippets         │  │  • Tool calling     │      │\n│  │  • 99.9% SLA        │  │  • JS rendering     │  │  • 99.5% SLA        │      │\n│  │                     │  │  • PDF extraction   │  │                     │      │\n│  │  Price:             │  │                     │  │  Price:             │      │\n│  │  $0.15/$0.60 per 1M │  │  Price:             │  │  $0.13/$0.52 per 1M │      │\n│  │                     │  │  Search: $5/1K      │  │                     │      │\n│  │  Role: PRIMARY      │  │  Extract: $1/1K     │  │  Role: FALLBACK     │      │\n│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘      │\n│                                                                                  │\n└─────────────────────────────────────────────────────────────────────────────────┘\n```\n\n### Request Flow\n\n```\nUser Query: \"What are the latest developments in quantum computing?\"\n                                    │\n                                    ▼\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                              REQUEST FLOW                                        │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\n1. USER INPUT\n   │\n   ▼\n2. POST /api/agent/conversations/{id}/runs\n   │  Body: { \"query\": \"...\", \"max_steps\": 10 }\n   │\n   ▼\n3. CREATE RUN RECORD\n   │  run_id = uuid4()\n   │  status = \"running\"\n   │  mode = \"agent\"\n   │\n   ▼\n4. START SSE STREAM ◄─────────────────────────────────────────────┐\n   │  GET /api/agent/runs/{run_id}/stream                         │\n   │                                                               │\n   ▼                                                               │\n5. AGENT LOOP                                                      │\n   │                                                               │\n   ├──▶ STEP 1: PLANNING                                          │\n   │    │  • Create agent_step record                             │\n   │    │  • Call model with tools                                │\n   │    │  • Model decides: search for \"quantum computing 2024\"   │\n   │    │                                                          │\n   │    ▼                                                          │\n   │    TOOL_CALLING                                               │\n   │    │  • Create agent_tool_calls record                       │\n   │    │  • Execute web_search                         ──────────▶│ SSE: TOOL_START\n   │    │  • Save results + citations                   ──────────▶│ SSE: TOOL_RESULT\n   │    │                                               ──────────▶│ SSE: CITATION\n   │    │                                                          │\n   │    ▼                                                          │\n   ├──▶ STEP 2: PLANNING                                          │\n   │    │  • Model sees search results                            │\n   │    │  • Decides: extract from top 3 URLs                     │\n   │    │                                                          │\n   │    ▼                                                          │\n   │    TOOL_CALLING                                               │\n   │    │  • Execute web_extract                        ──────────▶│ SSE: TOOL_START\n   │    │  • Save extracted content + citations         ──────────▶│ SSE: TOOL_RESULT\n   │    │                                                          │\n   │    ▼                                                          │\n   ├──▶ STEP 3: PLANNING                                          │\n   │    │  • Model has enough information                         │\n   │    │  • Decides: synthesize answer                           │\n   │    │                                                          │\n   │    ▼                                                          │\n   │    SYNTHESIZING                                               │\n   │    │  • Generate final answer                      ──────────▶│ SSE: ANSWER (stream)\n   │    │  • Include citation references [1], [2]                  │\n   │    │  • Mark used citations                                   │\n   │    │                                                          │\n   │    ▼                                                          │\n   └──▶ COMPLETE                                                   │\n        │  • Update run status = \"succeeded\"            ──────────▶│ SSE: COMPLETE\n        │  • Final answer saved                                    │\n        │                                                          │\n        ▼                                                          │\n6. UI RENDERS                                                      │\n   • Thinking panel shows steps + tool calls                       │\n   • Answer panel shows markdown + citations                       │\n   • Citation tooltips show snippets                               │\n```\n\n---\n\n## 3. Model & Provider Layer\n\n### Provider Selection\n\n| Provider | Endpoint | Price (per 1M tokens) | Latency | SLA | Role |\n|----------|----------|----------------------|---------|-----|------|\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | `api.together.xyz/v1` | $0.15 in / $0.60 out | ~2s | 99.9% | Primary |\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | `api.deepinfra.com/v1/openai` | $0.13 in / $0.52 out | ~2s | 99.5% | Fallback |\n\n### Model: gpt-oss-120b\n\n**Specifications:**\n- 117B parameters (MoE architecture)\n- 5.1B active parameters per forward pass\n- 128K context window\n- Native tool/function calling\n- Requires Harmony chat format\n- Apache 2.0 license\n\n**Harmony Format:**\n```json\n{\n  \"model\": \"openai/gpt-oss-120b\",\n  \"messages\": [\n    {\"role\": \"system\", \"content\": \"You are a research assistant...\"},\n    {\"role\": \"user\", \"content\": \"What are the latest...\"},\n    {\"role\": \"assistant\", \"content\": null, \"tool_calls\": [...]},\n    {\"role\": \"tool\", \"tool_call_id\": \"...\", \"content\": \"...\"}\n  ],\n  \"tools\": [...],\n  \"reasoning_effort\": \"medium\"\n}\n```\n\n### Provider Chain Implementation\n\n```python\n# orchestrator/providers/chain.py\n\nfrom dataclasses import dataclass\nfrom typing import Optional\nimport asyncio\n\n@dataclass\nclass ProviderConfig:\n    name: str\n    base_url: str\n    api_key: str\n    model: str\n    timeout_ms: int = 60000\n    max_retries: int = 2\n\nclass CircuitBreaker:\n    \"\"\"Prevents cascading failures by tracking error rates.\"\"\"\n\n    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):\n        self.failure_threshold = failure_threshold\n        self.recovery_timeout = recovery_timeout\n        self.failures = 0\n        self.last_failure_time: Optional[float] = None\n        self.state = \"closed\"  # closed | open | half_open\n\n    @property\n    def is_open(self) -> bool:\n        if self.state == \"open\":\n            # Check if recovery timeout has passed\n            if time.time() - self.last_failure_time > self.recovery_timeout:\n                self.state = \"half_open\"\n                return False\n            return True\n        return False\n\n    def record_success(self):\n        self.failures = 0\n        self.state = \"closed\"\n\n    def record_failure(self):\n        self.failures += 1\n        self.last_failure_time = time.time()\n        if self.failures >= self.failure_threshold:\n            self.state = \"open\"\n\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[ProviderConfig]):\n        self.providers = []\n        self.circuit_breakers = {}\n\n        for config in providers:\n            provider = OpenAICompatibleProvider(\n                base_url=config.base_url,\n                api_key=config.api_key,\n                default_model=config.model,\n                timeout=config.timeout_ms / 1000,\n            )\n            self.providers.append((config.name, provider))\n            self.circuit_breakers[config.name] = CircuitBreaker()\n\n    async def complete(\n        self,\n        messages: list[dict],\n        tools: Optional[list[dict]] = None,\n        reasoning_effort: str = \"medium\",\n        **kwargs\n    ) -> LLMResponse:\n        \"\"\"Call model with automatic failover between providers.\"\"\"\n\n        last_error = None\n\n        for name, provider in self.providers:\n            cb = self.circuit_breakers[name]\n\n            if cb.is_open:\n                logger.warning(f\"Provider {name} circuit breaker is open, skipping\")\n                continue\n\n            try:\n                logger.info(f\"Attempting model call with {name}\")\n\n                response = await provider.complete(\n                    messages=messages,\n                    tools=tools,\n                    reasoning_effort=reasoning_effort,\n                    **kwargs\n                )\n\n                cb.record_success()\n                logger.info(f\"Model call succeeded with {name}\")\n                return response\n\n            except RateLimitError as e:\n                logger.warning(f\"Rate limit hit on {name}: {e}\")\n                cb.record_failure()\n                last_error = e\n\n                # Wait if retry-after is specified\n                if e.retry_after:\n                    await asyncio.sleep(min(e.retry_after, 10))\n\n            except TimeoutError as e:\n                logger.warning(f\"Timeout on {name}: {e}\")\n                cb.record_failure()\n                last_error = e\n\n            except ServerError as e:\n                logger.warning(f\"Server error on {name}: {e}\")\n                cb.record_failure()\n                last_error = e\n\n        # All providers failed\n        raise AllProvidersFailedError(\n            f\"All model providers failed. Last error: {last_error}\"\n        )\n\n    async def complete_streaming(\n        self,\n        messages: list[dict],\n        on_token: Callable[[str], None],\n        on_reasoning: Optional[Callable[[str], None]] = None,\n        tools: Optional[list[dict]] = None,\n        **kwargs\n    ) -> LLMResponse:\n        \"\"\"Stream completion with failover.\"\"\"\n\n        # Similar to complete() but with streaming callbacks\n        # Implementation details...\n        pass\n```\n\n---\n\n## 4. Tool System\n\n### Tool Architecture\n\n```\n┌─────────────────────────────────────────────────────────────────┐\n│                        TOOL SYSTEM                               │\n└─────────────────────────────────────────────────────────────────┘\n\n┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐\n│   BaseTool      │     │  ToolRegistry   │     │   ToolResult    │\n│   (ABC)         │     │                 │     │   (dataclass)   │\n├─────────────────┤     ├─────────────────┤     ├─────────────────┤\n│ • name          │────▶│ • register()    │────▶│ • success       │\n│ • description   │     │ • get()         │     │ • data          │\n│ • parameters    │     │ • execute()     │     │ • error         │\n│ • execute()     │     │ • to_openai()   │     │ • citations     │\n│ • to_openai()   │     │                 │     │ • duration_ms   │\n└─────────────────┘     └─────────────────┘     └─────────────────┘\n        │\n        ├──────────────────┬──────────────────┐\n        ▼                  ▼                  ▼\n┌───────────────┐  ┌───────────────┐  ┌───────────────┐\n│ WebSearchTool │  │WebExtractTool │  │PythonSandbox  │\n│               │  │               │  │    Tool       │\n├───────────────┤  ├───────────────┤  ├───────────────┤\n│ API:          │  │ API:          │  │ Runtime:      │\n│ Parallel.ai   │  │ Parallel.ai   │  │ Docker        │\n│ /v1beta/search│  │ /v1beta/extract│ │               │\n│               │  │               │  │ Security:     │\n│ Returns:      │  │ Returns:      │  │ --network=none│\n│ • URLs        │  │ • Excerpts    │  │ --read-only   │\n│ • Titles      │  │ • Markdown    │  │ --memory=256m │\n│ • Snippets    │  │               │  │               │\n│ → Citations   │  │ → Citations   │  │ Returns:      │\n│               │  │               │  │ • stdout      │\n│ Idempotent:   │  │ Idempotent:   │  │ • stderr      │\n│ YES           │  │ YES           │  │ • exit_code   │\n│               │  │               │  │               │\n│ Max retries:  │  │ Max retries:  │  │ Idempotent:   │\n│ 3             │  │ 3             │  │ NO            │\n└───────────────┘  └───────────────┘  └───────────────┘\n```\n\n### Base Tool Interface\n\n```python\n# orchestrator/agent/tools/base.py\n\nfrom abc import ABC, abstractmethod\nfrom dataclasses import dataclass, field\nfrom typing import Any, Optional\n\n@dataclass\nclass ToolResult:\n    \"\"\"Normalized result from any tool execution.\"\"\"\n    success: bool\n    data: Optional[dict[str, Any]] = None\n    error: Optional[str] = None\n    error_type: Optional[str] = None  # timeout | api_error | parse_error\n    citations: list[dict] = field(default_factory=list)\n    duration_ms: int = 0\n\nclass BaseTool(ABC):\n    \"\"\"Abstract base class for all agent tools.\"\"\"\n\n    @property\n    @abstractmethod\n    def name(self) -> str:\n        \"\"\"Unique tool identifier used in function calling.\"\"\"\n        pass\n\n    @property\n    @abstractmethod\n    def description(self) -> str:\n        \"\"\"Description shown to the model.\"\"\"\n        pass\n\n    @property\n    @abstractmethod\n    def parameters(self) -> dict:\n        \"\"\"JSON Schema for tool parameters.\"\"\"\n        pass\n\n    @property\n    def is_idempotent(self) -> bool:\n        \"\"\"Whether this tool can be safely retried.\"\"\"\n        return True\n\n    def to_openai_tool(self) -> dict:\n        \"\"\"Convert to OpenAI function calling format.\"\"\"\n        return {\n            \"type\": \"function\",\n            \"function\": {\n                \"name\": self.name,\n                \"description\": self.description,\n                \"parameters\": self.parameters,\n            }\n        }\n\n    @abstractmethod\n    async def execute(\n        self,\n        arguments: dict[str, Any],\n        idempotency_key: Optional[str] = None,\n        timeout_ms: int = 30000,\n    ) -> ToolResult:\n        \"\"\"Execute the tool with given arguments.\"\"\"\n        pass\n```\n\n### Web Search Tool\n\n```python\n# orchestrator/agent/tools/web_search.py\n\nimport httpx\nfrom typing import Any, Optional\n\nclass WebSearchTool(BaseTool):\n    \"\"\"Search the web using Parallel.ai Search API.\"\"\"\n\n    name = \"web_search\"\n    description = \"\"\"Search the web for current information on any topic.\n    Returns ranked URLs with titles and relevant snippets.\n    Use this when you need to find information that may not be in your training data.\"\"\"\n\n    parameters = {\n        \"type\": \"object\",\n        \"properties\": {\n            \"query\": {\n                \"type\": \"string\",\n                \"description\": \"Search query - be specific and include relevant keywords\"\n            },\n            \"max_results\": {\n                \"type\": \"integer\",\n                \"description\": \"Maximum number of results to return (1-10)\",\n                \"default\": 5,\n                \"minimum\": 1,\n                \"maximum\": 10\n            }\n        },\n        \"required\": [\"query\"]\n    }\n\n    def __init__(self, api_key: str, config: dict):\n        self.api_key = api_key\n        self.base_url = config.get(\"base_url\", \"https://api.parallel.ai/v1beta\")\n        self.timeout_ms = config.get(\"timeout_ms\", 15000)\n        self.max_retries = config.get(\"max_retries\", 3)\n\n    async def execute(\n        self,\n        arguments: dict[str, Any],\n        idempotency_key: Optional[str] = None,\n        timeout_ms: Optional[int] = None,\n    ) -> ToolResult:\n        \"\"\"Execute web search.\"\"\"\n\n        query = arguments[\"query\"]\n        max_results = arguments.get(\"max_results\", 5)\n        timeout = (timeout_ms or self.timeout_ms) / 1000\n\n        headers = {\n            \"x-api-key\": self.api_key,\n            \"parallel-beta\": \"search-extract-2025-10-10\",\n            \"Content-Type\": \"application/json\",\n        }\n\n        if idempotency_key:\n            headers[\"Idempotency-Key\"] = idempotency_key\n\n        payload = {\n            \"objective\": query,\n            \"search_queries\": [query],\n            \"max_results\": max_results,\n            \"excerpts\": {\n                \"max_chars_per_result\": 500\n            }\n        }\n\n        start_time = time.time()\n\n        for attempt in range(self.max_retries):\n            try:\n                async with httpx.AsyncClient() as client:\n                    response = await client.post(\n                        f\"{self.base_url}/search\",\n                        headers=headers,\n                        json=payload,\n                        timeout=timeout,\n                    )\n\n                    if response.status_code == 429:\n                        # Rate limited - wait and retry\n                        retry_after = int(response.headers.get(\"Retry-After\", 2))\n                        await asyncio.sleep(retry_after)\n                        continue\n\n                    response.raise_for_status()\n\n                    data = response.json()\n                    duration_ms = int((time.time() - start_time) * 1000)\n\n                    # Extract citations from results\n                    citations = []\n                    for i, result in enumerate(data.get(\"results\", [])):\n                        citations.append({\n                            \"id\": f\"cite_{i+1}\",\n                            \"source_url\": result.get(\"url\", \"\"),\n                            \"title\": result.get(\"title\", \"\"),\n                            \"snippet\": result.get(\"excerpts\", [\"\"])[0] if result.get(\"excerpts\") else \"\",\n                        })\n\n                    return ToolResult(\n                        success=True,\n                        data={\n                            \"search_id\": data.get(\"search_id\"),\n                            \"results\": data.get(\"results\", []),\n                            \"result_count\": len(data.get(\"results\", [])),\n                        },\n                        citations=citations,\n                        duration_ms=duration_ms,\n                    )\n\n            except httpx.TimeoutException:\n                if attempt == self.max_retries - 1:\n                    return ToolResult(\n                        success=False,\n                        error=\"Search request timed out\",\n                        error_type=\"timeout\",\n                        duration_ms=int((time.time() - start_time) * 1000),\n                    )\n                await asyncio.sleep(2 ** attempt)\n\n            except httpx.HTTPStatusError as e:\n                return ToolResult(\n                    success=False,\n                    error=f\"Search API error: {e.response.status_code}\",\n                    error_type=\"api_error\",\n                    duration_ms=int((time.time() - start_time) * 1000),\n                )\n\n        return ToolResult(\n            success=False,\n            error=\"Max retries exceeded\",\n            error_type=\"api_error\",\n            duration_ms=int((time.time() - start_time) * 1000),\n        )\n```\n\n### Web Extract Tool\n\n```python\n# orchestrator/agent/tools/web_extract.py\n\nclass WebExtractTool(BaseTool):\n    \"\"\"Extract content from URLs using Parallel.ai Extract API.\"\"\"\n\n    name = \"web_extract\"\n    description = \"\"\"Extract and summarize content from specific web URLs.\n    Use this after web_search to get detailed information from promising results.\n    Can handle JavaScript-heavy pages and PDFs.\"\"\"\n\n    parameters = {\n        \"type\": \"object\",\n        \"properties\": {\n            \"urls\": {\n                \"type\": \"array\",\n                \"items\": {\"type\": \"string\"},\n                \"description\": \"URLs to extract content from (max 5)\",\n                \"maxItems\": 5\n            },\n            \"objective\": {\n                \"type\": \"string\",\n                \"description\": \"What information to focus on when extracting\"\n            }\n        },\n        \"required\": [\"urls\"]\n    }\n\n    def __init__(self, api_key: str, config: dict):\n        self.api_key = api_key\n        self.base_url = config.get(\"base_url\", \"https://api.parallel.ai/v1beta\")\n        self.timeout_ms = config.get(\"timeout_ms\", 30000)\n        self.max_urls = config.get(\"max_urls_per_request\", 5)\n\n    async def execute(\n        self,\n        arguments: dict[str, Any],\n        idempotency_key: Optional[str] = None,\n        timeout_ms: Optional[int] = None,\n    ) -> ToolResult:\n        \"\"\"Execute content extraction.\"\"\"\n\n        urls = arguments[\"urls\"][:self.max_urls]\n        objective = arguments.get(\"objective\", \"\")\n\n        headers = {\n            \"x-api-key\": self.api_key,\n            \"parallel-beta\": \"search-extract-2025-10-10\",\n            \"Content-Type\": \"application/json\",\n        }\n\n        if idempotency_key:\n            headers[\"Idempotency-Key\"] = idempotency_key\n\n        payload = {\n            \"urls\": urls,\n            \"objective\": objective,\n            \"excerpts\": True,\n            \"full_content\": False,  # Only excerpts for UI\n        }\n\n        start_time = time.time()\n\n        try:\n            async with httpx.AsyncClient() as client:\n                response = await client.post(\n                    f\"{self.base_url}/extract\",\n                    headers=headers,\n                    json=payload,\n                    timeout=(timeout_ms or self.timeout_ms) / 1000,\n                )\n\n                response.raise_for_status()\n                data = response.json()\n\n                duration_ms = int((time.time() - start_time) * 1000)\n\n                # Extract citations from results\n                citations = []\n                for i, result in enumerate(data.get(\"results\", [])):\n                    for j, excerpt in enumerate(result.get(\"excerpts\", [])):\n                        citations.append({\n                            \"id\": f\"cite_{len(citations)+1}\",\n                            \"source_url\": result.get(\"url\", \"\"),\n                            \"title\": result.get(\"title\", \"\"),\n                            \"snippet\": excerpt.get(\"text\", \"\") if isinstance(excerpt, dict) else str(excerpt),\n                        })\n\n                return ToolResult(\n                    success=True,\n                    data={\n                        \"extract_id\": data.get(\"extract_id\"),\n                        \"results\": data.get(\"results\", []),\n                        \"errors\": data.get(\"errors\", []),\n                    },\n                    citations=citations,\n                    duration_ms=duration_ms,\n                )\n\n        except httpx.TimeoutException:\n            return ToolResult(\n                success=False,\n                error=\"Extraction request timed out\",\n                error_type=\"timeout\",\n                duration_ms=int((time.time() - start_time) * 1000),\n            )\n\n        except httpx.HTTPStatusError as e:\n            return ToolResult(\n                success=False,\n                error=f\"Extract API error: {e.response.status_code}\",\n                error_type=\"api_error\",\n                duration_ms=int((time.time() - start_time) * 1000),\n            )\n```\n\n### Python Sandbox Tool\n\n```python\n# orchestrator/agent/tools/python_sandbox.py\n\nimport asyncio\nimport subprocess\nimport tempfile\nimport uuid\n\nclass PythonSandboxTool(BaseTool):\n    \"\"\"Execute Python code in a secure Docker sandbox.\"\"\"\n\n    name = \"python_execute\"\n    description = \"\"\"Execute Python code for calculations, data analysis, or processing.\n    Available libraries: numpy, pandas, scipy, sympy, math, statistics.\n    No network access. 30 second timeout. 256MB memory limit.\n    Use for: math calculations, data transformations, formula evaluation.\"\"\"\n\n    parameters = {\n        \"type\": \"object\",\n        \"properties\": {\n            \"code\": {\n                \"type\": \"string\",\n                \"description\": \"Python code to execute. Must print results to stdout.\"\n            }\n        },\n        \"required\": [\"code\"]\n    }\n\n    is_idempotent = False  # Code execution is NOT idempotent\n\n    def __init__(self, config: dict):\n        self.image = config.get(\"image\", \"reasoner-sandbox:latest\")\n        self.memory_limit = config.get(\"memory_limit\", \"256m\")\n        self.cpu_limit = config.get(\"cpu_limit\", \"0.5\")\n        self.timeout_seconds = config.get(\"timeout_seconds\", 30)\n        self.network_disabled = config.get(\"network_disabled\", True)\n\n    async def execute(\n        self,\n        arguments: dict[str, Any],\n        idempotency_key: Optional[str] = None,\n        timeout_ms: Optional[int] = None,\n    ) -> ToolResult:\n        \"\"\"Execute Python code in Docker sandbox.\"\"\"\n\n        code = arguments[\"code\"]\n        timeout = (timeout_ms or self.timeout_seconds * 1000) / 1000\n        container_name = f\"sandbox-{uuid.uuid4().hex[:8]}\"\n\n        start_time = time.time()\n\n        try:\n            # Write code to temp file\n            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:\n                f.write(code)\n                code_path = f.name\n\n            # Build Docker command with security options\n            docker_cmd = [\n                \"docker\", \"run\",\n                \"--rm\",\n                \"--name\", container_name,\n                \"--network=none\" if self.network_disabled else \"\",\n                f\"--memory={self.memory_limit}\",\n                f\"--cpus={self.cpu_limit}\",\n                \"--read-only\",\n                \"--tmpfs\", \"/tmp:size=64m\",\n                \"--pids-limit=50\",\n                \"--security-opt=no-new-privileges\",\n                \"-v\", f\"{code_path}:/code/script.py:ro\",\n                self.image,\n                \"python\", \"/code/script.py\"\n            ]\n\n            # Remove empty strings\n            docker_cmd = [c for c in docker_cmd if c]\n\n            # Run with timeout\n            process = await asyncio.create_subprocess_exec(\n                *docker_cmd,\n                stdout=asyncio.subprocess.PIPE,\n                stderr=asyncio.subprocess.PIPE,\n            )\n\n            try:\n                stdout, stderr = await asyncio.wait_for(\n                    process.communicate(),\n                    timeout=timeout\n                )\n            except asyncio.TimeoutError:\n                # Kill the container\n                subprocess.run([\"docker\", \"stop\", container_name], capture_output=True)\n\n                return ToolResult(\n                    success=False,\n                    error=f\"Execution timed out after {timeout}s\",\n                    error_type=\"timeout\",\n                    duration_ms=int((time.time() - start_time) * 1000),\n                )\n\n            duration_ms = int((time.time() - start_time) * 1000)\n\n            if process.returncode != 0:\n                return ToolResult(\n                    success=False,\n                    data={\n                        \"stdout\": stdout.decode()[:5000],\n                        \"stderr\": stderr.decode()[:5000],\n                        \"exit_code\": process.returncode,\n                    },\n                    error=f\"Execution failed: {stderr.decode()[:500]}\",\n                    error_type=\"execution_error\",\n                    duration_ms=duration_ms,\n                )\n\n            return ToolResult(\n                success=True,\n                data={\n                    \"stdout\": stdout.decode()[:10000],\n                    \"stderr\": stderr.decode()[:1000],\n                    \"exit_code\": 0,\n                },\n                duration_ms=duration_ms,\n            )\n\n        except Exception as e:\n            return ToolResult(\n                success=False,\n                error=f\"Sandbox error: {str(e)}\",\n                error_type=\"sandbox_error\",\n                duration_ms=int((time.time() - start_time) * 1000),\n            )\n\n        finally:\n            # Cleanup temp file\n            if 'code_path' in locals():\n                try:\n                    os.unlink(code_path)\n                except:\n                    pass\n```\n\n### Tool Registry\n\n```python\n# orchestrator/agent/tools/registry.py\n\nclass ToolRegistry:\n    \"\"\"Registry of available tools for the agent.\"\"\"\n\n    def __init__(self):\n        self._tools: dict[str, BaseTool] = {}\n\n    def register(self, tool: BaseTool) -> None:\n        \"\"\"Register a tool.\"\"\"\n        self._tools[tool.name] = tool\n        logger.info(f\"Registered tool: {tool.name}\")\n\n    def get(self, name: str) -> Optional[BaseTool]:\n        \"\"\"Get a tool by name.\"\"\"\n        return self._tools.get(name)\n\n    def list_tools(self, enabled: Optional[list[str]] = None) -> list[BaseTool]:\n        \"\"\"List all or specified tools.\"\"\"\n        if enabled is None:\n            return list(self._tools.values())\n        return [t for name, t in self._tools.items() if name in enabled]\n\n    def get_openai_tools(self, enabled: Optional[list[str]] = None) -> list[dict]:\n        \"\"\"Get tools in OpenAI function calling format.\"\"\"\n        return [t.to_openai_tool() for t in self.list_tools(enabled)]\n\n    async def execute(\n        self,\n        tool_name: str,\n        arguments: dict[str, Any],\n        idempotency_key: Optional[str] = None,\n        timeout_ms: int = 30000,\n    ) -> ToolResult:\n        \"\"\"Execute a tool by name.\"\"\"\n\n        tool = self.get(tool_name)\n        if not tool:\n            return ToolResult(\n                success=False,\n                error=f\"Unknown tool: {tool_name}\",\n                error_type=\"unknown_tool\",\n            )\n\n        logger.info(f\"Executing tool: {tool_name}\", extra={\"arguments\": arguments})\n\n        try:\n            result = await tool.execute(\n                arguments=arguments,\n                idempotency_key=idempotency_key,\n                timeout_ms=timeout_ms,\n            )\n            logger.info(f\"Tool {tool_name} completed\", extra={\n                \"success\": result.success,\n                \"duration_ms\": result.duration_ms,\n            })\n            return result\n\n        except Exception as e:\n            logger.exception(f\"Tool {tool_name} failed unexpectedly\")\n            return ToolResult(\n                success=False,\n                error=str(e),\n                error_type=\"unexpected_error\",\n            )\n\ndef create_tool_registry(config: ChatConfig) -> ToolRegistry:\n    \"\"\"Factory function to create and populate tool registry.\"\"\"\n\n    registry = ToolRegistry()\n\n    # Register web tools\n    if config.parallel.api_key:\n        registry.register(WebSearchTool(\n            api_key=config.parallel.api_key,\n            config=config.parallel.search.model_dump(),\n        ))\n        registry.register(WebExtractTool(\n            api_key=config.parallel.api_key,\n            config=config.parallel.extract.model_dump(),\n        ))\n\n    # Register Python sandbox\n    if config.sandbox.docker.enabled:\n        registry.register(PythonSandboxTool(\n            config=config.sandbox.docker.model_dump(),\n        ))\n\n    return registry\n```\n\n---\n\n## 5. Agent Engine\n\n### State Machine\n\n```\n                              AGENT STATE MACHINE\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                                                                                  │\n│                                    ┌────────┐                                   │\n│                            ┌──────▶│COMPLETE│                                   │\n│                            │       └────────┘                                   │\n│                            │                                                     │\n│    ┌──────┐    ┌────────┐  │  ┌────────────┐    ┌───────────┐                   │\n│    │ INIT │───▶│PLANNING│──┴─▶│TOOL_CALLING│───▶│SYNTHESIZE │──────────────┐    │\n│    └──────┘    └───┬────┘     └─────┬──────┘    └───────────┘              │    │\n│                    │                │                                       │    │\n│                    │                │                                       ▼    │\n│                    │    ┌───────────┘                                  ┌────────┐│\n│                    │    │                                              │COMPLETE││\n│                    │    │    (tool result added to context)            └────────┘│\n│                    │    │                                                        │\n│                    │    │         ┌─────────────────────────────────────┐        │\n│                    └────┴────────▶│              PLANNING               │◀───────┘\n│                                   │  (loop until max_steps or no tools) │        │\n│                                   └─────────────────────────────────────┘        │\n│                                                    │                             │\n│    ┌────────────────────────────────────────────────────────────────────────┐    │\n│    │                            ERROR PATHS                                  │    │\n│    │                                                                         │    │\n│    │    Any State ────────▶ RecoverableError ────▶ Log + Continue           │    │\n│    │                                                                         │    │\n│    │    Any State ────────▶ FatalError ────────▶ ┌───────┐                  │    │\n│    │                                             │ ERROR │                  │    │\n│    │                                             └───────┘                  │    │\n│    │                                                                         │    │\n│    │    Any State ────────▶ User Cancel ───────▶ ┌─────────┐                │    │\n│    │                                             │CANCELLED│                │    │\n│    │                                             └─────────┘                │    │\n│    └────────────────────────────────────────────────────────────────────────┘    │\n│                                                                                  │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\nState Definitions:\n──────────────────\n• INIT        : Run created, context being initialized\n• PLANNING    : Model is deciding next action (call tool or synthesize)\n• TOOL_CALLING: Executing a tool, waiting for result\n• SYNTHESIZE  : Model is generating final answer with citations\n• COMPLETE    : Run finished successfully\n• ERROR       : Run failed with unrecoverable error\n• CANCELLED   : Run was cancelled by user\n```\n\n### Agent Engine Implementation\n\n```python\n# orchestrator/agent/agent_engine.py\n\nfrom dataclasses import dataclass, field\nfrom enum import Enum\nfrom typing import Optional, Callable\nimport asyncio\nimport uuid\n\nclass AgentState(str, Enum):\n    INIT = \"init\"\n    PLANNING = \"planning\"\n    TOOL_CALLING = \"tool_calling\"\n    SYNTHESIZING = \"synthesizing\"\n    COMPLETE = \"complete\"\n    ERROR = \"error\"\n    CANCELLED = \"cancelled\"\n\n@dataclass\nclass AgentContext:\n    \"\"\"Mutable context for agent execution.\"\"\"\n    run_id: str\n    conversation_id: str\n    query: str\n\n    # State\n    state: AgentState = AgentState.INIT\n    step_number: int = 0\n    max_steps: int = 10\n\n    # Accumulated data\n    messages: list[dict] = field(default_factory=list)\n    tool_results: list[dict] = field(default_factory=list)\n    citations: list[dict] = field(default_factory=list)\n    errors: list[str] = field(default_factory=list)\n\n    # Output\n    final_answer: Optional[str] = None\n\n    def add_tool_result(self, tool_call_id: str, result: ToolResult):\n        \"\"\"Add tool result to context.\"\"\"\n        self.tool_results.append({\n            \"tool_call_id\": tool_call_id,\n            \"result\": result.data,\n            \"success\": result.success,\n            \"error\": result.error,\n        })\n\n        # Add citations\n        for citation in result.citations:\n            citation[\"tool_call_id\"] = tool_call_id\n            self.citations.append(citation)\n\n        # Add to messages for model context\n        self.messages.append({\n            \"role\": \"tool\",\n            \"tool_call_id\": tool_call_id,\n            \"content\": self._format_tool_result(result),\n        })\n\n    def _format_tool_result(self, result: ToolResult) -> str:\n        \"\"\"Format tool result for model context.\"\"\"\n        if result.success:\n            return json.dumps(result.data, indent=2)\n        else:\n            return f\"Error: {result.error}\"\n\n@dataclass\nclass AgentResult:\n    \"\"\"Final result of agent execution.\"\"\"\n    run_id: str\n    status: str\n    final_answer: Optional[str]\n    citations: list[dict]\n    steps: int\n    total_tool_calls: int\n    error: Optional[str] = None\n\nclass RecoverableError(Exception):\n    \"\"\"Error that can be recovered from by continuing to next step.\"\"\"\n    pass\n\nclass FatalError(Exception):\n    \"\"\"Error that requires stopping the agent.\"\"\"\n    pass\n\nclass AgentEngine:\n    \"\"\"Main agent orchestration engine.\"\"\"\n\n    def __init__(\n        self,\n        provider_chain: ModelProviderChain,\n        tool_registry: ToolRegistry,\n        agent_repo: AgentRepo,\n        config: AgentConfig,\n    ):\n        self.provider_chain = provider_chain\n        self.tools = tool_registry\n        self.repo = agent_repo\n        self.config = config\n\n    async def run(\n        self,\n        conversation_id: str,\n        query: str,\n        run_id: Optional[str] = None,\n        event_callback: Optional[Callable[[dict], None]] = None,\n        max_steps: int = 10,\n    ) -> AgentResult:\n        \"\"\"Execute the agent loop.\"\"\"\n\n        # Initialize or restore context\n        context = await self._init_context(\n            conversation_id=conversation_id,\n            query=query,\n            run_id=run_id,\n            max_steps=max_steps,\n        )\n\n        self._emit_event(event_callback, \"agent_state\", {\n            \"state\": context.state.value,\n            \"step\": context.step_number,\n        })\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(context.run_id):\n                    return await self._finalize(context, AgentState.CANCELLED, event_callback)\n\n                # Update heartbeat for crash detection\n                await self._update_heartbeat(context.run_id)\n\n                context.step_number += 1\n                context.state = AgentState.PLANNING\n\n                self._emit_event(event_callback, \"step_start\", {\n                    \"step\": context.step_number,\n                    \"state\": context.state.value,\n                })\n\n                # Create step record\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model with tools\n                    response = await self._call_model(context, event_callback)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING: Execute tools sequentially\n                        context.state = AgentState.TOOL_CALLING\n\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool(\n                                context, step, tool_call, event_callback\n                            )\n                            context.add_tool_result(tool_call[\"id\"], result)\n\n                        # Continue to next planning step\n                        await self._complete_step(step, \"call_tool\")\n\n                    else:\n                        # SYNTHESIZING: Model has final answer\n                        context.state = AgentState.SYNTHESIZING\n                        context.final_answer = response.text\n\n                        # Stream answer to UI\n                        self._emit_event(event_callback, \"answer\", {\n                            \"content\": response.text,\n                            \"streaming\": False,\n                        })\n\n                        # Mark used citations\n                        await self._mark_used_citations(context)\n                        await self._complete_step(step, \"synthesize\")\n\n                        return await self._finalize(context, AgentState.COMPLETE, event_callback)\n\n                except RecoverableError as e:\n                    logger.warning(f\"Recoverable error in step {context.step_number}: {e}\")\n                    context.errors.append(str(e))\n                    await self._record_step_error(step, e, recoverable=True)\n                    # Continue to next step\n\n                except FatalError as e:\n                    logger.error(f\"Fatal error in step {context.step_number}: {e}\")\n                    await self._record_step_error(step, e, recoverable=False)\n                    return await self._finalize(context, AgentState.ERROR, event_callback, str(e))\n\n            # Max steps reached - force synthesis\n            logger.warning(f\"Max steps ({context.max_steps}) reached, forcing synthesis\")\n            return await self._force_synthesis(context, event_callback)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {context.run_id}\")\n            return await self._finalize(context, AgentState.ERROR, event_callback, str(e))\n\n    async def _call_model(\n        self,\n        context: AgentContext,\n        event_callback: Optional[Callable],\n    ) -> LLMResponse:\n        \"\"\"Call the model with current context and tools.\"\"\"\n\n        # Build system prompt\n        system_prompt = self._build_system_prompt(context)\n\n        messages = [\n            {\"role\": \"system\", \"content\": system_prompt},\n            {\"role\": \"user\", \"content\": context.query},\n            *context.messages,  # Previous assistant/tool messages\n        ]\n\n        # Emit thinking event\n        self._emit_event(event_callback, \"thinking\", {\n            \"content\": \"Analyzing query and deciding next action...\",\n        })\n\n        try:\n            response = await self.provider_chain.complete(\n                messages=messages,\n                tools=self.tools.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n\n            # Emit model reasoning if present\n            if response.reasoning:\n                self._emit_event(event_callback, \"thinking\", {\n                    \"content\": response.reasoning,\n                })\n\n            # Add assistant message to context\n            if response.tool_calls:\n                context.messages.append({\n                    \"role\": \"assistant\",\n                    \"content\": None,\n                    \"tool_calls\": response.tool_calls,\n                })\n            else:\n                context.messages.append({\n                    \"role\": \"assistant\",\n                    \"content\": response.text,\n                })\n\n            return response\n\n        except AllProvidersFailedError as e:\n            raise FatalError(f\"All model providers unavailable: {e}\")\n\n        except RateLimitError as e:\n            # Could retry, but for now treat as recoverable\n            raise RecoverableError(f\"Rate limited: {e}\")\n\n    async def _execute_tool(\n        self,\n        context: AgentContext,\n        step: AgentStep,\n        tool_call: dict,\n        event_callback: Optional[Callable],\n    ) -> ToolResult:\n        \"\"\"Execute a single tool call with full lifecycle tracking.\"\"\"\n\n        tool_name = tool_call[\"function\"][\"name\"]\n        arguments = json.loads(tool_call[\"function\"][\"arguments\"])\n        tool_call_id = tool_call[\"id\"]\n\n        # Create tool record BEFORE execution (write-ahead)\n        idempotency_key = str(uuid.uuid4())\n        tool_record = await self.repo.create_tool_call(\n            run_id=context.run_id,\n            step_id=step.id,\n            tool_name=tool_name,\n            arguments=arguments,\n            idempotency_key=idempotency_key,\n        )\n\n        self._emit_event(event_callback, \"tool_start\", {\n            \"tool_call_id\": tool_call_id,\n            \"tool_name\": tool_name,\n            \"arguments\": arguments,\n        })\n\n        try:\n            # Update status to running\n            await self.repo.update_tool_call(tool_record.id, status=\"running\")\n\n            # Execute the tool\n            result = await self.tools.execute(\n                tool_name=tool_name,\n                arguments=arguments,\n                idempotency_key=idempotency_key,\n            )\n\n            # Save result\n            await self.repo.update_tool_call(\n                tool_record.id,\n                status=\"success\" if result.success else \"error\",\n                result_summary=self._summarize_result(result),\n                result_raw=json.dumps(result.data) if result.data else None,\n                error_message=result.error,\n                duration_ms=result.duration_ms,\n            )\n\n            # Save citations\n            for citation in result.citations:\n                await self.repo.create_citation(\n                    run_id=context.run_id,\n                    tool_call_id=tool_record.id,\n                    source_url=citation[\"source_url\"],\n                    title=citation.get(\"title\"),\n                    snippet=citation[\"snippet\"],\n                )\n\n            self._emit_event(event_callback, \"tool_result\", {\n                \"tool_call_id\": tool_call_id,\n                \"tool_name\": tool_name,\n                \"success\": result.success,\n                \"summary\": self._summarize_result(result),\n                \"citation_count\": len(result.citations),\n            })\n\n            # Emit citations\n            for citation in result.citations:\n                self._emit_event(event_callback, \"citation\", citation)\n\n            return result\n\n        except Exception as e:\n            await self.repo.update_tool_call(\n                tool_record.id,\n                status=\"error\",\n                error_message=str(e),\n            )\n            raise RecoverableError(f\"Tool {tool_name} failed: {e}\")\n\n    def _build_system_prompt(self, context: AgentContext) -> str:\n        \"\"\"Build system prompt for the agent.\"\"\"\n        return f\"\"\"You are a research assistant that helps users find accurate, up-to-date information.\n\nYou have access to the following tools:\n- web_search: Search the web for current information\n- web_extract: Extract detailed content from specific URLs\n- python_execute: Run Python code for calculations\n\nIMPORTANT GUIDELINES:\n1. Use web_search first to find relevant sources\n2. Use web_extract to get detailed information from promising URLs\n3. Use python_execute for any calculations or data processing\n4. Always cite your sources using [cite_N] notation\n5. Only include information you can verify from search results\n6. If you cannot find reliable information, say so\n\nCurrent step: {context.step_number} of {context.max_steps}\nCitations collected so far: {len(context.citations)}\n\nWhen you have enough information to answer the query, provide your response WITHOUT calling any tools.\nInclude [cite_1], [cite_2], etc. to reference the sources.\"\"\"\n\n    def _summarize_result(self, result: ToolResult) -> str:\n        \"\"\"Create brief summary of tool result for UI.\"\"\"\n        if not result.success:\n            return f\"Error: {result.error}\"\n\n        if result.data:\n            if \"result_count\" in result.data:\n                return f\"Found {result.data['result_count']} results\"\n            if \"stdout\" in result.data:\n                output = result.data[\"stdout\"][:200]\n                return f\"Output: {output}...\"\n            if \"results\" in result.data:\n                return f\"Extracted {len(result.data['results'])} pages\"\n\n        return \"Completed successfully\"\n\n    def _emit_event(self, callback: Optional[Callable], event_type: str, data: dict):\n        \"\"\"Emit event to callback if provided.\"\"\"\n        if callback:\n            callback({\n                \"type\": event_type,\n                \"timestamp\": datetime.now().isoformat(),\n                **data,\n            })\n\n    async def _finalize(\n        self,\n        context: AgentContext,\n        state: AgentState,\n        event_callback: Optional[Callable],\n        error: Optional[str] = None,\n    ) -> AgentResult:\n        \"\"\"Finalize the run and return result.\"\"\"\n\n        # Update run in database\n        await self.repo.update_run(\n            context.run_id,\n            status=\"succeeded\" if state == AgentState.COMPLETE else state.value,\n            agent_state=state.value,\n            final_answer=context.final_answer,\n            error_message=error,\n        )\n\n        # Emit completion event\n        self._emit_event(event_callback, state.value, {\n            \"run_id\": context.run_id,\n            \"final_answer\": context.final_answer,\n            \"citation_count\": len(context.citations),\n            \"step_count\": context.step_number,\n            \"error\": error,\n        })\n\n        return AgentResult(\n            run_id=context.run_id,\n            status=state.value,\n            final_answer=context.final_answer,\n            citations=context.citations,\n            steps=context.step_number,\n            total_tool_calls=len(context.tool_results),\n            error=error,\n        )\n```\n\n---\n\n## 6. Data Model\n\n### Complete Database Schema\n\n```sql\n-- =============================================================================\n-- AGENT TABLES\n-- =============================================================================\n\n-- Extended runs table (add columns to existing)\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;\n\n-- Agent steps - one row per planning/execution cycle\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State tracking\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,   -- FK to trace_events\n    model_response_event_id TEXT,  -- FK to trace_events\n    thinking_text TEXT,            -- Model's reasoning for this step\n\n    -- Decision outcome\n    decision TEXT,        -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,    -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_agent_steps_run ON agent_steps(run_id);\nCREATE INDEX idx_agent_steps_state ON agent_steps(state);\n\n-- Agent tool calls - one row per tool execution\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool identification\n    tool_name TEXT NOT NULL,    -- web_search | web_extract | python_execute\n    arguments TEXT NOT NULL,    -- JSON of tool arguments\n\n    -- Execution tracking\n    status TEXT NOT NULL,       -- pending | running | success | error | timeout\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result storage\n    result_summary TEXT,        -- Brief summary for UI\n    result_raw TEXT,            -- Full result (backend only, not sent to UI)\n    error_message TEXT,\n    error_type TEXT,            -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\nCREATE INDEX idx_tool_calls_step ON agent_tool_calls(step_id);\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\n\n-- Agent citations - one row per citation extracted\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Citation content\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    -- Usage tracking\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\nCREATE INDEX idx_citations_tool_call ON agent_citations(tool_call_id);\n```\n\n### Entity Relationships\n\n```\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                           ENTITY RELATIONSHIP DIAGRAM                           │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\n┌──────────────┐       ┌──────────────┐       ┌───────────────┐\n│conversations │──────<│    runs      │──────<│  agent_steps  │\n│              │  1:N  │              │  1:N  │               │\n│ • id         │       │ • id         │       │ • id          │\n│ • title      │       │ • conv_id    │       │ • run_id      │\n│ • created_at │       │ • mode       │       │ • step_number │\n│              │       │ • status     │       │ • state       │\n│              │       │ • agent_state│       │ • decision    │\n│              │       │ • final_ans  │       │ • thinking    │\n└──────────────┘       └──────┬───────┘       └───────┬───────┘\n                              │                       │\n                              │                       │ 1:N\n                              │                       ▼\n                              │               ┌───────────────┐\n                              │               │agent_tool_calls│\n                              │               │               │\n                              │        1:N    │ • id          │\n                              └──────────────<│ • step_id     │\n                                              │ • tool_name   │\n                                              │ • arguments   │\n                                              │ • status      │\n                                              │ • result      │\n                                              └───────┬───────┘\n                                                      │\n                                                      │ 1:N\n                                                      ▼\n                                              ┌───────────────┐\n                                              │agent_citations│\n                                              │               │\n                                              │ • id          │\n                                              │ • tool_call_id│\n                                              │ • source_url  │\n                                              │ • title       │\n                                              │ • snippet     │\n                                              │ • used        │\n                                              └───────────────┘\n\nAlso linked to existing trace_events table:\n┌──────────────┐\n│ trace_events │\n│              │\n│ • id         │\n│ • run_id     │\n│ • seq        │\n│ • event_type │ ← llm_request, llm_response, tool_call, tool_response\n│ • content    │\n│ • duration   │\n└──────────────┘\n```\n\n### Pydantic Models\n\n```python\n# orchestrator/schemas.py (additions)\n\nfrom enum import Enum\nfrom typing import Optional\nfrom pydantic import BaseModel\n\nclass AgentState(str, Enum):\n    INIT = \"init\"\n    PLANNING = \"planning\"\n    TOOL_CALLING = \"tool_calling\"\n    SYNTHESIZING = \"synthesizing\"\n    COMPLETE = \"complete\"\n    ERROR = \"error\"\n    CANCELLED = \"cancelled\"\n\nclass ToolCallStatus(str, Enum):\n    PENDING = \"pending\"\n    RUNNING = \"running\"\n    SUCCESS = \"success\"\n    ERROR = \"error\"\n    TIMEOUT = \"timeout\"\n\nclass Citation(BaseModel):\n    id: str\n    source_url: str\n    title: Optional[str]\n    snippet: str\n    tool_call_id: str\n    used_in_answer: bool = False\n\nclass ToolCallRecord(BaseModel):\n    id: str\n    tool_name: str\n    arguments: dict\n    status: ToolCallStatus\n    result_summary: Optional[str] = None\n    error_message: Optional[str] = None\n    duration_ms: Optional[int] = None\n    citations: list[Citation] = []\n\nclass AgentStep(BaseModel):\n    id: str\n    step_number: int\n    state: str\n    thinking_text: Optional[str] = None\n    decision: Optional[str] = None\n    tool_calls: list[ToolCallRecord] = []\n    error_message: Optional[str] = None\n\nclass CreateAgentRunRequest(BaseModel):\n    query: str\n    max_steps: int = 10\n\nclass AgentRunResponse(BaseModel):\n    run_id: str\n    status: str\n    agent_state: Optional[AgentState]\n    final_answer: Optional[str]\n    steps: list[AgentStep]\n    citations: list[Citation]\n    error: Optional[str] = None\n```\n\n---\n\n## 7. API Design\n\n### Endpoint Summary\n\n| Endpoint | Method | Description |\n|----------|--------|-------------|\n| `/api/agent/conversations/{id}/runs` | POST | Create new agent run |\n| `/api/agent/runs/{id}` | GET | Get run details |\n| `/api/agent/runs/{id}/stream` | GET | SSE stream of events |\n| `/api/agent/runs/{id}/cancel` | POST | Cancel running agent |\n| `/api/agent/runs/{id}/resume` | POST | Resume from crash |\n| `/api/agent/runs/{id}/steps` | GET | Get step history |\n| `/api/agent/runs/{id}/citations` | GET | Get all citations |\n\n### Route Implementation\n\n```python\n# orchestrator/routes/agent.py\n\nfrom fastapi import APIRouter, HTTPException, Query, BackgroundTasks\nfrom sse_starlette.sse import EventSourceResponse\n\nrouter = APIRouter(prefix=\"/api/agent\", tags=[\"agent\"])\n\n# Active run queues (in-memory, single instance)\n_active_queues: dict[str, asyncio.Queue] = {}\n_cancel_signals: dict[str, asyncio.Event] = {}\n\n@router.post(\"/conversations/{conversation_id}/runs\")\nasync def create_agent_run(\n    conversation_id: str,\n    request: CreateAgentRunRequest,\n    background_tasks: BackgroundTasks,\n):\n    \"\"\"Create and start an agent research run.\"\"\"\n\n    db = await get_db()\n    conv_repo = ConversationRepo(db)\n    agent_repo = AgentRepo(db)\n\n    # Verify conversation exists\n    conversation = await conv_repo.get(conversation_id)\n    if not conversation:\n        raise HTTPException(status_code=404, detail=\"Conversation not found\")\n\n    # Create run record\n    run_id = str(uuid.uuid4())\n    await agent_repo.create_run(\n        run_id=run_id,\n        conversation_id=conversation_id,\n        mode=\"agent\",\n        user_message=request.query,\n        max_steps=request.max_steps,\n    )\n\n    # Create event queue\n    event_queue = asyncio.Queue(maxsize=200)\n    _active_queues[run_id] = event_queue\n    _cancel_signals[run_id] = asyncio.Event()\n\n    # Start agent in background\n    async def run_agent():\n        config = get_chat_config()\n        engine = AgentEngine(\n            provider_chain=create_provider_chain(config),\n            tool_registry=create_tool_registry(config),\n            agent_repo=agent_repo,\n            config=config.agent,\n        )\n\n        def event_callback(event: dict):\n            try:\n                event_queue.put_nowait(event)\n            except asyncio.QueueFull:\n                logger.warning(f\"Event queue full for run {run_id}\")\n\n        try:\n            result = await engine.run(\n                conversation_id=conversation_id,\n                query=request.query,\n                run_id=run_id,\n                event_callback=event_callback,\n                max_steps=request.max_steps,\n            )\n\n            # Final event\n            event_queue.put_nowait({\n                \"type\": \"complete\",\n                \"run_id\": run_id,\n                \"status\": result.status,\n                \"final_answer\": result.final_answer,\n            })\n\n        except Exception as e:\n            logger.exception(f\"Agent run {run_id} failed\")\n            event_queue.put_nowait({\n                \"type\": \"error\",\n                \"run_id\": run_id,\n                \"error\": str(e),\n            })\n\n        finally:\n            # Cleanup after delay (for late SSE subscribers)\n            await asyncio.sleep(5)\n            _active_queues.pop(run_id, None)\n            _cancel_signals.pop(run_id, None)\n\n    background_tasks.add_task(run_agent)\n\n    return {\n        \"run_id\": run_id,\n        \"stream_url\": f\"/api/agent/runs/{run_id}/stream\",\n    }\n\n@router.get(\"/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events via Server-Sent Events.\"\"\"\n\n    db = await get_db()\n    agent_repo = AgentRepo(db)\n\n    async def event_generator():\n        seq = since_seq\n\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await agent_repo.get_events_since(run_id, since_seq)\n            for event in missed_events:\n                seq = event[\"seq\"]\n                yield {\n                    \"event\": event[\"type\"],\n                    \"data\": json.dumps(event),\n                }\n\n        # Check if run is already complete\n        run = await agent_repo.get_run(run_id)\n        if run and run[\"status\"] in (\"succeeded\", \"failed\", \"cancelled\"):\n            yield {\n                \"event\": \"complete\",\n                \"data\": json.dumps({\n                    \"run_id\": run_id,\n                    \"status\": run[\"status\"],\n                    \"final_answer\": run.get(\"final_answer\"),\n                }),\n            }\n            return\n\n        # Stream live events\n        queue = _active_queues.get(run_id)\n        if not queue:\n            yield {\n                \"event\": \"error\",\n                \"data\": json.dumps({\"error\": \"Run not found or already complete\"}),\n            }\n            return\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                seq += 1\n                event[\"seq\"] = seq\n\n                yield {\n                    \"event\": event[\"type\"],\n                    \"data\": json.dumps(event),\n                }\n\n                if event[\"type\"] in (\"complete\", \"error\", \"cancelled\"):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat\n                yield {\n                    \"event\": \"heartbeat\",\n                    \"data\": json.dumps({\"seq\": seq}),\n                }\n\n    return EventSourceResponse(event_generator())\n\n@router.post(\"/runs/{run_id}/cancel\")\nasync def cancel_agent_run(run_id: str):\n    \"\"\"Cancel a running agent.\"\"\"\n\n    if run_id not in _active_queues:\n        raise HTTPException(status_code=404, detail=\"Run not found or already complete\")\n\n    # Signal cancellation\n    if run_id in _cancel_signals:\n        _cancel_signals[run_id].set()\n\n    # Notify via queue\n    queue = _active_queues.get(run_id)\n    if queue:\n        queue.put_nowait({\n            \"type\": \"cancelled\",\n            \"run_id\": run_id,\n        })\n\n    return {\"status\": \"cancelling\", \"run_id\": run_id}\n\n@router.get(\"/runs/{run_id}\")\nasync def get_agent_run(run_id: str):\n    \"\"\"Get agent run details.\"\"\"\n\n    db = await get_db()\n    agent_repo = AgentRepo(db)\n\n    run = await agent_repo.get_run(run_id)\n    if not run:\n        raise HTTPException(status_code=404, detail=\"Run not found\")\n\n    steps = await agent_repo.get_steps(run_id)\n    citations = await agent_repo.get_citations(run_id)\n\n    return AgentRunResponse(\n        run_id=run_id,\n        status=run[\"status\"],\n        agent_state=run.get(\"agent_state\"),\n        final_answer=run.get(\"final_answer\"),\n        steps=steps,\n        citations=citations,\n        error=run.get(\"error_message\"),\n    )\n\n@router.get(\"/runs/{run_id}/citations\")\nasync def get_run_citations(run_id: str):\n    \"\"\"Get all citations from a run.\"\"\"\n\n    db = await get_db()\n    agent_repo = AgentRepo(db)\n\n    citations = await agent_repo.get_citations(run_id)\n    return {\"citations\": citations}\n```\n\n---\n\n## 8. SSE & Streaming\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State transitions\n    AGENT_STATE = \"agent_state\"       # Agent state changed\n    STEP_START = \"step_start\"         # New step beginning\n    STEP_COMPLETE = \"step_complete\"   # Step finished\n\n    # Tool lifecycle\n    TOOL_START = \"tool_start\"         # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"   # Progress update (optional)\n    TOOL_RESULT = \"tool_result\"       # Tool completed\n\n    # Content\n    THINKING = \"thinking\"             # Model reasoning\n    ANSWER = \"answer\"                 # Final answer (may stream)\n    CITATION = \"citation\"             # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"             # Run finished successfully\n    ERROR = \"error\"                   # Run failed\n    CANCELLED = \"cancelled\"           # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"           # Keep-alive ping\n```\n\n### Event Payloads\n\n```typescript\n// All events have these common fields\ninterface BaseEvent {\n  type: SSEEventType;\n  seq: number;           // Monotonic sequence for resumption\n  timestamp: string;     // ISO timestamp\n  run_id: string;\n}\n\n// Specific event payloads\ninterface StepStartEvent extends BaseEvent {\n  type: \"step_start\";\n  step: number;\n  state: \"planning\" | \"tool_calling\";\n}\n\ninterface ToolStartEvent extends BaseEvent {\n  type: \"tool_start\";\n  tool_call_id: string;\n  tool_name: string;\n  arguments: Record<string, unknown>;\n}\n\ninterface ToolResultEvent extends BaseEvent {\n  type: \"tool_result\";\n  tool_call_id: string;\n  tool_name: string;\n  success: boolean;\n  summary: string;        // Brief summary for UI\n  citation_count: number;\n  // NOTE: Full result NOT sent to UI\n}\n\ninterface CitationEvent extends BaseEvent {\n  type: \"citation\";\n  id: string;            // cite_1, cite_2, etc.\n  source_url: string;\n  title?: string;\n  snippet: string;       // The relevant text\n}\n\ninterface ThinkingEvent extends BaseEvent {\n  type: \"thinking\";\n  content: string;       // Model's reasoning\n}\n\ninterface AnswerEvent extends BaseEvent {\n  type: \"answer\";\n  content: string;       // May be partial if streaming\n  streaming: boolean;\n}\n\ninterface CompleteEvent extends BaseEvent {\n  type: \"complete\";\n  status: \"succeeded\" | \"failed\" | \"cancelled\";\n  final_answer?: string;\n  citation_count: number;\n  step_count: number;\n  error?: string;\n}\n```\n\n### Frontend SSE Hook with Reconnection\n\n```typescript\n// ui/src/hooks/useAgentSSE.ts\n\nimport { useEffect, useRef, useState, useCallback } from 'react';\nimport { useStore } from './useStore';\n\ninterface UseAgentSSEOptions {\n  onComplete?: (data: CompleteEvent) => void;\n  onError?: (error: string) => void;\n}\n\nexport function useAgentSSE(runId: string | null, options: UseAgentSSEOptions = {}) {\n  const [connected, setConnected] = useState(false);\n  const lastSeqRef = useRef(0);\n  const reconnectAttemptsRef = useRef(0);\n  const eventSourceRef = useRef<EventSource | null>(null);\n\n  const {\n    addAgentStep,\n    updateToolCall,\n    addCitation,\n    setAgentState,\n    appendThinking,\n    setFinalAnswer,\n  } = useStore();\n\n  const connect = useCallback(() => {\n    if (!runId) return;\n\n    const url = `/api/agent/runs/${runId}/stream?since_seq=${lastSeqRef.current}`;\n    const eventSource = new EventSource(url);\n    eventSourceRef.current = eventSource;\n\n    eventSource.onopen = () => {\n      setConnected(true);\n      reconnectAttemptsRef.current = 0;\n    };\n\n    // Handle different event types\n    eventSource.addEventListener('step_start', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      addAgentStep(runId, {\n        stepNumber: data.step,\n        state: data.state,\n        toolCalls: [],\n      });\n    });\n\n    eventSource.addEventListener('tool_start', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      updateToolCall(runId, data.tool_call_id, {\n        name: data.tool_name,\n        arguments: data.arguments,\n        status: 'running',\n      });\n    });\n\n    eventSource.addEventListener('tool_result', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      updateToolCall(runId, data.tool_call_id, {\n        status: data.success ? 'success' : 'error',\n        summary: data.summary,\n      });\n    });\n\n    eventSource.addEventListener('citation', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      addCitation(runId, {\n        id: data.id,\n        sourceUrl: data.source_url,\n        title: data.title,\n        snippet: data.snippet,\n      });\n    });\n\n    eventSource.addEventListener('thinking', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      appendThinking(runId, data.content);\n    });\n\n    eventSource.addEventListener('answer', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      setFinalAnswer(runId, data.content, data.streaming);\n    });\n\n    eventSource.addEventListener('complete', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      setAgentState(runId, 'complete');\n      options.onComplete?.(data);\n      eventSource.close();\n    });\n\n    eventSource.addEventListener('error', (e) => {\n      const data = JSON.parse(e.data);\n      lastSeqRef.current = data.seq;\n      setAgentState(runId, 'error');\n      options.onError?.(data.error);\n      eventSource.close();\n    });\n\n    eventSource.addEventListener('heartbeat', (e) => {\n      const data = JSON.parse(e.data);\n      // Update seq but don't process\n    });\n\n    eventSource.onerror = () => {\n      setConnected(false);\n      eventSource.close();\n\n      // Reconnect with exponential backoff\n      if (reconnectAttemptsRef.current < 5) {\n        const delay = Math.pow(2, reconnectAttemptsRef.current) * 1000;\n        reconnectAttemptsRef.current++;\n\n        setTimeout(() => {\n          connect();\n        }, delay);\n      } else {\n        // Give up, poll for final state\n        pollFinalState(runId);\n      }\n    };\n  }, [runId, addAgentStep, updateToolCall, addCitation, setAgentState, appendThinking, setFinalAnswer, options]);\n\n  const pollFinalState = async (runId: string) => {\n    try {\n      const response = await fetch(`/api/agent/runs/${runId}`);\n      const data = await response.json();\n\n      if (data.status === 'succeeded') {\n        setFinalAnswer(runId, data.final_answer, false);\n        setAgentState(runId, 'complete');\n        options.onComplete?.(data);\n      } else if (data.status === 'failed') {\n        setAgentState(runId, 'error');\n        options.onError?.(data.error);\n      }\n    } catch (e) {\n      console.error('Failed to poll final state:', e);\n    }\n  };\n\n  useEffect(() => {\n    connect();\n\n    return () => {\n      eventSourceRef.current?.close();\n    };\n  }, [connect]);\n\n  const disconnect = useCallback(() => {\n    eventSourceRef.current?.close();\n    setConnected(false);\n  }, []);\n\n  return { connected, disconnect };\n}\n```\n\n---\n\n## 9. Frontend Architecture\n\n### Component Hierarchy\n\n```\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                          FRONTEND COMPONENT TREE                                 │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\nApp\n├── AppLayout\n│   ├── Sidebar\n│   │   └── ConversationList\n│   │\n│   ├── MainContent\n│   │   └── ConversationView\n│   │       ├── MessageList\n│   │       │   ├── UserMessage\n│   │       │   └── AgentRunMessage          ◄── NEW\n│   │       │       ├── AgentThinkingPanel   ◄── NEW\n│   │       │       │   ├── StepCard\n│   │       │       │   │   └── ToolCallCard ◄── NEW\n│   │       │       │   └── StateIndicator\n│   │       │       │\n│   │       │       └── AnswerWithCitations  ◄── NEW\n│   │       │           ├── Markdown\n│   │       │           └── CitationInline   ◄── NEW\n│   │       │\n│   │       └── InputArea\n│   │           └── ModeSelector (chat/agent)\n│   │\n│   └── DetailPanel\n│       └── TraceViewer\n│           └── CitationList\n```\n\n### Key Components\n\n#### AgentThinkingPanel\n\n```tsx\n// ui/src/components/AgentThinkingPanel.tsx\n\ninterface AgentThinkingPanelProps {\n  steps: AgentStep[];\n  currentState: AgentState;\n  thinking: string;\n  isStreaming: boolean;\n}\n\nexport function AgentThinkingPanel({\n  steps,\n  currentState,\n  thinking,\n  isStreaming,\n}: AgentThinkingPanelProps) {\n  return (\n    <div className=\"agent-thinking-panel border rounded-lg p-4 bg-gray-50\">\n      {/* State indicator */}\n      <div className=\"flex items-center gap-2 mb-4\">\n        <StateIndicator state={currentState} />\n        <span className=\"text-sm text-gray-600\">\n          Step {steps.length} of max 10\n        </span>\n      </div>\n\n      {/* Current thinking */}\n      {thinking && (\n        <div className=\"mb-4 p-3 bg-white rounded border-l-4 border-blue-400\">\n          <div className=\"text-xs text-gray-500 mb-1\">Thinking</div>\n          <div className=\"text-sm whitespace-pre-wrap\">{thinking}</div>\n          {isStreaming && <span className=\"animate-pulse\">▌</span>}\n        </div>\n      )}\n\n      {/* Steps timeline */}\n      <div className=\"space-y-3\">\n        {steps.map((step) => (\n          <StepCard key={step.id} step={step} />\n        ))}\n      </div>\n    </div>\n  );\n}\n\nfunction StepCard({ step }: { step: AgentStep }) {\n  return (\n    <div className=\"border rounded p-3 bg-white\">\n      <div className=\"flex items-center gap-2 mb-2\">\n        <span className=\"text-xs font-medium text-gray-500\">\n          Step {step.stepNumber}\n        </span>\n        <StepStateChip state={step.state} />\n      </div>\n\n      {/* Tool calls in this step */}\n      {step.toolCalls.map((toolCall) => (\n        <ToolCallCard key={toolCall.id} toolCall={toolCall} />\n      ))}\n    </div>\n  );\n}\n```\n\n#### ToolCallCard\n\n```tsx\n// ui/src/components/ToolCallCard.tsx\n\ninterface ToolCallCardProps {\n  toolCall: ToolCallRecord;\n}\n\nexport function ToolCallCard({ toolCall }: ToolCallCardProps) {\n  const [expanded, setExpanded] = useState(false);\n\n  const icon = {\n    web_search: <SearchIcon />,\n    web_extract: <FileTextIcon />,\n    python_execute: <CodeIcon />,\n  }[toolCall.name];\n\n  const statusColor = {\n    pending: 'bg-gray-200',\n    running: 'bg-blue-200 animate-pulse',\n    success: 'bg-green-200',\n    error: 'bg-red-200',\n    timeout: 'bg-yellow-200',\n  }[toolCall.status];\n\n  return (\n    <div className={`border rounded p-2 ${statusColor}`}>\n      <div\n        className=\"flex items-center gap-2 cursor-pointer\"\n        onClick={() => setExpanded(!expanded)}\n      >\n        {icon}\n        <span className=\"font-medium text-sm\">{toolCall.name}</span>\n        <span className=\"text-xs text-gray-500 ml-auto\">\n          {toolCall.durationMs ? `${toolCall.durationMs}ms` : '...'}\n        </span>\n        <ChevronIcon direction={expanded ? 'up' : 'down'} />\n      </div>\n\n      {expanded && (\n        <div className=\"mt-2 pt-2 border-t text-sm\">\n          {/* Arguments */}\n          <div className=\"mb-2\">\n            <span className=\"text-xs text-gray-500\">Arguments:</span>\n            <pre className=\"text-xs bg-gray-100 p-1 rounded mt-1 overflow-auto\">\n              {JSON.stringify(toolCall.arguments, null, 2)}\n            </pre>\n          </div>\n\n          {/* Result summary */}\n          {toolCall.resultSummary && (\n            <div>\n              <span className=\"text-xs text-gray-500\">Result:</span>\n              <p className=\"text-sm mt-1\">{toolCall.resultSummary}</p>\n            </div>\n          )}\n\n          {/* Error */}\n          {toolCall.errorMessage && (\n            <div className=\"text-red-600 text-sm mt-1\">\n              Error: {toolCall.errorMessage}\n            </div>\n          )}\n\n          {/* Citation count */}\n          {toolCall.citations.length > 0 && (\n            <div className=\"text-xs text-gray-500 mt-1\">\n              {toolCall.citations.length} citations extracted\n            </div>\n          )}\n        </div>\n      )}\n    </div>\n  );\n}\n```\n\n#### AnswerWithCitations\n\n```tsx\n// ui/src/components/AnswerWithCitations.tsx\n\ninterface AnswerWithCitationsProps {\n  content: string;\n  citations: Citation[];\n  isStreaming: boolean;\n}\n\nexport function AnswerWithCitations({\n  content,\n  citations,\n  isStreaming,\n}: AnswerWithCitationsProps) {\n  const citationMap = useMemo(\n    () => new Map(citations.map((c) => [c.id, c])),\n    [citations]\n  );\n\n  // Replace [cite_N] with interactive components\n  const processedContent = useMemo(() => {\n    return content.replace(/\\[cite_(\\d+)\\]/g, (match, num) => {\n      const citation = citationMap.get(`cite_${num}`);\n      if (citation) {\n        return `<citation id=\"cite_${num}\" />`;\n      }\n      return match;\n    });\n  }, [content, citationMap]);\n\n  return (\n    <div className=\"answer-with-citations\">\n      <ReactMarkdown\n        components={{\n          // Custom renderer for citation placeholders\n          citation: ({ id }) => {\n            const citation = citationMap.get(id);\n            if (!citation) return `[${id}]`;\n            return <CitationInline citation={citation} />;\n          },\n        }}\n      >\n        {processedContent}\n      </ReactMarkdown>\n\n      {isStreaming && <span className=\"animate-pulse\">▌</span>}\n\n      {/* Citation list at bottom */}\n      {citations.length > 0 && (\n        <div className=\"mt-6 pt-4 border-t\">\n          <h4 className=\"text-sm font-medium text-gray-500 mb-2\">Sources</h4>\n          <ol className=\"list-decimal list-inside space-y-1 text-sm\">\n            {citations.map((citation) => (\n              <li key={citation.id}>\n                <a\n                  href={citation.sourceUrl}\n                  target=\"_blank\"\n                  rel=\"noopener noreferrer\"\n                  className=\"text-blue-600 hover:underline\"\n                >\n                  {citation.title || citation.sourceUrl}\n                </a>\n              </li>\n            ))}\n          </ol>\n        </div>\n      )}\n    </div>\n  );\n}\n```\n\n#### CitationInline\n\n```tsx\n// ui/src/components/CitationInline.tsx\n\ninterface CitationInlineProps {\n  citation: Citation;\n}\n\nexport function CitationInline({ citation }: CitationInlineProps) {\n  const [showTooltip, setShowTooltip] = useState(false);\n\n  // Extract number from cite_N\n  const num = citation.id.replace('cite_', '');\n\n  return (\n    <span className=\"relative inline\">\n      <button\n        className=\"inline-flex items-center justify-center w-5 h-5 text-xs\n                   bg-blue-100 text-blue-700 rounded hover:bg-blue-200\n                   font-medium cursor-pointer\"\n        onMouseEnter={() => setShowTooltip(true)}\n        onMouseLeave={() => setShowTooltip(false)}\n        onClick={() => window.open(citation.sourceUrl, '_blank')}\n      >\n        {num}\n      </button>\n\n      {showTooltip && (\n        <div className=\"absolute z-50 bottom-full left-0 mb-2 w-72 p-3\n                        bg-white border rounded-lg shadow-lg\">\n          <div className=\"text-sm font-medium text-gray-900 mb-1\">\n            {citation.title || 'Source'}\n          </div>\n          <div className=\"text-xs text-gray-500 mb-2 truncate\">\n            {citation.sourceUrl}\n          </div>\n          <div className=\"text-sm text-gray-700 line-clamp-3\">\n            \"{citation.snippet}\"\n          </div>\n        </div>\n      )}\n    </span>\n  );\n}\n```\n\n### Zustand Store Extensions\n\n```typescript\n// ui/src/hooks/useStore.ts (agent additions)\n\ninterface AgentSlice {\n  // Per-run state\n  agentSteps: Record<string, AgentStep[]>;\n  agentCitations: Record<string, Citation[]>;\n  agentState: Record<string, AgentState>;\n  agentThinking: Record<string, string>;\n  agentAnswer: Record<string, { content: string; streaming: boolean }>;\n\n  // Actions\n  addAgentStep: (runId: string, step: AgentStep) => void;\n  updateToolCall: (runId: string, toolCallId: string, update: Partial<ToolCallRecord>) => void;\n  addCitation: (runId: string, citation: Citation) => void;\n  setAgentState: (runId: string, state: AgentState) => void;\n  appendThinking: (runId: string, content: string) => void;\n  setFinalAnswer: (runId: string, content: string, streaming: boolean) => void;\n  clearAgentRun: (runId: string) => void;\n}\n\nconst createAgentSlice: StateCreator<AgentSlice> = (set) => ({\n  agentSteps: {},\n  agentCitations: {},\n  agentState: {},\n  agentThinking: {},\n  agentAnswer: {},\n\n  addAgentStep: (runId, step) =>\n    set((state) => ({\n      agentSteps: {\n        ...state.agentSteps,\n        [runId]: [...(state.agentSteps[runId] || []), step],\n      },\n    })),\n\n  updateToolCall: (runId, toolCallId, update) =>\n    set((state) => {\n      const steps = state.agentSteps[runId] || [];\n      const updatedSteps = steps.map((step) => ({\n        ...step,\n        toolCalls: step.toolCalls.map((tc) =>\n          tc.id === toolCallId ? { ...tc, ...update } : tc\n        ),\n      }));\n      return {\n        agentSteps: { ...state.agentSteps, [runId]: updatedSteps },\n      };\n    }),\n\n  addCitation: (runId, citation) =>\n    set((state) => ({\n      agentCitations: {\n        ...state.agentCitations,\n        [runId]: [...(state.agentCitations[runId] || []), citation],\n      },\n    })),\n\n  setAgentState: (runId, agentState) =>\n    set((state) => ({\n      agentState: { ...state.agentState, [runId]: agentState },\n    })),\n\n  appendThinking: (runId, content) =>\n    set((state) => ({\n      agentThinking: {\n        ...state.agentThinking,\n        [runId]: (state.agentThinking[runId] || '') + content,\n      },\n    })),\n\n  setFinalAnswer: (runId, content, streaming) =>\n    set((state) => ({\n      agentAnswer: {\n        ...state.agentAnswer,\n        [runId]: { content, streaming },\n      },\n    })),\n\n  clearAgentRun: (runId) =>\n    set((state) => {\n      const { [runId]: _, ...restSteps } = state.agentSteps;\n      const { [runId]: __, ...restCitations } = state.agentCitations;\n      const { [runId]: ___, ...restState } = state.agentState;\n      const { [runId]: ____, ...restThinking } = state.agentThinking;\n      const { [runId]: _____, ...restAnswer } = state.agentAnswer;\n      return {\n        agentSteps: restSteps,\n        agentCitations: restCitations,\n        agentState: restState,\n        agentThinking: restThinking,\n        agentAnswer: restAnswer,\n      };\n    }),\n});\n```\n\n---\n\n## 10. Failure Scenarios & Recovery\n\n### Failure Matrix\n\n```\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                           FAILURE SCENARIO MATRIX                                │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\n┌────────────────────┬─────────────────┬────────────────────┬─────────────────────┐\n│ COMPONENT          │ FAILURE         │ DETECTION          │ RECOVERY            │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Model Provider     │ Rate limit 429  │ HTTP status        │ Backoff + retry     │\n│ (Together AI)      │                 │                    │ max 3 attempts      │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Timeout >30s    │ Request timeout    │ Failover to         │\n│                    │                 │                    │ DeepInfra           │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ 5xx error       │ HTTP status        │ Retry once, then    │\n│                    │                 │                    │ failover            │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ All down        │ Both providers     │ Mark run as error   │\n│                    │                 │ fail               │ \"Service unavail\"   │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Model Provider     │ Rate limit      │ HTTP status        │ Wait retry_after    │\n│ (DeepInfra)        │                 │                    │ + retry             │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Timeout/5xx     │ HTTP status        │ No more fallback    │\n│                    │                 │                    │ → ERROR state       │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Web Search         │ API error       │ HTTP 4xx/5xx       │ Retry 3x with       │\n│ (Parallel.ai)      │                 │                    │ backoff             │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Timeout >15s    │ Request timeout    │ Retry once          │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Rate limit      │ 429 status         │ Wait + retry        │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ All retries     │ Max attempts       │ Return error to     │\n│                    │ exhausted       │ exceeded           │ model, continue     │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Web Extract        │ URL unreachable │ Error in response  │ Skip URL, continue  │\n│ (Parallel.ai)      │                 │                    │ with others         │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Timeout >30s    │ Request timeout    │ Retry once          │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Python Sandbox     │ Timeout >30s    │ Docker stop        │ Return timeout err  │\n│ (Docker)           │                 │                    │ to model            │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ OOM killed      │ Exit code 137      │ Return memory err   │\n│                    │                 │                    │ to model            │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Syntax error    │ Non-zero exit      │ Return stderr to    │\n│                    │                 │                    │ model               │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Crash mid-exec  │ status=\"running\"   │ Mark as error       │\n│                    │                 │ on restart         │ (not idempotent)    │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Database           │ Connection lost │ SQLite exception   │ Reconnect with      │\n│ (SQLite/Turso)     │                 │                    │ backoff             │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Disk full       │ Write error        │ Alert, pause runs   │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Lock contention │ Timeout            │ Retry with backoff  │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ SSE Connection     │ Client          │ Connection close   │ Continue run,       │\n│                    │ disconnect      │ event              │ discard events      │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Network timeout │ No heartbeat       │ Client reconnects   │\n│                    │                 │ received           │ with since_seq      │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Backend crash   │ SSE drops          │ Client polls for    │\n│                    │                 │                    │ final state         │\n├────────────────────┼─────────────────┼────────────────────┼─────────────────────┤\n│ Backend Process    │ Crash mid-step  │ updated_at stale   │ Startup recovery    │\n│                    │                 │ on restart         │ scan                │\n│                    ├─────────────────┼────────────────────┼─────────────────────┤\n│                    │ Crash during    │ status=\"running\"   │ Retry idempotent    │\n│                    │ tool exec       │ on tool_call       │ tools, mark others  │\n│                    │                 │                    │ as error            │\n└────────────────────┴─────────────────┴────────────────────┴─────────────────────┘\n```\n\n### Crash Recovery Implementation\n\n```python\n# orchestrator/agent/recovery.py\n\nfrom enum import Enum\nfrom typing import Optional\nfrom datetime import datetime, timedelta\n\nclass RecoveryAction(Enum):\n    CONTINUE = \"continue\"           # Resume from last step\n    RETRY_TOOL = \"retry_tool\"       # Retry stuck tool call\n    MARK_FAILED = \"mark_failed\"     # Cannot recover\n\nasync def recover_incomplete_runs(agent_repo: AgentRepo):\n    \"\"\"Called on server startup to recover crashed runs.\"\"\"\n\n    logger.info(\"Starting crash recovery scan...\")\n\n    # Find runs that were in progress\n    stale_threshold = datetime.utcnow() - timedelta(minutes=5)\n\n    incomplete_runs = await agent_repo.get_incomplete_runs(\n        stale_threshold=stale_threshold.isoformat()\n    )\n\n    logger.info(f\"Found {len(incomplete_runs)} incomplete runs to recover\")\n\n    for run in incomplete_runs:\n        run_id = run[\"run_id\"]\n\n        try:\n            action = await determine_recovery_action(agent_repo, run_id)\n            logger.info(f\"Recovery action for {run_id}: {action}\")\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue for processing\n                asyncio.create_task(resume_agent_run(run_id))\n\n            elif action == RecoveryAction.RETRY_TOOL:\n                # Reset stuck tool and continue\n                await reset_stuck_tools(agent_repo, run_id)\n                asyncio.create_task(resume_agent_run(run_id))\n\n            elif action == RecoveryAction.MARK_FAILED:\n                await agent_repo.update_run(\n                    run_id,\n                    status=\"failed\",\n                    agent_state=\"error\",\n                    error_message=\"Crashed during execution and could not recover\",\n                )\n\n        except Exception as e:\n            logger.exception(f\"Recovery failed for {run_id}\")\n            await agent_repo.update_run(\n                run_id,\n                status=\"failed\",\n                agent_state=\"error\",\n                error_message=f\"Recovery failed: {e}\",\n            )\n\nasync def determine_recovery_action(\n    agent_repo: AgentRepo,\n    run_id: str,\n) -> RecoveryAction:\n    \"\"\"Determine how to recover a crashed run.\"\"\"\n\n    # Check for stuck tool calls\n    stuck_tools = await agent_repo.get_tool_calls(run_id, status=\"running\")\n\n    if stuck_tools:\n        tool = stuck_tools[0]  # Sequential, so only one at a time\n\n        if tool[\"tool_name\"] == \"python_execute\":\n            # Python is NOT idempotent - cannot retry safely\n            await agent_repo.update_tool_call(\n                tool[\"id\"],\n                status=\"error\",\n                error_message=\"Crashed during execution - cannot safely retry\",\n            )\n            return RecoveryAction.CONTINUE\n\n        elif tool[\"tool_name\"] in (\"web_search\", \"web_extract\"):\n            # Idempotent - safe to retry\n            return RecoveryAction.RETRY_TOOL\n\n    # No stuck tools - can continue from last step\n    return RecoveryAction.CONTINUE\n\nasync def reset_stuck_tools(agent_repo: AgentRepo, run_id: str):\n    \"\"\"Reset stuck tool calls to pending for retry.\"\"\"\n\n    stuck_tools = await agent_repo.get_tool_calls(run_id, status=\"running\")\n\n    for tool in stuck_tools:\n        if tool[\"tool_name\"] in (\"web_search\", \"web_extract\"):\n            await agent_repo.update_tool_call(\n                tool[\"id\"],\n                status=\"pending\",\n                execution_attempt=tool[\"execution_attempt\"] + 1,\n            )\n```\n\n---\n\n## 11. Deployment\n\n### Deployment Architecture\n\n```\n┌─────────────────────────────────────────────────────────────────────────────────┐\n│                           DEPLOYMENT ARCHITECTURE                                │\n└─────────────────────────────────────────────────────────────────────────────────┘\n\n                              ┌─────────────────┐\n                              │    Cloudflare   │\n                              │       DNS       │\n                              └────────┬────────┘\n                                       │\n                    ┌──────────────────┴──────────────────┐\n                    │                                      │\n                    ▼                                      ▼\n           ┌─────────────────┐                    ┌─────────────────┐\n           │     Vercel      │                    │    Railway      │\n           │                 │                    │                 │\n           │  ┌───────────┐  │                    │  ┌───────────┐  │\n           │  │  Frontend │  │                    │  │  Backend  │  │\n           │  │   React   │  │       SSE          │  │  FastAPI  │  │\n           │  │   Vite    │  │◄───────────────────│  │           │  │\n           │  │           │  │                    │  │           │  │\n           │  └───────────┘  │                    │  └─────┬─────┘  │\n           │                 │                    │        │        │\n           │  Auto-deploy    │                    │        │        │\n           │  from: main     │                    │  ┌─────┴─────┐  │\n           │  branch         │                    │  │  Docker   │  │\n           │                 │                    │  │  Sandbox  │  │\n           └─────────────────┘                    │  │ (sidecar) │  │\n                                                  │  └───────────┘  │\n                                                  │                 │\n                                                  │  Auto-deploy    │\n                                                  │  from: main     │\n                                                  │  branch         │\n                                                  └────────┬────────┘\n                                                           │\n                                                           ▼\n                                                  ┌─────────────────┐\n                                                  │     Turso       │\n                                                  │                 │\n                                                  │  ┌───────────┐  │\n                                                  │  │  LibSQL   │  │\n                                                  │  │(SQLite)   │  │\n                                                  │  │           │  │\n                                                  │  │ Replicated│  │\n                                                  │  └───────────┘  │\n                                                  │                 │\n                                                  │  Edge replicas  │\n                                                  │  Auto-backup    │\n                                                  └─────────────────┘\n```\n\n### Deployment Commands\n\n#### Backend (Railway)\n\n```bash\n# 1. Login and create project\nrailway login\nrailway init --name reasoner-agent\n\n# 2. Link to repo\nrailway link\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\nrailway variables set TURSO_DATABASE_URL=libsql://xxx\nrailway variables set TURSO_AUTH_TOKEN=xxx\n\n# 4. Create Dockerfile for Railway\ncat > Dockerfile.railway << 'EOF'\nFROM python:3.11-slim\n\nWORKDIR /app\n\n# Install Docker CLI for sandbox\nRUN apt-get update && apt-get install -y docker.io\n\n# Install Python dependencies\nCOPY pyproject.toml uv.lock ./\nRUN pip install uv && uv sync --frozen\n\n# Copy application\nCOPY orchestrator/ ./orchestrator/\nCOPY docker/ ./docker/\n\n# Build sandbox image\nRUN docker build -t reasoner-sandbox:latest ./docker/sandbox/\n\nEXPOSE 9000\n\nCMD [\"uvicorn\", \"orchestrator.app:app\", \"--host\", \"0.0.0.0\", \"--port\", \"9000\"]\nEOF\n\n# 5. Deploy\nrailway up\n```\n\n#### Frontend (Vercel)\n\n```bash\n# 1. Install Vercel CLI\nnpm i -g vercel\n\n# 2. Login\nvercel login\n\n# 3. Link project\ncd ui\nvercel link\n\n# 4. Set environment variables\nvercel env add VITE_API_URL production\n# Enter: https://your-railway-app.railway.app\n\n# 5. Deploy\nvercel --prod\n```\n\n#### Database (Turso)\n\n```bash\n# 1. Install Turso CLI\ncurl -sSfL https://get.tur.so/install.sh | bash\n\n# 2. Login\nturso auth login\n\n# 3. Create database\nturso db create reasoner-prod --location ord\n\n# 4. Get connection string\nturso db show reasoner-prod --url\n# Output: libsql://reasoner-prod-xxx.turso.io\n\n# 5. Create auth token\nturso db tokens create reasoner-prod\n# Output: eyJhbGci...\n\n# 6. Run migrations\nturso db shell reasoner-prod < orchestrator/storage/schema.sql\n```\n\n#### Docker Sandbox Image\n\n```dockerfile\n# docker/sandbox/Dockerfile\n\nFROM python:3.11-slim\n\n# Install scientific computing libraries\nRUN pip install --no-cache-dir \\\n    numpy==1.26.0 \\\n    pandas==2.1.0 \\\n    scipy==1.11.0 \\\n    sympy==1.12 \\\n    matplotlib==3.8.0\n\n# Create non-root user\nRUN useradd -m -s /bin/bash sandbox\nUSER sandbox\n\n# Set working directory\nWORKDIR /code\n\n# Default command\nCMD [\"python\", \"/code/script.py\"]\n```\n\n---\n\n## 12. Configuration\n\n### Complete Configuration File\n\n```yaml\n# orchestrator/chat_config.yaml\n\n# =============================================================================\n# Model Providers\n# =============================================================================\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY:-}  # Optional\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# =============================================================================\n# Agent Settings\n# =============================================================================\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker for providers\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# =============================================================================\n# Parallel.ai (Web Tools)\n# =============================================================================\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n    excerpt_max_chars: 500\n\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# =============================================================================\n# Python Sandbox\n# =============================================================================\nsandbox:\n  docker:\n    enabled: true\n    image: \"reasoner-sandbox:latest\"\n    memory_limit: \"256m\"\n    cpu_limit: \"0.5\"\n    timeout_seconds: 30\n    network_disabled: true\n    read_only: true\n    pids_limit: 50\n\n# =============================================================================\n# Database\n# =============================================================================\ndatabase:\n  # Use Turso in production, local SQLite in development\n  url: ${TURSO_DATABASE_URL:-sqlite:///./data/reasoner.db}\n  auth_token: ${TURSO_AUTH_TOKEN:-}\n\n# =============================================================================\n# Logging\n# =============================================================================\nlogging:\n  level: INFO\n  format: json\n  file: logs/app.log\n  max_bytes: 10485760  # 10MB\n  backup_count: 5\n```\n\n### Environment Variables Summary\n\n```bash\n# Required\nTOGETHER_API_KEY=xxx          # Primary model provider\nPARALLEL_API_KEY=xxx          # Web search/extract\n\n# Optional\nDEEPINFRA_API_KEY=xxx         # Fallback model provider\n\n# Database (production)\nTURSO_DATABASE_URL=libsql://xxx.turso.io\nTURSO_AUTH_TOKEN=xxx\n\n# Frontend\nVITE_API_URL=https://api.example.com\n```\n\n---\n\n## 13. Observability\n\n### Structured Logging\n\n```python\n# All agent operations produce structured JSON logs\n\n{\n  \"timestamp\": \"2024-01-15T10:30:45.123Z\",\n  \"level\": \"INFO\",\n  \"logger\": \"orchestrator.agent.agent_engine\",\n  \"request_id\": \"req_abc123\",\n  \"run_id\": \"run_xyz789\",\n  \"component\": \"agent_engine\",\n  \"message\": \"Tool execution completed\",\n  \"extra\": {\n    \"tool_name\": \"web_search\",\n    \"duration_ms\": 1234,\n    \"success\": true,\n    \"citation_count\": 5\n  }\n}\n```\n\n### Key Metrics to Track\n\n| Metric | Type | Description |\n|--------|------|-------------|\n| `agent.runs.total` | Counter | Total runs started |\n| `agent.runs.completed` | Counter | Runs completed successfully |\n| `agent.runs.failed` | Counter | Runs that failed |\n| `agent.runs.cancelled` | Counter | Runs cancelled by user |\n| `agent.steps.total` | Counter | Total steps executed |\n| `agent.tools.duration_ms` | Histogram | Tool execution latency |\n| `agent.tools.failures` | Counter | Tool failures by type |\n| `agent.model.latency_ms` | Histogram | Model call latency |\n| `agent.model.failures` | Counter | Model call failures |\n| `agent.model.fallbacks` | Counter | Fallback to secondary provider |\n\n### Health Checks\n\n```python\n@router.get(\"/health\")\nasync def health_check():\n    \"\"\"Health check endpoint.\"\"\"\n\n    checks = {\n        \"database\": await check_database(),\n        \"together_ai\": await check_provider(\"together_ai\"),\n        \"parallel\": await check_parallel_api(),\n        \"sandbox\": await check_docker_sandbox(),\n    }\n\n    all_healthy = all(c[\"status\"] == \"healthy\" for c in checks.values())\n\n    return {\n        \"status\": \"healthy\" if all_healthy else \"degraded\",\n        \"checks\": checks,\n        \"timestamp\": datetime.utcnow().isoformat(),\n    }\n```\n\n---\n\n## 14. Security\n\n### Security Measures\n\n| Concern | Measure |\n|---------|---------|\n| API Key Protection | Environment variables, never logged |\n| Sandbox Isolation | `--network=none`, `--read-only`, memory limits |\n| Input Validation | Pydantic models, max lengths |\n| Output Sanitization | No raw content to UI, only summaries |\n| Rate Limiting | Per-IP limits on agent endpoints |\n| CORS | Strict origin checking |\n\n### Sandbox Security\n\n```bash\n# Docker sandbox security flags\ndocker run \\\n  --rm \\\n  --network=none \\           # No network access\n  --memory=256m \\            # Memory limit\n  --cpus=0.5 \\               # CPU limit\n  --read-only \\              # Read-only filesystem\n  --tmpfs /tmp:size=64m \\    # Limited writable temp\n  --pids-limit=50 \\          # Process limit\n  --security-opt=no-new-privileges \\\n  --user sandbox \\           # Non-root user\n  reasoner-sandbox:latest\n```\n\n### API Key Redaction\n\n```python\n# Redact API keys from logs\nSECRET_PATTERNS = [\n    r'api[_-]?key[\"\\']?\\s*[:=]\\s*[\"\\']?[\\w-]+',\n    r'token[\"\\']?\\s*[:=]\\s*[\"\\']?[\\w-]+',\n    r'Bearer\\s+[\\w-]+',\n]\n\ndef redact_secrets(text: str) -> str:\n    for pattern in SECRET_PATTERNS:\n        text = re.sub(pattern, '[REDACTED]', text, flags=re.IGNORECASE)\n    return text\n```\n\n---\n\n## 15. Implementation Plan\n\n### Phase 1: Data Layer (Files 1-3)\n\n1. `orchestrator/storage/schema.sql` - Add agent tables\n2. `orchestrator/schemas.py` - Pydantic models\n3. `orchestrator/storage/repositories/agent_repo.py` - CRUD\n\n### Phase 2: Provider Chain (Files 4-6)\n\n4. `orchestrator/providers/circuit_breaker.py` - Circuit breaker\n5. `orchestrator/providers/chain.py` - Provider chain\n6. `orchestrator/config.py` - Config updates\n\n### Phase 3: Tool Layer (Files 7-12)\n\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Search tool\n10. `orchestrator/agent/tools/web_extract.py` - Extract tool\n11. `orchestrator/agent/tools/python_sandbox.py` - Sandbox tool\n12. `docker/sandbox/Dockerfile` - Sandbox image\n\n### Phase 4: Agent Core (Files 13-15)\n\n13. `orchestrator/agent/state_machine.py` - State machine\n14. `orchestrator/agent/recovery.py` - Crash recovery\n15. `orchestrator/agent/agent_engine.py` - Main engine\n\n### Phase 5: API Layer (Files 16-17)\n\n16. `orchestrator/routes/agent.py` - Agent routes\n17. `orchestrator/app.py` - Router registration\n\n### Phase 6: Frontend (Files 18-26)\n\n18. `ui/src/types/agent.ts` - Types\n19. `ui/src/api/client.ts` - API client\n20. `ui/src/hooks/useStore.ts` - Store additions\n21. `ui/src/hooks/useAgentSSE.ts` - SSE hook\n22. `ui/src/components/ToolCallCard.tsx`\n23. `ui/src/components/AgentThinkingPanel.tsx`\n24. `ui/src/components/CitationInline.tsx`\n25. `ui/src/components/AnswerWithCitations.tsx`\n26. `ui/src/components/ConversationView.tsx`\n\n---\n\n## Appendix: Quick Reference\n\n### File Structure\n\n```\norchestrator/\n├── agent/\n│   ├── __init__.py\n│   ├── agent_engine.py\n│   ├── state_machine.py\n│   ├── recovery.py\n│   └── tools/\n│       ├── __init__.py\n│       ├── base.py\n│       ├── registry.py\n│       ├── web_search.py\n│       ├── web_extract.py\n│       └── python_sandbox.py\n├── providers/\n│   ├── chain.py\n│   └── circuit_breaker.py\n├── routes/\n│   └── agent.py\n├── storage/\n│   ├── schema.sql\n│   └── repositories/\n│       └── agent_repo.py\n└── schemas.py\n\nui/src/\n├── types/\n│   └── agent.ts\n├── api/\n│   └── client.ts\n├── hooks/\n│   ├── useStore.ts\n│   └── useAgentSSE.ts\n└── components/\n    ├── ToolCallCard.tsx\n    ├── AgentThinkingPanel.tsx\n    ├── CitationInline.tsx\n    ├── AnswerWithCitations.tsx\n    └── ConversationView.tsx\n\ndocker/\n└── sandbox/\n    └── Dockerfile\n```\n\n### API Quick Reference\n\n```\nPOST   /api/agent/conversations/{id}/runs     Create agent run\nGET    /api/agent/runs/{id}                   Get run details\nGET    /api/agent/runs/{id}/stream            SSE event stream\nPOST   /api/agent/runs/{id}/cancel            Cancel run\nGET    /api/agent/runs/{id}/citations         Get citations\n```\n\n### SSE Events Quick Reference\n\n```\nagent_state    - State changed\nstep_start     - Step began\ntool_start     - Tool executing\ntool_result    - Tool finished\ncitation       - Citation added\nthinking       - Model reasoning\nanswer         - Final answer\ncomplete       - Run finished\nerror          - Run failed\nheartbeat      - Keep-alive\n```\n"}
```
---
## USER (2026-01-04T09:41:32.790Z)


---
## USER (2026-01-04T09:42:40.725Z)

This session is being continued from a previous conversation that ran out of context. The conversation is summarized below:
Analysis:
Let me chronologically analyze the conversation:

1. **Initial Request**: User wants to build a web research agent on top of existing reasoner repo with:
   - Web + Python tools
   - Parallel.ai APIs for search/extract
   - Python execution sandbox
   - gpt-oss-120b model
   - UI with thinking view (tool calls, summaries) and answer view (markdown with citations)
   - Goals: Evidence-grounded answers, durable runs, full trace system, thinking UI as projection of traces

2. **Exploration Phase**: I launched 3 explore agents to:
   - Explore existing repo structure (FastAPI backend, React frontend, SQLite storage)
   - Read agent architecture research doc
   - Research parallel.ai APIs and gpt-oss-120b model

3. **User Questions**: I asked about Python runtime, durability, and concurrency. User responded they want production-grade design.

4. **Plan Agent**: Launched plan agent to design comprehensive implementation.

5. **User Feedback #1**: User criticized the initial plan:
   - "Parallel tool concurrency is nice UX, but it creates: ordering ambiguity, step attribution complexity, more retry edge cases"
   - "Their checkpoint schema is too 'big JSON blob' and will hurt debugging"
   - "SSE Redis pub/sub is totally out of scope for now"
   - "E2B is not currently what im looking for i dont want extra overhead for v1"

6. **Plan Revisions**: I updated the plan to:
   - Sequential tool execution (not parallel)
   - Normalized schema with separate tables instead of JSON blobs
   - Removed Redis pub/sub
   - Docker sandbox only (no E2B)

7. **User Feedback #2**: "but it still has to be production grade" - I confirmed the design maintains production-grade quality.

8. **User Feedback #3**: "how does the check pointing work if you've removed" - User asked about checkpointing after I removed the checkpoint table. I explained implicit checkpointing via normalized tables.

9. **User Feedback #4**: "what happens when i fails" - User asked about failure scenarios. I added detailed failure handling with write-ahead logging pattern and idempotency keys.

10. **User Feedback #5**: Major request - "i need you circle back on the entire plan work on scenario where it fails and prepare a plan based on that scenarios too, you should consider deployment too as for the model we use whoever provides gpt-ss-120b apis with harmony see that too, where should we host frontend and backend how are we handling all queues and streaming there has to be design and plan based on both happy paths and unhappy paths"

11. **Research**: I searched for gpt-oss-120b providers and found Together AI and DeepInfra.

12. **Complete Plan Rewrite**: I rewrote the entire plan at `/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md` to cover:
   - Provider selection with failover strategy
   - Deployment architecture (Vercel frontend, Railway backend, Turso database)
   - System-wide failure scenarios
   - Data model
   - Agent engine design
   - SSE architecture
   - Configuration
   - Implementation order
   - Production checklist

13. **User Final Request**: "i need you to show me everything in this doc the entire plan not just upgrades on top of exisiting repo in a new md" - User wanted a standalone comprehensive document.

14. **Final Action**: I created a complete standalone system design document at `/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md` with all 15 sections.

Key files created/modified:
- `/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md` - The plan file (incrementally updated)
- `/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md` - Complete standalone system design doc

Key architectural decisions made:
- Sequential tool execution (not parallel)
- Normalized database schema (agent_steps, agent_tool_calls, agent_citations tables)
- Together AI primary + DeepInfra fallback for gpt-oss-120b
- Vercel for frontend, Railway for backend, Turso for database
- Docker sandbox with security hardening (--network=none, memory limits, read-only)
- In-memory asyncio.Queue for SSE (single instance)
- Write-ahead logging pattern for crash recovery
- SSE with resumption support via since_seq parameter

Summary:
1. Primary Request and Intent:
   The user wants to build a production-grade web research agent on top of their existing reasoner repo (FastAPI + React). The agent should:
   - Use Parallel.ai APIs for web search and content extraction
   - Execute Python code in a sandboxed environment
   - Use gpt-oss-120b model via Harmony-compatible providers
   - Provide evidence-grounded answers with citations
   - Have full trace system and crash recovery
   - UI with thinking view (showing tool calls/summaries) and answer view (markdown with citations)
   - Never render full extracted pages to UI - only metadata and cited snippets
   
   Non-negotiables: Seamless monitoring/observability, durability, complete trace system, answer accuracy.

2. Key Technical Concepts:
   - **gpt-oss-120b model**: 117B parameter MoE model requiring Harmony format
   - **Provider Chain with Failover**: Together AI (primary) + DeepInfra (fallback)
   - **Circuit Breaker Pattern**: Prevent cascading failures
   - **Write-Ahead Logging**: Create records before execution for crash recovery
   - **Idempotency Keys**: For safe tool retry
   - **Sequential Tool Execution**: One tool at a time for deterministic ordering
   - **SSE with Resumption**: `since_seq` parameter for reconnection
   - **Normalized Database Schema**: Separate tables instead of JSON blobs
   - **Docker Sandbox**: `--network=none`, `--read-only`, memory limits for security
   - **Parallel.ai APIs**: Search API ($5/1K) and Extract API ($1/1K)

3. Files and Code Sections:
   - **`/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md`** (NEW - Complete standalone document)
     - 15 comprehensive sections covering entire system design
     - Includes all code implementations, database schema, API design, deployment steps
     - Created per user request for standalone documentation

   - **`/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md`** (Plan file - incrementally updated)
     - Original plan file that evolved through user feedback
     - Eventually superseded by the complete system design doc

   - **Key files read during exploration:**
     - `orchestrator/storage/schema.sql` - Existing trace_events table structure
     - `orchestrator/routes/runs.py` - SSE streaming patterns, abort signals
     - `orchestrator/providers/base.py` - LLMProvider protocol with tools support

   - **Database Schema (from final design):**
     ```sql
     -- Extended runs table
     ALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';
     ALTER TABLE runs ADD COLUMN agent_state TEXT;
     ALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;
     ALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;
     ALTER TABLE runs ADD COLUMN updated_at TEXT;

     -- agent_steps table
     CREATE TABLE IF NOT EXISTS agent_steps (
         id TEXT PRIMARY KEY,
         run_id TEXT NOT NULL,
         step_number INTEGER NOT NULL,
         created_at TEXT NOT NULL,
         completed_at TEXT,
         state TEXT NOT NULL,
         model_request_event_id TEXT,
         model_response_event_id TEXT,
         thinking_text TEXT,
         decision TEXT,
         decision_raw TEXT,
         error_message TEXT,
         error_recoverable BOOLEAN DEFAULT TRUE,
         UNIQUE(run_id, step_number),
         FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
     );

     -- agent_tool_calls table
     CREATE TABLE IF NOT EXISTS agent_tool_calls (
         id TEXT PRIMARY KEY,
         run_id TEXT NOT NULL,
         step_id TEXT NOT NULL,
         created_at TEXT NOT NULL,
         tool_name TEXT NOT NULL,
         arguments TEXT NOT NULL,
         status TEXT NOT NULL,
         started_at TEXT,
         completed_at TEXT,
         duration_ms INTEGER,
         idempotency_key TEXT NOT NULL,
         execution_attempt INTEGER DEFAULT 1,
         max_attempts INTEGER DEFAULT 3,
         result_summary TEXT,
         result_raw TEXT,
         error_message TEXT,
         error_type TEXT,
         trace_event_id TEXT,
         FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
         FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE
     );

     -- agent_citations table
     CREATE TABLE IF NOT EXISTS agent_citations (
         id TEXT PRIMARY KEY,
         run_id TEXT NOT NULL,
         tool_call_id TEXT NOT NULL,
         created_at TEXT NOT NULL,
         source_url TEXT NOT NULL,
         title TEXT,
         snippet TEXT NOT NULL,
         used_in_answer BOOLEAN DEFAULT FALSE,
         FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
         FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE
     );
     ```

   - **Deployment Architecture:**
     - Frontend: Vercel (free tier, global CDN)
     - Backend: Railway or Fly.io (Docker support)
     - Database: Turso (distributed SQLite)
     - Sandbox: Docker sidecar container

4. Errors and Fixes:
   - **Parallel tool execution complexity**: User pointed out ordering ambiguity and step attribution issues → Fixed by switching to sequential tool execution
   - **JSON blob checkpoint schema**: User said it would hurt debugging → Fixed by normalizing into separate tables (agent_steps, agent_tool_calls, agent_citations)
   - **E2B overhead**: User didn't want external dependency for v1 → Changed to local Docker container with security hardening
   - **Redis pub/sub scope creep**: User said out of scope → Removed, using in-memory asyncio.Queue for single instance
   - **Missing failure scenarios**: User asked "what happens when it fails" → Added comprehensive failure matrix and recovery logic
   - **Incomplete checkpointing explanation**: User asked about checkpointing after table removal → Added write-ahead logging pattern with idempotency keys and detailed recovery logic

5. Problem Solving:
   - **Crash recovery for non-idempotent tools**: Python execution is NOT idempotent - if crash happens mid-execution, mark as error and let model decide (cannot safely retry)
   - **Crash recovery for idempotent tools**: web_search and web_extract can be safely retried
   - **SSE reconnection**: Frontend tracks lastSeqRef and reconnects with `since_seq` parameter
   - **Provider failover**: Circuit breaker pattern to prevent cascading failures when Together AI is down

6. All User Messages:
   - Initial scope: "Build an agent based on (Web + Python) on top of existing repo optimized for web research + verification + computation" with detailed requirements for UI, tools, goals, APIs
   - "We'll be moving to prod you should be designing for that, the current setup is fully local i need you to circle back a little on decide on that" (response to all 3 questions about runtime/durability/concurrency)
   - "1. Parallel tool concurrency is nice UX, but it creates: ordering ambiguity, step attribution complexity, more retry edge cases 2. Their checkpoint schema is too 'big JSON blob' and will hurt debugging 3. SSE Redis pub/sub is totally out of scope for now 4. E2B is not currently what im looking for i dont want extra overhead for v1"
   - "but it still has to be production grade"
   - "how does the check pointing work if you've removed"
   - "what happens when i fails"
   - "i need you circle back on the entire plan work on scenario where it fails and prepare a plan based on that scenarios too, you should consider deployment too as for the model we use whoever provides gpt-ss-120b apis with harmony see that too, where should we host frontend and backend how are we handling all queues and streaming there has to be design and plan based on both happy paths and unhappy paths"
   - "i need you to show me everything in this doc the entire plan not just upgrades on top of exisiting repo in a new md"

7. Pending Tasks:
   - Exit plan mode and begin implementation
   - Implementation has 6 phases with 26 files to create/modify

8. Current Work:
   I just completed creating the comprehensive standalone system design document at `/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md`. This document contains:
   - 15 sections covering the complete system architecture
   - All code implementations (Python backend, TypeScript frontend)
   - Database schema
   - API design
   - SSE streaming architecture
   - Failure scenarios and recovery
   - Deployment instructions
   - Security measures
   - Implementation order (26 files across 6 phases)

   This was in direct response to user's request: "i need you to show me everything in this doc the entire plan not just upgrades on top of existing repo in a new md"

9. Optional Next Step:
   Wait for user to review the complete system design document and provide feedback or approval to proceed with implementation. The user is still in plan mode and hasn't indicated readiness to begin coding. The planning phase appears complete with the creation of the comprehensive design document..
Please continue the conversation from where we left it off without asking the user any further questions. Continue with the last task that you were asked to work on.
---
## ASSISTANT (2026-01-04T09:42:50.914Z)

<details><summary>Thinking...</summary>

The user wants me to continue from where we left off. Looking at the summary, I had just completed creating the comprehensive standalone system design document at `/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md`. 

The plan file exists at `/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md` and contains the complete production implementation plan.

The summary indicates:
- Planning phase appears complete
- User hasn't indicated readiness to begin coding yet
- I should wait for user to review and provide feedback

However, the instruction says "Please continue the conversation from where we left it off without asking the user any further questions. Continue with the last task that you were asked to work on."

The last task was creating the comprehensive design document, which was completed. The natural next step would be to exit plan mode since the plan is complete and the user wanted a complete design document (which I created).

Let me exit plan mode since the planning is complete and the comprehensive document has been created. The user can then review it and we can proceed to implementation.

</details>
---
## ASSISTANT (2026-01-04T09:42:57.199Z)

The comprehensive system design document has been created at [docs/AGENT_SYSTEM_DESIGN.md](docs/AGENT_SYSTEM_DESIGN.md). The planning phase is complete with all 15 sections covering:

1. **Goals & Non-Negotiables** - Evidence-grounded answers, durability, full tracing
2. **High-Level Architecture** - Component diagram and data flow
3. **Model Provider Selection** - Together AI (primary) + DeepInfra (fallback) with pricing
4. **Deployment Architecture** - Vercel (frontend), Railway (backend), Turso (database)
5. **System-Wide Failure Scenarios** - Model API, tool execution, database, SSE, crash recovery
6. **Data Model** - Normalized schema with `agent_steps`, `agent_tool_calls`, `agent_citations` tables
7. **Agent Engine Design** - State machine and main loop with error handling
8. **Tool Implementations** - web_search, web_extract, python_execute with recovery logic
9. **SSE & Streaming Architecture** - Event types, resumption support
10. **API Design** - REST + SSE endpoints
11. **Frontend Architecture** - React components with reconnection logic
12. **Configuration** - chat_config.yaml additions
13. **Security** - Docker sandbox hardening, API key handling
14. **Implementation Order** - 26 files across 6 phases
15. **Production Checklist** - Pre-launch, monitoring, recovery testing, security

Let me exit plan mode so we can begin implementation.
---
## ASSISTANT (2026-01-04T09:42:57.311Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.13 / $0.52 | Low | Yes | Native | 99.5% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: Together AI (Primary) + DeepInfra (Fallback)\n\n**Why Together AI primary:**\n- Native Harmony format support\n- 99.9% SLA with dedicated clusters\n- OpenAI-compatible API (drop-in replacement)\n- Good tool calling support for agents\n\n**Failover strategy:**\n```\nRequest → Together AI\n  ↓ (if 5xx or timeout > 30s)\n  → DeepInfra (fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Docker Sandbox    │               │     │\n│         │              │  │  (Sidecar per pod) │               │     │\n│         │              │  └────────────────────┘               │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | Sidecar Docker | Co-located with API for low latency |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result\n    result_summary TEXT,\n    result_raw TEXT,\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox\nsandbox:\n  docker:\n    image: \"reasoner-sandbox:latest\"\n    memory_limit: \"256m\"\n    cpu_limit: \"0.5\"\n    timeout_seconds: 30\n    network_disabled: true\n```\n\n### Environment Variables\n\n```bash\n# Required\nTOGETHER_API_KEY=xxx      # Primary model provider\nPARALLEL_API_KEY=xxx      # Web search/extract\n\n# Optional (for failover)\nDEEPINFRA_API_KEY=xxx     # Fallback model provider\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add all agent tables\n2. `orchestrator/schemas.py` - Pydantic models for agent\n3. `orchestrator/storage/repositories/agent_repo.py` - CRUD operations\n\n### Phase 2: Provider Chain\n4. `orchestrator/providers/chain.py` - Multi-provider with failover\n5. `orchestrator/providers/circuit_breaker.py` - Circuit breaker implementation\n6. Update `orchestrator/config.py` - Add provider chain config\n\n### Phase 3: Tool Layer\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Parallel Search\n10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract\n11. `orchestrator/agent/tools/python_sandbox.py` - Docker sandbox\n12. `docker/sandbox/Dockerfile` - Sandbox image\n\n### Phase 4: Agent Core\n13. `orchestrator/agent/state_machine.py` - State transitions\n14. `orchestrator/agent/recovery.py` - Crash recovery logic\n15. `orchestrator/agent/agent_engine.py` - Main loop\n\n### Phase 5: API Layer\n16. `orchestrator/routes/agent.py` - Agent endpoints + SSE\n17. `orchestrator/app.py` - Register router, startup recovery\n\n### Phase 6: Frontend\n18. `ui/src/types/agent.ts` - TypeScript types\n19. `ui/src/api/client.ts` - Agent API client\n20. `ui/src/hooks/useStore.ts` - Agent state\n21. `ui/src/hooks/useAgentSSE.ts` - SSE with reconnection\n22. `ui/src/components/AgentThinkingPanel.tsx`\n23. `ui/src/components/ToolCallCard.tsx`\n24. `ui/src/components/CitationInline.tsx`\n25. `ui/src/components/AnswerWithCitations.tsx`\n26. `ui/src/components/ConversationView.tsx` - Integrate agent mode\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] Together AI API key configured\n- [ ] Parallel.ai API key configured\n- [ ] DeepInfra API key configured (fallback)\n- [ ] Docker sandbox image built and pushed\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] Sandbox network isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T09:46:33.176Z)


---
## USER (2026-01-04T09:46:33.193Z)

[Request interrupted by user for tool use]
---
## USER (2026-01-04T10:10:24.180Z)

<ide_opened_file>The user opened the file /Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md in the IDE. This may or may not be related to the current task.</ide_opened_file>

noticed e2b offers 100 credits plus 
1. The "Docker-in-Cloud" Deployment Failure (Critical)
Location: Section 11 (Deployment) & Section 4 (python_sandbox.py) The Hole: You are planning to run subprocess.run(["docker", "run", ...]) inside your backend application hosted on Railway or Fly.io. Why It Will Fail:

Container-in-Container: Railway and standard Fly.io instances are already containers. They do not have a Docker daemon inside them (dockerd).

The Error: Your application will crash immediately with FileNotFoundError: [Errno 2] No such file or directory: 'docker' because the Docker CLI is not present, or Cannot connect to the Docker daemon because you don't have privileges to spawn sibling containers.

The Fix: You cannot use a "sidecar" Docker container in this environment easily. You must use an external sandbox API (like E2B, which offers a generous free tier for researchers) or deploy a separate dedicated VM (Droplet/EC2) just for the sandbox that exposes an HTTP API.

2. The "Token Context" Blowout (High Severity)
Location: Section 5 (Agent Engine - _call_model) The Hole: You are appending every tool result directly to the message history (context.messages.append(...)) without any pruning or summarization. Why It Will Fail:

Parallel.ai Excerpts are Large: Parallel.ai's "extract" API returns semantic chunks. If you extract from 3 URLs, you might easily get 5k-10k tokens of text.

The Math: By Step 4 or 5, your history will exceed 30k tokens. By Step 10, you will hit the 128k limit of gpt-oss-120b or experience massive latency (and cost).

The Fix: Implement a "Context Pruner". For any tool call older than the last 2 steps, replace the massive JSON body in the history with a 1-line summary string (e.g., [Extracted 400 lines from wikipedia regarding quantum coherence]).

3. The "Zombie Container" Resource Leak (Medium Severity)
Location: Section 10 (Failure Scenarios) & Section 4 (python_sandbox.py) The Hole: You handle cleanup in a finally block inside the execute method. Why It Will Fail:

Hard Crashes: If your Python backend process is killed by the OS (e.g., Out Of Memory - OOM), the finally block will not run.

The Consequence: The Docker container (if you were running locally) would keep running. Over a week of debugging and restarting, you will accumulate dozens of "orphan" containers consuming CPU/RAM until the server locks up.

The Fix: You need a "Startup Sweep" routine in app.py that runs docker kill $(docker ps -q --filter name=sandbox-*) before the web server starts accepting requests.

4. Non-Idempotent Recovery Amnesia (Logic Bug)
Location: Section 10 (Crash Recovery) The Hole: Your recovery logic marks failed python_execute calls as ERROR and then hands control back to the agent. Why It Will Fail:

Lost State: Suppose the agent wrote code to calculate pi to 50 digits. The tool runs, calculates it, but the backend crashes before saving the result.

The Loop: On restart, the system marks that step as ERROR. The Agent wakes up and sees: Step 4: Calculate Pi -> Error.

The Failure: The Agent thinks the code failed to run. It doesn't know the result. It will likely hallucinate the number or fail to answer.

The Fix: If you recover a non-idempotent tool, you must inject a System Hint into the next prompt: "The previous tool execution was interrupted by a system restart. Please regenerate the code and run it again."

5. Provider Economics (Efficiency Gap)
Location: Section 3 (Model & Provider Layer) The Hole: You listed Together AI as Primary and DeepInfra as Fallback. Why It Matters:

Price Difference: DeepInfra currently charges approx $0.09/1M input tokens for gpt-oss-120b. Together AI charges $0.15/1M.

Optimization: Since it is the exact same open-weights model, you are paying ~60% more for the same inference. Make DeepInfra primary for a research project.

6. Database WAL Growth (Efficiency Gap)
Location: Section 6 (Data Model) & agent_tool_calls table The Hole: You are storing result_raw in the main SQLite database. Why It Matters:

Bloat: web_extract results can be massive HTML/Markdown blobs. Storing these in SQLite (especially with Write-Ahead Logging active) will cause your .wal file to grow to gigabytes very quickly, potentially exceeding the disk limits of a cheap Railway tier.

The Fix: Enable auto_vacuum or use an external object store (S3/R2) for the result_raw content, storing only the reference URL in SQLite.
---
## ASSISTANT (2026-01-04T10:10:35.004Z)

<details><summary>Thinking...</summary>

The user has identified 6 critical holes in my design. Let me analyze each one and update the plan file accordingly:

1. **Docker-in-Cloud Deployment Failure** - This is critical. Railway/Fly.io are containers themselves and don't have Docker daemons. The user is right - I need to use E2B (they mention 100 credits plus free tier) or a dedicated VM.

2. **Token Context Blowout** - Valid concern. Appending all tool results to history will blow up context. Need a context pruner.

3. **Zombie Container Resource Leak** - Even if we use E2B, this principle matters. Need startup sweep.

4. **Non-Idempotent Recovery Amnesia** - Good catch. Need to inject system hint about interrupted execution.

5. **Provider Economics** - DeepInfra is cheaper, should be primary.

6. **Database WAL Growth** - Need to handle large blobs differently.

Let me update the plan file to address all these issues. The user mentioned E2B offers 100 credits, so they're open to using it now.

</details>
---
## ASSISTANT (2026-01-04T10:10:35.723Z)

Excellent catches. These are real production failure modes. Let me update the plan to address all 6 issues:
---
## ASSISTANT (2026-01-04T10:10:36.390Z)

**Tool Use:** Read
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md"}
```
---
## USER (2026-01-04T10:10:37.002Z)


---
## ASSISTANT (2026-01-04T10:10:46.523Z)

<details><summary>Thinking...</summary>

Now I need to update the plan to address all 6 critical issues the user identified:

1. **Docker-in-Cloud Deployment Failure** - Switch to E2B (100 free credits)
2. **Token Context Blowout** - Add Context Pruner
3. **Zombie Container Resource Leak** - Add startup sweep (for E2B this becomes session cleanup)
4. **Non-Idempotent Recovery Amnesia** - Add system hint injection
5. **Provider Economics** - Swap DeepInfra to primary
6. **Database WAL Growth** - Move result_raw to object store or just store summaries

Let me make comprehensive edits to fix all 6 issues.

</details>
---
## ASSISTANT (2026-01-04T10:10:46.841Z)

Now let me make comprehensive updates to address all 6 critical issues:
---
## ASSISTANT (2026-01-04T10:10:59.003Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.13 / $0.52 | Low | Yes | Native | 99.5% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: Together AI (Primary) + DeepInfra (Fallback)\n\n**Why Together AI primary:**\n- Native Harmony format support\n- 99.9% SLA with dedicated clusters\n- OpenAI-compatible API (drop-in replacement)\n- Good tool calling support for agents\n\n**Failover strategy:**\n```\nRequest → Together AI\n  ↓ (if 5xx or timeout > 30s)\n  → DeepInfra (fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```","new_string":"## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```"}
```
---
## USER (2026-01-04T10:10:59.015Z)


---
## ASSISTANT (2026-01-04T10:11:05.894Z)

<details><summary>Thinking...</summary>

Good, issue #5 (Provider Economics) is fixed. Now let me fix issue #1 (Docker-in-Cloud) by switching to E2B:

</details>
---
## ASSISTANT (2026-01-04T10:11:09.538Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Docker Sandbox    │               │     │\n│         │              │  │  (Sidecar per pod) │               │     │\n│         │              │  └────────────────────┘               │     │\n│         │              └──────────────────────────────────────┘     │","new_string":"│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │"}
```
---
## USER (2026-01-04T10:11:09.680Z)


---
## ASSISTANT (2026-01-04T10:11:16.642Z)

<details><summary>Thinking...</summary>

Good progress. Now let me update the hosting decisions table to reflect E2B:

</details>
---
## ASSISTANT (2026-01-04T10:11:24.917Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | Sidecar Docker | Co-located with API for low latency |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |","new_string":"### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling"}
```
---
## USER (2026-01-04T10:11:24.933Z)


---
## ASSISTANT (2026-01-04T10:11:32.331Z)

<details><summary>Thinking...</summary>

Now I need to add the Context Pruner section (Issue #2) and update the database schema to address the WAL growth issue (Issue #6). Let me add a new section for the Context Pruner after the Agent Engine Design section.

</details>
---
## ASSISTANT (2026-01-04T10:11:32.798Z)

Now let me add the Context Pruner to fix Issue #2 (Token Blowout):
---
## ASSISTANT (2026-01-04T10:11:50.632Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))","new_string":"            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```"}
```
---
## USER (2026-01-04T10:11:50.647Z)


---
## ASSISTANT (2026-01-04T10:11:59.828Z)

<details><summary>Thinking...</summary>

Good progress. Now let me:
1. Fix Issue #4 (Non-Idempotent Recovery Amnesia) - Add system hint injection
2. Fix Issue #6 (Database WAL Growth) - Update schema to not store result_raw
3. Fix Issue #3 (Zombie Container) - Add E2B session cleanup on startup

Let me add the recovery hint injection first:

</details>
---
## ASSISTANT (2026-01-04T10:12:00.211Z)

Now let me add the Non-Idempotent Recovery fix (Issue #4):
---
## ASSISTANT (2026-01-04T10:12:16.807Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaway.md","old_string":"**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```","new_string":"**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```"}
```
---
## USER (2026-01-04T10:12:16.815Z)


---
## ASSISTANT (2026-01-04T10:12:22.874Z)

<details><summary>Thinking...</summary>

Typo in the filename. Let me fix it:

</details>
---
## ASSISTANT (2026-01-04T10:12:35.605Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)","new_string":"**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)"}
```
---
## USER (2026-01-04T10:12:35.617Z)


---
## ASSISTANT (2026-01-04T10:12:43.559Z)

<details><summary>Thinking...</summary>

Good. Now I need to address Issue #6 (Database WAL Growth) by updating the schema to not store large result_raw blobs in SQLite. Let me update the agent_tool_calls table:

</details>
---
## ASSISTANT (2026-01-04T10:12:43.705Z)

Now let me fix Issue #6 (Database WAL Growth) by updating the schema:
---
## ASSISTANT (2026-01-04T10:12:59.719Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result\n    result_summary TEXT,\n    result_raw TEXT,\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```","new_string":"### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway."}
```
---
## USER (2026-01-04T10:12:59.729Z)


---
## ASSISTANT (2026-01-04T10:13:06.940Z)

<details><summary>Thinking...</summary>

Now let me update the config to reflect E2B instead of Docker, and update the implementation order. Let me also update the environment variables section.

</details>
---
## ASSISTANT (2026-01-04T10:13:07.568Z)

Now let me update the config and implementation sections for E2B:
---
## ASSISTANT (2026-01-04T10:13:13.153Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"# Sandbox\nsandbox:\n  docker:\n    image: \"reasoner-sandbox:latest\"\n    memory_limit: \"256m\"\n    cpu_limit: \"0.5\"\n    timeout_seconds: 30\n    network_disabled: true","new_string":"# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification"}
```
---
## USER (2026-01-04T10:13:13.170Z)


---
## ASSISTANT (2026-01-04T10:13:19.181Z)

<details><summary>Thinking...</summary>

Good. Now let me update the environment variables and implementation order sections:

</details>
---
## ASSISTANT (2026-01-04T10:13:24.587Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Environment Variables\n\n```bash\n# Required\nTOGETHER_API_KEY=xxx      # Primary model provider\nPARALLEL_API_KEY=xxx      # Web search/extract\n\n# Optional (for failover)\nDEEPINFRA_API_KEY=xxx     # Fallback model provider\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```","new_string":"### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```"}
```
---
## USER (2026-01-04T10:13:24.635Z)


---
## ASSISTANT (2026-01-04T10:13:30.711Z)

<details><summary>Thinking...</summary>

Now let me update the implementation order to reflect E2B instead of Docker sandbox:

</details>
---
## ASSISTANT (2026-01-04T10:13:36.771Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 3: Tool Layer\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Parallel Search\n10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract\n11. `orchestrator/agent/tools/python_sandbox.py` - Docker sandbox\n12. `docker/sandbox/Dockerfile` - Sandbox image","new_string":"### Phase 3: Tool Layer\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Parallel Search\n10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract\n11. `orchestrator/agent/tools/python_sandbox.py` - E2B integration"}
```
---
## USER (2026-01-04T10:13:36.783Z)


---
## ASSISTANT (2026-01-04T10:13:41.954Z)

<details><summary>Thinking...</summary>

I notice the numbering got messed up (12 removed but 13 stays). Let me fix that and also add the context pruner to the list:

</details>
---
## ASSISTANT (2026-01-04T10:13:45.161Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 4: Agent Core\n13. `orchestrator/agent/state_machine.py` - State transitions\n14. `orchestrator/agent/recovery.py` - Crash recovery logic\n15. `orchestrator/agent/agent_engine.py` - Main loop","new_string":"### Phase 4: Agent Core\n12. `orchestrator/agent/context_pruner.py` - Token management\n13. `orchestrator/agent/state_machine.py` - State transitions\n14. `orchestrator/agent/recovery.py` - Crash recovery logic (including non-idempotent hints)\n15. `orchestrator/agent/agent_engine.py` - Main loop"}
```
---
## USER (2026-01-04T10:13:45.172Z)


---
## ASSISTANT (2026-01-04T10:13:49.983Z)

<details><summary>Thinking...</summary>

Now let me update the production checklist to reflect the changes:

</details>
---
## ASSISTANT (2026-01-04T10:14:02.116Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## 10. Production Checklist\n\n### Pre-Launch\n- [ ] Together AI API key configured\n- [ ] Parallel.ai API key configured\n- [ ] DeepInfra API key configured (fallback)\n- [ ] Docker sandbox image built and pushed\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] Sandbox network isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints","new_string":"## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints"}
```
---
## USER (2026-01-04T10:14:02.126Z)


---
## ASSISTANT (2026-01-04T10:14:12.112Z)

<details><summary>Thinking...</summary>

Now let me also update the docs/AGENT_SYSTEM_DESIGN.md to reflect these same 6 fixes. But first, let me add a summary section at the top of the plan file that lists all the critical fixes I made:

</details>
---
## ASSISTANT (2026-01-04T10:14:13.215Z)

Let me add a summary of the critical fixes at the top of the plan:
---
## ASSISTANT (2026-01-04T10:14:28.706Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers","new_string":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |"}
```
---
## USER (2026-01-04T10:14:28.728Z)


---
## ASSISTANT (2026-01-04T10:14:38.114Z)

<details><summary>Thinking...</summary>

I've addressed all 6 critical issues in the plan file. Let me summarize what was fixed:

1. **Docker-in-Cloud** → E2B external API
2. **Token Blowout** → Context Pruner added
3. **Zombie Containers** → E2B session cleanup on startup
4. **Non-Idempotent Recovery** → System hint injection for python_execute
5. **Provider Economics** → DeepInfra primary, Together fallback
6. **WAL Bloat** → No result_raw in SQLite, only summaries

The plan is now comprehensive and addresses all failure scenarios. I should exit plan mode so we can begin implementation.

</details>
---
## ASSISTANT (2026-01-04T10:14:46.169Z)

The plan has been updated to address all 6 critical issues you identified:

| Issue | Fix Applied |
|-------|-------------|
| **1. Docker-in-Cloud** | Switched to E2B external sandbox API |
| **2. Token Blowout** | Added Context Pruner (Section 5) - summarizes old tool results |
| **3. Zombie Containers** | Added E2B session cleanup on startup (Section 3.7) |
| **4. Non-Idempotent Recovery** | Added system hint injection (Section 3.6) |
| **5. Provider Economics** | Swapped to DeepInfra primary ($0.09), Together fallback |
| **6. WAL Bloat** | Removed `result_raw` from schema, store only summaries |

Key changes in the plan:
- **Section 1**: DeepInfra now primary (40% cheaper)
- **Section 2**: E2B replaces Docker sidecar with explanation of why Docker-in-container fails
- **Section 3.6**: New section for non-idempotent tool recovery with hint injection
- **Section 3.7**: New section for E2B session cleanup on startup
- **Section 4**: Schema updated - `result_raw` → `result_summary` + optional `result_blob_ref`
- **Section 5**: Context Pruner added after Agent Engine
- **Section 7**: Config updated for E2B
- **Section 8**: Implementation order updated (context_pruner.py added, Dockerfile removed)
---
## ASSISTANT (2026-01-04T10:14:46.691Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway.\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification\n```\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add all agent tables\n2. `orchestrator/schemas.py` - Pydantic models for agent\n3. `orchestrator/storage/repositories/agent_repo.py` - CRUD operations\n\n### Phase 2: Provider Chain\n4. `orchestrator/providers/chain.py` - Multi-provider with failover\n5. `orchestrator/providers/circuit_breaker.py` - Circuit breaker implementation\n6. Update `orchestrator/config.py` - Add provider chain config\n\n### Phase 3: Tool Layer\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Parallel Search\n10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract\n11. `orchestrator/agent/tools/python_sandbox.py` - E2B integration\n\n### Phase 4: Agent Core\n12. `orchestrator/agent/context_pruner.py` - Token management\n13. `orchestrator/agent/state_machine.py` - State transitions\n14. `orchestrator/agent/recovery.py` - Crash recovery logic (including non-idempotent hints)\n15. `orchestrator/agent/agent_engine.py` - Main loop\n\n### Phase 5: API Layer\n16. `orchestrator/routes/agent.py` - Agent endpoints + SSE\n17. `orchestrator/app.py` - Register router, startup recovery\n\n### Phase 6: Frontend\n18. `ui/src/types/agent.ts` - TypeScript types\n19. `ui/src/api/client.ts` - Agent API client\n20. `ui/src/hooks/useStore.ts` - Agent state\n21. `ui/src/hooks/useAgentSSE.ts` - SSE with reconnection\n22. `ui/src/components/AgentThinkingPanel.tsx`\n23. `ui/src/components/ToolCallCard.tsx`\n24. `ui/src/components/CitationInline.tsx`\n25. `ui/src/components/AnswerWithCitations.tsx`\n26. `ui/src/components/ConversationView.tsx` - Integrate agent mode\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T10:19:58.921Z)


---
## USER (2026-01-04T10:19:58.927Z)

[Request interrupted by user for tool use]
---
## USER (2026-01-04T10:21:11.962Z)

<ide_opened_file>The user opened the file /Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md in the IDE. This may or may not be related to the current task.</ide_opened_file>

this has to be phased planning and incremental building with testing, tracing and observability baked in in each phase and make a master doc for easy reference
---
## ASSISTANT (2026-01-04T10:21:19.365Z)

<details><summary>Thinking...</summary>

The user wants:
1. Phased planning with incremental building
2. Testing, tracing, and observability baked into each phase
3. A master doc for easy reference

I need to restructure the plan to be more incremental with clear phases where each phase:
- Has its own tests
- Has tracing/observability built in
- Can be tested independently before moving to the next phase

Let me update the plan file to reflect this structure.

</details>
---
## ASSISTANT (2026-01-04T10:21:20.099Z)

I'll restructure the plan into incremental phases with testing/tracing/observability built into each phase, then create a master reference doc.
---
## ASSISTANT (2026-01-04T10:22:03.661Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## 8. Implementation Order\n\n### Phase 1: Data Layer\n1. `orchestrator/storage/schema.sql` - Add all agent tables\n2. `orchestrator/schemas.py` - Pydantic models for agent\n3. `orchestrator/storage/repositories/agent_repo.py` - CRUD operations\n\n### Phase 2: Provider Chain\n4. `orchestrator/providers/chain.py` - Multi-provider with failover\n5. `orchestrator/providers/circuit_breaker.py` - Circuit breaker implementation\n6. Update `orchestrator/config.py` - Add provider chain config\n\n### Phase 3: Tool Layer\n7. `orchestrator/agent/tools/base.py` - BaseTool ABC\n8. `orchestrator/agent/tools/registry.py` - Tool registry\n9. `orchestrator/agent/tools/web_search.py` - Parallel Search\n10. `orchestrator/agent/tools/web_extract.py` - Parallel Extract\n11. `orchestrator/agent/tools/python_sandbox.py` - E2B integration\n\n### Phase 4: Agent Core\n12. `orchestrator/agent/context_pruner.py` - Token management\n13. `orchestrator/agent/state_machine.py` - State transitions\n14. `orchestrator/agent/recovery.py` - Crash recovery logic (including non-idempotent hints)\n15. `orchestrator/agent/agent_engine.py` - Main loop\n\n### Phase 5: API Layer\n16. `orchestrator/routes/agent.py` - Agent endpoints + SSE\n17. `orchestrator/app.py` - Register router, startup recovery\n\n### Phase 6: Frontend\n18. `ui/src/types/agent.ts` - TypeScript types\n19. `ui/src/api/client.ts` - Agent API client\n20. `ui/src/hooks/useStore.ts` - Agent state\n21. `ui/src/hooks/useAgentSSE.ts` - SSE with reconnection\n22. `ui/src/components/AgentThinkingPanel.tsx`\n23. `ui/src/components/ToolCallCard.tsx`\n24. `ui/src/components/CitationInline.tsx`\n25. `ui/src/components/AnswerWithCitations.tsx`\n26. `ui/src/components/ConversationView.tsx` - Integrate agent mode","new_string":"## 8. Phased Implementation (Incremental with Testing)\n\nEach phase is **independently testable** before moving to the next. Testing, tracing, and observability are built into each phase.\n\n---\n\n### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files:**\n```\norchestrator/storage/schema.sql          # Add agent tables\norchestrator/schemas.py                  # Pydantic models\norchestrator/storage/repositories/agent_repo.py  # CRUD operations\ntests/unit/test_agent_repo.py           # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass\nuv run pytest tests/unit/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations\n\n---\n\n### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files:**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/unit/test_circuit_breaker.py          # Unit tests\ntests/unit/test_provider_chain.py           # Unit tests\ntests/integration/test_provider_failover.py # Integration test\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\nuv run pytest tests/unit/test_circuit_breaker.py -v\nuv run pytest tests/unit/test_provider_chain.py -v\n\n# 2. Integration test (real API calls)\nDEEPINFRA_API_KEY=xxx uv run pytest tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures\n\n---\n\n### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files:**\n```\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/unit/test_tool_registry.py            # Unit tests\ntests/integration/test_web_search.py        # Real Parallel.ai\ntests/integration/test_web_extract.py       # Real Parallel.ai\ntests/integration/test_python_sandbox.py    # Real E2B\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs)\nuv run pytest tests/unit/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs, one at a time)\nPARALLEL_API_KEY=xxx uv run pytest tests/integration/test_web_search.py -v\nPARALLEL_API_KEY=xxx uv run pytest tests/integration/test_web_extract.py -v\nE2B_API_KEY=xxx uv run pytest tests/integration/test_python_sandbox.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged\n\n---\n\n### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/unit/test_context_pruner.py           # Unit tests\ntests/unit/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Context pruner tests\nuv run pytest tests/unit/test_context_pruner.py -v\n\n# 2. State machine tests\nuv run pytest tests/unit/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions\n\n---\n\n### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/unit/test_recovery.py                 # Unit tests\ntests/unit/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py         # E2E with real APIs\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything)\nuv run pytest tests/unit/test_recovery.py -v\nuv run pytest tests/unit/test_agent_engine.py -v\n\n# 2. E2E test (real APIs)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  uv run pytest tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations\n\n---\n\n### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py         # API tests\ntests/integration/test_agent_sse.py         # SSE streaming tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Start server\njust dev\n\n# 2. API tests\nuv run pytest tests/integration/test_agent_api.py -v\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Manual test via curl\ncurl -X POST http://localhost:9000/api/agent/runs \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"query\": \"What is quantum computing?\"}'\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API\n\n---\n\n### Phase 7: Frontend Integration\n**Goal:** UI shows thinking view and answer with citations.\n\n**Files:**\n```\nui/src/types/agent.ts                        # TypeScript types\nui/src/api/client.ts                         # Agent API client\nui/src/hooks/useStore.ts                     # Agent state\nui/src/hooks/useAgentSSE.ts                  # SSE with reconnection\nui/src/components/AgentThinkingPanel.tsx     # Tool calls display\nui/src/components/ToolCallCard.tsx           # Individual tool card\nui/src/components/CitationInline.tsx         # [1] style citations\nui/src/components/AnswerWithCitations.tsx    # Final answer\nui/src/components/ConversationView.tsx       # Integrate agent mode\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. TypeScript compiles\ncd ui && pnpm tsc --noEmit\n\n# 2. Manual testing\ncd ui && pnpm dev\n# Open browser, submit query, verify:\n# - Thinking panel shows tool calls\n# - Answer has inline citations\n# - SSE reconnects on disconnect\n```\n\n**Observability Built-in:**\n- Console logging for SSE events\n- Error boundary with error reporting\n- Performance timing in dev tools\n\n**Exit Criteria:** ✅ Full user flow works: query → thinking → answer with citations\n\n---\n\n### Phase 8: Production Hardening\n**Goal:** Deploy to Railway/Vercel, verify recovery and monitoring.\n\n**Tasks:**\n```\n1. Deploy backend to Railway\n2. Deploy frontend to Vercel\n3. Configure Turso database\n4. Set up monitoring/alerting\n5. Test crash recovery in production\n6. Load test with 10 concurrent queries\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Deploy\nrailway up\nvercel --prod\n\n# 2. Smoke test\ncurl https://your-api.railway.app/health\n\n# 3. Recovery test\n# Kill Railway instance mid-run, verify it resumes\n\n# 4. Load test\nhey -n 100 -c 10 https://your-api.railway.app/api/agent/runs\n```\n\n**Observability Built-in:**\n- Structured JSON logs → Railway logs\n- Error alerting via Railway\n- Latency percentiles\n\n**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency"}
```
---
## USER (2026-01-04T10:22:03.696Z)


---
## ASSISTANT (2026-01-04T10:22:11.973Z)

<details><summary>Thinking...</summary>

Now I need to create a master reference document that provides easy access to all the key information. Let me create a new document at docs/AGENT_MASTER_REFERENCE.md that consolidates everything in an easy-to-scan format.

</details>
---
## ASSISTANT (2026-01-04T10:22:12.216Z)

Now let me create the master reference document:
---
## ASSISTANT (2026-01-04T10:22:58.707Z)

**Tool Use:** Write
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_MASTER_REFERENCE.md","content":"# Web Research Agent - Master Reference\n\n> Quick reference for the web research agent implementation. For detailed design, see [AGENT_SYSTEM_DESIGN.md](./AGENT_SYSTEM_DESIGN.md).\n\n---\n\n## Quick Links\n\n| What | Where |\n|------|-------|\n| Full Design Doc | [docs/AGENT_SYSTEM_DESIGN.md](./AGENT_SYSTEM_DESIGN.md) |\n| Implementation Plan | [.claude/plans/lazy-purring-nygaard.md](../.claude/plans/lazy-purring-nygaard.md) |\n| Agent Schema | [orchestrator/storage/schema.sql](../orchestrator/storage/schema.sql) |\n| Config | [orchestrator/chat_config.yaml](../orchestrator/chat_config.yaml) |\n\n---\n\n## Architecture Overview\n\n```\n┌─────────────┐     ┌─────────────────────────────────────┐\n│   Frontend  │────▶│              Backend                │\n│   (Vercel)  │ SSE │           (Railway)                 │\n└─────────────┘◀────│  ┌─────────┐    ┌──────────────┐   │\n                    │  │ Agent   │───▶│ Turso SQLite │   │\n                    │  │ Engine  │    └──────────────┘   │\n                    │  └────┬────┘                        │\n                    └───────┼────────────────────────────┘\n                            │\n          ┌─────────────────┼─────────────────┐\n          ▼                 ▼                 ▼\n    ┌──────────┐     ┌───────────┐     ┌──────────┐\n    │ DeepInfra│     │Parallel.ai│     │   E2B    │\n    │(gpt-oss) │     │(search/   │     │(sandbox) │\n    └──────────┘     │ extract)  │     └──────────┘\n                     └───────────┘\n```\n\n---\n\n## Critical Fixes (Must Remember)\n\n| # | Problem | Solution |\n|---|---------|----------|\n| 1 | Docker won't run in Railway/Fly.io containers | Use E2B external sandbox API |\n| 2 | Context blows up to 128k tokens | Context Pruner: summarize old tool results |\n| 3 | Orphan E2B sessions after crash | Session cleanup on startup |\n| 4 | python_execute crash loses result | Inject system hint: \"re-run the code\" |\n| 5 | Together AI is 60% more expensive | DeepInfra primary ($0.09/1M tokens) |\n| 6 | result_raw causes WAL bloat | Store only result_summary, no blobs |\n\n---\n\n## Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional\nTOGETHER_API_KEY=xxx      # Fallback model provider\nTURSO_DATABASE_URL=xxx    # Production database\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## Database Schema (Agent Tables)\n\n```sql\n-- Runs: Add agent columns\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\n\n-- Agent Steps\nCREATE TABLE agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n    thinking_text TEXT,\n    decision TEXT,        -- call_tool | synthesize | error\n    UNIQUE(run_id, step_number)\n);\n\n-- Tool Calls (NO result_raw - prevents WAL bloat)\nCREATE TABLE agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    result_summary TEXT,   -- 1-line only\n    idempotency_key TEXT NOT NULL\n);\n\n-- Citations\nCREATE TABLE agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n    used_in_answer BOOLEAN DEFAULT FALSE\n);\n```\n\n---\n\n## Tools Reference\n\n### web_search\n```json\n{\n  \"name\": \"web_search\",\n  \"description\": \"Search the web for information\",\n  \"parameters\": {\n    \"query\": \"string (required)\",\n    \"num_results\": \"integer (default: 10)\"\n  }\n}\n```\n**Idempotent:** Yes (safe to retry)\n\n### web_extract\n```json\n{\n  \"name\": \"web_extract\",\n  \"description\": \"Extract content from URLs\",\n  \"parameters\": {\n    \"urls\": \"array of strings (required, max 5)\"\n  }\n}\n```\n**Idempotent:** Yes (safe to retry)\n\n### python_execute\n```json\n{\n  \"name\": \"python_execute\",\n  \"description\": \"Execute Python code in sandbox\",\n  \"parameters\": {\n    \"code\": \"string (required)\"\n  }\n}\n```\n**Idempotent:** NO (inject hint on recovery)\n\n---\n\n## SSE Event Types\n\n| Event | When | Data |\n|-------|------|------|\n| `agent_state` | State transition | `{state: \"planning\"}` |\n| `step_start` | New step | `{step_number: 1}` |\n| `tool_start` | Tool executing | `{tool_name: \"web_search\"}` |\n| `tool_result` | Tool done | `{summary: \"Found 10 results\"}` |\n| `thinking` | Reasoning tokens | `{text: \"...\"}` |\n| `answer` | Final answer tokens | `{text: \"...\"}` |\n| `citation` | Citation added | `{url, title, snippet}` |\n| `complete` | Run finished | `{final_answer: \"...\"}` |\n| `error` | Run failed | `{message: \"...\"}` |\n| `heartbeat` | Keep-alive | `{}` |\n\n**Resumption:** Use `?since_seq=N` to resume from sequence N\n\n---\n\n## API Endpoints\n\n```\nPOST   /api/agent/runs              # Start new agent run\nGET    /api/agent/runs/{id}         # Get run status\nGET    /api/agent/runs/{id}/stream  # SSE event stream\nPOST   /api/agent/runs/{id}/cancel  # Cancel run\nGET    /api/agent/runs/{id}/trace   # Get full trace\n```\n\n---\n\n## Phased Implementation Checklist\n\n### Phase 1: Data Layer\n- [ ] Add agent tables to schema.sql\n- [ ] Create Pydantic models in schemas.py\n- [ ] Create agent_repo.py with CRUD\n- [ ] Write unit tests\n- [ ] **Exit:** `sqlite3 data/reasoner.db \".schema agent_steps\"` works\n\n### Phase 2: Provider Chain\n- [ ] Implement circuit_breaker.py\n- [ ] Implement chain.py with failover\n- [ ] Update config.py\n- [ ] Write unit + integration tests\n- [ ] **Exit:** Failover to Together works when DeepInfra fails\n\n### Phase 3: Tool Layer\n- [ ] Create base.py (BaseTool ABC)\n- [ ] Create registry.py\n- [ ] Implement web_search.py\n- [ ] Implement web_extract.py\n- [ ] Implement python_sandbox.py (E2B)\n- [ ] Write tests for each tool\n- [ ] **Exit:** Each tool works in isolation\n\n### Phase 4: Context Pruner + State Machine\n- [ ] Implement context_pruner.py\n- [ ] Implement state_machine.py\n- [ ] Write unit tests\n- [ ] **Exit:** Pruner reduces token count, state transitions work\n\n### Phase 5: Agent Engine\n- [ ] Implement recovery.py (with hint injection)\n- [ ] Implement agent_engine.py\n- [ ] Write unit + E2E tests\n- [ ] **Exit:** Agent answers \"What is the population of Tokyo?\"\n\n### Phase 6: API Layer\n- [ ] Create routes/agent.py\n- [ ] Update app.py with startup recovery\n- [ ] Write API + SSE tests\n- [ ] **Exit:** curl can start run and stream events\n\n### Phase 7: Frontend\n- [ ] Create TypeScript types\n- [ ] Create API client\n- [ ] Create useAgentSSE hook\n- [ ] Create UI components\n- [ ] **Exit:** Full user flow works in browser\n\n### Phase 8: Production\n- [ ] Deploy to Railway\n- [ ] Deploy to Vercel\n- [ ] Configure Turso\n- [ ] Test crash recovery\n- [ ] **Exit:** Production deployment with <5s p95 latency\n\n---\n\n## Debugging Commands\n\n```bash\n# View agent traces\nsqlite3 data/reasoner.db \"SELECT * FROM agent_steps WHERE run_id='xxx'\"\n\n# View tool calls\nsqlite3 data/reasoner.db \"SELECT tool_name, status, result_summary FROM agent_tool_calls WHERE run_id='xxx'\"\n\n# Check circuit breaker state\ngrep \"circuit_breaker\" logs/app.log | jq .\n\n# Check token usage\ngrep \"context_pruner\" logs/app.log | jq '{before: .tokens_before, after: .tokens_after}'\n\n# Check recovery actions\ngrep \"recovery\" logs/app.log | jq .\n```\n\n---\n\n## Common Issues\n\n### \"Docker daemon not found\"\n**Cause:** Trying to run Docker in Railway/Fly.io container\n**Fix:** Use E2B sandbox API instead\n\n### Context exceeds 128k tokens\n**Cause:** Tool results not being pruned\n**Fix:** Check context_pruner is being called before model calls\n\n### Agent hallucinates after crash recovery\n**Cause:** Non-idempotent tool (python_execute) crashed, result lost\n**Fix:** Verify hint injection is working in recovery.py\n\n### SSE disconnects and loses events\n**Cause:** Client not using `since_seq` parameter\n**Fix:** Frontend must track last seq and reconnect with `?since_seq=N`\n\n### WAL file growing to gigabytes\n**Cause:** Storing result_raw in agent_tool_calls\n**Fix:** Only store result_summary, enable auto_vacuum\n\n---\n\n## Key Files Map\n\n```\norchestrator/\n├── agent/\n│   ├── agent_engine.py      # Main agent loop\n│   ├── context_pruner.py    # Token management\n│   ├── recovery.py          # Crash recovery + hints\n│   ├── state_machine.py     # State transitions\n│   └── tools/\n│       ├── base.py          # BaseTool ABC\n│       ├── registry.py      # Tool registry\n│       ├── web_search.py    # Parallel.ai search\n│       ├── web_extract.py   # Parallel.ai extract\n│       └── python_sandbox.py # E2B sandbox\n├── providers/\n│   ├── chain.py             # Provider failover\n│   └── circuit_breaker.py   # Circuit breaker\n├── routes/\n│   └── agent.py             # HTTP + SSE endpoints\n└── storage/\n    └── repositories/\n        └── agent_repo.py    # DB operations\n\nui/src/\n├── components/\n│   ├── AgentThinkingPanel.tsx\n│   ├── ToolCallCard.tsx\n│   ├── CitationInline.tsx\n│   └── AnswerWithCitations.tsx\n└── hooks/\n    └── useAgentSSE.ts       # SSE with reconnection\n```\n"}
```
---
## USER (2026-01-04T10:23:28.901Z)


---
## ASSISTANT (2026-01-04T10:23:38.765Z)

<details><summary>Thinking...</summary>

I've created:
1. Updated the plan file with 8 phased implementation with testing/tracing/observability built into each phase
2. Created a master reference document at docs/AGENT_MASTER_REFERENCE.md

Now let me also update the AGENT_SYSTEM_DESIGN.md to include the phased implementation and critical fixes. But first, let me check what's already in there and if it needs updating.

Actually, the user asked for a master doc for easy reference - I've created that. Let me exit plan mode now.

</details>
---
## ASSISTANT (2026-01-04T10:23:43.976Z)

I've restructured the implementation into 8 incremental phases and created the master reference doc. Here's a summary:

**Phased Implementation (each independently testable):**

| Phase | Goal | Exit Criteria |
|-------|------|---------------|
| 1 | Data Layer | Can CRUD agent tables |
| 2 | Provider Chain | Failover + circuit breaker work |
| 3 | Tool Layer | Each tool works in isolation |
| 4 | Context Pruner + State | Token management works |
| 5 | Agent Engine | Agent answers questions E2E |
| 6 | API + SSE | HTTP endpoints + streaming work |
| 7 | Frontend | Full UI flow works |
| 8 | Production | Deployed with crash recovery |

**Documents created:**
- [docs/AGENT_MASTER_REFERENCE.md](docs/AGENT_MASTER_REFERENCE.md) - Quick reference with checklists, commands, schema
- Plan file updated with detailed testing checkpoints per phase

Each phase includes:
- Specific files to create
- Testing commands (unit + integration)
- Observability requirements (logging, tracing)
- Clear exit criteria
---
## ASSISTANT (2026-01-04T10:23:44.052Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway.\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification\n```\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Phased Implementation (Incremental with Testing)\n\nEach phase is **independently testable** before moving to the next. Testing, tracing, and observability are built into each phase.\n\n---\n\n### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files:**\n```\norchestrator/storage/schema.sql          # Add agent tables\norchestrator/schemas.py                  # Pydantic models\norchestrator/storage/repositories/agent_repo.py  # CRUD operations\ntests/unit/test_agent_repo.py           # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass\nuv run pytest tests/unit/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations\n\n---\n\n### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files:**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/unit/test_circuit_breaker.py          # Unit tests\ntests/unit/test_provider_chain.py           # Unit tests\ntests/integration/test_provider_failover.py # Integration test\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\nuv run pytest tests/unit/test_circuit_breaker.py -v\nuv run pytest tests/unit/test_provider_chain.py -v\n\n# 2. Integration test (real API calls)\nDEEPINFRA_API_KEY=xxx uv run pytest tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures\n\n---\n\n### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files:**\n```\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/unit/test_tool_registry.py            # Unit tests\ntests/integration/test_web_search.py        # Real Parallel.ai\ntests/integration/test_web_extract.py       # Real Parallel.ai\ntests/integration/test_python_sandbox.py    # Real E2B\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs)\nuv run pytest tests/unit/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs, one at a time)\nPARALLEL_API_KEY=xxx uv run pytest tests/integration/test_web_search.py -v\nPARALLEL_API_KEY=xxx uv run pytest tests/integration/test_web_extract.py -v\nE2B_API_KEY=xxx uv run pytest tests/integration/test_python_sandbox.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged\n\n---\n\n### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/unit/test_context_pruner.py           # Unit tests\ntests/unit/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Context pruner tests\nuv run pytest tests/unit/test_context_pruner.py -v\n\n# 2. State machine tests\nuv run pytest tests/unit/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions\n\n---\n\n### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/unit/test_recovery.py                 # Unit tests\ntests/unit/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py         # E2E with real APIs\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything)\nuv run pytest tests/unit/test_recovery.py -v\nuv run pytest tests/unit/test_agent_engine.py -v\n\n# 2. E2E test (real APIs)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  uv run pytest tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations\n\n---\n\n### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py         # API tests\ntests/integration/test_agent_sse.py         # SSE streaming tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Start server\njust dev\n\n# 2. API tests\nuv run pytest tests/integration/test_agent_api.py -v\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Manual test via curl\ncurl -X POST http://localhost:9000/api/agent/runs \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"query\": \"What is quantum computing?\"}'\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API\n\n---\n\n### Phase 7: Frontend Integration\n**Goal:** UI shows thinking view and answer with citations.\n\n**Files:**\n```\nui/src/types/agent.ts                        # TypeScript types\nui/src/api/client.ts                         # Agent API client\nui/src/hooks/useStore.ts                     # Agent state\nui/src/hooks/useAgentSSE.ts                  # SSE with reconnection\nui/src/components/AgentThinkingPanel.tsx     # Tool calls display\nui/src/components/ToolCallCard.tsx           # Individual tool card\nui/src/components/CitationInline.tsx         # [1] style citations\nui/src/components/AnswerWithCitations.tsx    # Final answer\nui/src/components/ConversationView.tsx       # Integrate agent mode\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. TypeScript compiles\ncd ui && pnpm tsc --noEmit\n\n# 2. Manual testing\ncd ui && pnpm dev\n# Open browser, submit query, verify:\n# - Thinking panel shows tool calls\n# - Answer has inline citations\n# - SSE reconnects on disconnect\n```\n\n**Observability Built-in:**\n- Console logging for SSE events\n- Error boundary with error reporting\n- Performance timing in dev tools\n\n**Exit Criteria:** ✅ Full user flow works: query → thinking → answer with citations\n\n---\n\n### Phase 8: Production Hardening\n**Goal:** Deploy to Railway/Vercel, verify recovery and monitoring.\n\n**Tasks:**\n```\n1. Deploy backend to Railway\n2. Deploy frontend to Vercel\n3. Configure Turso database\n4. Set up monitoring/alerting\n5. Test crash recovery in production\n6. Load test with 10 concurrent queries\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Deploy\nrailway up\nvercel --prod\n\n# 2. Smoke test\ncurl https://your-api.railway.app/health\n\n# 3. Recovery test\n# Kill Railway instance mid-run, verify it resumes\n\n# 4. Load test\nhey -n 100 -c 10 https://your-api.railway.app/api/agent/runs\n```\n\n**Observability Built-in:**\n- Structured JSON logs → Railway logs\n- Error alerting via Railway\n- Latency percentiles\n\n**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T10:26:15.900Z)


---
## ASSISTANT (2026-01-04T10:26:23.006Z)

<details><summary>Thinking...</summary>

The user is right - I need to:
1. Verify the links in the master reference are correct and have updated info
2. Explore the existing tests and scripts in the repo to understand what patterns already exist

Let me launch an explore agent to understand the current test structure and scripts.

</details>
---
## ASSISTANT (2026-01-04T10:26:23.666Z)

You're right. Let me explore the existing tests and scripts to understand current patterns before finalizing the docs.
---
## ASSISTANT (2026-01-04T10:26:27.082Z)

**Tool Use:** Task
```json
{"description":"Explore tests and scripts","prompt":"Explore the current test structure and scripts in this repo:\n\n1. Look at `tests/` directory structure - what test patterns exist (unit, integration, e2e)?\n2. Look at `scripts/` directory - what scripts exist and what do they do?\n3. Check existing test files to understand:\n   - How tests are organized\n   - What fixtures/mocks are used\n   - Any test utilities or helpers\n4. Check if there's a `justfile` or `Makefile` for common commands\n\nReturn a summary of:\n- Test directory structure\n- Existing test patterns and conventions\n- Scripts available\n- Test utilities/fixtures already in place","subagent_type":"Explore"}
```
---
## ASSISTANT (2026-01-04T10:26:30.612Z)

**Tool Use:** Task
```json
{"description":"Check AGENT_SYSTEM_DESIGN.md","prompt":"Read /Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md and check if it has the updated information including:\n\n1. Critical fixes (6 issues: Docker-in-Cloud, Token Blowout, Zombie Containers, Non-Idempotent Recovery, Provider Economics, WAL Bloat)\n2. E2B instead of Docker for sandbox\n3. DeepInfra as primary provider (not Together AI)\n4. Context Pruner section\n5. Non-idempotent recovery with hint injection\n\nReport what's present and what's missing.","subagent_type":"Explore"}
```
---
## USER (2026-01-04T10:26:58.221Z)


---
## USER (2026-01-04T10:27:13.407Z)


---
## ASSISTANT (2026-01-04T10:27:26.556Z)

<details><summary>Thinking...</summary>

Now I have important information:

1. **Existing Test Structure:**
   - Tests mirror `orchestrator/` structure
   - Unit tests in individual module folders
   - Integration tests in `tests/integration/`
   - E2E tests using FastAPI TestClient
   - Fixtures in `conftest.py` (event_loop, reset_trace_repo_lock)
   - Uses `unittest.mock.AsyncMock`, `MagicMock`, `patch`
   - Scripts: `test_loop.sh`, `test_loop.py`, `sanity_test.sh`
   - justfile commands: `just test`, `just test-loop`, `just sanity`

2. **AGENT_SYSTEM_DESIGN.md is OUTDATED:**
   - Missing 4 of 6 critical fixes
   - Uses Docker instead of E2B
   - Has Together AI as primary (not DeepInfra)
   - No Context Pruner section
   - No hint injection for recovery

I need to:
1. Update the plan file to reference existing test patterns
2. Update AGENT_SYSTEM_DESIGN.md with all the critical fixes (but I can only edit the plan file in plan mode)
3. Create a proper master reference that aligns with existing patterns

Wait - I'm in plan mode and can only edit the plan file. The user also said the AGENT_SYSTEM_DESIGN.md is outdated. So I should:
1. Update the plan file to include all the correct information
2. Note that AGENT_SYSTEM_DESIGN.md needs to be updated when we exit plan mode
3. Make the plan file the authoritative source for now

Let me update the plan file to include:
1. Existing test patterns to follow
2. Existing scripts to use
3. Note about needing to update AGENT_SYSTEM_DESIGN.md

</details>
---
## ASSISTANT (2026-01-04T10:27:29.352Z)

Good findings. The exploration revealed:

**Existing Test Patterns:**
- Tests mirror `orchestrator/` structure
- `tests/integration/` for integration + E2E
- Uses `AsyncMock`, `MagicMock`, `patch`
- Fixtures: `event_loop`, in-memory SQLite
- Scripts: `test_loop.sh`, `sanity_test.sh`
- justfile: `just test`, `just test-loop`, `just sanity`

**AGENT_SYSTEM_DESIGN.md is OUTDATED:**
- Missing 4 of 6 critical fixes
- Uses Docker (not E2B)
- Has Together AI as primary (not DeepInfra)
- No Context Pruner or hint injection

Let me update the plan to align with existing patterns and note what docs need updating:
---
## ASSISTANT (2026-01-04T10:27:48.942Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |","new_string":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Document Status\n\n| Document | Status | Action Needed |\n|----------|--------|---------------|\n| **This plan file** | ✅ Authoritative | Source of truth for implementation |\n| `docs/AGENT_SYSTEM_DESIGN.md` | ❌ Outdated | Needs full rewrite (Docker→E2B, Together→DeepInfra, missing 4/6 fixes) |\n| `docs/AGENT_MASTER_REFERENCE.md` | ⚠️ Partial | Needs update after implementation |\n\n---\n\n## Existing Codebase Patterns (MUST FOLLOW)\n\n### Test Structure\n```\ntests/\n├── conftest.py                    # Global fixtures (event_loop, reset_trace_repo_lock)\n├── config/test_config.py          # Unit: config loading\n├── engine/test_chat_engine.py     # Unit: chat engine\n├── providers/                     # Unit: provider logic\n├── storage/                       # Unit: database, repos\n├── integration/\n│   ├── test_full_flow.py          # Integration: mocked provider, real DB\n│   └── test_e2e_flow.py           # E2E: FastAPI TestClient, HTTP endpoints\n```\n\n### Test Patterns Already Used\n- `@pytest.mark.asyncio` for async tests\n- `unittest.mock.AsyncMock` for async mocking\n- `patch(\"orchestrator.module.func\")` for patching\n- In-memory SQLite via fixture\n- Factory functions like `create_mock_provider(response_text)`\n\n### Scripts Already Available\n- `just test` - Run pytest\n- `just test-loop` - Run with log analysis\n- `just sanity` - Integration tests (requires API running)\n- `./scripts/test_loop.sh` - Test harness with error extraction\n- `./scripts/sanity_test.sh` - Full integration test\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |"}
```
---
## USER (2026-01-04T10:27:48.958Z)


---
## ASSISTANT (2026-01-04T10:27:56.960Z)

<details><summary>Thinking...</summary>

Good. Now let me update the phased implementation to include proper test file paths that match the existing patterns:

</details>
---
## ASSISTANT (2026-01-04T10:27:57.362Z)

Now let me update the phased implementation to align with existing test patterns:
---
## ASSISTANT (2026-01-04T10:28:09.551Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files:**\n```\norchestrator/storage/schema.sql          # Add agent tables\norchestrator/schemas.py                  # Pydantic models\norchestrator/storage/repositories/agent_repo.py  # CRUD operations\ntests/unit/test_agent_repo.py           # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass\nuv run pytest tests/unit/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations","new_string":"### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass (use existing just command)\njust test tests/storage/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration (follow existing trace_repo.py pattern)\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations"}
```
---
## USER (2026-01-04T10:28:09.563Z)


---
## ASSISTANT (2026-01-04T10:28:16.435Z)

<details><summary>Thinking...</summary>

Let me continue updating the other phases to align with existing patterns:

</details>
---
## ASSISTANT (2026-01-04T10:28:27.890Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files:**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/unit/test_circuit_breaker.py          # Unit tests\ntests/unit/test_provider_chain.py           # Unit tests\ntests/integration/test_provider_failover.py # Integration test\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\nuv run pytest tests/unit/test_circuit_breaker.py -v\nuv run pytest tests/unit/test_provider_chain.py -v\n\n# 2. Integration test (real API calls)\nDEEPINFRA_API_KEY=xxx uv run pytest tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures","new_string":"### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files (following existing providers/ pattern):**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/providers/test_circuit_breaker.py      # Unit tests (matches existing test_openai_compat.py)\ntests/providers/test_provider_chain.py       # Unit tests\ntests/integration/test_provider_failover.py  # Integration test (matches test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\njust test tests/providers/test_circuit_breaker.py tests/providers/test_provider_chain.py -v\n\n# 2. Integration test (real API calls - optional, requires keys)\nDEEPINFRA_API_KEY=xxx just test tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures"}
```
---
## USER (2026-01-04T10:28:27.905Z)


---
## ASSISTANT (2026-01-04T10:28:33.443Z)

<details><summary>Thinking...</summary>

Let me continue updating the remaining phases:

</details>
---
## ASSISTANT (2026-01-04T10:28:48.876Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files:**\n```\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/unit/test_tool_registry.py            # Unit tests\ntests/integration/test_web_search.py        # Real Parallel.ai\ntests/integration/test_web_extract.py       # Real Parallel.ai\ntests/integration/test_python_sandbox.py    # Real E2B\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs)\nuv run pytest tests/unit/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs, one at a time)\nPARALLEL_API_KEY=xxx uv run pytest tests/integration/test_web_search.py -v\nPARALLEL_API_KEY=xxx uv run pytest tests/integration/test_web_extract.py -v\nE2B_API_KEY=xxx uv run pytest tests/integration/test_python_sandbox.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged","new_string":"### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files (new agent/ module):**\n```\norchestrator/agent/__init__.py               # Package init\norchestrator/agent/tools/__init__.py         # Tools package\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/agent/__init__.py                      # New test package\ntests/agent/test_tool_registry.py            # Unit tests\ntests/integration/test_agent_tools.py        # Integration: real APIs (optional)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs - always run)\njust test tests/agent/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs - optional, requires keys)\nPARALLEL_API_KEY=xxx E2B_API_KEY=xxx just test tests/integration/test_agent_tools.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged"}
```
---
## USER (2026-01-04T10:28:48.891Z)


---
## ASSISTANT (2026-01-04T10:28:53.826Z)

<details><summary>Thinking...</summary>

Let me continue updating the remaining phases:

</details>
---
## ASSISTANT (2026-01-04T10:29:01.670Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/unit/test_context_pruner.py           # Unit tests\ntests/unit/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Context pruner tests\nuv run pytest tests/unit/test_context_pruner.py -v\n\n# 2. State machine tests\nuv run pytest tests/unit/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions","new_string":"### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/agent/test_context_pruner.py           # Unit tests\ntests/agent/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# All unit tests in one command\njust test tests/agent/test_context_pruner.py tests/agent/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions"}
```
---
## USER (2026-01-04T10:29:01.685Z)


---
## ASSISTANT (2026-01-04T10:29:07.296Z)

<details><summary>Thinking...</summary>

Let me continue with the remaining phases:

</details>
---
## ASSISTANT (2026-01-04T10:29:18.683Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/unit/test_recovery.py                 # Unit tests\ntests/unit/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py         # E2E with real APIs\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything)\nuv run pytest tests/unit/test_recovery.py -v\nuv run pytest tests/unit/test_agent_engine.py -v\n\n# 2. E2E test (real APIs)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  uv run pytest tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations","new_string":"### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/agent/test_recovery.py                 # Unit tests\ntests/agent/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py          # E2E (follows test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything - always run)\njust test tests/agent/test_recovery.py tests/agent/test_agent_engine.py -v\n\n# 2. E2E test (real APIs - optional, requires all keys)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  just test tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations"}
```
---
## USER (2026-01-04T10:29:18.698Z)


---
## ASSISTANT (2026-01-04T10:29:23.507Z)

<details><summary>Thinking...</summary>

Let me update phases 6 and 7:

</details>
---
## ASSISTANT (2026-01-04T10:29:36.995Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py         # API tests\ntests/integration/test_agent_sse.py         # SSE streaming tests\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Start server\njust dev\n\n# 2. API tests\nuv run pytest tests/integration/test_agent_api.py -v\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Manual test via curl\ncurl -X POST http://localhost:9000/api/agent/runs \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"query\": \"What is quantum computing?\"}'\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API","new_string":"### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py          # API tests (follows test_e2e_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit/integration tests (mocked provider, uses TestClient)\njust test tests/integration/test_agent_api.py -v\n\n# 2. Start server for manual testing\njust dev\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Full integration (use existing sanity script pattern)\n./scripts/sanity_test.sh --debug\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API"}
```
---
## USER (2026-01-04T10:29:37.008Z)


---
## ASSISTANT (2026-01-04T10:29:43.138Z)

<details><summary>Thinking...</summary>

Let me now add a summary of all files and update at the end:

</details>
---
## ASSISTANT (2026-01-04T10:29:43.958Z)

Now let me add a consolidated file list at the end of the implementation section:
---
## ASSISTANT (2026-01-04T10:30:05.187Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n## 9. Deployment Steps","new_string":"**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n### Summary: All Files to Create/Modify\n\n**Backend (orchestrator/):**\n```\norchestrator/\n├── storage/\n│   ├── schema.sql                    # Phase 1: Add agent tables\n│   └── repositories/\n│       └── agent_repo.py             # Phase 1: CRUD operations\n├── schemas.py                        # Phase 1: Add agent Pydantic models\n├── config.py                         # Phase 2: Add provider chain config\n├── providers/\n│   ├── circuit_breaker.py            # Phase 2: Circuit breaker\n│   └── chain.py                      # Phase 2: Provider failover\n├── agent/\n│   ├── __init__.py                   # Phase 3\n│   ├── tools/\n│   │   ├── __init__.py               # Phase 3\n│   │   ├── base.py                   # Phase 3: BaseTool ABC\n│   │   ├── registry.py               # Phase 3: Tool registry\n│   │   ├── web_search.py             # Phase 3: Parallel.ai search\n│   │   ├── web_extract.py            # Phase 3: Parallel.ai extract\n│   │   └── python_sandbox.py         # Phase 3: E2B sandbox\n│   ├── context_pruner.py             # Phase 4: Token management\n│   ├── state_machine.py              # Phase 4: State transitions\n│   ├── recovery.py                   # Phase 5: Crash recovery + hints\n│   └── agent_engine.py               # Phase 5: Main loop\n├── routes/\n│   └── agent.py                      # Phase 6: HTTP + SSE endpoints\n└── app.py                            # Phase 6: Register router\n```\n\n**Tests (tests/):**\n```\ntests/\n├── storage/\n│   └── test_agent_repo.py            # Phase 1\n├── providers/\n│   ├── test_circuit_breaker.py       # Phase 2\n│   └── test_provider_chain.py        # Phase 2\n├── agent/\n│   ├── __init__.py\n│   ├── test_tool_registry.py         # Phase 3\n│   ├── test_context_pruner.py        # Phase 4\n│   ├── test_state_machine.py         # Phase 4\n│   ├── test_recovery.py              # Phase 5\n│   └── test_agent_engine.py          # Phase 5\n└── integration/\n    ├── test_provider_failover.py     # Phase 2 (optional)\n    ├── test_agent_tools.py           # Phase 3 (optional)\n    ├── test_agent_e2e.py             # Phase 5 (optional)\n    └── test_agent_api.py             # Phase 6\n```\n\n**Frontend (ui/src/):**\n```\nui/src/\n├── types/\n│   └── agent.ts                      # Phase 7\n├── api/\n│   └── client.ts                     # Phase 7: Add agent methods\n├── hooks/\n│   ├── useStore.ts                   # Phase 7: Add agent state\n│   └── useAgentSSE.ts                # Phase 7: SSE hook\n└── components/\n    ├── AgentThinkingPanel.tsx        # Phase 7\n    ├── ToolCallCard.tsx              # Phase 7\n    ├── CitationInline.tsx            # Phase 7\n    ├── AnswerWithCitations.tsx       # Phase 7\n    └── ConversationView.tsx          # Phase 7: Modify for agent mode\n```\n\n**Docs (to update after implementation):**\n```\ndocs/\n├── AGENT_SYSTEM_DESIGN.md            # Rewrite with all 6 fixes\n└── AGENT_MASTER_REFERENCE.md         # Quick reference\n```\n\n---\n\n## 9. Deployment Steps"}
```
---
## USER (2026-01-04T10:30:05.202Z)


---
## ASSISTANT (2026-01-04T10:30:13.588Z)

<details><summary>Thinking...</summary>

The plan file is now comprehensive and aligned with existing codebase patterns. Let me summarize what I've done and exit plan mode.

The plan now includes:
1. Document Status section - showing which docs are authoritative
2. Existing Codebase Patterns section - test structure, patterns, scripts
3. Critical Fixes section
4. 8 phased implementation with testing checkpoints
5. Summary of all files to create/modify
6. Deployment steps and production checklist

The AGENT_SYSTEM_DESIGN.md and AGENT_MASTER_REFERENCE.md will need to be updated after implementation since they're outdated.

</details>
---
## ASSISTANT (2026-01-04T10:30:18.961Z)

The plan is now updated with:

1. **Document Status** - Shows this plan file is authoritative, other docs need updating
2. **Existing Codebase Patterns** - Test structure, fixtures, scripts to follow
3. **8 Phased Implementation** - Each with files, testing checkpoints, exit criteria
4. **Consolidated File List** - All files organized by phase

Key updates made:
- Test files now follow existing patterns (`tests/storage/`, `tests/providers/`, `tests/agent/`, `tests/integration/`)
- Uses existing commands (`just test`, `just test-loop`, `./scripts/sanity_test.sh`)
- Marks `docs/AGENT_SYSTEM_DESIGN.md` as needing full rewrite after implementation
- Unit tests always run, integration tests optional (require API keys)
---
## ASSISTANT (2026-01-04T10:30:19.495Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Document Status\n\n| Document | Status | Action Needed |\n|----------|--------|---------------|\n| **This plan file** | ✅ Authoritative | Source of truth for implementation |\n| `docs/AGENT_SYSTEM_DESIGN.md` | ❌ Outdated | Needs full rewrite (Docker→E2B, Together→DeepInfra, missing 4/6 fixes) |\n| `docs/AGENT_MASTER_REFERENCE.md` | ⚠️ Partial | Needs update after implementation |\n\n---\n\n## Existing Codebase Patterns (MUST FOLLOW)\n\n### Test Structure\n```\ntests/\n├── conftest.py                    # Global fixtures (event_loop, reset_trace_repo_lock)\n├── config/test_config.py          # Unit: config loading\n├── engine/test_chat_engine.py     # Unit: chat engine\n├── providers/                     # Unit: provider logic\n├── storage/                       # Unit: database, repos\n├── integration/\n│   ├── test_full_flow.py          # Integration: mocked provider, real DB\n│   └── test_e2e_flow.py           # E2E: FastAPI TestClient, HTTP endpoints\n```\n\n### Test Patterns Already Used\n- `@pytest.mark.asyncio` for async tests\n- `unittest.mock.AsyncMock` for async mocking\n- `patch(\"orchestrator.module.func\")` for patching\n- In-memory SQLite via fixture\n- Factory functions like `create_mock_provider(response_text)`\n\n### Scripts Already Available\n- `just test` - Run pytest\n- `just test-loop` - Run with log analysis\n- `just sanity` - Integration tests (requires API running)\n- `./scripts/test_loop.sh` - Test harness with error extraction\n- `./scripts/sanity_test.sh` - Full integration test\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway.\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification\n```\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Phased Implementation (Incremental with Testing)\n\nEach phase is **independently testable** before moving to the next. Testing, tracing, and observability are built into each phase.\n\n---\n\n### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass (use existing just command)\njust test tests/storage/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration (follow existing trace_repo.py pattern)\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations\n\n---\n\n### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files (following existing providers/ pattern):**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/providers/test_circuit_breaker.py      # Unit tests (matches existing test_openai_compat.py)\ntests/providers/test_provider_chain.py       # Unit tests\ntests/integration/test_provider_failover.py  # Integration test (matches test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\njust test tests/providers/test_circuit_breaker.py tests/providers/test_provider_chain.py -v\n\n# 2. Integration test (real API calls - optional, requires keys)\nDEEPINFRA_API_KEY=xxx just test tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures\n\n---\n\n### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files (new agent/ module):**\n```\norchestrator/agent/__init__.py               # Package init\norchestrator/agent/tools/__init__.py         # Tools package\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/agent/__init__.py                      # New test package\ntests/agent/test_tool_registry.py            # Unit tests\ntests/integration/test_agent_tools.py        # Integration: real APIs (optional)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs - always run)\njust test tests/agent/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs - optional, requires keys)\nPARALLEL_API_KEY=xxx E2B_API_KEY=xxx just test tests/integration/test_agent_tools.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged\n\n---\n\n### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/agent/test_context_pruner.py           # Unit tests\ntests/agent/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# All unit tests in one command\njust test tests/agent/test_context_pruner.py tests/agent/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions\n\n---\n\n### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/agent/test_recovery.py                 # Unit tests\ntests/agent/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py          # E2E (follows test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything - always run)\njust test tests/agent/test_recovery.py tests/agent/test_agent_engine.py -v\n\n# 2. E2E test (real APIs - optional, requires all keys)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  just test tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations\n\n---\n\n### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py          # API tests (follows test_e2e_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit/integration tests (mocked provider, uses TestClient)\njust test tests/integration/test_agent_api.py -v\n\n# 2. Start server for manual testing\njust dev\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Full integration (use existing sanity script pattern)\n./scripts/sanity_test.sh --debug\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API\n\n---\n\n### Phase 7: Frontend Integration\n**Goal:** UI shows thinking view and answer with citations.\n\n**Files:**\n```\nui/src/types/agent.ts                        # TypeScript types\nui/src/api/client.ts                         # Agent API client\nui/src/hooks/useStore.ts                     # Agent state\nui/src/hooks/useAgentSSE.ts                  # SSE with reconnection\nui/src/components/AgentThinkingPanel.tsx     # Tool calls display\nui/src/components/ToolCallCard.tsx           # Individual tool card\nui/src/components/CitationInline.tsx         # [1] style citations\nui/src/components/AnswerWithCitations.tsx    # Final answer\nui/src/components/ConversationView.tsx       # Integrate agent mode\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. TypeScript compiles\ncd ui && pnpm tsc --noEmit\n\n# 2. Manual testing\ncd ui && pnpm dev\n# Open browser, submit query, verify:\n# - Thinking panel shows tool calls\n# - Answer has inline citations\n# - SSE reconnects on disconnect\n```\n\n**Observability Built-in:**\n- Console logging for SSE events\n- Error boundary with error reporting\n- Performance timing in dev tools\n\n**Exit Criteria:** ✅ Full user flow works: query → thinking → answer with citations\n\n---\n\n### Phase 8: Production Hardening\n**Goal:** Deploy to Railway/Vercel, verify recovery and monitoring.\n\n**Tasks:**\n```\n1. Deploy backend to Railway\n2. Deploy frontend to Vercel\n3. Configure Turso database\n4. Set up monitoring/alerting\n5. Test crash recovery in production\n6. Load test with 10 concurrent queries\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Deploy\nrailway up\nvercel --prod\n\n# 2. Smoke test\ncurl https://your-api.railway.app/health\n\n# 3. Recovery test\n# Kill Railway instance mid-run, verify it resumes\n\n# 4. Load test\nhey -n 100 -c 10 https://your-api.railway.app/api/agent/runs\n```\n\n**Observability Built-in:**\n- Structured JSON logs → Railway logs\n- Error alerting via Railway\n- Latency percentiles\n\n**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n### Summary: All Files to Create/Modify\n\n**Backend (orchestrator/):**\n```\norchestrator/\n├── storage/\n│   ├── schema.sql                    # Phase 1: Add agent tables\n│   └── repositories/\n│       └── agent_repo.py             # Phase 1: CRUD operations\n├── schemas.py                        # Phase 1: Add agent Pydantic models\n├── config.py                         # Phase 2: Add provider chain config\n├── providers/\n│   ├── circuit_breaker.py            # Phase 2: Circuit breaker\n│   └── chain.py                      # Phase 2: Provider failover\n├── agent/\n│   ├── __init__.py                   # Phase 3\n│   ├── tools/\n│   │   ├── __init__.py               # Phase 3\n│   │   ├── base.py                   # Phase 3: BaseTool ABC\n│   │   ├── registry.py               # Phase 3: Tool registry\n│   │   ├── web_search.py             # Phase 3: Parallel.ai search\n│   │   ├── web_extract.py            # Phase 3: Parallel.ai extract\n│   │   └── python_sandbox.py         # Phase 3: E2B sandbox\n│   ├── context_pruner.py             # Phase 4: Token management\n│   ├── state_machine.py              # Phase 4: State transitions\n│   ├── recovery.py                   # Phase 5: Crash recovery + hints\n│   └── agent_engine.py               # Phase 5: Main loop\n├── routes/\n│   └── agent.py                      # Phase 6: HTTP + SSE endpoints\n└── app.py                            # Phase 6: Register router\n```\n\n**Tests (tests/):**\n```\ntests/\n├── storage/\n│   └── test_agent_repo.py            # Phase 1\n├── providers/\n│   ├── test_circuit_breaker.py       # Phase 2\n│   └── test_provider_chain.py        # Phase 2\n├── agent/\n│   ├── __init__.py\n│   ├── test_tool_registry.py         # Phase 3\n│   ├── test_context_pruner.py        # Phase 4\n│   ├── test_state_machine.py         # Phase 4\n│   ├── test_recovery.py              # Phase 5\n│   └── test_agent_engine.py          # Phase 5\n└── integration/\n    ├── test_provider_failover.py     # Phase 2 (optional)\n    ├── test_agent_tools.py           # Phase 3 (optional)\n    ├── test_agent_e2e.py             # Phase 5 (optional)\n    └── test_agent_api.py             # Phase 6\n```\n\n**Frontend (ui/src/):**\n```\nui/src/\n├── types/\n│   └── agent.ts                      # Phase 7\n├── api/\n│   └── client.ts                     # Phase 7: Add agent methods\n├── hooks/\n│   ├── useStore.ts                   # Phase 7: Add agent state\n│   └── useAgentSSE.ts                # Phase 7: SSE hook\n└── components/\n    ├── AgentThinkingPanel.tsx        # Phase 7\n    ├── ToolCallCard.tsx              # Phase 7\n    ├── CitationInline.tsx            # Phase 7\n    ├── AnswerWithCitations.tsx       # Phase 7\n    └── ConversationView.tsx          # Phase 7: Modify for agent mode\n```\n\n**Docs (to update after implementation):**\n```\ndocs/\n├── AGENT_SYSTEM_DESIGN.md            # Rewrite with all 6 fixes\n└── AGENT_MASTER_REFERENCE.md         # Quick reference\n```\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T10:49:45.027Z)


---
## ASSISTANT (2026-01-04T10:49:55.151Z)

<details><summary>Thinking...</summary>

The user wants:1. Each phase to be its own git branch with testing before merging/moving to next phase2. A live doc that keeps updating on everything that phase builds3. This live doc should be separate from other docs4. When a new chat looks at this, it should be able to pick up based on all those docs alone

So I need to add:1. Branch strategy per phase2. A living implementation log/status doc that tracks what was built
3. Clear handoff documentation so any new conversation can pick up

Let me update the plan with these requirements.

</details>
---
## ASSISTANT (2026-01-04T10:49:55.842Z)

Got it. I'll add branch strategy per phase and a living implementation log that new chats can use to pick up where things left off.
---
## ASSISTANT (2026-01-04T10:50:17.630Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Document Status\n\n| Document | Status | Action Needed |\n|----------|--------|---------------|\n| **This plan file** | ✅ Authoritative | Source of truth for implementation |\n| `docs/AGENT_SYSTEM_DESIGN.md` | ❌ Outdated | Needs full rewrite (Docker→E2B, Together→DeepInfra, missing 4/6 fixes) |\n| `docs/AGENT_MASTER_REFERENCE.md` | ⚠️ Partial | Needs update after implementation |","new_string":"## Document Status\n\n| Document | Purpose | Status |\n|----------|---------|--------|\n| **This plan file** | Design & architecture decisions | ✅ Source of truth |\n| `docs/AGENT_IMPLEMENTATION_LOG.md` | **LIVE DOC** - Phase progress, what was built, handoff notes | 📝 Create at Phase 1 start |\n| `docs/AGENT_SYSTEM_DESIGN.md` | Full system design | ❌ Outdated - rewrite after Phase 8 |\n| `docs/AGENT_MASTER_REFERENCE.md` | Quick reference | ⚠️ Update after Phase 8 |\n\n---\n\n## Branch Strategy (CRITICAL)\n\nEach phase gets its own branch. **Do not merge until all tests pass.**\n\n```\nmain\n └── feature/agent-phase-1-data-layer\n      └── feature/agent-phase-2-provider-chain\n           └── feature/agent-phase-3-tools\n                └── feature/agent-phase-4-pruner-state\n                     └── feature/agent-phase-5-engine\n                          └── feature/agent-phase-6-api\n                               └── feature/agent-phase-7-frontend\n                                    └── feature/agent-phase-8-production\n```\n\n**Per-phase workflow:**\n```bash\n# 1. Create branch from previous phase (or main for Phase 1)\ngit checkout -b feature/agent-phase-N-<name>\n\n# 2. Implement phase\n# 3. Run tests\njust test tests/<relevant>/ -v\n\n# 4. Update AGENT_IMPLEMENTATION_LOG.md with:\n#    - What was built (files, functions)\n#    - Test results\n#    - Any deviations from plan\n#    - Next phase handoff notes\n\n# 5. Commit and push\ngit add . && git commit -m \"Phase N: <description>\"\n\n# 6. Create PR, get tests green\n# 7. Merge to previous branch (or main)\n# 8. Start next phase from merged branch\n```\n\n---\n\n## Living Documentation: AGENT_IMPLEMENTATION_LOG.md\n\n**Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.\n\n**Location:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n\n**Structure:**\n```markdown\n# Agent Implementation Log\n\n## Current Status\n- **Current Phase:** 3 (Tool Layer)\n- **Current Branch:** feature/agent-phase-3-tools\n- **Last Updated:** 2025-01-04 14:30 UTC\n- **Blockers:** None\n\n## Phase Progress\n\n### Phase 1: Data Layer ✅ COMPLETE\n- **Branch:** feature/agent-phase-1-data-layer (merged to main)\n- **PR:** #123\n- **Files Created:**\n  - orchestrator/storage/schema.sql (added agent tables)\n  - orchestrator/schemas.py (added AgentStep, AgentToolCall, AgentCitation)\n  - orchestrator/storage/repositories/agent_repo.py\n  - tests/storage/test_agent_repo.py\n- **Test Results:** 12/12 passing\n- **Deviations:** None\n- **Handoff Notes:** Schema ready, repo tested with in-memory SQLite\n\n### Phase 2: Provider Chain ✅ COMPLETE\n- **Branch:** feature/agent-phase-2-provider-chain (merged)\n- **PR:** #124\n- **Files Created:** ...\n- **Test Results:** ...\n- **Deviations:** Changed circuit breaker threshold from 5 to 3\n- **Handoff Notes:** DeepInfra working, Together fallback tested\n\n### Phase 3: Tool Layer 🔄 IN PROGRESS\n- **Branch:** feature/agent-phase-3-tools\n- **Files Created So Far:**\n  - orchestrator/agent/tools/base.py ✅\n  - orchestrator/agent/tools/registry.py ✅\n  - orchestrator/agent/tools/web_search.py 🔄\n- **Current Task:** Implementing Parallel.ai search\n- **Blockers:** None\n- **Notes:** Using httpx for async HTTP\n\n## Quick Resume for New Chat\n1. Read this log first\n2. Checkout current branch: `git checkout feature/agent-phase-3-tools`\n3. Current task: Finish web_search.py, then web_extract.py\n4. Test with: `just test tests/agent/ -v`\n5. Reference: See plan file for full design details\n```\n\n**Update this doc at:**\n- Start of each phase\n- After each significant file completion\n- On any blocker or deviation\n- At phase completion"}
```
---
## USER (2026-01-04T10:50:17.651Z)


---
## ASSISTANT (2026-01-04T10:50:25.737Z)

<details><summary>Thinking...</summary>

Good. Now let me also add a "New Chat Handoff" section at the very top of the plan file to make it clear what new conversations should do:

</details>
---
## ASSISTANT (2026-01-04T10:50:26.076Z)

Now let me add a clear handoff section at the very top for new conversations:
---
## ASSISTANT (2026-01-04T10:50:30.922Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"# Web Research Agent - Production Implementation Plan\n\n## Overview","new_string":"# Web Research Agent - Production Implementation Plan\n\n---\n\n## 🚨 NEW CHAT? START HERE\n\n**If you're a new conversation picking this up:**\n\n1. **Read the implementation log first:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n   - Shows current phase, branch, what's done, what's in progress\n   - Has \"Quick Resume\" section with exact next steps\n\n2. **Checkout the current branch** (from implementation log)\n\n3. **This plan file** = design decisions & architecture\n   **Implementation log** = what's actually built & current state\n\n4. **After any work, update the implementation log** with:\n   - Files created/modified\n   - Test results\n   - Deviations from plan\n   - Handoff notes for next conversation\n\n---\n\n## Overview"}
```
---
## USER (2026-01-04T10:50:30.934Z)


---
## ASSISTANT (2026-01-04T10:50:40.750Z)

<details><summary>Thinking...</summary>

Good - the plan now has:1. New Chat handoff section at the top
2. Document status table including the live implementation log3. Branch strategy with per-phase branches
4. Living documentation structure (AGENT_IMPLEMENTATION_LOG.md)5. Existing codebase patterns to follow
6. Critical fixes7. 8 phased implementation
8. Consolidated file list9. Deployment steps and checklistLet me exit plan mode now.

</details>
---
## ASSISTANT (2026-01-04T10:50:43.748Z)

The plan now includes:

**For new chat handoff:**
- Clear "NEW CHAT? START HERE" section at top
- Document hierarchy (plan = design, implementation log = live state)
- Instructions to update the log after any work

**Branch strategy:**
- Each phase = own branch (feature/agent-phase-N-...)
- No merge until tests pass
- Workflow for each phase

**Living documentation:**
- `docs/AGENT_IMPLEMENTATION_LOG.md` structure defined
- Current status, per-phase progress, quick resume section
- Update triggers (phase start, file completion, blockers, phase end)
---
## ASSISTANT (2026-01-04T10:50:43.848Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n---\n\n## 🚨 NEW CHAT? START HERE\n\n**If you're a new conversation picking this up:**\n\n1. **Read the implementation log first:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n   - Shows current phase, branch, what's done, what's in progress\n   - Has \"Quick Resume\" section with exact next steps\n\n2. **Checkout the current branch** (from implementation log)\n\n3. **This plan file** = design decisions & architecture\n   **Implementation log** = what's actually built & current state\n\n4. **After any work, update the implementation log** with:\n   - Files created/modified\n   - Test results\n   - Deviations from plan\n   - Handoff notes for next conversation\n\n---\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Document Status\n\n| Document | Purpose | Status |\n|----------|---------|--------|\n| **This plan file** | Design & architecture decisions | ✅ Source of truth |\n| `docs/AGENT_IMPLEMENTATION_LOG.md` | **LIVE DOC** - Phase progress, what was built, handoff notes | 📝 Create at Phase 1 start |\n| `docs/AGENT_SYSTEM_DESIGN.md` | Full system design | ❌ Outdated - rewrite after Phase 8 |\n| `docs/AGENT_MASTER_REFERENCE.md` | Quick reference | ⚠️ Update after Phase 8 |\n\n---\n\n## Branch Strategy (CRITICAL)\n\nEach phase gets its own branch. **Do not merge until all tests pass.**\n\n```\nmain\n └── feature/agent-phase-1-data-layer\n      └── feature/agent-phase-2-provider-chain\n           └── feature/agent-phase-3-tools\n                └── feature/agent-phase-4-pruner-state\n                     └── feature/agent-phase-5-engine\n                          └── feature/agent-phase-6-api\n                               └── feature/agent-phase-7-frontend\n                                    └── feature/agent-phase-8-production\n```\n\n**Per-phase workflow:**\n```bash\n# 1. Create branch from previous phase (or main for Phase 1)\ngit checkout -b feature/agent-phase-N-<name>\n\n# 2. Implement phase\n# 3. Run tests\njust test tests/<relevant>/ -v\n\n# 4. Update AGENT_IMPLEMENTATION_LOG.md with:\n#    - What was built (files, functions)\n#    - Test results\n#    - Any deviations from plan\n#    - Next phase handoff notes\n\n# 5. Commit and push\ngit add . && git commit -m \"Phase N: <description>\"\n\n# 6. Create PR, get tests green\n# 7. Merge to previous branch (or main)\n# 8. Start next phase from merged branch\n```\n\n---\n\n## Living Documentation: AGENT_IMPLEMENTATION_LOG.md\n\n**Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.\n\n**Location:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n\n**Structure:**\n```markdown\n# Agent Implementation Log\n\n## Current Status\n- **Current Phase:** 3 (Tool Layer)\n- **Current Branch:** feature/agent-phase-3-tools\n- **Last Updated:** 2025-01-04 14:30 UTC\n- **Blockers:** None\n\n## Phase Progress\n\n### Phase 1: Data Layer ✅ COMPLETE\n- **Branch:** feature/agent-phase-1-data-layer (merged to main)\n- **PR:** #123\n- **Files Created:**\n  - orchestrator/storage/schema.sql (added agent tables)\n  - orchestrator/schemas.py (added AgentStep, AgentToolCall, AgentCitation)\n  - orchestrator/storage/repositories/agent_repo.py\n  - tests/storage/test_agent_repo.py\n- **Test Results:** 12/12 passing\n- **Deviations:** None\n- **Handoff Notes:** Schema ready, repo tested with in-memory SQLite\n\n### Phase 2: Provider Chain ✅ COMPLETE\n- **Branch:** feature/agent-phase-2-provider-chain (merged)\n- **PR:** #124\n- **Files Created:** ...\n- **Test Results:** ...\n- **Deviations:** Changed circuit breaker threshold from 5 to 3\n- **Handoff Notes:** DeepInfra working, Together fallback tested\n\n### Phase 3: Tool Layer 🔄 IN PROGRESS\n- **Branch:** feature/agent-phase-3-tools\n- **Files Created So Far:**\n  - orchestrator/agent/tools/base.py ✅\n  - orchestrator/agent/tools/registry.py ✅\n  - orchestrator/agent/tools/web_search.py 🔄\n- **Current Task:** Implementing Parallel.ai search\n- **Blockers:** None\n- **Notes:** Using httpx for async HTTP\n\n## Quick Resume for New Chat\n1. Read this log first\n2. Checkout current branch: `git checkout feature/agent-phase-3-tools`\n3. Current task: Finish web_search.py, then web_extract.py\n4. Test with: `just test tests/agent/ -v`\n5. Reference: See plan file for full design details\n```\n\n**Update this doc at:**\n- Start of each phase\n- After each significant file completion\n- On any blocker or deviation\n- At phase completion\n\n---\n\n## Existing Codebase Patterns (MUST FOLLOW)\n\n### Test Structure\n```\ntests/\n├── conftest.py                    # Global fixtures (event_loop, reset_trace_repo_lock)\n├── config/test_config.py          # Unit: config loading\n├── engine/test_chat_engine.py     # Unit: chat engine\n├── providers/                     # Unit: provider logic\n├── storage/                       # Unit: database, repos\n├── integration/\n│   ├── test_full_flow.py          # Integration: mocked provider, real DB\n│   └── test_e2e_flow.py           # E2E: FastAPI TestClient, HTTP endpoints\n```\n\n### Test Patterns Already Used\n- `@pytest.mark.asyncio` for async tests\n- `unittest.mock.AsyncMock` for async mocking\n- `patch(\"orchestrator.module.func\")` for patching\n- In-memory SQLite via fixture\n- Factory functions like `create_mock_provider(response_text)`\n\n### Scripts Already Available\n- `just test` - Run pytest\n- `just test-loop` - Run with log analysis\n- `just sanity` - Integration tests (requires API running)\n- `./scripts/test_loop.sh` - Test harness with error extraction\n- `./scripts/sanity_test.sh` - Full integration test\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway.\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification\n```\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Phased Implementation (Incremental with Testing)\n\nEach phase is **independently testable** before moving to the next. Testing, tracing, and observability are built into each phase.\n\n---\n\n### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass (use existing just command)\njust test tests/storage/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration (follow existing trace_repo.py pattern)\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations\n\n---\n\n### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files (following existing providers/ pattern):**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/providers/test_circuit_breaker.py      # Unit tests (matches existing test_openai_compat.py)\ntests/providers/test_provider_chain.py       # Unit tests\ntests/integration/test_provider_failover.py  # Integration test (matches test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\njust test tests/providers/test_circuit_breaker.py tests/providers/test_provider_chain.py -v\n\n# 2. Integration test (real API calls - optional, requires keys)\nDEEPINFRA_API_KEY=xxx just test tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures\n\n---\n\n### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files (new agent/ module):**\n```\norchestrator/agent/__init__.py               # Package init\norchestrator/agent/tools/__init__.py         # Tools package\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/agent/__init__.py                      # New test package\ntests/agent/test_tool_registry.py            # Unit tests\ntests/integration/test_agent_tools.py        # Integration: real APIs (optional)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs - always run)\njust test tests/agent/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs - optional, requires keys)\nPARALLEL_API_KEY=xxx E2B_API_KEY=xxx just test tests/integration/test_agent_tools.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged\n\n---\n\n### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/agent/test_context_pruner.py           # Unit tests\ntests/agent/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# All unit tests in one command\njust test tests/agent/test_context_pruner.py tests/agent/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions\n\n---\n\n### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/agent/test_recovery.py                 # Unit tests\ntests/agent/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py          # E2E (follows test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything - always run)\njust test tests/agent/test_recovery.py tests/agent/test_agent_engine.py -v\n\n# 2. E2E test (real APIs - optional, requires all keys)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  just test tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations\n\n---\n\n### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py          # API tests (follows test_e2e_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit/integration tests (mocked provider, uses TestClient)\njust test tests/integration/test_agent_api.py -v\n\n# 2. Start server for manual testing\njust dev\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Full integration (use existing sanity script pattern)\n./scripts/sanity_test.sh --debug\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API\n\n---\n\n### Phase 7: Frontend Integration\n**Goal:** UI shows thinking view and answer with citations.\n\n**Files:**\n```\nui/src/types/agent.ts                        # TypeScript types\nui/src/api/client.ts                         # Agent API client\nui/src/hooks/useStore.ts                     # Agent state\nui/src/hooks/useAgentSSE.ts                  # SSE with reconnection\nui/src/components/AgentThinkingPanel.tsx     # Tool calls display\nui/src/components/ToolCallCard.tsx           # Individual tool card\nui/src/components/CitationInline.tsx         # [1] style citations\nui/src/components/AnswerWithCitations.tsx    # Final answer\nui/src/components/ConversationView.tsx       # Integrate agent mode\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. TypeScript compiles\ncd ui && pnpm tsc --noEmit\n\n# 2. Manual testing\ncd ui && pnpm dev\n# Open browser, submit query, verify:\n# - Thinking panel shows tool calls\n# - Answer has inline citations\n# - SSE reconnects on disconnect\n```\n\n**Observability Built-in:**\n- Console logging for SSE events\n- Error boundary with error reporting\n- Performance timing in dev tools\n\n**Exit Criteria:** ✅ Full user flow works: query → thinking → answer with citations\n\n---\n\n### Phase 8: Production Hardening\n**Goal:** Deploy to Railway/Vercel, verify recovery and monitoring.\n\n**Tasks:**\n```\n1. Deploy backend to Railway\n2. Deploy frontend to Vercel\n3. Configure Turso database\n4. Set up monitoring/alerting\n5. Test crash recovery in production\n6. Load test with 10 concurrent queries\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Deploy\nrailway up\nvercel --prod\n\n# 2. Smoke test\ncurl https://your-api.railway.app/health\n\n# 3. Recovery test\n# Kill Railway instance mid-run, verify it resumes\n\n# 4. Load test\nhey -n 100 -c 10 https://your-api.railway.app/api/agent/runs\n```\n\n**Observability Built-in:**\n- Structured JSON logs → Railway logs\n- Error alerting via Railway\n- Latency percentiles\n\n**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n### Summary: All Files to Create/Modify\n\n**Backend (orchestrator/):**\n```\norchestrator/\n├── storage/\n│   ├── schema.sql                    # Phase 1: Add agent tables\n│   └── repositories/\n│       └── agent_repo.py             # Phase 1: CRUD operations\n├── schemas.py                        # Phase 1: Add agent Pydantic models\n├── config.py                         # Phase 2: Add provider chain config\n├── providers/\n│   ├── circuit_breaker.py            # Phase 2: Circuit breaker\n│   └── chain.py                      # Phase 2: Provider failover\n├── agent/\n│   ├── __init__.py                   # Phase 3\n│   ├── tools/\n│   │   ├── __init__.py               # Phase 3\n│   │   ├── base.py                   # Phase 3: BaseTool ABC\n│   │   ├── registry.py               # Phase 3: Tool registry\n│   │   ├── web_search.py             # Phase 3: Parallel.ai search\n│   │   ├── web_extract.py            # Phase 3: Parallel.ai extract\n│   │   └── python_sandbox.py         # Phase 3: E2B sandbox\n│   ├── context_pruner.py             # Phase 4: Token management\n│   ├── state_machine.py              # Phase 4: State transitions\n│   ├── recovery.py                   # Phase 5: Crash recovery + hints\n│   └── agent_engine.py               # Phase 5: Main loop\n├── routes/\n│   └── agent.py                      # Phase 6: HTTP + SSE endpoints\n└── app.py                            # Phase 6: Register router\n```\n\n**Tests (tests/):**\n```\ntests/\n├── storage/\n│   └── test_agent_repo.py            # Phase 1\n├── providers/\n│   ├── test_circuit_breaker.py       # Phase 2\n│   └── test_provider_chain.py        # Phase 2\n├── agent/\n│   ├── __init__.py\n│   ├── test_tool_registry.py         # Phase 3\n│   ├── test_context_pruner.py        # Phase 4\n│   ├── test_state_machine.py         # Phase 4\n│   ├── test_recovery.py              # Phase 5\n│   └── test_agent_engine.py          # Phase 5\n└── integration/\n    ├── test_provider_failover.py     # Phase 2 (optional)\n    ├── test_agent_tools.py           # Phase 3 (optional)\n    ├── test_agent_e2e.py             # Phase 5 (optional)\n    └── test_agent_api.py             # Phase 6\n```\n\n**Frontend (ui/src/):**\n```\nui/src/\n├── types/\n│   └── agent.ts                      # Phase 7\n├── api/\n│   └── client.ts                     # Phase 7: Add agent methods\n├── hooks/\n│   ├── useStore.ts                   # Phase 7: Add agent state\n│   └── useAgentSSE.ts                # Phase 7: SSE hook\n└── components/\n    ├── AgentThinkingPanel.tsx        # Phase 7\n    ├── ToolCallCard.tsx              # Phase 7\n    ├── CitationInline.tsx            # Phase 7\n    ├── AnswerWithCitations.tsx       # Phase 7\n    └── ConversationView.tsx          # Phase 7: Modify for agent mode\n```\n\n**Docs (to update after implementation):**\n```\ndocs/\n├── AGENT_SYSTEM_DESIGN.md            # Rewrite with all 6 fixes\n└── AGENT_MASTER_REFERENCE.md         # Quick reference\n```\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T10:51:14.994Z)


---
## ASSISTANT (2026-01-04T10:51:26.577Z)

<details><summary>Thinking...</summary>

The user is right - I've described the AGENT_IMPLEMENTATION_LOG.md structure in the plan file, but I haven't actually created it yet. Also, the AGENT_MASTER_REFERENCE.md I created earlier needs to be checked - the user said those links may not have updated info.

In plan mode, I can only edit the plan file. The actual docs need to be created when we exit plan mode. But the user wants to see them now.

Actually, wait - I think the user wants me to create the actual implementation log file NOW before exiting plan mode. But I'm in plan mode and can only edit the plan file...

Let me clarify - I should note in the plan that these docs will be created as part of Phase 1 start. Or maybe the user wants me to exit plan mode and then create them?

Let me ask the user to clarify.

Actually, looking at this more carefully - I created AGENT_MASTER_REFERENCE.md earlier but that file is outside of plan mode editing. The user is saying they don't see the docs anywhere - maybe the file I wrote didn't save properly or they can't find it?

Let me check what exists in the docs folder.

</details>
---
## ASSISTANT (2026-01-04T10:51:27.042Z)

Let me check what docs currently exist:
---
## ASSISTANT (2026-01-04T10:51:27.287Z)

**Tool Use:** Glob
```json
{"pattern":"docs/**/*.md"}
```
---
## USER (2026-01-04T10:51:28.141Z)


---
## ASSISTANT (2026-01-04T10:51:36.659Z)

<details><summary>Thinking...</summary>

So the docs exist:- AGENT_MASTER_REFERENCE.md - I created this earlier- AGENT_SYSTEM_DESIGN.md - exists but outdatedBut there's no AGENT_IMPLEMENTATION_LOG.md yet - that needs to be created when Phase 1 starts.The user said "i dont see the docs anywhere" - they might mean:1. The docs aren't in the IDE or git yet (not committed)2. The AGENT_IMPLEMENTATION_LOG.md doesn't exist yet
3. The existing docs are outdated and don't reflect the planLet me read the AGENT_MASTER_REFERENCE.md to see what's there and if it needs updating:

</details>
---
## ASSISTANT (2026-01-04T10:51:37.615Z)

**Tool Use:** Read
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_MASTER_REFERENCE.md"}
```
---
## USER (2026-01-04T10:51:37.642Z)


---
## ASSISTANT (2026-01-04T10:51:47.394Z)

<details><summary>Thinking...</summary>

Ah I see! The AGENT_MASTER_REFERENCE.md exists and has the correct info (DeepInfra primary, E2B sandbox, all 6 critical fixes). But:

1. AGENT_IMPLEMENTATION_LOG.md doesn't exist yet - that's the live doc that needs to be created
2. AGENT_SYSTEM_DESIGN.md is outdated (still has Docker, Together AI, etc.)

The user said "i dont see the docs anywhere" - they might be referring to:
1. The files are not committed to git yet (just in the working directory)
2. The AGENT_IMPLEMENTATION_LOG.md doesn't exist

Since I'm in plan mode, I cannot create new files outside of the plan file. But I need to clarify with the user what they want.

Let me note in the plan file that when we exit plan mode, the first action will be to create AGENT_IMPLEMENTATION_LOG.md and update the other docs.

</details>
---
## ASSISTANT (2026-01-04T10:51:51.495Z)

I see the current docs situation:

**EXISTS:**
- `docs/AGENT_MASTER_REFERENCE.md` - Has correct info (DeepInfra, E2B, 6 fixes)
- `docs/AGENT_SYSTEM_DESIGN.md` - Outdated (Docker, Together AI)

**MISSING:**
- `docs/AGENT_IMPLEMENTATION_LOG.md` - The live doc (needs to be created)

These files exist on disk but may not be committed to git yet. In plan mode I can only edit the plan file. Let me update the plan to make it clear that creating the implementation log is the FIRST action when we start Phase 1:
---
## ASSISTANT (2026-01-04T10:51:59.118Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```","new_string":"### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**FIRST ACTION (before any code):**\n```bash\n# 1. Create implementation log\ntouch docs/AGENT_IMPLEMENTATION_LOG.md\n# (populate with initial template from plan)\n\n# 2. Create branch\ngit checkout -b feature/agent-phase-1-data-layer\n\n# 3. Commit log + any doc updates\ngit add docs/ && git commit -m \"Phase 1: Initialize implementation log\"\n```\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```"}
```
---
## USER (2026-01-04T10:51:59.132Z)


---
## ASSISTANT (2026-01-04T10:52:04.030Z)

<details><summary>Thinking...</summary>

Let me also add a note about which docs exist and their status:

</details>
---
## ASSISTANT (2026-01-04T10:52:13.954Z)

**Tool Use:** Edit
```json
{"file_path":"/Users/anudeepgadige/.claude/plans/lazy-purring-nygaard.md","old_string":"## Document Status\n\n| Document | Purpose | Status |\n|----------|---------|--------|\n| **This plan file** | Design & architecture decisions | ✅ Source of truth |\n| `docs/AGENT_IMPLEMENTATION_LOG.md` | **LIVE DOC** - Phase progress, what was built, handoff notes | 📝 Create at Phase 1 start |\n| `docs/AGENT_SYSTEM_DESIGN.md` | Full system design | ❌ Outdated - rewrite after Phase 8 |\n| `docs/AGENT_MASTER_REFERENCE.md` | Quick reference | ⚠️ Update after Phase 8 |","new_string":"## Document Status\n\n| Document | Purpose | Status | Location |\n|----------|---------|--------|----------|\n| **This plan file** | Design & architecture decisions | ✅ Source of truth | `.claude/plans/lazy-purring-nygaard.md` |\n| `AGENT_IMPLEMENTATION_LOG.md` | **LIVE DOC** - Phase progress, handoff | 📝 Create at Phase 1 start | `docs/AGENT_IMPLEMENTATION_LOG.md` |\n| `AGENT_MASTER_REFERENCE.md` | Quick reference (schema, API, fixes) | ✅ Updated | `docs/AGENT_MASTER_REFERENCE.md` |\n| `AGENT_SYSTEM_DESIGN.md` | Full system design | ❌ Outdated (Docker, Together) | `docs/AGENT_SYSTEM_DESIGN.md` |\n\n**Current doc files in repo:**\n```\ndocs/\n├── AGENT_MASTER_REFERENCE.md    # ✅ Has: DeepInfra, E2B, 6 fixes, schema, API\n├── AGENT_SYSTEM_DESIGN.md       # ❌ Outdated: Docker, Together AI primary\n├── AGENT_DESIGN.md              # Old design notes\n├── AGENT_ARCHITECTURE_RESEARCH.md # Research notes\n└── SYSTEM_DESIGN.md             # General system design\n```"}
```
---
## USER (2026-01-04T10:52:13.967Z)


---
## ASSISTANT (2026-01-04T10:52:20.028Z)

<details><summary>Thinking...</summary>

Now the plan is clear about:
1. What docs exist and their status
2. AGENT_IMPLEMENTATION_LOG.md will be created at Phase 1 start
3. AGENT_MASTER_REFERENCE.md already has the correct updated infoLet me exit plan mode now. When we start implementation, the first action will be to create the implementation log.

</details>
---
## ASSISTANT (2026-01-04T10:52:24.652Z)

Now the plan clearly shows:

1. **Existing docs and their status:**
   - `AGENT_MASTER_REFERENCE.md` - ✅ Already has correct info (DeepInfra, E2B, 6 fixes)
   - `AGENT_SYSTEM_DESIGN.md` - ❌ Outdated (needs rewrite)
   - `AGENT_IMPLEMENTATION_LOG.md` - 📝 Will be created at Phase 1 start

2. **Phase 1 starts with:**
   - Create `AGENT_IMPLEMENTATION_LOG.md` (the live doc)
   - Create branch
   - Commit docs before any code

3. **New chat handoff** works via:
   - Plan file (`.claude/plans/lazy-purring-nygaard.md`) - architecture
   - Implementation log (`docs/AGENT_IMPLEMENTATION_LOG.md`) - current state
   - Master reference (`docs/AGENT_MASTER_REFERENCE.md`) - quick lookup
---
## ASSISTANT (2026-01-04T10:52:24.970Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n---\n\n## 🚨 NEW CHAT? START HERE\n\n**If you're a new conversation picking this up:**\n\n1. **Read the implementation log first:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n   - Shows current phase, branch, what's done, what's in progress\n   - Has \"Quick Resume\" section with exact next steps\n\n2. **Checkout the current branch** (from implementation log)\n\n3. **This plan file** = design decisions & architecture\n   **Implementation log** = what's actually built & current state\n\n4. **After any work, update the implementation log** with:\n   - Files created/modified\n   - Test results\n   - Deviations from plan\n   - Handoff notes for next conversation\n\n---\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Document Status\n\n| Document | Purpose | Status | Location |\n|----------|---------|--------|----------|\n| **This plan file** | Design & architecture decisions | ✅ Source of truth | `.claude/plans/lazy-purring-nygaard.md` |\n| `AGENT_IMPLEMENTATION_LOG.md` | **LIVE DOC** - Phase progress, handoff | 📝 Create at Phase 1 start | `docs/AGENT_IMPLEMENTATION_LOG.md` |\n| `AGENT_MASTER_REFERENCE.md` | Quick reference (schema, API, fixes) | ✅ Updated | `docs/AGENT_MASTER_REFERENCE.md` |\n| `AGENT_SYSTEM_DESIGN.md` | Full system design | ❌ Outdated (Docker, Together) | `docs/AGENT_SYSTEM_DESIGN.md` |\n\n**Current doc files in repo:**\n```\ndocs/\n├── AGENT_MASTER_REFERENCE.md    # ✅ Has: DeepInfra, E2B, 6 fixes, schema, API\n├── AGENT_SYSTEM_DESIGN.md       # ❌ Outdated: Docker, Together AI primary\n├── AGENT_DESIGN.md              # Old design notes\n├── AGENT_ARCHITECTURE_RESEARCH.md # Research notes\n└── SYSTEM_DESIGN.md             # General system design\n```\n\n---\n\n## Branch Strategy (CRITICAL)\n\nEach phase gets its own branch. **Do not merge until all tests pass.**\n\n```\nmain\n └── feature/agent-phase-1-data-layer\n      └── feature/agent-phase-2-provider-chain\n           └── feature/agent-phase-3-tools\n                └── feature/agent-phase-4-pruner-state\n                     └── feature/agent-phase-5-engine\n                          └── feature/agent-phase-6-api\n                               └── feature/agent-phase-7-frontend\n                                    └── feature/agent-phase-8-production\n```\n\n**Per-phase workflow:**\n```bash\n# 1. Create branch from previous phase (or main for Phase 1)\ngit checkout -b feature/agent-phase-N-<name>\n\n# 2. Implement phase\n# 3. Run tests\njust test tests/<relevant>/ -v\n\n# 4. Update AGENT_IMPLEMENTATION_LOG.md with:\n#    - What was built (files, functions)\n#    - Test results\n#    - Any deviations from plan\n#    - Next phase handoff notes\n\n# 5. Commit and push\ngit add . && git commit -m \"Phase N: <description>\"\n\n# 6. Create PR, get tests green\n# 7. Merge to previous branch (or main)\n# 8. Start next phase from merged branch\n```\n\n---\n\n## Living Documentation: AGENT_IMPLEMENTATION_LOG.md\n\n**Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.\n\n**Location:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n\n**Structure:**\n```markdown\n# Agent Implementation Log\n\n## Current Status\n- **Current Phase:** 3 (Tool Layer)\n- **Current Branch:** feature/agent-phase-3-tools\n- **Last Updated:** 2025-01-04 14:30 UTC\n- **Blockers:** None\n\n## Phase Progress\n\n### Phase 1: Data Layer ✅ COMPLETE\n- **Branch:** feature/agent-phase-1-data-layer (merged to main)\n- **PR:** #123\n- **Files Created:**\n  - orchestrator/storage/schema.sql (added agent tables)\n  - orchestrator/schemas.py (added AgentStep, AgentToolCall, AgentCitation)\n  - orchestrator/storage/repositories/agent_repo.py\n  - tests/storage/test_agent_repo.py\n- **Test Results:** 12/12 passing\n- **Deviations:** None\n- **Handoff Notes:** Schema ready, repo tested with in-memory SQLite\n\n### Phase 2: Provider Chain ✅ COMPLETE\n- **Branch:** feature/agent-phase-2-provider-chain (merged)\n- **PR:** #124\n- **Files Created:** ...\n- **Test Results:** ...\n- **Deviations:** Changed circuit breaker threshold from 5 to 3\n- **Handoff Notes:** DeepInfra working, Together fallback tested\n\n### Phase 3: Tool Layer 🔄 IN PROGRESS\n- **Branch:** feature/agent-phase-3-tools\n- **Files Created So Far:**\n  - orchestrator/agent/tools/base.py ✅\n  - orchestrator/agent/tools/registry.py ✅\n  - orchestrator/agent/tools/web_search.py 🔄\n- **Current Task:** Implementing Parallel.ai search\n- **Blockers:** None\n- **Notes:** Using httpx for async HTTP\n\n## Quick Resume for New Chat\n1. Read this log first\n2. Checkout current branch: `git checkout feature/agent-phase-3-tools`\n3. Current task: Finish web_search.py, then web_extract.py\n4. Test with: `just test tests/agent/ -v`\n5. Reference: See plan file for full design details\n```\n\n**Update this doc at:**\n- Start of each phase\n- After each significant file completion\n- On any blocker or deviation\n- At phase completion\n\n---\n\n## Existing Codebase Patterns (MUST FOLLOW)\n\n### Test Structure\n```\ntests/\n├── conftest.py                    # Global fixtures (event_loop, reset_trace_repo_lock)\n├── config/test_config.py          # Unit: config loading\n├── engine/test_chat_engine.py     # Unit: chat engine\n├── providers/                     # Unit: provider logic\n├── storage/                       # Unit: database, repos\n├── integration/\n│   ├── test_full_flow.py          # Integration: mocked provider, real DB\n│   └── test_e2e_flow.py           # E2E: FastAPI TestClient, HTTP endpoints\n```\n\n### Test Patterns Already Used\n- `@pytest.mark.asyncio` for async tests\n- `unittest.mock.AsyncMock` for async mocking\n- `patch(\"orchestrator.module.func\")` for patching\n- In-memory SQLite via fixture\n- Factory functions like `create_mock_provider(response_text)`\n\n### Scripts Already Available\n- `just test` - Run pytest\n- `just test-loop` - Run with log analysis\n- `just sanity` - Integration tests (requires API running)\n- `./scripts/test_loop.sh` - Test harness with error extraction\n- `./scripts/sanity_test.sh` - Full integration test\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway.\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification\n```\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Phased Implementation (Incremental with Testing)\n\nEach phase is **independently testable** before moving to the next. Testing, tracing, and observability are built into each phase.\n\n---\n\n### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**FIRST ACTION (before any code):**\n```bash\n# 1. Create implementation log\ntouch docs/AGENT_IMPLEMENTATION_LOG.md\n# (populate with initial template from plan)\n\n# 2. Create branch\ngit checkout -b feature/agent-phase-1-data-layer\n\n# 3. Commit log + any doc updates\ngit add docs/ && git commit -m \"Phase 1: Initialize implementation log\"\n```\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass (use existing just command)\njust test tests/storage/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration (follow existing trace_repo.py pattern)\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations\n\n---\n\n### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files (following existing providers/ pattern):**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/providers/test_circuit_breaker.py      # Unit tests (matches existing test_openai_compat.py)\ntests/providers/test_provider_chain.py       # Unit tests\ntests/integration/test_provider_failover.py  # Integration test (matches test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\njust test tests/providers/test_circuit_breaker.py tests/providers/test_provider_chain.py -v\n\n# 2. Integration test (real API calls - optional, requires keys)\nDEEPINFRA_API_KEY=xxx just test tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures\n\n---\n\n### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files (new agent/ module):**\n```\norchestrator/agent/__init__.py               # Package init\norchestrator/agent/tools/__init__.py         # Tools package\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/agent/__init__.py                      # New test package\ntests/agent/test_tool_registry.py            # Unit tests\ntests/integration/test_agent_tools.py        # Integration: real APIs (optional)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs - always run)\njust test tests/agent/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs - optional, requires keys)\nPARALLEL_API_KEY=xxx E2B_API_KEY=xxx just test tests/integration/test_agent_tools.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged\n\n---\n\n### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/agent/test_context_pruner.py           # Unit tests\ntests/agent/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# All unit tests in one command\njust test tests/agent/test_context_pruner.py tests/agent/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions\n\n---\n\n### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/agent/test_recovery.py                 # Unit tests\ntests/agent/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py          # E2E (follows test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything - always run)\njust test tests/agent/test_recovery.py tests/agent/test_agent_engine.py -v\n\n# 2. E2E test (real APIs - optional, requires all keys)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  just test tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations\n\n---\n\n### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py          # API tests (follows test_e2e_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit/integration tests (mocked provider, uses TestClient)\njust test tests/integration/test_agent_api.py -v\n\n# 2. Start server for manual testing\njust dev\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Full integration (use existing sanity script pattern)\n./scripts/sanity_test.sh --debug\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API\n\n---\n\n### Phase 7: Frontend Integration\n**Goal:** UI shows thinking view and answer with citations.\n\n**Files:**\n```\nui/src/types/agent.ts                        # TypeScript types\nui/src/api/client.ts                         # Agent API client\nui/src/hooks/useStore.ts                     # Agent state\nui/src/hooks/useAgentSSE.ts                  # SSE with reconnection\nui/src/components/AgentThinkingPanel.tsx     # Tool calls display\nui/src/components/ToolCallCard.tsx           # Individual tool card\nui/src/components/CitationInline.tsx         # [1] style citations\nui/src/components/AnswerWithCitations.tsx    # Final answer\nui/src/components/ConversationView.tsx       # Integrate agent mode\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. TypeScript compiles\ncd ui && pnpm tsc --noEmit\n\n# 2. Manual testing\ncd ui && pnpm dev\n# Open browser, submit query, verify:\n# - Thinking panel shows tool calls\n# - Answer has inline citations\n# - SSE reconnects on disconnect\n```\n\n**Observability Built-in:**\n- Console logging for SSE events\n- Error boundary with error reporting\n- Performance timing in dev tools\n\n**Exit Criteria:** ✅ Full user flow works: query → thinking → answer with citations\n\n---\n\n### Phase 8: Production Hardening\n**Goal:** Deploy to Railway/Vercel, verify recovery and monitoring.\n\n**Tasks:**\n```\n1. Deploy backend to Railway\n2. Deploy frontend to Vercel\n3. Configure Turso database\n4. Set up monitoring/alerting\n5. Test crash recovery in production\n6. Load test with 10 concurrent queries\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Deploy\nrailway up\nvercel --prod\n\n# 2. Smoke test\ncurl https://your-api.railway.app/health\n\n# 3. Recovery test\n# Kill Railway instance mid-run, verify it resumes\n\n# 4. Load test\nhey -n 100 -c 10 https://your-api.railway.app/api/agent/runs\n```\n\n**Observability Built-in:**\n- Structured JSON logs → Railway logs\n- Error alerting via Railway\n- Latency percentiles\n\n**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n### Summary: All Files to Create/Modify\n\n**Backend (orchestrator/):**\n```\norchestrator/\n├── storage/\n│   ├── schema.sql                    # Phase 1: Add agent tables\n│   └── repositories/\n│       └── agent_repo.py             # Phase 1: CRUD operations\n├── schemas.py                        # Phase 1: Add agent Pydantic models\n├── config.py                         # Phase 2: Add provider chain config\n├── providers/\n│   ├── circuit_breaker.py            # Phase 2: Circuit breaker\n│   └── chain.py                      # Phase 2: Provider failover\n├── agent/\n│   ├── __init__.py                   # Phase 3\n│   ├── tools/\n│   │   ├── __init__.py               # Phase 3\n│   │   ├── base.py                   # Phase 3: BaseTool ABC\n│   │   ├── registry.py               # Phase 3: Tool registry\n│   │   ├── web_search.py             # Phase 3: Parallel.ai search\n│   │   ├── web_extract.py            # Phase 3: Parallel.ai extract\n│   │   └── python_sandbox.py         # Phase 3: E2B sandbox\n│   ├── context_pruner.py             # Phase 4: Token management\n│   ├── state_machine.py              # Phase 4: State transitions\n│   ├── recovery.py                   # Phase 5: Crash recovery + hints\n│   └── agent_engine.py               # Phase 5: Main loop\n├── routes/\n│   └── agent.py                      # Phase 6: HTTP + SSE endpoints\n└── app.py                            # Phase 6: Register router\n```\n\n**Tests (tests/):**\n```\ntests/\n├── storage/\n│   └── test_agent_repo.py            # Phase 1\n├── providers/\n│   ├── test_circuit_breaker.py       # Phase 2\n│   └── test_provider_chain.py        # Phase 2\n├── agent/\n│   ├── __init__.py\n│   ├── test_tool_registry.py         # Phase 3\n│   ├── test_context_pruner.py        # Phase 4\n│   ├── test_state_machine.py         # Phase 4\n│   ├── test_recovery.py              # Phase 5\n│   └── test_agent_engine.py          # Phase 5\n└── integration/\n    ├── test_provider_failover.py     # Phase 2 (optional)\n    ├── test_agent_tools.py           # Phase 3 (optional)\n    ├── test_agent_e2e.py             # Phase 5 (optional)\n    └── test_agent_api.py             # Phase 6\n```\n\n**Frontend (ui/src/):**\n```\nui/src/\n├── types/\n│   └── agent.ts                      # Phase 7\n├── api/\n│   └── client.ts                     # Phase 7: Add agent methods\n├── hooks/\n│   ├── useStore.ts                   # Phase 7: Add agent state\n│   └── useAgentSSE.ts                # Phase 7: SSE hook\n└── components/\n    ├── AgentThinkingPanel.tsx        # Phase 7\n    ├── ToolCallCard.tsx              # Phase 7\n    ├── CitationInline.tsx            # Phase 7\n    ├── AnswerWithCitations.tsx       # Phase 7\n    └── ConversationView.tsx          # Phase 7: Modify for agent mode\n```\n\n**Docs (to update after implementation):**\n```\ndocs/\n├── AGENT_SYSTEM_DESIGN.md            # Rewrite with all 6 fixes\n└── AGENT_MASTER_REFERENCE.md         # Quick reference\n```\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T10:54:18.257Z)


---
## ASSISTANT (2026-01-04T10:54:22.886Z)

<details><summary>Thinking...</summary>

The user wants me to actually create the docs NOW, but I'm in plan mode where I can only edit the plan file. I need to ask the user if I should exit plan mode so I can create the actual docs, or if they want to switch me out of plan mode.

Let me ask them directly.

</details>
---
## ASSISTANT (2026-01-04T10:54:24.211Z)

I understand. I'm currently in **plan mode** where I can only edit the plan file - I cannot create new files like `AGENT_IMPLEMENTATION_LOG.md` until you approve exiting plan mode.
---
## ASSISTANT (2026-01-04T10:54:27.381Z)

**Tool Use:** AskUserQuestion
```json
{"questions":[{"question":"Should I exit plan mode now so I can create the actual documentation files?","header":"Next step","options":[{"label":"Yes, exit and create docs","description":"Exit plan mode, create AGENT_IMPLEMENTATION_LOG.md, update AGENT_SYSTEM_DESIGN.md with all fixes"},{"label":"Stay in plan, add more detail","description":"Keep planning - add more detail to the plan file first"}],"multiSelect":false}]}
```
---
## USER (2026-01-04T10:54:43.447Z)


---
## ASSISTANT (2026-01-04T10:54:47.108Z)

<details><summary>Thinking...</summary>

The user wants me to exit plan mode and create the docs. Let me do that.

</details>
---
## ASSISTANT (2026-01-04T10:54:47.269Z)

**Tool Use:** ExitPlanMode
```json
{"plan":"# Web Research Agent - Production Implementation Plan\n\n---\n\n## 🚨 NEW CHAT? START HERE\n\n**If you're a new conversation picking this up:**\n\n1. **Read the implementation log first:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n   - Shows current phase, branch, what's done, what's in progress\n   - Has \"Quick Resume\" section with exact next steps\n\n2. **Checkout the current branch** (from implementation log)\n\n3. **This plan file** = design decisions & architecture\n   **Implementation log** = what's actually built & current state\n\n4. **After any work, update the implementation log** with:\n   - Files created/modified\n   - Test results\n   - Deviations from plan\n   - Handoff notes for next conversation\n\n---\n\n## Overview\n\nBuild a production-grade web research agent with:\n- **Tools**: Parallel.ai (search/extract) + Python sandbox (E2B)\n- **Model**: gpt-oss-120b via Harmony-compatible provider\n- **UI**: Thinking view (tool calls/summaries) + Answer view (citations)\n- **Non-negotiables**: Full tracing, durability, crash recovery, evidence-grounded answers\n\n---\n\n## Document Status\n\n| Document | Purpose | Status | Location |\n|----------|---------|--------|----------|\n| **This plan file** | Design & architecture decisions | ✅ Source of truth | `.claude/plans/lazy-purring-nygaard.md` |\n| `AGENT_IMPLEMENTATION_LOG.md` | **LIVE DOC** - Phase progress, handoff | 📝 Create at Phase 1 start | `docs/AGENT_IMPLEMENTATION_LOG.md` |\n| `AGENT_MASTER_REFERENCE.md` | Quick reference (schema, API, fixes) | ✅ Updated | `docs/AGENT_MASTER_REFERENCE.md` |\n| `AGENT_SYSTEM_DESIGN.md` | Full system design | ❌ Outdated (Docker, Together) | `docs/AGENT_SYSTEM_DESIGN.md` |\n\n**Current doc files in repo:**\n```\ndocs/\n├── AGENT_MASTER_REFERENCE.md    # ✅ Has: DeepInfra, E2B, 6 fixes, schema, API\n├── AGENT_SYSTEM_DESIGN.md       # ❌ Outdated: Docker, Together AI primary\n├── AGENT_DESIGN.md              # Old design notes\n├── AGENT_ARCHITECTURE_RESEARCH.md # Research notes\n└── SYSTEM_DESIGN.md             # General system design\n```\n\n---\n\n## Branch Strategy (CRITICAL)\n\nEach phase gets its own branch. **Do not merge until all tests pass.**\n\n```\nmain\n └── feature/agent-phase-1-data-layer\n      └── feature/agent-phase-2-provider-chain\n           └── feature/agent-phase-3-tools\n                └── feature/agent-phase-4-pruner-state\n                     └── feature/agent-phase-5-engine\n                          └── feature/agent-phase-6-api\n                               └── feature/agent-phase-7-frontend\n                                    └── feature/agent-phase-8-production\n```\n\n**Per-phase workflow:**\n```bash\n# 1. Create branch from previous phase (or main for Phase 1)\ngit checkout -b feature/agent-phase-N-<name>\n\n# 2. Implement phase\n# 3. Run tests\njust test tests/<relevant>/ -v\n\n# 4. Update AGENT_IMPLEMENTATION_LOG.md with:\n#    - What was built (files, functions)\n#    - Test results\n#    - Any deviations from plan\n#    - Next phase handoff notes\n\n# 5. Commit and push\ngit add . && git commit -m \"Phase N: <description>\"\n\n# 6. Create PR, get tests green\n# 7. Merge to previous branch (or main)\n# 8. Start next phase from merged branch\n```\n\n---\n\n## Living Documentation: AGENT_IMPLEMENTATION_LOG.md\n\n**Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.\n\n**Location:** `docs/AGENT_IMPLEMENTATION_LOG.md`\n\n**Structure:**\n```markdown\n# Agent Implementation Log\n\n## Current Status\n- **Current Phase:** 3 (Tool Layer)\n- **Current Branch:** feature/agent-phase-3-tools\n- **Last Updated:** 2025-01-04 14:30 UTC\n- **Blockers:** None\n\n## Phase Progress\n\n### Phase 1: Data Layer ✅ COMPLETE\n- **Branch:** feature/agent-phase-1-data-layer (merged to main)\n- **PR:** #123\n- **Files Created:**\n  - orchestrator/storage/schema.sql (added agent tables)\n  - orchestrator/schemas.py (added AgentStep, AgentToolCall, AgentCitation)\n  - orchestrator/storage/repositories/agent_repo.py\n  - tests/storage/test_agent_repo.py\n- **Test Results:** 12/12 passing\n- **Deviations:** None\n- **Handoff Notes:** Schema ready, repo tested with in-memory SQLite\n\n### Phase 2: Provider Chain ✅ COMPLETE\n- **Branch:** feature/agent-phase-2-provider-chain (merged)\n- **PR:** #124\n- **Files Created:** ...\n- **Test Results:** ...\n- **Deviations:** Changed circuit breaker threshold from 5 to 3\n- **Handoff Notes:** DeepInfra working, Together fallback tested\n\n### Phase 3: Tool Layer 🔄 IN PROGRESS\n- **Branch:** feature/agent-phase-3-tools\n- **Files Created So Far:**\n  - orchestrator/agent/tools/base.py ✅\n  - orchestrator/agent/tools/registry.py ✅\n  - orchestrator/agent/tools/web_search.py 🔄\n- **Current Task:** Implementing Parallel.ai search\n- **Blockers:** None\n- **Notes:** Using httpx for async HTTP\n\n## Quick Resume for New Chat\n1. Read this log first\n2. Checkout current branch: `git checkout feature/agent-phase-3-tools`\n3. Current task: Finish web_search.py, then web_extract.py\n4. Test with: `just test tests/agent/ -v`\n5. Reference: See plan file for full design details\n```\n\n**Update this doc at:**\n- Start of each phase\n- After each significant file completion\n- On any blocker or deviation\n- At phase completion\n\n---\n\n## Existing Codebase Patterns (MUST FOLLOW)\n\n### Test Structure\n```\ntests/\n├── conftest.py                    # Global fixtures (event_loop, reset_trace_repo_lock)\n├── config/test_config.py          # Unit: config loading\n├── engine/test_chat_engine.py     # Unit: chat engine\n├── providers/                     # Unit: provider logic\n├── storage/                       # Unit: database, repos\n├── integration/\n│   ├── test_full_flow.py          # Integration: mocked provider, real DB\n│   └── test_e2e_flow.py           # E2E: FastAPI TestClient, HTTP endpoints\n```\n\n### Test Patterns Already Used\n- `@pytest.mark.asyncio` for async tests\n- `unittest.mock.AsyncMock` for async mocking\n- `patch(\"orchestrator.module.func\")` for patching\n- In-memory SQLite via fixture\n- Factory functions like `create_mock_provider(response_text)`\n\n### Scripts Already Available\n- `just test` - Run pytest\n- `just test-loop` - Run with log analysis\n- `just sanity` - Integration tests (requires API running)\n- `./scripts/test_loop.sh` - Test harness with error extraction\n- `./scripts/sanity_test.sh` - Full integration test\n\n---\n\n## Critical Fixes Applied\n\n| Issue | Problem | Solution |\n|-------|---------|----------|\n| **1. Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon | Use E2B external sandbox API (100 free credits) |\n| **2. Token Blowout** | Tool results accumulate → context exceeds 128k | Context Pruner: summarize old tool results to 1-line |\n| **3. Zombie Containers** | Orphan sessions if backend crashes | E2B session cleanup on startup |\n| **4. Non-Idempotent Recovery** | python_execute crash → lost result → hallucination | Inject system hint: \"execution interrupted, re-run\" |\n| **5. Provider Economics** | Together AI is 60% more expensive | DeepInfra primary ($0.09), Together fallback |\n| **6. WAL Bloat** | Storing result_raw → gigabyte WAL files | Store only result_summary, no raw blobs in SQLite |\n\n---\n\n## 1. Model Provider Selection\n\n### Provider Comparison\n\n| Provider | Price (input/output per 1M) | Latency | Tool Calling | Harmony Support | SLA |\n|----------|----------------------------|---------|--------------|-----------------|-----|\n| [DeepInfra](https://deepinfra.com/openai/gpt-oss-120b) | $0.09 / $0.36 | Low | Yes | Native | 99.5% |\n| [Together AI](https://www.together.ai/models/gpt-oss-120b) | $0.15 / $0.60 | Low | Yes | Native | 99.9% |\n| [OpenRouter](https://openrouter.ai/openai/gpt-oss-120b) | Variable | Variable | Yes | Yes | Varies |\n\n### Recommendation: DeepInfra (Primary) + Together AI (Fallback)\n\n**Why DeepInfra primary:**\n- ~40% cheaper ($0.09 vs $0.15 per 1M input tokens)\n- Same open-weights model = identical quality\n- Native Harmony format support\n- OpenAI-compatible API (drop-in replacement)\n- For a research project, cost savings matter\n\n**Together AI as fallback:**\n- Higher SLA (99.9% vs 99.5%) makes it reliable backup\n- Well-tested tool calling support\n\n**Failover strategy:**\n```\nRequest → DeepInfra (cheaper)\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI (reliable fallback)\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Harmony Format Requirement\n\ngpt-oss-120b REQUIRES Harmony format - it will not work correctly otherwise. Both Together AI and DeepInfra handle this automatically via their OpenAI-compatible endpoints.\n\n---\n\n## 2. Deployment Architecture\n\n### Component Deployment\n\n```\n┌─────────────────────────────────────────────────────────────────────┐\n│                         PRODUCTION ARCHITECTURE                      │\n├─────────────────────────────────────────────────────────────────────┤\n│                                                                      │\n│  ┌──────────────┐      ┌──────────────────────────────────────┐     │\n│  │   Frontend   │      │            Backend Cluster            │     │\n│  │   (Vercel)   │─────▶│         (Railway / Fly.io)           │     │\n│  │              │ SSE  │                                       │     │\n│  │  React SPA   │◀─────│  ┌─────────┐  ┌─────────┐            │     │\n│  └──────────────┘      │  │ API Pod │  │ API Pod │ (N pods)   │     │\n│         │              │  │  :9000  │  │  :9000  │            │     │\n│         │              │  └────┬────┘  └────┬────┘            │     │\n│         │              │       │            │                  │     │\n│         │              │       ▼            ▼                  │     │\n│         │              │  ┌────────────────────┐               │     │\n│         │              │  │  Shared SQLite DB  │               │     │\n│         │              │  │  (Turso / Litestream)              │     │\n│         │              │  └────────────────────┘               │     │\n│         │              │           │                           │     │\n│         │              │           ▼                           │     │\n│         │              └──────────────────────────────────────┘     │\n│         │                          │                                 │\n│         │                          ▼                                 │\n│         │              ┌──────────────────────┐                      │\n│         │              │    E2B Sandbox API   │                      │\n│         │              │  (external service)  │                      │\n│         │              └──────────────────────┘                      │\n│         │                                                            │\n│         ▼                                                            │\n│  ┌──────────────────────────────────────────────────────────────┐   │\n│  │                    EXTERNAL SERVICES                          │   │\n│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │\n│  │  │ Together AI  │  │  Parallel.ai │  │  DeepInfra   │        │   │\n│  │  │ (gpt-oss)    │  │  (search/    │  │  (fallback)  │        │   │\n│  │  │              │  │   extract)   │  │              │        │   │\n│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │\n│  └──────────────────────────────────────────────────────────────┘   │\n└─────────────────────────────────────────────────────────────────────┘\n```\n\n### Hosting Decisions\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| **Frontend** | Vercel | Free tier, global CDN, auto-deploy from git |\n| **Backend** | Railway or Fly.io | Docker support, easy SQLite, auto-scaling |\n| **Database** | Turso (LibSQL) | Distributed SQLite, edge replicas, free tier |\n| **Sandbox** | E2B | External API, 100 free credits, no Docker-in-container issues |\n| **Secrets** | Platform secrets | Railway/Fly built-in secret management |\n\n### Why E2B instead of Docker sidecar?\n\n**The Problem:** Railway/Fly.io instances are already containers. They don't have a Docker daemon (`dockerd`) inside. Running `subprocess.run([\"docker\", \"run\", ...])` will fail with:\n- `FileNotFoundError: [Errno 2] No such file or directory: 'docker'`\n- Or `Cannot connect to the Docker daemon`\n\n**The Solution:** E2B provides a hosted sandbox API:\n- 100 free credits (generous for research)\n- HTTP API - works from any environment\n- Automatic session cleanup (no zombie containers)\n- Built-in timeout handling\n\n### Why NOT separate queue service (Redis/RabbitMQ)?\n\nFor V1 single-instance:\n- In-memory asyncio.Queue is sufficient\n- SSE is connection-based, not queue-based\n- Complexity not justified for single instance\n- Add Redis later when scaling to multi-instance\n\n---\n\n## 3. System-Wide Failure Scenarios\n\n### 3.1 Model API Failures\n\n| Failure | Detection | Recovery | User Experience |\n|---------|-----------|----------|-----------------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries | \"Thinking...\" with delay |\n| Timeout (>30s) | Request timeout | Fail to fallback provider | Seamless if fallback works |\n| 5xx error | HTTP status | Retry once, then fallback | Brief delay |\n| Invalid response | JSON parse error | Retry with same provider | Retry automatically |\n| All providers down | Both fail | Mark run as error, notify user | \"Service unavailable, retry later\" |\n\n**Implementation:**\n\n```python\nclass ModelProviderChain:\n    \"\"\"Chain of model providers with automatic failover.\"\"\"\n\n    def __init__(self, providers: list[LLMProvider]):\n        self.providers = providers  # [TogetherAI, DeepInfra]\n        self.circuit_breakers = {p.name: CircuitBreaker() for p in providers}\n\n    async def complete(self, messages, tools, **kwargs) -> LLMResponse:\n        last_error = None\n\n        for provider in self.providers:\n            cb = self.circuit_breakers[provider.name]\n\n            if cb.is_open:\n                continue  # Skip this provider\n\n            try:\n                response = await provider.complete(messages, tools, **kwargs)\n                cb.record_success()\n                return response\n            except RateLimitError as e:\n                cb.record_failure()\n                last_error = e\n                await asyncio.sleep(e.retry_after or 1)\n            except (TimeoutError, ServerError) as e:\n                cb.record_failure()\n                last_error = e\n                # Try next provider immediately\n\n        raise AllProvidersFailedError(last_error)\n```\n\n### 3.2 Tool Execution Failures\n\n| Tool | Failure | Detection | Recovery |\n|------|---------|-----------|----------|\n| **web_search** | API error | HTTP 4xx/5xx | Retry 3x, then error |\n| **web_search** | Rate limit | 429 | Backoff + retry |\n| **web_search** | Timeout | >15s | Retry once |\n| **web_extract** | URL unreachable | Error in response | Skip URL, continue with others |\n| **web_extract** | Rate limit | 429 | Backoff + retry |\n| **python_execute** | Timeout | Docker stop after 30s | Return timeout error |\n| **python_execute** | OOM | Container killed | Return memory error |\n| **python_execute** | Syntax error | Non-zero exit | Return stderr to model |\n\n**Tool Result to Model:**\n\n```python\n# On failure, we tell the model what happened so it can adapt\ntool_result = {\n    \"tool_call_id\": \"call_123\",\n    \"status\": \"error\",\n    \"error_type\": \"timeout\",\n    \"error_message\": \"Execution exceeded 30s limit\",\n    \"suggestion\": \"Try a simpler computation or break into smaller steps\"\n}\n```\n\n### 3.3 Database Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Connection lost | SQLite exception | Reconnect with backoff |\n| Disk full | Write error | Alert, pause new runs |\n| Corruption | Integrity check | Restore from backup |\n| Lock contention | Timeout | Retry with exponential backoff |\n\n**With Turso (recommended for prod):**\n- Automatic replication\n- Point-in-time recovery\n- No lock contention (distributed)\n\n### 3.4 SSE/Streaming Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Client disconnect | Connection close event | Continue run, discard events |\n| Network timeout | No heartbeat received | Client reconnects, resumes from last event |\n| Backend crash | SSE connection drops | Client polls `/runs/{id}` for final state |\n\n**Frontend Reconnection Logic:**\n\n```typescript\nfunction useAgentSSE(runId: string) {\n  const [lastEventSeq, setLastEventSeq] = useState(0);\n\n  useEffect(() => {\n    let eventSource: EventSource | null = null;\n    let reconnectAttempts = 0;\n\n    const connect = () => {\n      // Resume from last seen event\n      const url = `/api/agent/runs/${runId}/stream?since_seq=${lastEventSeq}`;\n      eventSource = new EventSource(url);\n\n      eventSource.onmessage = (event) => {\n        reconnectAttempts = 0;  // Reset on successful message\n        const data = JSON.parse(event.data);\n        setLastEventSeq(data.seq);\n        // Process event...\n      };\n\n      eventSource.onerror = () => {\n        eventSource?.close();\n\n        if (reconnectAttempts < 5) {\n          reconnectAttempts++;\n          setTimeout(connect, 1000 * Math.pow(2, reconnectAttempts));\n        } else {\n          // Give up, poll for final state\n          pollFinalState(runId);\n        }\n      };\n    };\n\n    connect();\n    return () => eventSource?.close();\n  }, [runId]);\n}\n```\n\n### 3.5 Process Crash & Recovery\n\n| Crash Point | State Before Crash | Recovery Action |\n|-------------|-------------------|-----------------|\n| Before step created | run.current_step = N | Create step N, continue |\n| After step, before model call | step exists, no response | Redo model call |\n| After model response, before tool record | step has response | Parse response, create tool call |\n| During tool execution | tool_call.status = \"running\" | See tool-specific recovery |\n| After tool result, before step complete | tool_call.status = \"success\" | Mark step complete, continue |\n\n**Startup Recovery Scan:**\n\n```python\nasync def recover_incomplete_runs():\n    \"\"\"Called on server startup to recover any crashed runs.\"\"\"\n\n    # Find runs that were in progress when we crashed\n    incomplete_runs = await db.execute(\"\"\"\n        SELECT run_id FROM runs\n        WHERE mode = 'agent'\n        AND status = 'running'\n        AND updated_at < datetime('now', '-5 minutes')\n    \"\"\")\n\n    for run in incomplete_runs:\n        try:\n            action = await determine_recovery_action(run.run_id)\n\n            if action == RecoveryAction.CONTINUE:\n                # Re-queue the run for processing\n                asyncio.create_task(resume_agent_run(run.run_id))\n            elif action == RecoveryAction.MARK_FAILED:\n                await mark_run_failed(run.run_id, \"Crashed during execution\")\n        except Exception as e:\n            logger.error(f\"Recovery failed for {run.run_id}: {e}\")\n            await mark_run_failed(run.run_id, f\"Recovery failed: {e}\")\n```\n\n### 3.6 Non-Idempotent Tool Recovery (Critical)\n\n**The Problem:** If `python_execute` runs successfully but backend crashes before saving result:\n1. On restart, we mark step as ERROR\n2. Agent sees \"Step 4: Calculate Pi -> Error\"\n3. Agent thinks code failed - may hallucinate result or fail\n\n**Python execution is NOT idempotent** - we cannot safely retry because:\n- Side effects may have occurred\n- State may have changed\n- Result is lost forever\n\n**The Solution:** Inject a system hint telling the model what happened:\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for non-idempotent tools like python_execute.\"\"\"\n\n    # Mark as interrupted (not error - important distinction)\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    # Inject system hint into next model call\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The code may or may not have \"\n            f\"executed successfully - the result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n\n    # Log for debugging\n    logger.warning(\n        f\"Non-idempotent tool recovery: {tool_call.id}\",\n        extra={\"tool_name\": tool_call.tool_name, \"run_id\": context.run_id}\n    )\n```\n\n**Integration in recovery logic:**\n\n```python\nasync def determine_recovery_action(run_id: str) -> RecoveryAction:\n    # Find the last tool call\n    last_tool = await get_last_tool_call(run_id)\n\n    if last_tool and last_tool.status == \"running\":\n        if last_tool.tool_name == \"python_execute\":\n            # Non-idempotent: cannot retry, inject hint\n            return RecoveryAction.INJECT_HINT\n        elif last_tool.tool_name in (\"web_search\", \"web_extract\"):\n            # Idempotent: safe to retry\n            return RecoveryAction.RETRY_TOOL\n        else:\n            return RecoveryAction.MARK_FAILED\n\n    return RecoveryAction.CONTINUE\n```\n\n### 3.7 E2B Session Cleanup on Startup\n\n**The Problem:** Even with E2B, orphan sessions can accumulate if backend crashes mid-execution.\n\n**The Solution:** Clean up stale sessions on startup:\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup to clean up any orphan E2B sessions.\"\"\"\n    from e2b import Sandbox\n\n    # Get all running sessions older than 10 minutes\n    # E2B automatically cleans up after timeout, but we can be proactive\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale E2B session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 4. Data Model (Complete)\n\n### Extended `runs` Table\n\n```sql\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;  -- For crash detection\n```\n\n### `agent_steps` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n\n    -- State\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n\n    -- Model interaction\n    model_request_event_id TEXT,\n    model_response_event_id TEXT,\n    thinking_text TEXT,\n\n    -- Decision\n    decision TEXT,  -- 'call_tool' | 'synthesize' | 'error'\n    decision_raw TEXT,  -- Raw model output for debugging\n\n    -- Error tracking\n    error_message TEXT,\n    error_recoverable BOOLEAN DEFAULT TRUE,\n\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n```\n\n### `agent_tool_calls` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    -- Tool info\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n\n    -- Execution tracking\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n\n    -- Idempotency & retry\n    idempotency_key TEXT NOT NULL,  -- UUID for deduplication\n    execution_attempt INTEGER DEFAULT 1,\n    max_attempts INTEGER DEFAULT 3,\n\n    -- Result (IMPORTANT: No result_raw - prevents WAL bloat)\n    result_summary TEXT,           -- 1-line summary for UI display\n    result_blob_ref TEXT,          -- Reference to external storage (if needed)\n    error_message TEXT,\n    error_type TEXT,  -- timeout | api_error | parse_error | etc.\n\n    -- Trace linkage\n    trace_event_id TEXT,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\n```\n\n### Avoiding WAL Bloat (Critical for Production)\n\n**The Problem:** Storing `result_raw` (web_extract can return 10KB+ per URL) causes:\n- SQLite WAL file grows to gigabytes\n- Exceeds cheap Railway tier disk limits\n- Slow queries and backups\n\n**The Solution:** Don't store raw results in SQLite:\n\n1. **For web_extract:** Only store `result_summary` (URLs + char counts)\n2. **For web_search:** Only store `result_summary` (query + result count)\n3. **For python_execute:** Store stdout/stderr directly (usually small)\n\n**If you need raw results for debugging:**\n\nOption A: Use `result_blob_ref` pointing to Cloudflare R2/S3:\n```python\nasync def save_large_result(tool_call_id: str, raw: str) -> str:\n    \"\"\"Save large result to R2, return reference.\"\"\"\n    if len(raw) < 5000:\n        return None  # Store inline in summary\n\n    key = f\"tool-results/{tool_call_id}.json\"\n    await r2_client.put(key, raw)\n    return f\"r2://{key}\"\n```\n\nOption B: Enable SQLite auto_vacuum (less effective):\n```sql\nPRAGMA auto_vacuum = INCREMENTAL;\n```\n\n**Recommended:** Just don't store raw results. The context pruner summarizes them anyway.\n\n### `agent_citations` Table\n\n```sql\nCREATE TABLE IF NOT EXISTS agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n\n    used_in_answer BOOLEAN DEFAULT FALSE,\n\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 5. Agent Engine Design\n\n### State Machine\n\n```\n                         ┌──────────────────────────────────────────────┐\n                         │                                              │\n     ┌───────────────────┼──────────────────────────────────────────┐   │\n     │                   │                                          │   │\n     ▼                   │                                          ▼   ▼\n┌─────────┐         ┌────┴─────┐         ┌─────────────┐         ┌───────┐\n│  INIT   │────────▶│ PLANNING │────────▶│TOOL_CALLING │────────▶│COMPLETE│\n└─────────┘         └────┬─────┘         └──────┬──────┘         └───────┘\n                         │                      │\n                         │    ┌─────────────────┘\n                         │    │\n                         ▼    ▼\n                    ┌──────────┐\n                    │SYNTHESIZE│─────────────────────────────────────────▶\n                    └──────────┘\n                         │\n     ┌───────────────────┼───────────────────────────────────────────────┐\n     │                   │                                               │\n     │                   ▼                                               │\n     │              ┌─────────┐                                          │\n     └─────────────▶│  ERROR  │◀─────────────────────────────────────────┘\n                    └─────────┘\n                         │\n                         ▼\n                    ┌──────────┐\n                    │CANCELLED │ (user-initiated only)\n                    └──────────┘\n```\n\n### Agent Loop with Error Handling\n\n```python\nclass AgentEngine:\n    async def run(self, run_id: str, query: str) -> AgentResult:\n        context = await self._init_or_restore(run_id, query)\n\n        try:\n            while context.step_number < context.max_steps:\n                # Check for cancellation\n                if await self._is_cancelled(run_id):\n                    return await self._finalize(context, AgentState.CANCELLED)\n\n                # Heartbeat for crash detection\n                await self._update_heartbeat(run_id)\n\n                context.step_number += 1\n                step = await self._create_step(context)\n\n                try:\n                    # PLANNING: Call model\n                    response = await self._call_model_with_retry(context)\n                    await self._record_model_response(step, response)\n\n                    if response.tool_calls:\n                        # TOOL_CALLING\n                        for tool_call in response.tool_calls:\n                            result = await self._execute_tool_with_recovery(\n                                context, step, tool_call\n                            )\n                            context.add_tool_result(result)\n                    else:\n                        # SYNTHESIZING: Final answer\n                        context.final_answer = response.text\n                        await self._mark_citations_used(context)\n                        return await self._finalize(context, AgentState.COMPLETE)\n\n                except RecoverableError as e:\n                    # Log and continue to next step\n                    await self._record_step_error(step, e)\n                    context.add_error(e)\n\n                except FatalError as e:\n                    # Cannot continue\n                    return await self._finalize(context, AgentState.ERROR, str(e))\n\n            # Max steps reached - force synthesis\n            return await self._force_synthesis(context)\n\n        except Exception as e:\n            logger.exception(f\"Unexpected error in agent run {run_id}\")\n            return await self._finalize(context, AgentState.ERROR, str(e))\n\n### Context Pruner (Critical for Token Management)\n\n**The Problem:** Appending every tool result to message history without pruning causes context blowout:\n- Parallel.ai `extract` returns 5-10k tokens per batch\n- By step 4-5, history exceeds 30k tokens\n- By step 10, hits 128k limit of gpt-oss-120b\n\n**The Solution:** Prune old tool results to 1-line summaries:\n\n```python\nclass ContextPruner:\n    \"\"\"Prunes message history to prevent token blowout.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps fully detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        \"\"\"Replace old tool results with summaries.\"\"\"\n        pruned = []\n\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    # Summarize old tool results\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        \"\"\"Replace large tool result with 1-line summary.\"\"\"\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            # Parse and summarize\n            try:\n                data = json.loads(content)\n                urls = [r.get(\"url\", \"\")[:50] for r in data.get(\"results\", [])]\n                total_chars = sum(len(r.get(\"content\", \"\")) for r in data.get(\"results\", []))\n                summary = f\"[Extracted ~{total_chars//100}00 chars from {len(urls)} URLs: {', '.join(urls[:2])}...]\"\n            except:\n                summary = f\"[Extracted content - {len(content)} chars]\"\n\n        elif tool_name == \"web_search\":\n            try:\n                data = json.loads(content)\n                count = len(data.get(\"results\", []))\n                summary = f\"[Search returned {count} results]\"\n            except:\n                summary = f\"[Search results - {len(content)} chars]\"\n\n        elif tool_name == \"python_execute\":\n            # Keep stdout/stderr but truncate if huge\n            if len(content) > 500:\n                summary = f\"[Python output truncated: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg  # Keep small outputs fully\n\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {\n            **msg,\n            \"content\": summary,\n            \"_pruned\": True,\n            \"_original_length\": len(content)\n        }\n```\n\n**Integration in Agent Engine:**\n\n```python\nasync def _call_model_with_retry(self, context) -> LLMResponse:\n    # CRITICAL: Prune context before every model call\n    pruned_messages = self.context_pruner.prune(\n        context.messages,\n        context.step_number\n    )\n\n    for attempt in range(3):\n        try:\n            return await self.provider_chain.complete(\n                messages=pruned_messages,  # Use pruned, not raw\n                tools=self.tool_registry.get_openai_tools(),\n                reasoning_effort=\"medium\",\n            )\n        # ... rest of retry logic\n```\n\n    async def _call_model_with_retry(self, context) -> LLMResponse:\n        \"\"\"Call model with provider failover.\"\"\"\n        for attempt in range(3):\n            try:\n                return await self.provider_chain.complete(\n                    messages=context.messages,\n                    tools=self.tool_registry.get_openai_tools(),\n                    reasoning_effort=\"medium\",\n                )\n            except RateLimitError as e:\n                if attempt == 2:\n                    raise\n                await asyncio.sleep(e.retry_after or (2 ** attempt))\n            except AllProvidersFailedError:\n                raise FatalError(\"All model providers unavailable\")\n\n    async def _execute_tool_with_recovery(self, context, step, tool_call) -> ToolResult:\n        \"\"\"Execute tool with idempotency and recovery.\"\"\"\n\n        # Create record BEFORE execution (write-ahead)\n        tool_record = await self._create_tool_record(step, tool_call)\n\n        try:\n            await self._update_tool_status(tool_record.id, \"running\")\n\n            result = await self.tool_registry.execute(\n                tool_call.name,\n                tool_call.arguments,\n                idempotency_key=tool_record.idempotency_key,\n            )\n\n            await self._save_tool_result(tool_record.id, result)\n\n            # Extract and save citations\n            if result.citations:\n                await self._save_citations(context.run_id, tool_record.id, result.citations)\n\n            return result\n\n        except ToolTimeoutError:\n            await self._update_tool_status(tool_record.id, \"timeout\")\n            return ToolResult(\n                success=False,\n                error=\"Execution timed out after 30 seconds\"\n            )\n        except ToolError as e:\n            await self._update_tool_status(tool_record.id, \"error\", str(e))\n\n            if tool_record.execution_attempt < tool_record.max_attempts:\n                # Retry for idempotent tools\n                if tool_call.name in (\"web_search\", \"web_extract\"):\n                    return await self._retry_tool(context, step, tool_call, tool_record)\n\n            return ToolResult(success=False, error=str(e))\n```\n\n---\n\n## 6. SSE & Streaming Architecture\n\n### Event Types\n\n```python\nclass SSEEventType(str, Enum):\n    # State changes\n    AGENT_STATE = \"agent_state\"      # State transition\n    STEP_START = \"step_start\"        # New step beginning\n    STEP_COMPLETE = \"step_complete\"  # Step finished\n\n    # Tool events\n    TOOL_START = \"tool_start\"        # Tool execution starting\n    TOOL_PROGRESS = \"tool_progress\"  # Optional progress update\n    TOOL_RESULT = \"tool_result\"      # Tool completed (summary only)\n\n    # Content streaming\n    THINKING = \"thinking\"            # Model reasoning tokens\n    ANSWER = \"answer\"                # Final answer tokens\n    CITATION = \"citation\"            # Citation added\n\n    # Terminal\n    COMPLETE = \"complete\"            # Run finished successfully\n    ERROR = \"error\"                  # Run failed\n    CANCELLED = \"cancelled\"          # Run was cancelled\n\n    # Connection\n    HEARTBEAT = \"heartbeat\"          # Keep-alive ping\n```\n\n### Event Payload Structure\n\n```python\n@dataclass\nclass SSEEvent:\n    type: SSEEventType\n    seq: int                    # Monotonic sequence number\n    timestamp: str              # ISO timestamp\n    run_id: str\n    data: dict                  # Event-specific payload\n\n    def to_sse(self) -> str:\n        return f\"event: {self.type.value}\\ndata: {json.dumps(self.to_dict())}\\n\\n\"\n```\n\n### Streaming Endpoint with Resumption\n\n```python\n@router.get(\"/agent/runs/{run_id}/stream\")\nasync def stream_agent_events(\n    run_id: str,\n    since_seq: int = Query(0, description=\"Resume from this sequence number\"),\n):\n    \"\"\"Stream agent events with resumption support.\"\"\"\n\n    async def event_generator():\n        # First, replay any missed events from DB\n        if since_seq > 0:\n            missed_events = await get_events_since(run_id, since_seq)\n            for event in missed_events:\n                yield event.to_sse()\n\n        # Then stream live events\n        queue = get_or_create_queue(run_id)\n        last_heartbeat = time.time()\n\n        while True:\n            try:\n                event = await asyncio.wait_for(queue.get(), timeout=15.0)\n                yield event.to_sse()\n\n                if event.type in (SSEEventType.COMPLETE, SSEEventType.ERROR, SSEEventType.CANCELLED):\n                    break\n\n            except asyncio.TimeoutError:\n                # Send heartbeat to keep connection alive\n                yield SSEEvent(\n                    type=SSEEventType.HEARTBEAT,\n                    seq=-1,\n                    timestamp=datetime.now().isoformat(),\n                    run_id=run_id,\n                    data={}\n                ).to_sse()\n\n    return EventSourceResponse(event_generator())\n```\n\n---\n\n## 7. Configuration\n\n### `chat_config.yaml` additions\n\n```yaml\n# Model providers with failover\nmodel_providers:\n  primary:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 2\n  fallback:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n    max_retries: 1\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  step_timeout_ms: 120000\n\n  # Recovery settings\n  recovery:\n    enabled: true\n    scan_interval_seconds: 60\n    stale_run_threshold_minutes: 30\n\n  # Circuit breaker\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n    max_retries: 3\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n    max_retries: 3\n\n# Sandbox (E2B - external API, no Docker-in-container issues)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"      # Pre-built Python environment\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"        # For cleanup identification\n```\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider (cheaper)\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider (higher SLA)\n\n# Database (if using Turso)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 8. Phased Implementation (Incremental with Testing)\n\nEach phase is **independently testable** before moving to the next. Testing, tracing, and observability are built into each phase.\n\n---\n\n### Phase 1: Data Layer + Schema\n**Goal:** Agent tables exist, CRUD works, traces are recorded.\n\n**FIRST ACTION (before any code):**\n```bash\n# 1. Create implementation log\ntouch docs/AGENT_IMPLEMENTATION_LOG.md\n# (populate with initial template from plan)\n\n# 2. Create branch\ngit checkout -b feature/agent-phase-1-data-layer\n\n# 3. Commit log + any doc updates\ngit add docs/ && git commit -m \"Phase 1: Initialize implementation log\"\n```\n\n**Files (following existing patterns):**\n```\norchestrator/storage/schema.sql                    # Add agent tables\norchestrator/schemas.py                            # Add AgentStep, AgentToolCall, AgentCitation models\norchestrator/storage/repositories/agent_repo.py    # CRUD operations\ntests/storage/test_agent_repo.py                   # Unit tests (matches existing test_trace_repo.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Run migrations\nsqlite3 data/reasoner.db < orchestrator/storage/schema.sql\n\n# 2. Unit tests pass (use existing just command)\njust test tests/storage/test_agent_repo.py -v\n\n# 3. Manual verification\nsqlite3 data/reasoner.db \".schema agent_steps\"\n```\n\n**Observability Built-in:**\n- All repo methods log operation + duration (follow existing trace_repo.py pattern)\n- Trace events written for every DB write\n\n**Exit Criteria:** ✅ Can create/read/update agent_steps, agent_tool_calls, agent_citations\n\n---\n\n### Phase 2: Provider Chain + Circuit Breaker\n**Goal:** Model calls work with failover, circuit breaker trips on errors.\n\n**Files (following existing providers/ pattern):**\n```\norchestrator/providers/circuit_breaker.py    # Circuit breaker\norchestrator/providers/chain.py              # Provider chain with failover\norchestrator/config.py                       # Add provider chain config\ntests/providers/test_circuit_breaker.py      # Unit tests (matches existing test_openai_compat.py)\ntests/providers/test_provider_chain.py       # Unit tests\ntests/integration/test_provider_failover.py  # Integration test (matches test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked providers)\njust test tests/providers/test_circuit_breaker.py tests/providers/test_provider_chain.py -v\n\n# 2. Integration test (real API calls - optional, requires keys)\nDEEPINFRA_API_KEY=xxx just test tests/integration/test_provider_failover.py -v\n```\n\n**Observability Built-in:**\n- Log every provider attempt with latency\n- Log circuit breaker state changes (open/closed)\n- Trace event for each model call (endpoint, tokens, duration)\n\n**Exit Criteria:** ✅ DeepInfra works, failover to Together works, circuit breaker trips after 5 failures\n\n---\n\n### Phase 3: Tool Layer (Individual Tools)\n**Goal:** Each tool works independently with proper error handling.\n\n**Files (new agent/ module):**\n```\norchestrator/agent/__init__.py               # Package init\norchestrator/agent/tools/__init__.py         # Tools package\norchestrator/agent/tools/base.py             # BaseTool ABC\norchestrator/agent/tools/registry.py         # Tool registry\norchestrator/agent/tools/web_search.py       # Parallel Search\norchestrator/agent/tools/web_extract.py      # Parallel Extract\norchestrator/agent/tools/python_sandbox.py   # E2B integration\ntests/agent/__init__.py                      # New test package\ntests/agent/test_tool_registry.py            # Unit tests\ntests/integration/test_agent_tools.py        # Integration: real APIs (optional)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked APIs - always run)\njust test tests/agent/test_tool_registry.py -v\n\n# 2. Integration tests (real APIs - optional, requires keys)\nPARALLEL_API_KEY=xxx E2B_API_KEY=xxx just test tests/integration/test_agent_tools.py -v\n```\n\n**Observability Built-in:**\n- Each tool logs: name, args (truncated), duration, success/error\n- Trace event for each tool execution\n- Error classification (timeout, api_error, rate_limit, etc.)\n\n**Exit Criteria:** ✅ Each tool works in isolation, errors are properly classified and logged\n\n---\n\n### Phase 4: Context Pruner + State Machine\n**Goal:** Token management works, state transitions are correct.\n\n**Files:**\n```\norchestrator/agent/context_pruner.py         # Token management\norchestrator/agent/state_machine.py          # State transitions\ntests/agent/test_context_pruner.py           # Unit tests\ntests/agent/test_state_machine.py            # Unit tests\n```\n\n**Testing Checkpoint:**\n```bash\n# All unit tests in one command\njust test tests/agent/test_context_pruner.py tests/agent/test_state_machine.py -v\n```\n\n**Observability Built-in:**\n- Log token count before/after pruning\n- Log every state transition with reason\n- Trace events for state changes\n\n**Exit Criteria:** ✅ Pruner reduces context size, state machine handles all transitions\n\n---\n\n### Phase 5: Agent Engine (Core Loop)\n**Goal:** Agent can execute multi-step research queries end-to-end.\n\n**Files:**\n```\norchestrator/agent/recovery.py               # Crash recovery + hint injection\norchestrator/agent/agent_engine.py           # Main loop\ntests/agent/test_recovery.py                 # Unit tests\ntests/agent/test_agent_engine.py             # Unit tests (mocked tools)\ntests/integration/test_agent_e2e.py          # E2E (follows test_full_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit tests (mocked everything - always run)\njust test tests/agent/test_recovery.py tests/agent/test_agent_engine.py -v\n\n# 2. E2E test (real APIs - optional, requires all keys)\nDEEPINFRA_API_KEY=xxx PARALLEL_API_KEY=xxx E2B_API_KEY=xxx \\\n  just test tests/integration/test_agent_e2e.py -v\n```\n\n**Observability Built-in:**\n- Log every step: number, state, tool calls, duration\n- Log recovery actions with reason\n- Full trace timeline in DB (queryable)\n\n**Exit Criteria:** ✅ Agent completes \"What is the population of Tokyo?\" with citations\n\n---\n\n### Phase 6: API Layer + SSE\n**Goal:** HTTP endpoints work, SSE streams events correctly.\n\n**Files:**\n```\norchestrator/routes/agent.py                 # Agent endpoints + SSE\norchestrator/app.py                          # Register router, startup recovery\ntests/integration/test_agent_api.py          # API tests (follows test_e2e_flow.py pattern)\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Unit/integration tests (mocked provider, uses TestClient)\njust test tests/integration/test_agent_api.py -v\n\n# 2. Start server for manual testing\njust dev\n\n# 3. SSE test (verify events stream)\ncurl -N \"http://localhost:9000/api/agent/runs/test-123/stream\"\n\n# 4. Full integration (use existing sanity script pattern)\n./scripts/sanity_test.sh --debug\n```\n\n**Observability Built-in:**\n- Request logging (method, path, duration, status)\n- SSE event logging (type, seq, run_id)\n- Startup recovery logging\n\n**Exit Criteria:** ✅ Can start agent run via API, stream events via SSE, query traces via API\n\n---\n\n### Phase 7: Frontend Integration\n**Goal:** UI shows thinking view and answer with citations.\n\n**Files:**\n```\nui/src/types/agent.ts                        # TypeScript types\nui/src/api/client.ts                         # Agent API client\nui/src/hooks/useStore.ts                     # Agent state\nui/src/hooks/useAgentSSE.ts                  # SSE with reconnection\nui/src/components/AgentThinkingPanel.tsx     # Tool calls display\nui/src/components/ToolCallCard.tsx           # Individual tool card\nui/src/components/CitationInline.tsx         # [1] style citations\nui/src/components/AnswerWithCitations.tsx    # Final answer\nui/src/components/ConversationView.tsx       # Integrate agent mode\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. TypeScript compiles\ncd ui && pnpm tsc --noEmit\n\n# 2. Manual testing\ncd ui && pnpm dev\n# Open browser, submit query, verify:\n# - Thinking panel shows tool calls\n# - Answer has inline citations\n# - SSE reconnects on disconnect\n```\n\n**Observability Built-in:**\n- Console logging for SSE events\n- Error boundary with error reporting\n- Performance timing in dev tools\n\n**Exit Criteria:** ✅ Full user flow works: query → thinking → answer with citations\n\n---\n\n### Phase 8: Production Hardening\n**Goal:** Deploy to Railway/Vercel, verify recovery and monitoring.\n\n**Tasks:**\n```\n1. Deploy backend to Railway\n2. Deploy frontend to Vercel\n3. Configure Turso database\n4. Set up monitoring/alerting\n5. Test crash recovery in production\n6. Load test with 10 concurrent queries\n```\n\n**Testing Checkpoint:**\n```bash\n# 1. Deploy\nrailway up\nvercel --prod\n\n# 2. Smoke test\ncurl https://your-api.railway.app/health\n\n# 3. Recovery test\n# Kill Railway instance mid-run, verify it resumes\n\n# 4. Load test\nhey -n 100 -c 10 https://your-api.railway.app/api/agent/runs\n```\n\n**Observability Built-in:**\n- Structured JSON logs → Railway logs\n- Error alerting via Railway\n- Latency percentiles\n\n**Exit Criteria:** ✅ Production deployment works, crash recovery verified, <5s p95 latency\n\n---\n\n### Summary: All Files to Create/Modify\n\n**Backend (orchestrator/):**\n```\norchestrator/\n├── storage/\n│   ├── schema.sql                    # Phase 1: Add agent tables\n│   └── repositories/\n│       └── agent_repo.py             # Phase 1: CRUD operations\n├── schemas.py                        # Phase 1: Add agent Pydantic models\n├── config.py                         # Phase 2: Add provider chain config\n├── providers/\n│   ├── circuit_breaker.py            # Phase 2: Circuit breaker\n│   └── chain.py                      # Phase 2: Provider failover\n├── agent/\n│   ├── __init__.py                   # Phase 3\n│   ├── tools/\n│   │   ├── __init__.py               # Phase 3\n│   │   ├── base.py                   # Phase 3: BaseTool ABC\n│   │   ├── registry.py               # Phase 3: Tool registry\n│   │   ├── web_search.py             # Phase 3: Parallel.ai search\n│   │   ├── web_extract.py            # Phase 3: Parallel.ai extract\n│   │   └── python_sandbox.py         # Phase 3: E2B sandbox\n│   ├── context_pruner.py             # Phase 4: Token management\n│   ├── state_machine.py              # Phase 4: State transitions\n│   ├── recovery.py                   # Phase 5: Crash recovery + hints\n│   └── agent_engine.py               # Phase 5: Main loop\n├── routes/\n│   └── agent.py                      # Phase 6: HTTP + SSE endpoints\n└── app.py                            # Phase 6: Register router\n```\n\n**Tests (tests/):**\n```\ntests/\n├── storage/\n│   └── test_agent_repo.py            # Phase 1\n├── providers/\n│   ├── test_circuit_breaker.py       # Phase 2\n│   └── test_provider_chain.py        # Phase 2\n├── agent/\n│   ├── __init__.py\n│   ├── test_tool_registry.py         # Phase 3\n│   ├── test_context_pruner.py        # Phase 4\n│   ├── test_state_machine.py         # Phase 4\n│   ├── test_recovery.py              # Phase 5\n│   └── test_agent_engine.py          # Phase 5\n└── integration/\n    ├── test_provider_failover.py     # Phase 2 (optional)\n    ├── test_agent_tools.py           # Phase 3 (optional)\n    ├── test_agent_e2e.py             # Phase 5 (optional)\n    └── test_agent_api.py             # Phase 6\n```\n\n**Frontend (ui/src/):**\n```\nui/src/\n├── types/\n│   └── agent.ts                      # Phase 7\n├── api/\n│   └── client.ts                     # Phase 7: Add agent methods\n├── hooks/\n│   ├── useStore.ts                   # Phase 7: Add agent state\n│   └── useAgentSSE.ts                # Phase 7: SSE hook\n└── components/\n    ├── AgentThinkingPanel.tsx        # Phase 7\n    ├── ToolCallCard.tsx              # Phase 7\n    ├── CitationInline.tsx            # Phase 7\n    ├── AnswerWithCitations.tsx       # Phase 7\n    └── ConversationView.tsx          # Phase 7: Modify for agent mode\n```\n\n**Docs (to update after implementation):**\n```\ndocs/\n├── AGENT_SYSTEM_DESIGN.md            # Rewrite with all 6 fixes\n└── AGENT_MASTER_REFERENCE.md         # Quick reference\n```\n\n---\n\n## 9. Deployment Steps\n\n### Backend (Railway)\n\n```bash\n# 1. Create Railway project\nrailway login\nrailway init\n\n# 2. Add Dockerfile\n# (Uses existing orchestrator setup)\n\n# 3. Set environment variables\nrailway variables set TOGETHER_API_KEY=xxx\nrailway variables set PARALLEL_API_KEY=xxx\nrailway variables set DEEPINFRA_API_KEY=xxx\n\n# 4. Deploy\nrailway up\n```\n\n### Frontend (Vercel)\n\n```bash\n# 1. Connect to Vercel\ncd ui && vercel\n\n# 2. Set environment variables\nvercel env add VITE_API_URL  # Backend URL\n\n# 3. Deploy\nvercel --prod\n```\n\n### Database (Turso)\n\n```bash\n# 1. Create database\nturso db create reasoner\n\n# 2. Get credentials\nturso db tokens create reasoner\n\n# 3. Set in Railway\nrailway variables set TURSO_DATABASE_URL=libsql://...\nrailway variables set TURSO_AUTH_TOKEN=...\n```\n\n---\n\n## 10. Production Checklist\n\n### Pre-Launch\n- [ ] DeepInfra API key configured (primary)\n- [ ] Together AI API key configured (fallback)\n- [ ] Parallel.ai API key configured\n- [ ] E2B API key configured\n- [ ] Database migrated with agent tables\n- [ ] Environment variables set in Railway/Vercel\n- [ ] CORS configured for frontend domain\n\n### Monitoring\n- [ ] Structured logging for all tool calls\n- [ ] Error alerting configured\n- [ ] Latency metrics for model calls\n- [ ] Tool failure rate dashboard\n- [ ] Context token usage tracking\n\n### Recovery Testing\n- [ ] Kill backend mid-run → verify resume works\n- [ ] Kill backend during python_execute → verify hint injection works\n- [ ] Simulate model provider failure → verify fallback\n- [ ] Simulate tool timeout → verify graceful handling\n- [ ] Disconnect SSE client → verify reconnection\n\n### Security\n- [ ] API keys not in logs (redaction)\n- [ ] E2B sandbox isolation verified\n- [ ] Rate limiting on agent endpoints\n- [ ] Input validation on all endpoints\n"}
```
---
## USER (2026-01-04T10:54:59.096Z)


---
## ASSISTANT (2026-01-04T10:55:05.113Z)

<details><summary>Thinking...</summary>

The user is confused - they said "yes exit and create docs" but then rejected with "i dont see any docs". I think the issue is:

1. They want to SEE the docs before approving exit plan mode
2. But I can't create docs while IN plan mode

This is a chicken-and-egg problem. Let me try a different approach - I'll embed the full content of both docs directly INTO the plan file so the user can see exactly what will be created. Then when they approve exit plan mode, I'll extract those into actual files.

Let me add the full doc contents to the plan file.

</details>
---
## ASSISTANT (2026-01-04T10:55:06.009Z)

I see the issue - you want to see what the docs will contain before I create them. Let me add the full doc content directly to the plan file so you can review it:
---
## USER (2026-01-04T10:55:20.463Z)

[Request interrupted by user]
---
## USER (2026-01-04T10:55:29.354Z)

<ide_opened_file>The user opened the file /Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md in the IDE. This may or may not be related to the current task.</ide_opened_file>

create the docs
---
## ASSISTANT (2026-01-04T10:55:36.104Z)

<details><summary>Thinking...</summary>

The user wants me to create the documentation files. I'm now out of plan mode so I can create files. I need to:

1. Create `docs/AGENT_IMPLEMENTATION_LOG.md` - The live tracking doc
2. Update `docs/AGENT_SYSTEM_DESIGN.md` - It's outdated (has Docker, Together AI primary, missing fixes)
3. `docs/AGENT_MASTER_REFERENCE.md` already exists and has correct info

Let me start by creating the implementation log and then updating the system design doc.

</details>
---
## ASSISTANT (2026-01-04T10:55:36.624Z)

I'll create the implementation log and update the system design doc now.
---
## ASSISTANT (2026-01-04T10:56:02.869Z)

**Tool Use:** Write
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_IMPLEMENTATION_LOG.md","content":"# Agent Implementation Log\n\n> **Purpose:** Single source of truth for implementation progress. New conversations MUST read this first.\n\n---\n\n## Current Status\n\n- **Current Phase:** 0 (Not Started)\n- **Current Branch:** `main`\n- **Last Updated:** 2026-01-04\n- **Blockers:** None\n\n---\n\n## Quick Resume for New Chat\n\n1. Read this log first\n2. Read the plan file: `.claude/plans/lazy-purring-nygaard.md`\n3. Checkout the current branch (see above)\n4. Look at \"Next Steps\" below\n5. After work, update this log with what you built\n\n---\n\n## Next Steps\n\n**Phase 1: Data Layer** is next. To start:\n\n```bash\n# 1. Create branch\ngit checkout -b feature/agent-phase-1-data-layer\n\n# 2. Implement (see plan file for details):\n#    - Add agent tables to schema.sql\n#    - Add Pydantic models to schemas.py\n#    - Create agent_repo.py\n#    - Write tests\n\n# 3. Test\njust test tests/storage/test_agent_repo.py -v\n\n# 4. Update this log with results\n```\n\n---\n\n## Phase Progress\n\n### Phase 1: Data Layer - NOT STARTED\n- **Branch:** `feature/agent-phase-1-data-layer`\n- **Status:** Pending\n- **Files to Create:**\n  - `orchestrator/storage/schema.sql` (add agent tables)\n  - `orchestrator/schemas.py` (add AgentStep, AgentToolCall, AgentCitation)\n  - `orchestrator/storage/repositories/agent_repo.py`\n  - `tests/storage/test_agent_repo.py`\n- **Exit Criteria:** Can CRUD agent_steps, agent_tool_calls, agent_citations\n\n### Phase 2: Provider Chain - NOT STARTED\n- **Branch:** `feature/agent-phase-2-provider-chain`\n- **Status:** Pending\n- **Files to Create:**\n  - `orchestrator/providers/circuit_breaker.py`\n  - `orchestrator/providers/chain.py`\n  - `tests/providers/test_circuit_breaker.py`\n  - `tests/providers/test_provider_chain.py`\n- **Exit Criteria:** DeepInfra works, failover to Together works\n\n### Phase 3: Tool Layer - NOT STARTED\n- **Branch:** `feature/agent-phase-3-tools`\n- **Status:** Pending\n- **Files to Create:**\n  - `orchestrator/agent/tools/base.py`\n  - `orchestrator/agent/tools/registry.py`\n  - `orchestrator/agent/tools/web_search.py`\n  - `orchestrator/agent/tools/web_extract.py`\n  - `orchestrator/agent/tools/python_sandbox.py`\n- **Exit Criteria:** Each tool works in isolation\n\n### Phase 4: Context Pruner + State Machine - NOT STARTED\n- **Branch:** `feature/agent-phase-4-pruner-state`\n- **Status:** Pending\n- **Files to Create:**\n  - `orchestrator/agent/context_pruner.py`\n  - `orchestrator/agent/state_machine.py`\n- **Exit Criteria:** Pruner reduces token count, state transitions work\n\n### Phase 5: Agent Engine - NOT STARTED\n- **Branch:** `feature/agent-phase-5-engine`\n- **Status:** Pending\n- **Files to Create:**\n  - `orchestrator/agent/recovery.py`\n  - `orchestrator/agent/agent_engine.py`\n- **Exit Criteria:** Agent answers \"What is the population of Tokyo?\"\n\n### Phase 6: API Layer - NOT STARTED\n- **Branch:** `feature/agent-phase-6-api`\n- **Status:** Pending\n- **Files to Create:**\n  - `orchestrator/routes/agent.py`\n  - Update `orchestrator/app.py`\n- **Exit Criteria:** curl can start run and stream SSE events\n\n### Phase 7: Frontend - NOT STARTED\n- **Branch:** `feature/agent-phase-7-frontend`\n- **Status:** Pending\n- **Files to Create:**\n  - `ui/src/types/agent.ts`\n  - `ui/src/hooks/useAgentSSE.ts`\n  - `ui/src/components/AgentThinkingPanel.tsx`\n  - `ui/src/components/ToolCallCard.tsx`\n  - `ui/src/components/CitationInline.tsx`\n  - `ui/src/components/AnswerWithCitations.tsx`\n- **Exit Criteria:** Full user flow works in browser\n\n### Phase 8: Production - NOT STARTED\n- **Branch:** `feature/agent-phase-8-production`\n- **Status:** Pending\n- **Exit Criteria:** Deployed with crash recovery verified\n\n---\n\n## Key Documents\n\n| Document | Purpose |\n|----------|---------|\n| `.claude/plans/lazy-purring-nygaard.md` | Full design, architecture, code samples |\n| `docs/AGENT_MASTER_REFERENCE.md` | Quick reference (schema, API, fixes) |\n| `docs/AGENT_SYSTEM_DESIGN.md` | Detailed system design |\n| This file | Live implementation progress |\n\n---\n\n## Critical Fixes to Remember\n\n1. **E2B not Docker** - Railway/Fly.io can't run Docker\n2. **Context Pruner** - Summarize old tool results to prevent 128k blowout\n3. **DeepInfra primary** - 40% cheaper than Together AI\n4. **Hint injection** - For python_execute crash recovery\n5. **No result_raw** - Store only summaries to prevent WAL bloat\n6. **Session cleanup** - Clean E2B sessions on startup\n\n---\n\n## Completed Work\n\n(Nothing yet - implementation not started)\n"}
```
---
## USER (2026-01-04T10:57:03.138Z)


---
## ASSISTANT (2026-01-04T10:57:08.625Z)

<details><summary>Thinking...</summary>

Now I need to update the AGENT_SYSTEM_DESIGN.md file. Let me read the current content first and then rewrite it with all the fixes.

</details>
---
## ASSISTANT (2026-01-04T10:57:09.404Z)

Now let me update AGENT_SYSTEM_DESIGN.md with all the fixes:
---
## ASSISTANT (2026-01-04T10:57:10.341Z)

**Tool Use:** Read
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md","limit":100}
```
---
## USER (2026-01-04T10:57:10.367Z)


---
## ASSISTANT (2026-01-04T10:57:15.448Z)

<details><summary>Thinking...</summary>

The file is large - I can see it still has "Docker-sandboxed Python" at line 41 and "Together AI" as primary at lines 96-97. I need to rewrite this entire file with the correct information.Let me write a complete new version of the file.

</details>
---
## ASSISTANT (2026-01-04T10:57:16.212Z)

The file has outdated info (Docker, Together AI primary). Let me rewrite it completely:
---
## ASSISTANT (2026-01-04T10:58:54.898Z)

**Tool Use:** Write
```json
{"file_path":"/Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md","content":"# Web Research Agent - Complete System Design\n\n> **Last Updated:** 2026-01-04\n> **Status:** Authoritative design document\n\n---\n\n## Table of Contents\n\n1. [System Overview](#1-system-overview)\n2. [Critical Fixes](#2-critical-fixes)\n3. [Architecture](#3-architecture)\n4. [Model & Provider Layer](#4-model--provider-layer)\n5. [Tool System](#5-tool-system)\n6. [Agent Engine](#6-agent-engine)\n7. [Data Model](#7-data-model)\n8. [API Design](#8-api-design)\n9. [SSE & Streaming](#9-sse--streaming)\n10. [Failure Scenarios & Recovery](#10-failure-scenarios--recovery)\n11. [Deployment](#11-deployment)\n12. [Configuration](#12-configuration)\n\n---\n\n## 1. System Overview\n\n### What We're Building\n\nA production-grade web research agent that:\n- Searches the web using Parallel.ai APIs\n- Extracts and summarizes content from web pages\n- Executes Python code in E2B sandbox\n- Provides evidence-grounded answers with citations\n- Recovers from crashes gracefully\n- Streams real-time progress to the UI\n\n### Core Capabilities\n\n| Capability | Implementation |\n|------------|----------------|\n| Web Search | Parallel.ai Search API |\n| Content Extraction | Parallel.ai Extract API |\n| Computation | **E2B sandbox** (not Docker) |\n| Reasoning | gpt-oss-120b with Harmony format |\n| Primary Provider | **DeepInfra** ($0.09/1M tokens) |\n| Fallback Provider | Together AI ($0.15/1M tokens) |\n| Streaming | Server-Sent Events (SSE) |\n| Durability | SQLite with Turso (production) |\n\n### Non-Negotiables\n\n1. **Evidence-grounded answers** - Every claim backed by citations\n2. **Durable runs** - Crash recovery, cancel works, retries recorded\n3. **Full trace system** - Complete trace of all events\n4. **Thinking UI = trace projection** - Visualization of actual events\n5. **Answer accuracy** - Correctness over speed\n\n---\n\n## 2. Critical Fixes\n\nThese are production failure modes that MUST be addressed:\n\n| # | Problem | Why It Fails | Solution |\n|---|---------|--------------|----------|\n| 1 | **Docker-in-Cloud** | Railway/Fly.io are containers - no Docker daemon inside | Use **E2B external sandbox API** |\n| 2 | **Token Blowout** | Tool results accumulate, context exceeds 128k tokens | **Context Pruner**: summarize old results to 1-line |\n| 3 | **Zombie Sessions** | Backend crash leaves orphan E2B sessions | **Session cleanup on startup** |\n| 4 | **Non-Idempotent Recovery** | python_execute crash loses result, model hallucinates | **Inject system hint**: \"execution interrupted, re-run\" |\n| 5 | **Provider Economics** | Together AI is 60% more expensive | **DeepInfra primary** ($0.09 vs $0.15) |\n| 6 | **WAL Bloat** | Storing result_raw causes gigabyte WAL files | **Store only result_summary**, no blobs |\n\n---\n\n## 3. Architecture\n\n```\n┌─────────────────┐         HTTPS/SSE          ┌──────────────────────────────────┐\n│    FRONTEND     │◄──────────────────────────▶│            BACKEND               │\n│    (Vercel)     │                            │        (Railway/Fly.io)          │\n│                 │                            │                                  │\n│  • React/Vite   │                            │  ┌────────────────────────────┐  │\n│  • Zustand      │                            │  │      FastAPI Server        │  │\n│  • SSE Client   │                            │  └────────────┬───────────────┘  │\n└─────────────────┘                            │               │                  │\n                                               │               ▼                  │\n                                               │  ┌────────────────────────────┐  │\n                                               │  │      Agent Engine          │  │\n                                               │  │  • State Machine           │  │\n                                               │  │  • Context Pruner          │  │\n                                               │  │  • Recovery Logic          │  │\n                                               │  └────────────┬───────────────┘  │\n                                               │               │                  │\n                                               │  ┌────────────┴───────────────┐  │\n                                               │  │      Tool Registry         │  │\n                                               │  │  • web_search              │  │\n                                               │  │  • web_extract             │  │\n                                               │  │  • python_execute          │  │\n                                               │  └────────────────────────────┘  │\n                                               │               │                  │\n                                               │  ┌────────────┴───────────────┐  │\n                                               │  │    Provider Chain          │  │\n                                               │  │  • DeepInfra (primary)     │  │\n                                               │  │  • Together AI (fallback)  │  │\n                                               │  │  • Circuit Breaker         │  │\n                                               │  └────────────────────────────┘  │\n                                               │               │                  │\n                                               │  ┌────────────┴───────────────┐  │\n                                               │  │    Turso SQLite            │  │\n                                               │  └────────────────────────────┘  │\n                                               └──────────────────────────────────┘\n                                                              │\n                    ┌─────────────────────────────────────────┼─────────────────────────────────────────┐\n                    │                                         │                                         │\n                    ▼                                         ▼                                         ▼\n           ┌───────────────┐                         ┌───────────────┐                         ┌───────────────┐\n           │   DeepInfra   │                         │  Parallel.ai  │                         │     E2B       │\n           │  (gpt-oss)    │                         │ (search/ext)  │                         │  (sandbox)    │\n           └───────────────┘                         └───────────────┘                         └───────────────┘\n```\n\n---\n\n## 4. Model & Provider Layer\n\n### Provider Selection\n\n| Provider | Price (per 1M tokens) | Role | SLA |\n|----------|----------------------|------|-----|\n| **DeepInfra** | $0.09 input / $0.36 output | Primary | 99.5% |\n| Together AI | $0.15 input / $0.60 output | Fallback | 99.9% |\n\n**DeepInfra is primary because:**\n- 40% cheaper for same open-weights model\n- Native Harmony format support\n- OpenAI-compatible API\n\n### Failover Strategy\n\n```\nRequest → DeepInfra\n  ↓ (if 5xx or timeout > 30s)\n  → Together AI\n  ↓ (if also fails)\n  → Error with retry option\n```\n\n### Circuit Breaker\n\n```python\nclass CircuitBreaker:\n    def __init__(self, failure_threshold=5, recovery_timeout=30):\n        self.failure_count = 0\n        self.failure_threshold = failure_threshold\n        self.recovery_timeout = recovery_timeout\n        self.state = \"closed\"  # closed | open | half-open\n        self.last_failure_time = None\n\n    def record_failure(self):\n        self.failure_count += 1\n        self.last_failure_time = time.time()\n        if self.failure_count >= self.failure_threshold:\n            self.state = \"open\"\n\n    def record_success(self):\n        self.failure_count = 0\n        self.state = \"closed\"\n\n    @property\n    def is_open(self) -> bool:\n        if self.state == \"open\":\n            if time.time() - self.last_failure_time > self.recovery_timeout:\n                self.state = \"half-open\"\n                return False\n            return True\n        return False\n```\n\n---\n\n## 5. Tool System\n\n### Tool Definitions\n\n#### web_search\n```json\n{\n  \"name\": \"web_search\",\n  \"description\": \"Search the web for information\",\n  \"parameters\": {\n    \"query\": {\"type\": \"string\", \"required\": true},\n    \"num_results\": {\"type\": \"integer\", \"default\": 10}\n  }\n}\n```\n**Idempotent:** Yes (safe to retry)\n\n#### web_extract\n```json\n{\n  \"name\": \"web_extract\",\n  \"description\": \"Extract content from URLs\",\n  \"parameters\": {\n    \"urls\": {\"type\": \"array\", \"items\": \"string\", \"maxItems\": 5}\n  }\n}\n```\n**Idempotent:** Yes (safe to retry)\n\n#### python_execute\n```json\n{\n  \"name\": \"python_execute\",\n  \"description\": \"Execute Python code in sandbox\",\n  \"parameters\": {\n    \"code\": {\"type\": \"string\", \"required\": true}\n  }\n}\n```\n**Idempotent:** NO (inject hint on recovery)\n\n### E2B Sandbox Integration\n\n```python\nfrom e2b import Sandbox\n\nclass PythonSandboxTool(BaseTool):\n    name = \"python_execute\"\n\n    async def execute(self, code: str) -> ToolResult:\n        sandbox = None\n        try:\n            sandbox = await Sandbox.create(\n                template=\"python3\",\n                timeout=30,\n                metadata={\"app\": \"reasoner\"}\n            )\n\n            result = await sandbox.run_code(code)\n\n            return ToolResult(\n                success=True,\n                output=result.stdout,\n                error=result.stderr if result.stderr else None\n            )\n        except TimeoutError:\n            return ToolResult(success=False, error=\"Execution timed out\")\n        finally:\n            if sandbox:\n                await sandbox.kill()\n```\n\n### E2B Session Cleanup on Startup\n\n```python\nasync def cleanup_stale_e2b_sessions():\n    \"\"\"Called on server startup.\"\"\"\n    from e2b import Sandbox\n\n    try:\n        sessions = await Sandbox.list()\n        for session in sessions:\n            if session.metadata.get(\"app\") == \"reasoner\":\n                age_minutes = (datetime.now() - session.created_at).total_seconds() / 60\n                if age_minutes > 10:\n                    logger.info(f\"Cleaning up stale session: {session.id}\")\n                    await session.kill()\n    except Exception as e:\n        logger.warning(f\"E2B cleanup failed (non-fatal): {e}\")\n```\n\n---\n\n## 6. Agent Engine\n\n### State Machine\n\n```\n     ┌─────────┐\n     │  INIT   │\n     └────┬────┘\n          │\n          ▼\n     ┌─────────┐\n     │PLANNING │◄─────────────────────┐\n     └────┬────┘                      │\n          │                           │\n          ▼                           │\n  ┌───────────────┐                   │\n  │ TOOL_CALLING  │───────────────────┘\n  └───────┬───────┘\n          │ (no more tools)\n          ▼\n  ┌───────────────┐\n  │ SYNTHESIZING  │\n  └───────┬───────┘\n          │\n          ▼\n     ┌─────────┐\n     │COMPLETE │\n     └─────────┘\n```\n\n### Context Pruner (Critical)\n\n```python\nclass ContextPruner:\n    \"\"\"Prevents token blowout by summarizing old tool results.\"\"\"\n\n    KEEP_FULL_STEPS = 2  # Keep last 2 steps detailed\n\n    def prune(self, messages: list[dict], current_step: int) -> list[dict]:\n        pruned = []\n        for msg in messages:\n            if msg[\"role\"] == \"tool\":\n                step = self._get_step_number(msg)\n                if step is not None and step < current_step - self.KEEP_FULL_STEPS:\n                    pruned.append(self._summarize_tool_result(msg))\n                else:\n                    pruned.append(msg)\n            else:\n                pruned.append(msg)\n        return pruned\n\n    def _summarize_tool_result(self, msg: dict) -> dict:\n        content = msg.get(\"content\", \"\")\n        tool_name = msg.get(\"name\", \"unknown\")\n\n        if tool_name == \"web_extract\":\n            summary = f\"[Extracted content - {len(content)} chars]\"\n        elif tool_name == \"web_search\":\n            summary = f\"[Search results - {len(content)} chars]\"\n        elif tool_name == \"python_execute\":\n            if len(content) > 500:\n                summary = f\"[Output: {content[:200]}...{content[-200:]}]\"\n            else:\n                return msg\n        else:\n            summary = f\"[Tool result - {len(content)} chars]\"\n\n        return {**msg, \"content\": summary, \"_pruned\": True}\n```\n\n### Non-Idempotent Recovery (Hint Injection)\n\n```python\nasync def _recover_non_idempotent_tool(self, context, tool_call) -> None:\n    \"\"\"Handle recovery for python_execute crashes.\"\"\"\n\n    await self._update_tool_status(tool_call.id, \"interrupted\")\n\n    hint = {\n        \"role\": \"system\",\n        \"content\": (\n            f\"IMPORTANT: The previous {tool_call.tool_name} execution was \"\n            f\"interrupted by a system restart. The result was lost. \"\n            f\"Please regenerate and re-run the code to get the result.\"\n        )\n    }\n    context.messages.append(hint)\n```\n\n---\n\n## 7. Data Model\n\n### Agent Tables\n\n```sql\n-- Extend runs table\nALTER TABLE runs ADD COLUMN mode TEXT DEFAULT 'chat';\nALTER TABLE runs ADD COLUMN agent_state TEXT;\nALTER TABLE runs ADD COLUMN current_step INTEGER DEFAULT 0;\nALTER TABLE runs ADD COLUMN max_steps INTEGER DEFAULT 10;\nALTER TABLE runs ADD COLUMN updated_at TEXT;\n\n-- Agent steps\nCREATE TABLE agent_steps (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_number INTEGER NOT NULL,\n    created_at TEXT NOT NULL,\n    completed_at TEXT,\n    state TEXT NOT NULL,  -- planning | tool_calling | complete | error\n    thinking_text TEXT,\n    decision TEXT,        -- call_tool | synthesize | error\n    error_message TEXT,\n    UNIQUE(run_id, step_number),\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE\n);\n\n-- Tool calls (NO result_raw - prevents WAL bloat)\nCREATE TABLE agent_tool_calls (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    step_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n    tool_name TEXT NOT NULL,\n    arguments TEXT NOT NULL,\n    status TEXT NOT NULL,  -- pending | running | success | error | timeout | interrupted\n    started_at TEXT,\n    completed_at TEXT,\n    duration_ms INTEGER,\n    idempotency_key TEXT NOT NULL,\n    execution_attempt INTEGER DEFAULT 1,\n    result_summary TEXT,   -- 1-line only, no blobs\n    error_message TEXT,\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE\n);\n\n-- Citations\nCREATE TABLE agent_citations (\n    id TEXT PRIMARY KEY,\n    run_id TEXT NOT NULL,\n    tool_call_id TEXT NOT NULL,\n    created_at TEXT NOT NULL,\n    source_url TEXT NOT NULL,\n    title TEXT,\n    snippet TEXT NOT NULL,\n    used_in_answer BOOLEAN DEFAULT FALSE,\n    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,\n    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE\n);\n\n-- Indexes\nCREATE INDEX idx_agent_steps_run ON agent_steps(run_id);\nCREATE INDEX idx_tool_calls_run ON agent_tool_calls(run_id);\nCREATE INDEX idx_tool_calls_status ON agent_tool_calls(status);\nCREATE INDEX idx_citations_run ON agent_citations(run_id);\n```\n\n---\n\n## 8. API Design\n\n### Endpoints\n\n```\nPOST   /api/agent/runs              # Start new agent run\nGET    /api/agent/runs/{id}         # Get run status\nGET    /api/agent/runs/{id}/stream  # SSE event stream\nPOST   /api/agent/runs/{id}/cancel  # Cancel run\nGET    /api/agent/runs/{id}/trace   # Get full trace\n```\n\n### Start Run Request\n\n```json\nPOST /api/agent/runs\n{\n  \"query\": \"What is the population of Tokyo?\",\n  \"conversation_id\": \"optional-uuid\"\n}\n```\n\n### Response\n\n```json\n{\n  \"run_id\": \"uuid\",\n  \"status\": \"running\",\n  \"stream_url\": \"/api/agent/runs/{id}/stream\"\n}\n```\n\n---\n\n## 9. SSE & Streaming\n\n### Event Types\n\n| Event | When | Data |\n|-------|------|------|\n| `agent_state` | State transition | `{state: \"planning\"}` |\n| `step_start` | New step | `{step_number: 1}` |\n| `tool_start` | Tool executing | `{tool_name: \"web_search\"}` |\n| `tool_result` | Tool done | `{summary: \"Found 10 results\"}` |\n| `thinking` | Reasoning tokens | `{text: \"...\"}` |\n| `answer` | Final answer | `{text: \"...\"}` |\n| `citation` | Citation added | `{url, title, snippet}` |\n| `complete` | Run finished | `{final_answer: \"...\"}` |\n| `error` | Run failed | `{message: \"...\"}` |\n| `heartbeat` | Keep-alive | `{}` |\n\n### Resumption Support\n\n```\nGET /api/agent/runs/{id}/stream?since_seq=42\n```\n\nFrontend tracks `lastSeq` and reconnects with this parameter.\n\n---\n\n## 10. Failure Scenarios & Recovery\n\n### Model API Failures\n\n| Failure | Detection | Recovery |\n|---------|-----------|----------|\n| Rate limit (429) | HTTP status | Exponential backoff, max 3 retries |\n| Timeout (>30s) | Request timeout | Failover to Together AI |\n| 5xx error | HTTP status | Retry once, then failover |\n| All providers down | Both fail | Mark run as error |\n\n### Tool Failures\n\n| Tool | Failure | Recovery |\n|------|---------|----------|\n| web_search | API error | Retry 3x, then error |\n| web_extract | URL unreachable | Skip URL, continue |\n| python_execute | Timeout | Return timeout error to model |\n| python_execute | Crash mid-execution | **Inject hint, re-run** |\n\n### Crash Recovery\n\n| Crash Point | Recovery Action |\n|-------------|-----------------|\n| Before step created | Create step, continue |\n| After step, before model call | Redo model call |\n| During tool execution (idempotent) | Retry tool |\n| During tool execution (python_execute) | Inject hint |\n| After tool result | Mark step complete |\n\n---\n\n## 11. Deployment\n\n### Hosting\n\n| Component | Platform | Rationale |\n|-----------|----------|-----------|\n| Frontend | Vercel | Free tier, global CDN |\n| Backend | Railway | Docker support, easy SQLite |\n| Database | Turso | Distributed SQLite |\n| Sandbox | E2B | External API, 100 free credits |\n\n### Environment Variables\n\n```bash\n# Required\nDEEPINFRA_API_KEY=xxx     # Primary model provider\nPARALLEL_API_KEY=xxx      # Web search/extract\nE2B_API_KEY=xxx           # Python sandbox\n\n# Optional (for failover)\nTOGETHER_API_KEY=xxx      # Fallback model provider\n\n# Database (production)\nTURSO_DATABASE_URL=xxx\nTURSO_AUTH_TOKEN=xxx\n```\n\n---\n\n## 12. Configuration\n\n### chat_config.yaml additions\n\n```yaml\n# Model providers\nmodel_providers:\n  primary:\n    name: deepinfra\n    base_url: \"https://api.deepinfra.com/v1/openai\"\n    api_key: ${DEEPINFRA_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n  fallback:\n    name: together_ai\n    base_url: \"https://api.together.xyz/v1\"\n    api_key: ${TOGETHER_API_KEY}\n    model: \"openai/gpt-oss-120b\"\n    timeout_ms: 60000\n\n# Agent settings\nagent:\n  enabled: true\n  max_steps: 10\n  circuit_breaker:\n    failure_threshold: 5\n    recovery_timeout_seconds: 30\n\n# Parallel.ai\nparallel:\n  base_url: \"https://api.parallel.ai/v1beta\"\n  api_key: ${PARALLEL_API_KEY}\n  search:\n    max_results: 10\n    timeout_ms: 15000\n  extract:\n    timeout_ms: 30000\n    max_urls_per_request: 5\n\n# Sandbox (E2B)\nsandbox:\n  provider: e2b\n  e2b:\n    api_key: ${E2B_API_KEY}\n    template: \"python3\"\n    timeout_seconds: 30\n    metadata:\n      app: \"reasoner\"\n```\n"}
```
---
## USER (2026-01-04T11:02:00.015Z)


---
## ASSISTANT (2026-01-04T11:02:13.431Z)

<details><summary>Thinking...</summary>

I've created both docs. Let me verify what we have and give the user a summary:

1. `docs/AGENT_IMPLEMENTATION_LOG.md` - Created (live tracking doc)
2. `docs/AGENT_SYSTEM_DESIGN.md` - Updated with all 6 fixes (E2B, DeepInfra primary, context pruner, etc.)
3. `docs/AGENT_MASTER_REFERENCE.md` - Already existed and was correct

Let me also check that all docs are properly linked and ready to go.

</details>
---
## ASSISTANT (2026-01-04T11:02:13.921Z)

Docs created. Let me verify what's in place:
---
## ASSISTANT (2026-01-04T11:02:16.167Z)

**Tool Use:** Bash
```json
{"command":"ls -la /Users/anudeepgadige/Desktop/Projects/reasoner/docs/*.md","description":"List all docs"}
```
---
## USER (2026-01-04T11:03:39.056Z)


---
## ASSISTANT (2026-01-04T11:03:45.119Z)

<details><summary>Thinking...</summary>

All docs are in place. Let me give the user a summary of what was created.

</details>
---
## ASSISTANT (2026-01-04T11:03:51.581Z)

All docs are now in place:

| Document | Status | Purpose |
|----------|--------|---------|
| [AGENT_IMPLEMENTATION_LOG.md](docs/AGENT_IMPLEMENTATION_LOG.md) | **NEW** | Live tracking - phase progress, handoff notes |
| [AGENT_SYSTEM_DESIGN.md](docs/AGENT_SYSTEM_DESIGN.md) | **UPDATED** | Full design with all 6 fixes |
| [AGENT_MASTER_REFERENCE.md](docs/AGENT_MASTER_REFERENCE.md) | Existing | Quick reference (schema, API, commands) |

**Key updates in AGENT_SYSTEM_DESIGN.md:**
- E2B sandbox (not Docker)
- DeepInfra primary ($0.09), Together fallback
- Context Pruner section
- Hint injection for python_execute recovery
- No result_raw in schema (WAL bloat fix)
- Session cleanup on startup

**AGENT_IMPLEMENTATION_LOG.md structure:**
- Current status (phase, branch, blockers)
- Quick resume for new chats
- Next steps with commands
- Phase-by-phase progress tracking
- Key documents reference

Ready to start Phase 1 when you are.
---
## USER (2026-01-04T11:04:01.450Z)

Caveat: The messages below were generated by the user while running local commands. DO NOT respond to these messages or otherwise consider them in your response unless the user explicitly asks you to.
---
## USER (2026-01-04T11:04:00.258Z)

<command-name>/compact</command-name>
            <command-message>compact</command-message>
            <command-args></command-args>
---
## USER (2026-01-04T11:04:01.449Z)

<local-command-stderr>Error: Error during compaction: Error: Conversation too long. Press esc twice to go up a few messages and try again.</local-command-stderr>
---
## USER (2026-01-04T11:04:13.703Z)

Caveat: The messages below were generated by the user while running local commands. DO NOT respond to these messages or otherwise consider them in your response unless the user explicitly asks you to.
---
## USER (2026-01-04T11:04:12.430Z)

<command-name>/compact</command-name>
            <command-message>compact</command-message>
            <command-args></command-args>
---
## USER (2026-01-04T11:04:13.703Z)

<local-command-stderr>Error: Error during compaction: Error: Conversation too long. Press esc twice to go up a few messages and try again.</local-command-stderr>
---
## USER (2026-01-04T11:04:24.663Z)

Caveat: The messages below were generated by the user while running local commands. DO NOT respond to these messages or otherwise consider them in your response unless the user explicitly asks you to.
---
## USER (2026-01-04T11:04:22.757Z)

<command-name>/compact</command-name>
            <command-message>compact</command-message>
            <command-args></command-args>
---
## USER (2026-01-04T11:04:24.663Z)

<local-command-stderr>Error: Error during compaction: Error: Conversation too long. Press esc twice to go up a few messages and try again.</local-command-stderr>
---
## USER (2026-01-04T11:05:02.258Z)

<ide_opened_file>The user opened the file /Users/anudeepgadige/Desktop/Projects/reasoner/docs/AGENT_SYSTEM_DESIGN.md in the IDE. This may or may not be related to the current task.</ide_opened_file>

continue with commits for these docs once done let me know
---
## ASSISTANT (2026-01-04T11:05:11.089Z)

<details><summary>Thinking...</summary>

The user wants me to commit the docs that I created. Let me commit them now.

</details>
---
## ASSISTANT (2026-01-04T11:05:11.736Z)

**Tool Use:** Bash
```json
{"command":"git status","description":"Check git status"}
```
---
## USER (2026-01-04T11:05:11.839Z)


---
## ASSISTANT (2026-01-04T11:05:19.018Z)

<details><summary>Thinking...</summary>

The docs/ folder is untracked. Let me add and commit it.

</details>
---
## ASSISTANT (2026-01-04T11:05:23.919Z)

**Tool Use:** Bash
```json
{"command":"git add docs/ && git commit -m \"$(cat <<'EOF'\ndocs: add comprehensive agent system documentation\n\n- AGENT_IMPLEMENTATION_LOG.md: Live tracking doc for phase progress\n- AGENT_SYSTEM_DESIGN.md: Complete system design with all 6 critical fixes\n  - E2B sandbox (not Docker)\n  - DeepInfra primary provider\n  - Context pruner for token management\n  - Hint injection for crash recovery\n  - No result_raw to prevent WAL bloat\n  - Session cleanup on startup\n- AGENT_MASTER_REFERENCE.md: Quick reference (schema, API, commands)\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n\nCo-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>\nEOF\n)\"","description":"Commit docs"}
```
---
## USER (2026-01-04T11:05:24.043Z)


---
## ASSISTANT (2026-01-04T11:05:31.177Z)

<details><summary>Thinking...</summary>

Good, committed. Let me verify the commit.

</details>
---
## ASSISTANT (2026-01-04T11:05:31.648Z)

**Tool Use:** Bash
```json
{"command":"git log -1 --stat","description":"Verify commit"}
```
---
## USER (2026-01-04T11:05:31.752Z)


---
## ASSISTANT (2026-01-04T11:05:38.609Z)

<details><summary>Thinking...</summary>

Commit done. Let me give the user a summary.

</details>
---
## ASSISTANT (2026-01-04T11:05:41.905Z)

Done. Docs committed:

```
commit 561437a
docs: add comprehensive agent system documentation

6 files changed, 4074 insertions(+)
 - AGENT_IMPLEMENTATION_LOG.md (148 lines) - Live tracking
 - AGENT_SYSTEM_DESIGN.md (605 lines) - Full design with all 6 fixes
 - AGENT_MASTER_REFERENCE.md (323 lines) - Quick reference
 - Plus existing research/design docs
```

**Ready for Phase 1.** Next steps:
1. Create branch: `git checkout -b feature/agent-phase-1-data-layer`
2. Implement data layer (schema, models, repo, tests)
3. Update implementation log with progress
---
## USER (2026-01-04T11:06:07.056Z)

cool i want you to merge this branch in the main and compact this conversation to conitnue in the next one
---
## ASSISTANT (2026-01-04T11:06:19.691Z)

<details><summary>Thinking...</summary>

The user wants me to:
1. Merge the current branch (cleanup/remove-dead-code) into main
2. The conversation is too long to compact automatically

Let me merge the branch first.

</details>
---
## ASSISTANT (2026-01-04T11:06:20.999Z)

**Tool Use:** Bash
```json
{"command":"git checkout main && git merge cleanup/remove-dead-code --no-edit","description":"Merge cleanup branch to main"}
```
---
## USER (2026-01-04T11:06:24.540Z)


---
## ASSISTANT (2026-01-04T11:06:30.213Z)

<details><summary>Thinking...</summary>

Merged successfully. Now the user wants to compact but it's too long. Let me give them a summary they can use for the next conversation.

</details>
---
## ASSISTANT (2026-01-04T11:06:34.127Z)

Merged to main. 

**For next conversation, start with:**

> "Continue implementing the web research agent. Read `docs/AGENT_IMPLEMENTATION_LOG.md` for current status and `.claude/plans/lazy-purring-nygaard.md` for the full plan. Start Phase 1: Data Layer."

**Current state:**
- **Branch:** `main` (docs merged)
- **Next:** Create `feature/agent-phase-1-data-layer` branch
- **Docs ready:** Implementation log, system design, master reference
---
## USER (2026-01-04T11:07:28.802Z)

in that case write a summary of this convo wrt to your compact template in a doc then i'll reference that doc for next chat
---
## ASSISTANT (2026-01-04T11:07:35.027Z)

Prompt is too long
