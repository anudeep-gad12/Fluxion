# Development process supervisor (use with honcho or foreman)
# Start all services: honcho start

ui: pnpm --dir ui dev --port 3000
orchestrator: uv run uvicorn orchestrator.app:app --host 127.0.0.1 --port 9000 --reload
