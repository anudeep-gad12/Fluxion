# System Prompt Research — Coding Agent Landscape

How commercial and OSS coding agents structure system prompts, handle agent loops, and prevent failure modes.

Compiled: 2026-02-25

---

## Architecture Summary

| Agent | Prompt Style | Loop Control | Stopping Mechanism | Max Steps |
|-------|-------------|-------------|-------------------|-----------|
| Claude Code | Modular, 110+ fragments assembled at runtime | `while(tool_use)` | Model emits text without tool calls | None (model decides) |
| Codex CLI | Static `.md` file + AGENTS.md chain | Event stream processing | Model emits "done" event | None |
| Cursor | Static XML-tagged sections | Tool call loop | No tool calls = done; 3 linter retry cap | Per-tool caps |
| OpenCode | Provider-specific `.txt` files | `stopWhen` callback | `steps >= 1000` hard cap + forced summary | 1000 |
| Aider | Class-based inheritance per edit format | Conversation-based | File gating (ask user to add files) | None |
| Kilocode | Mode-based dynamic assembly | Mode routing | Tool filtering by mode | None |
| OpenClaw | 13 fixed sections, under 1000 tokens core | Tool execution | Silent reply codes | None |
| Continue.dev | Composable fragments per mode | Permission gate | No tool calls = done | None |

---

## Key Patterns

### 1. Identity First, Constraints Second
Every agent starts with a clear "You are..." statement. Rules follow.

### 2. No Mid-Work Nudging
Nobody injects "stop and synthesize now" messages mid-execution. Hard caps exist as safety nets only.

### 3. Loop Prevention is Architectural
- Tool output truncation (OpenCode: 2000 lines / 50KB)
- Result count caps (Cursor: grep 50 results, file_search 10)
- Edit tool rate limits (Cursor: once per turn)
- Retry caps (Cursor: 3 linter attempts)
- Permission rejection = hard stop (OpenCode)
- Model escalation on failure (Cursor: `reapply` with stronger model)
- Mode-based tool filtering (everyone)

### 4. Thinking Guidelines Approaches
- **Claude Code**: "Choose an approach and commit. Avoid revisiting unless new info contradicts."
- **Cursor**: XML sections — "Address root causes", "NEVER lie", "Bias toward self-sufficiency"
- **Aider**: "If ambiguous, ask questions." Model-specific anti-laziness / anti-overeagerness.
- **OpenClaw**: Separate philosophy (SOUL.md) from rules (AGENTS.md). Minimalism.

### 5. Anti-Pattern Guardrails
- Anti-laziness prompts for models that produce incomplete code (Aider)
- Anti-overeagerness prompts for models that over-modify (Aider)
- "Before calling each tool, first explain" (Cursor) — forces reasoning
- "Avoid narrating routine operations" (OpenClaw)
- "Three similar lines of code is better than a premature abstraction" (Claude Code)

### 6. Forced Summarization at Max Steps (OpenCode)
When max steps hit, inject a message forcing the agent to summarize:
- What has been accomplished
- What remains incomplete
- Recommendations for next steps

### 7. Context Management
- Dynamic `<system-reminder>` injection to re-ground drifting agents (Claude Code)
- Compaction at 90% context capacity (OpenCode)
- Encrypted compaction items preserving latent understanding (Codex)
- Conversation summarization preserving function names/filenames (Aider)

---

## Sources

### Claude Code
- [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) — extracted prompts per release
- [Pierce Freeman: Under the Hood](https://pierce.dev/notes/under-the-hood-of-claude-code)
- [Rastrigin Systems: System Prompt Analysis](https://rastrigin.systems/blog/claude-code-part-2-system-prompt/)
- [Mikhail Shilkov: v1 to v2 Evolution](https://mikhail.io/2025/09/sonnet-4-5-system-prompt-changes/)

### Codex CLI
- [openai/codex](https://github.com/openai/codex) — open source, prompts in `codex-rs/core/`
- [OpenAI: Unrolling the Codex Agent Loop](https://openai.com/index/unrolling-the-codex-agent-loop/)
- [Simon Willison: Reverse Engineering](https://simonwillison.net/2025/Nov/9/gpt-5-codex-mini/)

### Cursor
- [Leaked System Prompt (March 2025)](https://gist.github.com/sshh12/25ad2e40529b269a88b80e7cf1c38084)
- [How Cursor Works](https://blog.sshh.io/p/how-cursor-ai-ide-works)
- [Agent Best Practices](https://cursor.com/blog/agent-best-practices)

### OpenCode
- [anomalyco/opencode](https://github.com/anomalyco/opencode)
- [Deep Dive](https://cefboud.com/posts/coding-agents-internals-opencode-deepdive/)

### OpenClaw
- [openclaw/openclaw](https://github.com/openclaw/openclaw)
- [Pi Architecture](https://medium.com/@shivam.agarwal.in/agentic-ai-pi-anatomy-of-a-minimal-coding-agent-powering-openclaw-5ecd4dd6b440)

### Aider
- [Aider-AI/aider](https://github.com/Aider-AI/aider) — prompts in `aider/coders/`

### Continue.dev
- [continuedev/continue](https://github.com/continuedev/continue) — `core/llm/defaultSystemMessages.ts`
