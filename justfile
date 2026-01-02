# Justfile for development commands
# Install just: brew install just

# Default recipe: show available commands
default:
    @just --list

# Install all dependencies
install:
    uv sync
    cd ui && pnpm install

# Start development servers (UI + Orchestrator)
dev:
    honcho start

# Start only the orchestrator API
api:
    uv run uvicorn orchestrator.app:app --host 127.0.0.1 --port 9000 --reload

# Start only the UI
ui:
    cd ui && pnpm dev --port 3000

# Build UI for production
build:
    cd ui && pnpm build

# Run Python linting
lint:
    uv run ruff check orchestrator

# Run Python formatting
fmt:
    uv run ruff format orchestrator

# Run tests
test:
    uv run pytest

# Run test loop with log analysis (clears logs, runs tests, shows errors)
test-loop *ARGS:
    ./scripts/test_loop.sh {{ARGS}}

# Run sanity tests with log analysis
sanity:
    ./scripts/sanity_test.sh

# Run sanity tests with live log tailing
sanity-debug:
    ./scripts/sanity_test.sh --debug

# Clean generated files
clean:
    rm -rf var/
    rm -rf ui/dist/
    rm -rf .pytest_cache/
    find . -type d -name __pycache__ -exec rm -rf {} +

# Initialize var directory
init:
    mkdir -p var/artifacts/model/{router,planner,worker_general,worker_code,critic}
    mkdir -p var/artifacts/tool/{python/in,python/out,tests/in,tests/out}
    mkdir -p var/artifacts/draft
    mkdir -p var/tmp
    mkdir -p var/scratch
