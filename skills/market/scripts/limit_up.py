import sys
import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import argparse
import time
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Query A-share Limit-Up Pool (今日及历史涨停股池)")
    parser.add_argument("--date", type=str, default=None, help="Date in YYYYMMDD format (default: today)")
    return parser.parse_args()

def show_limit_ups():
    args = parse_args()
    
    # Format date
    if args.date:
        query_date = args.date
    else:
        query_date = datetime.now().strftime("%Y%m%d")
        
    print("==================================================")
    print(f" A-SHARE LIMIT-UP POOL (涨停股池)")
    print(f" Query Date: {query_date}")
    print(f" Query Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    try:
        cache_key = f"limit_up:{query_date}"
        df = cache_db.get_cache(cache_key)
        
        if df is None:
            df = ak.stock_zt_pool_em(date=query_date)
            if df is not None and not df.empty:
                # If query_date is today, use dynamic cache category; otherwise permanent
                is_today = (query_date == datetime.now().strftime("%Y%m%d"))
                category = "limit_up" if is_today else "permanent"
                cache_db.set_cache(cache_key, df, category)

        if df is not None and not df.empty:
            # Sort by continuous limit-up count descending, then sealing funds descending
            if "连板数" in df.columns:
                df = df.sort_values(by=["连板数", "封板资金"], ascending=[False, False])
            
            # Select columns to display
            # We want: 代码, 名称, 最新价, 涨跌幅, 换手率, 连板数, 封板资金, 炸板次数, 所属行业
            display_cols = []
            rename_dict = {}
            
            possible_cols = {
                "代码": "Code",
                "名称": "Name",
                "最新价": "Price",
                "涨跌幅": "Change%",
                "换手率": "TurnoverRate%",
                "连板数": "LimitUpDays",
                "封板资金": "SealingFunds(Yuan)",
                "炸板次数": "BreakTimes",
                "所属行业": "Industry"
            }
            
            for col, eng_name in possible_cols.items():
                if col in df.columns:
                    display_cols.append(col)
                    rename_dict[col] = eng_name
            
            filtered_df = df[display_cols].copy()
            filtered_df.rename(columns=rename_dict, inplace=True)
            
            # Format SealingFunds to Millions for readability
            sealing_col = "SealingFunds(Yuan)"
            if sealing_col in filtered_df.columns:
                filtered_df[sealing_col] = pd.to_numeric(filtered_df[sealing_col], errors="coerce")
                filtered_df["SealingFunds(M)"] = (filtered_df[sealing_col] / 1000000).round(2)
                filtered_df.drop(columns=[sealing_col], inplace=True)
            
            print(f"Total Limit-Up Stocks: {len(filtered_df)}")
            print(filtered_df.to_string(index=False))
        else:
            print(f"No limit-up data found for date {query_date}. (Market might be closed or data not ready)")
    except Exception as e:
        print(f"Error fetching limit-up data: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    show_limit_ups()
