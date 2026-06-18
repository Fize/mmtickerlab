import sys
import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import argparse
import time

def parse_args():
    parser = argparse.ArgumentParser(description="Query A-share top gainers or losers")
    parser.add_argument("--top", type=int, default=10, help="Number of stocks to display (default: 10)")
    parser.add_argument("--type", type=str, default="up", choices=["up", "down"], help="Rank by 'up' (gainers) or 'down' (losers) (default: up)")
    return parser.parse_args()

def show_rankings():
    args = parse_args()
    rank_type_ch = "涨幅榜 (Top Gainers)" if args.type == "up" else "跌幅榜 (Top Losers)"
    
    print("==================================================")
    print(f" A-SHARE MARKET RANKINGS: {rank_type_ch}")
    print(f" Query Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    try:
        df = None
        source = "sina"
        
        # Check cache for spot data
        cached_spot_data = cache_db.get_cache("spot:all_data")
        if cached_spot_data is not None:
            df = cached_spot_data.get("df_spot")
            source = cached_spot_data.get("source", "sina")
        else:
            try:
                print("Fetching A-share spot data from Sina...")
                df = ak.stock_zh_a_spot()
                source = "sina"
            except Exception as e:
                print(f"Sina spot query failed, falling back to Eastmoney spot API... ({str(e)})")
                df = ak.stock_zh_a_spot_em()
                source = "eastmoney"
            
            if df is not None and not df.empty:
                cache_db.set_cache("spot:all_data", {"df_spot": df, "source": source}, "realtime")

        if df is not None and not df.empty:
            if source == "sina" and "代码" in df.columns:
                # Clean code names like sh600519 to 600519
                df["代码"] = df["代码"].str[-6:]
            
            # Ensure change percent is numeric
            df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
            
            # Sort by change percent
            ascending = (args.type == "down")
            sorted_df = df.sort_values(by="涨跌幅", ascending=ascending)
            
            # Select top N
            top_df = sorted_df.head(args.top).copy()
            
            # Display columns selection
            if source == "eastmoney":
                cols = ["代码", "名称", "最新价", "涨跌幅", "成交额", "换手率"]
                col_names = ["Code", "Name", "Price", "Change%", "Turnover(Yuan)", "TurnoverRate%"]
            else:
                cols = ["代码", "名称", "最新价", "涨跌幅", "成交额"]
                col_names = ["Code", "Name", "Price", "Change%", "Turnover(Yuan)"]
                
            display_df = top_df[cols].copy()
            display_df.columns = col_names
            
            # Print table
            print(f"Data Source: {source.upper()}")
            print(display_df.to_string(index=False))
        else:
            print("No spot data returned.")
    except Exception as e:
        print(f"Error fetching ranking data: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    show_rankings()
