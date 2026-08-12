#!/usr/bin/env python3
"""Strict AKShare adapters for plan-review reports.

Every command emits one JSON document to stdout and exits non-zero when the
requested dataset cannot be proven complete.  Human-readable diagnostics go to
stderr so callers never have to parse mixed output.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

# This import order is mandatory.  See repository AGENTS.md.
import akshare_patch  # noqa: F401
import akshare as ak
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "report_snapshots"
SH_TZ = ZoneInfo("Asia/Shanghai")
NY_TZ = ZoneInfo("America/New_York")
INDEXES = {
    "000001": ("上证指数", "1.000001"),
    "399001": ("深证成指", "0.399001"),
    "399006": ("创业板指", "0.399006"),
    "000300": ("沪深300", "1.000300"),
    "000016": ("上证50", "1.000016"),
    "000905": ("中证500", "1.000905"),
    "000852": ("中证1000", "1.000852"),
}


class DataError(RuntimeError):
    pass


def now_shanghai() -> datetime:
    return datetime.now(SH_TZ)


def parse_day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise DataError(f"日期必须为 YYYYMMDD：{value}") from exc


def day_key(value: date) -> str:
    return value.strftime("%Y%m%d")


def clean_number(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): clean_number(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def ak_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Keep library progress/retry chatter away from JSON stdout."""
    with contextlib.redirect_stdout(sys.stderr):
        return fn(*args, **kwargs)


def envelope(dataset: str, target: date, source: str, payload: dict[str, Any],
             checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [item for item in checks if not item["passed"]]
    if failed:
        messages = "；".join(str(item["detail"]) for item in failed)
        raise DataError(f"{dataset} 数据校验失败：{messages}")
    return {
        "schema_version": 1,
        "dataset": dataset,
        "target_date": day_key(target),
        "source": source,
        "retrieved_at": now_shanghai().isoformat(timespec="seconds"),
        "status": "ready",
        "checks": checks,
        "data": payload,
    }


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def require_trading_day(target: date) -> dict[str, Any]:
    frame = ak_call(ak.tool_trade_date_hist_sina)
    if "trade_date" not in frame.columns:
        raise DataError("交易日历缺少 trade_date 字段")
    days = set(pd.to_datetime(frame["trade_date"]).dt.date)
    if target not in days:
        raise DataError(f"{target} 不是交易日，禁止采集交易阶段快照")
    return check("trading_day", True, f"{target} 已在交易日历中确认")


def write_json(document: dict[str, Any], output: str | None) -> None:
    encoded = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    if not output:
        print(encoded)
        return
    path = Path(output)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    os.replace(temporary, path)
    print(json.dumps({"status": "ready", "path": str(path)}, ensure_ascii=False))


def calendar_dataset(target: date, count: int) -> dict[str, Any]:
    frame = ak_call(ak.tool_trade_date_hist_sina)
    if "trade_date" not in frame.columns:
        raise DataError("交易日历缺少 trade_date 字段")
    days = sorted(pd.to_datetime(frame["trade_date"]).dt.date.unique())
    prior = [item for item in days if item <= target]
    previous = [item for item in days if item < target]
    next_days = [item for item in days if item > target]
    is_trade = target in set(days)
    selected = prior[-count:]
    payload = {
        "is_trading_day": is_trade,
        "previous_trading_day": day_key(previous[-1]) if previous else None,
        "next_trading_day": day_key(next_days[0]) if next_days else None,
        "last_trading_days": [day_key(item) for item in selected],
        "calendar_start": day_key(days[0]),
        "calendar_end": day_key(days[-1]),
    }
    checks = [
        check("schema", bool(days), f"共 {len(days)} 个交易日"),
        check("coverage", days[0] <= target <= days[-1],
              f"覆盖 {days[0]} 至 {days[-1]}，目标 {target}"),
        check("history_length", len(selected) == count,
              f"要求 {count} 个，取得 {len(selected)} 个"),
    ]
    return envelope("trading_calendar", target, "AKShare.tool_trade_date_hist_sina", payload, checks)


def _eastmoney_index_frame(code: str, start: date, end: date) -> pd.DataFrame:
    if code not in INDEXES:
        raise DataError(f"不支持的指数代码：{code}")
    _, secid = INDEXES[code]
    with contextlib.redirect_stdout(sys.stderr):
        response = requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
            "secid": secid,
            "klt": "101",
            "fqt": "0",
            "beg": day_key(start),
            "end": day_key(end),
            "lmt": "1000",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            },
            timeout=30,
        )
    body = response.json()
    klines = (body.get("data") or {}).get("klines") or []
    rows = []
    for item in klines:
        parts = item.split(",")
        if len(parts) < 11:
            continue
        rows.append({
            "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
            "high": float(parts[3]), "low": float(parts[4]), "volume": float(parts[5]),
            "turnover": float(parts[6]), "amplitude_pct": float(parts[7]),
            "change_pct": float(parts[8]), "change": float(parts[9]),
            "turnover_rate_pct": float(parts[10]),
        })
    return pd.DataFrame(rows)


def indices_dataset(target: date, count: int) -> dict[str, Any]:
    start = date(target.year - 2, 1, 1)
    result: dict[str, Any] = {}
    latest_dates: list[str] = []
    for code, (name, _) in INDEXES.items():
        frame = _eastmoney_index_frame(code, start, target)
        if frame.empty:
            raise DataError(f"指数 {code} 无数据")
        frame = frame[frame["date"] <= target.isoformat()].tail(count)
        if len(frame) < count:
            raise DataError(f"指数 {code} 仅有 {len(frame)} 条，要求 {count} 条")
        latest_dates.append(str(frame.iloc[-1]["date"]))
        result[code] = {"name": name, "rows": records(frame)}
    expected = target.isoformat()
    checks = [
        check("all_indices", len(result) == len(INDEXES),
              f"要求 {len(INDEXES)} 个，取得 {len(result)} 个"),
        check("same_latest_date", set(latest_dates) == {expected},
              f"各指数末日 {sorted(set(latest_dates))}，目标 {expected}"),
        check("history_length", all(len(item["rows"]) == count for item in result.values()),
              f"每个指数要求 {count} 条"),
    ]
    return envelope("index_history", target,
                    "Eastmoney push2his fixed secid via AKShare transport", {"indices": result}, checks)


def _session_allowed(target: date, session: str, now: datetime) -> tuple[bool, str]:
    if target != now.date():
        return False, "实时全市场接口不能重建历史截面"
    local_time = now.time().replace(tzinfo=None)
    if session == "noon":
        allowed = time(11, 30) <= local_time < time(13, 0)
        return allowed, f"午间快照仅允许 11:30-13:00，当前 {local_time:%H:%M:%S}"
    allowed = local_time >= time(15, 5)
    return allowed, f"收盘快照仅允许 15:05 后，当前 {local_time:%H:%M:%S}"


def snapshot_dataset(target: date, session: str) -> dict[str, Any]:
    now = now_shanghai()
    trading_day_check = require_trading_day(target)
    allowed, detail = _session_allowed(target, session, now)
    if not allowed:
        raise DataError(detail)
    spot = ak_call(ak.stock_zh_a_spot)
    master = ak_call(ak.stock_info_a_code_name)
    required = {"代码", "名称", "最新价", "涨跌幅", "成交额", "时间戳"}
    missing = sorted(required - set(spot.columns))
    if missing:
        raise DataError(f"全市场快照缺少字段：{missing}")
    work = spot.copy()
    work["plain_code"] = work["代码"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True)
    work["涨跌幅"] = pd.to_numeric(work["涨跌幅"], errors="coerce")
    work["成交额"] = pd.to_numeric(work["成交额"], errors="coerce")
    valid = work.dropna(subset=["plain_code", "名称", "最新价", "涨跌幅", "成交额"])
    master_count = master["code"].astype(str).nunique() if "code" in master.columns else 0
    coverage = valid["plain_code"].nunique() / master_count if master_count else 0
    latest_stamp = str(valid["时间戳"].dropna().max()) if not valid.empty else ""
    metrics = {
        "security_count": int(valid["plain_code"].nunique()),
        "master_count": int(master_count),
        "coverage_ratio": round(coverage, 6),
        "up_count": int((valid["涨跌幅"] > 0).sum()),
        "down_count": int((valid["涨跌幅"] < 0).sum()),
        "flat_count": int((valid["涨跌幅"] == 0).sum()),
        "total_turnover_yuan": float(valid["成交额"].sum()),
        "median_change_pct": float(valid["涨跌幅"].median()),
        "rise_over_5pct": int((valid["涨跌幅"] >= 5).sum()),
        "fall_over_5pct": int((valid["涨跌幅"] <= -5).sum()),
        "latest_source_timestamp": latest_stamp,
    }
    try:
        source_clock = datetime.strptime(latest_stamp[-8:], "%H:%M:%S").time()
    except ValueError:
        source_clock = None
    clock_ok = bool(source_clock and (
        source_clock >= time(14, 50)
        if session == "close"
        else time(11, 25) <= source_clock <= time(12, 59, 59)
    ))
    checks = [
        trading_day_check,
        check("session_window", allowed, detail),
        check("schema", not missing, f"必需字段完整；{len(valid)} 条有效记录"),
        check("coverage", coverage >= 0.98,
              f"有效 {metrics['security_count']} / 主表 {master_count} = {coverage:.2%}"),
        check("unique_codes", valid["plain_code"].nunique() == len(valid),
              "证券代码必须唯一"),
        check("source_clock", clock_ok,
              f"源时间 {latest_stamp} 与 {session} 阶段匹配；日期由当日采集门禁保证"),
    ]
    document = envelope(f"market_snapshot_{session}", target,
                        "AKShare.stock_zh_a_spot + stock_info_a_code_name",
                        {"session": session, "metrics": metrics}, checks)
    default_path = DATA_DIR / day_key(target) / f"market_{session}.json"
    default_path.parent.mkdir(parents=True, exist_ok=True)
    temp = default_path.with_suffix(".tmp")
    temp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, default_path)
    document["snapshot_path"] = str(default_path)
    return document


def limits_dataset(target: date) -> dict[str, Any]:
    trading_day_check = require_trading_day(target)
    age = (now_shanghai().date() - target).days
    if age < 0 or age > 30:
        raise DataError("涨跌停池仅用于最近 30 个自然日，禁止把接口空值解释为更早历史日的零记录")
    key = day_key(target)
    closed = ak_call(ak.stock_zt_pool_em, date=key)
    broken = ak_call(ak.stock_zt_pool_zbgc_em, date=key)
    down = ak_call(ak.stock_zt_pool_dtgc_em, date=key)
    closed_required = {"代码", "名称", "涨跌幅", "连板数", "炸板次数", "所属行业"}
    broken_required = {"代码", "名称", "最新价", "涨停价"}
    failed = broken.copy()
    if not failed.empty and broken_required <= set(failed.columns):
        failed["最新价"] = pd.to_numeric(failed["最新价"], errors="coerce")
        failed["涨停价"] = pd.to_numeric(failed["涨停价"], errors="coerce")
        failed = failed[failed["最新价"] < failed["涨停价"] - 0.001]
    closed_count = len(closed)
    failed_count = len(failed)
    touched = closed_count + failed_count
    metrics = {
        "closed_limit_up": closed_count,
        "failed_limit_up": failed_count,
        "limit_down": len(down),
        "touched_limit_up": touched,
        "failure_rate": round(failed_count / touched, 6) if touched else 0,
        "max_streak": int(pd.to_numeric(closed.get("连板数", pd.Series(dtype=float)), errors="coerce").max())
        if closed_count else 0,
        "reclosed_count": int((pd.to_numeric(closed.get("炸板次数", pd.Series(dtype=float)), errors="coerce") > 0).sum()),
    }
    checks = [
        trading_day_check,
        check("recent_window", True, f"目标日距采集日 {age} 天，处于最近 30 日窗口"),
        check("closed_schema", closed.empty or closed_required <= set(closed.columns),
              f"涨停池 {closed_count} 条，字段检查"),
        check("broken_schema", broken.empty or broken_required <= set(broken.columns),
              f"炸板池 {len(broken)} 条，字段检查"),
        check("down_schema", isinstance(down, pd.DataFrame), f"跌停池 {len(down)} 条"),
    ]
    payload = {
        "metrics": metrics,
        "closed": records(closed),
        "failed": records(failed),
        "limit_down_rows": records(down),
    }
    return envelope("limit_activity", target,
                    "AKShare.stock_zt_pool_em/zbgc_em/dtgc_em", payload, checks)


def _flow_frame(kind: str, period: int) -> pd.DataFrame:
    fn = ak.stock_fund_flow_industry if kind == "industry" else ak.stock_fund_flow_concept
    indicator = "即时" if period == 1 else f"{period}日排行"
    return ak_call(fn, symbol=indicator)


def flows_dataset(target: date, session: str) -> dict[str, Any]:
    now = now_shanghai()
    trading_day_check = require_trading_day(target)
    allowed, detail = _session_allowed(target, session, now)
    if not allowed:
        raise DataError(detail)
    result: dict[str, Any] = {}
    all_checks = [trading_day_check, check("session_window", allowed, detail)]
    for kind in ("industry", "concept"):
        for period in (1, 5):
            frame = _flow_frame(kind, period)
            preferred = ["净额(万元)", "净额"] if period == 1 else [f"{period}日累计净额(万元)", f"{period}日累计净额"]
            candidates = [col for col in preferred if col in frame.columns]
            if not candidates:
                candidates = [col for col in frame.columns if "净额" in str(col)]
            if len(candidates) != 1:
                raise DataError(f"{kind}/{period}日资金流无法唯一识别净额字段：{list(frame.columns)}")
            net_col = candidates[0]
            work = frame.copy()
            work[net_col] = pd.to_numeric(work[net_col], errors="coerce")
            work = work.dropna(subset=[net_col]).sort_values(net_col, ascending=False)
            key = f"{kind}_{period}d"
            result[key] = {
                "net_column": net_col,
                "amount_unit": "source_unspecified" if "(" not in str(net_col) else str(net_col).split("(", 1)[1].rstrip(")"),
                "usage_note": "单位未由源字段声明时只用于方向和排序，不做金额换算或金额陈述",
                "rows": records(work),
            }
            all_checks.append(check(f"{key}_rows", len(work) >= 20,
                                    f"取得 {len(work)} 个板块并按净额降序重排"))
    document = envelope(f"fund_flows_{session}", target,
                        "AKShare.stock_fund_flow_industry/concept (10jqka)",
                        {"session": session, "rankings": result}, all_checks)
    default_path = DATA_DIR / day_key(target) / f"flows_{session}.json"
    default_path.parent.mkdir(parents=True, exist_ok=True)
    temp = default_path.with_suffix(".tmp")
    temp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, default_path)
    document["snapshot_path"] = str(default_path)
    return document


def lhb_dataset(target: date) -> dict[str, Any]:
    now = now_shanghai()
    trading_day_check = require_trading_day(target)
    if target != now.date() or now.time().replace(tzinfo=None) < time(16, 30):
        raise DataError("龙虎榜仅允许在目标交易日 16:30 后采集，且不能用实时接口回填历史日期")
    key = day_key(target)
    detail = ak_call(ak.stock_lhb_detail_em, start_date=key, end_date=key)
    institutions = ak_call(ak.stock_lhb_jgmmtj_em, start_date=key, end_date=key)
    checks = [
        trading_day_check,
        check("detail_schema", detail.empty or {"代码", "名称"} <= set(detail.columns),
              f"龙虎榜明细 {len(detail)} 条"),
        check("institution_schema", institutions.empty or {"代码", "名称"} <= set(institutions.columns),
              f"机构统计 {len(institutions)} 条"),
    ]
    return envelope("dragon_tiger", target,
                    "AKShare.stock_lhb_detail_em/stock_lhb_jgmmtj_em",
                    {"detail": records(detail), "institutions": records(institutions)}, checks)


def _final_global_row(frame: pd.DataFrame, now: datetime) -> dict[str, Any]:
    work = frame.copy()
    date_col = "日期" if "日期" in work.columns else work.columns[0]
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    ny_now = now.astimezone(NY_TZ)
    latest_day = work.iloc[-1][date_col].date()
    latest_final = latest_day < ny_now.date() or (latest_day == ny_now.date() and ny_now.time() >= time(16, 15))
    index = -1 if latest_final else -2
    row = work.iloc[index]
    previous = work.iloc[index - 1]
    price_col = "最新价" if "最新价" in work.columns else "收盘"
    price = float(row[price_col])
    previous_price = float(previous[price_col])
    return {
        "row": {str(key): clean_number(value) for key, value in row.items()},
        "selected_row_final": True,
        "discarded_unfinished_latest": not latest_final,
        "previous_final_price": previous_price,
        "change": price - previous_price,
        "change_pct": (price / previous_price - 1) * 100 if previous_price else None,
    }


def overnight_dataset(target: date) -> dict[str, Any]:
    now = now_shanghai()
    global_rows: dict[str, Any] = {}
    for symbol in ("道琼斯", "标普500", "纳斯达克"):
        frame = ak_call(ak.index_global_hist_em, symbol=symbol)
        global_rows[symbol] = _final_global_row(frame, now)
    futures = ak_call(ak.futures_global_spot_em)
    # Search row-wise without assuming AKShare's translated column names.
    mask = futures.astype(str).apply(
        lambda row: row.str.contains("CN00Y|富时中国A50", case=False, regex=True).any(), axis=1
    )
    a50 = futures[mask]
    fx = ak_call(ak.fx_spot_quote)
    fx_mask = fx.astype(str).apply(
        lambda row: row.str.contains("美元人民币|USD/CNY|USDCNY", case=False, regex=True).any(), axis=1
    )
    usd_cny = fx[fx_mask]
    checks = [
        check("global_indices", len(global_rows) == 3, "美股三大指数均已取得"),
        check("a50", not a50.empty, f"A50 匹配 {len(a50)} 条"),
        check("usd_cny", not usd_cny.empty, f"美元人民币匹配 {len(usd_cny)} 条"),
    ]
    return envelope("overnight_markets", target,
                    "AKShare.index_global_hist_em/futures_global_spot_em/fx_spot_quote",
                    {"global_indices": global_rows,
                     "live_quotes_note": "A50 与美元人民币为采集时点行情，不标记为收盘值",
                     "a50": records(a50), "usd_cny": records(usd_cny)}, checks)


def watchlist_dataset(target: date, count: int) -> dict[str, Any]:
    path = ROOT / "data" / "watchlist.json"
    if not path.exists():
        payload = {"configured": False, "stocks": []}
        return envelope("watchlist_history", target, "local watchlist + AKShare.stock_zh_a_hist",
                        payload, [check("optional_watchlist", True, "未配置自选股；该模块不进入报告")])
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("stocks", [])
    codes = []
    for item in items:
        code = str(item.get("code") if isinstance(item, dict) else item).strip()
        if code:
            codes.append(code[-6:])
    stocks: dict[str, Any] = {}
    for code in codes:
        frame = ak_call(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="qfq",
                        start_date=(date(target.year - 2, 1, 1)).strftime("%Y%m%d"),
                        end_date=day_key(target))
        if len(frame) < count:
            raise DataError(f"自选股 {code} 仅有 {len(frame)} 条历史数据，要求 {count} 条")
        work = frame.tail(count).copy()
        if pd.to_datetime(work.iloc[-1]["日期"]).date() != target:
            raise DataError(f"自选股 {code} 最新交易日不是 {target}")
        stocks[code] = records(work)
    return envelope("watchlist_history", target, "local watchlist + AKShare.stock_zh_a_hist",
                    {"configured": bool(codes), "stocks": stocks},
                    [check("all_stocks", len(stocks) == len(codes), f"配置 {len(codes)}，取得 {len(stocks)}")])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="严格报告数据适配器")
    parser.add_argument("dataset", choices=["calendar", "indices", "snapshot", "limits", "flows", "lhb", "overnight", "watchlist"])
    parser.add_argument("--date", required=True, help="目标日期 YYYYMMDD")
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--session", choices=["noon", "close"], default="close")
    parser.add_argument("--output", help="可选 JSON 输出路径")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        target = parse_day(args.date)
        builders = {
            "calendar": lambda: calendar_dataset(target, args.count),
            "indices": lambda: indices_dataset(target, args.count),
            "snapshot": lambda: snapshot_dataset(target, args.session),
            "limits": lambda: limits_dataset(target),
            "flows": lambda: flows_dataset(target, args.session),
            "lhb": lambda: lhb_dataset(target),
            "overnight": lambda: overnight_dataset(target),
            "watchlist": lambda: watchlist_dataset(target, args.count),
        }
        write_json(builders[args.dataset](), args.output)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "dataset": args.dataset,
                          "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
