# Fluxion

Fluxion is a macOS coding agent that runs locally, opens in your browser, and works inside a repo workspace on your machine.

It can read files, edit code, run shell commands, search the web, extract pages, keep local conversation history, and switch between hosted provider models and local models.

I made it because the tools I wanted were split across different products in annoying ways. Local-model apps like LM Studio are good at running models, but they mostly stop at chat. A lot of coding agents can work in a repo, but they lean cloud-only, or they miss important tools once the task stops being purely local to the codebase. Fluxion is my attempt to put repo work, local models, hosted models, and web research in one place.

Fluxion is new and macOS-only right now. Expect bugs and rough edges.

Fluxion does not bundle, sell, or download models. Bring your own provider keys or local model files.

## Install

Download the latest macOS release from GitHub Releases:

```text
Fluxion-macos-arm64.zip
```

If the zip is in your Downloads folder, run:

```bash
cd ~/Downloads
unzip -o Fluxion-macos-arm64.zip
rm -rf /Applications/Fluxion.app
mv Fluxion.app /Applications/
xattr -dr com.apple.quarantine /Applications/Fluxion.app
open /Applications/Fluxion.app
```

Fluxion is unsigned, so right-click → Open is unreliable. The command path above avoids the repeated macOS prompts you can hit when moving the app manually.

When launched, Fluxion starts a local service and opens the app at:

```text
http://127.0.0.1:9000
```

Your conversations, settings, logs, and provider keys live outside the app bundle:

```text
~/Library/Application Support/Fluxion/data
```

Replacing `/Applications/Fluxion.app` updates the app without deleting your data.

Useful app commands:

```bash
/Applications/Fluxion.app/Contents/MacOS/Fluxion open
/Applications/Fluxion.app/Contents/MacOS/Fluxion start
/Applications/Fluxion.app/Contents/MacOS/Fluxion stop
/Applications/Fluxion.app/Contents/MacOS/Fluxion status
```

Uninstall and delete local data:

```bash
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/io.fluxion.local.plist 2>/dev/null || true
rm -f ~/Library/LaunchAgents/io.fluxion.local.plist
rm -rf ~/Library/Application\ Support/Fluxion
rm -rf /Applications/Fluxion.app
```

## Models

Fluxion can use hosted providers or local models.

### Hosted providers

Add model provider keys in the model picker for:

- Fireworks
- OpenRouter
- DeepInfra

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
- attach a terminal to a conversation

## Development from source

Source running is for development. The normal user install is the macOS app release.

```bash
uv sync
cd ui && pnpm install
./dev.sh start
```

Tests:

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
