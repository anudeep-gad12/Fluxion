# Fluxion

Fluxion is a coding agent that runs in your browser and works inside a local workspace.

It lets you use local models or provider APIs for coding tasks that involve reading files, editing code, running shell commands, and pulling in information from the web.

I made it because the tools I wanted were split across different products in annoying ways. Local-model apps like LM Studio are good at running models, but they mostly stop at chat. A lot of coding agents can work in a repo, but they lean cloud-only, or they miss important tools once the task stops being purely local to the codebase. In practice that usually means no real web search, no useful web extraction, or no clean way to do repo work and web research in one place.

Fluxion is my attempt to put that together. You can use local models you already have, or use hosted models through provider APIs, and point the agent at a workspace on your machine. From there it can inspect files, edit code, run commands, search the web, extract from pages, and keep going in the same conversation.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/anudeep-gad12/Fluxion/main/scripts/install_local_service.sh | bash
```

That command:

- downloads Fluxion
- installs it locally
- starts the local service
- opens the app in your browser

Current installer targets:

- macOS
- Linux

Installed locations:

macOS
- app: `~/Library/Application Support/Fluxion`
- service: `~/Library/LaunchAgents/io.fluxion.local.plist`

Linux
- app: `~/.local/share/fluxion`
- service: `~/.config/systemd/user/fluxion.service`

Installed command:

```bash
fluxion open
fluxion start
fluxion stop
fluxion restart
fluxion status
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
