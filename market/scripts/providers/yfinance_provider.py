"""Primary global market data provider using yfinance with resilient Sina fallback.

Covers:
- HK and US stock realtime quotes and multi-period K-lines.
- Global overnight indices (S&P 500, Nasdaq, Dow Jones, VIX).
- Global commodity futures.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
from datetime import date, datetime
from typing import Any

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


OVERNIGHT_SYMBOLS = {
    "道琼斯": "^DJI",
    "标普500": "^GSPC",
    "纳斯达克": "^IXIC",
    "VIX": "^VIX",
}

COMMODITY_SYMBOLS = {
    "GC": "GC=F",     # 纽约黄金
    "CL": "CL=F",     # WTI原油
    "HG": "HG=F",     # 纽约铜
    "SI": "SI=F",     # 纽约白银
}


def to_yf_symbol(code: str, market: str | None = None) -> str:
    """Normalize raw stock symbol to yfinance standard ticker."""
    raw = str(code).strip().upper()
    if market == "hk" or raw.endswith(".HK") or raw.startswith("HK"):
        digits = "".join(c for c in raw if c.isdigit())
        # yfinance uses 4-digit HK symbols, e.g. 0700.HK, 9988.HK
        hk_num = digits.lstrip("0").zfill(4) if digits else "0700"
        return f"{hk_num}.HK"
    elif market == "us" or raw.endswith(".US") or raw.startswith("US."):
        clean = raw
        if clean.endswith(".US"):
            clean = clean[:-3]
        if clean.startswith("US."):
            clean = clean[3:]
        # e.g. BRK.B -> BRK-B in Yahoo Finance
        return clean.replace(".", "-")
    return raw


# ---------------------------------------------------------------------------
# Realtime Stock Quote with Sina Fallback
# ---------------------------------------------------------------------------

def _fetch_sina_hk_quote(code: str) -> dict[str, Any]:
    digits = "".join(c for c in str(code) if c.isdigit()).zfill(5)
    url = f"http://hq.sinajs.cn/list=rt_hk{digits}"
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        text = resp.read().decode("gbk", errors="replace")
    if '"' not in text:
        raise RuntimeError(f"Sina HK quote returned invalid data for {code}")
    data_str = text.split('"')[1]
    parts = data_str.split(",")
    if len(parts) < 19:
        raise RuntimeError(f"Sina HK quote data truncated for {code}")
    name = parts[1]
    open_p = float(parts[2]) if parts[2] else 0.0
    pre_close = float(parts[3]) if parts[3] else 0.0
    high_p = float(parts[4]) if parts[4] else 0.0
    low_p = float(parts[5]) if parts[5] else 0.0
    last_p = float(parts[6]) if parts[6] else 0.0
    change = float(parts[7]) if parts[7] else 0.0
    change_pct = float(parts[8]) if parts[8] else 0.0
    turnover = float(parts[11]) if parts[11] else 0.0
    volume = float(parts[12]) if parts[12] else 0.0
    date_str = parts[17].replace("/", "-")
    time_str = parts[18]
    ts = f"{date_str} {time_str}"
    return {
        "name": name, "last": last_p, "change": change, "change_pct": change_pct,
        "open": open_p, "high": high_p, "low": low_p, "pre_close": pre_close,
        "volume": volume, "turnover_yuan": turnover, "quote_timestamp": ts,
        "source": "Sina.rt_hk",
    }


def _fetch_sina_us_quote(code: str) -> dict[str, Any]:
    clean = str(code).strip().lower()
    if clean.endswith(".us"):
        clean = clean[:-3]
    if clean.startswith("us."):
        clean = clean[3:]
    clean = clean.replace(".", "")
    url = f"http://hq.sinajs.cn/list=gb_{clean}"
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        text = resp.read().decode("gbk", errors="replace")
    if '"' not in text:
        raise RuntimeError(f"Sina US quote returned invalid data for {code}")
    data_str = text.split('"')[1]
    parts = data_str.split(",")
    if len(parts) < 11:
        raise RuntimeError(f"Sina US quote data truncated for {code}")
    name = parts[0]
    last_p = float(parts[1]) if parts[1] else 0.0
    change_pct = float(parts[2]) if parts[2] else 0.0
    ts = parts[3]
    change = float(parts[4]) if parts[4] else 0.0
    open_p = float(parts[5]) if parts[5] else 0.0
    high_p = float(parts[6]) if parts[6] else 0.0
    low_p = float(parts[7]) if parts[7] else 0.0
    volume = float(parts[10]) if parts[10] else 0.0
    pre_close = round(last_p - change, 4)
    return {
        "name": name, "last": last_p, "change": change, "change_pct": change_pct,
        "open": open_p, "high": high_p, "low": low_p, "pre_close": pre_close,
        "volume": volume, "turnover_yuan": None, "quote_timestamp": ts,
        "source": "Sina.gb_us",
    }


def get_stock_quote(code: str, market: str) -> dict[str, Any]:
    """Fetch realtime quote for HK or US stock using yfinance with Sina fallback."""
    yf_symbol = to_yf_symbol(code, market)
    quote_data: dict[str, Any] | None = None

    # 1. Try yfinance fast_info
    if yf is not None:
        try:
            ticker = yf.Ticker(yf_symbol)
            fast = ticker.fast_info
            last_p = fast.get("last_price")
            if last_p is not None and not math.isnan(last_p):
                pre_close = fast.get("previous_close") or last_p
                change = round(last_p - pre_close, 4)
                change_pct = round((change / pre_close) * 100, 4) if pre_close else 0.0
                quote_data = {
                    "name": getattr(ticker, "info", {}).get("shortName") or yf_symbol,
                    "last": float(last_p),
                    "change": change,
                    "change_pct": change_pct,
                    "open": float(fast.get("open") or last_p),
                    "high": float(fast.get("day_high") or last_p),
                    "low": float(fast.get("day_low") or last_p),
                    "pre_close": float(pre_close),
                    "volume": float(fast.get("last_volume") or 0.0),
                    "turnover_yuan": None,
                    "quote_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "yfinance.fast_info",
                }
        except Exception:
            quote_data = None

    # 2. Resilient fallback to Sina direct quote
    if quote_data is None:
        if market == "hk":
            quote_data = _fetch_sina_hk_quote(code)
        elif market == "us":
            quote_data = _fetch_sina_us_quote(code)
        else:
            raise ValueError(f"Unsupported market for yfinance provider: {market}")

    return quote_data


# ---------------------------------------------------------------------------
# Multi-period K-lines with AKShare Daily Fallback
# ---------------------------------------------------------------------------

PERIOD_MAP = {
    "daily": "1d",
    "weekly": "1wk",
    "monthly": "1mo",
    "30": "30m",
    "60": "60m",
    "120": "60m",  # yfinance doesn't have 120m, 60m will be resampled if needed
}


def get_kline_bars(
    code: str,
    market: str,
    period: str = "daily",
    count: int = 120,
    adjust: str = "qfq",
    at: datetime | None = None,
) -> pd.DataFrame:
    """Fetch multi-period K-lines for HK/US stock using yfinance with AKShare fallback."""
    yf_symbol = to_yf_symbol(code, market)
    frame: pd.DataFrame | None = None

    # 1. Try yfinance
    if yf is not None:
        yf_interval = PERIOD_MAP.get(period, "1d")
        history_multiplier = {"daily": 5, "weekly": 10, "monthly": 40}.get(period, 5)
        period_str = f"{max(count * history_multiplier, 365)}d" if period == "daily" else "max"
        if period in {"30", "60", "120"}:
            period_str = "60d"  # Yahoo finance max for minute data is 60d
        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period_str, interval=yf_interval, auto_adjust=(adjust == "qfq"))
            if df is not None and not df.empty and len(df) >= min(count, 5):
                df = df.reset_index()
                # Determine date column name
                date_col_src = "Datetime" if "Datetime" in df.columns else "Date"
                if date_col_src in df.columns:
                    target_date_col = "时间" if period in {"30", "60", "120"} else "日期"
                    df = df.rename(columns={
                        date_col_src: target_date_col,
                        "Open": "开盘",
                        "High": "最高",
                        "Low": "最低",
                        "Close": "收盘",
                        "Volume": "成交量",
                    })
                    df["成交额"] = df["收盘"] * df["成交量"]
                    previous_close = df["收盘"].shift(1)
                    df["涨跌幅"] = (df["收盘"] / previous_close - 1) * 100
                    df.attrs["market_source"] = f"yfinance.{yf_symbol}"
                    frame = df
        except Exception:
            frame = None

    # 2. Resilient fallback to AKShare Sina daily
    if frame is None:
        import akshare as ak
        if market == "hk":
            digits = "".join(c for c in str(code) if c.isdigit()).zfill(5)
            df = ak.stock_hk_daily(symbol=digits, adjust=adjust)
            df.attrs["market_source"] = "AKShare.stock_hk_daily (Sina)"
        elif market == "us":
            clean = str(code).strip().upper()
            if clean.endswith(".US"):
                clean = clean[:-3]
            df = ak.stock_us_daily(symbol=clean, adjust=adjust)
            df.attrs["market_source"] = "AKShare.stock_us_daily (Sina)"
        else:
            raise ValueError(f"Unsupported market for kline fallback: {market}")

        if df.empty:
            raise RuntimeError(f"No K-line data returned for {code}")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date").sort_index()

        # Sanitize numeric types and OHLC consistency across split adjustments
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"] = df[["low", "open", "close"]].min(axis=1)

        # Slice relevant time window
        history_multiplier = {"daily": 5, "weekly": 10, "monthly": 40}.get(period, 5)
        needed_bars = max(count * history_multiplier, count + 100)
        df = df.tail(needed_bars).copy()

        if period in {"weekly", "monthly"}:
            rule = "W-FRI" if period == "weekly" else "ME"
            df = df.resample(rule).agg({
                "open": "first", "high": "max", "low": "min", "close": "last",
                "volume": "sum",
            }).dropna(subset=["open", "close"])

        df = df.reset_index()
        previous_close = df["close"].shift(1)
        df["change_pct"] = (df["close"] / previous_close - 1) * 100
        target_date_col = "时间" if period in {"30", "60", "120"} else "日期"
        frame = df.rename(columns={
            "date": target_date_col,
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "change_pct": "涨跌幅",
        })
        frame["成交额"] = frame["收盘"] * frame["成交量"]

    return frame


SINA_INDEX_SYMBOLS = {
    "道琼斯": ".dji",
    "标普500": ".inx",
    "纳斯达克": ".ixic",
}


def get_global_index_history(symbol: str) -> pd.DataFrame:
    """Fetch global index historical data (e.g. 道琼斯, 标普500, 纳斯达克) with Sina and AKShare fallback."""
    yf_sym = OVERNIGHT_SYMBOLS.get(symbol)
    if yf_sym and yf is not None:
        try:
            ticker = yf.Ticker(yf_sym)
            df = ticker.history(period="1mo")
            if df is not None and not df.empty:
                df = df.reset_index()
                date_col = "Datetime" if "Datetime" in df.columns else "Date"
                df = df.rename(columns={date_col: "日期", "Close": "最新价"})
                df["日期"] = pd.to_datetime(df["日期"]).dt.tz_localize(None)
                previous = df["最新价"].shift(1)
                df["涨跌幅"] = (df["最新价"] / previous - 1) * 100
                df["涨跌额"] = df["最新价"] - previous
                return df
        except Exception:
            pass

    # 2. Resilient fallback to Sina US Daily K API
    sina_sym = SINA_INDEX_SYMBOLS.get(symbol)
    if sina_sym:
        try:
            url = f"https://stock.finance.sina.com.cn/usstock/api/json.php/US_MinKService.getDailyK?symbol={sina_sym}"
            req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if raw_data and isinstance(raw_data, list):
                df = pd.DataFrame(raw_data[-60:])
                df = df.rename(columns={"d": "日期", "c": "最新价", "o": "开盘", "h": "最高", "l": "最低", "v": "成交量"})
                df["最新价"] = df["最新价"].astype(float)
                df["日期"] = pd.to_datetime(df["日期"])
                prev = df["最新价"].shift(1)
                df["涨跌额"] = df["最新价"] - prev
                df["涨跌幅"] = (df["最新价"] / prev - 1) * 100
                return df
        except Exception:
            pass

    # 3. Last resort fallback to AKShare
    import akshare as ak
    return ak.index_global_hist_em(symbol=symbol)

