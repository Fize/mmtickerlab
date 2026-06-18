import sys
import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import time

def get_market_overview():
    print("==================================================")
    print(" A-SHARE MARKET OVERVIEW (A股大盘与市场概览)")
    print(f" Query Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    # 1. Fetch Major Indices
    print("\n[1] Major Indices (重要指数):")
    target_indices = {
        "000001": "上证指数",
        "399001": "深证成指",
        "399006": "创业板指",
        "000300": "沪深300",
        "000016": "上证50",
        "000905": "中证500",
        "000852": "中证1000"
    }
    
    # Try reading index cache
    cached_indices = cache_db.get_cache("overview:indices")
    if cached_indices is not None:
        print(cached_indices.to_string(index=False))
    else:
        try:
            # Try Sina index direct API first (extremely fast and robust)
            try:
                symbols = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000300", "s_sh000016", "s_sh000905", "s_sh000852"]
                url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
                r = akshare_patch.original_get(url, headers={"Referer": "http://finance.sina.com.cn"}, timeout=5)
                r.raise_for_status()
                text = r.text
                
                index_rows = []
                lines = text.strip().split("\n")
                for line in lines:
                    if not line or not line.startswith("var hq_str_s_"):
                        continue
                    eq_idx = line.find("=")
                    if eq_idx == -1:
                        continue
                    symbol = line[11:eq_idx] # e.g. s_sh000001
                    code = symbol[-6:] # e.g. 000001
                    
                    start_idx = line.find('"')
                    end_idx = line.rfind('"')
                    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
                        continue
                    data_str = line[start_idx+1:end_idx]
                    if not data_str:
                        continue
                    parts = data_str.split(",")
                    if len(parts) < 6:
                        continue
                    
                    name = target_indices.get(code, parts[0])
                    current = float(parts[1])
                    change_val = float(parts[2])
                    change_pct = float(parts[3])
                    volume = float(parts[4]) # Already in lots/hands
                    amount = float(parts[5]) * 10000 # Convert from 10k Yuan to Yuan
                    
                    index_rows.append({
                        "Code": code,
                        "Index Name": name,
                        "Current": f"{current:.2f}",
                        "Change%": f"{change_pct:+.2f}%",
                        "Change": f"{change_val:+.2f}",
                        "Volume(L)": f"{volume:.0f}",
                        "Amount(Yuan)": f"{amount:,.0f}"
                    })
                    
                if index_rows:
                    df_indices = pd.DataFrame(index_rows)
                    cache_db.set_cache("overview:indices", df_indices, "realtime")
                    print(df_indices.to_string(index=False))
                else:
                    raise ValueError("No index rows parsed")
                    
            except Exception as e:
                print(f"Sina direct index query failed, falling back to Eastmoney... ({str(e)})")
                # Fallback to Eastmoney
                df_index = ak.stock_zh_index_spot_em(symbol="上证系列指数")
                df_sz = ak.stock_zh_index_spot_em(symbol="深证系列指数")
                df_indices = None
                if df_index is not None and not df_index.empty and df_sz is not None and not df_sz.empty:
                    df_indices = pd.concat([df_index, df_sz], ignore_index=True)
                elif df_index is not None and not df_index.empty:
                    df_indices = df_index
                elif df_sz is not None and not df_sz.empty:
                    df_indices = df_sz

                if df_indices is not None and not df_indices.empty:
                    filtered_df = df_indices[df_indices["代码"].isin(target_indices.keys())].copy()
                    filtered_df["名称"] = filtered_df["代码"].map(target_indices)
                    display_cols = ["代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交量", "成交额"]
                    renamed_df = filtered_df[display_cols].copy()
                    renamed_df.columns = ["Code", "Index Name", "Current", "Change%", "Change", "Volume(L)", "Amount(Yuan)"]
                    cache_db.set_cache("overview:indices", renamed_df, "realtime")
                    print(renamed_df.to_string(index=False))
                else:
                    print("No index data returned.")
        except Exception as e:
            print(f"Error fetching index data: {type(e).__name__}: {str(e)}")

    # 2. Fetch Market Stats (Advancing/Declining)
    print("\n[2] Market Breadth Stats (市场涨跌分布与量能):")
    try:
        df_spot = None
        source = "sina"
        
        # Check cache for spot data
        cached_spot_data = cache_db.get_cache("spot:all_data")
        if cached_spot_data is not None:
            df_spot = cached_spot_data.get("df_spot")
            source = cached_spot_data.get("source", "sina")
        else:
            try:
                print("Fetching A-share spot data from Sina...")
                df_spot = ak.stock_zh_a_spot()
                source = "sina"
            except Exception as e:
                print(f"Sina spot query failed, falling back to Eastmoney spot API... ({str(e)})")
                df_spot = ak.stock_zh_a_spot_em()
                source = "eastmoney"
            
            if df_spot is not None and not df_spot.empty:
                cache_db.set_cache("spot:all_data", {"df_spot": df_spot, "source": source}, "realtime")

        if df_spot is not None and not df_spot.empty:
            # Normalize column names and values
            if source == "sina" and "代码" in df_spot.columns:
                # Sina columns: 代码, 名称, 最新价, 涨跌额, 涨跌幅, 昨收, 今开, 最高, 最低, 成交量, 成交额
                df_spot["代码"] = df_spot["代码"].str[-6:]  # Clean sh600519 to 600519
            
            # Ensure values are numeric
            df_spot["最新价"] = pd.to_numeric(df_spot["最新价"], errors="coerce")
            df_spot["涨跌幅"] = pd.to_numeric(df_spot["涨跌幅"], errors="coerce")
            df_spot["成交量"] = pd.to_numeric(df_spot["成交量"], errors="coerce")
            df_spot["成交额"] = pd.to_numeric(df_spot["成交额"], errors="coerce")
            
            total_stocks = len(df_spot)
            
            # Calculate counts
            rising = df_spot[df_spot["涨跌幅"] > 0]
            falling = df_spot[df_spot["涨跌幅"] < 0]
            flat = df_spot[df_spot["涨跌幅"] == 0]
            
            # Limit up/down counts
            limit_up = df_spot[df_spot["涨跌幅"] >= 9.9]
            limit_down = df_spot[df_spot["涨跌幅"] <= -9.9]
            
            # Median and mean changes
            mean_change = df_spot["涨跌幅"].mean()
            median_change = df_spot["涨跌幅"].median()
            
            # Total volume and amount
            total_vol = df_spot["成交量"].sum()
            total_amt = df_spot["成交额"].sum()
            
            print(f"Data Source: {source.upper()}")
            print(f"Total Stocks Tracked: {total_stocks}")
            print(f"Advancing (上涨): {len(rising)} ({len(rising)/total_stocks*100:.1f}%)")
            print(f"Declining (下跌): {len(falling)} ({len(falling)/total_stocks*100:.1f}%)")
            print(f"Flat (平盘): {len(flat)} ({len(flat)/total_stocks*100:.1f}%)")
            print(f"Limit Up (涨停 >= 9.9%): {len(limit_up)}")
            print(f"Limit Down (跌停 <= -9.9%): {len(limit_down)}")
            print(f"Average Change: {mean_change:.2f}%")
            print(f"Median Change: {median_change:.2f}%")
            print(f"Total Market Volume: {total_vol / 1000000:.2f} M lots")
            print(f"Total Market Turnover: {total_amt / 100000000:.2f} Billion Yuan")
            
            # Price distribution buckets
            print("\n[3] Price Change Distribution (涨跌幅区间分布):")
            buckets = [
                (">9.9% (涨停)", df_spot[df_spot["涨跌幅"] >= 9.9]),
                ("7% to 9.9%", df_spot[(df_spot["涨跌幅"] >= 7) & (df_spot["涨跌幅"] < 9.9)]),
                ("5% to 7%", df_spot[(df_spot["涨跌幅"] >= 5) & (df_spot["涨跌幅"] < 7)]),
                ("3% to 5%", df_spot[(df_spot["涨跌幅"] >= 3) & (df_spot["涨跌幅"] < 5)]),
                ("0% to 3%", df_spot[(df_spot["涨跌幅"] > 0) & (df_spot["涨跌幅"] < 3)]),
                ("0% (平盘)", flat),
                ("-3% to 0%", df_spot[(df_spot["涨跌幅"] > -3) & (df_spot["涨跌幅"] < 0)]),
                ("-5% to -3%", df_spot[(df_spot["涨跌幅"] > -5) & (df_spot["涨跌幅"] <= -3)]),
                ("-7% to -5%", df_spot[(df_spot["涨跌幅"] > -7) & (df_spot["涨跌幅"] <= -5)]),
                ("-9.9% to -7%", df_spot[(df_spot["涨跌幅"] > -9.9) & (df_spot["涨跌幅"] <= -7)]),
                ("<-9.9% (跌停)", df_spot[df_spot["涨跌幅"] <= -9.9]),
            ]
            for label, sub_df in buckets:
                pct = len(sub_df) / total_stocks * 100
                bar = "█" * int(pct // 2)
                print(f"  {label:<15}: {len(sub_df):>4} ({pct:>5.1f}%) {bar}")
        else:
            print("No spot data returned.")
    except Exception as e:
        print(f"Error fetching spot data: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    get_market_overview()
