from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from simtrade_core.database import Database
from simtrade_core.models import BookLevel, DataUnavailable, QuoteSnapshot, ValidationError
from simtrade_core.service import TradingService
from simtrade_core.trading_calendar import StaticCalendar


TZ = ZoneInfo("Asia/Shanghai")
FRIDAY = date(2026, 8, 14)
MONDAY = date(2026, 8, 17)
TUESDAY = date(2026, 8, 18)
MORNING = datetime(2026, 8, 14, 10, 0, 0, tzinfo=TZ)


def quote(
    *,
    at: datetime = MORNING,
    bids: tuple[BookLevel, ...] = (BookLevel(999, 100),),
    asks: tuple[BookLevel, ...] = (BookLevel(1000, 100),),
    upper: int | None = 1100,
    lower: int | None = 900,
) -> QuoteSnapshot:
    return QuoteSnapshot(
        code="600000",
        name="浦发银行",
        exchange="SH",
        source="fixture",
        quote_at=at,
        fetched_at=at,
        last_cents=1000,
        pre_close_cents=1000,
        upper_limit_cents=upper,
        lower_limit_cents=lower,
        listing_date=date(1999, 11, 10),
        status="TRADING",
        bids=bids,
        asks=asks,
        raw={"fixture": True},
    )


class FakeQuotes:
    def __init__(self, snapshots: list[QuoteSnapshot] | None = None):
        self.snapshots = snapshots or [quote()]
        self.index = 0

    def get_quote(self, code: str) -> QuoteSnapshot:
        item = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return item


class FailingQuotes:
    def get_quote(self, code: str) -> QuoteSnapshot:
        raise DataUnavailable("fixture provider unavailable")


class SimTradeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "simulation.db")
        self.calendar = StaticCalendar([FRIDAY, MONDAY, TUESDAY])
        self.quotes = FakeQuotes()
        self.service = TradingService(self.db, self.quotes, self.calendar)
        self.account = self.service.create_account("测试账户", "100000", now=MORNING)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_account_ledger_starts_reconciled(self) -> None:
        audit = self.service.audit(account_id=self.account["id"])
        self.assertTrue(audit["passed"], audit)
        self.assertEqual("100000.00", self.account["total_cash"])

    def test_buy_partial_fill_freezes_remainder_and_sets_next_trade_day(self) -> None:
        self.quotes.snapshots = [quote(asks=(BookLevel(1000, 100),))]
        order = self.service.place_order("BUY", "600000", 200, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("PARTIALLY_FILLED", order["status"])
        self.assertEqual(100, order["filled_quantity"])
        self.assertEqual("1000.01", order["frozen_cash"])
        portfolio = self.service.portfolio(account_id=self.account["id"], now=MORNING)
        self.assertEqual(100, portfolio["positions"][0]["shares"])
        self.assertEqual(0, portfolio["positions"][0]["available_shares"])
        with self.db.connect() as connection:
            lot = connection.execute("SELECT * FROM position_lots").fetchone()
        self.assertEqual(MONDAY.isoformat(), lot["available_on"])
        self.assertTrue(self.service.audit(account_id=self.account["id"])["passed"])

    def test_non_marketable_order_stays_open_and_cancel_releases_cash(self) -> None:
        self.quotes.snapshots = [quote(asks=(BookLevel(1050, 100),))]
        before = self.service.get_account(self.account["id"])
        order = self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("OPEN", order["status"])
        frozen = self.service.get_account(self.account["id"])
        self.assertNotEqual("0.00", frozen["frozen_cash"])
        cancelled = self.service.cancel_order(order["id"], now=MORNING)
        self.assertEqual("CANCELLED", cancelled["status"])
        after = self.service.get_account(self.account["id"])
        self.assertEqual(before["total_cash"], after["total_cash"])
        self.assertEqual(before["available_cash"], after["available_cash"])

    def test_stale_or_incomplete_quote_causes_no_order_or_cash_change(self) -> None:
        stale = quote(at=datetime(2026, 8, 14, 9, 58, tzinfo=TZ))
        self.quotes.snapshots = [stale]
        with self.assertRaises(DataUnavailable):
            self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual([], self.service.list_orders(account_id=self.account["id"]))

        self.quotes.snapshots = [quote(upper=None)]
        self.quotes.index = 0
        with self.assertRaises(DataUnavailable):
            self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual([], self.service.list_orders(account_id=self.account["id"]))

    def test_quote_without_book_is_valid_for_schema_but_not_matching(self) -> None:
        no_book = quote(bids=(), asks=())
        self.assertEqual([], no_book.schema_issues())
        self.quotes.snapshots = [no_book]
        with self.assertRaises(DataUnavailable):
            self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual([], self.service.list_orders(account_id=self.account["id"]))

    def test_price_tick_and_buy_lot_are_rejected_without_state_change(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.place_order("BUY", "600000", 100, "10.005", account_id=self.account["id"], now=MORNING)
        rejected = self.service.place_order("BUY", "600000", 101, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("REJECTED", rejected["status"])
        self.assertEqual("100000.00", self.service.get_account(self.account["id"])["total_cash"])

    def test_t_plus_one_and_sell_fees_realized_pnl(self) -> None:
        self.quotes.snapshots = [quote(asks=(BookLevel(1000, 100),))]
        buy = self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("FILLED", buy["status"])

        same_day = self.service.place_order("SELL", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("REJECTED", same_day["status"])

        monday_time = datetime(2026, 8, 17, 10, 0, tzinfo=TZ)
        self.quotes.snapshots = [quote(at=monday_time, bids=(BookLevel(1020, 100),), asks=())]
        self.quotes.index = 0
        sell = self.service.place_order("SELL", "600000", 100, "10.10", account_id=self.account["id"], now=monday_time)
        self.assertEqual("FILLED", sell["status"])
        fill = sell["fills"][0]
        self.assertEqual("5.00", fill["commission"])
        self.assertEqual("0.01", fill["transfer_fee"])
        self.assertEqual("0.51", fill["stamp_tax"])
        self.assertTrue(self.service.audit(account_id=self.account["id"])["passed"])

    def test_partial_order_reprocesses_with_new_snapshot(self) -> None:
        self.quotes.snapshots = [
            quote(asks=(BookLevel(1000, 100),)),
            quote(asks=(BookLevel(1000, 100),)),
        ]
        order = self.service.place_order("BUY", "600000", 200, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("PARTIALLY_FILLED", order["status"])
        processed = self.service.process_orders(order_id=order["id"], now=MORNING)
        self.assertEqual("FILLED", processed[0]["status"])
        self.assertEqual(2, len(processed[0]["fills"]))
        from decimal import Decimal

        self.assertEqual(Decimal("5.00"), sum((Decimal(fill["commission"]) for fill in processed[0]["fills"]), Decimal("0")))

    def test_transaction_rolls_back_when_next_trade_day_is_missing(self) -> None:
        broken = TradingService(self.db, FakeQuotes([quote()]), StaticCalendar([FRIDAY]))
        with self.assertRaises(DataUnavailable):
            broken.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual([], self.service.list_orders(account_id=self.account["id"]))
        self.assertEqual("100000.00", self.service.get_account(self.account["id"])["total_cash"])

    def test_expiration_releases_frozen_cash(self) -> None:
        self.quotes.snapshots = [quote(asks=(BookLevel(1050, 100),))]
        order = self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        self.assertEqual("OPEN", order["status"])
        after_close = datetime(2026, 8, 14, 15, 1, tzinfo=TZ)
        result = self.service.process_orders(order_id=order["id"], now=after_close)
        self.assertEqual("EXPIRED", result[0]["status"])
        account = self.service.get_account(self.account["id"])
        self.assertEqual("0.00", account["frozen_cash"])
        self.assertEqual("100000.00", account["available_cash"])

    def test_failed_valuation_never_falls_back_to_cost(self) -> None:
        self.service.place_order("BUY", "600000", 100, "10.00", account_id=self.account["id"], now=MORNING)
        failing = TradingService(self.db, FailingQuotes(), self.calendar)
        portfolio = failing.portfolio(account_id=self.account["id"], now=MORNING)
        self.assertEqual("INCOMPLETE", portfolio["valuation_status"])
        self.assertIsNone(portfolio["market_value"])
        self.assertIsNone(portfolio["total_assets"])
        self.assertIsNone(portfolio["positions"][0]["market_value"])

    def test_concurrent_orders_cannot_overspend(self) -> None:
        service = TradingService(self.db, FakeQuotes([quote(asks=(BookLevel(1100, 100),))]), self.calendar)

        def submit() -> str:
            return service.place_order("BUY", "600000", 5000, "10.00", account_id=self.account["id"], now=MORNING)["status"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(1, statuses.count("OPEN"))
        self.assertEqual(1, statuses.count("REJECTED"))
        account = self.service.get_account(self.account["id"])
        self.assertGreaterEqual(float(account["available_cash"]), 0)
        self.assertTrue(self.service.audit(account_id=self.account["id"])["passed"])


if __name__ == "__main__":
    unittest.main()
