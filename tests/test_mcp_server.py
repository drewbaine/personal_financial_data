import asyncio

from finance.mcp_server import build_server


def test_all_tools_are_read_only(engine):
    tools = asyncio.run(build_server(engine).list_tools())
    assert {t.name for t in tools} == {
        "list_accounts",
        "search_transactions",
        "spending_by_category",
        "monthly_cashflow",
    }
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
