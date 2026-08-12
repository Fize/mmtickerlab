from __future__ import annotations

import re
from datetime import datetime, time

from .models import QuoteSnapshot, ValidationError


_CODE = re.compile(r"^\d{6}$")
_SH_PREFIXES = ("600", "601", "603", "605", "688", "689")
_SZ_PREFIXES = ("000", "001", "002", "003", "300", "301")
_BJ_PREFIXES = ("4", "8", "920")


def normalize_code(value: str) -> str:
    clean = str(value).strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if clean.startswith(prefix):
            clean = clean[2:]
        if clean.endswith(f".{prefix}"):
            clean = clean[:-3]
    if not _CODE.fullmatch(clean):
        raise ValidationError(f"证券代码必须是受支持的六位 A 股代码：{value}")
    exchange_for_code(clean)
    return clean


def exchange_for_code(code: str) -> str:
    if code.startswith(_SH_PREFIXES):
        return "SH"
    if code.startswith(_SZ_PREFIXES):
        return "SZ"
    if code.startswith(_BJ_PREFIXES):
        return "BJ"
    raise ValidationError(f"不支持的证券代码范围：{code}")


def in_continuous_session(now: datetime) -> bool:
    current = now.timetz().replace(tzinfo=None)
    return time(9, 30) <= current <= time(11, 30) or time(13, 0) <= current <= time(15, 0)


def after_close(now: datetime) -> bool:
    return now.timetz().replace(tzinfo=None) > time(15, 0)


def validate_limit_price(price_cents: int, quote: QuoteSnapshot) -> None:
    if price_cents <= 0:
        raise ValidationError("限价必须大于 0")
    if quote.lower_limit_cents is None or quote.upper_limit_cents is None:
        raise ValidationError("缺少提供方明确涨跌停价，禁止委托")
    if not quote.lower_limit_cents <= price_cents <= quote.upper_limit_cents:
        raise ValidationError(
            "限价超出当日涨跌停范围",
            details={
                "lower_limit_cents": quote.lower_limit_cents,
                "upper_limit_cents": quote.upper_limit_cents,
                "price_cents": price_cents,
            },
        )


def validate_quantity(side: str, quantity: int, *, free_sellable: int | None = None) -> None:
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError("委托数量必须是正整数")
    if side == "BUY" and quantity % 100 != 0:
        raise ValidationError("买入数量必须是 100 股的整数倍")
    if side == "SELL" and quantity % 100 != 0 and quantity != free_sellable:
        raise ValidationError("零股卖出必须一次卖出当前全部可用零股")


def validate_quote_for_matching(quote: QuoteSnapshot, code: str, now: datetime, max_age_seconds: int = 30) -> None:
    issues = quote.schema_issues()
    if quote.code != code:
        issues.append(f"行情代码 {quote.code} 与委托代码 {code} 不一致")
    if quote.exchange != exchange_for_code(code):
        issues.append("行情交易所与代码不一致")
    if quote.status != "TRADING":
        issues.append(f"证券状态不是 TRADING：{quote.status}")
    if not quote.bids and not quote.asks:
        issues.append("五档盘口两侧均为空")
    if quote.quote_at.date() != now.date():
        issues.append("行情日期不是当前委托日期")
    age = (now - quote.quote_at).total_seconds()
    if age > max_age_seconds:
        issues.append(f"行情已过期 {age:.1f} 秒")
    if age < -5:
        issues.append(f"行情时间超前 {-age:.1f} 秒")
    if issues:
        from .models import DataUnavailable

        raise DataUnavailable("行情数据不足，禁止撮合", details={"issues": issues})
