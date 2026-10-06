# personal_financial_data

Pulls your bank transactions from [Plaid](https://plaid.com) into a local database and exposes them to Claude through a read-only [MCP](https://modelcontextprotocol.io) server, so you can ask questions like *"what did I spend on food last month?"*.

Designed to start on a laptop against the Plaid **sandbox** and move to a home server with Docker Compose.

## Quick start (Plaid sandbox)

Requires [uv](https://docs.astral.sh/uv/). On Linux/WSL/macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # or open a new terminal
```

On WSL, keep the repo in your Linux home (e.g. `~/personal_financial_data`), not under `/mnt/c`: it's much faster there, and the virtualenv behaves.

```bash
uv sync
cp -n .env.example .env       # -n: never overwrite an existing .env
uv run finance gen-key            # paste into FINANCE_ENCRYPTION_KEY in .env (run once)
# add PLAID_CLIENT_ID / PLAID_SECRET (sandbox) from https://dashboard.plaid.com/developers/keys
# ...then save .env BEFORE running the commands below

uv run finance sandbox-link       # creates a test Item at "First Platypus Bank"
uv run finance sync --wait        # pulls transactions (waits for Plaid's initial pull)
uv run finance accounts
uv run finance transactions --limit 10
```

## Ask Claude about your data

`.mcp.json` registers the `finance` MCP server for Claude Code in this directory. Start `claude` here, approve the server, and ask away. Tools:

| Tool | What it does |
| --- | --- |
| `list_accounts` | Accounts and balances |
| `search_transactions` | Filter by date range, text, account, category |
| `spending_by_category` | Outflows per category (excludes transfers & pending) |
| `monthly_cashflow` | Income / spending / net per month |

Amounts follow Plaid's convention: **positive = money out, negative = money in**.

## Home server

```bash
cp -n .env.example .env   # fill in
docker compose up -d --build
```

This runs a `sync` service (every 6 hours) and an `mcp` service on `127.0.0.1:8765/mcp` (streamable HTTP). The MCP server has no authentication: reach it over Tailscale/WireGuard or an authenticating reverse proxy, never the open internet.

## Development

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
```

See [CLAUDE.md](CLAUDE.md) for architecture and workflow conventions.
