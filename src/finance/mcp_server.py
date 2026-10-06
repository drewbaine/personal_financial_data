"""MCP server exposing read-only financial queries to Claude.

Tools here must never write to the database or call Plaid.
"""

from datetime import date, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy.engine import Engine

from finance import queries

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _parse_date(value: str | None, default: date) -> date:
    return date.fromisoformat(value) if value else default


def build_server(engine: Engine) -> MCPServer:
    server = MCPServer(
        name="finance",
        instructions=(
            "Read-only access to the user's personal financial data synced from Plaid. "
            "Amounts are in dollars; positive = money out (spending), negative = money in (income). "
            "Dates are ISO-8601 (YYYY-MM-DD)."
        ),
    )

    @server.tool(annotations=READ_ONLY)
    def list_accounts() -> list[dict[str, Any]]:
        """List linked accounts with current and available balances."""
        return queries.list_accounts(engine)

    @server.tool(annotations=READ_ONLY)
    def search_transactions(
        start_date: str | None = None,
        end_date: str | None = None,
        text: str | None = None,
        account_id: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search transactions, newest first.

        `text` matches the transaction or merchant name. `category` is a Plaid
        personal-finance primary category such as FOOD_AND_DRINK or TRANSPORTATION.
        """
        return queries.search_transactions(
            engine,
            start_date=date.fromisoformat(start_date) if start_date else None,
            end_date=date.fromisoformat(end_date) if end_date else None,
            text=text,
            account_id=account_id,
            category=category,
            limit=limit,
        )

    @server.tool(annotations=READ_ONLY)
    def spending_by_category(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        """Total spending per category between two dates (default: last 30 days). Excludes transfers."""
        today = date.today()
        return queries.spending_by_category(
            engine,
            _parse_date(start_date, today - timedelta(days=30)),
            _parse_date(end_date, today),
        )

    @server.tool(annotations=READ_ONLY)
    def monthly_cashflow(start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        """Income, spending, and net per month (default: last 365 days). Excludes transfers."""
        today = date.today()
        return queries.monthly_cashflow(
            engine,
            _parse_date(start_date, today - timedelta(days=365)),
            _parse_date(end_date, today),
        )

    return server
