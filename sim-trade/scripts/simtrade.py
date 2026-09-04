#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from simtrade_core.database import Database
from simtrade_core.market_data import EastMoneyQuoteProvider
from simtrade_core.models import SimTradeError
from simtrade_core.rules import in_continuous_session, validate_quote_for_matching
from simtrade_core.service import TradingService
from simtrade_core.trading_calendar import TradingCalendar


TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_DB = SCRIPT_DIR.parent / "data" / "simulation.db"
REQUIREMENTS_FILE = SCRIPT_DIR.parent / "requirements.txt"


def _account_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--account-id", help="明确指定模拟账户 ID")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="严格行情门禁和可审计账本驱动的 A 股模拟交易系统")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 数据库路径（默认使用 skill 本地数据库）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="检查环境、交易日历和实时行情数据完整性")
    doctor.add_argument("--code", default="600519")

    quote = commands.add_parser("quote", help="查看严格解析后的五档行情")
    quote.add_argument("code")

    account = commands.add_parser("account", help="账户管理")
    account_commands = account.add_subparsers(dest="account_command", required=True)
    create = account_commands.add_parser("create", help="创建新账户")
    create.add_argument("--name", required=True)
    create.add_argument("--cash", required=True)
    create.add_argument("--commission-rate", default="0.00025")
    create.add_argument("--minimum-commission", default="5")
    account_commands.add_parser("list", help="列出账户")
    show = account_commands.add_parser("show", help="查看账户")
    _account_arg(show)
    configure = account_commands.add_parser("configure", help="修改无活动订单账户的佣金参数")
    _account_arg(configure)
    configure.add_argument("--commission-rate")
    configure.add_argument("--minimum-commission")
    archive = account_commands.add_parser("archive", help="归档账户并保留全部账本")
    archive.add_argument("--account-id", required=True)
    archive.add_argument("--yes", action="store_true")

    order = commands.add_parser("order", help="限价订单管理")
    order_commands = order.add_subparsers(dest="order_command", required=True)
    for side in ("buy", "sell"):
        place = order_commands.add_parser(side, help=f"{side.upper()} 限价委托")
        place.add_argument("code")
        place.add_argument("shares", type=int)
        place.add_argument("--price", required=True)
        _account_arg(place)
    order_list = order_commands.add_parser("list", help="列出订单")
    _account_arg(order_list)
    order_list.add_argument("--status")
    order_show = order_commands.add_parser("show", help="查看订单和成交")
    order_show.add_argument("order_id")
    cancel = order_commands.add_parser("cancel", help="撤销活动订单")
    cancel.add_argument("order_id")
    process = order_commands.add_parser("process", help="用新行情处理活动订单")
    process.add_argument("--order-id")
    _account_arg(process)

    portfolio = commands.add_parser("portfolio", help="查看持仓和严格估值")
    _account_arg(portfolio)
    history = commands.add_parser("history", help="查看成交历史")
    _account_arg(history)
    history.add_argument("--code")
    history.add_argument("--limit", type=int, default=100)
    audit = commands.add_parser("audit", help="核对资金、冻结、订单和持仓不变量")
    _account_arg(audit)
    return parser


def _components(db_path: str) -> tuple[TradingService, EastMoneyQuoteProvider, TradingCalendar]:
    database = Database(db_path)
    quotes = EastMoneyQuoteProvider()
    calendar = TradingCalendar(database)
    return TradingService(database, quotes, calendar), quotes, calendar


def _doctor(db_path: str, code: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    service, quotes, calendar = _components(db_path)
    checks.append({"name": "sqlite_database", "passed": True, "path": str(service.database.path)})
    versions: dict[str, str] = {}
    expected_versions = {
        name.strip(): version.strip()
        for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "==" in line
        for name, version in [line.split("==", 1)]
    }
    for package in expected_versions:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "MISSING"
    mismatches = {
        package: {"expected": expected, "actual": versions[package]}
        for package, expected in expected_versions.items()
        if versions[package] != expected
    }
    checks.append({"name": "pinned_dependencies_installed", "passed": not mismatches,
                   "versions": versions, "expected_versions": expected_versions,
                   "mismatches": mismatches})
    current = datetime.now(TZ)
    try:
        is_open_day = calendar.is_trading_day(current.date())
        next_day = calendar.next_trading_day(current.date())
        checks.append({"name": "trading_calendar", "passed": True, "today_is_trading_day": is_open_day, "next_trading_day": next_day.isoformat()})
    except SimTradeError as exc:
        is_open_day = False
        checks.append({"name": "trading_calendar", "passed": False, "error": str(exc)})
    try:
        quote = quotes.get_quote(code)
        issues = quote.schema_issues()
        checks.append({"name": "quote_schema", "passed": not issues, "issues": issues, "quote": quote.as_dict()})
        matching_ready = False
        matching_error = None
        try:
            if not is_open_day or not in_continuous_session(current):
                raise RuntimeError("当前不是已确认的连续竞价时段")
            validate_quote_for_matching(quote, quote.code, current)
            matching_ready = True
        except Exception as exc:
            matching_error = str(exc)
        checks.append({"name": "matching_ready_now", "passed": matching_ready, "error": matching_error})
    except SimTradeError as exc:
        checks.append({"name": "quote_schema", "passed": False, "error": str(exc), "details": exc.details})
        checks.append({"name": "matching_ready_now", "passed": False, "error": "没有合格行情"})
    return {
        "ready": all(check["passed"] for check in checks),
        "checked_at": current.isoformat(),
        "checks": checks,
        "note": "matching_ready_now 在非交易时段失败是预期行为；此时禁止下单和撮合。",
    }


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "doctor":
        return _doctor(args.db, args.code)
    service, quotes, _calendar = _components(args.db)
    if args.command == "quote":
        return quotes.get_quote(args.code).as_dict(include_raw=True)
    if args.command == "account":
        if args.account_command == "create":
            return service.create_account(
                args.name,
                args.cash,
                commission_rate=args.commission_rate,
                minimum_commission=args.minimum_commission,
            )
        if args.account_command == "list":
            return service.list_accounts()
        if args.account_command == "show":
            return service.get_account(args.account_id)
        if args.account_command == "configure":
            return service.configure_account(
                args.account_id,
                commission_rate=args.commission_rate,
                minimum_commission=args.minimum_commission,
            )
        if args.account_command == "archive":
            return service.archive_account(args.account_id, confirmed=args.yes)
    if args.command == "order":
        if args.order_command in {"buy", "sell"}:
            return service.place_order(
                args.order_command.upper(),
                args.code,
                args.shares,
                args.price,
                account_id=args.account_id,
            )
        if args.order_command == "list":
            return service.list_orders(account_id=args.account_id, status=args.status)
        if args.order_command == "show":
            return service.get_order(args.order_id)
        if args.order_command == "cancel":
            return service.cancel_order(args.order_id)
        if args.order_command == "process":
            return service.process_orders(order_id=args.order_id, account_id=args.account_id)
    if args.command == "portfolio":
        return service.portfolio(account_id=args.account_id)
    if args.command == "history":
        return service.history(account_id=args.account_id, code=args.code, limit=args.limit)
    if args.command == "audit":
        return service.audit(account_id=args.account_id)
    raise RuntimeError("未处理的命令")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2, sort_keys=False))
        return 0
    except SimTradeError as exc:
        error = {"error": {"code": exc.code, "message": str(exc), "details": exc.details}}
        print(json.dumps(error, ensure_ascii=False, indent=None if args.json else 2), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"error": {"code": "INTERRUPTED", "message": "操作已中断"}}, ensure_ascii=False), file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
