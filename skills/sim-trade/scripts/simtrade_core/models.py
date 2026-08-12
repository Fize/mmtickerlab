from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


SHANGHAI_TZ = "Asia/Shanghai"
CENT = Decimal("0.01")


class SimTradeError(Exception):
    """Base error with a stable machine-readable code."""

    code = "SIM_TRADE_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


class ValidationError(SimTradeError):
    code = "VALIDATION_ERROR"


class DataUnavailable(SimTradeError):
    code = "DATA_UNAVAILABLE"


class NotFoundError(SimTradeError):
    code = "NOT_FOUND"


class ConflictError(SimTradeError):
    code = "CONFLICT"


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"{field} 必须是有效数字") from exc
    if not result.is_finite():
        raise ValidationError(f"{field} 必须是有限数字")
    return result


def money_to_cents(value: Any, field: str = "金额", *, positive: bool = False) -> int:
    amount = decimal_value(value, field).quantize(CENT, rounding=ROUND_HALF_UP)
    if positive and amount <= 0:
        raise ValidationError(f"{field} 必须大于 0")
    return int(amount * 100)


def price_to_cents(value: Any, field: str = "价格") -> int:
    raw = decimal_value(value, field)
    if raw <= 0:
        raise ValidationError(f"{field} 必须大于 0")
    rounded = raw.quantize(CENT, rounding=ROUND_HALF_UP)
    if raw != rounded:
        raise ValidationError(f"{field} 必须符合 ¥0.01 最小价格变动单位")
    return int(rounded * 100)


def cents_to_yuan(cents: int) -> str:
    return f"{(Decimal(cents) / 100).quantize(CENT):.2f}"


def rate_value(value: Any, field: str = "费率") -> Decimal:
    rate = decimal_value(value, field)
    if rate < 0 or rate >= 1:
        raise ValidationError(f"{field} 必须在 0（含）到 1（不含）之间")
    return rate


@dataclass(frozen=True)
class BookLevel:
    price_cents: int
    quantity: int

    def as_dict(self) -> dict[str, Any]:
        return {"price": cents_to_yuan(self.price_cents), "quantity": self.quantity}


@dataclass(frozen=True)
class QuoteSnapshot:
    code: str
    name: str
    exchange: str
    source: str
    quote_at: datetime
    fetched_at: datetime
    last_cents: int
    pre_close_cents: int
    upper_limit_cents: int | None
    lower_limit_cents: int | None
    listing_date: date | None
    status: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    raw: dict[str, Any]

    def schema_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.code or len(self.code) != 6 or not self.code.isdigit():
            issues.append("证券代码无效")
        if not self.name.strip():
            issues.append("证券名称缺失")
        if self.exchange not in {"SH", "SZ", "BJ"}:
            issues.append("交易所无效")
        if not self.source:
            issues.append("行情来源缺失")
        if self.quote_at.tzinfo is None:
            issues.append("行情时间缺少时区")
        if self.last_cents <= 0:
            issues.append("最新价缺失或非正数")
        if self.pre_close_cents <= 0:
            issues.append("昨收缺失或非正数")
        if not self.upper_limit_cents or not self.lower_limit_cents:
            issues.append("提供方未给出明确涨跌停价")
        elif self.lower_limit_cents >= self.upper_limit_cents:
            issues.append("涨跌停价关系无效")
        if self.listing_date is None:
            issues.append("上市日期缺失")
        for side, levels in (("买盘", self.bids), ("卖盘", self.asks)):
            if len(levels) > 5:
                issues.append(f"{side}超过五档")
            if any(level.price_cents <= 0 or level.quantity <= 0 for level in levels):
                issues.append(f"{side}包含无效价量")
        return issues

    def as_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        result = {
            "code": self.code,
            "name": self.name,
            "exchange": self.exchange,
            "source": self.source,
            "quote_at": self.quote_at.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "last": cents_to_yuan(self.last_cents),
            "pre_close": cents_to_yuan(self.pre_close_cents),
            "upper_limit": cents_to_yuan(self.upper_limit_cents) if self.upper_limit_cents else None,
            "lower_limit": cents_to_yuan(self.lower_limit_cents) if self.lower_limit_cents else None,
            "listing_date": self.listing_date.isoformat() if self.listing_date else None,
            "status": self.status,
            "bids": [level.as_dict() for level in self.bids],
            "asks": [level.as_dict() for level in self.asks],
            "schema_issues": self.schema_issues(),
        }
        if include_raw:
            result["raw"] = self.raw
        return result
