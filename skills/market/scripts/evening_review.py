#!/usr/bin/env python3
"""
Evening Review Generator (A股晚间市场数据汇总)

Fetches full-day market data, Dragon-Tiger Board (龙虎榜) data, performs
theme lifecycle analysis, and generates a next-day candidate pool.

Usage:
    skills/market/.venv/bin/python skills/market/scripts/evening_review.py
    
    # Pipe directly into journal:
    skills/market/.venv/bin/python skills/market/scripts/evening_review.py | \\
        skills/plan-review/.venv/bin/python skills/plan-review/scripts/journal.py append --section evening
    
    # Specify date for historical review:
    skills/market/.venv/bin/python skills/market/scripts/evening_review.py --date 20260617

Data Sources:
    Section 1: index_global_spot_em, stock_zh_a_spot (Sina/EM), stock_zt_pool_em
    Section 2: stock_fund_flow_concept, stock_fund_flow_industry, theme analysis
    Section 3: stock_lhb_detail_em, stock_lhb_ggtj_sina, stock_lhb_jgstatistic_em
    Section 4: derived analysis + candidate screening
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import time
import warnings

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import akshare_patch
import cache_db
import indicators
import akshare as ak
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = SCRIPT_DIR.parents[2]
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

def fmt_amount(v):
    """Format amount in 亿 or 万"""
    try:
        v = float(v)
        if abs(v) >= 1e8: return f"{v/1e8:.2f} 亿"
        elif abs(v) >= 1e4: return f"{v/1e4:.0f} 万"
        else: return f"{v:.0f}"
    except: return str(v)

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def load_watchlist():
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list): return data
        except: pass
    return []


# ─── Section 1: Full-Day Market Summary ─────────────────────────────────────

def fetch_full_day_summary(date_str: str) -> dict:
    """Fetch full-day market data."""
    result = {
        "indices": [], "breadth": {}, "max_board": 0,
        "max_board_stock": "", "board_ladder": "", "errors": []
    }

    # --- Major Indices ---
    target_indices = {
        "000001": "上证指数", "399001": "深证成指", "399006": "创业板指",
        "000300": "沪深300", "000016": "上证50", "000905": "中证500", "000852": "中证1000"
    }
    try:
        symbols = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000300",
                   "s_sh000016", "s_sh000905", "s_sh000852"]
        url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
        r = akshare_patch.original_get(url, headers={"Referer": "http://finance.sina.com.cn"}, timeout=5)
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
                "volume": safe_float(parts[4]),
                "amount": safe_float(parts[5]) * 10000 if safe_float(parts[5]) > 0 else 0,
            })
    except Exception as e:
        result["errors"].append(f"指数: {e}")

    # --- Market Breadth ---
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
            df_spot["成交额"] = pd.to_numeric(df_spot["成交额"], errors="coerce")

            total = len(df_spot)
            result["breadth"] = {
                "total": total,
                "rising": int((df_spot["涨跌幅"] > 0).sum()),
                "falling": int((df_spot["涨跌幅"] < 0).sum()),
                "flat": total - int((df_spot["涨跌幅"] > 0).sum()) - int((df_spot["涨跌幅"] < 0).sum()),
                "limit_up": int((df_spot["涨跌幅"] >= 9.9).sum()),
                "limit_down": int((df_spot["涨跌幅"] <= -9.9).sum()),
                "mean_change": round(df_spot["涨跌幅"].mean(), 2),
                "total_amount": round(df_spot["成交额"].sum() / 1e8, 0),
            }
    except Exception as e:
        result["errors"].append(f"市场宽度: {e}")

    # --- Limit-Up Pool & Board Ladder ---
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        if df_zt is not None and not df_zt.empty:
            if "连板数" in df_zt.columns:
                boards = df_zt[df_zt["连板数"] > 0].copy()
                if not boards.empty:
                    max_row = boards.loc[boards["连板数"].idxmax()]
                    result["max_board"] = int(max_row["连板数"])
                    result["max_board_stock"] = f"{max_row.get('名称','')}（{max_row.get('代码','')}）"

                    # Board ladder: check continuity
                    unique_boards = sorted(boards["连板数"].unique(), reverse=True)
                    expected = list(range(result["max_board"], 0, -1))
                    missing = [b for b in expected if b not in unique_boards]
                    result["board_ladder"] = "完整" if not missing else f"断层（缺{','.join(map(str, missing))}板）"
                else:
                    result["board_ladder"] = "无连板（全部首板）"
    except Exception as e:
        result["errors"].append(f"涨停池: {e}")

    return result


# ─── Section 2: Theme Lifecycle Analysis ────────────────────────────────────

def analyze_theme_lifecycle() -> dict:
    """
    Analyze current market themes and their lifecycle stages.
    Classifies leading themes into: 启动期/发酵期/极度高潮/第一次分歧/退潮期
    """
    result = {"main_theme": None, "hidden_theme": None, "errors": []}

    try:
        # Get concept fund flows
        df = ak.stock_fund_flow_concept(symbol="即时")
        if df is None or df.empty:
            result["errors"].append("概念资金流向数据不可用")
            return result

        top_concepts = []
        for _, row in df.head(10).iterrows():
            name = str(row.get("行业", ""))
            net_flow = safe_float(row.get("净额", 0))
            chg = safe_float(row.get("行业-涨跌幅", 0))
            top_stock = str(row.get("领涨股", ""))
            top_stock_chg = safe_float(row.get("领涨股-涨跌幅", 0))
            top_concepts.append({
                "name": name, "net_flow": net_flow, "chg": chg,
                "top_stock": top_stock, "top_stock_chg": top_stock_chg
            })

        if not top_concepts:
            return result

        # Main theme: highest net inflow with positive change
        positive_flows = [c for c in top_concepts if c["net_flow"] > 0]
        if positive_flows:
            main = max(positive_flows, key=lambda c: c["net_flow"])
        else:
            main = top_concepts[0]

        # Lifecycle classification
        if main["chg"] > 5:
            stage = "极度高潮 — 板块全面爆发，谨防次日分歧"
        elif main["chg"] > 2:
            stage = "发酵期 — 赚钱效应扩散，仍有参与价值"
        elif main["chg"] > 0:
            stage = "启动期 — 刚获资金关注，关注持续性"
        elif main["chg"] > -2:
            stage = "第一次分歧 — 板块内部分化，汰弱留强"
        else:
            stage = "退潮期 — 资金流出明显，回避为主"

        result["main_theme"] = {
            "name": main["name"],
            "stage": stage,
            "net_flow": main["net_flow"],
            "chg": main["chg"],
            "top_stock": main["top_stock"],
            "top_stock_chg": main["top_stock_chg"],
        }

        # Hidden theme: positive flow but smaller, or negative flow but rising
        others = [c for c in top_concepts if c["name"] != main["name"]]
        hidden_candidates = [c for c in others if c["net_flow"] > 0 and c["chg"] > 1]
        if hidden_candidates:
            hidden = hidden_candidates[0]
            result["hidden_theme"] = {
                "name": hidden["name"],
                "reason": f"资金温和流入 {hidden['net_flow']:.2f} 亿，板块涨幅 {hidden['chg']:+.2f}%，龙头 {hidden['top_stock']} {hidden['top_stock_chg']:+.2f}%",
            }

    except Exception as e:
        result["errors"].append(f"题材分析: {e}")

    return result


# ─── Section 3: Dragon-Tiger Board ──────────────────────────────────────────

def fetch_lhb_data(date_str: str) -> dict:
    """Fetch Dragon-Tiger Board (龙虎榜) data for today."""
    result = {
        "institutional": [],  # 机构聚焦
        "notable_traders": [],  # 知名游资
        "negative_feedback": [],  # 负反馈
        "errors": []
    }

    # --- LHB Detail (filter today's date) ---
    try:
        df = ak.stock_lhb_detail_em()
        if df is not None and not df.empty:
            # Filter by date - the 上榜日 column format varies
            today_date = datetime.strptime(date_str, "%Y%m%d")
            # Try to filter by approximate date
            df["上榜日_parsed"] = pd.to_datetime(df["上榜日"], errors="coerce")
            today_df = df[df["上榜日_parsed"].dt.date == today_date.date()]

            # If no today data, take recent entries
            if today_df.empty:
                today_df = df.head(20)

            # Institutional focus: entries with "机构" in 解读
            inst_df = today_df[today_df["解读"].str.contains("机构", na=False)].head(8)
            for _, row in inst_df.iterrows():
                result["institutional"].append({
                    "name": str(row.get("名称", "")),
                    "code": str(row.get("代码", "")),
                    "reason": str(row.get("解读", "")),
                    "net_buy": safe_float(row.get("龙虎榜净买额", 0)),
                    "change_pct": safe_float(row.get("涨跌幅", 0)),
                    "close": safe_float(row.get("收盘价", 0)),
                })

            # Notable traders / big moves
            for _, row in today_df.head(10).iterrows():
                net_buy = safe_float(row.get("龙虎榜净买额", 0))
                if abs(net_buy) > 5e7:  # > 5000万
                    result["notable_traders"].append({
                        "name": str(row.get("名称", "")),
                        "code": str(row.get("代码", "")),
                        "reason": str(row.get("上榜原因", "")),
                        "net_buy": net_buy,
                        "buy_amount": safe_float(row.get("龙虎榜买入额", 0)),
                        "sell_amount": safe_float(row.get("龙虎榜卖出额", 0)),
                        "change_pct": safe_float(row.get("涨跌幅", 0)),
                    })

            # Negative feedback: sell-heavy entries
            for _, row in today_df.iterrows():
                net_buy = safe_float(row.get("龙虎榜净买额", 0))
                buy = safe_float(row.get("龙虎榜买入额", 0))
                sell = safe_float(row.get("龙虎榜卖出额", 0))
                if sell > buy * 3 and sell > 5e7:  # Sell 3x more than buy
                    result["negative_feedback"].append({
                        "name": str(row.get("名称", "")),
                        "code": str(row.get("代码", "")),
                        "net_sell": net_buy,
                        "sell_amount": sell,
                    })

    except Exception as e:
        result["errors"].append(f"龙虎榜明细: {e}")

    # --- LHB Stock Aggregate (Sina) ---
    try:
        df_agg = ak.stock_lhb_ggtj_sina()
        if df_agg is not None and not df_agg.empty:
            result["lhb_aggregate"] = []
            for _, row in df_agg.head(5).iterrows():
                result["lhb_aggregate"].append({
                    "code": str(row.get("股票代码", "")),
                    "name": str(row.get("股票名称", "")),
                    "times": int(row.get("上榜次数", 0)),
                    "net_amount": safe_float(row.get("净额", 0)),
                })
    except Exception:
        pass  # Non-critical

    return result


# ─── Section 4: Deep Stock Analysis & Candidate Pool ────────────────────────

def deep_analyze_stock(code: str, name: str = "", context: dict = None) -> dict:
    """
    Fetch K-line + technical indicators for a single stock and produce a
    structured analysis with concrete reasoning.
    
    Returns dict with: technical_snapshot, analysis_points, risk_flags
    """
    result = {
        "code": code, "name": name,
        "technicals": None, "analysis": [], "risk_flags": [],
        "status": "ok"
    }
    
    if len(code) != 6 or not code.isdigit():
        result["status"] = "invalid_code"
        return result
    
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=500)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        k_df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                   start_date=start_str, end_date=end_str, adjust="qfq")
        if k_df is None or k_df.empty:
            result["status"] = "no_kline"
            return result
        
        rename_map = {"日期": "Date", "开盘": "Open", "最高": "High",
                     "最低": "Low", "收盘": "Close", "成交量": "Volume"}
        k_df = k_df.rename(columns=rename_map)
        ind_df = indicators.calculate_all_indicators(k_df)
        
        if ind_df.empty:
            result["status"] = "no_indicator"
            return result
        
        latest = ind_df.iloc[-1]
        prev = ind_df.iloc[-2] if len(ind_df) > 1 else latest
        prev5 = ind_df.iloc[-6] if len(ind_df) > 5 else latest
        
        close = safe_float(latest.get("Close", 0))
        sma_5 = safe_float(latest.get("SMA_5", close))
        sma_10 = safe_float(latest.get("SMA_10", close))
        sma_20 = safe_float(latest.get("SMA_20", close))
        sma_60 = safe_float(latest.get("SMA_60", close))
        boll_upper = safe_float(latest.get("BOLL_UP", 0))
        boll_mid = safe_float(latest.get("BOLL_MID", 0))
        boll_lower = safe_float(latest.get("BOLL_LB", 0))
        rsi_6 = safe_float(latest.get("RSI_6", 50))
        macd_val = safe_float(latest.get("MACD", 0))
        dif = safe_float(latest.get("DIF", 0))
        dea = safe_float(latest.get("DEA", 0))
        kdj_k = safe_float(latest.get("KDJ_K", 50))
        kdj_d = safe_float(latest.get("KDJ_D", 50))
        kdj_j = safe_float(latest.get("KDJ_J", 50))
        vol = safe_float(latest.get("Volume", 0))
        prev_vol = safe_float(prev.get("Volume", 0))
        prev_close = safe_float(prev.get("Close", 0))
        
        # Volume ratio
        vol_ratio = round(vol / prev_vol, 2) if prev_vol > 0 else 1.0
        
        result["technicals"] = {
            "close": close, "sma_5": sma_5, "sma_10": sma_10,
            "sma_20": sma_20, "sma_60": sma_60,
            "boll_mid": boll_mid, "boll_upper": boll_upper, "boll_lower": boll_lower,
            "rsi_6": rsi_6, "macd_val": macd_val, "dif": dif, "dea": dea,
            "kdj_k": kdj_k, "kdj_d": kdj_d, "kdj_j": kdj_j,
            "vol_ratio": vol_ratio,
        }
        
        # ── Analysis Points ──
        analysis = []
        risks = []
        
        # 1. Trend assessment
        if close > sma_5 > sma_10 > sma_20 > sma_60:
            analysis.append("均线多头排列，趋势强劲，处于主升浪结构")
        elif close > sma_20 and sma_5 > sma_10:
            analysis.append("短期均线向上，中期趋势偏多，站上 MA20 关键位")
        elif close > sma_20 and close <= sma_20 * 1.02:
            analysis.append(f"紧贴 MA20（{sma_20:.2f}）运行，均线支撑有效")
        elif close < sma_60:
            analysis.append("股价运行在 MA60 下方，中期趋势偏弱")
            risks.append("趋势偏弱，若参与需等待放量站回 MA20")
        else:
            analysis.append(f"短期震荡格局，MA20={sma_20:.2f} 为多空分水岭")
        
        # 2. Volume analysis
        if vol_ratio > 2.0:
            analysis.append(f"放巨量（量比 {vol_ratio:.1f}x），关注是吸筹还是出货")
            if close > prev_close:
                analysis.append("结合上涨放量，偏多信号")
            else:
                risks.append("下跌放量，可能有资金出逃")
        elif vol_ratio > 1.2:
            analysis.append(f"温和放量（量比 {vol_ratio:.1f}x），量价配合健康")
        elif vol_ratio < 0.7:
            analysis.append(f"缩量（量比 {vol_ratio:.1f}x），关注是否地量见底")
        
        # 3. MACD
        if macd_val > 0 and prev.get("MACD", 0) and safe_float(prev.get("MACD", 0)) <= 0:
            analysis.append("MACD 今日金叉，零轴附近转多，趋势转折信号")
        elif macd_val > 0 and dif > dea:
            analysis.append("MACD 多头运行中，DIF 在 DEA 上方，动能持续")
        elif macd_val < 0:
            analysis.append("MACD 绿柱，空头占优，等待转红信号")
        
        # 4. RSI
        if rsi_6 > 80:
            risks.append(f"RSI(6)={rsi_6:.1f} 严重超买，短线回调风险大")
        elif rsi_6 > 70:
            analysis.append(f"RSI(6)={rsi_6:.1f} 偏强区域，动能充足但需警惕超买")
        elif rsi_6 < 30:
            analysis.append(f"RSI(6)={rsi_6:.1f} 超卖区域，技术面有反弹需求")
        elif rsi_6 < 50:
            analysis.append(f"RSI(6)={rsi_6:.1f} 偏弱，等待回到 50 上方确认转强")
        else:
            analysis.append(f"RSI(6)={rsi_6:.1f} 中性偏强")
        
        # 5. Bollinger position
        if boll_upper > 0 and close >= boll_upper * 0.98:
            analysis.append("股价运行至布林上轨附近，强势但短期空间有限")
            risks.append("布林上轨压制，追高性价比低，等回踩中轨再介入")
        elif boll_lower > 0 and close <= boll_lower * 1.02:
            analysis.append("触及布林下轨，技术层面有反弹需求")
        elif boll_mid > 0 and abs(close - boll_mid) / boll_mid < 0.02:
            analysis.append("紧贴布林中轨运行，方向选择节点，关注突破方向")
        
        # 6. KDJ
        if kdj_j < 0:
            analysis.append("KDJ 极度超卖（J<0），短期反弹概率高")
        elif kdj_j > 100:
            risks.append("KDJ 极度超买（J>100），短线追高风险极大")
        
        result["analysis"] = analysis
        result["risk_flags"] = risks
        
    except Exception as e:
        result["status"] = "error"
        result["analysis"] = [f"技术分析失败: {str(e)[:80]}"]
    
    return result


def generate_candidate_pool(summary: dict, lhb: dict, theme: dict) -> dict:
    """
    Generate next-day sentiment expectation, attack mode, and a
    deeply-analyzed candidate pool. Each candidate gets K-line + 
    technical indicator analysis with concrete reasoning.
    """
    breadth = summary.get("breadth", {})
    limit_up = breadth.get("limit_up", 0)
    limit_down = breadth.get("limit_down", 0)
    rising = breadth.get("rising", 0)
    total = breadth.get("total", 1)
    max_board = summary.get("max_board", 0)
    board_ladder = summary.get("board_ladder", "")

    result = {
        "sentiment": "", "attack_mode": "", "candidates": []
    }

    # --- Sentiment Expectation ---
    rising_pct = rising / max(total, 1) * 100
    if limit_up >= 100 and limit_down < 10 and rising_pct > 60:
        result["sentiment"] = "强修复/延续强势 — 赚钱效应好，但需防高潮次日分歧"
    elif limit_up >= 50 and max_board >= 5 and "完整" in board_ladder:
        result["sentiment"] = "弱转强可期 — 连板梯队完整，关注龙头分歧转一致机会"
    elif limit_up >= 50:
        result["sentiment"] = "延续强势中带分歧 — 涨停数多但注意分化，聚焦主线辨识度"
    elif limit_up >= 30:
        result["sentiment"] = "延续分歧 — 板块轮动快，追高风险大，等分歧结束信号"
    elif limit_up < 20 or limit_down > 50:
        result["sentiment"] = "加速退潮 — 严格控制仓位，等待冰点信号"
    else:
        result["sentiment"] = "方向不明 — 观望为主，等待明确信号"

    # --- Attack Mode ---
    if "强修复" in result["sentiment"] or "弱转强" in result["sentiment"]:
        if max_board >= 3 and "完整" in board_ladder:
            result["attack_mode"] = "龙头股分歧低吸或断板反包试错"
        else:
            result["attack_mode"] = "主流题材首板试错，关注新发酵方向"
    elif "延续强势" in result["sentiment"]:
        result["attack_mode"] = "聚焦主线龙头分歧低吸，高辨识度个股回踩均线介入"
    elif "延续分歧" in result["sentiment"]:
        result["attack_mode"] = "控仓参与，只做最强辨识度个股的低吸"
    else:
        result["attack_mode"] = "空仓防守或极轻仓试探"

    # --- Candidate Pool with Deep Analysis ---
    raw_candidates = []
    
    # Source 1: LHB institutional buying stocks (highest priority)
    inst_stocks = lhb.get("institutional", [])[:5]
    for s in inst_stocks:
        if s["net_buy"] > 0 and s.get("code"):
            raw_candidates.append({
                "code": s["code"], "name": s["name"],
                "context": f"龙虎榜机构净买入 {fmt_amount(s['net_buy'])}，上榜原因：{s.get('reason','')}",
                "source": "龙虎榜机构",
                "priority": 1,
            })
    
    # Source 2: Notable trader activity
    for s in lhb.get("notable_traders", [])[:5]:
        if s.get("code") and s["net_buy"] > 0:
            if not any(c["code"] == s["code"] for c in raw_candidates):
                raw_candidates.append({
                    "code": s["code"], "name": s["name"],
                    "context": f"龙虎榜大额净买入 {fmt_amount(s['net_buy'])}，{s.get('reason','')[:40]}",
                    "source": "龙虎榜游资",
                    "priority": 2,
                })
    
    # Source 3: LHB aggregate (Sina stats)
    for s in lhb.get("lhb_aggregate", [])[:3]:
        if s.get("code") and s["net_amount"] > 0:
            if not any(c["code"] == s["code"] for c in raw_candidates):
                raw_candidates.append({
                    "code": s["code"], "name": s["name"],
                    "context": f"龙虎榜统计净买入 {fmt_amount(s['net_amount'])}，上榜{s.get('times',0)}次",
                    "source": "龙虎榜统计",
                    "priority": 3,
                })
    
    # Sort by priority, take top 5
    raw_candidates.sort(key=lambda c: c["priority"])
    raw_candidates = raw_candidates[:5]
    
    # Deep analyze each candidate
    for rc in raw_candidates:
        code = rc["code"]
        name = rc.get("name", code)
        analysis = deep_analyze_stock(code, name, rc.get("context"))
        
        # Build the composite reason from LHB context + technical analysis
        reasons = []
        reasons.append(rc["context"])
        
        if analysis.get("analysis"):
            for pt in analysis["analysis"][:2]:  # Top 2 technical points
                reasons.append(pt)
        
        # Combine risk flags
        risks = analysis.get("risk_flags", [])
        
        techs = analysis.get("technicals")
        
        result["candidates"].append({
            "code": code,
            "name": name,
            "reasons": reasons,
            "risks": risks,
            "technicals": techs,
            "source": rc["source"],
        })
    
    return result


# ─── Output Formatter ────────────────────────────────────────────────────────

def format_evening_output(date_display: str, summary: dict, theme: dict,
                          lhb: dict, strategy: dict) -> str:
    lines = []
    a = lines.append

    a(f"# 🌙 A股晚间市场数据汇总")
    a(f"报告时间: {date_display} {datetime.now().strftime('%H:%M')}")
    a("")
    a(f"> 🤖 本数据由 evening_review.py 自动汇总。")
    a("")

    # ══ Section 1 ══
    a("## 1. 市场全天总览")
    a("")

    # Indices
    if summary["indices"]:
        a("### 核心指数")
        a("")
        a("| 指数 | 收盘 | 涨跌幅 | 涨跌额 |")
        a("|:---|:---|:---|:---|")
        for idx in summary["indices"]:
            a(f"| {idx['name']} | {idx['price']:.2f} | {idx['change_pct']:+.2f}% | {idx['change']:+.2f} |")
        a("")

    # Breadth
    b = summary.get("breadth", {})
    if b:
        rising_pct = b["rising"] / max(b["total"], 1) * 100
        a("### 成交能见度")
        a("")
        a(f"- 全天总成交：**{b['total_amount']:.0f} 亿**")
        a(f"- 上涨 **{b['rising']}** 家（{rising_pct:.1f}%）| 下跌 **{b['falling']}** 家 | 涨停 **{b['limit_up']}** 家 | 跌停 **{b['limit_down']}** 家")
        a(f"- 平均涨幅：{b['mean_change']:+.2f}%")
        a("")

    # Board height
    if summary["max_board"] > 0:
        a("### 连板高度")
        a("")
        a(f"- 市场最高 **{summary['max_board']}** 连板：{summary['max_board_stock']}")
        a(f"- 连板阶梯：**{summary['board_ladder']}**")
        a("")

    # ══ Section 2 ══
    a("## 2. 概念资金流向")
    a("")

    if theme.get("main_theme"):
        a("### 概念资金流向Top10")
        a("")
        a("| 板块名 | 净流入(亿) | 涨跌幅 | 领涨股 | 领涨涨跌幅 |")
        a("|:---|:---|:---|:---|:---|")
        mt = theme["main_theme"]
        a(f"| {mt['name']} | {mt['net_flow']:.2f} | {mt['chg']:+.2f}% | {mt['top_stock']} | {mt['top_stock_chg']:+.2f}% |")
        if theme.get("hidden_theme"):
            ht = theme["hidden_theme"]
            a(f"| {ht['name']} | — | — | — | — |")
        a("")
    else:
        a("今日无明确概念资金流向数据。")
        a("")

    # ══ Section 3 ══
    a("## 3. 主力资金异动（龙虎榜精选）")
    a("")

    # Institutional
    if lhb.get("institutional"):
        a("### 机构资金聚焦")
        a("")
        for item in lhb["institutional"][:5]:
            direction = "净买入" if item["net_buy"] > 0 else "净卖出"
            a(f"- **{item['name']}**（{item['code']}）：机构{direction} **{fmt_amount(abs(item['net_buy']))}**，{item['reason']}")
        a("")

    # Notable traders
    if lhb.get("notable_traders"):
        a("### 知名游资动向")
        a("")
        for item in lhb["notable_traders"][:5]:
            direction = "净买入" if item["net_buy"] > 0 else "净卖出"
            a(f"- **{item['name']}**（{item['code']}）：{direction} **{fmt_amount(abs(item['net_buy']))}**，{item['reason'][:40]}")
        a("")

    # Negative feedback
    if lhb.get("negative_feedback"):
        a("### ⚠️ 核心负反馈提示")
        a("")
        for item in lhb["negative_feedback"][:3]:
            a(f"- **{item['name']}**（{item['code']}）：遭遇坚决卖出，净卖出 {fmt_amount(abs(item['net_sell']))}")
        a("")

    if not (lhb.get("institutional") or lhb.get("notable_traders")):
        a("今日龙虎榜数据暂不可用或无显著异动。")
        a("")

    # ══ Section 4 ══
    a("## 4. 次日备选股池（龙虎榜初筛）")
    a("")

    a("### 备选股池")
    a("")
    if strategy.get("candidates"):
        for i, c in enumerate(strategy["candidates"], 1):
            code = c.get("code", "")
            name = c.get("name", "")
            source = c.get("source", "")

            # LHB data
            reasons = c.get("reasons", [])
            lhb_info = reasons[0] if reasons else ""

            # Technical snapshot
            techs = c.get("technicals")
            if techs:
                tech_line = f"close={techs.get('close','N/A')} MA20={techs.get('sma_20','N/A')} MA60={techs.get('sma_60','N/A')} RSI(6)={techs.get('rsi_6','N/A')} 量比={techs.get('vol_ratio','N/A')}"
                tech_detail = f"MACD DIF={techs.get('dif','N/A')} DEA={techs.get('dea','N/A')} | KDJ J={techs.get('kdj_j','N/A')}"
            else:
                tech_line = "技术数据不可用"
                tech_detail = ""

            a(f"**{i}. {name}（{code}）** — 来源：{source}")
            a(f"- {lhb_info}")
            a(f"- 技术数据：{tech_line}")
            if tech_detail:
                a(f"- {tech_detail}")
            a("")
    else:
        a("暂无明确备选标的。")
    a("")

    # Errors
    all_errors = summary.get("errors", []) + theme.get("errors", []) + lhb.get("errors", [])
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
    parser = argparse.ArgumentParser(description="Evening review generator")
    parser.add_argument("--date", type=str, default=None,
                       help="Date in YYYYMMDD (default: today)")
    args = parser.parse_args()

    today = datetime.now()
    if args.date:
        ref_date = datetime.strptime(args.date, "%Y%m%d")
    else:
        ref_date = today

    date_str = ref_date.strftime("%Y%m%d")
    date_display = ref_date.strftime("%Y-%m-%d")

    print(f"[evening_review] 复盘日期: {date_display}", file=sys.stderr)

    # Section 1: Full-day summary
    print("[evening_review] 采集全天市场数据...", file=sys.stderr)
    t0 = time.time()
    summary = fetch_full_day_summary(date_str)
    print(f"[evening_review]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # Section 2: Theme lifecycle
    print("[evening_review] 分析主线题材生命周期...", file=sys.stderr)
    t0 = time.time()
    theme = analyze_theme_lifecycle()
    print(f"[evening_review]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # Section 3: LHB
    print("[evening_review] 采集龙虎榜数据...", file=sys.stderr)
    t0 = time.time()
    lhb = fetch_lhb_data(date_str)
    print(f"[evening_review]   ✓ 完成 ({time.time()-t0:.1f}s)", file=sys.stderr)

    # Section 4: Strategy & candidates
    print("[evening_review] 生成次日策略与备选股池...", file=sys.stderr)
    strategy = generate_candidate_pool(summary, lhb, theme)

    # Format & output
    print("[evening_review] 生成复盘报告...", file=sys.stderr)
    output = format_evening_output(date_display, summary, theme, lhb, strategy)
    print(output)


if __name__ == "__main__":
    main()
