# Fluxion

Fluxion is a coding agent that runs in your browser and works inside a local workspace.

It lets you use local models or provider APIs for coding tasks that involve reading files, editing code, running shell commands, and pulling in information from the web.

I made it because the tools I wanted were split across different products in annoying ways. Local-model apps like LM Studio are good at running models, but they mostly stop at chat. A lot of coding agents can work in a repo, but they lean cloud-only, or they miss important tools once the task stops being purely local to the codebase. In practice that usually means no real web search, no useful web extraction, or no clean way to do repo work and web research in one place.

Fluxion is my attempt to put that together. You can use local models you already have, or use hosted models through provider APIs, and point the agent at a workspace on your machine. From there it can inspect files, edit code, run commands, search the web, extract from pages, and keep going in the same conversation.

## Install

Download the latest macOS release from GitHub Releases:

```text
Fluxion-macos-arm64.zip
```

Unzip it, move `Fluxion.app` to `/Applications`, then clear macOS quarantine:

```bash
xattr -dr com.apple.quarantine /Applications/Fluxion.app
open /Applications/Fluxion.app
```

Fluxion is unsigned and not notarized, so the quarantine command is the reliable open path. Right-click → Open may work on some systems, but it is not required.

The app:

- starts the local service
- opens Fluxion in your browser at `http://127.0.0.1:9000`
- stores conversations outside the app bundle

Installed locations:

macOS
- app: `/Applications/Fluxion.app`
- service: `~/Library/LaunchAgents/io.fluxion.local.plist`
- data: `~/Library/Application Support/Fluxion/data`
- conversations SQLite: `~/Library/Application Support/Fluxion/data/var/traces.sqlite`

Replacing `Fluxion.app` updates the app without deleting conversations, settings, logs, or provider keys.

App command:

```bash
/Applications/Fluxion.app/Contents/MacOS/Fluxion open
/Applications/Fluxion.app/Contents/MacOS/Fluxion start
/Applications/Fluxion.app/Contents/MacOS/Fluxion stop
/Applications/Fluxion.app/Contents/MacOS/Fluxion restart
/Applications/Fluxion.app/Contents/MacOS/Fluxion status
```

Uninstall and delete local data:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/io.fluxion.local.plist 2>/dev/null || true
rm -f ~/Library/LaunchAgents/io.fluxion.local.plist
rm -rf ~/Library/Application\ Support/Fluxion
rm -rf /Applications/Fluxion.app
```

## Model setup

For cloud providers, add API keys in the model picker for:

- OpenRouter
- DeepInfra
- Fireworks

For local models:

- Fluxion uses `llama.cpp` / `llama-server` to launch local GGUF models, so you need that installed if you want local GGUF model support
- it only scans these LM Studio directories:
  - `~/.lmstudio/models`
  - `~/.cache/lm-studio/models`
- it ignores paths containing `ollama`
- if it finds GGUF files or MLX model directories there, you can select them from the model picker

For web search and web extraction:

- Fluxion uses Parallel's web APIs
- bring your own `PARALLEL_API_KEY`

## What it can do

- work inside a local workspace
- read and edit files
- search the codebase with `grep` and `glob`
- run shell commands with `bash`
- search the web and extract page content using Parallel's web APIs
- continue coding conversations across many turns
- switch between local and hosted models from the same UI
- keep a terminal attached to the conversation session

## Quick start

1. Install Fluxion.
2. Open the app.
3. Add a provider key or pick a local model Fluxion found in the LM Studio directories above.
4. Create a workspace conversation for your repo.
5. Give the agent a concrete coding task.

Example prompts:

```text
Fix the failing auth test without changing the API response shape.
```

```text
Add a dark mode toggle, wire it into settings, and update the tests.
```

```text
Refactor this parser to remove duplication, then run the relevant test file.
```

```text
Find where this endpoint builds the response, add the missing field, and verify it.
```

## Clone and run from source

```bash
uv sync
cd ui && pnpm install
just dev
```

or:

```bash
./dev.sh start
```

If you want local GGUF models from source, install `llama.cpp` / `llama-server` first.

Source install fallback:

```bash
curl -fsSL https://raw.githubusercontent.com/anudeep-gad12/Fluxion/main/scripts/install_local_service.sh | bash
```

## Tests

```bash
uv run pytest
./scripts/sanity_test.sh --debug
```

Useful debugging:

```bash
./dev.sh traces
./dev.sh debug
./dev.sh applogs
```

## License

Apache-2.0
