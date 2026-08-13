#!/usr/bin/env python3
"""Strict AKShare data adapters for agents.

Every command emits one JSON document to stdout and exits non-zero when the
requested dataset cannot be proven complete.  Human-readable diagnostics go to
stderr so callers never have to parse mixed output.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

# This import order is mandatory.  See repository AGENTS.md.
import akshare_patch  # noqa: F401
import akshare as ak
import pandas as pd
import requests

import indicators


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


def number(value: Any) -> float | None:
    value = clean_number(value)
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def percent_number(value: Any) -> float | None:
    if value is None:
        return None
    return number(str(value).strip().rstrip("%"))


def rounded_number(value: Any, digits: int = 4) -> float | None:
    parsed = number(value)
    return round(parsed, digits) if parsed is not None else None


def stock_code(value: str) -> str:
    clean = str(value).strip().upper().replace(".", "")
    for prefix in ("SH", "SZ", "BJ"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
        if clean.endswith(prefix):
            clean = clean[:-len(prefix)]
    if len(clean) != 6 or not clean.isdigit():
        raise DataError(f"Invalid security code: {value}")
    return clean


def exchange_for(code: str) -> str:
    if code.startswith(("60", "68", "51", "52", "56", "58")):
        return "sh"
    if code.startswith(("00", "30", "15", "16")):
        return "sz"
    if code.startswith(("4", "8", "9")):
        return "bj"
    raise DataError(f"Unsupported security code: {code}")


def amount_yuan(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    multiplier = 1.0
    if text.endswith("亿"):
        multiplier, text = 100_000_000.0, text[:-1]
    elif text.endswith("万"):
        multiplier, text = 10_000.0, text[:-1]
    parsed = number(text)
    return round(parsed * multiplier, 2) if parsed is not None else None


def provider_amount_yuan(value: Any, column: str) -> float | None:
    parsed = amount_yuan(value)
    if parsed is None:
        return None
    if isinstance(value, str) and ("亿" in value or "万" in value):
        return parsed
    if "万元" in column:
        return round(parsed * 10_000, 2)
    # 10jqka fund-flow endpoints expose bare numeric fund amounts in 100M CNY.
    if "净额" in column or column in {"流入资金", "流出资金"}:
        return round(parsed * 100_000_000, 2)
    return round(parsed, 2)


def quote_timestamps(values: pd.Series, target: date) -> pd.Series:
    """Parse provider timestamps without inferring today's date for time-only values."""
    text = values.astype(str).str.strip()
    time_only = text.str.fullmatch(r"\d{1,2}:\d{2}:\d{2}")
    normalized = text.where(~time_only, target.isoformat() + " " + text)
    return pd.to_datetime(normalized, errors="coerce")


def persist_document(path: Path, document: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)
    return {"path": str(path), "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def exchange_and_type(code: str) -> tuple[str, str]:
    exchange = exchange_for(code)
    security_type = "fund" if code.startswith(("15", "16", "51", "52", "56", "58")) else "stock"
    return exchange, security_type


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


def indices_dataset(target: date, count: int, session: str | None = None) -> dict[str, Any]:
    if session == "noon":
        allowed, detail = _session_allowed(target, session, now_shanghai())
        if not allowed:
            raise DataError(detail)
    elif session == "close" and target == now_shanghai().date():
        allowed, detail = _session_allowed(target, session, now_shanghai())
        if not allowed:
            raise DataError(detail)
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
    bar_state = "intraday" if session == "noon" and target == now_shanghai().date() else "final"
    dataset_name = f"index_history_{session}" if session else "index_history"
    return envelope(dataset_name, target,
                    "Eastmoney push2his fixed secid via AKShare transport",
                    {"bar_state": bar_state, "session": session, "indices": result}, checks)


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
    timestamps = quote_timestamps(valid["时间戳"], target)
    local_times = timestamps.dt.time
    if session == "close":
        fresh_mask = (timestamps.dt.date == target) & (local_times >= time(14, 50))
    else:
        fresh_mask = ((timestamps.dt.date == target) & (local_times >= time(11, 25)) &
                      (local_times <= time(12, 59, 59)))
    fresh_ratio = float(fresh_mask.sum() / len(valid)) if len(valid) else 0.0
    valid_timestamps = timestamps.dropna().sort_values()
    latest_stamp = valid_timestamps.iloc[-1].isoformat() if not valid_timestamps.empty else ""
    changes = valid["涨跌幅"]
    distribution_masks = {
        "gte_9_9": changes >= 9.9,
        "7_to_9_9": (changes >= 7) & (changes < 9.9),
        "5_to_7": (changes >= 5) & (changes < 7),
        "3_to_5": (changes >= 3) & (changes < 5),
        "0_to_3": (changes > 0) & (changes < 3),
        "flat": changes == 0,
        "minus_3_to_0": (changes >= -3) & (changes < 0),
        "minus_5_to_minus_3": (changes >= -5) & (changes < -3),
        "minus_7_to_minus_5": (changes >= -7) & (changes < -5),
        "minus_9_9_to_minus_7": (changes > -9.9) & (changes < -7),
        "lte_minus_9_9": changes <= -9.9,
    }
    distribution = [{"bucket": label, "count": int(mask.sum())}
                    for label, mask in distribution_masks.items()]
    normalized_rows = []
    for _, row in valid.iterrows():
        normalized_rows.append({
            "security_code": str(row["plain_code"]), "name": str(row["名称"]),
            "last": number(row.get("最新价")), "pre_close": number(row.get("昨收")),
            "open": number(row.get("今开")), "high": number(row.get("最高")),
            "low": number(row.get("最低")), "change": number(row.get("涨跌额")),
            "change_pct": number(row.get("涨跌幅")), "volume": number(row.get("成交量")),
            "turnover_yuan": number(row.get("成交额")),
            "turnover_rate_pct": number(row.get("换手率")),
            "quote_timestamp": clean_number(row.get("时间戳")),
        })
    ranking_frame = valid.assign(_change=pd.to_numeric(valid["涨跌幅"], errors="coerce"),
                                 _turnover=pd.to_numeric(valid["成交额"], errors="coerce"))
    def ranked(frame: pd.DataFrame) -> list[dict[str, Any]]:
        by_code = {item["security_code"]: item for item in normalized_rows}
        return [by_code[code] for code in frame["plain_code"].astype(str) if code in by_code]
    rankings = {
        "gainers": ranked(ranking_frame.nlargest(20, "_change")),
        "losers": ranked(ranking_frame.nsmallest(20, "_change")),
        "turnover": ranked(ranking_frame.nlargest(20, "_turnover")),
    }
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
        "earliest_source_timestamp": valid_timestamps.iloc[0].isoformat() if not valid_timestamps.empty else None,
        "median_source_timestamp": valid_timestamps.iloc[len(valid_timestamps) // 2].isoformat()
        if not valid_timestamps.empty else None,
        "fresh_record_ratio": round(fresh_ratio, 6),
    }
    checks = [
        trading_day_check,
        check("session_window", allowed, detail),
        check("schema", not missing, f"必需字段完整；{len(valid)} 条有效记录"),
        check("coverage", coverage >= 0.98,
              f"有效 {metrics['security_count']} / 主表 {master_count} = {coverage:.2%}"),
        check("unique_codes", valid["plain_code"].nunique() == len(valid),
              "证券代码必须唯一"),
        check("source_freshness", fresh_ratio >= 0.98,
              f"{fresh_mask.sum()} / {len(valid)} = {fresh_ratio:.2%} records match {session}"),
    ]
    document = envelope(f"market_snapshot_{session}", target,
                        "AKShare.stock_zh_a_spot + stock_info_a_code_name",
                        {"session": session, "metrics": metrics,
                         "distribution": distribution, "rankings": rankings,
                         "rows": normalized_rows}, checks)
    reference = persist_document(DATA_DIR / day_key(target) / session / "market_snapshot.json", document)
    document["data"].pop("rows")
    document["data"]["raw"] = {**reference, "row_count": len(normalized_rows)}
    return document


def limits_dataset(target: date, session: str | None = None) -> dict[str, Any]:
    if session == "noon":
        allowed, detail = _session_allowed(target, session, now_shanghai())
        if not allowed:
            raise DataError(detail)
    elif session == "close" and target == now_shanghai().date():
        allowed, detail = _session_allowed(target, session, now_shanghai())
        if not allowed:
            raise DataError(detail)
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
    streak_values = pd.to_numeric(closed.get("连板数", pd.Series(dtype=float)), errors="coerce")
    streak_ladder = [
        {"streak": int(streak), "count": int(count)}
        for streak, count in streak_values.dropna().astype(int).value_counts().sort_index().items()
    ]
    industry_stats: dict[str, dict[str, int]] = {}
    for frame, field in ((closed, "closed"), (failed, "failed"), (down, "limit_down")):
        if "所属行业" not in frame.columns:
            continue
        for industry, count in frame["所属行业"].fillna("Unknown").astype(str).value_counts().items():
            industry_stats.setdefault(industry, {"closed": 0, "failed": 0, "limit_down": 0})[field] = int(count)
    checks = [
        trading_day_check,
        check("recent_window", True, f"目标日距采集日 {age} 天，处于最近 30 日窗口"),
        check("closed_schema", closed.empty or closed_required <= set(closed.columns),
              f"涨停池 {closed_count} 条，字段检查"),
        check("broken_schema", broken.empty or broken_required <= set(broken.columns),
              f"炸板池 {len(broken)} 条，字段检查"),
        check("down_schema", isinstance(down, pd.DataFrame), f"跌停池 {len(down)} 条"),
    ]
    def limit_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return [{
            "security_code": str(row.get("代码", "")).zfill(6), "name": clean_number(row.get("名称")),
            "last": number(row.get("最新价")), "change_pct": percent_number(row.get("涨跌幅")),
            "turnover_yuan": provider_amount_yuan(row.get("成交额"), "成交额"),
            "turnover_rate_pct": percent_number(row.get("换手率")),
            "sealed_funds_yuan": provider_amount_yuan(row.get("封板资金"), "封板资金"),
            "first_sealed_at": clean_number(row.get("首次封板时间")),
            "last_sealed_at": clean_number(row.get("最后封板时间")),
            "streak": int(number(row.get("连板数")) or 0),
            "break_count": int(number(row.get("炸板次数")) or 0),
            "industry": clean_number(row.get("所属行业")),
        } for _, row in frame.iterrows()]
    normalized_closed = limit_rows(closed)
    normalized_failed = limit_rows(failed)
    normalized_down = limit_rows(down)
    payload = {
        "session": session,
        "metrics": metrics,
        "streak_ladder": streak_ladder,
        "industry_stats": [{"industry": key, **value} for key, value in sorted(industry_stats.items())],
        "closed": normalized_closed,
        "failed": normalized_failed,
        "limit_down_rows": normalized_down,
    }
    dataset_name = f"limit_activity_{session}" if session else "limit_activity"
    document = envelope(dataset_name, target,
                        "AKShare.stock_zt_pool_em/zbgc_em/dtgc_em", payload, checks)
    reference = persist_document(DATA_DIR / day_key(target) / (session or "query") / "limit_activity.json", document)
    document["data"]["raw"] = {**reference, "row_count": closed_count + failed_count + len(down)}
    return document


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
        for period in (1, 3, 5):
            frame = _flow_frame(kind, period)
            preferred = ["净额(万元)", "净额"] if period == 1 else [f"{period}日累计净额(万元)", f"{period}日累计净额"]
            candidates = [col for col in preferred if col in frame.columns]
            if not candidates:
                candidates = [col for col in frame.columns if "净额" in str(col)]
            if len(candidates) != 1:
                raise DataError(f"{kind}/{period}日资金流无法唯一识别净额字段：{list(frame.columns)}")
            net_col = candidates[0]
            work = frame.copy()
            work["_net_yuan"] = work[net_col].map(lambda value: provider_amount_yuan(value, net_col))
            work = work.dropna(subset=["_net_yuan"]).sort_values("_net_yuan", ascending=False)
            def flow_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
                return [{
                    "rank": int(number(row.get("序号")) or 0),
                    "sector": clean_number(row.get("行业")), "sector_kind": kind,
                    "period_days": period, "company_count": int(number(row.get("公司家数")) or 0),
                    "index_value": number(row.get("行业指数")),
                    "change_pct": percent_number(row.get("行业-涨跌幅", row.get("阶段涨跌幅"))),
                    "inflow_yuan": provider_amount_yuan(row.get("流入资金"), "流入资金"),
                    "outflow_yuan": provider_amount_yuan(row.get("流出资金"), "流出资金"),
                    "net_flow_yuan": number(row.get("_net_yuan")),
                    "leading_stock": clean_number(row.get("领涨股")),
                    "leading_stock_change_pct": percent_number(row.get("领涨股-涨跌幅")),
                } for _, row in frame.iterrows()]
            normalized = flow_rows(work)
            key = f"{kind}_{period}d"
            result[key] = {
                "amount_unit": "CNY",
                "rows": normalized,
                "top_inflow": normalized[:20],
                "top_outflow": flow_rows(work.tail(20).sort_values("_net_yuan")),
            }
            all_checks.append(check(f"{key}_rows", len(work) >= 20,
                                    f"{key}: 取得 {len(work)} 个板块并按净额降序重排"))
    document = envelope(f"fund_flows_{session}", target,
                        "AKShare.stock_fund_flow_industry/concept (10jqka)",
                        {"session": session, "rankings": result}, all_checks)
    reference = persist_document(DATA_DIR / day_key(target) / session / "sector_fund_flows.json", document)
    for ranking in document["data"]["rankings"].values():
        ranking.pop("rows")
    document["data"]["raw"] = reference
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
    def lhb_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return [{
            "date": clean_number(row.get("上榜日", row.get("上榜日期"))),
            "security_code": str(row.get("代码", "")).zfill(6), "name": clean_number(row.get("名称")),
            "close": number(row.get("收盘价")), "change_pct": percent_number(row.get("涨跌幅")),
            "reason": clean_number(row.get("上榜原因")), "interpretation": clean_number(row.get("解读")),
            "buy_yuan": provider_amount_yuan(row.get("龙虎榜买入额", row.get("机构买入总额")), "元"),
            "sell_yuan": provider_amount_yuan(row.get("龙虎榜卖出额", row.get("机构卖出总额")), "元"),
            "net_buy_yuan": provider_amount_yuan(row.get("龙虎榜净买额", row.get("机构买入净额")), "元"),
            "institution_buyers": int(number(row.get("买方机构数")) or 0),
            "institution_sellers": int(number(row.get("卖方机构数")) or 0),
            "turnover_rate_pct": percent_number(row.get("换手率")),
        } for _, row in frame.iterrows()]
    return envelope("dragon_tiger", target,
                    "AKShare.stock_lhb_detail_em/stock_lhb_jgmmtj_em",
                    {"detail": lhb_rows(detail), "institutions": lhb_rows(institutions)}, checks)


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
    if target != now.date():
        raise DataError("Overnight data is current pre-market context and cannot be backfilled")
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


def security_master_dataset(target: date) -> dict[str, Any]:
    if target != now_shanghai().date():
        raise DataError("Security master describes the current listed universe and cannot be backfilled")
    frame = ak_call(ak.stock_info_a_code_name)
    if not {"code", "name"} <= set(frame.columns):
        raise DataError("Security master is missing code or name")
    rows = []
    for _, row in frame.iterrows():
        code = str(row["code"]).zfill(6)
        exchange, security_type = exchange_and_type(code)
        rows.append({"security_code": code, "name": str(row["name"]), "exchange": exchange,
                     "security_type": security_type, "listing_status": "listed"})
    return envelope("security_master", target, "AKShare.stock_info_a_code_name",
                    {"rows": rows}, [check("unique_codes", len({row["security_code"] for row in rows}) == len(rows),
                                                   f"Loaded {len(rows)} securities")])


def big_deals_dataset(target: date) -> dict[str, Any]:
    now = now_shanghai()
    if target != now.date():
        raise DataError("Large trades are current-session data and cannot be backfilled")
    trading_day_check = require_trading_day(target)
    if now.time().replace(tzinfo=None) < time(9, 30):
        raise DataError("Large trades are not available before the current trading session starts")
    frame = ak_call(ak.stock_fund_flow_big_deal)
    required = {"成交时间", "股票代码", "股票简称", "成交价格", "成交额", "大单性质", "涨跌幅"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise DataError(f"Large trades are missing fields: {missing}")
    trade_times = pd.to_datetime(frame["成交时间"], errors="coerce")
    dated_rows = int(trade_times.notna().sum())
    target_rows = int((trade_times.dt.date == target).sum())
    rows = [{
        "trade_time": clean_number(row.get("成交时间")),
        "security_code": str(row.get("股票代码")).zfill(6), "name": str(row.get("股票简称")),
        "price": number(row.get("成交价格")), "volume": number(row.get("成交量")),
        # This endpoint labels the column as “成交额” but returns values in 10K CNY.
        "amount_yuan": provider_amount_yuan(row.get("成交额"), "成交额(万元)"),
        "side": clean_number(row.get("大单性质")),
        "change_pct": percent_number(row.get("涨跌幅")),
    } for _, row in frame.iterrows()]
    side_counts: dict[str, int] = {}
    for row in rows:
        side = str(row["side"] or "unknown")
        side_counts[side] = side_counts.get(side, 0) + 1
    document = envelope(
        "large_trades", target, "AKShare.stock_fund_flow_big_deal",
        {"metrics": {
            "trade_count": len(rows),
            "total_amount_yuan": round(sum(row["amount_yuan"] or 0 for row in rows), 2),
            "side_counts": side_counts,
        }, "rows": rows},
        [trading_day_check,
         check("schema", not missing, f"Loaded {len(rows)} trades"),
         check("trade_dates", dated_rows == len(rows) and target_rows == len(rows),
               f"{target_rows} / {len(rows)} trades belong to {target}")],
    )
    reference = persist_document(DATA_DIR / day_key(target) / "intraday" / "large_trades.json", document)
    document["data"]["largest_trades"] = sorted(
        rows, key=lambda row: row["amount_yuan"] or 0, reverse=True
    )[:50]
    document["data"].pop("rows")
    document["data"]["raw"] = {**reference, "row_count": len(rows)}
    return document


def quote_dataset(target: date, code_value: str) -> dict[str, Any]:
    code = stock_code(code_value)
    if target != now_shanghai().date():
        raise DataError("Realtime quotes are only valid for the current date")
    info = akshare_patch.get_single_stock_realtime(code)
    source = "Sina direct quote"
    if not info:
        frame = ak_call(ak.stock_zh_a_spot)
        frame["plain_code"] = frame["代码"].astype(str).str[-6:]
        selected = frame[frame["plain_code"] == code]
        if selected.empty:
            raise DataError(f"No realtime quote for {code}")
        row = selected.iloc[0]
        info = {"name": row.get("名称"), "price": row.get("最新价"), "change_pct": row.get("涨跌幅"),
                "change": row.get("涨跌额"), "open": row.get("今开"), "pre_close": row.get("昨收"),
                "high": row.get("最高"), "low": row.get("最低"), "volume": row.get("成交量"),
                "turnover": row.get("成交额"), "quote_timestamp": row.get("时间戳")}
        source = "AKShare.stock_zh_a_spot"
    data = {"security_code": code, "exchange": exchange_for(code), "name": info.get("name"),
            "last": number(info.get("price")), "change_pct": rounded_number(info.get("change_pct"), 6),
            "change": rounded_number(info.get("change")), "open": number(info.get("open")),
            "pre_close": number(info.get("pre_close")), "high": number(info.get("high")),
            "low": number(info.get("low")), "volume": number(info.get("volume")),
            "turnover_yuan": number(info.get("turnover")),
            "quote_timestamp": clean_number(info.get("quote_timestamp"))}
    quote_time = quote_timestamps(pd.Series([data["quote_timestamp"]]), target).iloc[0]
    quote_date_ok = not pd.isna(quote_time) and quote_time.date() == target
    fresh = False
    freshness_detail = f"Quote timestamp {data['quote_timestamp']}"
    if quote_date_ok:
        now = now_shanghai()
        quote_dt = quote_time.to_pydatetime()
        if quote_dt.tzinfo is None:
            quote_dt = quote_dt.replace(tzinfo=SH_TZ)
        local_time = now.time().replace(tzinfo=None)
        quote_local_time = quote_dt.astimezone(SH_TZ).time().replace(tzinfo=None)
        if time(9, 15) <= local_time <= time(11, 30) or time(13, 0) <= local_time <= time(15, 0):
            age_seconds = (now - quote_dt.astimezone(SH_TZ)).total_seconds()
            fresh = -60 <= age_seconds <= 300
            freshness_detail = f"Trading-session quote age {age_seconds:.0f}s"
        elif time(11, 30) < local_time < time(13, 0):
            fresh = quote_local_time >= time(11, 29)
            freshness_detail = f"Lunch quote time {quote_local_time}"
        elif local_time > time(15, 0):
            fresh = quote_local_time >= time(14, 59)
            freshness_detail = f"Closing quote time {quote_local_time}"
    return envelope("stock_quote", target, source, data,
                    [check("identity", data["last"] is not None, f"Loaded quote for {code}"),
                     check("quote_date", quote_date_ok, f"Quote timestamp {data['quote_timestamp']}"),
                     check("quote_freshness", fresh, freshness_detail)])


def _kline_frame(code: str, target: date, period: str, count: int, adjust: str) -> pd.DataFrame:
    start = target - timedelta(days=max(count * 5, 500))
    if period in {"30", "60", "120"}:
        frame = ak_call(ak.stock_zh_a_hist_min_em, symbol=code, period=period, adjust=adjust)
        date_col = "时间"
        timestamps = pd.to_datetime(frame.get(date_col), errors="coerce")
        frame = frame[timestamps.dt.date <= target]
    else:
        frame = ak_call(ak.stock_zh_a_hist, symbol=code, period=period, adjust=adjust,
                        start_date=day_key(start), end_date=day_key(target))
        date_col = "日期"
    if frame.empty or date_col not in frame.columns:
        raise DataError(f"No {period} K-line data for {code}")
    return frame.tail(count).copy()


def kline_dataset(target: date, code_value: str, period: str, count: int, adjust: str) -> dict[str, Any]:
    code = stock_code(code_value)
    frame = _kline_frame(code, target, period, count, adjust)
    date_col = "时间" if "时间" in frame.columns else "日期"
    rows = [{"timestamp": clean_number(row.get(date_col)), "open": number(row.get("开盘")),
             "high": number(row.get("最高")), "low": number(row.get("最低")),
             "close": number(row.get("收盘")), "volume": number(row.get("成交量")),
             "turnover_yuan": number(row.get("成交额")), "amplitude_pct": number(row.get("振幅")),
             "change_pct": number(row.get("涨跌幅")), "turnover_rate_pct": number(row.get("换手率"))}
            for _, row in frame.iterrows()]
    actual_latest = pd.to_datetime(frame.iloc[-1][date_col], errors="coerce")
    latest_ok = not pd.isna(actual_latest) and actual_latest.date() <= target
    return envelope("stock_kline", target, "AKShare stock history",
                    {"security_code": code, "period": period, "adjust": adjust,
                     "actual_latest_timestamp": clean_number(actual_latest), "rows": rows},
                    [check("rows", len(rows) == count, f"Requested {count}, loaded {len(rows)}"),
                     check("latest_not_after_target", latest_ok, f"Latest {actual_latest}, target {target}")])


def technical_dataset(target: date, code_value: str, count: int, adjust: str) -> dict[str, Any]:
    code = stock_code(code_value)
    frame = _kline_frame(code, target, "daily", max(260, count), adjust)
    if len(frame) < 250:
        raise DataError(f"Technical indicators require 250 rows; loaded {len(frame)}")
    renamed = frame.rename(columns={"日期": "Date", "开盘": "Open", "最高": "High",
                                    "最低": "Low", "收盘": "Close", "成交量": "Volume"})
    calculated = indicators.calculate_all_indicators(renamed).tail(count)
    columns = ["Date", "Open", "High", "Low", "Close", "Volume",
               "SMA_5", "SMA_10", "SMA_20", "SMA_30", "SMA_60", "SMA_120", "SMA_250",
               "EMA_5", "EMA_10", "EMA_20", "DIF", "DEA", "MACD", "RSI_6", "RSI_12",
               "RSI_24", "BOLL_MID", "BOLL_UP", "BOLL_LB", "KDJ_K", "KDJ_D", "KDJ_J",
               "ATR", "CCI", "WR", "VWMA", "MFI"]
    return envelope("stock_technical", target, "AKShare.stock_zh_a_hist + deterministic indicators",
                    {"security_code": code, "adjust": adjust, "warmup_rows": len(frame),
                     "actual_latest_date": clean_number(frame.iloc[-1]["日期"]),
                     "rows": records(calculated[columns])},
                    [check("warmup", len(frame) >= 250, f"Loaded {len(frame)} rows")])


def chip_dataset(target: date, code_value: str, count: int) -> dict[str, Any]:
    code = stock_code(code_value)
    frame = ak_call(ak.stock_cyq_em, symbol=code, adjust="")
    required = {"日期", "获利比例", "平均成本", "90成本-低", "90成本-高", "90集中度",
                "70成本-低", "70成本-高", "70集中度"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise DataError(f"Chip distribution is missing fields: {missing}")
    mapping = {"日期": "date", "获利比例": "profit_ratio", "平均成本": "average_cost",
               "90成本-低": "cost_90_low", "90成本-高": "cost_90_high", "90集中度": "concentration_90",
               "70成本-低": "cost_70_low", "70成本-高": "cost_70_high", "70集中度": "concentration_70"}
    frame = frame.copy()
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce")
    frame = frame[frame["日期"].dt.date <= target]
    work = frame.tail(count).rename(columns=mapping)
    return envelope("stock_chip_distribution", target, "AKShare.stock_cyq_em",
                    {"security_code": code, "rows": records(work[list(mapping.values())])},
                    [check("schema", not missing, f"Loaded {len(work)} rows"),
                     check("rows", not work.empty, f"Loaded {len(work)} rows on or before {target}")])


def sentiment_dataset(target: date, code_value: str, count: int) -> dict[str, Any]:
    code = stock_code(code_value)
    source_functions = {
        "score": ak.stock_comment_detail_zhpj_lspf_em,
        "focus": ak.stock_comment_detail_scrd_focus_em,
        "desire": ak.stock_comment_detail_scrd_desire_em,
        "institution": ak.stock_comment_detail_zlkp_jgcyd_em,
    }
    mappings = {
        "score": {"交易日": "date", "评分": "score"},
        "focus": {"交易日": "date", "用户关注指数": "focus_index"},
        "desire": {"交易日": "date", "交易日期": "date", "参与意愿": "desire",
                   "5日平均参与意愿": "desire_5d_average", "参与意愿变化": "desire_change",
                   "5日平均变化": "desire_change_5d_average", "当日意愿上升": "desire_change"},
        "institution": {"交易日": "date", "机构参与度": "institution_participation_pct"},
    }
    payload: dict[str, Any] = {}
    source_errors: dict[str, str] = {}
    for key, function in source_functions.items():
        try:
            frame = ak_call(function, symbol=code)
        except Exception as exc:
            payload[key] = []
            source_errors[key] = str(exc)
            continue
        work = frame.copy()
        date_col = next((column for column in ("交易日", "交易日期") if column in work.columns), None)
        if date_col:
            parsed = pd.to_datetime(work[date_col], errors="coerce")
            work = work[parsed.dt.date <= target]
        present = {source: destination for source, destination in mappings[key].items() if source in work.columns}
        payload[key] = records(work.tail(count)[list(present)].rename(columns=present)) if present else []
    available = sum(bool(rows) for rows in payload.values())
    return envelope("stock_sentiment", target, "AKShare stock comment detail APIs",
                    {"security_code": code, **payload, "source_errors": source_errors},
                    [check("available_sources", available > 0,
                           f"Loaded {available} of {len(source_functions)} sources")])


def stock_flow_dataset(target: date, code_value: str, period: int) -> dict[str, Any]:
    code = stock_code(code_value)
    now = now_shanghai()
    if target != now.date():
        raise DataError("Stock fund flow rankings are current data and cannot be backfilled")
    trading_day_check = require_trading_day(target)
    if now.time().replace(tzinfo=None) < time(9, 30):
        raise DataError("Stock fund flow rankings are not available before the current trading session starts")
    symbol = "即时" if period == 1 else f"{period}日排行"
    frame = ak_call(ak.stock_fund_flow_individual, symbol=symbol)
    selected = frame[frame["股票代码"].astype(str).str.zfill(6) == code]
    if selected.empty:
        raise DataError(f"No {period}-day fund flow for {code}")
    row = selected.iloc[0]
    data = {"security_code": code, "name": clean_number(row.get("股票简称")), "period_days": period,
            "last": number(row.get("最新价")), "change_pct": percent_number(row.get("涨跌幅", row.get("阶段涨跌幅"))),
            "turnover_rate_pct": percent_number(row.get("换手率", row.get("连续换手率"))),
            "inflow_yuan": provider_amount_yuan(row.get("流入资金"), "流入资金"),
            "outflow_yuan": provider_amount_yuan(row.get("流出资金"), "流出资金"),
            "net_flow_yuan": provider_amount_yuan(row.get("净额", row.get("资金流入净额")), "净额"),
            "turnover_yuan": amount_yuan(row.get("成交额")),
            "as_of": now.isoformat(timespec="seconds"),
            "freshness_basis": "current trading day and retrieval time; provider exposes no row timestamp"}
    return envelope("stock_fund_flow", target, "AKShare.stock_fund_flow_individual", data,
                    [trading_day_check,
                     check("identity", True, f"Loaded {period}-day flow for {code}"),
                     check("net_flow", data["net_flow_yuan"] is not None,
                           f"{period}-day net flow is available")])


def financial_dataset(target: date, code_value: str, statement: str, count: int) -> dict[str, Any]:
    code = stock_code(code_value)
    symbol = f"{exchange_for(code).upper()}{code}"
    functions = {"income": ak.stock_profit_sheet_by_report_em,
                 "balance_sheet": ak.stock_balance_sheet_by_report_em,
                 "cashflow": ak.stock_cash_flow_sheet_by_report_em}
    frame = ak_call(functions[statement], symbol=symbol)
    if "NOTICE_DATE" in frame.columns:
        notices = pd.to_datetime(frame["NOTICE_DATE"], errors="coerce")
        frame = frame[notices.dt.date <= target]
    if frame.empty:
        raise DataError(f"No {statement} data for {code}")
    sort_columns = [column for column in ("NOTICE_DATE", "REPORT_DATE") if column in frame.columns]
    if sort_columns:
        ordering = pd.DataFrame(
            {column: pd.to_datetime(frame[column], errors="coerce") for column in sort_columns},
            index=frame.index,
        ).sort_values(sort_columns, ascending=False, na_position="last").index
        frame = frame.loc[ordering]
    selected = frame.head(count)
    full_document = envelope("stock_financials", target, f"AKShare.{functions[statement].__name__}",
                             {"security_code": code, "statement": statement, "rows": records(selected)},
                             [check("rows", True, f"Loaded {len(selected)} statements")])
    reference = persist_document(DATA_DIR / day_key(target) / "stocks" / code / f"{statement}.json", full_document)
    common = ["REPORT_DATE", "REPORT_TYPE", "REPORT_DATE_NAME", "NOTICE_DATE", "CURRENCY"]
    metrics = {
        "income": ["TOTAL_OPERATE_INCOME", "TOTAL_OPERATE_INCOME_YOY", "OPERATE_PROFIT",
                   "OPERATE_PROFIT_YOY", "NETPROFIT", "NETPROFIT_YOY", "PARENT_NETPROFIT",
                   "PARENT_NETPROFIT_YOY", "BASIC_EPS"],
        "balance_sheet": ["TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_PARENT_EQUITY"],
        "cashflow": ["NETCASH_OPERATE", "NETCASH_INVEST", "NETCASH_FINANCE"],
    }
    fields = [field for field in common + metrics[statement] if field in selected.columns]
    rows = records(selected[fields].rename(columns={field: field.lower() for field in fields}))
    full_document["data"] = {"security_code": code, "statement": statement, "rows": rows, "raw": reference}
    return full_document


def news_dataset(target: date, code_value: str, count: int) -> dict[str, Any]:
    code = stock_code(code_value)
    frame = ak_call(ak.stock_news_em, symbol=code)
    seen: set[tuple[str, str]] = set()
    rows = []
    for _, row in frame.iterrows():
        title, published = str(row.get("新闻标题", "")), str(row.get("发布时间", ""))
        published_time = pd.to_datetime(published, errors="coerce")
        if not pd.isna(published_time) and published_time.date() > target:
            continue
        key = (title, published)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"title": title, "content": clean_number(row.get("新闻内容")),
                     "published_at": published, "source": clean_number(row.get("新闻来源", row.get("文章来源"))),
                     "url": clean_number(row.get("新闻链接"))})
        if len(rows) >= count:
            break
    return envelope("stock_news", target, "AKShare.stock_news_em",
                    {"security_code": code, "rows": rows},
                    [check("rows", bool(rows), f"Loaded {len(rows)} unique news items")])


def watchlist_dataset(target: date, count: int) -> dict[str, Any]:
    path = ROOT / "data" / "watchlist.json"
    if not path.exists():
        payload = {"configured": False, "stocks": {}}
        return envelope("watchlist_data", target, "local watchlist + AKShare.stock_zh_a_hist",
                        payload, [check("optional_watchlist", True, "未配置自选股；该模块不进入报告")])
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("stocks", [])
    codes = []
    for item in items:
        value = str(item.get("code") if isinstance(item, dict) else item).strip()
        if value:
            codes.append(stock_code(value))
    codes = list(dict.fromkeys(codes))
    stocks: dict[str, Any] = {}
    for code in codes:
        try:
            frame = ak_call(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="qfq",
                            start_date=(date(target.year - 2, 1, 1)).strftime("%Y%m%d"),
                            end_date=day_key(target))
        except Exception as exc:
            stocks[code] = {"status": "provider_error", "error": str(exc),
                            "available_rows": 0, "kline": [], "technical": []}
            continue
        if frame.empty or "日期" not in frame.columns:
            stocks[code] = {"status": "no_data", "available_rows": 0,
                            "kline": [], "technical": []}
            continue
        work = frame.tail(count).copy()
        latest = pd.to_datetime(work.iloc[-1]["日期"], errors="coerce")
        if pd.isna(latest):
            status = "invalid_latest_date"
        elif latest.date() != target:
            status = "stale"
        elif len(frame) < count:
            status = "insufficient_history"
        else:
            status = "ready"
        renamed = work.rename(columns={"日期": "date", "开盘": "open", "最高": "high",
                                       "最低": "low", "收盘": "close", "成交量": "volume",
                                       "成交额": "turnover_yuan", "振幅": "amplitude_pct",
                                       "涨跌幅": "change_pct", "换手率": "turnover_rate_pct"})
        kline_columns = [column for column in ("date", "open", "high", "low", "close", "volume",
                                                 "turnover_yuan", "amplitude_pct", "change_pct",
                                                 "turnover_rate_pct") if column in renamed.columns]
        technical_rows = []
        if len(frame) >= 250:
            calculated = indicators.calculate_all_indicators(
                frame.tail(260).rename(columns={"日期": "Date", "开盘": "Open", "最高": "High",
                                                "最低": "Low", "收盘": "Close", "成交量": "Volume"})
            ).tail(10)
            indicator_columns = [column for column in calculated.columns
                                 if column == "Date" or column in {"Close", "SMA_5", "SMA_10", "SMA_20",
                                 "SMA_30", "SMA_60", "SMA_120", "SMA_250", "EMA_5", "EMA_10", "EMA_20",
                                 "DIF", "DEA", "MACD", "RSI_6", "RSI_12", "RSI_24", "BOLL_MID", "BOLL_UP",
                                 "BOLL_LB", "KDJ_K", "KDJ_D", "KDJ_J", "ATR", "CCI", "WR", "VWMA", "MFI"}]
            technical_rows = records(calculated[indicator_columns])
        stocks[code] = {
            "status": status,
            "available_rows": len(frame),
            "requested_rows": count,
            "latest_date": None if pd.isna(latest) else clean_number(latest),
            "kline": records(renamed[kline_columns]),
            "technical": technical_rows,
        }
    ready_count = sum(item["status"] == "ready" for item in stocks.values())
    document = envelope("watchlist_data", target, "local watchlist + AKShare.stock_zh_a_hist",
                        {"configured": bool(codes), "ready_count": ready_count,
                         "unavailable_count": len(codes) - ready_count, "stocks": stocks},
                        [check("all_stocks_represented", len(stocks) == len(codes),
                               f"配置 {len(codes)}，返回 {len(stocks)} 个状态")])
    if not codes:
        return document
    reference = persist_document(DATA_DIR / day_key(target) / "watchlist.json", document)
    for item in document["data"]["stocks"].values():
        item["kline"] = item["kline"][-30:]
    document["data"]["raw"] = reference
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strict JSON market data for agents")
    parser.add_argument("dataset", choices=[
        "calendar", "master", "indices", "snapshot", "limits", "flows", "big-deals", "lhb",
        "overnight", "watchlist", "quote", "kline", "technical", "chips", "sentiment",
        "stock-flow", "financials", "news",
    ])
    parser.add_argument("--date", required=True, help="目标日期 YYYYMMDD")
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--session", choices=["noon", "close"], default="close")
    parser.add_argument("--code")
    parser.add_argument("--period", default="daily",
                        choices=["daily", "weekly", "monthly", "30", "60", "120"])
    parser.add_argument("--flow-period", type=int, choices=[1, 3, 5, 10, 20], default=1)
    parser.add_argument("--adjust", choices=["", "qfq", "hfq"], default="qfq")
    parser.add_argument("--statement", choices=["income", "balance_sheet", "cashflow"], default="income")
    parser.add_argument("--output", help="可选 JSON 输出路径")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        target = parse_day(args.date)
        if args.count <= 0:
            raise DataError("--count must be greater than zero")
        if target > now_shanghai().date() and args.dataset != "calendar":
            raise DataError(f"{args.dataset} does not accept a future target date")
        code_required = {"quote", "kline", "technical", "chips", "sentiment", "stock-flow", "financials", "news"}
        if args.dataset in code_required and not args.code:
            raise DataError(f"{args.dataset} requires --code")
        builders = {
            "calendar": lambda: calendar_dataset(target, args.count),
            "master": lambda: security_master_dataset(target),
            "indices": lambda: indices_dataset(target, args.count, args.session),
            "snapshot": lambda: snapshot_dataset(target, args.session),
            "limits": lambda: limits_dataset(target, args.session),
            "flows": lambda: flows_dataset(target, args.session),
            "big-deals": lambda: big_deals_dataset(target),
            "lhb": lambda: lhb_dataset(target),
            "overnight": lambda: overnight_dataset(target),
            "watchlist": lambda: watchlist_dataset(target, args.count),
            "quote": lambda: quote_dataset(target, args.code),
            "kline": lambda: kline_dataset(target, args.code, args.period, args.count, args.adjust),
            "technical": lambda: technical_dataset(target, args.code, args.count, args.adjust),
            "chips": lambda: chip_dataset(target, args.code, args.count),
            "sentiment": lambda: sentiment_dataset(target, args.code, args.count),
            "stock-flow": lambda: stock_flow_dataset(target, args.code, args.flow_period),
            "financials": lambda: financial_dataset(target, args.code, args.statement, args.count),
            "news": lambda: news_dataset(target, args.code, args.count),
        }
        write_json(builders[args.dataset](), args.output)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "dataset": args.dataset,
                          "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
