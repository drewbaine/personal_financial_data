"""`finance` command-line interface."""

import json
import time
from typing import Annotated

import typer

from finance import queries
from finance.config import get_settings
from finance.crypto import TokenCipher, generate_key
from finance.db import init_db, make_engine
from finance.plaid_client import DEFAULT_SANDBOX_INSTITUTION, PlaidSDKGateway
from finance.sync import link_sandbox_item, sync_all

app = typer.Typer(no_args_is_help=True, help="Personal financial data: Plaid ingestion and queries.")


def _engine():
    engine = make_engine(get_settings().database_url)
    init_db(engine)
    return engine


def _cipher() -> TokenCipher:
    return TokenCipher(get_settings().finance_encryption_key.get_secret_value())


@app.command("gen-key")
def gen_key() -> None:
    """Print a new FINANCE_ENCRYPTION_KEY for your .env."""
    typer.echo(generate_key())


@app.command("init-db")
def init_db_cmd() -> None:
    """Create database tables if they don't exist."""
    _engine()
    typer.echo("Database ready.")


@app.command("sandbox-link")
def sandbox_link(
    institution_id: Annotated[str, typer.Option(help="Plaid sandbox institution id")] = DEFAULT_SANDBOX_INSTITUTION,
) -> None:
    """Create a sandbox Item without Plaid Link and store its (encrypted) access token."""
    settings = get_settings()
    item_id = link_sandbox_item(_engine(), PlaidSDKGateway(settings), _cipher(), institution_id, settings.plaid_env)
    typer.echo(f"Linked item {item_id}. Run `finance sync --wait` to pull transactions.")


@app.command()
def sync(
    wait: Annotated[bool, typer.Option(help="Poll until a newly linked Item has transactions")] = False,
    every: Annotated[int, typer.Option(help="Keep running, syncing every N seconds (0 = once)")] = 0,
) -> None:
    """Pull new, modified, and removed transactions for every linked Item."""
    engine, gateway, cipher = _engine(), PlaidSDKGateway(get_settings()), _cipher()
    while True:
        for result in sync_all(engine, gateway, cipher, wait_until_ready=wait):
            typer.echo(f"{result.item_id}: +{result.added} ~{result.modified} -{result.removed}")
        if not every:
            break
        time.sleep(every)


@app.command()
def accounts() -> None:
    """Show linked accounts and balances as JSON."""
    typer.echo(json.dumps(queries.list_accounts(_engine()), indent=2))


@app.command()
def transactions(
    limit: int = 20,
    text: Annotated[str | None, typer.Option(help="Match transaction or merchant name")] = None,
) -> None:
    """Show recent transactions as JSON."""
    typer.echo(json.dumps(queries.search_transactions(_engine(), text=text, limit=limit), indent=2))


@app.command()
def mcp(
    transport: Annotated[str, typer.Option(help="stdio or streamable-http")] = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Run the read-only MCP server so Claude can query your data."""
    from finance.mcp_server import build_server

    server = build_server(_engine())
    if transport == "stdio":
        server.run("stdio")
    elif transport == "streamable-http":
        server.run("streamable-http", host=host, port=port)
    else:
        raise typer.BadParameter("transport must be stdio or streamable-http")
