"""Read-only queries shared by the CLI and the MCP server.

Everything here returns JSON-friendly dicts with amounts in dollars
(Plaid sign convention: positive = money out, negative = money in).
"""

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine

from finance.db import Account, Transaction, session_scope

# Money moving between your own accounts isn't spending or income.
TRANSFER_CATEGORIES = ("TRANSFER_IN", "TRANSFER_OUT")


def _dollars(cents: int | None) -> float | None:
    return None if cents is None else cents / 100


def list_accounts(engine: Engine) -> list[dict[str, Any]]:
    with session_scope(engine) as session:
        return [
            {
                "account_id": a.account_id,
                "name": a.name,
                "mask": a.mask,
                "type": a.type,
                "subtype": a.subtype,
                "current_balance": _dollars(a.current_balance_cents),
                "available_balance": _dollars(a.available_balance_cents),
                "currency": a.iso_currency_code,
            }
            for a in session.scalars(select(Account).order_by(Account.name))
        ]


def search_transactions(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
    text: str | None = None,
    account_id: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = select(Transaction, Account.name).join(Account)
    if start_date:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.date <= end_date)
    if text:
        pattern = f"%{text}%"
        stmt = stmt.where(or_(Transaction.name.ilike(pattern), Transaction.merchant_name.ilike(pattern)))
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category:
        stmt = stmt.where(Transaction.category_primary == category.upper())
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.transaction_id).limit(min(limit, 1000))

    with session_scope(engine) as session:
        return [
            {
                "transaction_id": t.transaction_id,
                "date": t.date.isoformat(),
                "name": t.name,
                "merchant": t.merchant_name,
                "amount": _dollars(t.amount_cents),
                "currency": t.iso_currency_code,
                "category": t.category_primary,
                "category_detailed": t.category_detailed,
                "pending": t.pending,
                "account": account_name,
            }
            for t, account_name in session.execute(stmt)
        ]


def spending_by_category(engine: Engine, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Total outflows per category, excluding pending transactions and transfers."""
    total = func.sum(Transaction.amount_cents)
    stmt = (
        select(Transaction.category_primary, total, func.count())
        .where(
            Transaction.date.between(start_date, end_date),
            Transaction.amount_cents > 0,
            Transaction.pending.is_(False),
            or_(
                Transaction.category_primary.is_(None),
                Transaction.category_primary.not_in(TRANSFER_CATEGORIES),
            ),
        )
        .group_by(Transaction.category_primary)
        .order_by(total.desc())
    )
    with session_scope(engine) as session:
        return [
            {"category": category or "UNCATEGORIZED", "total": _dollars(cents), "count": count}
            for category, cents, count in session.execute(stmt)
        ]


def monthly_cashflow(engine: Engine, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Income vs. spending per month, excluding pending transactions and transfers."""
    with session_scope(engine) as session:
        rows = session.execute(
            select(Transaction.date, Transaction.amount_cents).where(
                Transaction.date.between(start_date, end_date),
                Transaction.pending.is_(False),
                or_(
                    Transaction.category_primary.is_(None),
                    Transaction.category_primary.not_in(TRANSFER_CATEGORIES),
                ),
            )
        ).all()

    months: dict[str, dict[str, int]] = {}
    for txn_date, cents in rows:
        bucket = months.setdefault(txn_date.strftime("%Y-%m"), {"income": 0, "spending": 0})
        if cents < 0:
            bucket["income"] += -cents
        else:
            bucket["spending"] += cents
    return [
        {
            "month": month,
            "income": _dollars(v["income"]),
            "spending": _dollars(v["spending"]),
            "net": _dollars(v["income"] - v["spending"]),
        }
        for month, v in sorted(months.items())
    ]
