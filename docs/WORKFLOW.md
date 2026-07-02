# Development Workflow

> Trunk-based workflow for Fluxion, the macOS desktop app.
> One branch (`main`), effort scaled to the size of the change.

---

## The Rules

1. **`main` is the only long-lived branch.** Work directly on it.
2. **Branch only for risky or multi-day work** (engine rewrites, schema migrations). Merge back within days, delete the branch.
3. **Run the checks that match what you changed** — not a fixed checklist.
4. **Push after every commit.** GitHub `main` is the backup.
5. **One-line entry in `docs/IMPLEMENTATION_LOG.md` per commit.** Update other docs only when the feature actually changed what they describe.
6. **Releases are tags** (`v*`), not branches.

---

## Everyday Flow (fixes, small features)

```bash
# 1. Implement on main
# 2. Run the matching checks (see table below)
# 3. Commit + log + push
git add <files>                        # never `git add .` — pick files
git commit -m "Fix overlay screenshot attachment"
# add one line to docs/IMPLEMENTATION_LOG.md (fold into the commit)
git push origin main
```

## Risky / Multi-Day Flow

```bash
git checkout -b feature/<name>         # branch from main
# ... implement, commit as you go ...
uv run pytest                          # full gate before merging
git checkout main && git merge feature/<name>
git branch -d feature/<name>
git push origin main
```

---

## Checks by Change Type

Run what matches the files you touched. Nothing more.

| You changed | Run |
|-------------|-----|
| `orchestrator/` (Python) | `uv run pytest tests/<module>/ -v -x`, then `uv run pytest` before commit; `uv run ruff check orchestrator` |
| Agent/tool/provider behavior | the above, plus `./scripts/sanity_test.sh --debug` (real LLM smoke test) |
| `ui/` (React) | `cd ui && ./node_modules/.bin/tsc --noEmit && pnpm build` |
| `src-tauri/` (Rust) | `cd src-tauri && cargo check`, then a real build if it touches windows/permissions |
| `scripts/`, config | run the script / start the app once |
| `docs/` only | nothing |

**Verify behavior, not just compilation.** For agent changes, make a real
request and inspect it:

```bash
./dev.sh traces                        # recent runs
./dev.sh explore <run_id>              # step-by-step detail
./dev.sh debug                         # recent errors in logs
```

---

## Running the App

```bash
# Web dev loop (fastest iteration on UI + backend)
./dev.sh start                         # API :9000 + Vite UI :3000

# Desktop shell against local backend
./dev.sh desktop                       # API :9000 + built UI bundle
cd src-tauri && SPARKLE_FRAMEWORK_PATH=$PWD/Frameworks cargo tauri dev

# Full local .app (signed with your Developer ID automatically)
./scripts/build_macos_tauri.sh         # → dist/macos/Fluxion.app
```

The build script signs local builds with a stable identity so macOS
permission grants (Screen Recording etc.) survive rebuilds. Local builds use
bundle id `io.fluxion.local.dev`; releases use `io.fluxion.local`.

---

## Releases

A release is a tag on `main`. The build script derives the version from the
latest `v*` tag.

```bash
# 1. Make sure main is green and pushed
uv run pytest && git push origin main

# 2. Tag
git tag v0.6.0 && git push origin v0.6.0

# 3. Build the release artifacts (requires APPLE_SIGNING_IDENTITY for
#    Developer ID signing + dmg; notarize before public distribution)
APPLE_SIGNING_IDENTITY="Developer ID Application: Anudeep Gadige (3GHJTM7AV7)" \
  ./scripts/build_macos_tauri.sh       # → dist/macos/Fluxion.app, .dmg, .zip, SHA256SUMS
```

The zip + SHA256SUMS feed Sparkle auto-updates and Homebrew.

---

## Error Investigation

```bash
# Failed runs
sqlite3 var/traces.sqlite "SELECT run_id, status, error_message FROM runs
  WHERE status='failed' ORDER BY created_at DESC LIMIT 10;"
./dev.sh explore <run_id>

# Logs
./dev.sh debug
grep '"level":"ERROR"' logs/app.log | tail -20 | jq '{ts: .timestamp, msg: .message, err: .error}'
```

More trace queries: see the Traces DB section in `.claude/CLAUDE.md`.

---

## Key Files by Task

| Task | Files to Read |
|------|---------------|
| New feature | `docs/COMPONENTS.md`, similar existing feature |
| Bug fix | `logs/app.log`, `./dev.sh traces`, error location |
| API change | `orchestrator/routes/`, `orchestrator/schemas.py` |
| Agent change | `orchestrator/agent/agent_engine.py`, `orchestrator/agent/tools/` |
| UI change | `ui/src/components/`, `ui/src/hooks/` |
| Tauri/macOS shell | `src-tauri/src/lib.rs`, `scripts/build_macos_tauri.sh` |
| Config change | `orchestrator/chat_config.yaml`, `orchestrator/config.py` |
