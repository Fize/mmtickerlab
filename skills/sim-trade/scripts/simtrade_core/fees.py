from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


TRANSFER_RATE = Decimal("0.00001")
STAMP_TAX_RATE = Decimal("0.0005")


def _fee_cents(gross_cents: int, rate: Decimal) -> int:
    return int((Decimal(gross_cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class FeeConfig:
    commission_rate: Decimal
    minimum_commission_cents: int


@dataclass(frozen=True)
class FillFees:
    commission_cents: int
    transfer_fee_cents: int
    stamp_tax_cents: int

    @property
    def total_cents(self) -> int:
        return self.commission_cents + self.transfer_fee_cents + self.stamp_tax_cents


def cumulative_commission_cents(gross_cents: int, config: FeeConfig) -> int:
    if gross_cents <= 0:
        return 0
    return max(config.minimum_commission_cents, _fee_cents(gross_cents, config.commission_rate))


def fees_for_fill(
    side: str,
    fill_gross_cents: int,
    cumulative_gross_after_cents: int,
    commission_already_cents: int,
    config: FeeConfig,
) -> FillFees:
    target_commission = cumulative_commission_cents(cumulative_gross_after_cents, config)
    commission = max(0, target_commission - commission_already_cents)
    transfer = _fee_cents(fill_gross_cents, TRANSFER_RATE)
    stamp = _fee_cents(fill_gross_cents, STAMP_TAX_RATE) if side == "SELL" else 0
    return FillFees(commission, transfer, stamp)


def maximum_buy_reserve_cents(gross_cents: int, config: FeeConfig, *, prior_gross_cents: int = 0, prior_commission_cents: int = 0) -> int:
    commission = cumulative_commission_cents(prior_gross_cents + gross_cents, config) - prior_commission_cents
    return gross_cents + max(0, commission) + _fee_cents(gross_cents, TRANSFER_RATE)
