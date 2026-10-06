"""Linking Items and syncing transactions into the database."""

import json
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine

from finance.crypto import TokenCipher
from finance.db import Account, Item, Transaction, session_scope, utcnow
from finance.plaid_client import MutationDuringPagination, PlaidGateway

MAX_PAGINATION_RESTARTS = 3


@dataclass
class SyncResult:
    item_id: str
    added: int = 0
    modified: int = 0
    removed: int = 0


def to_cents(amount: float | None) -> int | None:
    if amount is None:
        return None
    return int((Decimal(str(amount)) * 100).quantize(Decimal(1)))


def link_sandbox_item(
    engine: Engine, gateway: PlaidGateway, cipher: TokenCipher, institution_id: str, environment: str
) -> str:
    public_token = gateway.sandbox_create_public_token(institution_id)
    access_token, item_id = gateway.exchange_public_token(public_token)
    with session_scope(engine) as session:
        session.merge(
            Item(
                item_id=item_id,
                institution_id=institution_id,
                access_token_encrypted=cipher.encrypt(access_token),
                environment=environment,
            )
        )
    return item_id


def _fetch_all_pages(gateway: PlaidGateway, access_token: str, cursor: str | None) -> dict[str, Any]:
    """Page through /transactions/sync, restarting from `cursor` if Plaid reports a mutation."""
    for _ in range(MAX_PAGINATION_RESTARTS):
        added: list[dict] = []
        modified: list[dict] = []
        removed: list[dict] = []
        accounts: dict[str, dict] = {}
        next_cursor = cursor
        try:
            while True:
                page = gateway.transactions_sync(access_token, next_cursor)
                added += page.get("added", [])
                modified += page.get("modified", [])
                removed += page.get("removed", [])
                for account in page.get("accounts", []):
                    accounts[account["account_id"]] = account
                next_cursor = page["next_cursor"]
                if not page.get("has_more"):
                    break
        except MutationDuringPagination:
            continue
        return {
            "added": added,
            "modified": modified,
            "removed": removed,
            "accounts": list(accounts.values()),
            "next_cursor": next_cursor,
            "transactions_update_status": page.get("transactions_update_status"),
        }
    raise RuntimeError("Plaid data kept changing during pagination; try again later.")


def _account_row(item_id: str, data: dict) -> Account:
    balances = data.get("balances") or {}
    return Account(
        account_id=data["account_id"],
        item_id=item_id,
        name=data.get("name") or "",
        official_name=data.get("official_name"),
        mask=data.get("mask"),
        type=str(data["type"]) if data.get("type") is not None else None,
        subtype=str(data["subtype"]) if data.get("subtype") is not None else None,
        current_balance_cents=to_cents(balances.get("current")),
        available_balance_cents=to_cents(balances.get("available")),
        iso_currency_code=balances.get("iso_currency_code"),
        updated_at=utcnow(),
    )


def _as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _transaction_row(data: dict) -> Transaction:
    pfc = data.get("personal_finance_category") or {}
    return Transaction(
        transaction_id=data["transaction_id"],
        account_id=data["account_id"],
        date=_as_date(data["date"]),
        authorized_date=_as_date(data.get("authorized_date")),
        name=data.get("name") or "",
        merchant_name=data.get("merchant_name"),
        amount_cents=to_cents(data["amount"]),
        iso_currency_code=data.get("iso_currency_code"),
        pending=bool(data.get("pending")),
        category_primary=pfc.get("primary"),
        category_detailed=pfc.get("detailed"),
        payment_channel=str(data["payment_channel"]) if data.get("payment_channel") else None,
        raw_json=json.dumps(data, default=str, sort_keys=True),
        updated_at=utcnow(),
    )


def sync_item(engine: Engine, gateway: PlaidGateway, cipher: TokenCipher, item_id: str) -> SyncResult:
    """Apply all pending changes for one Item atomically, then advance its cursor."""
    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        if item is None:
            raise KeyError(f"Unknown item {item_id}")
        access_token = cipher.decrypt(item.access_token_encrypted)
        changes = _fetch_all_pages(gateway, access_token, item.sync_cursor)

        for account in changes["accounts"]:
            session.merge(_account_row(item_id, account))
        session.flush()
        for txn in changes["added"] + changes["modified"]:
            session.merge(_transaction_row(txn))
        for removed in changes["removed"]:
            existing = session.get(Transaction, removed["transaction_id"])
            if existing is not None:
                session.delete(existing)

        item.sync_cursor = changes["next_cursor"]
        item.last_synced_at = utcnow()
        return SyncResult(
            item_id=item_id,
            added=len(changes["added"]),
            modified=len(changes["modified"]),
            removed=len(changes["removed"]),
        )


def sync_all(
    engine: Engine,
    gateway: PlaidGateway,
    cipher: TokenCipher,
    wait_until_ready: bool = False,
    poll_seconds: float = 5,
    max_polls: int = 12,
) -> list[SyncResult]:
    """Sync every Item.

    A freshly linked sandbox Item can return no transactions until Plaid finishes
    its initial pull; with `wait_until_ready`, retry Items that came back empty.
    """
    with session_scope(engine) as session:
        item_ids = list(session.scalars(select(Item.item_id)))

    results = []
    for item_id in item_ids:
        result = sync_item(engine, gateway, cipher, item_id)
        polls = 0
        while wait_until_ready and result.added == 0 and polls < max_polls and _never_had_data(engine, item_id):
            time.sleep(poll_seconds)
            polls += 1
            result = sync_item(engine, gateway, cipher, item_id)
        results.append(result)
    return results


def _never_had_data(engine: Engine, item_id: str) -> bool:
    with session_scope(engine) as session:
        stmt = select(Transaction.transaction_id).join(Account).where(Account.item_id == item_id).limit(1)
        return session.scalar(stmt) is None
