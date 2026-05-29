# Fluxion

AI chat application with thinking system and agent mode.
FastAPI backend (`orchestrator/`) + React/Vite frontend (`ui/`).
SQLite storage, OpenAI-compatible providers (DeepInfra cloud default, supports local llama-cpp).

## Session Start

```bash
git status && git log --oneline -3     # Current state
cat docs/IMPLEMENTATION_LOG.md | head -40  # What's been done
./dev.sh traces                        # Recent runs
```

Key references:

- `docs/IMPLEMENTATION_LOG.md` - Feature tracking (read first, **update after every feature/bug fix**)
- `docs/WORKFLOW.md` - Development process guide

## Commands

```bash
# Development (use just if installed, otherwise alternatives below)
just dev              # Start all (API:9000 + UI:3000)
./dev.sh start        # Alternative: start all services

# macOS desktop (Tauri)
./dev.sh desktop                          # API + built UI on :9000, then:
cd src-tauri && SPARKLE_FRAMEWORK_PATH=$PWD/Frameworks cargo tauri dev
./scripts/build_macos_tauri.sh            # Release .app (unsigned locally)

# Testing
uv run pytest         # Run tests
./scripts/sanity_test.sh --debug  # Integration tests with live logs

# Quality (requires: uv pip install ruff)
uv run ruff check orchestrator && uv run ruff format orchestrator
```

## Development

- **Config**: `orchestrator/chat_config.yaml` (single source of truth)
- **Env vars**: `${VAR:-default}` syntax supported in config
- **Python deps**: `uv sync`
- **UI deps**: `cd ui && pnpm install`
- **Prerequisite**: Start llama-cpp server on port 8080 before running (if using local)

## Testing

- Tests in `tests/` mirror `orchestrator/` structure
- Use `@pytest.mark.asyncio` for async tests
- **Unit tests**: Mock with `unittest.mock.AsyncMock`, `MagicMock`, `patch`
- **Integration tests** (`tests/integration/`): Real HTTP + DB, mocks LLM provider (fast, no API costs)
- **E2E sanity test** (`./scripts/sanity_test.sh --debug`): Full flow with actual LLM, validates traces/steps/tools
- Watch mode: `./scripts/test_loop.sh` (reruns on changes with log analysis)

## Debugging

```bash
./dev.sh debug        # Show recent errors
./dev.sh applogs      # Tail JSON logs
./dev.sh traces       # View SQLite traces
```

- Logs: `logs/app.log` (JSON, rotated)
- Find errors: `grep '"level":"ERROR"' logs/app.log | jq .`
- Find slow ops: `grep -E '"duration_ms":[0-9]{4,}' logs/app.log | jq .`

## Code Style

- Python: 4-space indent, full type hints, Google docstrings
- Naming: `PascalCase` (classes), `snake_case` (functions), `UPPER_SNAKE_CASE` (constants)
- Private methods: prefix with `_`

## Key Files


| Purpose      | Path                                      |
| ------------ | ----------------------------------------- |
| API entry    | `orchestrator/app.py`                     |
| UI entry     | `ui/src/App.tsx`                          |
| Chat engine  | `orchestrator/engine/chat_engine.py`      |
| Agent engine | `orchestrator/agent/agent_engine.py`      |
| Provider     | `orchestrator/providers/openai_compat.py` |
| Config       | `orchestrator/chat_config.yaml`           |


## Documentation

Source of truth for architecture (docs/ folder only):


| Document                     | Purpose                       |
| ---------------------------- | ----------------------------- |
| `docs/IMPLEMENTATION_LOG.md` | Feature tracking (read first) |
| `docs/WORKFLOW.md`           | Development process guide     |
| `docs/ARCHITECTURE.md`       | System architecture           |
| `docs/COMPONENTS.md`         | Component documentation       |
| `docs/DATA_MODELS.md`        | Data models                   |
| `docs/DATA_FLOW.md`          | Data flow diagrams            |
| `docs/API_REFERENCE.md`      | API documentation             |


