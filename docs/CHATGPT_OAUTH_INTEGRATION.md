# ChatGPT OAuth Integration — Research Findings

> **Status:** Historical research note. ChatGPT/Codex OAuth is implemented in `orchestrator/routes/auth.py` + `orchestrator/providers/chatgpt.py` and is available from the desktop model picker as well as API routes under `/api/auth/chatgpt`. Keep this file for design context; use `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md`, and the code as current source of truth.


## Goal

Allow users to log in with their ChatGPT subscription (Plus/Pro/etc.) and use OpenAI models (GPT-5, Codex, etc.) as the LLM provider in the Fluxion app — at no extra API cost to us or the user.

## How It Works

ChatGPT subscriptions now include Codex access. OpenAI provides a public OAuth flow for Codex authentication. Third-party tools (OpenClaw, CLIProxyAPI, OpenCode) already use this to route API calls through ChatGPT subscription tokens instead of paid API keys.

### The Key Insight

The Codex **app-server protocol** (JSON-RPC 2.0, agent loop owned by OpenAI) is NOT what we want. That would require rewriting the entire agent engine.

What we want is the **Codex OAuth token** — which authenticates against the **ChatGPT backend API**. A translation layer proxies standard `/v1/chat/completions` requests through this backend using the subscription token.

### Architecture

```
User clicks "Sign in with ChatGPT"
  → OpenAI OAuth flow in browser
  → Returns access token + refresh token
  → Token stored (session/cookie/DB)

User sends a query
  → Agent engine runs (UNCHANGED — same loop, tools, planning, citations)
  → openai_compat.py makes LLM call
  → Instead of DeepInfra, routes to ChatGPT backend with OAuth token
  → Translation layer converts between standard OpenAI API format and ChatGPT backend format
  → Response comes back in standard format
  → Agent engine continues as normal
```

### What Changes

- **New**: ChatGPT OAuth login flow (frontend button + backend token exchange)
- **New**: Token storage and refresh logic
- **New**: Provider option for "ChatGPT subscription" alongside DeepInfra
- **New**: Request/response translation layer (ChatGPT backend format differs slightly from standard OpenAI API)
- **Unchanged**: Agent engine, tools, planning structure, citations, SSE streaming, frontend UI

### What Does NOT Change

- `agent_engine.py` — agent loop stays exactly the same
- Current agent planning/Plan Mode lives in `orchestrator/agent/plan_mode.py` and durable plan docs; the old standalone research planner is no longer current runtime architecture.
- context handling remains backend-owned and provider-agnostic, but the current implementation now uses normalized model context profiles, bounded tool-result history, and 90%-threshold conversation compaction
- Tool execution (web_search, web_extract, python_execute) — all the same
- SSE streaming and frontend — all the same
- Citations, step tracking, forced synthesis — all the same

## Existing Implementations (Reference)

### OpenClaw
- Docs: https://docs.openclaw.ai/providers/openai
- Uses `openai-codex` provider with OAuth login
- Model IDs: `openai-codex/gpt-5.3-codex`, `openai-codex/codex-mini-latest`
- Auth command: `openclaw models auth login --provider openai-codex`

### OpenCode Codex Auth Plugin
- GitHub: https://github.com/numman-ali/opencode-openai-codex-auth
- Docs: https://numman-ali.github.io/opencode-openai-codex-auth/
- Intercepts OpenAI SDK requests, transforms for ChatGPT backend API
- 7-step fetch flow with format transformations
- Handles `item_reference` and other SDK constructs that ChatGPT backend doesn't recognize
- Stateless multi-turn via encrypted reasoning content
- Auto token refresh

### CLIProxyAPI
- GitHub: https://github.com/router-for-me/CLIProxyAPI
- Wraps ChatGPT Codex as OpenAI-compatible `/v1/chat/completions` endpoint
- Supports streaming and function calling/tools
- OAuth login for Codex

## OAuth Flow Details

From OpenAI's Codex auth docs (https://developers.openai.com/codex/auth/):

1. **Browser OAuth**: Opens browser window for ChatGPT login, returns access token
2. **Device code flow** (beta): For headless environments
3. **Tokens cached**: Stored at `~/.codex/auth.json` or OS credential store
4. **Auto refresh**: Token refresh handled automatically

For our integration, the flow would be:
1. Frontend: "Sign in with ChatGPT" button
2. Opens OpenAI OAuth URL in popup/redirect
3. User logs in with ChatGPT credentials
4. Callback receives access token + refresh token
5. Backend stores tokens per user session
6. Provider uses tokens for LLM calls

## OpenAI's Stance on Third-Party Usage

- OAuth flow is publicly documented and officially supported
- Codex CLI explicitly supports ChatGPT OAuth as a primary auth method
- OpenClaw, OpenCode, CLIProxyAPI all use this openly
- OpenAI has NOT restricted third-party OAuth usage (unlike Anthropic and Google who updated ToS to block it)
- Appears to be a deliberate competitive strategy — OpenAI embraced it after competitors blocked it

## Available Models via ChatGPT Subscription

- GPT-5 / GPT-5.1 / GPT-5.2 / GPT-5.3
- Codex (gpt-5.1-codex, gpt-5.3-codex)
- Codex Mini (codex-mini-latest)
- Various reasoning effort levels per model

## Risks

- OpenAI could change their ToS or block third-party OAuth usage at any time
- Rate limits tied to ChatGPT subscription tier (Plus: 30-150 msgs/5hr, Pro: 300-1500 msgs/5hr)
- ChatGPT backend API format may change without notice (it's not a stable public API)
- Token refresh edge cases

## Current Codebase Reality

This integration now coexists with the newer context system:
- active model metadata is normalized through the shared context-profile abstraction
- effective input budget is tracked as `context_window - max_output_tokens`
- historical reasoning is not rehydrated into future prompt history
- agent conversations compact visibly at 90% of effective input budget regardless of provider source

## Next Steps

1. Study the OpenCode Codex Auth Plugin source code for the exact translation logic
2. Understand the ChatGPT backend API format differences from standard OpenAI API
3. Decide: build translation layer in-app vs run external proxy (CLIProxyAPI)
4. Implement OAuth flow (frontend + backend)
5. Provider selection UI is implemented in the desktop model picker for hosted providers, local models, ChatGPT/Codex OAuth, and Grok OAuth.
6. Handle token storage and refresh
