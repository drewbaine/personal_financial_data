# CLAUDE.md

Guidance for Claude (and humans) working in this repo.

## What this is

A personal finance pipeline: **Plaid → local DB → read-only MCP server → Claude**.

- Phase 1 (now): ingest transactions from the Plaid **sandbox**, store in SQLite, query via CLI and MCP.
- Phase 2: deploy on the owner's home server with Docker Compose (`compose.yaml`).
- Phase 3: real accounts (Plaid `production`), which needs a Plaid Link web flow, Postgres, and webhooks.

## Commands

```bash
uv sync                          # install deps (incl. dev)
uv run pytest -q                 # tests — no network, uses tests/fakes.py
uv run ruff check . && uv run ruff format .
uv run finance --help            # CLI: gen-key, init-db, sandbox-link, sync, accounts, transactions, mcp
uv add <pkg> / uv add --dev <pkg>  # never edit dependency lists or uv.lock by hand
```

## Layout

```
src/finance/
  config.py        Settings from env/.env (pydantic-settings)
  crypto.py        Fernet encryption for Plaid access tokens at rest
  db.py            SQLAlchemy models: Item, Account, Transaction
  plaid_client.py  The ONLY module that imports the Plaid SDK; returns plain dicts
  sync.py          Link + /transactions/sync logic (gateway-agnostic, unit-tested)
  queries.py       Read-only queries shared by CLI and MCP
  mcp_server.py    MCP tools (read-only wrappers over queries.py)
  cli.py           Typer CLI
tests/             pytest; FakeGateway in tests/fakes.py stands in for Plaid
```

## Invariants — do not break these

1. **Secrets never leave `.env`.** Never commit `.env`, `data/`, or any `*.db`. Never print, log, or return Plaid access tokens, `PLAID_SECRET`, or `FINANCE_ENCRYPTION_KEY`, not even in tests, debug output, or chat. Access tokens are stored only Fernet-encrypted (`Item.access_token_encrypted`).
2. **Real financial data is private.** Don't paste real transactions into commits, tests, fixtures, issues, or PRs. Test data is synthetic (see `tests/fakes.py`).
3. **MCP tools are read-only.** `mcp_server.py` may only call functions in `queries.py`; it must never write to the DB or call Plaid. Every tool carries `READ_ONLY` annotations, and `tests/test_mcp_server.py` enforces this.
4. **Money is integer cents** in the DB (`*_cents`), converted with `sync.to_cents` (Decimal, never float math). Convert to dollars only at the query/presentation boundary.
5. **Sign convention is Plaid's:** positive `amount_cents` = money out, negative = money in. Don't flip it in storage.
6. **Plaid stays behind `PlaidGateway`.** New Plaid calls go in `plaid_client.py`, return dicts, and get a matching method on `tests/fakes.FakeGateway`. Business logic must be testable without network.
7. **Sync is atomic per Item.** All pages of `/transactions/sync` are applied in one DB transaction and the cursor advances only on commit. On `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION`, restart from the original cursor.
8. **Stay portable to Postgres.** No SQLite-only SQL or types. Use SQLAlchemy constructs.

## Workflow

1. **Branch** off `main`; one focused change per branch/PR. Don't push to `main` directly.
2. **Test first for logic changes:** add or adjust a test in `tests/` that uses `FakeGateway`, then implement.
3. **Before every commit**, run `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`. All must pass (CI runs the same in `.github/workflows/ci.yml`).
4. **Schema changes:** there is no migration tool yet (`init_db` uses `create_all`, which doesn't alter existing tables). Adding a column means deleting the local sandbox DB (`rm data/finance.db`, then re-link and re-sync). **Before any real (production) data exists, introduce Alembic**, and make every schema change from then on a migration.
5. **Adding an MCP tool:** add the query to `queries.py` (with a test in `tests/test_queries.py`), then a thin wrapper in `mcp_server.py` with `annotations=READ_ONLY`, and update the expected tool set in `tests/test_mcp_server.py` and the README table.
6. **Commits:** imperative subject line (`Add merchant search tool`), body explains why.
7. **Verifying against real Plaid sandbox** needs network access to `sandbox.plaid.com` and keys in `.env`: `finance sandbox-link` then `finance sync --wait`. Cloud sandboxes may block that host; then rely on unit tests and say that the live run was not done.

## Plaid notes

- Sandbox institution default: `ins_109508` (First Platypus Bank). `sandbox-link` uses `/sandbox/public_token/create`, so no Link UI is needed in sandbox.
- A new Item may return zero transactions until Plaid's first pull finishes; `sync --wait` polls for it.
- Categories come from `personal_finance_category` (`category_primary` such as `FOOD_AND_DRINK`, `TRANSFER_OUT`). Spending and cashflow queries exclude `TRANSFER_IN`/`TRANSFER_OUT` and pending transactions.
- The full Plaid payload is kept in `Transaction.raw_json` so new fields can be backfilled without re-fetching.

## Roadmap (not built yet)

- Plaid Link web flow (small FastAPI page) for linking real institutions in production.
- Alembic migrations, then Postgres service in `compose.yaml` (add `psycopg[binary]`, set `DATABASE_URL`).
- Plaid webhooks (`SYNC_UPDATES_AVAILABLE`) instead of polling, behind a reverse proxy.
- Balance refresh, recurring-transaction detection, budgets.
- Auth for the HTTP MCP endpoint before exposing it beyond localhost/VPN.
