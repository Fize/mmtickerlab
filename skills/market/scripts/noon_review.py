#!/usr/bin/env python3
"""
Noon Review Generator (午间盘面数据汇总)

Fetches real-time morning market data and checks against the morning
trading plan to generate a complete noon review report.

Usage:
    skills/market/.venv/bin/python skills/market/scripts/noon_review.py
    
    # Pipe directly into journal:
    skills/market/.venv/bin/python skills/market/scripts/noon_review.py | \\
        skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py append --section noon
    
    # Save to file:
    skills/market/.venv/bin/python skills/market/scripts/noon_review.py > /tmp/noon.md

Data Sources:
    Section 1: Sina index spot, stock_zh_a_spot (Sina/EM), stock_zt_pool_em
    Section 2: stock_fund_flow_concept, stock_fund_flow_big_deal
    Section 3: data/journal/YYYYMMDD.md (morning plan) + real-time stock quotes
    Section 4: AI-derived strategy from Section 1-3 data
"""

import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import time
import warnings

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = SCRIPT_DIR.parents[2]
JOURNAL_DIR = PROJECT_ROOT / "data" / "journal"
WATCHLIST_PATH = PROJECT_ROOT / "data" / "watchlist.json"

# ─── Helpers ─────────────────────────────────────────────────────────────────

def safe_float(v, fallback=0.0):
    try: return float(v)
    except (ValueError, TypeError): return fallback

def fmt_pct(v, default="N/A"):
    try: return f"{float(v):+.2f}%"
    except: return default

def fmt_price(v, default="N/A"):
    try: return f"{float(v):.2f}"
    except: return default

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_watchlist():
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list): return data
        except: pass
    return []

def find_today_journal():
    """Find today's journal file if it exists."""
    today = datetime.now().strftime("%Y%m%d")
    path = JOURNAL_DIR / f"{today}.md"
    return path if path.exists() else None

def extract_plan_stocks(journal_path):
    """
    Parse the morning plan to extract stock codes mentioned in section 四.
    Returns list of stock codes.
    """
    if not journal_path:
        return []
    content = journal_path.read_text(encoding="utf-8")
    # Find stock codes: 6-digit numbers, often in parentheses like (600519)
    codes = set()
    # Pattern: (XXXXXX) where X is digit
    for m in re.finditer(r'\((\d{6})\)', content):
        codes.add(m.group(1))
    # Also look for bare 6-digit codes in the plan section
    plan_section = content.split("## 午间复盘")[0] if "## 午间复盘" in content else content
    for m in re.finditer(r'\b(\d{6})\b', plan_section):
        codes.add(m.group(1))
    return list(codes)


# ─── Section 1: Morning Market Snapshot ─────────────────────────────────────

def fetch_morning_snapshot() -> dict:
    """Fetch real-time morning market data."""
    result = {
        "indices": [],
        "breadth": {},
        "volume_vs_yesterday": "",
        "errors": []
    }

    # --- Indices ---
    target_indices = {
        "000001": "上证指数", "399001": "深证成指", "399006": "创业板指"
    }
    try:
        symbols = ["s_sh000001", "s_sz399001", "s_sz399006"]
        url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
        r = akshare_patch.original_get(url,
            headers={"Referer": "http://finance.sina.com.cn"}, timeout=5)
        r.raise_for_status()
        for line in r.text.strip().split("\n"):
            if not line.startswith("var hq_str_s_"): continue
            eq_idx = line.find("=")
            if eq_idx == -1: continue
            code = line[11:eq_idx][-6:]
            s = line.find('"'); e = line.rfind('"')
            if s == -1 or e == -1 or s >= e: continue
            parts = line[s+1:e].split(",")
            if len(parts) < 6: continue
            name = target_indices.get(code, parts[0])
            result["indices"].append({
                "code": code, "name": name,
                "price": safe_float(parts[1]),
                "change_pct": safe_float(parts[3]),
                "change": safe_float(parts[2]),
            })
    except Exception as e:
        result["errors"].append(f"指数: {e}")

    # --- Breadth (try EM, then Sina) ---
    try:
        df_spot = None
        try: df_spot = ak.stock_zh_a_spot_em()
        except: pass
        if df_spot is None or df_spot.empty:
            try:
                df_spot = ak.stock_zh_a_spot()
                if df_spot is not None and not df_spot.empty:
                    df_spot["代码"] = df_spot["代码"].str[-6:]
            except: pass

        if df_spot is not None and not df_spot.empty:
            df_spot["涨跌幅"] = pd.to_numeric(df_spot["涨跌幅"], errors="coerce")
            df_spot["成交量"] = pd.to_numeric(df_spot["成交量"], errors="coerce")
            df_spot["成交额"] = pd.to_numeric(df_spot["成交额"], errors="coerce")

            total = len(df_spot)
            rising = int((df_spot["涨跌幅"] > 0).sum())
            falling = int((df_spot["涨跌幅"] < 0).sum())
            limit_up = int((df_spot["涨跌幅"] >= 9.9).sum())
            limit_down = int((df_spot["涨跌幅"] <= -9.9).sum())

            # 炸板率: stocks that once hit limit-up but closed below
            # Approximation: stocks with high > yesterday's limit-up price
            # but close < limit-up threshold. Use a simpler proxy.
            # For now: use zt_pool for炸板数据
            total_amount = df_spot["成交额"].sum() / 1e8  # 亿

            result["breadth"] = {
                "total": total, "rising": rising, "falling": falling,
                "flat": total - rising - falling,
                "limit_up": limit_up, "limit_down": limit_down,
                "total_amount": total_amount,
            }
    except Exception as e:
        result["errors"].append(f"市场宽度: {e}")

    # --- ZT Pool (for 炸板率) ---
    try:
        today_str = datetime.now().strftime("%Y%m%d")
        df_zt = ak.stock_zt_pool_em(date=today_str)
        if df_zt is not None and not df_zt.empty:
            total_zt = len(df_zt)
            # 炸板次数 > 0 means stock hit limit-up then broke
            if "炸板次数" in df_zt.columns:
                broken = int((df_zt["炸板次数"] > 0).sum())
                result["breadth"]["broken_board"] = broken
                result["breadth"]["broken_rate"] = round(broken / max(total_zt, 1) * 100, 1)
    except Exception:
        pass

    return result


# ─── Section 2: Fund Flow & Abnormal Moves ──────────────────────────────────

def fetch_fund_winds() -> dict:
    """Fetch leading sectors and big deal alerts."""
    result = {"top_concepts": [], "big_deals": [], "errors": []}

    # Concept fund flow (today real-time)
    try:
        df = ak.stock_fund_flow_concept(symbol="即时")
        if df is not None and not df.empty:
            top = df.head(5)
            for _, row in top.iterrows():
                result["top_concepts"].append({
                    "name": str(row.get("行业", "")),
                    "net_flow": safe_float(row.get("净额", 0)),
                    "change_pct": safe_float(row.get("行业-涨跌幅", 0)),
                    "top_stock": str(row.get("领涨股", "")),
                    "top_stock_chg": safe_float(row.get("领涨股-涨跌幅", 0)),
                })
    except Exception as e:
        result["errors"].append(f"概念流向: {e}")

    # Big deal flow (大单成交)
    try:
        df_bd = ak.stock_fund_flow_big_deal()
        if df_bd is not None and not df_bd.empty:
            for _, row in df_bd.head(8).iterrows():
                result["big_deals"].append({
                    "time": str(row.get("成交时间", "")),
                    "code": str(row.get("股票代码", "")),
                    "name": str(row.get("股票简称", "")),
                    "price": safe_float(row.get("成交价格", 0)),
                    "amount": safe_float(row.get("成交额", 0)) / 1e4,  # 万
                    "type": str(row.get("大单性质", "")),
                    "change_pct": safe_float(row.get("涨跌幅", 0)),
                })
    except Exception:
        pass  # Big deal data not critical

    return result


# ─── Section 3: Plan Alignment Check ────────────────────────────────────────

def check_plan_alignment(plan_stocks: list) -> list:
    """
    For each stock in the morning plan, fetch real-time prices and
    check if plan conditions were met.
    """
    results = []
    if not plan_stocks:
        return results

    for code in plan_stocks:
        code = str(code).strip()
        if len(code) != 6 or not code.isdigit():
            continue

        item = {"code": code, "name": code, "high": None, "low": None,
                "current": None, "change_pct": None, "status": "数据不可用",
                "error": None}

        try:
            # Try Sina direct for real-time quote
            market = "sh" if code.startswith(("60", "68", "51")) else \
                     "sz" if code.startswith(("00", "30")) else "bj"
            info = akshare_patch.get_single_stock_realtime(code)
            if info:
                item["name"] = info.get("name", code)
                item["high"] = info.get("high")
                item["low"] = info.get("low")
                item["current"] = info.get("price")
                item["change_pct"] = info.get("change_pct")
                item["open"] = info.get("open")
                item["pre_close"] = info.get("pre_close")

                # Simple status assessment
                chg = safe_float(item.get("change_pct", 0))
                if chg >= 9.5:
                    item["status"] = "涨停"
                elif chg <= -9.5:
                    item["status"] = "跌停"
                elif chg > 3:
                    item["status"] = "强势拉升中"
                elif chg > 0:
                    item["status"] = "小幅上涨"
                elif chg > -3:
                    item["status"] = "小幅回调"
                else:
                    item["status"] = "明显走弱"
            else:
                # Fallback: use East Money spot
                df = ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    row = df[df["代码"] == code]
                    if not row.empty:
                        r = row.iloc[0]
                        item["name"] = str(r.get("名称", code))
                        item["current"] = safe_float(r.get("最新价"))
                        item["change_pct"] = safe_float(r.get("涨跌幅"))
                        item["high"] = safe_float(r.get("最高"))
                        item["low"] = safe_float(r.get("最低"))
                        item["status"] = "已获取（EM源）"
        except Exception as e:
            item["error"] = str(e)[:60]
            item["status"] = "获取失败"

        results.append(item)

    return results


# ─── Section 4: Afternoon Strategy ──────────────────────────────────────────

def generate_afternoon_strategy(morning_data: dict, fund_data: dict) -> dict:
    """Generate afternoon trading strategy based on morning data."""
    breadth = morning_data.get("breadth", {})
    limit_up = breadth.get("limit_up", 0)
    limit_down = breadth.get("limit_down", 0)
    rising = breadth.get("rising", 0)
    total = breadth.get("total", 1)
    broken_rate = breadth.get("broken_rate", 0)
    rising_pct = rising / max(total, 1) * 100

    strategy = {"action": "", "risk_warning": "", "rationale": ""}

    # Determine market condition — prioritize absolute limit-up count over rate
    if limit_up >= 80 and limit_down < 10:
        strategy["action"] = "可积极操作，关注下午新发酵方向"
        strategy["risk_warning"] = "防范高位连板分歧，午后不追缩量涨停"
        strategy["rationale"] = f"上午涨停{limit_up}家，赚钱效应强，下午热度可延续"
    elif limit_up >= 50:
        if broken_rate > 50:
            strategy["action"] = "分歧加大，控仓参与，只做最强辨识度"
            strategy["risk_warning"] = "炸板率高，下午可能加速分歧，避免追高中位股"
            strategy["rationale"] = f"上午涨停{limit_up}家但炸板率{broken_rate}%，多空分歧剧烈"
        else:
            strategy["action"] = "可适度参与，尾盘允许低吸试错"
            strategy["risk_warning"] = "防范缩量回落，尾盘确认再出手"
            strategy["rationale"] = f"上午涨停{limit_up}家，炸板率{broken_rate}%，情绪正常"
    elif limit_up >= 20:
        strategy["action"] = "控仓参与，尾盘低吸试错"
        strategy["risk_warning"] = "防范缩量回落，弱势行情尾盘更安全"
        strategy["rationale"] = f"上午涨停{limit_up}家，情绪一般，精选个股"
    elif limit_up < 20 or rising_pct < 20:
        strategy["action"] = "建议减仓观望，不新开仓"
        strategy["risk_warning"] = "市场情绪低迷，下午可能加速退潮"
        strategy["rationale"] = f"上午涨停仅{limit_up}家，上涨占比{rising_pct:.0f}%，情绪偏冷"
    else:
        strategy["action"] = "维持现有仓位，等待尾盘信号"
        strategy["risk_warning"] = "防范午后突然跳水"
        strategy["rationale"] = "市场方向不明，多看少动"

    return strategy


# ─── Output Formatter ────────────────────────────────────────────────────────

def format_noon_output(morning: dict, fund: dict, plan_results: list,
                       strategy: dict) -> str:
    lines = []
    a = lines.append
    now = datetime.now()
    date_display = now.strftime("%Y-%m-%d")
    time_display = now.strftime("%H:%M")

    a(f"# ☀️ A股午间盘面数据汇总")
    a(f"报告时间: {date_display} {time_display}")
    a("")
    a(f"> 🤖 本数据由 noon_review.py 自动汇总。")
    a("")

    # ══ Section 1 ══
    a("## 1. 早盘数据快照")
    a("")

    # Indices
    if morning["indices"]:
        parts = []
        for idx in morning["indices"]:
            parts.append(f"{idx['name']} {fmt_price(idx['price'])}（{fmt_pct(idx['change_pct'])}）")
        a(f"* 三大指数: {' | '.join(parts)}")
    else:
        a("* 三大指数: 数据暂不可用")

    # Breadth
    b = morning.get("breadth", {})
    if b:
        total_amt = b.get("total_amount", 0)
        rising = b.get("rising", 0)
        falling = b.get("falling", 0)
        flat = b.get("flat", 0)
        lu = b.get("limit_up", 0)
        ld = b.get("limit_down", 0)
        br = b.get("broken_rate", None)

        a(f"* 涨跌分布: 上涨 **{rising}** 家 | 下跌 **{falling}** 家 | 平盘 {flat} 家")
        zt_line = f"* 涨停 **{lu}** 家 | 跌停 **{ld}** 家"
        if br is not None:
            zt_line += f" | 炸板率 **{br}%**"
        a(zt_line)
        a(f"* 半日总成交: **约 {total_amt:.0f} 亿**" if total_amt > 0 else "* 半日成交额: 数据暂不可用")
    else:
        a("* 涨跌分布: 数据暂不可用（可能非交易时段）")

    a("")

    # ══ Section 2 ══
    a("## 2. 资金风口与异动")
    a("")

    if fund["top_concepts"]:
        a("### 领涨题材")
        a("")
        for i, c in enumerate(fund["top_concepts"][:5], 1):
            a(f"{i}. **{c['name']}**（核心股: {c['top_stock']} {fmt_pct(c['top_stock_chg'])}，净流入 {c['net_flow']:.2f} 亿）")
        a("")

    # Big deals / abnormal moves
    if fund["big_deals"]:
        a("### 早盘大单成交")
        a("")
        for d in fund["big_deals"][:5]:
            a(f"- [{d['time']}] **{d['name']}**（{d['code']}） {d['type']} {d['amount']:.0f}万 @ {fmt_price(d['price'])}（{fmt_pct(d['change_pct'])}）")
        a("")
    else:
        a("### 早盘异动/闪崩提示")
        a("")
        a("无显著异常大单成交记录。")
        a("")

    # ══ Section 3 ══
    a("## 3. 盘前计划执行对齐")
    a("")

    if not plan_results:
        a("⚠️ 今日盘前计划中未提取到目标标的（可能计划尚未创建或格式不匹配）。")
        a("")
        a("建议：先运行 `pre_market.py` 生成盘前计划，再执行午间复盘。")
    else:
        for item in plan_results:
            code = item["code"]
            name = item.get("name", code)
            high = fmt_price(item.get("high"), "—")
            low = fmt_price(item.get("low"), "—")
            current = fmt_price(item.get("current"), "—")
            chg = fmt_pct(item.get("change_pct"), "—")
            status = item["status"]
            error = item.get("error")

            status_emoji = "✅" if status in ("涨停", "强势拉升中", "小幅上涨") else \
                          "⚠️" if status in ("小幅回调", "明显走弱") else \
                          "⏳" if "获取" in status else "❌"

            a(f"* {status_emoji} **{name}** [{code}]: "
              f"现价 {current}（{chg}）| 最高 {high} | 最低 {low} → 状态: **{status}**")
            if error:
                a(f"  > 数据异常: {error}")
        a("")

    # ══ Section 4 omitted: strategy generation removed — AI handles analysis ══

    # Errors
    all_errors = morning.get("errors", []) + fund.get("errors", [])
    if all_errors:
        a("---")
        a("")
        a("### ⚠️ 数据获取异常")
        for err in all_errors:
            a(f"- {err}")
        a("")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Noon review generator")
    parser.add_argument("--journal", type=str, default=None,
                       help="Path to journal file (default: auto-find today's)")
    args = parser.parse_args()

    print(f"[noon_review] 报告时间: {now_str()}", file=sys.stderr)

    # Section 1: Morning snapshot
    print("[noon_review] 采集早盘数据...", file=sys.stderr)
    t0 = time.time()
    morning = fetch_morning_snapshot()
    print(f"[noon_review]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # Section 2: Fund winds
    print("[noon_review] 采集资金异动...", file=sys.stderr)
    t0 = time.time()
    fund = fetch_fund_winds()
    print(f"[noon_review]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # Section 3: Plan alignment
    journal_path = Path(args.journal) if args.journal else find_today_journal()
    plan_stocks = extract_plan_stocks(journal_path) if journal_path else []
    if plan_stocks:
        print(f"[noon_review] 检查计划标的 ({len(plan_stocks)}只)...", file=sys.stderr)
    else:
        print("[noon_review] 未找到盘前计划或计划中无标的代码", file=sys.stderr)
    t0 = time.time()
    plan_results = check_plan_alignment(plan_stocks)
    print(f"[noon_review]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # Section 4: Strategy
    strategy = generate_afternoon_strategy(morning, fund)

    # Format & output
    print("[noon_review] 生成报告...", file=sys.stderr)
    output = format_noon_output(morning, fund, plan_results, strategy)
    print(output)


if __name__ == "__main__":
    main()
