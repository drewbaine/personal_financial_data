from sqlalchemy import select

from finance.db import Item, Transaction, session_scope
from finance.sync import link_sandbox_item, sync_all, sync_item, to_cents
from tests.fakes import FakeGateway, txn


def _link(engine, gateway, cipher):
    return link_sandbox_item(engine, gateway, cipher, "ins_109508", "sandbox")


def test_to_cents_avoids_float_error():
    assert to_cents(0.1 + 0.2) == 30
    assert to_cents(-12.34) == -1234
    assert to_cents(None) is None


def test_link_encrypts_access_token(engine, cipher):
    item_id = _link(engine, FakeGateway(), cipher)
    with session_scope(engine) as session:
        item = session.get(Item, item_id)
        assert item.access_token_encrypted != "access-sandbox-secret"
        assert cipher.decrypt(item.access_token_encrypted) == "access-sandbox-secret"


def test_sync_paginates_and_advances_cursor(engine, cipher):
    gateway = FakeGateway(
        {
            None: {"added": [txn("t1", 4.5)], "next_cursor": "c1", "has_more": True},
            "c1": {
                "added": [txn("t2", -1000, name="Payroll", category="INCOME")],
                "next_cursor": "c2",
                "has_more": False,
            },
        }
    )
    item_id = _link(engine, gateway, cipher)

    result = sync_item(engine, gateway, cipher, item_id)

    assert (result.added, result.modified, result.removed) == (2, 0, 0)
    with session_scope(engine) as session:
        assert session.get(Item, item_id).sync_cursor == "c2"
        amounts = {t.transaction_id: t.amount_cents for t in session.scalars(select(Transaction))}
    assert amounts == {"t1": 450, "t2": -100000}


def test_sync_applies_modified_and_removed(engine, cipher):
    gateway = FakeGateway(
        {
            None: {"added": [txn("t1", 4.5), txn("t2", 9.99)], "next_cursor": "c1", "has_more": False},
            "c1": {
                "modified": [txn("t1", 5.25)],
                "removed": [{"transaction_id": "t2"}],
                "next_cursor": "c2",
                "has_more": False,
            },
        }
    )
    item_id = _link(engine, gateway, cipher)
    sync_item(engine, gateway, cipher, item_id)
    sync_item(engine, gateway, cipher, item_id)

    with session_scope(engine) as session:
        rows = {t.transaction_id: t.amount_cents for t in session.scalars(select(Transaction))}
    assert rows == {"t1": 525}


def test_mutation_during_pagination_restarts_from_original_cursor(engine, cipher):
    gateway = FakeGateway(
        {
            None: {"added": [txn("t1", 1)], "next_cursor": "c1", "has_more": True},
            "c1": {"added": [txn("t2", 2)], "next_cursor": "c2", "has_more": False},
        },
        mutate_once_at="c1",
    )
    item_id = _link(engine, gateway, cipher)

    result = sync_item(engine, gateway, cipher, item_id)

    assert gateway.calls == [None, "c1", None, "c1"]
    assert result.added == 2  # page one not double-counted


def test_sync_all_waits_for_initial_data(engine, cipher, monkeypatch):
    gateway = FakeGateway()
    _link(engine, gateway, cipher)
    real_sync = gateway.transactions_sync

    def becomes_ready(access_token, cursor):
        if len(gateway.calls) >= 2:
            gateway.pages_by_cursor[cursor] = {"added": [txn("t1", 3)], "next_cursor": "ready", "has_more": False}
        return real_sync(access_token, cursor)

    monkeypatch.setattr(gateway, "transactions_sync", becomes_ready)
    results = sync_all(engine, gateway, cipher, wait_until_ready=True, poll_seconds=0)

    assert results[0].added == 1
