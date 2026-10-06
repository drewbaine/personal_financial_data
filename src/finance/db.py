"""Database schema and session helpers.

Kept portable between SQLite (local/dev) and Postgres (home server): no
dialect-specific types, money stored as integer cents.
"""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


class Item(Base):
    """A Plaid Item: one login at one institution."""

    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    institution_id: Mapped[str | None] = mapped_column(String)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    sync_cursor: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"), index=True)
    name: Mapped[str] = mapped_column(String)
    official_name: Mapped[str | None] = mapped_column(String)
    mask: Mapped[str | None] = mapped_column(String)
    type: Mapped[str | None] = mapped_column(String)
    subtype: Mapped[str | None] = mapped_column(String)
    current_balance_cents: Mapped[int | None] = mapped_column(Integer)
    available_balance_cents: Mapped[int | None] = mapped_column(Integer)
    iso_currency_code: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    """A Plaid transaction. `amount_cents` follows Plaid's sign: positive = money out."""

    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    authorized_date: Mapped[dt.date | None] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String)
    merchant_name: Mapped[str | None] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(Integer)
    iso_currency_code: Mapped[str | None] = mapped_column(String)
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    category_primary: Mapped[str | None] = mapped_column(String, index=True)
    category_detailed: Mapped[str | None] = mapped_column(String)
    payment_channel: Mapped[str | None] = mapped_column(String)
    raw_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:///:memory:"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Session that commits on success and rolls back on any exception."""
    session = sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
