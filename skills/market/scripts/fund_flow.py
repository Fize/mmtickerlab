import sys
import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import argparse
import time

def parse_args():
    parser = argparse.ArgumentParser(description="Query Concept, Industry, or Big Deal Cash Flow (资金流向分析)")
    parser.add_argument("--type", type=str, default="concept", choices=["concept", "industry", "bigdeal"], 
    help="Sector type: concept (default), industry, or bigdeal")
    parser.add_argument("--period", type=int, default=1, choices=[1, 3, 5], 
    help="Time period: 1 (real-time/daily, default), 3, or 5 days")
    return parser.parse_args()

PERIOD_LABELS = {1: "今日", 3: "3日", 5: "5日"}

def show_fund_flow():
    args = parse_args()
    
    print("==================================================")
    print(f" FUND FLOW ANALYSIS: {args.type.upper()}")
    if args.type != "bigdeal":
        print(f" Period: {PERIOD_LABELS.get(args.period, args.period)}")
    print(f" Query Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    try:
        if args.type == "concept":
            # Map period to akshare symbol
            # "即时" (11 cols: has 领涨股), "3日排行"/"5日排行" (8 cols: no 领涨股)
            period_map = {1: "即时", 3: "3日排行", 5: "5日排行"}
            symbol = period_map[args.period]
            cache_key = f"fundflow:concept:{symbol}"
            df = cache_db.get_cache(cache_key)
            if df is None:
                df = ak.stock_fund_flow_concept(symbol=symbol)
                if df is not None and not df.empty:
                    cache_db.set_cache(cache_key, df, "fund_flow_sector")
            
            if df is not None and not df.empty:
                top_n = df.head(15).copy()
                is_today = (args.period == 1)
                
                if is_today:
                    # 即时 mode: has 领涨股/行业-涨跌幅/行业指数 columns
                    display_cols = ["序号", "行业", "净额"]
                    if "行业指数" in top_n.columns:
                        display_cols.insert(2, "行业指数")
                    if "行业-涨跌幅" in top_n.columns:
                        display_cols.insert(3, "行业-涨跌幅")
                    if "领涨股" in top_n.columns:
                        display_cols.append("领涨股")
                    if "领涨股-涨跌幅" in top_n.columns:
                        display_cols.append("领涨股-涨跌幅")
                        
                    rename_dict = {
                        "序号": "Rank",
                        "行业": "Concept",
                        "行业指数": "Index",
                        "行业-涨跌幅": "Change%",
                        "净额": "NetFlow(亿)",
                        "领涨股": "TopStock",
                        "领涨股-涨跌幅": "TopStockChange%"
                    }
                else:
                    # 3日/5日排行 mode: 8 cols, no 领涨股
                    display_cols = ["序号", "行业", "公司家数", "行业指数", "阶段涨跌幅", "净额"]
                    rename_dict = {
                        "序号": "Rank",
                        "行业": "Concept",
                        "公司家数": "Count",
                        "行业指数": "Index",
                        "阶段涨跌幅": "StageChg%",
                        "净额": "NetFlow(亿)",
                    }
                
                filtered_df = top_n[[c for c in display_cols if c in top_n.columns]].copy()
                filtered_df.rename(columns=rename_dict, inplace=True)
                # 净额 already in 亿, just ensure numeric
                net_col = [c for c in filtered_df.columns if "NetFlow" in c]
                for c in net_col:
                    filtered_df[c] = pd.to_numeric(filtered_df[c], errors="coerce").round(2)
                
                print(filtered_df.to_string(index=False))
            else:
                print(f"No concept flow data found for period: {symbol}")
                
        elif args.type == "industry":
            # Map period to akshare symbol
            period_map = {1: "即时", 3: "3日排行", 5: "5日排行"}
            symbol = period_map[args.period]
            cache_key = f"fundflow:industry:{symbol}"
            df = cache_db.get_cache(cache_key)
            if df is None:
                df = ak.stock_fund_flow_industry(symbol=symbol)
                if df is not None and not df.empty:
                    cache_db.set_cache(cache_key, df, "fund_flow_sector")
            
            if df is not None and not df.empty:
                top_n = df.head(15).copy()
                is_today = (args.period == 1)
                
                if is_today:
                    display_cols = ["序号", "行业", "净额"]
                    if "行业指数" in top_n.columns:
                        display_cols.insert(2, "行业指数")
                    if "行业-涨跌幅" in top_n.columns:
                        display_cols.insert(3, "行业-涨跌幅")
                    if "领涨股" in top_n.columns:
                        display_cols.append("领涨股")
                    if "领涨股-涨跌幅" in top_n.columns:
                        display_cols.append("领涨股-涨跌幅")
                        
                    rename_dict = {
                        "序号": "Rank",
                        "行业": "Industry",
                        "行业指数": "Index",
                        "行业-涨跌幅": "Change%",
                        "净额": "NetFlow(亿)",
                        "领涨股": "TopStock",
                        "领涨股-涨跌幅": "TopStockChange%"
                    }
                else:
                    display_cols = ["序号", "行业", "公司家数", "行业指数", "阶段涨跌幅", "净额"]
                    rename_dict = {
                        "序号": "Rank",
                        "行业": "Industry",
                        "公司家数": "Count",
                        "行业指数": "Index",
                        "阶段涨跌幅": "StageChg%",
                        "净额": "NetFlow(亿)",
                    }
                
                filtered_df = top_n[[c for c in display_cols if c in top_n.columns]].copy()
                filtered_df.rename(columns=rename_dict, inplace=True)
                net_col = [c for c in filtered_df.columns if "NetFlow" in c]
                for c in net_col:
                    filtered_df[c] = pd.to_numeric(filtered_df[c], errors="coerce").round(2)
                
                print(filtered_df.to_string(index=False))
            else:
                print(f"No industry flow data found for period: {symbol}")
                
        elif args.type == "bigdeal":
            cache_key = "fundflow:bigdeal"
            df = cache_db.get_cache(cache_key)
            if df is None:
                df = ak.stock_fund_flow_big_deal()
                if df is not None and not df.empty:
                    cache_db.set_cache(cache_key, df, "fund_flow_sector")
            
            if df is not None and not df.empty:
                # Columns: 成交时间, 股票代码, 股票简称, 成交价格, 成交量, 成交额, 大单性质, 涨跌幅, 涨跌额
                # Limit to latest 15 rows for console readability
                display_cols = ["成交时间", "股票代码", "股票简称", "成交价格", "成交额", "大单性质", "涨跌幅"]
                rename_dict = {
                    "成交时间": "Time",
                    "股票代码": "Code",
                    "股票简称": "Name",
                    "成交价格": "Price",
                    "成交额": "Amount(Yuan)",
                    "大单性质": "Type",
                    "涨跌幅": "Change%"
                }
                filtered_df = df[display_cols].head(15).copy()
                filtered_df.rename(columns=rename_dict, inplace=True)
                
                print(filtered_df.to_string(index=False))
            else:
                print("No big deal data found.")
                
    except Exception as e:
        print(f"Error fetching fund flow data: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    show_fund_flow()
