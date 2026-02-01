# Data Flow

Complete documentation of request lifecycles, streaming patterns, and data flow in the Reasoner system.

## Table of Contents

1. [Chat Mode Flow](#chat-mode-flow)
2. [Research/Agent Mode Flow](#researchagent-mode-flow)
3. [Provider Failover Flow](#provider-failover-flow)
4. [SSE Streaming Protocol](#sse-streaming-protocol)
5. [Database Operations](#database-operations)

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
| `tool_result` | Tool finished | `{tool_call_id, success, result_summary}` |
| `answer` | Answer token | `{content: "..."}` |
| `complete` | Agent done | `{final_answer, citations, total_steps, timing_ms}` |
| `error` | Error occurred | `{error: "...", step: N}` |
| `cancelled` | User cancelled | `{message: "..."}` |
| `heartbeat` | Keep-alive | `{}` |

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
3. Calls `subscribe(runId, 0, streamToken)` to reconnect
4. Server replays all events from in-memory `_event_history` snapshot
5. Live events from queue are deduplicated by sequence number (`event_seq > seq`)
6. Client receives full state: past steps, thinking, tool calls, then live stream

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

## Related Documentation

- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Data Models](DATA_MODELS.md) - Complete data model reference
- [Components](COMPONENTS.md) - Detailed component documentation
- [API Reference](API_REFERENCE.md) - Complete API documentation
