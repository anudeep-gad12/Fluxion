# Data Flow

Complete documentation of request lifecycles, streaming patterns, and data flow in the Reasoner system.

## Table of Contents

1. [Chat Mode Flow](#chat-mode-flow)
2. [Research/Agent Mode Flow](#researchagent-mode-flow)
3. [CLI Data Flow](#cli-data-flow)
4. [Tool Approval Flow](#tool-approval-flow)
5. [Context Pipeline](#context-pipeline)
6. [Provider Failover Flow](#provider-failover-flow)
7. [SSE Streaming Protocol](#sse-streaming-protocol)
8. [Database Operations](#database-operations)
9. [Model Selection Flow](#model-selection-flow)
10. [ChatGPT OAuth Flow](#chatgpt-oauth-flow)

---

## Chat Mode Flow

### Overview

Chat mode processes a single user message and returns a streamed response with optional thinking display.

### Sequence Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Browser │     │  React   │     │  FastAPI │     │  Chat    │     │  LLM     │     │  SQLite  │
│          │     │  + Store │     │  Routes  │     │  Engine  │     │ Provider │     │          │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │                │                │
     │  User types    │                │                │                │                │
     │  message       │                │                │                │                │
     │───────────────>│                │                │                │                │
     │                │                │                │                │                │
     │                │ POST /api/conversations/{id}/runs                │                │
     │                │ {message, thinking_mode, reasoning_effort}       │                │
     │                │───────────────>│                │                │                │
     │                │                │                │                │                │
     │                │                │ Generate run_id│                │                │
     │                │                │ Create Queue   │                │                │
     │                │                │───────────────>│                │                │
     │                │                │                │                │                │
     │                │ {run_id,       │                │                │                │
     │                │  stream_url}   │                │                │                │
     │                │<───────────────│                │                │                │
     │                │                │                │                │                │
     │                │ Subscribe to   │                │                │                │
     │                │ SSE stream     │                │                │                │
     │                │───────────────>│                │                │                │
     │                │                │                │                │                │
     │                │                │ Background:    │                │                │
     │                │                │ run_chat()     │                │                │
     │                │                │───────────────>│                │                │
     │                │                │                │                │                │
     │                │                │                │ Load history   │                │
     │                │                │                │────────────────────────────────>│
     │                │                │                │<───────────────────────────────│
     │                │                │                │                │                │
     │                │                │                │ Create run     │                │
     │                │                │                │ status=running │                │
     │                │                │                │────────────────────────────────>│
     │                │                │                │                │                │
     │                │                │                │ Build messages │                │
     │                │                │                │ (system + history + user)       │
     │                │                │                │                │                │
     │                │                │                │ complete_      │                │
     │                │                │                │ streaming()    │                │
     │                │                │                │───────────────>│                │
     │                │                │                │                │                │
     │                │                │                │                │ Stream tokens  │
     │                │                │                │<─ ─ ─ ─ ─ ─ ─ ─│                │
     │                │                │                │   (on_token,   │                │
     │                │                │                │    on_reason)  │                │
     │                │                │                │                │                │
     │                │                │                │ StreamParser   │                │
     │                │                │                │ routes tokens  │                │
     │                │                │                │                │                │
     │                │ SSE: {type:    │<───────────────│                │                │
     │                │ "THINKING_     │ event_callback │                │                │
     │                │  TOKEN"}       │                │                │                │
     │<───────────────│                │                │                │                │
     │                │                │                │                │                │
     │  Display       │                │                │                │                │
     │  thinking      │                │                │                │                │
     │                │                │                │                │                │
     │                │ SSE: {type:    │<───────────────│                │                │
     │                │ "TOKEN"}       │                │                │                │
     │<───────────────│                │                │                │                │
     │                │                │                │                │                │
     │  Display       │                │                │                │                │
     │  answer        │                │                │                │                │
     │                │                │                │                │                │
     │                │                │                │<───────────────│ LLMResponse    │
     │                │                │                │                │                │
     │                │                │                │ Record trace   │                │
     │                │                │                │ events         │                │
     │                │                │                │────────────────────────────────>│
     │                │                │                │                │                │
     │                │                │                │ Update run     │                │
     │                │                │                │ status=succeeded│               │
     │                │                │                │ final_answer   │                │
     │                │                │                │────────────────────────────────>│
     │                │                │                │                │                │
     │                │ SSE: event:    │<───────────────│                │                │
     │                │ complete       │                │                │                │
     │<───────────────│                │                │                │                │
     │                │                │                │                │                │
     │  Update UI     │                │                │                │                │
     │  final state   │                │                │                │                │
     │                │                │                │                │                │
```

### Step-by-Step Flow

1. **User Input**
   - User types message in `ConversationView.tsx`
   - Form submission triggers `handleSubmit()`

2. **Create Run Request**
   - Frontend calls `POST /api/conversations/{id}/runs`
   - Request body: `{message, thinking_mode, reasoning_effort}`

3. **Backend Initialization**
   - Generate `run_id` (UUID[:8])
   - Create `asyncio.Queue` for SSE events
   - Start background task `run_chat()`
   - Return `{run_id, stream_url}` immediately

4. **SSE Subscription**
   - Frontend subscribes to `GET /api/runs/{run_id}/stream`
   - `useSSE` hook manages connection

5. **Chat Execution (Background)**
   - Load conversation history from SQLite
   - Create run record with `status="running"`
   - Build message list (system prompt + history + user message)
   - Call `LLMProvider.complete_streaming()`

6. **Token Streaming**
   - `on_token()` callback receives tokens
   - `StreamParser.feed()` separates thinking/answer tokens
   - Events pushed to queue: `{type: "TOKEN"}` or `{type: "THINKING_TOKEN"}`

7. **SSE Delivery**
   - `EventSourceResponse` streams events from queue
   - Frontend receives and updates store

8. **Completion**
   - Record trace events (llm_request, llm_response)
   - Update run with `final_answer`, `status="succeeded"`
   - Send `event: complete` with full result

---

## Research/Agent Mode Flow

### Overview

Research mode runs an agent loop that plans, calls tools, and synthesizes an answer with citations.

### Sequence Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Browser │     │  React   │     │  FastAPI │     │  Agent   │     │  LLM     │     │  Tools   │
│          │     │  + Store │     │  Routes  │     │  Engine  │     │ Provider │     │          │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │                │                │
     │  User enters   │                │                │                │                │
     │  research query│                │                │                │                │
     │───────────────>│                │                │                │                │
     │                │                │                │                │                │
     │                │ POST /api/agent/runs            │                │                │
     │                │ {query, conversation_id, max_steps}              │                │
     │                │───────────────>│                │                │                │
     │                │                │                │                │                │
     │                │                │ Create run_id  │                │                │
     │                │                │ Start background│               │                │
     │                │                │───────────────>│                │                │
     │                │                │                │                │                │
     │                │ {run_id,       │                │                │                │
     │                │  stream_url}   │                │                │                │
     │                │<───────────────│                │                │                │
     │                │                │                │                │                │
     │                │ Subscribe to   │                │                │                │
     │                │ agent stream   │                │                │                │
     │                │───────────────>│                │                │                │
     │                │                │                │                │                │
     │                │ SSE: agent_state               │                │                │
     │<───────────────│<───────────────│<──────────────│                │                │
     │                │                │                │                │                │
     │                │                │                │ ═══════════════════════════════│
     │                │                │                │      AGENT LOOP (per step)     │
     │                │                │                │ ═══════════════════════════════│
     │                │                │                │                │                │
     │                │ SSE: step_start│<──────────────│ Step N started │                │
     │<───────────────│<───────────────│                │                │                │
     │                │                │                │                │                │
     │                │                │                │ Prune context  │                │
     │                │                │                │ (token budget) │                │
     │                │                │                │                │                │
     │                │                │                │ complete() with│                │
     │                │                │                │ tool schemas   │                │
     │                │                │                │───────────────>│                │
     │                │                │                │                │                │
     │                │ SSE: thinking  │<──────────────│<───────────────│                │
     │<───────────────│<───────────────│                │ (streaming)    │                │
     │                │                │                │                │                │
     │                │                │                │<───────────────│ Response with  │
     │                │                │                │                │ tool_calls     │
     │                │                │                │                │                │
     │                │ SSE: tool_start│<──────────────│ Start tool     │                │
     │<───────────────│<───────────────│                │───────────────────────────────>│
     │                │                │                │                │                │
     │                │                │                │<──────────────────────────────│
     │                │                │                │                │ Tool result    │
     │                │                │                │                │                │
     │                │ SSE: tool_result<─────────────│                │                │
     │<───────────────│<───────────────│                │                │                │
     │                │                │                │                │                │
     │                │                │                │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │                │                │                │   Repeat for more tools/steps  │
     │                │                │                │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │                │                │                │                │                │
     │                │                │                │ Decision:      │                │
     │                │                │                │ synthesize     │                │
     │                │                │                │                │                │
     │                │ SSE: agent_state│<─────────────│ SYNTHESIZING   │                │
     │<───────────────│<───────────────│                │                │                │
     │                │                │                │                │                │
     │                │                │                │ Generate final │                │
     │                │                │                │ answer         │                │
     │                │                │                │───────────────>│                │
     │                │                │                │                │                │
     │                │ SSE: answer    │<──────────────│<───────────────│                │
     │<───────────────│<───────────────│                │ (streaming)    │                │
     │                │                │                │                │                │
     │                │                │                │ Extract        │                │
     │                │                │                │ citations      │                │
     │                │                │                │                │                │
     │                │ SSE: complete  │<──────────────│                │                │
     │<───────────────│<───────────────│                │                │                │
     │                │                │                │                │                │
     │  Display       │                │                │                │                │
     │  answer +      │                │                │                │                │
     │  citations     │                │                │                │                │
     │                │                │                │                │                │
```

### Agent Loop Details

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT LOOP                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

while not (synthesis_decision or step >= max_steps):
    │
    ▼
┌─────────────────────┐
│ 1. PRUNE CONTEXT    │
│ ┌─────────────────┐ │
│ │ Calculate token │ │
│ │ budget          │ │
│ │                 │ │
│ │ Remove old      │ │
│ │ tool results    │ │
│ │                 │ │
│ │ Keep recent     │ │
│ │ context         │ │
│ └─────────────────┘ │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. LLM CALL         │
│ ┌─────────────────┐ │
│ │ Messages:       │ │
│ │ - System prompt │ │
│ │ - Prior steps   │ │
│ │ - Tool results  │ │
│ │ - Current query │ │
│ │                 │ │
│ │ Tools:            │ │
│ │ - python_execute  │ │
│ │ - web_search      │ │
│ │ - web_extract     │ │
│ └───────────────────┘ │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. PARSE RESPONSE   │
│ ┌─────────────────┐ │
│ │ Decision:       │ │
│ │ ├─ call_tool    │──────┐
│ │ ├─ synthesize   │─────┐│
│ │ └─ error        │     ││
│ └─────────────────┘     ││
└─────────────────────────┼┼───────────────────────────────────────────────────────┐
                          ││                                                       │
           ┌──────────────┘│                                                       │
           │               │                                                       │
           ▼               │                                                       │
┌─────────────────────┐    │                                                       │
│ 4a. EXECUTE TOOLS   │    │                                                       │
│ ┌─────────────────┐ │    │                                                       │
│ │ For each tool:  │ │    │                                                       │
│ │                 │ │    │                                                       │
│ │ 1. Check        │ │    │                                                       │
│ │    idempotency  │ │    │                                                       │
│ │                 │ │    │                                                       │
│ │ 2. Execute tool │ │    │                                                       │
│ │                 │ │    │                                                       │
│ │ 3. Record       │ │    │                                                       │
│ │    result       │ │    │                                                       │
│ │                 │ │    │                                                       │
│ │ 4. Emit SSE     │ │    │                                                       │
│ │    tool_result  │ │    │                                                       │
│ └─────────────────┘ │    │                                                       │
└──────────┬──────────┘    │                                                       │
           │               │                                                       │
           │ Continue loop │                                                       │
           └───────────────┼───────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌─────────────────────┐
              │ 4b. SYNTHESIZE      │
              │ ┌─────────────────┐ │
              │ │ Generate final  │ │
              │ │ answer from     │ │
              │ │ tool results    │ │
              │ │                 │ │
              │ │ Stream tokens   │ │
              │ │ via SSE         │ │
              │ │                 │ │
              │ │ Extract         │ │
              │ │ citations       │ │
              │ └─────────────────┘ │
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ 5. COMPLETE         │
              │ ┌─────────────────┐ │
              │ │ Update run      │ │
              │ │ status=complete │ │
              │ │                 │ │
              │ │ Emit SSE        │ │
              │ │ complete event  │ │
              │ └─────────────────┘ │
              └─────────────────────┘
```

---

## CLI Data Flow

### Overview

The CLI/TUI communicates with the same FastAPI backend as the web UI, using HTTP for commands and SSE for streaming events. The key difference is the tool approval flow.

### Sequence Diagram

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Terminal  │     │ Textual  │     │  API     │     │  FastAPI │     │  Agent   │
│          │     │ Widgets  │     │  Client  │     │  Routes  │     │  Engine  │
└────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                │                │                │                │
     │  User types    │                │                │                │
     │  query         │                │                │                │
     │───────────────>│                │                │                │
     │                │                │                │                │
     │                │ InputArea.     │                │                │
     │                │ Submitted      │                │                │
     │                │───────────────>│                │                │
     │                │                │                │                │
     │                │                │ POST /api/agent/runs             │
     │                │                │ {query, profile: "coding",      │
     │                │                │  permission: "relaxed",         │
     │                │                │  working_dir: "/path"}          │
     │                │                │───────────────>│                │
     │                │                │                │ Start engine   │
     │                │                │                │───────────────>│
     │                │                │                │                │
     │                │                │ {run_id,       │                │
     │                │                │  stream_token} │                │
     │                │                │<───────────────│                │
     │                │                │                │                │
     │                │                │ GET /stream?token=xxx            │
     │                │                │───────────────>│                │
     │                │                │                │                │
     │                │                │ SSE: step_start│                │
     │                │ StepStartEvent │<───────────────│<──────────────│
     │                │<───────────────│                │                │
     │  StatusBar     │                │                │                │
     │  "Step 1/25"   │                │                │                │
     │<───────────────│                │                │                │
     │                │                │                │                │
     │                │                │ SSE: tool_start│                │
     │                │ ToolStartEvent │<───────────────│<──────────────│
     │                │<───────────────│                │                │
     │  ToolCallPanel │                │                │                │
     │  ▸ read_file() │                │                │                │
     │<───────────────│                │                │                │
     │                │                │                │                │
     │                │                │ SSE: tool_approval_required     │
     │                │ ToolApproval   │<───────────────│<──────────────│
     │                │ RequiredEvent  │                │  (bash tool)  │
     │                │<───────────────│                │                │
     │  InputArea →   │                │                │                │
     │  approval mode │                │                │                │
     │  "[y/n] bash..."│               │                │                │
     │<───────────────│                │                │                │
     │                │                │                │                │
     │  User: y       │                │                │                │
     │───────────────>│                │                │                │
     │                │ ApprovalDecision                │                │
     │                │───────────────>│                │                │
     │                │                │ POST /approve/ │                │
     │                │                │ {tool_call_id} │                │
     │                │                │───────────────>│ Future.set(T)  │
     │                │                │                │───────────────>│
     │                │                │                │                │
     │                │                │ SSE: tool_result                │
     │                │ ToolResultEvent│<───────────────│<──────────────│
     │                │<───────────────│                │                │
     │  ToolCallPanel │                │                │                │
     │  ✓ bash (2.3s) │                │                │                │
     │<───────────────│                │                │                │
     │                │                │                │                │
     │                │                │ SSE: answer    │                │
     │                │ AnswerToken    │<───────────────│<──────────────│
     │                │ Event          │                │                │
     │                │<───────────────│                │                │
     │  StreamingMD   │                │                │                │
     │  renders answer │               │                │                │
     │<───────────────│                │                │                │
     │                │                │                │                │
     │                │                │ SSE: complete  │                │
     │                │ AgentComplete  │<───────────────│<──────────────│
     │                │ Event          │                │                │
     │                │<───────────────│                │                │
     │  Show context  │                │                │                │
     │  usage in bar  │                │                │                │
     │<───────────────│                │                │                │
```

### Key Differences from Web UI

| Aspect | Web UI | CLI/TUI |
|--------|--------|---------|
| Profile | `research` (default) | `coding` (always) |
| Tools | web + python | web + python + filesystem |
| Approval | Not supported | Permission-gated (strict/relaxed/yolo) |
| Context | Date only | 5-layer project context |
| Provider | Request header override | `--provider` flag or `/login` command |
| Session | Cookie-based | `X-CLI-Session` header |

---

## Tool Approval Flow

### Permission Decision Tree

```
┌───────────────────────────────────────────────────────────┐
│                  TOOL APPROVAL DECISION                     │
└───────────────────────────────────────────────────────────┘

         Tool execution requested
                   │
                   ▼
         ┌──────────────────┐
         │ Tool permission  │
         │ level?           │
         └────────┬─────────┘
                  │
     ┌────────────┼────────────────┐
     ▼            ▼                ▼
  "auto"      "confirm"       "dangerous"
  (read-only)  (write ops)    (bash)
     │            │                │
     ▼            │                │
  Execute         │                │
  immediately     │                │
                  ▼                ▼
         ┌──────────────────┐
         │ Policy?          │
         └────────┬─────────┘
                  │
     ┌────────────┼────────────────┐
     ▼            ▼                ▼
  "yolo"      "relaxed"       "strict"
     │            │                │
     ▼            │                │
  Execute         ▼                ▼
  immediately  ┌──────────┐   Require
               │ confirm  │   approval
               │ or       │   for ALL
               │ dangerous?│   (incl.
               └──┬───┬───┘   confirm)
              yes │   │ no        │
                  │   ▼           │
                  │ Execute       │
                  │ immediately   │
                  ▼               ▼
         ┌──────────────────────────┐
         │    APPROVAL REQUIRED      │
         │                           │
         │  1. Create Future[bool]   │
         │  2. Emit SSE event:       │
         │     tool_approval_required│
         │  3. Wait for response     │
         │     (5 min timeout)       │
         └─────────┬────────────────┘
                   │
          ┌────────┴─────────┐
          ▼                  ▼
     /approve/          /deny/ or timeout
          │                  │
          ▼                  ▼
     Execute tool       Skip tool
     Record:            Record:
     approval_decision  approval_decision
     = "approved"       = "denied"/"timeout"
```

### Backend State

The approval flow uses in-memory state (single-process):

```python
_approval_queues: Dict[run_id, Dict[tool_call_id, asyncio.Future[bool]]]
```

- Agent engine creates a `Future` when approval is needed
- `/approve/{tool_call_id}` resolves with `True`
- `/deny/{tool_call_id}` resolves with `False`
- Timeout (5 min): resolves with `False` automatically
- Futures are cleaned up when the run completes

---

## Context Pipeline

### Agent Loop with Context Management

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      AGENT LOOP (with context pipeline)                          │
└─────────────────────────────────────────────────────────────────────────────────┘

Step 0: INITIALIZATION
    │
    ├── Load AgentProfile (research or coding)
    ├── Build context via ContextStrategy:
    │   ├── Research: date + knowledge cutoff
    │   └── Coding: environment + rules + structure + git + working_dir
    ├── Format system prompt with context slots
    └── Create planner with profile-specific prompt
    │
    ▼
Step 1: PLANNING (optional)
    │
    ├── Planner generates ResearchPlan
    ├── Plan injected into system message (not separate message)
    └── Plan includes: analysis, approach, steps with tool hints
    │
    ▼
Step 2+: MAIN LOOP (while not synthesis and step < max_steps)
    │
    ├── 1. CONTEXT PRUNING (ContextPruner)
    │   ├── Calculate current token usage
    │   ├── If over budget:
    │   │   ├── Keep last 2 steps detailed
    │   │   ├── Summarize older tool results via LLM
    │   │   │   (query-aware: only facts relevant to user query)
    │   │   ├── Python output: head/tail pattern (not LLM)
    │   │   └── Cache summaries to prevent duplicate LLM calls
    │   └── Fallback to basic truncation on error
    │
    ├── 2. HISTORY BUILDING (HistoryBuilder)
    │   ├── Load prior runs for conversation
    │   ├── Use turn_summary if available (~10x more history)
    │   ├── Else use raw user_message + final_answer pairs
    │   └── Apply token budget with sliding window
    │
    ├── 3. LLM CALL with tool schemas
    │   └── Messages: system + history + current context + user query
    │
    ├── 4. PARSE RESPONSE
    │   ├── tool_calls → check approval → execute tools → extract findings
    │   └── synthesize decision → break to synthesis
    │
    └── 5. RECORD (DB + SSE events)
    │
    ▼
SYNTHESIS
    │
    ├── Generate final answer (streaming)
    ├── Include accumulated findings in prompt
    ├── Store turn_summary for future context
    └── Extract citations
```

---

## Provider Failover Flow

### Circuit Breaker State Machine

```
                                    Request arrives
                                          │
                                          ▼
                               ┌─────────────────────┐
                               │ Check circuit state │
                               └──────────┬──────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
             ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
             │   CLOSED    │       │    OPEN     │       │  HALF_OPEN  │
             │  (healthy)  │       │ (unhealthy) │       │  (testing)  │
             └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
                    │                     │                     │
                    ▼                     ▼                     ▼
           ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
           │ Try request    │    │ Check timeout  │    │ Try test       │
           └───────┬────────┘    └───────┬────────┘    │ request        │
                   │                     │             └───────┬────────┘
           ┌───────┴───────┐     ┌───────┴───────┐            │
           │               │     │               │     ┌──────┴──────┐
           ▼               ▼     ▼               ▼     │             │
      ┌─────────┐    ┌─────────┐ │          ┌────────┐ ▼             ▼
      │ Success │    │ Failure │ │          │Expired │Success      Failure
      └────┬────┘    └────┬────┘ │          └───┬────┘  │             │
           │              │      │              │       │             │
           │              ▼      │              ▼       ▼             ▼
           │    ┌──────────────┐ │   ┌──────────────┐ Record       Record
           │    │ failures++   │ │   │ Try HALF_OPEN│ success      failure
           │    └──────┬───────┘ │   └──────────────┘   │             │
           │           │         │                      │             │
           │    ┌──────┴──────┐  │               ┌──────┴──────┐      │
           │    │ >= threshold?│  │               │>=threshold? │      │
           │    └──────┬──────┘  │               └──────┬──────┘      │
           │           │         │                      │             │
           │     Yes   │  No     │                Yes   │  No         │
           │     ┌─────┴──┐      │                ┌─────┴──┐          │
           │     ▼        │      ▼                ▼        │          │
           │ ┌──────┐     │ ┌──────────┐     ┌──────┐      │          │
           │ │ OPEN │     │ │ Reject   │     │CLOSED│      │          │
           │ └──────┘     │ │ request  │     └──────┘      │          │
           │              │ └──────────┘                   │          │
           │              │                                │          │
           ▼              ▼                                ▼          ▼
      ┌───────────────────────────────────────────────────────────────────┐
      │                         Return result                              │
      └───────────────────────────────────────────────────────────────────┘
```

### Provider Chain Failover

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           PROVIDER CHAIN FAILOVER                                │
└─────────────────────────────────────────────────────────────────────────────────┘

Providers sorted by priority:
  [0] DeepInfra (priority: 0)
  [1] Together.ai (priority: 1)
  [2] Local vLLM (priority: 2)

                         Request arrives
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Try Provider [0]    │
                    │ (DeepInfra)         │
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
              ▼                                 ▼
       ┌─────────────┐                   ┌─────────────┐
       │   Success   │                   │   Failure   │
       │             │                   │ or circuit  │
       │             │                   │ OPEN        │
       └──────┬──────┘                   └──────┬──────┘
              │                                 │
              ▼                                 ▼
       ┌─────────────┐                ┌─────────────────────┐
       │  Return     │                │ Try Provider [1]    │
       │  response   │                │ (Together.ai)       │
       └─────────────┘                └──────────┬──────────┘
                                                 │
                                ┌────────────────┴────────────────┐
                                │                                 │
                                ▼                                 ▼
                         ┌─────────────┐                   ┌─────────────┐
                         │   Success   │                   │   Failure   │
                         └──────┬──────┘                   └──────┬──────┘
                                │                                 │
                                ▼                                 ▼
                         ┌─────────────┐                ┌─────────────────────┐
                         │  Return     │                │ Try Provider [2]    │
                         │  response   │                │ (Local vLLM)        │
                         └─────────────┘                └──────────┬──────────┘
                                                                   │
                                                  ┌────────────────┴────────────────┐
                                                  │                                 │
                                                  ▼                                 ▼
                                           ┌─────────────┐                   ┌─────────────┐
                                           │   Success   │                   │   Failure   │
                                           └──────┬──────┘                   └──────┬──────┘
                                                  │                                 │
                                                  ▼                                 ▼
                                           ┌─────────────┐                ┌──────────────────┐
                                           │  Return     │                │ AllProvidersFailed│
                                           │  response   │                │ Error            │
                                           └─────────────┘                └──────────────────┘
```

### Retry Logic Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              RETRY LOGIC                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

                         Request to provider
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Attempt 1           │
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
              ▼                                 ▼
       ┌─────────────┐                   ┌─────────────┐
       │   Success   │                   │   Failure   │
       └──────┬──────┘                   └──────┬──────┘
              │                                 │
              ▼                                 ▼
       ┌─────────────┐                ┌─────────────────────┐
       │  Return     │                │ Is status retryable?│
       │  response   │                │ [429,500,502,503,504]│
       └─────────────┘                └──────────┬──────────┘
                                                 │
                                    ┌────────────┴────────────┐
                                    │                         │
                                    ▼                         ▼
                               ┌─────────┐               ┌─────────┐
                               │   Yes   │               │   No    │
                               └────┬────┘               └────┬────┘
                                    │                         │
                                    ▼                         ▼
                         ┌─────────────────────┐       ┌─────────────┐
                         │ Calculate delay:    │       │ Raise error │
                         │                     │       └─────────────┘
                         │ base * 2^attempt    │
                         │ + random jitter     │
                         │                     │
                         │ Attempt 1: ~1.0s    │
                         │ Attempt 2: ~2.0s    │
                         │ Attempt 3: ~4.0s    │
                         │ (max 30s)           │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ await sleep(delay)  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ attempts < max?     │
                         └──────────┬──────────┘
                                    │
                       ┌────────────┴────────────┐
                       │                         │
                       ▼                         ▼
                  ┌─────────┐               ┌─────────────────┐
                  │   Yes   │               │       No        │
                  └────┬────┘               └────────┬────────┘
                       │                             │
                       ▼                             ▼
                ┌─────────────┐               ┌─────────────────┐
                │ Retry       │               │ MaxRetries      │
                │ (loop back) │               │ Exceeded Error  │
                └─────────────┘               └─────────────────┘
```

---

## SSE Streaming Protocol

### Event Format

All SSE events follow this structure:

```
event: <event_name>
data: <json_payload>

```

### Chat Mode Events

| Event Type | When | Payload |
|-----------|------|---------|
| `data` | Token stream | `{type: "TOKEN", content: "..."}` or `{type: "THINKING_TOKEN", content: "..."}` |
| `event: complete` | Stream end | Full `RunResponse` object |
| `event: error` | Error occurred | `{error: "...", code: "..."}` |
| `event: aborted` | User aborted | `{message: "Run aborted"}` |

### Chat Event Flow

```
Connection opened
        │
        ▼
┌─────────────────┐
│ data: {type:    │
│ "CHAT_STARTED"} │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     (repeated for each token)
│ data: {type:    │◄────────────────────────────┐
│ "THINKING_TOKEN"│                             │
│ content: "..."}│                              │
└────────┬────────┘                             │
         │                                      │
         ▼                                      │
┌─────────────────┐                             │
│ data: {type:    │◄───────────────────────────┐│
│ "TOKEN",        │                            ││
│ content: "..."}│                             ││
└────────┬────────┘                            ││
         │                                     ││
         ├─────────────────────────────────────┘│
         │ (more tokens)                        │
         ├──────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ event: complete │
│ data: {run_id,  │
│ final_answer,   │
│ ...}            │
└────────┬────────┘
         │
         ▼
   Connection closed
```

### Agent Mode Events

| Event Type | When | Payload |
|-----------|------|---------|
| `agent_state` | State change | `{state: "...", current_step: N, max_steps: M}` |
| `step_start` | New step | `{step_number: N, steps_remaining: M}` |
| `thinking` | Thinking token | `{content: "..."}` |
| `tool_start` | Tool starting | `{tool_call_id, tool_name, arguments}` |
| `tool_approval_required` | Approval needed | `{tool_call_id, tool_name, arguments}` |
| `tool_result` | Tool finished | `{tool_call_id, success, result_summary}` |
| `answer` | Answer token | `{content: "..."}` |
| `complete` | Agent done | `{final_answer, citations, total_steps, timing_ms}` |
| `error` | Error occurred | `{error: "...", step: N}` |
| `cancelled` | User cancelled | `{message: "..."}` |
| `heartbeat` | Keep-alive | `{}` |

**Agent SSE Architecture** (cursor-based pub/sub):
- Events are appended to an in-memory `_event_history[run_id]` list (append-only log)
- Each SSE generator maintains its own read `cursor` index into the shared history
- New events notify all waiting generators via `_event_notify[run_id]` (`asyncio.Event`)
- Each generator reads `history[cursor:]` and advances its cursor independently
- This allows multiple concurrent clients (reconnects, React StrictMode double-mount) to each receive ALL events without interference
- Chat mode uses a simpler `asyncio.Queue` approach (single consumer per run)

### Agent Event Flow

```
Connection opened
        │
        ▼
┌──────────────────────┐
│ agent_state          │
│ {state: "init",      │
│  current_step: 0,    │
│  max_steps: 10}      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ step_start           │
│ {step_number: 1,     │
│  steps_remaining: 9} │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     (repeated)
│ thinking             │◄────────────────────────┐
│ {content: "..."}     │                         │
└──────────┬───────────┘                         │
           │                                     │
           ├─────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│ tool_start           │
│ {tool_call_id: "...",│
│  tool_name: "search",│
│  arguments: {...}}   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ tool_result          │
│ {tool_call_id: "...",│
│  success: true,      │
│  result_summary: "...│
│  duration_ms: 1234}  │
└──────────┬───────────┘
           │
           │ (may repeat for more steps/tools)
           │
           ▼
┌──────────────────────┐
│ agent_state          │
│ {state: "synthesizing│
│  current_step: 3}    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     (repeated)
│ answer               │◄────────────────────────┐
│ {content: "..."}     │                         │
└──────────┬───────────┘                         │
           │                                     │
           ├─────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│ complete             │
│ {final_answer: "...",│
│  citations: [...],   │
│  total_steps: 3,     │
│  timing_ms: 5432}    │
└──────────┬───────────┘
           │
           ▼
   Connection closed
```

### SSE Resumption & Stream Token Auth

Agent streams support resumption and token-authenticated reconnection:

```
GET /api/agent/runs/{run_id}/stream?token=abc123&since_seq=15
```

**Stream Token Flow**:
1. `POST /api/agent/runs` generates `secrets.token_urlsafe(16)` per run
2. Frontend stores token in `localStorage` (`stream_token:{runId}`)
3. On reconnect (page reload), frontend reads token from `localStorage`
4. Token passed as `?token=` query parameter on SSE connection
5. Server validates: rejects only if token provided but wrong (403)
6. Token cleaned up from `localStorage` and server on complete/error

**Reconnection Flow**:
1. On page reload, `loadConversation()` detects running agent runs
2. Reads stream token from `localStorage`
3. Calls `subscribe(runId, 0, streamToken)` to reconnect (skipped if `subscribedRunRef` indicates `handleSubmit` already subscribed)
4. Server creates a new SSE generator with its own read cursor into the append-only `_event_history[run_id]` log
5. Generator reads all events from cursor position, advancing independently of other clients
6. Events with `seq <= since_seq` are skipped (deduplication)
7. Client receives full state: past steps, thinking, tool calls, then live stream
8. `connectionIdRef` guard on the frontend drops events from any stale EventSource connections

---

## Database Operations

### Write Patterns

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE WRITE PATTERNS                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

Chat Run Creation:
├── 1. INSERT into runs (status='running')
├── 2. For each LLM call:
│   ├── INSERT trace_event (type='llm_request', status='pending')
│   ├── INSERT trace_event (type='llm_response', status='success')
│   └── (or INSERT trace_event type='error' if failed)
├── 3. UPDATE runs (final_answer, thinking_summary, status='succeeded')
└── 4. Commit

Agent Run Creation:
├── 1. INSERT into runs (status='running', agent_state='init')
├── 2. For each step:
│   ├── INSERT agent_steps
│   ├── For each tool call:
│   │   ├── INSERT agent_tool_calls (status='pending')
│   │   ├── UPDATE agent_tool_calls (status='running')
│   │   └── UPDATE agent_tool_calls (status='success', result_summary)
│   └── UPDATE agent_steps (completed_at)
├── 3. INSERT agent_citations (from synthesis)
├── 4. UPDATE runs (final_answer, status='complete')
└── 5. Commit

Trace Event Sequence:
├── Acquire class-level asyncio.Lock (_seq_lock)
├── SELECT MAX(seq) FROM trace_events WHERE run_id = ?
├── INSERT trace_event with seq = max + 1
└── Release lock
```

### Read Patterns

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE READ PATTERNS                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

Conversation History (for chat):
├── SELECT runs WHERE conversation_id = ? ORDER BY created_at
├── For each run: deserialize model_config_snapshot, usage_stats
└── Build message list: user_message + final_answer pairs

Run Timeline:
├── SELECT trace_events WHERE run_id = ? ORDER BY seq
├── Deserialize content_json for each event
└── Return as RunTimelineResponse

Agent Trace:
├── SELECT runs WHERE run_id = ?
├── SELECT agent_steps WHERE run_id = ? ORDER BY step_number
├── SELECT agent_tool_calls WHERE run_id = ? ORDER BY created_at
├── SELECT agent_citations WHERE run_id = ?
└── Assemble AgentRunTraceResponse

Conversation List:
├── SELECT conversations WHERE status = ? ORDER BY created_at DESC
├── Optional: LIMIT ? OFFSET ?
└── Return as list
```

---

## Model Selection Flow

### Hot-Swap via Registry

```
Client (CLI Ctrl+M or API)
    │
    │ POST /api/models/select {"model": "qwen3-72b"}
    ▼
routes/models.py
    │
    │ ModelRegistry.resolve("qwen3-72b")
    │   1. Check alias match → ModelPreset
    │   2. Check provider:model_id prefix
    │   3. Fallback: auto-detect provider from model string
    ▼
ResolvedModel (model_id, provider, base_url, api_key, context_window, ...)
    │
    │ Store in module state: _active_model, _active_model_name
    ▼
Next agent/chat run reads get_active_model()
    │
    │ create_provider_for_model(resolved) in factory.py
    ▼
New OpenAICompatProvider with resolved config
    │
    │ Used for this request only (per-request resolution)
    ▼
LLM call with new provider
```

### Local Model Start/Stop

```
POST /api/models/local/start {"model_path": "/path/to/model.gguf"}
    │
    ▼
local_models.start(model_path, ctx_size)
    │
    │ subprocess: llama-server --model X --port 8080 --jinja
    │ Poll health until ready
    ▼
set_provider_override(OpenAICompatProvider(base_url=localhost:8080))
    │
    │ All subsequent LLM calls route to local server
    ▼
POST /api/models/local/stop
    │
    │ SIGTERM llama-server, clear provider override
    ▼
Reverts to cloud provider (config default or registry selection)
```

---

## ChatGPT OAuth Flow

```
CLI: /login command
    │
    │ GET /api/auth/chatgpt/login
    ▼
Backend generates PKCE pair (code_verifier, code_challenge)
    │
    │ Stores in _pending_auth[state]
    │ Starts callback server on port 1455
    ▼
Redirect URL → auth.openai.com/oauth/authorize
    │
    │ User authenticates in browser
    ▼
OAuth callback → localhost:1455/auth/callback?code=XXX&state=YYY
    │
    │ Exchange code for tokens (access_token, refresh_token)
    │ Store in chatgpt_tokens table
    │ Backup to ~/.config/reasoner/chatgpt_auth.json
    ▼
ChatGPTProvider created with access_token
    │
    │ Translates chat completions → Codex Responses API
    │ chatgpt.com/backend-api/codex/responses
    ▼
Token refresh: automatic on 401, or manual via POST /api/auth/chatgpt/refresh
```

---

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Components](COMPONENTS.md) - Detailed component documentation
- [API Reference](API_REFERENCE.md) - Complete API documentation
