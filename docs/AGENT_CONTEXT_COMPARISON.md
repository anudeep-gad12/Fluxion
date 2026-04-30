# Agent Context Handling Comparison

Date: 2026-04-30

Scope:
- `reasoner` (this repo)
- `projects/opencode`
- `projects/pi`

This document compares how each agent handles context continuity, compaction, tool-result retention, and cross-turn coding memory. The focus is the user-visible problem in `reasoner`: repeated file rereads and unnecessary token burn on follow-up coding turns.

---

## Executive summary

`opencode` and `pi` are both **session-native** coding agents.

They keep a persistent session/thread, replay real assistant/tool history into later turns, and compact that history **inside the same session** while retaining a recent raw tail.

`reasoner` is still mostly **run-native**:

- each browser agent turn is a separate run
- cross-turn history is rebuilt from `turn_summary`
- coding continuity is supplemented by a small persisted coding scratchpad
- prior raw tool transcript is not the primary continuation mechanism

That difference is the main reason `reasoner` rereads files more often.

In one line:

- `opencode` and `pi` compact a session
- `reasoner` summarizes a run

Those are not equivalent for multi-turn coding work.

---

## 1. How `reasoner` handles context today

### 1.1 Cross-turn history is summary-first

`HistoryBuilder` explicitly builds prior context from:

- `turn_summary` when present
- otherwise `user_message + final_answer`

Relevant code:

- `orchestrator/context/history_builder.py:12-19`
- `orchestrator/context/history_builder.py:81-136`

This means prior assistant/tool transcript is not replayed across turns.

### 1.2 New coding turns start from summary scaffold + working memory

Initial prompt assembly:

- build system prompt
- load prior runs for the conversation
- build summary-based history
- inject working memory
- add current user message

Relevant code:

- `orchestrator/agent/agent_engine.py:2489-2554`
- `orchestrator/agent/agent_engine.py:500-523`

### 1.3 Coding continuity is a bounded scratchpad, not a session transcript

We now persist `CodingSessionState`, but it is intentionally small:

- prior outcomes: max 6
- files inspected: max 8
- files changed: max 8
- validation results: max 8
- unresolved tasks: max 6
- raw evidence: max 8

Relevant code:

- `orchestrator/agent/coding_session.py:9-14`
- `orchestrator/agent/coding_session.py:127-147`

Stored file evidence is also compact:

- one `CodingFileState` per file
- one short excerpt
- excerpt is only the first 3 non-empty lines, capped to ~240 chars

Relevant code:

- `orchestrator/agent/agent_engine.py:738-755`
- `orchestrator/agent/agent_engine.py:971-1019`

### 1.4 Restore behavior on later coding turns

On a follow-up coding turn, `reasoner` restores:

- prior outcomes
- validation
- unresolved tasks
- recent raw evidence
- stored file summaries/excerpts if file hashes still match

Relevant code:

- `orchestrator/agent/agent_engine.py:1108-1196`

This is better than pure summary-only history, but still much weaker than replaying a persistent session transcript.

### 1.5 In-run compaction is aggressive

When prompt usage crosses threshold:

- `reasoner` compacts to:
  - base system prompt
  - one system compaction summary
  - maybe the final user tail

Relevant code:

- `orchestrator/agent/agent_engine.py:2184-2245`

If still too large, it force-prunes tool results:

- `read_file` keeps only head/tail
- `grep` keeps first chunk
- generic tool results become short placeholders

Relevant code:

- `orchestrator/agent/agent_engine.py:3599-3752`

So even inside one long run, `reasoner` preserves less raw recent context than the other two systems.

---

## 2. How `opencode` handles context

### 2.1 `opencode` is session-native

The core loop reloads session history from storage on every cycle:

- `packages/opencode/src/session/prompt.ts:1282-1288`

Specifically:

- `MessageV2.filterCompactedEffect(sessionID)` loads the retained session transcript

This means each continuation starts from the persisted session, not from a turn summary.

### 2.2 History is stored as structured message parts

`opencode` stores rich session messages containing parts such as:

- text
- reasoning
- tool calls
- tool results
- step markers
- compaction markers

Relevant code:

- `packages/opencode/src/session/message-v2.ts`

When converting to model input, `toModelMessagesEffect()` replays those parts into model-ready messages.

Relevant code:

- `packages/opencode/src/session/message-v2.ts:729-1104`

Important behavior:

- completed tool results are replayed
- pending/running tool calls are turned into synthetic interrupted results
- compacted tool outputs become `"[Old tool result content cleared]"`

This avoids malformed or dangling tool history and keeps the session resumable.

### 2.3 Compaction keeps a recent raw tail

`opencode` compaction:

- creates an anchored structured summary
- keeps a bounded recent raw tail
- stores where that retained tail begins via `tail_start_id`

Relevant code:

- summary template: `packages/opencode/src/session/compaction.ts:33-75`
- tail selection: `packages/opencode/src/session/compaction.ts:244-292`

Defaults:

- `DEFAULT_TAIL_TURNS = 2`
- recent raw preservation budget is dynamically sized

So after compaction, the model still sees:

- compacted older summary
- real recent turns raw

### 2.4 Old tool outputs are pruned, not the whole session structure

`opencode` has a second-stage pruning pass for old tool outputs:

- protected recent tool outputs are preserved first
- older completed tool outputs get marked compacted
- replay then uses a placeholder instead of full output

Relevant code:

- pruning logic: `packages/opencode/src/session/compaction.ts:295-340`
- replay placeholder handling: `packages/opencode/src/session/message-v2.ts:868-901`

This is important:

- the transcript structure remains stable
- only bulky content is cleared
- the model still sees that the tool happened

### 2.5 Why `opencode` rereads less

If turn 1 explored files and turn 2 says “do it”, the recent raw transcript is often still present:

- the model sees the actual earlier read/edit/tool sequence
- it usually does not need to rediscover the same files immediately

---

## 3. How `pi` handles context

### 3.1 `pi` uses a persistent JSONL session tree

`pi` stores a durable session file with explicit entries:

- messages
- model changes
- thinking level changes
- compactions
- branch summaries
- custom entries

Relevant code:

- `packages/coding-agent/src/core/session-manager.ts`

This is not just a chat log. It is a structured continuation graph.

### 3.2 `buildSessionContext()` reconstructs the actual LLM context

This is the core function:

- `packages/coding-agent/src/core/session-manager.ts:315-421`

Behavior:

- walk from current leaf to root
- extract effective model + thinking level
- if a compaction exists on the path:
  - emit compaction summary first
  - then replay raw kept messages from `firstKeptEntryId`
  - then replay later messages
- otherwise replay full path messages

That is a true session reconstruction model.

### 3.3 Compaction is iterative and file-aware

Defaults:

- `reserveTokens = 16384`
- `keepRecentTokens = 20000`

Relevant code:

- `packages/coding-agent/src/core/compaction/compaction.ts:115-125`

Trigger:

- compact when `contextTokens > contextWindow - reserveTokens`

Relevant code:

- `packages/coding-agent/src/core/compaction/compaction.ts:217-221`

It computes a cut point by walking backward from newest messages and keeping recent raw context.

Relevant code:

- `packages/coding-agent/src/core/compaction/compaction.ts:386-447`

If a single turn is too large, it supports **split-turn compaction**, meaning it can summarize the early part of one huge turn while keeping the later suffix raw.

Relevant code:

- split-turn preparation: `packages/coding-agent/src/core/compaction/compaction.ts:651-688`
- split-turn summary merge: `packages/coding-agent/src/core/compaction/compaction.ts:695-803`

### 3.4 `pi` explicitly tracks file operations across compactions

This is one of the strongest differences from `reasoner`.

`pi` extracts cumulative file operations from:

- tool calls in messages being summarized
- previous compaction details

Relevant code:

- `packages/coding-agent/src/core/compaction/compaction.ts:25-58`
- `packages/coding-agent/src/core/compaction/compaction.ts:669-687`

The compaction result stores:

- `readFiles`
- `modifiedFiles`

Relevant code:

- `packages/coding-agent/src/core/compaction/compaction.ts:791-796`

So even after compaction, the summary carries explicit file memory instead of just generic prose.

### 3.5 Session context is restored directly into live agent state

When restoring or after compaction:

- rebuild session context
- assign rebuilt messages back to live agent state

Relevant code:

- startup restore: `packages/coding-agent/src/core/sdk.ts:208-251`
- after auto-compaction: `packages/coding-agent/src/core/agent-session.ts:1951-1954`

This is exactly the kind of session continuity `reasoner` currently lacks.

### 3.6 Why `pi` rereads less

Because:

- it preserves the real session path
- it keeps recent raw context
- it uses iterative structured summaries for older history
- it explicitly carries forward cumulative read/modified file lists

That is much closer to how a human coding assistant would resume work.

---

## 4. Direct comparison

| Dimension | `reasoner` | `opencode` | `pi` |
|---|---|---|---|
| Primary continuity unit | per-turn run | persistent session | persistent session tree |
| Cross-turn source | `turn_summary` + small coding scratchpad | retained session transcript | rebuilt session path |
| Raw prior tool transcript across turns | mostly no | yes | yes |
| Recent raw tail after compaction | no strong retained tail; compacts to system summary + tail user | yes | yes |
| Old history compaction style | replace big chunks with one system summary | anchored session summary | compaction checkpoint entry |
| File-aware memory | capped scratchpad, 8 files max | relevant-files summary + recent raw history | explicit cumulative `readFiles` / `modifiedFiles` |
| Split-turn compaction | no | partial tail-preservation logic | yes |
| Tool result replay safety | canonicalized replay from parsed calls | structured replay from persisted parts | session rebuild from stored messages |
| Risk of broad rereads on follow-up turns | high | lower | lowest of the three |

---

## 5. Why `reasoner` still rereads files

This is the main causal chain.

### 5.1 We do not restore a real coding session transcript

A follow-up coding turn in `reasoner` starts from:

- summary-based prior runs
- current query
- a small working-memory/coding-session block

Not from:

- prior `read_file` output
- prior `grep` output
- recent assistant/tool exchange
- recent raw turns

### 5.2 Our persisted coding state is intentionally too small for strong continuation

Current limits are tight:

- only 8 inspected files
- only 8 changed files
- only one short excerpt per file
- excerpts are tiny

For multi-file frontend work, this is usually not enough.

### 5.3 Our compaction model is closer to chat summarization than coding-session continuation

Inside a run, once compaction triggers, `reasoner` can collapse context down to:

- base system
- one compaction summary
- maybe latest user tail

That drops the recent raw coding trail much more aggressively than `opencode` or `pi`.

### 5.4 Resulting user-visible behavior

For a workflow like:

1. inspect UI and suggest improvements
2. yes do it

`reasoner` turn 2 often has the idea of what to do, but not enough concrete code context to safely edit.

So it rereads.

That is not model stupidity.
It is a consequence of the continuation architecture.

---

## 6. Practical implications for `reasoner`

If the goal is to behave more like `opencode` or `pi`, the major missing pieces are:

1. A real persisted coding session/thread, not just per-run summaries
2. Retained raw recent coding history across turns
3. Compaction that preserves a recent raw tail
4. Stronger file-aware structured continuity:
   - multiple file spans
   - cumulative read/modified file tracking
   - explicit step/progress/decision state
5. Session-native prompt reconstruction instead of run-summary reconstruction

The recent `coding_sessions` work is a step in that direction, but it is still a thin overlay on a run-summary architecture.

---

## 7. Files inspected during this research

### `reasoner`

- `orchestrator/context/history_builder.py`
- `orchestrator/context/turn_summary.py`
- `orchestrator/agent/agent_engine.py`
- `orchestrator/agent/coding_session.py`
- `orchestrator/agent/context_pruner.py`
- `orchestrator/agent/profile.py`

### `opencode`

- `packages/opencode/src/session/prompt.ts`
- `packages/opencode/src/session/message-v2.ts`
- `packages/opencode/src/session/compaction.ts`
- `packages/opencode/src/session/processor.ts`
- `packages/opencode/src/session/llm.ts`
- `packages/opencode/src/session/session.ts`
- `packages/opencode/src/session/instruction.ts`

### `pi`

- `packages/coding-agent/src/core/session-manager.ts`
- `packages/coding-agent/src/core/compaction/compaction.ts`
- `packages/coding-agent/src/core/agent-session.ts`
- `packages/coding-agent/src/core/sdk.ts`
- `packages/coding-agent/docs/compaction.md`
- `packages/coding-agent/docs/session-format.md`

