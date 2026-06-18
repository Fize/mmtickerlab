#!/usr/bin/env python3
"""
Pre-Market Data Aggregator (盘前数据聚合器)

Fetches ALL available pre-market data and outputs a complete trading plan
in markdown format. Every field is auto-filled — no manual placeholders.

Usage:
    skills/market/.venv/bin/python skills/market/scripts/pre_market.py [--date YYYYMMDD]
    
    # Pipe directly into journal:
    skills/market/.venv/bin/python skills/market/scripts/pre_market.py | \\
        skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py create

    # Save to file for preview:
    skills/market/.venv/bin/python skills/market/scripts/pre_market.py > /tmp/plan.md

Data Sources (all via akshare):
    Module 1: index_global_spot_em, futures_global_spot_em, fx_spot_quote,
              stock_info_global_em, news_cctv
    Module 2: stock_zh_a_spot, stock_zt_pool_em, stock_fund_flow_concept,
              stock_fund_flow_industry
    Module 3: derived from Module 2 + global news
    Module 4: watchlist.json + stock_zh_a_hist + indicators
    Module 5: calculated from Module 2 data
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import time
import warnings

# --- Path setup: allow importing sibling modules ---
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# Project root and data paths
PROJECT_ROOT = SCRIPT_DIR.parents[2]
WATCHLIST_PATH = PROJECT_ROOT / "data" / "watchlist.json"
STOCK_NAMES_PATH = PROJECT_ROOT / "data" / "stock_names.json"

# ─── Helpers ─────────────────────────────────────────────────────────────────

def last_trading_day(ref_date: datetime) -> datetime:
    """Walk backward from ref_date to find the most recent Mon-Fri."""
    d = ref_date
    for _ in range(10):
        if d.weekday() < 5:
            return d
        d -= timedelta(days=1)
    return ref_date  # fallback

def fmt_pct(v, default="N/A"):
    """Format a numeric value as +/-XX.XX%"""
    try:
        return f"{float(v):+.2f}%"
    except (ValueError, TypeError):
        return default

def fmt_price(v, default="N/A"):
    """Format a numeric value as .2f price"""
    try:
        return f"{float(v):.2f}"
    except (ValueError, TypeError):
        return default

def safe_float(v, fallback=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return fallback

def load_stock_names() -> dict:
    """Load cached stock name lookup."""
    if STOCK_NAMES_PATH.exists():
        try:
            return json.loads(STOCK_NAMES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def load_watchlist() -> list:
    """Load watchlist from data/watchlist.json."""
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─── Module 1: 宏观与外围环境 ──────────────────────────────────────────────

def fetch_global_macro() -> dict:
    """
    Fetch A50 futures, US indices, RMB, HSI, and macro news.
    Returns a dict with all fields populated.
    """
    result = {
        "a50": {"name": "富时A50当月连续", "price": "N/A", "change_pct": "N/A", "change": "N/A"},
        "us_djia": {"name": "道琼斯", "price": "N/A", "change_pct": "N/A"},
        "us_spx": {"name": "标普500", "price": "N/A", "change_pct": "N/A"},
        "us_ndx": {"name": "纳斯达克", "price": "N/A", "change_pct": "N/A"},
        "hsi": {"name": "恒生指数", "price": "N/A", "change_pct": "N/A"},
        "rmb": {"pair": "USD/CNY", "bid": "N/A", "ask": "N/A"},
        "news": [],
        "errors": []
    }

    # --- Global Indices (US + HK + others) ---
    try:
        df = ak.index_global_spot_em()
        if df is not None and not df.empty:
            targets = {
                "DJIA": "us_djia", "SPX": "us_spx", "NDX": "us_ndx", "HSI": "hsi"
            }
            for _, row in df.iterrows():
                code = str(row.get("代码", ""))
                if code in targets:
                    key = targets[code]
                    result[key]["price"] = fmt_price(row.get("最新价"))
                    result[key]["change_pct"] = fmt_pct(row.get("涨跌幅"))
                    result[key]["change"] = fmt_price(row.get("涨跌额"))
    except Exception as e:
        result["errors"].append(f"全球指数: {e}")

    # --- A50 Futures ---
    try:
        df = ak.futures_global_spot_em()
        if df is not None and not df.empty:
            a50_row = df[df["名称"].str.contains("A50期指当月连续", na=False)]
            if not a50_row.empty:
                r = a50_row.iloc[0]
                result["a50"]["price"] = fmt_price(r.get("最新价"))
                result["a50"]["change_pct"] = fmt_pct(r.get("涨跌幅"))
                result["a50"]["change"] = fmt_price(r.get("涨跌额"))
    except Exception as e:
        result["errors"].append(f"A50期货: {e}")

    # --- RMB ---
    try:
        df = ak.fx_spot_quote()
        if df is not None and not df.empty:
            usd_row = df[df["货币对"] == "USD/CNY"]
            if not usd_row.empty:
                r = usd_row.iloc[0]
                result["rmb"]["bid"] = fmt_price(r.get("买报价"))
                result["rmb"]["ask"] = fmt_price(r.get("卖报价"))
    except Exception as e:
        result["errors"].append(f"人民币汇率: {e}")

    # --- Macro News (East Money global) ---
    try:
        df = ak.stock_info_global_em()
        if df is not None and not df.empty:
            for _, row in df.head(8).iterrows():
                title = str(row.get("标题", ""))
                pub_time = str(row.get("发布时间", ""))[:16]
                summary = str(row.get("摘要", ""))
                # Keep only relevant macro/policy news
                keywords = ["央行", "证监会", "政策", "利率", "经济", "市场", "A股", 
                           "美股", "汇率", "贸易", "关税", "部委", "国务院", "商务部",
                           "美联储", "通胀", "GDP", "PMI", "A50", "外资", "北向"]
                if any(kw in title for kw in keywords) or not result["news"]:
                    result["news"].append({
                        "title": title[:80],
                        "time": pub_time,
                        "summary": summary[:120] if summary else ""
                    })
                    if len(result["news"]) >= 5:
                        break
    except Exception as e:
        result["errors"].append(f"宏观新闻: {e}")

    return result


# ─── Module 2: 市场情绪与资金记忆 ──────────────────────────────────────────

def fetch_market_sentiment(date_str: str) -> dict:
    """
    Fetch yesterday's market breadth, limit-up pool, and fund flows.
    """
    result = {
        "indices": [],
        "breadth": {
            "total": 0, "rising": 0, "falling": 0, "flat": 0,
            "limit_up": 0, "limit_down": 0,
            "mean_change": 0.0, "median_change": 0.0,
            "total_amount": 0.0  # 亿
        },
        "limit_up_pool": [],
        "top_concepts": [],
        "top_industries": [],
        "sentiment_judgment": "",
        "errors": []
    }

    # --- Major Indices ---
    target_indices = {
        "000001": "上证指数", "399001": "深证成指", "399006": "创业板指",
        "000300": "沪深300", "000016": "上证50", "000905": "中证500", "000852": "中证1000"
    }
    try:
        # Try Sina direct first
        try:
            symbols = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000300",
                       "s_sh000016", "s_sh000905", "s_sh000852"]
            url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
            r = akshare_patch.original_get(url, headers={"Referer": "http://finance.sina.com.cn"}, timeout=5)
            r.raise_for_status()
            for line in r.text.strip().split("\n"):
                if not line.startswith("var hq_str_s_"):
                    continue
                eq_idx = line.find("=")
                if eq_idx == -1:
                    continue
                code = line[11:eq_idx][-6:]
                s = line.find('"')
                e = line.rfind('"')
                if s == -1 or e == -1 or s >= e:
                    continue
                parts = line[s+1:e].split(",")
                if len(parts) < 6:
                    continue
                name = target_indices.get(code, parts[0])
                result["indices"].append({
                    "code": code, "name": name,
                    "price": safe_float(parts[1]),
                    "change_pct": safe_float(parts[3]),
                    "change": safe_float(parts[2]),
                })
        except Exception:
            df_idx = ak.stock_zh_index_spot_em(symbol="上证系列指数")
            if df_idx is not None and not df_idx.empty:
                for _, row in df_idx.iterrows():
                    code = str(row.get("代码", ""))
                    if code in target_indices:
                        result["indices"].append({
                            "code": code, "name": target_indices[code],
                            "price": safe_float(row.get("最新价")),
                            "change_pct": safe_float(row.get("涨跌幅")),
                            "change": safe_float(row.get("涨跌额")),
                        })
    except Exception as e:
        result["errors"].append(f"指数数据: {e}")

    # --- Market Breadth (spot data, try EM then Sina) ---
    try:
        df_spot = None
        # Try East Money first
        try:
            df_spot = ak.stock_zh_a_spot_em()
        except Exception:
            pass
        
        # Fallback to Sina
        if df_spot is None or df_spot.empty:
            try:
                df_spot = ak.stock_zh_a_spot()
                if df_spot is not None and not df_spot.empty:
                    df_spot["代码"] = df_spot["代码"].str[-6:]
            except Exception:
                pass

        if df_spot is not None and not df_spot.empty:
            df_spot["涨跌幅"] = pd.to_numeric(df_spot["涨跌幅"], errors="coerce")
            df_spot["成交额"] = pd.to_numeric(df_spot["成交额"], errors="coerce")

            total = len(df_spot)
            rising = (df_spot["涨跌幅"] > 0).sum()
            falling = (df_spot["涨跌幅"] < 0).sum()
            flat = total - rising - falling
            limit_up = (df_spot["涨跌幅"] >= 9.9).sum()
            limit_down = (df_spot["涨跌幅"] <= -9.9).sum()

            result["breadth"] = {
                "total": total,
                "rising": int(rising),
                "falling": int(falling),
                "flat": int(flat),
                "limit_up": int(limit_up),
                "limit_down": int(limit_down),
                "mean_change": round(df_spot["涨跌幅"].mean(), 2),
                "median_change": round(df_spot["涨跌幅"].median(), 2),
                "total_amount": round(df_spot["成交额"].sum() / 1e8, 0),  # 亿
            }
    except Exception as e:
        result["errors"].append(f"市场宽度: {e}")

    # --- Limit-Up Pool ---
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if df_zt is not None and not df_zt.empty:
            # Sort by 连板数 desc, then 封板资金 desc
            if "连板数" in df_zt.columns:
                df_zt = df_zt.sort_values(by=["连板数", "封板资金"], ascending=[False, False])
            
            for _, row in df_zt.head(20).iterrows():
                item = {
                    "code": str(row.get("代码", "")),
                    "name": str(row.get("名称", "")),
                    "price": safe_float(row.get("最新价")),
                    "change_pct": safe_float(row.get("涨跌幅")),
                    "limit_up_days": int(row.get("连板数", 0)) if pd.notna(row.get("连板数")) else 0,
                    "industry": str(row.get("所属行业", "")),
                    "turnover_rate": safe_float(row.get("换手率")),
                    "sealing_funds": safe_float(row.get("封板资金", 0)),
                }
                # Include breakout count (炸板次数) if available
                if "炸板次数" in row and pd.notna(row["炸板次数"]):
                    item["break_times"] = int(row["炸板次数"])
                result["limit_up_pool"].append(item)
            
            # Count by industry
            if result["limit_up_pool"]:
                industry_counts = {}
                for item in result["limit_up_pool"]:
                    ind = item.get("industry", "其他")
                    industry_counts[ind] = industry_counts.get(ind, 0) + 1
                result["top_zt_industries"] = sorted(
                    industry_counts.items(), key=lambda x: x[1], reverse=True
                )[:5]
    except Exception as e:
        result["errors"].append(f"涨停池: {e}")

    # --- Concept Fund Flow (今日即时) ---
    try:
        df_concept = ak.stock_fund_flow_concept(symbol="即时")
        if df_concept is not None and not df_concept.empty:
            top = df_concept.head(5)
            for _, row in top.iterrows():
                result["top_concepts"].append({
                    "name": str(row.get("行业", "")),
                    "net_flow": safe_float(row.get("净额", 0)),
                    "change_pct": safe_float(row.get("行业-涨跌幅", 0)),
                    "top_stock": str(row.get("领涨股", "")),
                    "top_stock_change": safe_float(row.get("领涨股-涨跌幅", 0)),
                })
    except Exception as e:
        result["errors"].append(f"概念资金流向: {e}")

    # --- Industry Fund Flow ---
    try:
        df_ind = ak.stock_fund_flow_industry(symbol="即时")
        if df_ind is not None and not df_ind.empty:
            top = df_ind.head(5)
            for _, row in top.iterrows():
                result["top_industries"].append({
                    "name": str(row.get("行业", "")),
                    "net_flow": safe_float(row.get("净额", 0)),
                    "change_pct": safe_float(row.get("行业-涨跌幅", 0)),
                    "top_stock": str(row.get("领涨股", "")),
                })
    except Exception as e:
        result["errors"].append(f"行业资金流向: {e}")

    return result


# ─── Module 4: 自选股技术分析 ─────────────────────────────────────────────

def fetch_watchlist_analysis(watchlist_codes: list) -> list:
    """
    For each watchlist stock, fetch K-line data, compute indicators,
    and return a structured analysis dict.
    """
    import indicators as ind_mod
    results = []

    end_date = datetime.now()
    start_date = end_date - timedelta(days=500)
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    for code in watchlist_codes:
        code = str(code).strip()
        if len(code) != 6 or not code.isdigit():
            continue

        stock_info = {"code": code, "name": code, "status": "ok", "setup": None, "errors": []}

        try:
            # Fetch K-line
            k_df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                       start_date=start_str, end_date=end_str, adjust="qfq")
            if k_df is None or k_df.empty:
                stock_info["status"] = "no_data"
                results.append(stock_info)
                continue

            # Rename to English for indicators
            rename_map = {"日期": "Date", "开盘": "Open", "最高": "High",
                         "最低": "Low", "收盘": "Close", "成交量": "Volume"}
            k_df = k_df.rename(columns=rename_map)

            # Compute indicators
            ind_df = ind_mod.calculate_all_indicators(k_df)

            if ind_df.empty:
                stock_info["status"] = "no_indicator"
                results.append(stock_info)
                continue

            latest = ind_df.iloc[-1]
            prev = ind_df.iloc[-2] if len(ind_df) > 1 else latest
            prev5 = ind_df.iloc[-6] if len(ind_df) > 5 else latest

            # Stock name
            stock_info["name"] = str(latest.get("Date", code))

            close = safe_float(latest.get("Close", 0))
            sma_5 = safe_float(latest.get("SMA_5", close))
            sma_10 = safe_float(latest.get("SMA_10", close))
            sma_20 = safe_float(latest.get("SMA_20", close))
            sma_60 = safe_float(latest.get("SMA_60", close))
            boll_upper = safe_float(latest.get("BOLL_UP", close * 1.1))
            boll_mid = safe_float(latest.get("BOLL_MID", close))
            boll_lower = safe_float(latest.get("BOLL_LB", close * 0.9))
            atr = safe_float(latest.get("ATR", close * 0.02))
            rsi_6 = safe_float(latest.get("RSI_6", 50))
            macd_val = safe_float(latest.get("MACD", 0))
            dif = safe_float(latest.get("DIF", 0))
            dea = safe_float(latest.get("DEA", 0))
            kdj_k = safe_float(latest.get("KDJ_K", 50))
            kdj_d = safe_float(latest.get("KDJ_D", 50))
            kdj_j = safe_float(latest.get("KDJ_J", 50))

            stock_info["technicals"] = {
                "close": close, "sma_5": sma_5, "sma_10": sma_10,
                "sma_20": sma_20, "sma_60": sma_60,
                "boll_upper": boll_upper, "boll_mid": boll_mid, "boll_lower": boll_lower,
                "atr": atr, "rsi_6": rsi_6,
                "macd_val": macd_val, "dif": dif, "dea": dea,
                "kdj_k": kdj_k, "kdj_d": kdj_d, "kdj_j": kdj_j,
            }

            # --- AI-Ready Setup Detection ---
            setups = []

            # 1. Pullback to SMA_20 with bullish KDJ
            if close > sma_20 * 0.98 and close <= sma_20 * 1.02 and kdj_j < 30:
                setups.append({
                    "type": "均线支撑回踩",
                    "signal": "回踩MA20附近，KDJ低位拐头预期",
                    "support": round(sma_20, 2),
                    "resistance_target": round(boll_mid, 2),
                    "stop_loss_zone": round(min(sma_60, sma_20 * 0.97), 2),
                })

            # 2. Breakout above BOLL mid with volume confirmation
            prev_close = safe_float(prev.get("Close", close))
            if prev_close <= boll_mid < close and rsi_6 > 40 and rsi_6 < 70:
                setups.append({
                    "type": "布林中轨突破",
                    "signal": "突破BOLL中轨，若放量可追",
                    "support": round(boll_mid, 2),
                    "resistance_target": round(boll_upper, 2),
                    "stop_loss_zone": round(boll_mid * 0.98, 2),
                })

            # 3. Golden cross (MACD just turned positive)
            prev_macd = safe_float(prev.get("MACD", 0))
            if macd_val > 0 and prev_macd <= 0 and dif > dea:
                setups.append({
                    "type": "MACD金叉",
                    "signal": "MACD零轴附近金叉，趋势转多信号",
                    "support": round(sma_20, 2),
                    "resistance_target": round(close * 1.05, 2),
                    "stop_loss_zone": round(sma_20 * 0.97, 2),
                })

            # 4. Bounce off BOLL lower band (oversold)
            if close <= boll_lower * 1.02 and rsi_6 < 30:
                setups.append({
                    "type": "布林下轨超跌反弹",
                    "signal": "触及布林下轨+RSI超卖，有反弹需求",
                    "support": round(boll_lower, 2),
                    "resistance_target": round(boll_mid, 2),
                    "stop_loss_zone": round(boll_lower * 0.97, 2),
                })

            # 5. Trend strength: close above all major MAs
            if close > sma_5 > sma_10 > sma_20 > sma_60:
                setups.append({
                    "type": "多头排列",
                    "signal": "均线多头排列，趋势强劲",
                    "support": round(sma_10, 2),
                    "resistance_target": round(close * 1.08, 2),
                    "stop_loss_zone": round(sma_20, 2),
                })

            stock_info["setups"] = setups

        except Exception as e:
            stock_info["status"] = "error"
            stock_info["errors"].append(str(e))

        results.append(stock_info)

    return results


# ─── Module 5: 市场温度计算 ────────────────────────────────────────────────

def calculate_temperature(breadth: dict) -> tuple:
    """
    Calculate market temperature and recommended position limit.
    Returns (temperature_label, position_limit_pct).
    """
    limit_up = breadth.get("limit_up", 0)
    limit_down = breadth.get("limit_down", 0)
    rising = breadth.get("rising", 0)
    total = breadth.get("total", 1)
    rising_ratio = (rising / total * 100) if total > 0 else 50

    if limit_up >= 80 and limit_down < 10 and rising_ratio > 60:
        return ("🔥 微暖", 70)
    elif limit_up >= 40 and limit_down < 30:
        return ("☀️ 正常", 50)
    elif limit_up >= 20 and limit_down < 50:
        return ("🌥 偏冷", 20)
    else:
        return ("❄️ 冰冷", 10)


# ─── Output Formatter ────────────────────────────────────────────────────────

def format_output(date_str: str, macro: dict, sentiment: dict,
                  watchlist_data: list, date_display: str) -> str:
    """Assemble all data into the complete markdown plan."""
    breadth = sentiment["breadth"]

    lines = []
    a = lines.append

    a(f"【今日盘前数据汇总 {date_display}】")
    a("")
    a("> 🤖 本数据由 pre_market.py 自动汇总，所有数据字段均由系统采集。")
    a(f"> 生成时间：{now_str()} | 参考交易日：{date_display}")
    a("")

    # ═══════════════════════════════════════════════════════════════════════
    # 模块一：宏观与外围环境
    # ═══════════════════════════════════════════════════════════════════════
    a("## 一、宏观与外围环境")
    a("")
    a("| 观察项 | 最新数据 | 涨跌幅 |")
    a("|:---|:---|:---|")

    # A50
    a50 = macro["a50"]
    a(f"| {a50['name']} | {a50['price']} | {a50['change_pct']} |")

    # RMB
    rmb = macro["rmb"]
    a(f"| {rmb['pair']} | 买{rmb['bid']} / 卖{rmb['ask']} | - |")

    # US Indices
    for key, label in [("us_djia", "道琼斯"), ("us_spx", "标普500"), ("us_ndx", "纳斯达克")]:
        idx = macro[key]
        a(f"| {idx['name']} | {idx['price']} | {idx['change_pct']} |")

    # HSI
    hsi = macro["hsi"]
    a(f"| {hsi['name']} | {hsi['price']} | {hsi['change_pct']} |")

    a("")

    # Macro news
    if macro["news"]:
        a("### 宏观消息面")
        a("")
        for n in macro["news"]:
            a(f"- **[{n['time']}]** {n['title']}")
            if n.get("summary"):
                a(f"  > {n['summary']}")
        a("")
    else:
        a("### 宏观消息面")
        a("")
        a("暂无重大宏观消息。")
        a("")

    # ═══════════════════════════════════════════════════════════════════════
    # 模块二：市场情绪与资金记忆
    # ═══════════════════════════════════════════════════════════════════════
    a("## 二、市场情绪与资金记忆（找风口）")
    a("")

    # Indices
    if sentiment["indices"]:
        a("### 主要指数")
        a("")
        a("| 指数 | 收盘价 | 涨跌幅 | 涨跌额 |")
        a("|:---|:---|:---|:---|")
        for idx in sentiment["indices"]:
            a(f"| {idx['name']} | {idx['price']:.2f} | {idx['change_pct']:+.2f}% | {idx['change']:+.2f} |")
        a("")

    # Breadth
    b = breadth
    a("### 市场宽度")
    a("")
    if b["total"] > 0:
        rising_pct = b["rising"] / b["total"] * 100 if b["total"] > 0 else 0
        falling_pct = b["falling"] / b["total"] * 100 if b["total"] > 0 else 0
        a(f"- 上涨：**{b['rising']}** 家（{rising_pct:.1f}%）| 下跌：**{b['falling']}** 家（{falling_pct:.1f}%）| 平盘：{b['flat']} 家")
        a(f"- 涨停：**{b['limit_up']}** 家 | 跌停：**{b['limit_down']}** 家")
        a(f"- 平均涨幅：{b['mean_change']:+.2f}% | 中位数涨幅：{b['median_change']:+.2f}%")
        a(f"- 两市成交额：**{b['total_amount']:.0f} 亿**")
    else:
        a("市场宽度数据暂不可用（可能非交易时段）。")
    a("")

    # Limit-up pool
    if sentiment["limit_up_pool"]:
        a("### 涨停股池（前15）")
        a("")
        a("| 代码 | 名称 | 现价 | 涨幅 | 连板 | 所属行业 | 换手率 |")
        a("|:---|:---|:---|:---|:---|:---|:---|")
        for item in sentiment["limit_up_pool"][:15]:
            days_str = f"{item['limit_up_days']}板" if item["limit_up_days"] > 0 else "首板"
            turnover = f"{item.get('turnover_rate', 0):.1f}%" if item.get("turnover_rate", 0) > 0 else "-"
            a(f"| {item['code']} | {item['name']} | {item['price']:.2f} | {item['change_pct']:+.2f}% | {days_str} | {item.get('industry','-')} | {turnover} |")
        a("")

        # Top ZT industries
        if sentiment.get("top_zt_industries"):
            a("### 涨停集中行业")
            a("")
            for ind_name, cnt in sentiment["top_zt_industries"]:
                a(f"- **{ind_name}**：{cnt} 家涨停")
            a("")

        # Highest board
        max_board = max((item["limit_up_days"] for item in sentiment["limit_up_pool"]), default=0)
        if max_board > 0:
            max_item = next((item for item in sentiment["limit_up_pool"] if item["limit_up_days"] == max_board), None)
            if max_item:
                a(f"**最高连板：{max_board} 连板** → {max_item['name']}（{max_item['code']}，{max_item.get('industry','-')}）")
                a("")

    # Top concepts (fund flow)
    if sentiment["top_concepts"]:
        a("### 资金流入 Top 5 概念板块")
        a("")
        a("| 板块 | 净流入(亿) | 涨幅 | 领涨股 | 领涨涨幅 |")
        a("|:---|:---|:---|:---|:---|")
        for c in sentiment["top_concepts"]:
            a(f"| {c['name']} | {c['net_flow']:.2f} | {c['change_pct']:+.2f}% | {c['top_stock']} | {c['top_stock_change']:+.2f}% |")
        a("")

    # Industry fund flow
    if sentiment["top_industries"]:
        a("### 资金流入 Top 5 行业板块")
        a("")
        a("| 行业 | 净流入(亿) | 涨幅 | 领涨股 |")
        a("|:---|:---|:---|:---|")
        for ind in sentiment["top_industries"][:5]:
            a(f"| {ind['name']} | {ind['net_flow']:.2f} | {ind['change_pct']:+.2f}% | {ind['top_stock']} |")
        a("")

    # ═══════════════════════════════════════════════════════════════════════
    # 模块三：昨日资金与涨停数据
    # ═══════════════════════════════════════════════════════════════════════
    a("## 三、昨日资金与涨停数据")
    a("")

    # Top concepts (fund flow)
    if sentiment["top_concepts"]:
        a("### 资金流入Top5概念板块")
        a("")
        a("| 板块 | 净流入(亿) | 涨幅 | 领涨股 | 领涨涨幅 |")
        a("|:---|:---|:---|:---|:---|")
        for c in sentiment["top_concepts"]:
            a(f"| {c['name']} | {c['net_flow']:.2f} | {c['change_pct']:+.2f}% | {c['top_stock']} | {c['top_stock_change']:+.2f}% |")
        a("")

    # Top ZT industries
    if sentiment.get("top_zt_industries"):
        a("### 涨停集中行业")
        a("")
        for ind_name, cnt in sentiment["top_zt_industries"]:
            a(f"- **{ind_name}**：{cnt} 家涨停")
        a("")

    # ═══════════════════════════════════════════════════════════════════════
    # 模块四：自选股技术指标
    # ═══════════════════════════════════════════════════════════════════════
    a("## 四、自选股技术指标")
    a("")

    if not watchlist_data:
        a("⚠️ 自选股列表为空。请先在 `data/watchlist.json` 中添加关注标的。")
        a("")
    else:
        for stock in watchlist_data:
            code = stock["code"]
            name = stock.get("name", code)
            techs = stock.get("technicals")
            status = stock.get("status", "ok")

            if status != "ok" or not techs:
                continue

            a(f"### {name}（{code}）")
            a("")
            close = techs.get("close", "N/A")
            a(f"- 收盘价：{close}")
            a(f"- MA5={techs.get('sma_5','N/A')} | MA10={techs.get('sma_10','N/A')} | MA20={techs.get('sma_20','N/A')} | MA60={techs.get('sma_60','N/A')}")
            a(f"- BOLL：上轨={techs.get('boll_upper','N/A')} | 中轨={techs.get('boll_mid','N/A')} | 下轨={techs.get('boll_lower','N/A')}")
            a(f"- RSI(6)={techs.get('rsi_6','N/A')} | MACD：DIF={techs.get('dif','N/A')} DEA={techs.get('dea','N/A')} 柱={techs.get('macd_val','N/A')}")
            a(f"- KDJ：K={techs.get('kdj_k','N/A')} D={techs.get('kdj_d','N/A')} J={techs.get('kdj_j','N/A')}")
            a("")

        stocks_error = [s for s in watchlist_data if s.get("status") not in ("ok",)]
        for stock in stocks_error:
            a(f"- ⚠️ **{stock['code']}**：数据获取失败 — {'; '.join(stock.get('errors', ['未知错误']))}")
        if stocks_error:
            a("")

    # ═══════════════════════════════════════════════════════════════════════
    # 模块五：市场数据摘要
    # ═══════════════════════════════════════════════════════════════════════
    a("## 五、市场数据摘要")
    a("")
    a(f"- 涨停 **{breadth['limit_up']}** 家 / 跌停 **{breadth['limit_down']}** 家")
    a(f"- 上涨占比 **{breadth['rising']/max(breadth['total'],1)*100:.1f}%**")
    a(f"- 两市成交额 **{breadth['total_amount']:.0f} 亿**")
    a("")

    # Errors section
    all_errors = macro.get("errors", []) + sentiment.get("errors", [])
    if all_errors:
        a("---")
        a("")
        a("### ⚠️ 数据获取异常")
        a("")
        for err in all_errors:
            a(f"- {err}")
        a("")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pre-market plan data aggregator (盘前计划自动生成器)"
    )
    parser.add_argument("--date", type=str, default=None,
                        help="Reference trading date in YYYYMMDD (default: last trading day)")
    args = parser.parse_args()

    # Determine date
    today = datetime.now()
    if args.date:
        ref_date = datetime.strptime(args.date, "%Y%m%d")
    else:
        ref_date = last_trading_day(today - timedelta(days=1))

    date_str = ref_date.strftime("%Y%m%d")
    date_display = ref_date.strftime("%Y-%m-%d")

    print(f"[pre_market] 参考交易日: {date_display} ({'周' + '一二三四五六日'[ref_date.weekday()]})", file=sys.stderr)
    print(f"[pre_market] 开始采集数据...", file=sys.stderr)

    # ── Module 1: Macro ──
    print("[pre_market] 模块一：宏观与外围环境...", file=sys.stderr)
    t0 = time.time()
    macro = fetch_global_macro()
    print(f"[pre_market]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # ── Module 2: Market Sentiment ──
    print("[pre_market] 模块二：市场情绪与资金记忆...", file=sys.stderr)
    t0 = time.time()
    sentiment = fetch_market_sentiment(date_str)
    print(f"[pre_market]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # ── Module 4: Watchlist Analysis ──
    print("[pre_market] 模块四：自选股技术分析...", file=sys.stderr)
    t0 = time.time()
    watchlist = load_watchlist()
    if watchlist:
        print(f"[pre_market]   自选股数量: {len(watchlist)}", file=sys.stderr)
        watchlist_data = fetch_watchlist_analysis(watchlist)
    else:
        watchlist_data = []
    print(f"[pre_market]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # ── Format & Output ──
    print("[pre_market] 生成交易计划...", file=sys.stderr)
    output = format_output(date_str, macro, sentiment, watchlist_data, date_display)

    print(output)


if __name__ == "__main__":
    main()
