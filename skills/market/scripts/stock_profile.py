import sys
import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import argparse
import time
from datetime import datetime, timedelta

def clean_stock_code(code: str) -> str:
    """Extract the 6-digit code from user input (e.g. 600519.SH -> 600519)"""
    if not code:
        raise ValueError("Stock code cannot be empty.")
    clean = code.strip().upper()
    if "." in clean:
        clean = clean.split(".")[0]
    for prefix in ["SH", "SZ", "BJ"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
        if clean.endswith(prefix):
            clean = clean[:-len(prefix)]
    clean = clean.strip()
    if len(clean) != 6 or not clean.isdigit():
        raise ValueError(f"Invalid stock code format: {code}")
    return clean

def get_exchange_market(code: str) -> str:
    """Get lowercase market code (sh/sz/bj)"""
    if code.startswith(('60', '68', '51')):
        return "sh"
    elif code.startswith(('00', '30')):
        return "sz"
    elif code.startswith(('8', '4')):
        return "bj"
    else:
        raise ValueError(f"Unknown exchange for stock code: {code}")

def parse_value_with_unit(val) -> float:
    """Parse a value string that may contain unit suffixes like '亿' or '万'.
       Returns the value converted to 亿 (100M)."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0
    try:
        if '亿' in s:
            return float(s.replace('亿', '').strip())
        elif '万' in s:
            return float(s.replace('万', '').strip()) / 10000
        else:
            return float(s)
    except (ValueError, TypeError):
        return 0.0

def parse_args():
    parser = argparse.ArgumentParser(description="Query deep-dive stock profile")
    parser.add_argument("code", type=str, help="Stock code (e.g., 600519)")
    parser.add_argument("--mode", type=str, default="realtime", 
                        choices=["realtime", "kline", "cyq", "comment", "fundflow", "financials", "technical"],
                        help="Analysis mode (default: realtime)")
    parser.add_argument("--period", type=str, default="daily",
                        choices=["daily", "weekly", "monthly", "yearly", "30min", "60min", "120min"],
                        help="Kline period (default: daily)")
    parser.add_argument("--days", type=int, default=10, 
                        help="Show past N data points/days (default: 10)")
    parser.add_argument("--type", type=str, default="income", 
                        choices=["income", "balance_sheet", "cashflow"],
                        help="Financial statement type (default: income)")
    parser.add_argument("--source", type=str, default="auto",
                        choices=["auto", "sina", "eastmoney", "xueqiu"],
                        help="Quote source for realtime mode (default: auto)")
    parser.add_argument("--token", type=str, default=None,
                        help="Xueqiu API token (xq_a_token)")
    return parser.parse_args()

def print_realtime_info(code, info, source_name):
    print(f"  Stock Name: {info.get('name', 'N/A')}")
    print(f"  Current Price: {info.get('price', 0.0):.2f}")
    print(f"  Change %: {info.get('change_pct', 0.0):.2f}%")
    print(f"  Change Amount: {info.get('change', 0.0):.2f}")
    print(f"  Open: {info.get('open', 0.0):.2f} | Pre-Close: {info.get('pre_close', 0.0):.2f}")
    print(f"  High: {info.get('high', 0.0):.2f} | Low: {info.get('low', 0.0):.2f}")
    print(f"  Volume: {info.get('volume', 0.0) / 100:.0f} lots")
    print(f"  Turnover: {info.get('turnover', 0.0):,.2f} Yuan")
    print(f"  Data Source: {source_name}")

def handle_realtime(code, market, source="auto", token=None):
    print(f"\n[Realtime Quote for {code}]")
    
    # Read environment variable for token if not passed
    if token is None:
        import os
        token = os.environ.get("XUEQIU_TOKEN")
        
    # Determine which source to try
    sources_to_try = []
    if source == "xueqiu":
        sources_to_try = ["xueqiu"]
    elif source == "sina":
        sources_to_try = ["sina_direct", "sina_full"]
    elif source == "eastmoney":
        sources_to_try = ["eastmoney"]
    else:  # auto
        sources_to_try = ["xueqiu", "sina_direct", "sina_full", "eastmoney"]

    # We will try sources in order
    for src in sources_to_try:
        try:
            if src == "xueqiu":
                exchange = market.upper()
                xueqiu_code = f"{exchange}{code}"
                # Get cache
                cache_key = f"realtime:xq:{code}"
                cached = cache_db.get_cache(cache_key)
                if cached is not None:
                    info = cached
                else:
                    df_xq = ak.stock_individual_spot_xq(symbol=xueqiu_code, token=token)
                    if df_xq is not None and not df_xq.empty:
                        row_dict = dict(zip(df_xq["item"], df_xq["value"]))
                        info = {
                            "name": str(row_dict.get("名称", "N/A")),
                            "price": float(row_dict.get("现价", 0.0)),
                            "change_pct": float(row_dict.get("涨幅", 0.0)),
                            "change": float(row_dict.get("涨跌", 0.0)),
                            "open": float(row_dict.get("今开", 0.0)),
                            "pre_close": float(row_dict.get("昨收", 0.0)),
                            "high": float(row_dict.get("最高", 0.0)),
                            "low": float(row_dict.get("最低", 0.0)),
                            "volume": float(row_dict.get("成交量", 0.0)),
                            "turnover": float(row_dict.get("成交额", 0.0)),
                            "source": "xueqiu"
                        }
                        cache_db.set_cache(cache_key, info, "realtime")
                    else:
                        raise ValueError("Empty response from Xueqiu API")
                
                print_realtime_info(code, info, "XUEQIU")
                return
                
            elif src == "sina_direct":
                info = akshare_patch.get_single_stock_realtime(code)
                if info:
                    info["source"] = "sina_direct"
                    print_realtime_info(code, info, "SINA_DIRECT")
                    return
                    
            elif src == "sina_full":
                df_all = ak.stock_zh_a_spot()
                if df_all is not None and not df_all.empty:
                    df_all["代码"] = df_all["代码"].str[-6:]
                    df = df_all[df_all["代码"] == code]
                    if not df.empty:
                        row = df.iloc[0]
                        info = {
                            "name": row.get("名称", "N/A"),
                            "price": float(row.get("最新价", 0.0)),
                            "change_pct": float(row.get("涨跌幅", 0.0)),
                            "change": float(row.get("涨跌额", 0.0)),
                            "open": float(row.get("今开", 0.0)),
                            "pre_close": float(row.get("昨收", 0.0)),
                            "high": float(row.get("最高", 0.0)),
                            "low": float(row.get("最低", 0.0)),
                            "volume": float(row.get("成交量", 0.0)) * 100,
                            "turnover": float(row.get("成交额", 0.0)),
                            "source": "sina_full"
                        }
                        print_realtime_info(code, info, "SINA_FULL")
                        return
                        
            elif src == "eastmoney":
                df_all = ak.stock_zh_a_spot_em()
                if df_all is not None and not df_all.empty:
                    df = df_all[df_all["代码"] == code]
                    if not df.empty:
                        row = df.iloc[0]
                        info = {
                            "name": row.get("名称", "N/A"),
                            "price": float(row.get("最新价", 0.0)),
                            "change_pct": float(row.get("涨跌幅", 0.0)),
                            "change": float(row.get("涨跌额", 0.0)),
                            "open": float(row.get("今开", 0.0)),
                            "pre_close": float(row.get("昨收", 0.0)),
                            "high": float(row.get("最高", 0.0)),
                            "low": float(row.get("最低", 0.0)),
                            "volume": float(row.get("成交量", 0.0)) * 100,
                            "turnover": float(row.get("成交额", 0.0)),
                            "source": "eastmoney"
                        }
                        print_realtime_info(code, info, "EASTMONEY")
                        return
        except Exception as e:
            if source != "auto":
                raise e
            else:
                print(f"Warning: Realtime quote query failed using source {src} ({type(e).__name__}: {str(e)}). Falling back...")
                
    raise RuntimeError("All real-time quote sources failed.")

def handle_kline(code, period, days):
    print(f"\n[K-Line Chart for {code} - Period: {period} - Latest {days} bars]")
    try:
        # Calculate date range for historical query (give a large buffer)
        end_date = datetime.now()
        start_str = ""
        end_str = ""
        if period in ["daily", "weekly", "monthly", "yearly"]:
            if period == "yearly":
                start_date = end_date - timedelta(days=365 * 20)
            else:
                start_date = end_date - timedelta(days=days * 5 + 100)
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")
            cache_key = f"kline:{code}:{period}:{start_str}:{end_str}"
        else:
            cache_key = f"kline:{code}:{period}"
            
        k_df = cache_db.get_cache(cache_key)
        if k_df is None:
            if period in ["daily", "weekly", "monthly", "yearly"]:
                if period == "yearly":
                    # start_str already computed above; fetch monthly and aggregate by year
                    df = ak.stock_zh_a_hist(symbol=code, period="monthly", start_date=start_str, end_date=end_str, adjust="qfq")
                    if df is not None and not df.empty:
                        df["日期"] = pd.to_datetime(df["日期"])
                        df["Year"] = df["日期"].dt.year
                        
                        # Group by Year
                        yearly_bars = []
                        for year, group in df.groupby("Year"):
                            group = group.sort_values(by="日期")
                            yearly_bars.append({
                                "日期": str(year),
                                "开盘": group.iloc[0]["开盘"],
                                "收盘": group.iloc[-1]["收盘"],
                                "最高": group["最高"].max(),
                                "最低": group["最低"].min(),
                                "成交量": group["成交量"].sum(),
                                "成交额": group["成交额"].sum(),
                                "涨跌幅": ((group.iloc[-1]["收盘"] - group.iloc[0]["开盘"]) / group.iloc[0]["开盘"] * 100)
                            })
                        k_df = pd.DataFrame(yearly_bars)
                    else:
                        k_df = pd.DataFrame()
                else:
                    k_df = ak.stock_zh_a_hist(symbol=code, period=period, start_date=start_str, end_date=end_str, adjust="qfq")
            else:
                # Minute-level history
                min_period_map = {"30min": "30", "60min": "60", "120min": "120"}
                p_val = min_period_map[period]
                k_df = ak.stock_zh_a_hist_min_em(symbol=code, period=p_val, adjust="qfq")

            if k_df is not None and not k_df.empty:
                # Cache the retrieved DataFrame
                is_minute = period in ["30min", "60min", "120min"]
                is_today = (end_str == datetime.now().strftime("%Y%m%d"))
                is_trading = cache_db.is_trading_hour(datetime.now())
                category = "kline_today" if (is_minute or (is_today and is_trading)) else "permanent"
                cache_db.set_cache(cache_key, k_df, category)

        if k_df is not None and not k_df.empty:
            # Sort chronologically, take the last `days` rows
            # Columns in stock_zh_a_hist: 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
            # Columns in stock_zh_a_hist_min_em: 时间, 开盘, 收盘, 最高, 最低, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅, 换手率
            date_col = "日期" if "日期" in k_df.columns else "时间"
            k_df = k_df.tail(days).copy()
            
            # Normalize date column: handle cached numeric timestamps
            if pd.api.types.is_numeric_dtype(k_df[date_col]):
                k_df[date_col] = pd.to_datetime(k_df[date_col], unit="ms").dt.strftime("%Y-%m-%d")
            else:
                try:
                    k_df[date_col] = pd.to_datetime(k_df[date_col]).dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass  # Keep original format if conversion fails
            
            # Format and display
            display_cols = [date_col, "开盘", "最高", "最低", "收盘", "成交量", "涨跌幅"]
            rename_dict = {
                date_col: "Date/Time",
                "开盘": "Open",
                "最高": "High",
                "最低": "Low",
                "收盘": "Close",
                "成交量": "Volume",
                "涨跌幅": "Change%"
            }
            display_df = k_df[display_cols].copy()
            display_df.rename(columns=rename_dict, inplace=True)
            print(display_df.to_string(index=False))
        else:
            print("No K-line data returned.")
    except Exception as e:
        print(f"Error fetching K-line data: {type(e).__name__}: {str(e)}")

def handle_cyq(code, days):
    print(f"\n[Chip Distribution (筹码分布) for {code} - Latest {days} days]")
    today_str = datetime.now().strftime("%Y%m%d")
    cache_key = f"cyq:{code}:{today_str}"
    df = cache_db.get_cache(cache_key)
    
    if df is None or df.empty:
        try:
            # stock_cyq_em uses py_mini_racer JS engine + push2his.eastmoney.com
            # Now works via curl_cffi impersonation in akshare_patch
            df = ak.stock_cyq_em(symbol=code, adjust="")
            if df is not None and not df.empty:
                # CYQ data is computed from historical K-line — completely static for past dates.
                # Cache permanently to avoid expensive JS engine re-computation on every invocation.
                cache_db.set_cache(cache_key, df, "permanent")
        except Exception as e:
            print(f"  (unavailable: failed to fetch chip distribution data: {e})")
            return
    
    if df is not None and not df.empty:
        # Normalize date column — JSON serialization converts date objects to epoch timestamps
        if "日期" in df.columns:
            if pd.api.types.is_integer_dtype(df["日期"]) or pd.api.types.is_float_dtype(df["日期"]):
                df["日期"] = pd.to_datetime(df["日期"], unit="ms").dt.date
            else:
                df["日期"] = pd.to_datetime(df["日期"]).dt.date
        
        df = df.tail(days).copy()
        display_cols = ["日期", "获利比例", "平均成本", "90成本-低", "90成本-高", "90集中度", "70成本-低", "70成本-高", "70集中度"]
        rename_dict = {
            "日期": "Date",
            "获利比例": "Profit%",
            "平均成本": "AvgCost",
            "90成本-低": "90%CostL",
            "90成本-高": "90%CostH",
            "90集中度": "90%Conc%",
            "70成本-低": "70%CostL",
            "70成本-高": "70%CostH",
            "70集中度": "70%Conc%"
        }
        display_df = df[display_cols].copy()
        display_df.rename(columns=rename_dict, inplace=True)
        print(display_df.to_string(index=False))
    else:
        print("  (unavailable: no chip distribution data)")

def handle_comment(code, days):
    print(f"\n[Institution and Market Sentiment (千股千评) for {code} - Latest {days} days]")
    try:
        # Score
        cache_key_score = f"comment:score:{code}"
        df_score = cache_db.get_cache(cache_key_score)
        if df_score is None:
            df_score = ak.stock_comment_detail_zhpj_lspf_em(symbol=code)
            if df_score is not None and not df_score.empty:
                cache_db.set_cache(cache_key_score, df_score, "permanent")
                
        # Focus
        cache_key_focus = f"comment:focus:{code}"
        df_focus = cache_db.get_cache(cache_key_focus)
        if df_focus is None:
            df_focus = ak.stock_comment_detail_scrd_focus_em(symbol=code)
            if df_focus is not None and not df_focus.empty:
                cache_db.set_cache(cache_key_focus, df_focus, "permanent")
                
        # Desire (renamed from stock_comment_detail_scrd_desire_daily_em in newer akshare)
        cache_key_desire = f"comment:desire:{code}"
        df_desire = cache_db.get_cache(cache_key_desire)
        if df_desire is None:
            df_desire = ak.stock_comment_detail_scrd_desire_em(symbol=code)
            if df_desire is not None and not df_desire.empty:
                cache_db.set_cache(cache_key_desire, df_desire, "permanent")
                
        # Institution
        cache_key_inst = f"comment:inst:{code}"
        df_inst = cache_db.get_cache(cache_key_inst)
        if df_inst is None:
            df_inst = ak.stock_comment_detail_zlkp_jgcyd_em(symbol=code)
            if df_inst is not None and not df_inst.empty:
                cache_db.set_cache(cache_key_inst, df_inst, "permanent")
        
        # Score DF Clean
        if df_score is not None and not df_score.empty:
            df_score_clean = df_score[["交易日", "评分"]].rename(columns={"交易日": "Date", "评分": "Score"})
        else:
            df_score_clean = pd.DataFrame(columns=["Date", "Score"])
            
        # Focus DF Clean
        if df_focus is not None and not df_focus.empty:
            df_focus_clean = df_focus[["交易日", "用户关注指数"]].rename(columns={"交易日": "Date", "用户关注指数": "FocusIndex"})
        else:
            df_focus_clean = pd.DataFrame(columns=["Date", "FocusIndex"])
            
        # Desire DF Clean (new API columns: 交易日期, 参与意愿, 5日平均参与意愿, 参与意愿变化, 5日平均变化)
        if df_desire is not None and not df_desire.empty:
            if "当日意愿上升" in df_desire.columns:
                # Old API format (fallback)
                df_desire_clean = df_desire[["交易日", "当日意愿上升"]].rename(columns={"交易日": "Date", "当日意愿上升": "DesireChg"})
            elif "交易日期" in df_desire.columns:
                # New API format
                desire_cols = ["交易日期"]
                desire_rename = {"交易日期": "Date"}
                if "参与意愿" in df_desire.columns:
                    desire_cols.append("参与意愿")
                    desire_rename["参与意愿"] = "Desire"
                if "参与意愿变化" in df_desire.columns:
                    desire_cols.append("参与意愿变化")
                    desire_rename["参与意愿变化"] = "DesireChg"
                df_desire_clean = df_desire[desire_cols].rename(columns=desire_rename)
            else:
                df_desire_clean = pd.DataFrame(columns=["Date", "DesireChg"])
        else:
            df_desire_clean = pd.DataFrame(columns=["Date", "DesireChg"])
            
        # Institution DF Clean
        if df_inst is not None and not df_inst.empty:
            df_inst_clean = df_inst[["交易日", "机构参与度"]].rename(columns={"交易日": "Date", "机构参与度": "Institution%"})
        else:
            df_inst_clean = pd.DataFrame(columns=["Date", "Institution%"])
            
        # Merge all on Date
        merged = pd.merge(df_score_clean, df_focus_clean, on="Date", how="outer")
        merged = pd.merge(merged, df_desire_clean, on="Date", how="outer")
        merged = pd.merge(merged, df_inst_clean, on="Date", how="outer")
        
        if not merged.empty:
            # Drop rows without a date
            merged = merged.dropna(subset=["Date"])
            # Normalize Date: handle both string dates and numeric timestamps
            if pd.api.types.is_numeric_dtype(merged["Date"]):
                merged["Date"] = pd.to_datetime(merged["Date"], unit="ms").dt.strftime("%Y-%m-%d")
            else:
                try:
                    merged["Date"] = pd.to_datetime(merged["Date"]).dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    merged["Date"] = merged["Date"].astype(str)
            # Sort chronologically, take the last N
            merged = merged.sort_values(by="Date").tail(days)
            print(merged.to_string(index=False))
        else:
            print("No sentiment comments data found.")
    except Exception as e:
        print(f"Error fetching comments: {type(e).__name__}: {str(e)}")

def handle_fundflow(code, market, days):
    print(f"\n[Money Flow (个股资金流向) for {code} ({market.upper()})]")
    try:
        # Map days to period label for the 10jqka API
        # stock_fund_flow_individual returns all-stock ranking; we filter by code
        if days <= 1:
            period = "即时"
            period_label = "今日"
        elif days <= 3:
            period = "3日排行"
            period_label = "3日"
        elif days <= 5:
            period = "5日排行"
            period_label = "5日"
        elif days <= 10:
            period = "10日排行"
            period_label = "10日"
        else:
            period = "20日排行"
            period_label = "20日"
            
        cache_key = f"fundflow:individual:{code}:{period}"
        df = cache_db.get_cache(cache_key)
        if df is None:
            df = ak.stock_fund_flow_individual(symbol=period)
            if df is not None and not df.empty:
                cache_db.set_cache(cache_key, df, "fundflow_today")
        
        print(f"  Period: {period_label}")
        
        if df is not None and not df.empty:
            # stock_fund_flow_individual returns stock_code as int64, so convert to int for comparison
            try:
                code_int = int(code)
            except ValueError:
                code_int = None
            
            # Filter by stock code (match both string and int formats)
            mask = df["股票代码"].astype(str).str.zfill(6) == code
            if code_int is not None:
                mask = mask | (df["股票代码"] == code_int)
            row_df = df[mask]
            
            if row_df.empty:
                print(f"No money flow data found for {code} in period '{period_label}'.")
                return
                
            row = row_df.iloc[0]
            
            if period == "即时":
                # Columns: 序号, 股票代码, 股票简称, 最新价, 涨跌幅, 换手率, 流入资金, 流出资金, 净额, 成交额
                print(f"  Stock: {row.get('股票简称', 'N/A')}")
                print(f"  Price: {row.get('最新价', 'N/A')}")
                print(f"  Change%: {row.get('涨跌幅', 'N/A')}")
                print(f"  Turnover Rate: {row.get('换手率', 'N/A')}")
                # Parse values with unit suffixes like '1.23亿' or '1234.56万'
                for label, col in [("Inflow", "流入资金"), ("Outflow", "流出资金"), ("NetFlow", "净额"), ("Turnover", "成交额")]:
                    val = row.get(col, 0)
                    num = parse_value_with_unit(val)
                    print(f"  {label}(亿): {num:.2f}")
            else:
                # 3日/5日/10日/20日排行: 序号, 股票代码, 股票简称, 最新价, 阶段涨跌幅, 连续换手率, 资金流入净额
                print(f"  Stock: {row.get('股票简称', 'N/A')}")
                print(f"  Price: {row.get('最新价', 'N/A')}")
                print(f"  Stage Change%: {row.get('阶段涨跌幅', 'N/A')}")
                print(f"  Consecutive Turnover: {row.get('连续换手率', 'N/A')}")
                netflow_val = row.get('资金流入净额')
                if netflow_val is not None:
                    netflow_str = str(netflow_val)
                    if '亿' in netflow_str:
                        num_part = netflow_str.replace('亿', '').strip()
                        print(f"  NetFlow(亿): {float(num_part):.2f}")
                    elif '万' in netflow_str:
                        num_part = netflow_str.replace('万', '').strip()
                        print(f"  NetFlow(万): {float(num_part):.2f}")
                    else:
                        print(f"  NetFlow: {netflow_str}")
        else:
            print("No money flow data found.")
    except Exception as e:
        print(f"Error fetching money flow: {type(e).__name__}: {str(e)}")

def handle_financials(code, market, type_str, days):
    market_code = market.upper()
    prefixed_code = f"{market_code}{code}"
    
    print(f"\n[Financial Report: {type_str.upper()} for {prefixed_code} - Latest {days} periods]")
    try:
        cache_key = f"financials:{prefixed_code}:{type_str}"
        df = cache_db.get_cache(cache_key)
        if df is None:
            if type_str == "balance_sheet":
                df = ak.stock_balance_sheet_by_report_em(symbol=prefixed_code)
            elif type_str == "income":
                df = ak.stock_profit_sheet_by_report_em(symbol=prefixed_code)
            elif type_str == "cashflow":
                df = ak.stock_cash_flow_sheet_by_report_em(symbol=prefixed_code)
            
            if df is not None and not df.empty:
                cache_db.set_cache(cache_key, df, "permanent")

        metrics_map = {}
        if type_str == "balance_sheet":
            metrics_map = {
                "REPORT_DATE_NAME": "Period",
                "TOTAL_ASSETS": "Total Assets",
                "TOTAL_LIABILITIES": "Total Liab",
                "TOTAL_PARENT_EQUITY": "Equity(Parent)"
            }
        elif type_str == "income":
            metrics_map = {
                "REPORT_DATE_NAME": "Period",
                "TOTAL_OPERATE_INCOME": "Revenue",
                "OPERATE_PROFIT": "Op Profit",
                "NETPROFIT": "Net Profit"
            }
        elif type_str == "cashflow":
            metrics_map = {
                "REPORT_DATE_NAME": "Period",
                "NETCASH_OPERATE": "Op CashFlow",
                "NETCASH_INVEST": "Inv CashFlow",
                "NETCASH_FINANCE": "Fin CashFlow"
            }

        if df is not None and not df.empty:
            # Sort chronologically (earliest first or latest first? Let's take latest N)
            # In EM reports, iloc[0] is the latest report, so it is sorted latest first.
            df = df.head(days).copy()
            
            # Format columns
            present_cols = [c for c in metrics_map.keys() if c in df.columns]
            filtered_df = df[present_cols].copy()
            filtered_df.rename(columns=metrics_map, inplace=True)
            
            # Convert values to millions for neatness
            for col in filtered_df.columns:
                if col != "Period":
                    filtered_df[col] = pd.to_numeric(filtered_df[col], errors="coerce")
                    filtered_df[col] = (filtered_df[col] / 1000000).round(2)
                    filtered_df.rename(columns={col: f"{col}(M)"}, inplace=True)
            
            # Transpose for neat horizontal reading: Metrics as rows, Periods as columns!
            transposed = filtered_df.set_index("Period").T
            # Reset index to print nicely
            transposed.insert(0, "Metric / Period", transposed.index)
            print(transposed.to_string(index=False))
        else:
            print("No financial data found.")
    except Exception as e:
        print(f"Error fetching financials: {type(e).__name__}: {str(e)}")

def handle_technical(code, days):
    print(f"\n[Technical Indicators for {code} - Daily - Latest {days} days]")
    try:
        import indicators
        
        # Calculate date range for historical query (we need at least 250 trading days, so past 500 calendar days is safe)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=500)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        
        cache_key = f"kline:{code}:daily:{start_str}:{end_str}"
        k_df = cache_db.get_cache(cache_key)
        if k_df is None:
            # We always use daily period for standard technical indicators
            k_df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_str, end_date=end_str, adjust="qfq")
            if k_df is not None and not k_df.empty:
                # Use same cache category logic as handle_kline: today's data is not permanent
                is_today = (end_str == datetime.now().strftime("%Y%m%d"))
                is_trading = cache_db.is_trading_hour(datetime.now())
                category = "kline_today" if (is_today and is_trading) else "permanent"
                cache_db.set_cache(cache_key, k_df, category)
                
        if k_df is not None and not k_df.empty:
            # Rename columns to English so indicators.py works:
            rename_map = {
                "日期": "Date",
                "开盘": "Open",
                "最高": "High",
                "最低": "Low",
                "收盘": "Close",
                "成交量": "Volume"
            }
            k_df_en = k_df.rename(columns=rename_map)
            
            # Calculate all indicators
            ind_df = indicators.calculate_all_indicators(k_df_en)
            
            # Take the latest `days` rows to display
            display_df = ind_df.tail(days).copy()
            
            # Normalize Date column representation (handles cached integer timestamps)
            if pd.api.types.is_numeric_dtype(display_df["Date"]):
                display_df["Date"] = pd.to_datetime(display_df["Date"], unit="ms").dt.strftime("%Y-%m-%d")
            else:
                try:
                    display_df["Date"] = pd.to_datetime(display_df["Date"]).dt.strftime("%Y-%m-%d")
                except:
                    pass
            
            # Print Trend (Price & SMA / EMA)
            print("\n1. Trend & Moving Averages (趋势均线):")
            trend_cols = ["Date", "Close", "SMA_5", "SMA_10", "SMA_20", "SMA_30", "SMA_60", "SMA_120", "SMA_250"]
            print(display_df[trend_cols].to_string(index=False, formatters={
                "Close": "{:.2f}".format, "SMA_5": "{:.2f}".format, "SMA_10": "{:.2f}".format,
                "SMA_20": "{:.2f}".format, "SMA_30": "{:.2f}".format, "SMA_60": "{:.2f}".format,
                "SMA_120": "{:.2f}".format, "SMA_250": "{:.2f}".format
            }))
            
            # Print Momentum & Channels (MACD & BOLL)
            print("\n2. MACD & Bollinger Bands (动量与通道):")
            momentum_cols = ["Date", "Close", "DIF", "DEA", "MACD", "BOLL_MID", "BOLL_UP", "BOLL_LB"]
            print(display_df[momentum_cols].to_string(index=False, formatters={
                "Close": "{:.2f}".format, "DIF": "{:.2f}".format, "DEA": "{:.2f}".format,
                "MACD": "{:.2f}".format, "BOLL_MID": "{:.2f}".format, "BOLL_UP": "{:.2f}".format,
                "BOLL_LB": "{:.2f}".format
            }))
            
            # Print Oscillators (RSI, KDJ, WR)
            print("\n3. Oscillators (超买超卖: RSI, KDJ, WR):")
            oscillator_cols = ["Date", "RSI_6", "RSI_12", "RSI_24", "KDJ_K", "KDJ_D", "KDJ_J", "WR"]
            print(display_df[oscillator_cols].to_string(index=False, formatters={
                "RSI_6": "{:.2f}".format, "RSI_12": "{:.2f}".format, "RSI_24": "{:.2f}".format,
                "KDJ_K": "{:.2f}".format, "KDJ_D": "{:.2f}".format, "KDJ_J": "{:.2f}".format,
                "WR": "{:.2f}".format
            }))
            
            # Print Volatility & Volume (ATR, CCI, VWMA, MFI)
            print("\n4. Volatility & Volume (波动率与成交量: ATR, CCI, VWMA, MFI):")
            vol_cols = ["Date", "Close", "ATR", "CCI", "VWMA", "MFI"]
            print(display_df[vol_cols].to_string(index=False, formatters={
                "Close": "{:.2f}".format, "ATR": "{:.2f}".format, "CCI": "{:.2f}".format,
                "VWMA": "{:.2f}".format, "MFI": "{:.2f}".format
            }))
        else:
            print("No K-line history data found to compute indicators.")
    except Exception as e:
        print(f"Error computing technical indicators: {type(e).__name__}: {str(e)}")

def main():
    args = parse_args()
    try:
        clean_code = clean_stock_code(args.code)
        market = get_exchange_market(clean_code)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    print("==================================================")
    print(f" STOCK PROFILE DEEP-DIVE: {clean_code}.{market.upper()}")
    print(f" Mode: {args.mode.upper()}")
    print(f" Query Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    if args.mode == "realtime":
        handle_realtime(clean_code, market, source=args.source, token=args.token)
    elif args.mode == "kline":
        handle_kline(clean_code, args.period, args.days)
    elif args.mode == "cyq":
        handle_cyq(clean_code, args.days)
    elif args.mode == "comment":
        handle_comment(clean_code, args.days)
    elif args.mode == "fundflow":
        handle_fundflow(clean_code, market, args.days)
    elif args.mode == "financials":
        handle_financials(clean_code, market, args.type, args.days)
    elif args.mode == "technical":
        handle_technical(clean_code, args.days)

if __name__ == "__main__":
    main()
