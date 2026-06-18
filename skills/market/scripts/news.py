import sys
import akshare_patch
import cache_db
import akshare as ak
import pandas as pd
import argparse
import time

def clean_stock_code(code: str) -> str:
    """Extract the 6-digit code from user input (e.g. 600519.SH -> 600519)"""
    if not code:
        raise ValueError("Stock code cannot be empty.")
    # Remove SH/SZ prefixes or suffixes
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

def parse_args():
    parser = argparse.ArgumentParser(description="Query latest news for a specific A-share stock")
    parser.add_argument("code", type=str, help="6-digit stock code (e.g., 600519)")
    parser.add_argument("--n", type=int, default=10, help="Number of news items to fetch (default: 10)")
    return parser.parse_args()

def show_news():
    args = parse_args()
    try:
        clean_code = clean_stock_code(args.code)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    print("==================================================")
    print(f" LATEST NEWS FOR STOCK: {clean_code}")
    print(f" Query Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    try:
        cache_key = f"news:{clean_code}"
        df = cache_db.get_cache(cache_key)
        if df is None:
            df = ak.stock_news_em(symbol=clean_code)
            if df is not None and not df.empty:
                cache_db.set_cache(cache_key, df, "news")
                
        if df is not None and not df.empty:
            # Sort news by publish time if available, or take head
            news_df = df.head(args.n)
            
            print(f"Latest {len(news_df)} News Items:\n")
            for idx, row in news_df.iterrows():
                title = row.get("新闻标题", "No Title")
                content = row.get("新闻内容", "No Content")
                pub_time = row.get("发布时间", "No Time")
                source = row.get("新闻来源", row.get("文章来源", "Unknown Source"))
                url = row.get("新闻链接", "No URL")
                
                print(f"[{idx + 1}] {title}")
                print(f"    Source: {source} | Time: {pub_time}")
                print(f"    Summary: {content}")
                print(f"    Link: {url}")
                print("-" * 50)
        else:
            print(f"No news found for stock {clean_code}.")
    except Exception as e:
        print(f"Error fetching news: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    show_news()
