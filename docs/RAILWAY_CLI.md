# Railway CLI Reference

Complete reference for the [Railway CLI](https://docs.railway.com/reference/cli-api) (v4.29+).

## Installation

```bash
brew install railway                      # macOS (Homebrew)
npm i -g @railway/cli                     # npm (Node 16+)
bash <(curl -fsSL cli.new)                # Shell script (macOS/Linux/WSL)
scoop install railway                     # Windows (Scoop)
cargo install railwayapp --locked         # Rust/Cargo
docker pull ghcr.io/railwayapp/cli:latest # Docker
```

## Authentication

```bash
railway login                  # Browser-based login
railway login --browserless    # Token-based login (headless/CI)
railway logout                 # Log out
railway whoami                 # Show current user
```

**CI/CD tokens** (set as env vars, no `railway login` needed):
- `RAILWAY_TOKEN` — Project-scoped token (deploy, logs, variables for one project)
- `RAILWAY_API_TOKEN` — Account/workspace-scoped token (cross-project operations)

## Global Flags

These work on most commands:

| Flag | Description |
|------|-------------|
| `-s, --service <NAME\|ID>` | Target a specific service |
| `-e, --environment <NAME\|ID>` | Target a specific environment |
| `--json` | Output in JSON format |
| `-y, --yes` | Skip confirmation prompts |
| `-h, --help` | Show help |
| `-V, --version` | Show CLI version |
| `-v, --verbose` | Verbose output |

---

## Project Management

### `railway init`

Create a new project. Alias: `railway new`

```bash
railway init                                    # Interactive
railway init --name my-api                      # Named project
railway init --name my-api --workspace "Team"   # In specific workspace
```

| Flag | Description |
|------|-------------|
| `-n, --name <NAME>` | Project name (random if omitted) |
| `-w, --workspace <ID\|NAME>` | Target workspace |
| `--json` | JSON output |

### `railway link`

Link current directory to an existing project.

```bash
railway link                                           # Interactive
railway link --project my-api                          # By name
railway link --project my-api --environment staging    # With environment
railway link --project my-api --service backend        # With service
```

| Flag | Description |
|------|-------------|
| `-p, --project <ID\|NAME>` | Project to link |
| `-e, --environment <ID\|NAME>` | Environment to link |
| `-s, --service <ID\|NAME>` | Service to link |
| `-w, --workspace <ID\|NAME>` | Workspace |
| `--json` | JSON output |

Stores config in `.railway/` directory (add to `.gitignore`).

### `railway unlink`

Disconnect current directory from a project.

```bash
railway unlink
```

### `railway list`

List all projects.

```bash
railway list
```

### `railway status`

Show linked project, environment, and service info.

```bash
railway status
```

### `railway open`

Open project in browser.

```bash
railway open             # Project dashboard
railway open live         # Live deployment
railway open metrics      # Metrics page
railway open settings     # Settings page
```

### `railway delete`

Delete a project.

```bash
railway delete
```

---

## Deployment

### `railway up`

Deploy current directory (your code). This is the main deploy command.

```bash
railway up                          # Deploy with live logs
railway up --detach                 # Deploy, return immediately
railway up --ci                     # Stream build logs only, exit when done
railway up --service backend        # Deploy to specific service
railway up --environment staging    # Deploy to specific environment
railway up ./backend                # Deploy a subdirectory
railway up --json                   # JSON output (implies --ci)
```

| Flag | Description |
|------|-------------|
| `-d, --detach` | Don't stream logs after upload |
| `-c, --ci` | Stream build logs only, exit when done |
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `-p, --project <ID>` | Target project |
| `--no-gitignore` | Don't respect .gitignore |
| `--path-as-root` | Use path argument as archive root |
| `--verbose` | Verbose output |
| `--json` | JSON log output (implies CI mode) |

Respects `.gitignore` and `.railwayignore`. Auto-excludes `.git` and `node_modules`.

Exit codes: `0` = success, `1` = failure.

### `railway deploy`

Deploy a **template** (not your code — use `railway up` for that).

```bash
railway deploy                                              # Interactive
railway deploy --template postgres                          # PostgreSQL
railway deploy --template postgres --template redis         # Multiple
railway deploy --template my-app --variable "PORT=3000"     # With vars
railway deploy --template my-app --variable "Backend.PORT=3000"  # Service-scoped var
```

| Flag | Description |
|------|-------------|
| `-t, --template <CODE>` | Template to deploy (postgres, mysql, redis, mongo, etc.) |
| `-v, --variable <KEY=VALUE>` | Set env var on template |

### `railway redeploy`

Redeploy the latest deployment without uploading new code. Useful for applying variable changes or recovering from failures.

```bash
railway redeploy                      # Redeploy linked service
railway redeploy --service backend    # Redeploy specific service
railway redeploy --yes                # Skip confirmation
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Target service |
| `-y, --yes` | Skip confirmation |
| `--json` | JSON output |

### `railway restart`

Restart a service's latest deployment.

```bash
railway restart
railway restart --service backend
railway restart --yes
```

### `railway down`

Remove the most recent deployment.

```bash
railway down
```

---

## Services

### `railway add`

Add a service to your project.

```bash
railway add                                          # Interactive
railway add --database postgres                      # Add PostgreSQL
railway add --database postgres --database redis     # Add multiple DBs
railway add --service                                # Empty service
railway add --service my-api                         # Named empty service
railway add --repo user/my-repo                      # From GitHub repo
railway add --image nginx:latest                     # From Docker image
railway add --service api --variables "PORT=3000"    # With env vars
```

| Flag | Description |
|------|-------------|
| `-d, --database <TYPE>` | Add database (postgres, mysql, redis, mongo) |
| `-s, --service [NAME]` | Create empty service (optional name) |
| `-r, --repo <REPO>` | Create from GitHub repo |
| `-i, --image <IMAGE>` | Create from Docker image |
| `-v, --variables <KEY=VALUE>` | Set env vars on new service |
| `--verbose` | Verbose output |
| `--json` | JSON output |

### `railway service`

Manage services. Has subcommands.

```bash
railway service                   # Interactive service linking
railway service backend           # Link specific service
railway service status            # Deployment status of linked service
railway service status --all      # Status of all services
railway service logs              # View service logs
railway service redeploy          # Redeploy service
railway service restart           # Restart service
railway service scale --us-west1=2  # Scale service
```

Subcommands: `link`, `status`, `logs`, `redeploy`, `restart`, `scale`

**Status flags:** `-a/--all`, `--json`
**Logs flags:** `-d/--deployment`, `-b/--build`, `-n/--lines`, `-f/--filter`, `--latest`, `-S/--since`, `-U/--until`, `--json`
**Redeploy/Restart flags:** `-y/--yes`, `--json`
**Scale flags:** `--<REGION>=<N>`, `--json`

### `railway scale`

Scale a service across regions. Auto-redeploys after changes.

```bash
railway scale                                   # Interactive
railway scale --us-west1=2 --us-east4=1         # Multi-region
railway scale --service backend --us-west1=3    # Named service
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `--<REGION>=<N>` | Instance count per region |
| `--json` | JSON output |

Available regions: `us-west1`, `us-west2`, `us-east4`, `europe-west4`, `asia-southeast1` (and more — dynamically fetched).

---

## Variables

### `railway variable`

Manage environment variables. Aliases: `variables`, `vars`, `var`

#### List variables

```bash
railway variable list                # Table format
railway variable list --kv           # KEY=VALUE format
railway variable list --json         # JSON format
railway variable ls                  # Alias
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `-k, --kv` | KEY=VALUE format |
| `--json` | JSON output |

#### Set variables

```bash
railway variable set API_KEY=secret123
railway variable set API_KEY=secret DEBUG=true          # Multiple at once
railway variable set SECRET --stdin <<< "my-secret"     # From stdin
railway variable set API_KEY=val --skip-deploys          # Don't trigger redeploy
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `--stdin` | Read value from stdin (single key) |
| `--skip-deploys` | Don't trigger redeployment |
| `--json` | JSON output |

#### Delete variables

```bash
railway variable delete API_KEY
railway variable rm API_KEY           # Alias
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `--json` | JSON output |

---

## Environments

### `railway environment`

Manage environments. Alias: `env`

```bash
railway environment                                         # Interactive switch
railway environment new staging                             # Create
railway environment new staging --duplicate production      # Clone from existing
railway environment delete staging                          # Delete
railway environment delete staging --yes                    # Skip confirmation
railway environment config                                  # Show config
railway environment config --environment staging            # Specific env config
```

#### Subcommands

| Subcommand | Description |
|------------|-------------|
| `link` | Link an environment |
| `new` | Create new environment |
| `delete` | Delete an environment |
| `edit` | Edit environment config |
| `config` | Show environment config |

**New flags:** `-d/--duplicate <ENV>` (alias: `--copy`), `--json`
**Delete flags:** `-y/--yes`, `--2fa-code <CODE>`, `--json`
**Edit flags:** `-e/--environment`, `-s/--service-config <SERVICE> <PATH> <VALUE>`, `-m/--message <MSG>`, `--stage`, `--json`
**Config flags:** `-e/--environment`, `--json`

#### Edit examples

```bash
# Set a service config using dot-path notation
railway environment edit --service-config backend variables.API_KEY.value "secret"

# Stage changes without committing
railway environment edit --service-config backend variables.PORT.value "3000" --stage
```

---

## Local Development

### `railway run`

Run a command locally with Railway env vars injected. Alias: `railway local`

```bash
railway run npm start                              # Run with env vars
railway run python main.py                         # Python
railway run --service backend npm start            # From specific service
railway run npx prisma migrate deploy              # DB migrations
railway run rails console                          # Interactive REPL
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Service to pull vars from |
| `-e, --environment <ENV>` | Environment to pull vars from |
| `-p, --project <ID>` | Project to use |
| `--no-local` | Skip local develop overrides |
| `-v, --verbose` | Verbose domain replacement info |

Returns the same exit code as the executed command.

### `railway shell`

Open an interactive shell with Railway env vars loaded.

```bash
railway shell                        # Open shell
railway shell --service backend      # With specific service vars
railway shell --silent               # No welcome banner
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Service to pull vars from |
| `--silent` | Suppress welcome banner |

Sets `IN_RAILWAY_SHELL=true`. Exit with `exit`.

### `railway dev`

Run your full project locally using Docker. Alias: `railway develop`

```bash
railway dev                                    # Start all services
railway dev --verbose                          # Verbose output
railway dev --dry-run                          # Generate compose file only
railway dev --no-tui                           # Stream logs (no TUI)
railway dev down                               # Stop services
railway dev clean                              # Stop + remove volumes/data
railway dev configure --service backend        # Configure a service
railway dev configure --remove                 # Remove all configs
```

#### Subcommands

| Subcommand | Description |
|------------|-------------|
| `up` | Start services (default) |
| `down` | Stop services |
| `clean` | Stop + remove volumes/data |
| `configure` | Configure local services |

**Up flags:** `-e/--environment`, `-o/--output <PATH>`, `--dry-run`, `--no-https`, `-v/--verbose`, `--no-tui`
**Configure flags:** `--service <SERVICE>`, `--remove [SERVICE]`

---

## Logs & Debugging

### `railway logs`

View/stream deployment logs.

```bash
railway logs                                         # Stream live logs
railway logs --build                                 # Build logs
railway logs --lines 100                             # Last 100 lines
railway logs --since 1h                              # Last hour
railway logs --since 30m --until 10m                 # Time range
railway logs --filter "@level:error"                 # Filter by level
railway logs --service backend --environment prod    # Specific service+env
railway logs --latest                                # Latest deploy (even if failed)
railway logs --json                                  # JSON format
```

| Flag | Description |
|------|-------------|
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `-d, --deployment` | Show deployment logs |
| `-b, --build` | Show build logs |
| `-n, --lines <N>` | Number of lines (disables streaming) |
| `-f, --filter <QUERY>` | Filter using Railway query syntax |
| `--latest` | Show logs from latest deploy (even if failed/building) |
| `-S, --since <TIME>` | Logs since time (disables streaming) |
| `-U, --until <TIME>` | Logs until time (disables streaming) |
| `--json` | JSON output |

**Time formats:** Relative (`30s`, `5m`, `2h`, `1d`, `1w`) or ISO 8601 (`2024-01-15T10:30:00Z`).

**Filter syntax:** `@level:error`, `@level:warn`, free text search, etc.

### `railway ssh`

SSH into a running service container (WebSocket-based, not standard SSH).

```bash
railway ssh                              # Interactive shell in container
railway ssh -- ls -la                    # Run single command
railway ssh --session                    # Persistent tmux session
railway ssh --service backend            # Target service
```

| Flag | Description |
|------|-------------|
| `-p, --project <ID>` | Target project |
| `-s, --service <SERVICE>` | Target service |
| `-e, --environment <ENV>` | Target environment |
| `-d, --deployment-instance <ID>` | Specific deployment instance |
| `--session [NAME]` | Use tmux session (installs tmux if needed) |

Limitations: No SCP/SFTP, no port forwarding, no VS Code Remote-SSH.

### `railway connect`

Connect to a database shell directly (psql, mysql, redis-cli, mongosh).

```bash
railway connect                           # Interactive selection
railway connect postgres                  # Connect to PostgreSQL
railway connect postgres --environment staging
```

| Flag | Description |
|------|-------------|
| `-e, --environment <ENV>` | Target environment |

Requirements: Database must have TCP Proxy enabled (public URL). Matching client must be installed locally.

---

## Networking

### `railway domain`

Manage domains for a service.

```bash
railway domain                                # Generate *.up.railway.app domain
railway domain example.com                    # Add custom domain (shows DNS records)
railway domain example.com --port 8080        # With specific port
railway domain example.com --service api      # For specific service
```

| Flag | Description |
|------|-------------|
| `-p, --port <PORT>` | Port to connect domain to |
| `-s, --service <SERVICE>` | Target service |
| `--json` | JSON output |

One Railway-provided domain per service. Multiple custom domains allowed.

---

## Volumes

### `railway volume`

Manage persistent storage volumes.

#### Subcommands

| Subcommand | Aliases | Description |
|------------|---------|-------------|
| `list` | `ls` | List volumes |
| `add` | `create` | Create a volume |
| `delete` | `remove`, `rm` | Delete a volume |
| `update` | `edit` | Update volume config |
| `detach` | — | Detach from service |
| `attach` | — | Attach to service |

```bash
railway volume list
railway volume add --mount-path /data
railway volume delete --volume my-volume
railway volume delete --volume my-volume --yes
railway volume update --volume my-volume --mount-path /new/path
railway volume update --volume my-volume --name new-name
railway volume detach --volume my-volume
railway volume attach --volume my-volume --service backend
```

**Common flags:** `-s/--service`, `-e/--environment`, `--json`
**Add:** `-m/--mount-path <PATH>` (must start with `/`)
**Delete:** `-v/--volume <VOLUME>`, `-y/--yes`, `--2fa-code <CODE>`
**Update:** `-v/--volume`, `-m/--mount-path`, `-n/--name`
**Detach/Attach:** `-v/--volume`, `-y/--yes`

---

## Functions

### `railway functions`

Manage Railway Functions (serverless). Aliases: `function`, `func`, `fn`, `funcs`, `fns`

#### Subcommands

| Subcommand | Aliases | Description |
|------------|---------|-------------|
| `list` | `ls` | List functions |
| `new` | `create` | Create a function |
| `delete` | `remove`, `rm` | Delete a function |
| `push` | `up` | Push/deploy changes |
| `pull` | — | Pull changes from linked function |
| `link` | — | Link a function manually |

```bash
railway functions list
railway functions new --path ./handler.ts --name my-func
railway functions new --path ./api.ts --name api --http           # HTTP endpoint
railway functions new --path ./job.ts --name cleanup --cron "0 * * * *"  # Cron job
railway functions new --path ./func.ts --name f --serverless      # Dormancy mode
railway functions push                                             # Deploy
railway functions push --watch                                     # Auto-deploy on changes
railway functions delete --function my-func
railway functions pull                                             # Pull remote changes
```

**New flags:** `-p/--path`, `-n/--name`, `-c/--cron <SCHEDULE>`, `--http`, `-s/--serverless`, `-w/--watch`
**Push flags:** `-p/--path`, `-w/--watch`
**Delete flags:** `-f/--function`, `-y/--yes`
**Universal:** `-e/--environment`

---

## Utilities

### `railway completion`

Generate shell completions.

```bash
railway completion bash
railway completion zsh
railway completion fish
```

### `railway docs`

Open Railway documentation in browser.

```bash
railway docs
```

### `railway upgrade`

Upgrade the CLI to the latest version.

```bash
railway upgrade
```

### `railway starship`

Output project metadata as JSON for [Starship](https://starship.rs/) prompt integration.

```bash
railway starship
# Output: {"project":"id","name":"my-project","environment":"id","environmentName":"production"}
```

---

## Quick Reference: Common Workflows

```bash
# Setup a new project
railway login && railway init --name my-app && railway up

# Link to existing and deploy
railway link --project my-app --environment production --service backend
railway up

# Check logs for errors
railway logs --lines 200 --filter "@level:error"
railway logs --since 1h --service backend

# Set env vars and redeploy
railway variable set API_KEY=abc123 DB_URL=postgres://...
railway redeploy

# Debug in production
railway ssh --service backend
railway connect postgres

# Scale up
railway scale --service backend --us-west1=3 --us-east4=2

# Local dev with prod vars
railway run npm start
railway shell  # interactive

# Full local environment
railway dev
railway dev down
```

---

*Source: [Railway CLI Docs](https://docs.railway.com/reference/cli-api) | [CLI Guide](https://docs.railway.com/guides/cli) | [GitHub](https://github.com/railwayapp/cli)*
