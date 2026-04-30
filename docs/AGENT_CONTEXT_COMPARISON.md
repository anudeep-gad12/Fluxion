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

`reasoner` is now **hybrid**:

- each browser agent turn is still a separate run
- generic cross-turn history is still rebuilt from `turn_summary`
- but coding-profile continuation now persists a real replayable coding transcript via `coding_session_entries`
- coding prompts are rebuilt from `system prompt + neutral metadata + transcript replay`

So `reasoner` is no longer just “summarize a run”.
It now has a session-like continuation path specifically for coding work, while still keeping the broader run-based architecture.

In one line:

- `opencode` and `pi` compact a native session
- `reasoner` now reconstructs a coding session from persisted transcript + metadata state

That narrows the gap substantially for multi-turn coding work, even though the overall app architecture is still run-oriented.

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

### 1.2 New coding turns start from summary scaffold + coding-session replay

Initial coding prompt assembly now does this:

- build system prompt
- load persisted `CodingSessionState`
- load replayable `coding_session_entries` in persisted `seq` order
- inject at most a tiny neutral metadata block
- replay canonical assistant/tool transcript messages
- append the current user query

Relevant code:

- `orchestrator/agent/agent_engine.py`
- `orchestrator/agent/coding_context_builder.py`

### 1.3 Coding continuity is now transcript-first replay

`reasoner` now persists two layers:

1. `CodingSessionState`
   - objective
   - read files / modified files
   - recent commands
   - file evidence with multiple spans and freshness hashes

   This layer is metadata-only bookkeeping, not prompt-authoritative narrative memory.

2. `coding_session_entries`
   - user messages
   - assistant messages
   - canonical assistant tool calls
   - tool results
   - replay eligibility flags on structurally bad assistant turns
   - compaction markers via `compacted_at`

This is a real replayable coding transcript, not just a scratchpad.

### 1.4 Restore behavior on later coding turns

On a follow-up coding turn, `reasoner` now restores:

- durable coding-session metadata
- fresh file evidence where hashes still match
- stale-file reread hints where stored evidence is outdated
- replayable assistant/tool history from uncompacted `coding_session_entries`
- no checkpoint/prior-outcome narrative injection from `state_json`

That is materially closer to session-native continuation than the earlier summary-only model.

### 1.5 Coding-session compaction now preserves active replay boundaries

For coding runs, `reasoner` now compacts persisted coding history by:

- marking older `coding_session_entries` as compacted
- excluding compacted entries from future prompt rebuilds
- preserving canonical assistant/tool structure in the retained replay set

This is separate from the generic visible prompt compaction used elsewhere in the app.

### 1.6 Generic in-run prompt compaction is still aggressive

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

So the generic prompt layer is still more aggressive than the other two systems, but coding follow-ups now have an additional persisted replay layer that softens that loss across turns.

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
| Cross-turn source | `turn_summary` + coding transcript replay | retained session transcript | rebuilt session path |
| Raw prior tool transcript across turns | yes for coding flows via `coding_session_entries`; otherwise mostly no | yes | yes |
| Recent raw tail after compaction | yes for coding flows; weaker in generic prompt compaction | yes | yes |
| Old history compaction style | generic prompt summary for non-coding; compacted coding transcript entries excluded from replay | anchored session summary | compaction checkpoint entry |
| File-aware memory | capped scratchpad, 8 files max | relevant-files summary + recent raw history | explicit cumulative `readFiles` / `modifiedFiles` |
| Split-turn compaction | no | partial tail-preservation logic | yes |
| Tool result replay safety | canonicalized replay from parsed calls | structured replay from persisted parts | session rebuild from stored messages |
| Risk of broad rereads on follow-up turns | high | lower | lowest of the three |

---

## 5. Why `reasoner` can still reread files

This is the main causal chain.

### 5.1 The overall architecture is still run-oriented

Coding continuity is now much stronger, but the app still does not keep one single native long-lived model session the way `opencode` and `pi` do.

It reconstructs the coding session from persisted state and replay entries.

That is much better than before, but still not identical to a truly continuous provider-side thread.

### 5.2 Replay is still bounded

`reasoner` intentionally bounds replayable coding history and excludes compacted entries from active replay.

That means some older raw detail still drops out of the active transcript instead of remaining fully replayable forever.

### 5.3 Freshness checks correctly force some rereads

If file hashes changed, or stored spans do not cover the newly requested lines, rereads are now expected behavior, not wasted behavior.

That is the right tradeoff for correctness.

### 5.4 Generic prompt compaction is still more aggressive than session-native systems

The non-coding/global prompt layer can still compact more aggressively than `opencode` or `pi`, especially during long heavy runs.

### 5.4 Resulting user-visible behavior

For a workflow like:

1. inspect UI and suggest improvements
2. yes do it

`reasoner` turn 2 often has the idea of what to do, but not enough concrete code context to safely edit.

So it rereads.

So rereads are now less often caused by missing continuity, and more often caused by bounded replay, real file drift, or generic prompt-budget pressure.

---

## 6. Practical implications for `reasoner`

If the goal is to behave even more like `opencode` or `pi`, the remaining gaps are:

1. A truly native long-lived coding session/thread instead of reconstructed continuity
2. Even richer retained raw history under very large coding sessions
3. Less aggressive generic prompt compaction under pressure
4. Potentially stronger tool-result preservation beyond the current bounded replay model

The recent `coding_sessions` + `coding_session_entries` work closes a large part of the original gap.

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
