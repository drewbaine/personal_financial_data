from datetime import date

from finance import queries
from finance.sync import link_sandbox_item, sync_item
from tests.fakes import FakeGateway, txn


def _seed(engine, cipher):
    gateway = FakeGateway(
        {
            None: {
                "added": [
                    txn("t1", 4.50, date="2026-09-01", name="Starbucks"),
                    txn("t2", 60.00, date="2026-09-03", name="Uber", category="TRANSPORTATION"),
                    txn("t3", -2000.00, date="2026-09-15", name="Payroll", category="INCOME"),
                    txn("t4", 500.00, date="2026-09-20", name="To savings", category="TRANSFER_OUT"),
                    txn("t5", 12.00, date="2026-10-01", name="Starbucks", pending=True),
                ],
                "next_cursor": "c1",
                "has_more": False,
            }
        }
    )
    item_id = link_sandbox_item(engine, gateway, cipher, "ins_109508", "sandbox")
    sync_item(engine, gateway, cipher, item_id)


def test_list_accounts(engine, cipher):
    _seed(engine, cipher)
    [account] = queries.list_accounts(engine)
    assert account["current_balance"] == 110.0


def test_search_transactions_text_and_order(engine, cipher):
    _seed(engine, cipher)
    rows = queries.search_transactions(engine, text="starbucks")
    assert [r["transaction_id"] for r in rows] == ["t5", "t1"]
    assert rows[1]["amount"] == 4.5


def test_spending_by_category_excludes_transfers_income_and_pending(engine, cipher):
    _seed(engine, cipher)
    rows = queries.spending_by_category(engine, date(2026, 9, 1), date(2026, 10, 31))
    assert rows == [
        {"category": "TRANSPORTATION", "total": 60.0, "count": 1},
        {"category": "FOOD_AND_DRINK", "total": 4.5, "count": 1},
    ]


def test_monthly_cashflow(engine, cipher):
    _seed(engine, cipher)
    rows = queries.monthly_cashflow(engine, date(2026, 9, 1), date(2026, 10, 31))
    assert rows == [{"month": "2026-09", "income": 2000.0, "spending": 64.5, "net": 1935.5}]
