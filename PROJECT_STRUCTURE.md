# Project Structure

Current high-level structure for Fluxion.

## Root Directory

```text
fluxion/
├── AGENTS.md                 # Agent/project instructions
├── README.md                 # User-facing overview and install/dev notes
├── PROJECT_STRUCTURE.md      # This file
├── dev.sh                    # Local service/dev helper
├── justfile                  # Common development recipes
├── pyproject.toml / uv.lock  # Python package metadata and lockfile
├── src-tauri/                # macOS Tauri desktop shell
├── ui/                       # React/Vite frontend
├── orchestrator/             # FastAPI backend and agent runtime
├── tests/                    # Python tests mirroring backend modules
├── scripts/                  # Build, install, GAIA, sanity, and test-loop scripts
├── docs/                     # Architecture/API/workflow/reference docs
├── assets/                   # Brand assets
├── site/                     # Landing/site assets
├── logs/                     # Runtime logs, ignored by git
└── var/                      # Runtime SQLite DB, run artifacts, scratch state
```

## Documentation (`docs/`)

```text
docs/
├── API_REFERENCE.md
├── ARCHITECTURE.md
├── BENCHMARKS.md             # Historical benchmark archive
├── CHATGPT_OAUTH_INTEGRATION.md # Historical OAuth research/current notes
├── COMPONENTS.md
├── DATA_FLOW.md
├── DATA_MODELS.md
├── IMPLEMENTATION_LOG.md
└── WORKFLOW.md
```

## Backend (`orchestrator/`)

```text
orchestrator/
├── app.py                    # FastAPI app, middleware, router wiring, lifespan
├── chat_config.yaml          # Runtime config source of truth
├── config.py                 # Pydantic config loading/env resolution
├── schemas.py                # API request/response models
├── runtime_paths.py          # Desktop/package-aware runtime paths
├── reasoning_controls.py     # Runtime reasoning-setting merge logic
├── vision.py                 # Image attachment validation/formatting
├── agent/                    # Coding agent loop, Plan Mode, session replay, tools
│   └── tools/                # apply_patch, exec_command, read/edit/write, grep/glob, web, python, image, artifacts
├── context/                  # Context profiles, budgets, history building, turn summaries
├── engine/                   # ChatEngine for non-agent chat runs
├── middleware/               # Session/rate-limit middleware
├── models/                   # Provider/model registry and metadata
├── providers/                # OpenAI-compatible, ChatGPT, failover, parsers/builders
├── routes/                   # conversations, runs, agent, auth, Grok auth, models, terminal, workspaces, benchmarks
├── services/                 # browser terminal, local models, provider keys, model catalog, reasoning settings, rewind, Grok auth
├── storage/                  # SQLite schema, migrations, repositories
├── thinking/                 # Direct thinking/reasoning stream parsing
└── utils/                    # token counting, sanitization, Harmony parsing
```

## Frontend (`ui/`)

```text
ui/
├── package.json / pnpm-lock.yaml
├── vite.config.ts
├── dist/                     # Built desktop/static bundle
└── src/
    ├── App.tsx               # App layout and routing
    ├── api/client.ts         # REST/SSE API client
    ├── assets/               # UI assets
    ├── components/           # Conversation, messages, tools, terminal, desktop shell UI
    │   ├── desktop/          # Tauri desktop panes/titlebar/composer/browser/terminal
    │   └── ui/               # Shared UI primitives
    ├── hooks/                # Zustand store and SSE hooks
    ├── lib/                  # platform/retry/live-state/usage utilities
    ├── styles/               # CSS modules/global styles
    └── types/                # Shared TypeScript types
```

## Desktop Shell (`src-tauri/`)

```text
src-tauri/
├── Cargo.toml / Cargo.lock
├── tauri.conf.json
├── src/main.rs / src/lib.rs  # Tauri commands, windows, Browser WebViews, backend process integration
├── build.rs
├── capabilities/             # Tauri permissions
├── entitlements.plist
├── Info.extend.plist
├── icons/
└── binaries/                 # Bundled backend binary placeholder/output
```

## Tests (`tests/`)

```text
tests/
├── agent/                    # Agent engine, tools, permissions, Plan Mode, artifacts
├── config/
├── context/
├── engine/
├── gaia/
├── integration/              # Mock-provider HTTP/DB integration flows
├── middleware/
├── models/
├── providers/
├── routes/
├── schemas/
├── services/
├── storage/
├── thinking/
├── tools/
└── utils/
```

## Scripts (`scripts/`)

```text
scripts/
├── build_macos_tauri.sh      # Local unsigned macOS .app build
├── build_macos_app.sh        # Legacy/local app build helper
├── ensure_sparkle_framework.sh
├── install_local_service.sh
├── sanity_test.sh            # Real-provider smoke test
├── test_loop.py / test_loop.sh
├── gaia/                     # GAIA loader/scorer/runner
└── tauri-before-build.sh / tauri-before-dev.sh
```

## Runtime Data

- `var/traces.sqlite` — main local SQLite DB for conversations, runs, traces, settings, tokens, terminal metadata, and artifacts.
- `.fluxion/runs/<run_id>/` — workspace-local run output artifacts created by agent tools.
- `.fluxion/plans/<run_id>.md` — durable Plan Mode proposal/progress files.
- `logs/app.log`, `logs/llama.log`, `logs/mlx.log` — JSON app logs and local-model startup logs.

Generated directories such as `.venv/`, `.uv-cache/`, `.pnpm-store/`, `ui/dist/`, `src-tauri/target/`, `__pycache__/`, and `node_modules/` are intentionally omitted from the structural inventory.
