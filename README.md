# Fluxion

Fluxion is a macOS coding agent that runs locally in a desktop app and works inside a repo workspace on your machine.

It can read files, edit code, run shell commands, search the web, extract pages, keep local conversation history, and switch between hosted provider models and local models.

I made it because the tools I wanted were split across different products in annoying ways. Local-model apps like LM Studio are good at running models, but they mostly stop at chat. A lot of coding agents can work in a repo, but they lean cloud-only, or they miss important tools once the task stops being purely local to the codebase. Fluxion is my attempt to put repo work, local models, hosted models, and web research in one place.

Fluxion is new and macOS-only right now. Expect bugs and rough edges.

Fluxion does not bundle, sell, or download models. Bring your own provider keys or local model files.

<p align="center">
  <img src="assets/brand/logo-128.png" alt="Fluxion" width="128">
</p>

## Install

Homebrew:

```bash
brew install --cask anudeep-gad12/tap/fluxion
open /Applications/Fluxion.app
```

Manual install: download **`Fluxion-macos-arm64.dmg`** from [GitHub Releases](https://github.com/anudeep-gad12/Fluxion/releases/latest), open it, and drag **Fluxion** to Applications.

Your conversations, settings, logs, and provider keys live outside the app bundle:

```text
~/Library/Application Support/Fluxion/data
```

Replacing `/Applications/Fluxion.app` updates the app without deleting your data.

### Legacy LaunchAgent installs

Older builds installed a background `io.fluxion.local` LaunchAgent. The desktop app removes it on startup. To clean up manually:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/io.fluxion.local.plist 2>/dev/null || true
rm -f ~/Library/LaunchAgents/io.fluxion.local.plist
```

### Uninstall

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/io.fluxion.local.plist 2>/dev/null || true
rm -f ~/Library/LaunchAgents/io.fluxion.local.plist
rm -rf ~/Library/Application\ Support/Fluxion
rm -rf /Applications/Fluxion.app
```

## Development

Source development still uses the FastAPI backend and Vite UI:

```bash
./dev.sh start          # API :9000 + UI :3000
```

Tauri desktop shell (API serves built UI on `:9000`):

```bash
./dev.sh desktop        # terminal 1 — API + ui/dist on :9000
cd src-tauri && cargo tauri dev   # terminal 2
```

After UI edits, run `./dev.sh desktop` again so `ui/dist` rebuilds, then quit and reopen Tauri.

Release build:

```bash
./scripts/build_macos_tauri.sh
```

Requires Rust, Xcode CLT, `uv`, and `pnpm`.

## Models

Fluxion can use hosted providers or local models.

Recommended starting point: for hosted models, try Fireworks with Kimi K2.6, GLM-5.1, or MiniMax M2.7.

For local models, I use Qwen3.6 27B and Qwen3.6 35B-A3B downloaded through LM Studio.

### Hosted providers

Add model provider keys or connect accounts in the model picker for:

- Fireworks
- OpenRouter
- DeepInfra
- OpenAI API
- ChatGPT / Codex OAuth
- xAI API
- Grok OAuth

Add a [Parallel](https://parallel.ai/) key if you want web search and page extraction. Parallel is not a model provider in Fluxion; it is only used for web tools.

### Local models

Fluxion only scans these folders:

```text
~/.lmstudio/models
~/.cache/lm-studio/models
```

Download models with LM Studio, or download GGUF/MLX models from Hugging Face and place them under one of those folders.

Example GGUF path:

```text
~/.lmstudio/models/lmstudio-community/Qwen3-8B-GGUF/Qwen3-8B-Q4_K_M.gguf
```

Example MLX path:

```text
~/.lmstudio/models/mlx-community/Qwen3-8B-MLX-4bit/config.json
```

GGUF models:

- require `llama.cpp` installed with `llama-server` available on `PATH`
- Fluxion starts `llama-server` automatically when you select a GGUF model
- `.gguf` files can live anywhere under the scanned folders

MLX models:

- require `mlx-lm` installed with `mlx_lm.server` available on `PATH`
- Fluxion starts `mlx_lm.server` automatically when you select an MLX model directory
- model directories must contain `config.json` and one or more `*.safetensors` files

Fluxion ignores Ollama folders, `mmproj` files, and extra GGUF split shards.

## What it can do

- create workspace conversations for local repos
- read and edit files
- search the codebase with grep/glob
- run shell commands
- search the web and extract page content with Parallel
- switch models from the app
- keep conversation history in local SQLite
- attach multiple integrated terminal sessions per conversation
- open app-managed browser tabs beside the agent in the desktop shell

## License

Apache-2.0
