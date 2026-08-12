from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

# Required project import order: install the transport patch before importing AKShare.
import akshare_patch  # noqa: F401
import akshare as ak
import requests

from .models import BookLevel, DataUnavailable, QuoteSnapshot, money_to_cents
from .rules import exchange_for_code, normalize_code


TZ = ZoneInfo("Asia/Shanghai")


class QuoteProvider(Protocol):
    def get_quote(self, code: str) -> QuoteSnapshot: ...


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _price_cents(value: Any) -> int | None:
    number = _number(value)
    return money_to_cents(number) if number is not None else None


def _listing_date(value: Any) -> date | None:
    if value in (None, "", "-"):
        return None
    text = str(value).split(".")[0]
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _quote_time(value: Any) -> datetime | None:
    try:
        stamp = int(float(value))
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    return datetime.fromtimestamp(stamp, TZ)


def _book(data: dict[str, Any], pairs: tuple[tuple[str, str], ...]) -> tuple[BookLevel, ...]:
    levels: list[BookLevel] = []
    for price_field, volume_field in pairs:
        price = _price_cents(data.get(price_field))
        volume_lots = _number(data.get(volume_field))
        quantity = int(volume_lots * 100) if volume_lots is not None else 0
        if price and quantity > 0:
            levels.append(BookLevel(price, quantity))
    return tuple(levels)


class EastMoneyQuoteProvider:
    """Strict single-security five-level quote adapter."""

    URL = "https://push2.eastmoney.com/api/qt/stock/get"
    FIELDS = ",".join(
        [
            "f11", "f12", "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20",
            "f31", "f32", "f33", "f34", "f35", "f36", "f37", "f38", "f39", "f40",
            "f43", "f51", "f52", "f57", "f58", "f60", "f86", "f107", "f189", "f292",
        ]
    )

    def get_quote(self, code: str) -> QuoteSnapshot:
        clean = normalize_code(code)
        exchange = exchange_for_code(clean)
        market = "1" if exchange == "SH" else "0"
        try:
            response = requests.get(
                self.URL,
                params={"fltt": "2", "invt": "2", "fields": self.FIELDS, "secid": f"{market}.{clean}"},
                timeout=15,
            )
            payload = response.json()
        except Exception as exc:
            raise DataUnavailable(f"获取 {clean} 五档行情失败：{exc}") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise DataUnavailable(f"{clean} 行情响应缺少 data", details={"provider_response": payload})

        fetched_at = datetime.now(TZ)
        quote_at = _quote_time(data.get("f86"))
        if quote_at is None:
            quote_at = fetched_at.replace(year=1970, month=1, day=1)
        bids = _book(data, (("f19", "f20"), ("f17", "f18"), ("f15", "f16"), ("f13", "f14"), ("f11", "f12")))
        asks = _book(data, (("f39", "f40"), ("f37", "f38"), ("f35", "f36"), ("f33", "f34"), ("f31", "f32")))
        last = _price_cents(data.get("f43")) or 0
        pre_close = _price_cents(data.get("f60")) or 0
        status = "TRADING" if last > 0 and pre_close > 0 and (bids or asks) else "CLOSED_OR_NO_BOOK"
        return QuoteSnapshot(
            code=str(data.get("f57") or clean).zfill(6),
            name=str(data.get("f58") or "").strip(),
            exchange=exchange,
            source="EastMoney.push2/AKShare-transport",
            quote_at=quote_at,
            fetched_at=fetched_at,
            last_cents=last,
            pre_close_cents=pre_close,
            upper_limit_cents=_price_cents(data.get("f51")),
            lower_limit_cents=_price_cents(data.get("f52")),
            listing_date=_listing_date(data.get("f189")),
            status=status,
            bids=bids,
            asks=asks,
            raw=data,
        )


def fetch_trade_dates() -> list[date]:
    try:
        frame = ak.tool_trade_date_hist_sina()
    except Exception as exc:
        raise DataUnavailable(f"AKShare 交易日历获取失败：{exc}") from exc
    if frame is None or frame.empty or "trade_date" not in frame.columns:
        raise DataUnavailable("AKShare 交易日历为空或缺少 trade_date")
    days: list[date] = []
    for value in frame["trade_date"].tolist():
        if isinstance(value, datetime):
            days.append(value.date())
        elif isinstance(value, date):
            days.append(value)
        else:
            try:
                days.append(datetime.fromisoformat(str(value)).date())
            except ValueError as exc:
                raise DataUnavailable(f"交易日历包含无效日期：{value}") from exc
    if not days:
        raise DataUnavailable("AKShare 交易日历没有有效日期")
    return sorted(set(days))
