from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

from .database import Database
from .market_data import fetch_trade_dates
from .models import DataUnavailable


TZ = ZoneInfo("Asia/Shanghai")


class CalendarProvider(Protocol):
    def is_trading_day(self, day: date) -> bool: ...
    def next_trading_day(self, day: date) -> date: ...
    def latest_trading_day(self, day: date) -> date: ...


class TradingCalendar:
    def __init__(self, database: Database):
        self.database = database

    def refresh(self) -> int:
        days = fetch_trade_dates()
        fetched_at = datetime.now(TZ).isoformat()
        with self.database.transaction() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO trading_calendar(trade_date,source,fetched_at) VALUES(?,?,?)",
                ((day.isoformat(), "AKShare.tool_trade_date_hist_sina", fetched_at) for day in days),
            )
        return len(days)

    def _ensure(self, day: date, *, need_future: bool = False) -> None:
        with self.database.connect() as connection:
            exact = connection.execute("SELECT 1 FROM trading_calendar WHERE trade_date=?", (day.isoformat(),)).fetchone()
            future = connection.execute(
                "SELECT 1 FROM trading_calendar WHERE trade_date>? LIMIT 1", (day.isoformat(),)
            ).fetchone()
            count = connection.execute("SELECT COUNT(*) AS n FROM trading_calendar").fetchone()["n"]
        if count == 0 or (need_future and future is None):
            self.refresh()
        elif exact is None:
            # A populated calendar can safely identify a closed day only when it spans both sides.
            with self.database.connect() as connection:
                before = connection.execute("SELECT 1 FROM trading_calendar WHERE trade_date<? LIMIT 1", (day.isoformat(),)).fetchone()
                after = connection.execute("SELECT 1 FROM trading_calendar WHERE trade_date>? LIMIT 1", (day.isoformat(),)).fetchone()
            if before is None or after is None:
                self.refresh()

    def is_trading_day(self, day: date) -> bool:
        self._ensure(day)
        with self.database.connect() as connection:
            return connection.execute("SELECT 1 FROM trading_calendar WHERE trade_date=?", (day.isoformat(),)).fetchone() is not None

    def next_trading_day(self, day: date) -> date:
        self._ensure(day, need_future=True)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT trade_date FROM trading_calendar WHERE trade_date>? ORDER BY trade_date LIMIT 1",
                (day.isoformat(),),
            ).fetchone()
        if row is None:
            raise DataUnavailable(f"交易日历无法确定 {day} 的下一交易日")
        return date.fromisoformat(row["trade_date"])

    def latest_trading_day(self, day: date) -> date:
        self._ensure(day)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT trade_date FROM trading_calendar WHERE trade_date<=? ORDER BY trade_date DESC LIMIT 1",
                (day.isoformat(),),
            ).fetchone()
        if row is None:
            raise DataUnavailable(f"交易日历无法确定 {day} 之前的最近交易日")
        return date.fromisoformat(row["trade_date"])


class StaticCalendar:
    """Deterministic calendar for isolated tests."""

    def __init__(self, days: Iterable[date]):
        self.days = tuple(sorted(set(days)))

    def is_trading_day(self, day: date) -> bool:
        return day in self.days

    def next_trading_day(self, day: date) -> date:
        for candidate in self.days:
            if candidate > day:
                return candidate
        raise DataUnavailable(f"测试日历缺少 {day} 的下一交易日")

    def latest_trading_day(self, day: date) -> date:
        candidates = [candidate for candidate in self.days if candidate <= day]
        if not candidates:
            raise DataUnavailable(f"测试日历缺少 {day} 之前的交易日")
        return candidates[-1]
