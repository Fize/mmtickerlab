from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from . import RULE_VERSION
from .database import Database
from .fees import FeeConfig, fees_for_fill, maximum_buy_reserve_cents
from .market_data import QuoteProvider
from .models import (
    ConflictError,
    DataUnavailable,
    NotFoundError,
    QuoteSnapshot,
    SimTradeError,
    ValidationError,
    cents_to_yuan,
    money_to_cents,
    price_to_cents,
    rate_value,
)
from .rules import (
    after_close,
    in_continuous_session,
    normalize_code,
    validate_limit_price,
    validate_quantity,
    validate_quote_for_matching,
)
from .trading_calendar import CalendarProvider


TZ = ZoneInfo("Asia/Shanghai")
ACTIVE_STATUSES = ("OPEN", "PARTIALLY_FILLED")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _now() -> datetime:
    return datetime.now(TZ)


def _fee_config(row: sqlite3.Row) -> FeeConfig:
    return FeeConfig(Decimal(row["commission_rate"]), row["minimum_commission_cents"])


def _order_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "code": row["code"],
        "name": row["name"],
        "side": row["side"],
        "order_type": row["order_type"],
        "limit_price": cents_to_yuan(row["limit_price_cents"]),
        "quantity": row["quantity"],
        "filled_quantity": row["filled_quantity"],
        "remaining_quantity": row["quantity"] - row["filled_quantity"],
        "status": row["status"],
        "frozen_cash": cents_to_yuan(row["frozen_cash_cents"]),
        "frozen_quantity": row["frozen_quantity"],
        "reject_reason": row["reject_reason"],
        "expires_on": row["expires_on"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class TradingService:
    def __init__(self, database: Database, quotes: QuoteProvider, calendar: CalendarProvider):
        self.database = database
        self.quotes = quotes
        self.calendar = calendar
        self.database.initialize()

    def _account_row(self, connection: sqlite3.Connection, account_id: str | None, *, active: bool = True) -> sqlite3.Row:
        if account_id:
            row = connection.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"账户不存在：{account_id}")
            if active and row["status"] != "ACTIVE":
                raise ConflictError(f"账户不是 ACTIVE：{account_id}")
            return row
        rows = connection.execute("SELECT * FROM accounts WHERE status='ACTIVE' ORDER BY created_at").fetchall()
        if not rows:
            raise NotFoundError("没有 ACTIVE 模拟账户，请先创建账户")
        if len(rows) > 1:
            raise ConflictError("存在多个 ACTIVE 账户，请明确提供 --account-id")
        return rows[0]

    def create_account(
        self,
        name: str,
        cash: Any,
        *,
        commission_rate: Any = "0.00025",
        minimum_commission: Any = "5",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("账户名称不能为空")
        cash_cents = money_to_cents(cash, "初始资金", positive=True)
        rate = rate_value(commission_rate, "佣金费率")
        minimum_cents = money_to_cents(minimum_commission, "最低佣金")
        if minimum_cents < 0:
            raise ValidationError("最低佣金不能为负")
        current = now or _now()
        account_id = _id("acct")
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO accounts(
                    id,name,status,initial_cash_cents,available_cash_cents,frozen_cash_cents,
                    commission_rate,minimum_commission_cents,created_at,updated_at
                ) VALUES(?,?,'ACTIVE',?,?,0,?,?,?,?)""",
                (account_id, clean_name, cash_cents, cash_cents, str(rate), minimum_cents, current.isoformat(), current.isoformat()),
            )
            connection.execute(
                "INSERT INTO cash_ledger(id,account_id,event_type,amount_cents,balance_after_cents,created_at) VALUES(?,?,?,?,?,?)",
                (_id("cash"), account_id, "OPENING_DEPOSIT", cash_cents, cash_cents, current.isoformat()),
            )
        return self.get_account(account_id)

    def list_accounts(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM accounts ORDER BY created_at").fetchall()
        return [self._account_dict(row) for row in rows]

    def _account_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "initial_cash": cents_to_yuan(row["initial_cash_cents"]),
            "available_cash": cents_to_yuan(row["available_cash_cents"]),
            "frozen_cash": cents_to_yuan(row["frozen_cash_cents"]),
            "total_cash": cents_to_yuan(row["available_cash_cents"] + row["frozen_cash_cents"]),
            "commission_rate": row["commission_rate"],
            "minimum_commission": cents_to_yuan(row["minimum_commission_cents"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_account(self, account_id: str | None = None) -> dict[str, Any]:
        with self.database.connect() as connection:
            return self._account_dict(self._account_row(connection, account_id, active=False))

    def configure_account(
        self,
        account_id: str | None,
        *,
        commission_rate: Any | None = None,
        minimum_commission: Any | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if commission_rate is None and minimum_commission is None:
            raise ValidationError("至少提供一个佣金配置项")
        current = now or _now()
        with self.database.transaction() as connection:
            account = self._account_row(connection, account_id)
            active_orders = connection.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE account_id=? AND status IN ('OPEN','PARTIALLY_FILLED')",
                (account["id"],),
            ).fetchone()["n"]
            if active_orders:
                raise ConflictError("存在活动订单时不能修改佣金配置")
            new_rate = rate_value(commission_rate, "佣金费率") if commission_rate is not None else Decimal(account["commission_rate"])
            new_min = money_to_cents(minimum_commission, "最低佣金") if minimum_commission is not None else account["minimum_commission_cents"]
            if new_min < 0:
                raise ValidationError("最低佣金不能为负")
            connection.execute(
                "UPDATE accounts SET commission_rate=?,minimum_commission_cents=?,updated_at=? WHERE id=?",
                (str(new_rate), new_min, current.isoformat(), account["id"]),
            )
            resolved = account["id"]
        return self.get_account(resolved)

    def archive_account(self, account_id: str, *, confirmed: bool, now: datetime | None = None) -> dict[str, Any]:
        if not confirmed:
            raise ValidationError("归档账户必须显式提供 --yes")
        current = now or _now()
        with self.database.transaction() as connection:
            account = self._account_row(connection, account_id)
            count = connection.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE account_id=? AND status IN ('OPEN','PARTIALLY_FILLED')",
                (account_id,),
            ).fetchone()["n"]
            if count:
                raise ConflictError("账户仍有活动订单；请先取消订单")
            connection.execute("UPDATE accounts SET status='ARCHIVED',updated_at=? WHERE id=?", (current.isoformat(), account_id))
        return self.get_account(account_id)

    def _assert_session(self, current: datetime) -> None:
        if not self.calendar.is_trading_day(current.date()):
            raise ValidationError(f"{current.date()} 未被交易日历确认为交易日")
        if not in_continuous_session(current):
            raise ValidationError("当前不在连续竞价时段 09:30–11:30 或 13:00–15:00")

    def _free_sellable(self, connection: sqlite3.Connection, account_id: str, code: str, day: date) -> int:
        unlocked = connection.execute(
            """SELECT COALESCE(SUM(remaining_quantity),0) AS n FROM position_lots
               WHERE account_id=? AND code=? AND remaining_quantity>0 AND available_on<=?""",
            (account_id, code, day.isoformat()),
        ).fetchone()["n"]
        reserved = connection.execute(
            """SELECT COALESCE(SUM(frozen_quantity),0) AS n FROM orders
               WHERE account_id=? AND code=? AND side='SELL' AND status IN ('OPEN','PARTIALLY_FILLED')""",
            (account_id, code),
        ).fetchone()["n"]
        return int(unlocked) - int(reserved)

    def _insert_snapshot(
        self,
        connection: sqlite3.Connection,
        quote: QuoteSnapshot,
        *,
        order_id: str | None,
        purpose: str,
        current: datetime,
    ) -> str:
        snapshot_id = _id("quote")
        connection.execute(
            """INSERT INTO quote_snapshots(
                id,order_id,code,source,purpose,quote_at,fetched_at,last_cents,pre_close_cents,
                upper_limit_cents,lower_limit_cents,bids_json,asks_json,raw_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                snapshot_id,
                order_id,
                quote.code,
                quote.source,
                purpose,
                quote.quote_at.isoformat(),
                quote.fetched_at.isoformat(),
                quote.last_cents,
                quote.pre_close_cents,
                quote.upper_limit_cents,
                quote.lower_limit_cents,
                json.dumps([level.as_dict() for level in quote.bids], ensure_ascii=False),
                json.dumps([level.as_dict() for level in quote.asks], ensure_ascii=False),
                json.dumps(quote.raw, ensure_ascii=False, default=str),
                current.isoformat(),
            ),
        )
        return snapshot_id

    def _record_rejected(
        self,
        account_id: str,
        code: str,
        side: str,
        price_cents: int,
        quantity: int,
        reason: str,
        current: datetime,
        name: str = "未知",
        quote: QuoteSnapshot | None = None,
    ) -> dict[str, Any]:
        order_id = _id("ord")
        with self.database.transaction() as connection:
            self._account_row(connection, account_id)
            connection.execute(
                """INSERT INTO orders(
                    id,account_id,code,name,side,order_type,limit_price_cents,quantity,filled_quantity,status,
                    frozen_cash_cents,frozen_quantity,reject_reason,expires_on,created_at,updated_at
                ) VALUES(?,?,?,?,?,'LIMIT',?,?,0,'REJECTED',0,0,?,?,?,?)""",
                (order_id, account_id, code, name, side, price_cents, quantity, reason, current.date().isoformat(), current.isoformat(), current.isoformat()),
            )
            if quote is not None:
                self._insert_snapshot(connection, quote, order_id=order_id, purpose="REJECT", current=current)
        return self.get_order(order_id)

    def place_order(
        self,
        side: str,
        code: str,
        quantity: int,
        price: Any,
        *,
        account_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or _now()
        clean = normalize_code(code)
        normalized_side = side.upper()
        if normalized_side not in {"BUY", "SELL"}:
            raise ValidationError("side 必须是 BUY 或 SELL")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValidationError("委托数量必须是正整数")
        price_cents = price_to_cents(price, "限价")
        with self.database.connect() as connection:
            account = self._account_row(connection, account_id)
            resolved_account_id = account["id"]

        quote: QuoteSnapshot | None = None
        try:
            self._assert_session(current)
            quote = self.quotes.get_quote(clean)
            validate_quote_for_matching(quote, clean, current)
            validate_limit_price(price_cents, quote)
            with self.database.transaction() as connection:
                account = self._account_row(connection, resolved_account_id)
                free_sellable = None
                if normalized_side == "SELL":
                    free_sellable = self._free_sellable(connection, account["id"], clean, current.date())
                validate_quantity(normalized_side, quantity, free_sellable=free_sellable)
                config = _fee_config(account)
                reserve_cash = 0
                reserve_quantity = 0
                if normalized_side == "BUY":
                    reserve_cash = maximum_buy_reserve_cents(price_cents * quantity, config)
                    if account["available_cash_cents"] < reserve_cash:
                        raise ValidationError(
                            "可用资金不足",
                            details={"required": cents_to_yuan(reserve_cash), "available": cents_to_yuan(account["available_cash_cents"])},
                        )
                    connection.execute(
                        "UPDATE accounts SET available_cash_cents=available_cash_cents-?,frozen_cash_cents=frozen_cash_cents+?,updated_at=? WHERE id=?",
                        (reserve_cash, reserve_cash, current.isoformat(), account["id"]),
                    )
                else:
                    assert free_sellable is not None
                    if quantity > free_sellable:
                        raise ValidationError(
                            "可卖股份不足或股份仍受 T+1/其他卖单冻结",
                            details={"requested": quantity, "free_sellable": free_sellable},
                        )
                    reserve_quantity = quantity

                order_id = _id("ord")
                connection.execute(
                    """INSERT INTO orders(
                        id,account_id,code,name,side,order_type,limit_price_cents,quantity,filled_quantity,status,
                        frozen_cash_cents,frozen_quantity,expires_on,created_at,updated_at
                    ) VALUES(?,?,?,?,?,'LIMIT',?,?,0,'OPEN',?,?,?, ?,?)""",
                    (
                        order_id,
                        account["id"],
                        clean,
                        quote.name,
                        normalized_side,
                        price_cents,
                        quantity,
                        reserve_cash,
                        reserve_quantity,
                        current.date().isoformat(),
                        current.isoformat(),
                        current.isoformat(),
                    ),
                )
                snapshot_id = self._insert_snapshot(connection, quote, order_id=order_id, purpose="MATCH", current=current)
                self._match_order(connection, order_id, quote, snapshot_id, current)
            return self.get_order(order_id)
        except DataUnavailable:
            raise
        except (ValidationError, ConflictError) as exc:
            return self._record_rejected(
                resolved_account_id,
                clean,
                normalized_side,
                price_cents,
                quantity,
                str(exc),
                current,
                quote.name if quote else "未知",
                quote,
            )

    def _match_order(
        self,
        connection: sqlite3.Connection,
        order_id: str,
        quote: QuoteSnapshot,
        snapshot_id: str,
        current: datetime,
    ) -> None:
        order = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if order is None or order["status"] not in ACTIVE_STATUSES:
            return
        remaining = order["quantity"] - order["filled_quantity"]
        if order["side"] == "BUY":
            levels = sorted(quote.asks, key=lambda item: item.price_cents)
            executable = lambda price: price <= order["limit_price_cents"]
        else:
            levels = sorted(quote.bids, key=lambda item: item.price_cents, reverse=True)
            executable = lambda price: price >= order["limit_price_cents"]
        for level in levels:
            if remaining <= 0 or not executable(level.price_cents):
                break
            fill_quantity = min(remaining, level.quantity)
            self._apply_fill(connection, order_id, snapshot_id, level.price_cents, fill_quantity, current)
            remaining -= fill_quantity

    def _apply_fill(
        self,
        connection: sqlite3.Connection,
        order_id: str,
        snapshot_id: str,
        price_cents: int,
        quantity: int,
        current: datetime,
    ) -> None:
        order = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        account = connection.execute("SELECT * FROM accounts WHERE id=?", (order["account_id"],)).fetchone()
        totals = connection.execute(
            "SELECT COALESCE(SUM(gross_cents),0) AS gross,COALESCE(SUM(commission_cents),0) AS commission FROM fills WHERE order_id=?",
            (order_id,),
        ).fetchone()
        gross = price_cents * quantity
        fees = fees_for_fill(order["side"], gross, totals["gross"] + gross, totals["commission"], _fee_config(account))
        fill_id = _id("fill")
        disposed_cost = 0
        if order["side"] == "BUY":
            cash_effect = -(gross + fees.total_cents)
            available_on = self.calendar.next_trading_day(current.date())
            connection.execute(
                """INSERT INTO position_lots(
                    id,account_id,code,name,acquired_fill_id,acquired_on,available_on,
                    original_quantity,remaining_quantity,cost_cents,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _id("lot"), account["id"], order["code"], order["name"], fill_id,
                    current.date().isoformat(), available_on.isoformat(), quantity, quantity,
                    gross + fees.total_cents, current.isoformat(),
                ),
            )
            filled_after = order["filled_quantity"] + quantity
            remaining_after = order["quantity"] - filled_after
            future_reserve = maximum_buy_reserve_cents(
                order["limit_price_cents"] * remaining_after,
                _fee_config(account),
                prior_gross_cents=totals["gross"] + gross,
                prior_commission_cents=totals["commission"] + fees.commission_cents,
            ) if remaining_after else 0
            actual_cost = -cash_effect
            release = order["frozen_cash_cents"] - actual_cost - future_reserve
            if release < 0:
                raise ConflictError("买单冻结资金不变量被破坏，事务已回滚")
            connection.execute(
                """UPDATE accounts SET
                    available_cash_cents=available_cash_cents+?,
                    frozen_cash_cents=frozen_cash_cents-?+?,updated_at=? WHERE id=?""",
                (release, order["frozen_cash_cents"], future_reserve, current.isoformat(), account["id"]),
            )
            new_frozen_cash = future_reserve
            new_frozen_quantity = 0
        else:
            disposed_cost = self._dispose_fifo(connection, account["id"], order["code"], current.date(), quantity, fill_id)
            cash_effect = gross - fees.total_cents
            connection.execute(
                "UPDATE accounts SET available_cash_cents=available_cash_cents+?,updated_at=? WHERE id=?",
                (cash_effect, current.isoformat(), account["id"]),
            )
            new_frozen_cash = 0
            new_frozen_quantity = order["frozen_quantity"] - quantity

        realized = cash_effect - disposed_cost if order["side"] == "SELL" else 0
        connection.execute(
            """INSERT INTO fills(
                id,order_id,account_id,quote_snapshot_id,code,side,price_cents,quantity,gross_cents,
                commission_cents,transfer_fee_cents,stamp_tax_cents,net_cash_cents,disposed_cost_cents,
                realized_pnl_cents,rule_version,filled_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fill_id, order_id, account["id"], snapshot_id, order["code"], order["side"], price_cents,
                quantity, gross, fees.commission_cents, fees.transfer_fee_cents, fees.stamp_tax_cents,
                cash_effect, disposed_cost, realized, RULE_VERSION, current.isoformat(),
            ),
        )
        filled_after = order["filled_quantity"] + quantity
        status = "FILLED" if filled_after == order["quantity"] else "PARTIALLY_FILLED"
        connection.execute(
            "UPDATE orders SET filled_quantity=?,status=?,frozen_cash_cents=?,frozen_quantity=?,updated_at=? WHERE id=?",
            (filled_after, status, new_frozen_cash, new_frozen_quantity, current.isoformat(), order_id),
        )
        refreshed = connection.execute("SELECT available_cash_cents,frozen_cash_cents FROM accounts WHERE id=?", (account["id"],)).fetchone()
        connection.execute(
            """INSERT INTO cash_ledger(
                id,account_id,event_type,amount_cents,balance_after_cents,order_id,fill_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                _id("cash"), account["id"], f"{order['side']}_FILL", cash_effect,
                refreshed["available_cash_cents"] + refreshed["frozen_cash_cents"], order_id, fill_id, current.isoformat(),
            ),
        )

    def _dispose_fifo(
        self,
        connection: sqlite3.Connection,
        account_id: str,
        code: str,
        trade_day: date,
        quantity: int,
        sell_fill_id: str,
    ) -> int:
        lots = connection.execute(
            """SELECT * FROM position_lots WHERE account_id=? AND code=? AND remaining_quantity>0
               AND available_on<=? ORDER BY acquired_on,created_at,id""",
            (account_id, code, trade_day.isoformat()),
        ).fetchall()
        remaining = quantity
        total_cost = 0
        for lot in lots:
            if remaining <= 0:
                break
            used = min(remaining, lot["remaining_quantity"])
            if used == lot["remaining_quantity"]:
                cost = lot["cost_cents"]
            else:
                cost = int(
                    (Decimal(lot["cost_cents"]) * Decimal(used) / Decimal(lot["remaining_quantity"])).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
            connection.execute(
                "UPDATE position_lots SET remaining_quantity=remaining_quantity-?,cost_cents=cost_cents-? WHERE id=?",
                (used, cost, lot["id"]),
            )
            connection.execute(
                "INSERT INTO lot_disposals(id,sell_fill_id,lot_id,quantity,cost_cents) VALUES(?,?,?,?,?)",
                (_id("dispose"), sell_fill_id, lot["id"], used, cost),
            )
            total_cost += cost
            remaining -= used
        if remaining:
            raise ConflictError("可用持仓与卖出冻结不一致，事务已回滚")
        return total_cost

    def _release_order(self, connection: sqlite3.Connection, order: sqlite3.Row, status: str, current: datetime) -> None:
        if order["side"] == "BUY" and order["frozen_cash_cents"]:
            connection.execute(
                """UPDATE accounts SET available_cash_cents=available_cash_cents+?,
                   frozen_cash_cents=frozen_cash_cents-?,updated_at=? WHERE id=?""",
                (order["frozen_cash_cents"], order["frozen_cash_cents"], current.isoformat(), order["account_id"]),
            )
        connection.execute(
            "UPDATE orders SET status=?,frozen_cash_cents=0,frozen_quantity=0,updated_at=? WHERE id=?",
            (status, current.isoformat(), order["id"]),
        )

    def cancel_order(self, order_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or _now()
        with self.database.transaction() as connection:
            order = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if order is None:
                raise NotFoundError(f"订单不存在：{order_id}")
            if order["status"] not in ACTIVE_STATUSES:
                raise ConflictError(f"订单状态 {order['status']} 不能撤单")
            self._release_order(connection, order, "CANCELLED", current)
        return self.get_order(order_id)

    def _expire_due(self, connection: sqlite3.Connection, current: datetime, account_id: str | None = None) -> int:
        condition = "AND account_id=?" if account_id else ""
        params: list[Any] = [current.date().isoformat(), current.date().isoformat()]
        if account_id:
            params.append(account_id)
        rows = connection.execute(
            f"""SELECT * FROM orders WHERE status IN ('OPEN','PARTIALLY_FILLED')
                AND (expires_on<? OR (expires_on=? AND ?)) {condition}""",
            (*params[:2], 1 if after_close(current) else 0, *params[2:]),
        ).fetchall()
        for order in rows:
            self._release_order(connection, order, "EXPIRED", current)
        return len(rows)

    def process_orders(
        self,
        *,
        order_id: str | None = None,
        account_id: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        current = now or _now()
        with self.database.transaction() as connection:
            self._expire_due(connection, current, account_id)
        if after_close(current):
            return [self.get_order(order_id)] if order_id else self.list_orders(account_id=account_id)
        self._assert_session(current)
        with self.database.connect() as connection:
            if order_id:
                rows = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchall()
            else:
                account = self._account_row(connection, account_id)
                rows = connection.execute(
                    "SELECT * FROM orders WHERE account_id=? AND status IN ('OPEN','PARTIALLY_FILLED') ORDER BY created_at,id",
                    (account["id"],),
                ).fetchall()
        if order_id and not rows:
            raise NotFoundError(f"订单不存在：{order_id}")
        processed: list[str] = []
        for row in rows:
            if row["status"] not in ACTIVE_STATUSES:
                processed.append(row["id"])
                continue
            quote = self.quotes.get_quote(row["code"])
            validate_quote_for_matching(quote, row["code"], current)
            with self.database.transaction() as connection:
                fresh = connection.execute("SELECT * FROM orders WHERE id=?", (row["id"],)).fetchone()
                if fresh["status"] not in ACTIVE_STATUSES:
                    continue
                snapshot_id = self._insert_snapshot(connection, quote, order_id=row["id"], purpose="REMATCH", current=current)
                self._match_order(connection, row["id"], quote, snapshot_id, current)
            processed.append(row["id"])
        return [self.get_order(item) for item in processed]

    def get_order(self, order_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"订单不存在：{order_id}")
            result = _order_dict(row)
            fills = connection.execute("SELECT * FROM fills WHERE order_id=? ORDER BY filled_at,id", (order_id,)).fetchall()
        result["fills"] = [self._fill_dict(fill) for fill in fills]
        return result

    def list_orders(self, *, account_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            account = self._account_row(connection, account_id, active=False)
            params: list[Any] = [account["id"]]
            condition = ""
            if status:
                condition = " AND status=?"
                params.append(status.upper())
            rows = connection.execute(
                f"SELECT * FROM orders WHERE account_id=?{condition} ORDER BY created_at DESC,id DESC", params
            ).fetchall()
        return [_order_dict(row) for row in rows]

    def _fill_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "order_id": row["order_id"],
            "code": row["code"],
            "side": row["side"],
            "price": cents_to_yuan(row["price_cents"]),
            "quantity": row["quantity"],
            "gross": cents_to_yuan(row["gross_cents"]),
            "commission": cents_to_yuan(row["commission_cents"]),
            "transfer_fee": cents_to_yuan(row["transfer_fee_cents"]),
            "stamp_tax": cents_to_yuan(row["stamp_tax_cents"]),
            "net_cash_effect": cents_to_yuan(row["net_cash_cents"]),
            "disposed_cost": cents_to_yuan(row["disposed_cost_cents"]),
            "realized_pnl": cents_to_yuan(row["realized_pnl_cents"]),
            "rule_version": row["rule_version"],
            "filled_at": row["filled_at"],
        }

    def history(self, *, account_id: str | None = None, code: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0 or limit > 1000:
            raise ValidationError("limit 必须在 1 到 1000 之间")
        with self.database.connect() as connection:
            account = self._account_row(connection, account_id, active=False)
            params: list[Any] = [account["id"]]
            condition = ""
            if code:
                condition = " AND code=?"
                params.append(normalize_code(code))
            params.append(limit)
            rows = connection.execute(
                f"SELECT * FROM fills WHERE account_id=?{condition} ORDER BY filled_at DESC,id DESC LIMIT ?", params
            ).fetchall()
        return [self._fill_dict(row) for row in rows]

    def portfolio(self, *, account_id: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        current = now or _now()
        with self.database.connect() as connection:
            account = self._account_row(connection, account_id, active=False)
            rows = connection.execute(
                """SELECT code,MAX(name) AS name,SUM(remaining_quantity) AS shares,SUM(cost_cents) AS cost_cents,
                   SUM(CASE WHEN available_on<=? THEN remaining_quantity ELSE 0 END) AS unlocked
                   FROM position_lots WHERE account_id=? AND remaining_quantity>0 GROUP BY code ORDER BY code""",
                (current.date().isoformat(), account["id"]),
            ).fetchall()
            reservations = {
                row["code"]: row["n"]
                for row in connection.execute(
                    """SELECT code,SUM(frozen_quantity) AS n FROM orders WHERE account_id=?
                       AND side='SELL' AND status IN ('OPEN','PARTIALLY_FILLED') GROUP BY code""",
                    (account["id"],),
                ).fetchall()
            }
            realized = connection.execute(
                "SELECT COALESCE(SUM(realized_pnl_cents),0) AS n FROM fills WHERE account_id=? AND side='SELL'",
                (account["id"],),
            ).fetchone()["n"]
        expected_day = self.calendar.latest_trading_day(current.date())
        positions: list[dict[str, Any]] = []
        all_valued = True
        market_total = 0
        cost_total = 0
        for row in rows:
            cost_total += row["cost_cents"]
            item: dict[str, Any] = {
                "code": row["code"],
                "name": row["name"],
                "shares": row["shares"],
                "available_shares": max(0, row["unlocked"] - reservations.get(row["code"], 0)),
                "frozen_sell_shares": reservations.get(row["code"], 0),
                "cost": cents_to_yuan(row["cost_cents"]),
                "average_cost": cents_to_yuan(int(Decimal(row["cost_cents"]) / Decimal(row["shares"]))) if row["shares"] else None,
            }
            try:
                quote = self.quotes.get_quote(row["code"])
                issues = []
                if quote.code != row["code"] or quote.last_cents <= 0:
                    issues.append("证券身份或最新价无效")
                if quote.quote_at.date() != expected_day:
                    issues.append(f"行情日期 {quote.quote_at.date()} 不是最近交易日 {expected_day}")
                if self.calendar.is_trading_day(current.date()) and in_continuous_session(current):
                    age = (current - quote.quote_at).total_seconds()
                    if age > 30 or age < -5:
                        issues.append("交易时段估值行情不够新鲜")
                if issues:
                    raise DataUnavailable("；".join(issues))
                market_value = quote.last_cents * row["shares"]
                market_total += market_value
                item.update(
                    valuation_status="AVAILABLE",
                    quote_at=quote.quote_at.isoformat(),
                    last=cents_to_yuan(quote.last_cents),
                    market_value=cents_to_yuan(market_value),
                    unrealized_pnl=cents_to_yuan(market_value - row["cost_cents"]),
                )
                with self.database.transaction() as connection:
                    self._insert_snapshot(connection, quote, order_id=None, purpose="VALUATION", current=current)
            except SimTradeError as exc:
                all_valued = False
                item.update(
                    valuation_status="UNAVAILABLE",
                    valuation_error=str(exc),
                    quote_at=None,
                    last=None,
                    market_value=None,
                    unrealized_pnl=None,
                )
            positions.append(item)
        total_cash = account["available_cash_cents"] + account["frozen_cash_cents"]
        total_assets = total_cash + market_total if all_valued else None
        return {
            "account": self._account_dict(account),
            "as_of": current.isoformat(),
            "valuation_status": "AVAILABLE" if all_valued else "INCOMPLETE",
            "positions": positions,
            "position_cost": cents_to_yuan(cost_total),
            "market_value": cents_to_yuan(market_total) if all_valued else None,
            "total_assets": cents_to_yuan(total_assets) if total_assets is not None else None,
            "realized_pnl": cents_to_yuan(realized),
            "total_pnl": cents_to_yuan(total_assets - account["initial_cash_cents"]) if total_assets is not None else None,
        }

    def audit(self, *, account_id: str | None = None) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        with self.database.connect() as connection:
            account = self._account_row(connection, account_id, active=False)
            total_cash = account["available_cash_cents"] + account["frozen_cash_cents"]
            ledger = connection.execute(
                "SELECT COALESCE(SUM(amount_cents),0) AS summed,MAX(rowid) AS last_rowid FROM cash_ledger WHERE account_id=?",
                (account["id"],),
            ).fetchone()
            last = connection.execute(
                "SELECT balance_after_cents FROM cash_ledger WHERE account_id=? ORDER BY rowid DESC LIMIT 1",
                (account["id"],),
            ).fetchone()
            frozen_orders = connection.execute(
                "SELECT COALESCE(SUM(frozen_cash_cents),0) AS n FROM orders WHERE account_id=? AND status IN ('OPEN','PARTIALLY_FILLED')",
                (account["id"],),
            ).fetchone()["n"]
            mismatched_orders = connection.execute(
                """SELECT COUNT(*) AS n FROM orders o WHERE account_id=? AND filled_quantity !=
                   (SELECT COALESCE(SUM(quantity),0) FROM fills f WHERE f.order_id=o.id)""",
                (account["id"],),
            ).fetchone()["n"]
            sell_reservations = connection.execute(
                """SELECT o.code,SUM(o.frozen_quantity) AS reserved,
                   (SELECT COALESCE(SUM(l.remaining_quantity),0) FROM position_lots l
                    WHERE l.account_id=o.account_id AND l.code=o.code) AS held
                   FROM orders o WHERE o.account_id=? AND o.status IN ('OPEN','PARTIALLY_FILLED') AND o.side='SELL'
                   GROUP BY o.code""",
                (account["id"],),
            ).fetchall()

        checks.append({"name": "ledger_sum_equals_total_cash", "passed": ledger["summed"] == total_cash, "expected": total_cash, "actual": ledger["summed"]})
        checks.append({"name": "ledger_tail_equals_total_cash", "passed": bool(last) and last["balance_after_cents"] == total_cash, "expected": total_cash, "actual": last["balance_after_cents"] if last else None})
        checks.append({"name": "buy_order_freeze_equals_account_freeze", "passed": frozen_orders == account["frozen_cash_cents"], "expected": account["frozen_cash_cents"], "actual": frozen_orders})
        checks.append({"name": "order_fill_quantities_reconcile", "passed": mismatched_orders == 0, "mismatches": mismatched_orders})
        invalid_sell = [dict(row) for row in sell_reservations if row["reserved"] > row["held"]]
        checks.append({"name": "sell_reservations_backed_by_positions", "passed": not invalid_sell, "invalid": invalid_sell})
        return {"account_id": account["id"], "passed": all(check["passed"] for check in checks), "checks": checks}
