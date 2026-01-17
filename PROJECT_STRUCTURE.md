# Project Structure

This document provides a complete overview of the folder and file structure for the Reasoner project.

## Root Directory

```
reasoner/
├── architecture-diagram.html
├── ARCHITECTURE.md
├── DEBUGGING.md
├── dev.sh
├── justfile
├── Procfile
├── pyproject.toml
├── README.md
├── uv.lock
├── docs/
├── logs/
├── orchestrator/
├── scripts/
├── tests/
├── ui/
└── var/
```

## Documentation (`docs/`)

```
docs/
├── AGENT_ARCHITECTURE_RESEARCH.md
├── AGENT_CONVO_FULL.md
├── AGENT_DESIGN.md
├── AGENT_IMPLEMENTATION_LOG.md
├── AGENT_MASTER_REFERENCE.md
├── AGENT_SYSTEM_DESIGN.md
└── SYSTEM_DESIGN.md
```

## Logs (`logs/`)

```
logs/
├── api.log
├── app.log
├── test_run.log
└── ui.log
```

## Orchestrator (`orchestrator/`)

```
orchestrator/
├── __init__.py
├── app.py
├── chat_config.yaml
├── config.py
├── logging_config.py
├── schemas.py
├── agent/
│   ├── __init__.py
│   ├── agent_engine.py
│   ├── context_pruner.py
│   ├── factory.py
│   ├── recovery.py
│   ├── state_machine.py
│   └── tools/
│       ├── __init__.py
│       ├── base.py
│       ├── python_sandbox.py
│       ├── registry.py
│       ├── web_extract.py
│       └── web_search.py
├── engine/
│   ├── __init__.py
│   └── chat_engine.py
├── monitoring/
│   └── (empty or __pycache__ only)
├── providers/
│   ├── __init__.py
│   ├── base.py
│   ├── chain.py
│   ├── circuit_breaker.py
│   ├── factory.py
│   ├── openai_compat.py
│   ├── request_builders.py
│   └── response_parsers.py
├── reporting/
│   ├── __init__.py
│   └── report_builder.py
├── routes/
│   ├── __init__.py
│   ├── agent_runs.py
│   ├── conversations.py
│   └── runs.py
├── storage/
│   ├── __init__.py
│   ├── db.py
│   ├── schema.sql
│   └── repositories/
│       ├── __init__.py
│       ├── agent_repo.py
│       ├── conversation_repo.py
│       └── trace_repo.py
├── thinking/
│   ├── __init__.py
│   ├── base.py
│   ├── orchestrator.py
│   └── strategies/
│       ├── __init__.py
│       └── direct.py
├── tools/
│   ├── builtin/
│   └── providers/
└── utils/
    ├── __init__.py
    └── tokens.py
```

## Tests (`tests/`)

```
tests/
├── __init__.py
├── conftest.py
├── agent/
│   ├── __init__.py
│   ├── test_agent_engine.py
│   ├── test_agent_integration.py
│   ├── test_context_pruner.py
│   ├── test_recovery.py
│   ├── test_state_machine.py
│   └── tools/
│       ├── __init__.py
│       ├── test_base.py
│       ├── test_python_sandbox.py
│       ├── test_registry.py
│       ├── test_web_extract.py
│       └── test_web_search.py
├── config/
│   ├── __init__.py
│   └── test_config.py
├── engine/
│   ├── __init__.py
│   └── test_chat_engine.py
├── integration/
│   ├── __init__.py
│   ├── test_agent_e2e.py
│   ├── test_e2e_flow.py
│   └── test_full_flow.py
├── providers/
│   ├── __init__.py
│   ├── test_circuit_breaker.py
│   ├── test_openai_compat.py
│   ├── test_provider_chain.py
│   ├── test_request_builders.py
│   └── test_response_parsers.py
├── routes/
│   ├── __init__.py
│   └── test_agent_runs.py
├── schemas/
│   ├── __init__.py
│   └── test_schemas.py
├── storage/
│   ├── __init__.py
│   ├── test_agent_repo.py
│   ├── test_conversation_repo.py
│   ├── test_database.py
│   └── test_trace_repo.py
├── thinking/
│   ├── __init__.py
│   └── test_thinking_orchestrator.py
├── tools/
│   └── providers/
└── utils/
    ├── __init__.py
    └── test_tokens.py
```

## UI (`ui/`)

```
ui/
├── index.html
├── package.json
├── pnpm-lock.yaml
├── postcss.config.js
├── tailwind.config.js
├── tsconfig.json
├── tsconfig.tsbuildinfo
├── vite.config.ts
├── dist/
│   ├── index.html
│   └── assets/
│       └── (compiled assets: JS, CSS, fonts)
├── node_modules/
│   └── (dependencies)
└── src/
    ├── App.tsx
    ├── index.css
    ├── main.tsx
    ├── api/
    │   └── client.ts
    ├── components/
    │   ├── AgentRunMessage.tsx
    │   ├── AgentStepsPanel.tsx
    │   ├── AnswerMarkdown.tsx
    │   ├── AnswerWithCitations.tsx
    │   ├── CitationInline.tsx
    │   ├── ConversationList.tsx
    │   ├── ConversationView.tsx
    │   ├── DetailPanel.tsx
    │   ├── ThinkingPanel.tsx
    │   ├── ToolCallCard.tsx
    │   └── ui/
    │       ├── badge.tsx
    │       ├── button.tsx
    │       ├── card.tsx
    │       ├── dialog.tsx
    │       ├── input.tsx
    │       ├── scroll-area.tsx
    │       ├── separator.tsx
    │       ├── skeleton.tsx
    │       └── textarea.tsx
    ├── hooks/
    │   ├── useAgentSSE.ts
    │   ├── useSSE.ts
    │   └── useStore.ts
    ├── lib/
    │   ├── retry.ts
    │   └── utils.ts
    └── types/
        ├── agent.ts
        └── index.ts
```

## Scripts (`scripts/`)

```
scripts/
├── sanity_test.sh
├── test_loop.py
└── test_loop.sh
```

## Variable/Artifact Storage (`var/`)

```
var/
├── artifacts/
│   ├── discriminator/
│   │   └── (0001.json - 0009.json)
│   ├── draft/
│   │   ├── (0001.txt - 0015.txt, 0013.json)
│   │   ├── candidate_A/
│   │   │   └── (0001.txt - 0010.txt)
│   │   ├── candidate_B/
│   │   │   └── (0001.txt - 0010.txt)
│   │   └── candidate_C/
│   │       └── (0001.txt - 0010.txt)
│   ├── model/
│   │   ├── critic/
│   │   │   └── (0001.json - 0060.json)
│   │   ├── discriminator/
│   │   │   └── (0001.json - 0009.json)
│   │   ├── planner/
│   │   │   └── (0001.json - 0057.json)
│   │   ├── planner_fork/
│   │   │   └── (0001.json - 0010.json)
│   │   ├── router/
│   │   │   └── (0001.json - 0065.json)
│   │   ├── verifier/
│   │   │   └── (17 JSON files)
│   │   ├── worker_code/
│   │   └── worker_general/
│   │       └── (21 JSON files)
│   ├── tool/
│   │   ├── python/
│   │   │   ├── in/
│   │   │   │   └── (46 JSON files)
│   │   │   └── out/
│   │   │       └── (46 JSON files)
│   │   └── tests/
│   │       ├── in/
│   │       └── out/
│   └── verifier/
│       ├── candidate_A/
│       │   └── (8 JSON files)
│       ├── candidate_B/
│       │   └── (6 JSON files)
│       └── candidate_C/
│           └── (0001.json - 0003.json)
├── scratch/
├── tmp/
└── traces.sqlite
```

## Key Files Description

### Root Level
- `architecture-diagram.html` - Visual architecture diagram
- `ARCHITECTURE.md` - Architecture documentation
- `DEBUGGING.md` - Debugging guide
- `dev.sh` - Development script
- `justfile` - Just command runner configuration
- `Procfile` - Process configuration (likely for deployment)
- `pyproject.toml` - Python project configuration
- `README.md` - Project readme
- `uv.lock` - UV package manager lock file

### Core Application
- `orchestrator/app.py` - Main application entry point
- `orchestrator/config.py` - Configuration management
- `orchestrator/schemas.py` - Data schemas
- `orchestrator/chat_config.yaml` - Chat configuration

### Agent System
- `orchestrator/agent/agent_engine.py` - Core agent engine
- `orchestrator/agent/state_machine.py` - Agent state management
- `orchestrator/agent/recovery.py` - Recovery mechanisms
- `orchestrator/agent/context_pruner.py` - Context management
- `orchestrator/agent/tools/` - Agent tool implementations

### Storage
- `orchestrator/storage/db.py` - Database connection
- `orchestrator/storage/schema.sql` - Database schema
- `orchestrator/storage/repositories/` - Data access layer

### Frontend
- `ui/src/App.tsx` - Main React application
- `ui/src/components/` - React components
- `ui/src/hooks/` - React hooks
- `ui/src/api/client.ts` - API client

## Notes

- `__pycache__/` directories are Python bytecode cache (excluded from structure)
- `node_modules/` contains npm/pnpm dependencies (excluded from detailed structure)
- `dist/` contains compiled frontend assets (excluded from detailed structure)
- `var/artifacts/` contains runtime artifacts and model outputs
- Test files mirror the structure of the main application code

