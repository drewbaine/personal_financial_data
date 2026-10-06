"""Personal financial data: Plaid ingestion, local storage, and an MCP server for Claude."""


def main() -> None:
    from finance.cli import app

    app()
