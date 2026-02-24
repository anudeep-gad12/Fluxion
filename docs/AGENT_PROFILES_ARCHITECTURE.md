# Agent Profiles Architecture — Unified Multi-Mode Agent Engine

> Research compiled Feb 2026. Sources: Claude Code, Cursor, Codex CLI, Replit Agent, Devin, LangGraph, Anthropic docs.

## Problem Statement

The Reasoner agent engine was built as a **web research agent**. Filesystem tools were bolted on for the CLI coding assistant. Every layer — system prompt, planner, citations, tool registry — assumes the primary job is web searching, not writing code.

**Goal**: ONE agentic loop, ONE trace/observability system, ONE tool execution pipeline — behavior adapts based on a **profile**.

---

## Core Insight from Industry

Every production system (Claude Code, Cursor, Codex CLI, Replit, Devin) uses **ONE loop, MANY profiles**. The agent loop itself is universal:

```
while not done:
    response = llm.call(messages, tools=profile.tools, system=profile.system_prompt)
    if response.has_tool_calls:
        results = execute_tools(response.tool_calls)
        messages.append(results)
    else:
        done = True
        return response
```

Behavioral differences come from what's injected INTO the loop:
- **System prompt** — persona, tool usage rules, response format
- **Tool set** — which tools are available
- **Context** — what gets injected into messages before the LLM call
- **Planning template** — how the agent plans its work
- **Result handling** — what artifacts are extracted from the run

---

## The Profile Concept

A profile bundles all mode-specific configuration:

```python
@dataclass
class AgentProfile:
    name: str                          # "research", "coding", "full"
    display_name: str                  # "Web Research", "Coding Assistant"

    # System prompt template (with {variable} placeholders)
    system_prompt_template: str

    # Which tool sets to load
    tool_sets: list[str]               # ["web", "filesystem", "python"]

    # Context strategy class
    context_strategy: Type[ContextStrategy]

    # Planning configuration
    planning_enabled: bool = True
    planning_prompt_template: str = ""
    plan_step_types: list[str] = field(default_factory=list)

    # Result handler (extracts mode-specific artifacts)
    result_handler: Type[ResultHandler] = DefaultResultHandler

    # Model overrides (optional)
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    max_steps: int = 10
```

### Three Profiles

| Profile | Tools | Context Injected | Planning Steps | Result Artifacts |
|---------|-------|-----------------|----------------|-----------------|
| `research` | web + python | date, search guidelines, citation rules | search, extract, calculate, synthesize | citations, sources |
| `coding` | filesystem + python + (web for docs) | git status, project tree, language detection, rules file | read, implement, test, debug, synthesize | files_modified, tests_run, diffs |
| `full` | ALL tools | both contexts merged | all step types available | both artifact types |

---

## Context Strategy (Per Profile)

Instead of if/else spaghetti, use a pluggable strategy:

```python
class ContextStrategy(Protocol):
    def get_context_vars(self) -> dict[str, str]: ...
    def get_context_messages(self) -> list[dict]: ...
    def prune_context(self, messages, max_tokens) -> list[dict]: ...
```

### Research Context Strategy
- Injects: current date, knowledge cutoff, search guidelines, citation format rules
- Pruning: keeps source URLs and key findings, drops verbose page extracts

### Coding Context Strategy
- Injects: project directory tree (top 2-3 levels), git status + recent commits, detected language/framework, `.reasoner/rules.md` or `CLAUDE.md` content, working directory path
- Pruning: keeps file paths, error messages, stack frames; drops large file contents

### Full Context Strategy
- Combines both: date context + project context
- Pruning: hybrid — keeps both sources and code references

---

## System Prompts (Per Profile)

### Research System Prompt (existing, clean up)
```
You are a research assistant that helps users find and analyze information.
Tools: web_search, web_extract, python_execute
Guidelines: use good sources, be efficient, cite properly
Response format: warm, engaging, no inline citation numbers
```

### Coding System Prompt (NEW)
```
You are a coding assistant that helps users understand, modify, and build software.

You work in the user's project directory. You have filesystem tools to read, search,
write, and edit code, plus a shell for running commands.

{project_context}

=== TOOL USAGE RULES ===
1. ALWAYS read a file before editing it — never make blind changes
2. Use grep/glob to find code before reading — don't guess file paths
3. After making changes, verify with bash (run tests, lint, build)
4. Prefer edit_file (precise replacement) over write_file (full overwrite)
5. For searching, prefer grep over bash grep
6. Use web_search ONLY for external docs/API references — not for local code questions

=== CODE GUIDELINES ===
- Match the existing code style (indentation, naming, patterns)
- Don't add features beyond what was asked
- Don't refactor surrounding code unless asked
- Keep changes minimal and focused
- If something breaks, fix it — don't leave broken code

=== RESPONSE FORMAT ===
Be concise. Show what you changed and why. If you ran commands, show the output.
```

### Full System Prompt
Combines both: research capabilities + filesystem access + coding guidelines.

---

## Tool Registry Composition

Replace boolean flags with declarative tool sets:

```python
TOOL_SETS = {
    "web": [WebSearchTool, WebExtractTool],
    "filesystem": [ReadFileTool, ListDirectoryTool, GlobTool, GrepTool,
                   WriteFileTool, EditFileTool, BashTool],
    "python": [PythonExecuteTool],  # Daytona or local
}

def create_tool_registry(profile: AgentProfile, config) -> ToolRegistry:
    registry = ToolRegistry()
    for tool_set_name in profile.tool_sets:
        for tool_class in TOOL_SETS[tool_set_name]:
            registry.register(tool_class(...))
    return registry
```

**Key decisions:**
- Web tools STAY available in coding mode (for looking up API docs, package info)
- System prompt guides tool PREFERENCE, not availability
- Filesystem tools available in research mode only when working_dir is set

---

## Planner Abstraction

One planner class, different templates per profile:

### Research Planning Template (existing)
```
Create a research plan for: {query}
Step types: search, extract, calculate, synthesize
Max steps: {max_steps}
```

### Coding Planning Template (NEW)
```
Create an implementation plan for: {query}
Step types: read_codebase, implement, test, debug, synthesize
Available tools: {tool_names}
Project context: {project_summary}
Max steps: {max_steps}
```

### Universal Plan Step Types
- `ANALYZE` — understand what needs to be done (maps to SEARCH for research, READ for coding)
- `EXECUTE` — perform an action (maps to EXTRACT/CALCULATE for research, IMPLEMENT/TEST for coding)
- `SYNTHESIZE` — produce final output (universal)

---

## Result/Output Abstraction

Unified result model with optional artifacts:

```python
@dataclass
class AgentResult:
    run_id: str
    success: bool
    final_answer: Optional[str] = None
    total_steps: int = 0
    error_message: Optional[str] = None
    timing_ms: int = 0
    total_tokens: int = 0

    # Mode-specific artifacts (replaces citations-only)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    # Research: {"citations": [...], "sources_consulted": [...]}
    # Coding:   {"files_modified": [...], "files_read": [...], "commands_run": [...]}
```

### Result Handlers
- **ResearchResultHandler**: Extracts citations from web_search/web_extract tool results
- **CodingResultHandler**: Tracks files read/modified/created, bash commands run, test results
- **FullResultHandler**: Combines both

---

## What Changes vs What Stays

### Stays the Same (NO fork needed)
- `AgentEngine.run()` main loop
- `AgentStateMachine` state transitions (INIT → RUNNING → PLANNING → TOOL_CALLING → SYNTHESIZING → COMPLETE)
- Trace/observability schema (trace_events, agent_steps, agent_tool_calls tables)
- SSE event streaming pipeline
- Tool execution pipeline (`_execute_tool_calls()`)
- Permission system (approval_callback, permission_policy)
- Context pruner (base class)
- Crash recovery / idempotency

### Gets Extracted into Profiles
- System prompts (currently hardcoded as `DEFAULT_SYSTEM_PROMPT`, `CALCULATION_SYSTEM_PROMPT`)
- Tool registry composition (currently `filesystem_enabled`, `calculation_only` booleans)
- Planning prompt + step types (currently research-only in `planner.py`)
- Context injection in `_build_messages()` (currently date-only)
- Findings extraction in `_extract_finding_from_result()` (currently hardcoded for web tools only)
- Result artifacts (currently `citations` field only)

### New Additions
- `orchestrator/agent/profile.py` — AgentProfile dataclass + built-in profiles + ContextStrategy
- Coding system prompt
- Coding planning template
- Project context injection (git status, directory tree, language detection, rules file loading)
- File change tracking (CodingResultHandler)
- `.reasoner/rules.md` support (auto-loaded like CLAUDE.md)

---

## Files That Change

| File | Change Type | Description |
|------|------------|-------------|
| `orchestrator/agent/profile.py` | **NEW** | AgentProfile dataclass, built-in profiles, ContextStrategy protocol |
| `orchestrator/agent/agent_engine.py` | **MODIFY** | Accept profile param, remove hardcoded prompts, use profile.context_strategy |
| `orchestrator/agent/planner.py` | **MODIFY** | Accept planning_prompt from profile, generalize step types to strings |
| `orchestrator/agent/tools/registry.py` | **MODIFY** | Replace boolean flags with `tool_sets: list[str]` from profile |
| `orchestrator/agent/factory.py` | **MODIFY** | Accept profile name, resolve profile, pass to engine |
| `orchestrator/chat_config.yaml` | **MODIFY** | Add `agent_profiles:` section with named profiles |
| `orchestrator/schemas.py` | **MODIFY** | Add `profile` field to CreateAgentRunRequest |
| `cli/__main__.py` | **MODIFY** | Add `--profile` CLI option |
| `cli/config.py` | **MODIFY** | Add `profile` to CLIConfig |

---

## Current Engine Extension Points (from code audit)

### Already Parameterizable (keep these)
| Parameter | Location | Purpose |
|-----------|----------|---------|
| `system_prompt` | agent_engine.py:255 | Behavior instruction |
| `max_steps` | agent_engine.py:252 | Execution depth |
| `planning_enabled` | agent_engine.py:260 | Research plan generation |
| `max_plan_steps` | agent_engine.py:261 | Plan complexity ceiling |
| `tool_choice` | agent_engine.py:257 | Force specific tool on first step |
| `approval_callback` | agent_engine.py:262 | Permission gating |
| `permission_policy` | agent_engine.py:263 | strict/relaxed/yolo |

### Hardcoded That Should Be Profile-Driven
| What | Location | Current | Should Be |
|------|----------|---------|-----------|
| System prompts | agent_engine.py:161-240 | Two class constants | `profile.system_prompt_template` |
| Planning prompt | planner.py:169-205 | Single template | `profile.planning_prompt_template` |
| Plan step types | planner.py:36-42 | Fixed enum (SEARCH, EXTRACT, etc.) | `profile.plan_step_types` (strings) |
| Date context | agent_engine.py:1100-1104 | Hardcoded format | `profile.context_strategy.get_context_vars()` |
| Findings extraction | agent_engine.py:1895-1932 | Only web tools | `profile.should_extract_finding(tool_name)` |
| Max history | agent_engine.py:1120 | `max_history = 10` | `profile.max_conversation_history` |
| Tool result truncation | agent_engine.py:243 | 50000 chars | `profile.max_tool_result_chars` |
| "ONLY three tools" | agent_engine.py:165 | Hardcoded claim | Removed (profile controls) |

### Missing Entirely (needs new code)
- Project context injection (git status, dir tree, language detect, rules files)
- Coding system prompt
- Coding planning template
- File change tracking (CodingResultHandler)
- `.reasoner/rules.md` auto-loading
- `--profile` CLI option

---

## Implementation Order

### Phase 1: Profile Abstraction (foundation)
1. Create `profile.py` with AgentProfile dataclass and 3 built-in profiles
2. Update factory.py to accept profile name, resolve, and pass through
3. Update schemas.py — add `profile` field to CreateAgentRunRequest
4. Update registry.py — replace boolean flags with tool_sets

### Phase 2: Coding System Prompt + Context
5. Write CODING_SYSTEM_PROMPT with tool priority rules, code guidelines
6. Implement CodingContextStrategy (git status, project tree, language detection)
7. Add rules file loading (`.reasoner/rules.md`)
8. Update `_build_messages()` to use profile.context_strategy

### Phase 3: Planner + Results
9. Generalize PlanStepType to strings from profile
10. Add coding planning template
11. Change AgentResult.citations → AgentResult.artifacts
12. Implement CodingResultHandler (track file changes)

### Phase 4: CLI Integration
13. Add `--profile` to CLI entry point
14. Update CLIConfig with profile field
15. Pass profile through API client to backend

---

## References

- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic — Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [How Cursor Shipped its Coding Agent (ByteByteGo)](https://blog.bytebytego.com/p/how-cursor-shipped-its-coding-agent)
- [Cursor 2.0 Agent-First Architecture](https://www.digitalapplied.com/blog/cursor-2-0-agent-first-architecture-guide)
- [OpenAI Codex — AGENTS.md](https://developers.openai.com/codex/guides/agents-md/)
- [Replit Agent — LangChain Case Study](https://www.langchain.com/breakoutagents/replit)
- [Replit — Plan Mode](https://blog.replit.com/introducing-plan-mode-a-safer-way-to-vibe-code)
- [Devin 2.0 Technical Design](https://medium.com/@takafumi.endo/agent-native-development-a-deep-dive-into-devin-2-0s-technical-design-3451587d23c0)
- [VS Code — Unified Agent Experience](https://code.visualstudio.com/blogs/2025/11/03/unified-agent-experience)
- [GitHub Copilot Coding Agent](https://github.blog/news-insights/product-news/github-copilot-meet-the-new-coding-agent/)
- [LangGraph Agent Orchestration](https://www.langchain.com/langgraph)
- [LangChain Plan-and-Execute Agents](https://blog.langchain.com/planning-agents/)
- [ToolRegistry: Protocol-Agnostic Tool Management](https://arxiv.org/html/2507.10593v1)
- [OpenTelemetry AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [Context Engineering for Coding Agents — Martin Fowler](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html)
- [Claude Agent Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)
- [Anthropic 2026 Agentic Coding Trends Report](https://resources.anthropic.com/hubfs/2026%20Agentic%20Coding%20Trends%20Report.pdf)
