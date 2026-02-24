# CLI Coding Assistant Landscape Research

**Date:** 2026-02-24
**Purpose:** Survey of every major CLI coding tool — unique features, patterns, and what to steal for Reasoner CLI.

---

## Tool-by-Tool Breakdown

### Claude Code (Anthropic)
- **CLAUDE.md hierarchy**: 6 layers of memory (managed, project, rules, user, local, auto), path-scoped rules with glob patterns, `@import` syntax
- **Hooks system**: 17 lifecycle events (PreToolUse, PostToolUse, SessionStart, etc.) with 3 hook types (command, prompt, agent). Deterministic control regardless of LLM decisions
- **Multi-agent orchestration**: Subagents in worktrees, background execution (Ctrl+B), agent teams via SendMessage, custom agents as markdown files
- **MCP (Model Context Protocol)**: Universal tool protocol, dynamic tool loading when >10% context consumed
- **Skills & plugins**: Packaged workflows, plugin marketplace via git repos, auto-invoked slash commands
- **Session teleportation**: `/teleport` pulls web sessions into terminal, `&` prefix sends tasks to cloud
- **Plan mode**: Read-only exploration before execution, separate planning from doing

### Codex CLI (OpenAI)
- **Two-layer security**: Sandbox (OS-level: Landlock + seccomp on Linux, Seatbelt on macOS) separate from approval policy. Network disabled by default
- **PLANS.md**: Living design docs enabling 7+ hour autonomous sessions. Agent updates plan at every stopping point
- **V4A diff format**: Structured patch format GPT models are specifically trained to produce
- **Context compaction**: Auto-summarizes as context fills (not just truncation)
- **Cloud sandboxes**: Each task in isolated preloaded container (setup phase with network, agent phase without)
- **`/review` command**: Dedicated code review mode that reads diffs without modifying working tree

### Aider
- **Repo map (PageRank)**: Tree-sitter parses every file -> NetworkX graph -> PageRank ranks importance -> binary search to fit token budget. Dynamic sizing based on chat state
- **Architect + Editor split**: One model reasons, another translates to edits. Hit 85% on code editing benchmark
- **Git-as-safety-net**: Every change auto-committed with conventional commit messages. Undo = `git revert`
- **Auto-lint/auto-test loop**: Runs linters + tests after every AI edit, feeds failures back for automatic correction
- **Voice coding**: `/voice` command, 3.75x faster than typing
- **Watch mode**: Monitors files for `// AI!` comments placed from any editor, executes in batch

### Kilo Code
- **Orchestrator mode**: Meta-agent dispatches subtasks to specialist modes (Architect, Code, Debug, Ask), each with constrained tool/file access
- **JSON-IO mode**: Bidirectional JSON over stdin/stdout for external orchestration
- **AI Safety Gatekeeper**: Secondary AI reviews every action in YOLO mode, blocks dangerous ones
- **500+ models, 60+ providers**: Widest model support, zero markup pricing

### Cline
- **ACP (Agent Client Protocol)**: LSP-like standard for agent-editor communication. One protocol, every editor
- **Browser automation**: Launches headless Chromium, clicks/types/scrolls, captures screenshots + console logs
- **Self-extending via MCP**: Agent can define new tools for itself mid-session

### Gemini CLI (Google)
- **Shadow git checkpointing**: Purpose-built checkpoint system at `~/.gemini/history/<project_hash>`. Captures full file state + conversation + tool call. Undo restores everything and re-proposes the original action
- **1M token context window**: Can hold enormous codebases
- **60 req/min free tier**: Most generous free access

### OpenCode
- **LSP integration**: Auto-configures language servers, feeds diagnostics directly to LLM
- **Go + Bubble Tea**: Fast binary, no runtime deps, beautiful TUI
- **Session sharing**: Share conversation links with teammates

### Cursor
- **Cloud handoff**: `&` prefix pushes conversation to cloud, resume on any device (web, mobile)
- **ASCII diagram rendering**: Mermaid diagrams rendered inline in terminal

### Continue.dev
- **CI-first design**: Entire product built around async agents in pipelines (PR review, Sentry alert resolution, Snyk fixes)

### Amazon Kiro
- **Spec-driven development**: Converts prompts into EARS requirements -> technical design -> task list -> code
- **Days-long autonomous operation**: Persistent context across sessions

### Augment Code
- **Context Engine as MCP server**: Semantic codebase indexing that improves ANY agent's performance by 70%+
- **Memories**: Automatically learns from coding patterns

### Other Notable Tools
- **Goose (Block)**: MCP-first, Apache 2.0, Linux Foundation stewardship
- **Amp (Sourcegraph)**: "Deep mode" with extended reasoning, free ad-supported tier
- **Warp**: Full GPU-accelerated terminal replacement (Rust), runs multiple agents simultaneously
- **Crush (Charmbracelet)**: Broadest cross-platform (macOS, Linux, Windows, Android, BSD)
- **Droid (Factory)**: Specialized sub-agents (Code, Knowledge, Reliability, Product)

---

## Emerging Patterns

### Headless/CI Mode
Table stakes — every major tool now has `-p` or `--headless` flag for non-interactive CI use. Claude Code, Cline, Kilo, Codex, Copilot CLI all support this.

### Background Agents
- Cursor: `&` prefix pushes to cloud agent
- Kiro: Days-long autonomous operation
- VS Code: Dedicated worktrees per background session
- Continue.dev: Background agents in CI resolving Sentry alerts, Snyk vulns

### Computer Use / Browser Automation
- Cline: Headless Chromium with screenshots + console logs
- Vercel Agent Browser: Standalone CLI for AI browser automation
- Codex: Image/screenshot input for multimodal prompts

### Multi-Repo Support
Standard approach: **git worktrees**. Claude Code, Kilo, Windsurf all use them for parallel isolation.

### Team Collaboration
- **AGENTS.md standard**: 60K+ repos, Linux Foundation backed
- Custom slash commands (Claude Code), custom agents (Copilot CLI)
- Session sharing (OpenCode), forking (Kilo)

### Cost Tracking
- Kiro: Per-prompt credit system with real-time visibility
- ccusage: Open-source tool for Claude Code/Codex usage analysis
- General trend: developers demand exact per-prompt costs

### Checkpoint/Undo
- Gemini CLI: Shadow git repo (best in class)
- Aider: Git auto-commit (simplest)
- Codex: Patch-based workflows
- Claude Code: Worktree hooks (isolation, not true checkpointing)

---

## Patterns Worth Stealing (Ranked by Impact for Reasoner)

| # | Pattern | From | Why |
|---|---------|------|-----|
| 1 | Shadow git checkpointing | Gemini CLI | Only 1 tool has this. Full undo of file state + conversation |
| 2 | Repo map (tree-sitter + PageRank) | Aider | Structural awareness of entire codebase in ~1K tokens |
| 3 | Auto-lint/auto-test loop | Aider | Run checks after every AI edit, auto-feed failures back |
| 4 | Hooks system | Claude Code | Lifecycle hooks (pre/post tool) for formatting, validation |
| 5 | Orchestrator/specialist dispatch | Kilo Code | Meta-agent routes to constrained modes |
| 6 | Context compaction | Codex CLI | Summarize conversation intelligently when approaching limits |
| 7 | Cloud handoff | Cursor | Start locally, push to cloud when it'll take long |
| 8 | AGENTS.md support | Standard | 60K+ repos, instant interop with every other agent |
| 9 | LSP diagnostics as context | OpenCode | Language servers already know about errors/warnings/types |
| 10 | JSON-IO mode | Kilo Code | Bidirectional stdin/stdout JSON for external orchestration |
| 11 | Headless/CI mode | Everyone | `-p` flag for non-interactive use in GitHub Actions |
| 12 | Cost tracking | Kiro, ccusage | Per-prompt costs, session totals, daily burn rate |

---

## What Reasoner CLI Has vs Field

**Already have:** Agentic loop, 10 tools, SSE streaming, traces/observability, permission system, TUI, thinking display

**Critical gaps:**
- No repo map / structural codebase awareness (just file tree)
- No checkpoint/undo system
- No auto-lint/auto-test after edits
- No hooks (pre/post tool execution)
- No headless/CI mode
- No context compaction (will just truncate)
- No cost tracking
- No AGENTS.md support
- No specialist mode dispatch

---

## Implementation Priority for Reasoner

```
Phase 1 (Foundation):     Profile + ContextStrategy + coding prompt
Phase 2 (Safety):         Shadow git checkpoints + file change tracking
Phase 3 (Intelligence):   Auto-lint/test loop + repo map
Phase 4 (Polish):         Headless mode + cost tracking + hooks
```

Phase 1 is ~4 files changed, zero breaking changes to web.
