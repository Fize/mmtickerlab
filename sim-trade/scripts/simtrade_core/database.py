from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import SCHEMA_VERSION
from .models import ConflictError


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','ARCHIVED')),
    initial_cash_cents INTEGER NOT NULL CHECK(initial_cash_cents > 0),
    available_cash_cents INTEGER NOT NULL CHECK(available_cash_cents >= 0),
    frozen_cash_cents INTEGER NOT NULL DEFAULT 0 CHECK(frozen_cash_cents >= 0),
    commission_rate TEXT NOT NULL,
    minimum_commission_cents INTEGER NOT NULL CHECK(minimum_commission_cents >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    order_type TEXT NOT NULL CHECK(order_type = 'LIMIT'),
    limit_price_cents INTEGER NOT NULL CHECK(limit_price_cents > 0),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    filled_quantity INTEGER NOT NULL DEFAULT 0 CHECK(filled_quantity >= 0),
    status TEXT NOT NULL CHECK(status IN ('OPEN','PARTIALLY_FILLED','FILLED','CANCELLED','EXPIRED','REJECTED')),
    frozen_cash_cents INTEGER NOT NULL DEFAULT 0 CHECK(frozen_cash_cents >= 0),
    frozen_quantity INTEGER NOT NULL DEFAULT 0 CHECK(frozen_quantity >= 0),
    reject_reason TEXT,
    expires_on TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_account_status ON orders(account_id, status);
CREATE TABLE IF NOT EXISTS quote_snapshots (
    id TEXT PRIMARY KEY,
    order_id TEXT REFERENCES orders(id),
    code TEXT NOT NULL,
    source TEXT NOT NULL,
    purpose TEXT NOT NULL,
    quote_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    last_cents INTEGER NOT NULL,
    pre_close_cents INTEGER NOT NULL,
    upper_limit_cents INTEGER,
    lower_limit_cents INTEGER,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    quote_snapshot_id TEXT NOT NULL REFERENCES quote_snapshots(id),
    code TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
    price_cents INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    gross_cents INTEGER NOT NULL,
    commission_cents INTEGER NOT NULL,
    transfer_fee_cents INTEGER NOT NULL,
    stamp_tax_cents INTEGER NOT NULL,
    net_cash_cents INTEGER NOT NULL,
    disposed_cost_cents INTEGER NOT NULL DEFAULT 0,
    realized_pnl_cents INTEGER NOT NULL DEFAULT 0,
    rule_version TEXT NOT NULL,
    filled_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fills_account_time ON fills(account_id, filled_at);
CREATE TABLE IF NOT EXISTS position_lots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    acquired_fill_id TEXT NOT NULL REFERENCES fills(id) DEFERRABLE INITIALLY DEFERRED,
    acquired_on TEXT NOT NULL,
    available_on TEXT NOT NULL,
    original_quantity INTEGER NOT NULL,
    remaining_quantity INTEGER NOT NULL CHECK(remaining_quantity >= 0),
    cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lots_account_code ON position_lots(account_id, code, available_on);
CREATE TABLE IF NOT EXISTS lot_disposals (
    id TEXT PRIMARY KEY,
    sell_fill_id TEXT NOT NULL REFERENCES fills(id) DEFERRABLE INITIALLY DEFERRED,
    lot_id TEXT NOT NULL REFERENCES position_lots(id),
    quantity INTEGER NOT NULL,
    cost_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cash_ledger (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    event_type TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    balance_after_cents INTEGER NOT NULL CHECK(balance_after_cents >= 0),
    order_id TEXT REFERENCES orders(id),
    fill_id TEXT REFERENCES fills(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ledger_account_time ON cash_ledger(account_id, created_at);
CREATE TABLE IF NOT EXISTS trading_calendar (
    trade_date TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


class ClosingConnection(sqlite3.Connection):
    """Make ``with database.connect()`` close as well as commit/rollback."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta(key,value) VALUES('schema_version',?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise ConflictError(
                    f"数据库 schema 版本 {row['value']} 与程序版本 {SCHEMA_VERSION} 不一致；本 skill 不提供兼容迁移"
                )

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
