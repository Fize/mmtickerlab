import sys
from pathlib import Path
import json
from datetime import datetime
import pandas as pd
import argparse

import akshare_patch
import akshare as ak

def clean_stock_code(code: str) -> str:
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

def check_trading_hours():
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    time_str = now.strftime("%H:%M:%S")
    is_morning = "09:30:00" <= time_str <= "11:30:00"
    is_afternoon = "13:00:00" <= time_str <= "15:00:00"
    return is_morning or is_afternoon

def get_pre_close_and_current(code: str):
    # Try Sina direct API first (very fast, no history download)
    try:
        info = akshare_patch.get_single_stock_realtime(code)
        if info:
            pre_close = info["pre_close"]
            current_price = info["price"]
            if pre_close > 0 and current_price > 0:
                return pre_close, current_price
    except Exception as e:
        print(f"Warning: Sina direct API failed for {code}: {e}. Falling back to history K-line.")

    end_date = datetime.now()
    start_date = end_date - pd.Timedelta(days=7)
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust="qfq"
    )
    if df is None or df.empty:
        raise ValueError(f"Could not fetch price history for {code}.")
    
    last_row = df.iloc[-1]
    last_date_str = str(last_row["日期"])
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_price = float(last_row["收盘"])
    
    if last_date_str == today_str:
        if len(df) < 2:
            raise ValueError(f"Not enough price history for {code} to check pre-close.")
        pre_close = float(df.iloc[-2]["收盘"])
    else:
        pre_close = current_price
        
    return pre_close, current_price

def load_portfolio_and_sync(portfolio_path):
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    updated_at = datetime.fromisoformat(portfolio["updated_at"])
    today = datetime.now()
    if today.date() > updated_at.date():
        for code, pos in portfolio["positions"].items():
            pos["available_shares"] = pos["shares"]
        portfolio["updated_at"] = today.isoformat()
        portfolio_path.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
    return portfolio

def parse_args():
    parser = argparse.ArgumentParser(description="Place a simulation sell order")
    parser.add_argument("code", type=str, help="Stock code (e.g. 600519)")
    parser.add_argument("qty", type=int, help="Quantity to sell")
    parser.add_argument("--price", type=float, default=None, help="Execution limit price (defaults to real-time close)")
    parser.add_argument("--force", action="store_true", help="Bypass trading hours validation")
    return parser.parse_args()

def place_sell_order():
    args = parse_args()
    
    try:
        code = clean_stock_code(args.code)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    if args.qty <= 0:
        print(f"Error: Sell quantity must be positive. Provided: {args.qty}")
        sys.exit(1)
        
    # 1. Validate trading hours
    if not args.force and not check_trading_hours():
        print("Error: Orders can only be placed during A-share trading hours (9:30-11:30, 13:00-15:00 on weekdays). Use --force to bypass this check.")
        sys.exit(1)
        
    # 2. Load Portfolio
    sim_dir = Path(__file__).resolve().parents[1] / "data" / "simulation"
    portfolio_path = sim_dir / "portfolio.json"
    if not portfolio_path.exists():
        print("Error: Portfolio file not found. Run reset.py first.")
        sys.exit(1)
        
    portfolio = load_portfolio_and_sync(portfolio_path)
    positions = portfolio["positions"]
    
    # 3. Check if stock is held
    if code not in positions:
        print(f"Error: You do not hold any shares of {code}.")
        sys.exit(1)
        
    pos = positions[code]
    shares = pos["shares"]
    available = pos["available_shares"]
    name = pos["name"]
    
    # 4. Check available shares (T+1 enforcement)
    if args.qty > available:
        print(f"Error: Insufficient available shares for {code} ({name}).")
        print(f"  Total Shares Held  : {shares}")
        print(f"  Available (Sellable): {available} (T+1 restriction covers recently bought shares)")
        print(f"  Requested to Sell  : {args.qty}")
        sys.exit(1)
        
    # 5. Fetch price data
    try:
        pre_close, current_price = get_pre_close_and_current(code)
    except Exception as e:
        if args.force and args.price is not None:
            print(f"Warning: Could not fetch price limits from API, but continuing due to --force: {str(e)}")
            pre_close = args.price
            current_price = args.price
        else:
            print(f"Error checking price limits: {str(e)}. (Specify --price and --force to override)")
            sys.exit(1)
        
    # Determine limit price
    price = args.price if args.price is not None else current_price
    
    # 6. Validate price limits
    if "ST" in name or "*ST" in name:
        limit_pct = 0.05
    elif code.startswith(("30", "68")):
        limit_pct = 0.20
    elif code.startswith(("4", "8")):
        limit_pct = 0.30
    else:
        limit_pct = 0.10
        
    upper_limit = round(pre_close * (1 + limit_pct), 2)
    lower_limit = round(pre_close * (1 - limit_pct), 2)
    
    if not (lower_limit <= price <= upper_limit):
        print(f"Error: Order price ({price:.2f}) exceeds price limits [{lower_limit:.2f} - {upper_limit:.2f}] based on pre-close ({pre_close:.2f}).")
        sys.exit(1)
        
    # 7. Calculate fees & cash cash-in
    trade_amount = price * args.qty
    commission = max(5.0, trade_amount * 0.00025)
    transfer_fee = trade_amount * 0.00002
    stamp_tax = trade_amount * 0.001  # Stamp tax 0.1% on sell only
    
    net_inflow = trade_amount - commission - transfer_fee - stamp_tax
    
    # 8. Execute order
    portfolio["cash"] += net_inflow
    portfolio["updated_at"] = datetime.now().isoformat()
    
    # Update position
    if args.qty == shares:
        # Sold completely, delete position
        del positions[code]
    else:
        # Subtract shares and update cost
        pos["shares"] -= args.qty
        pos["available_shares"] -= args.qty
        pos["total_cost"] = round(pos["cost_per_share"] * pos["shares"], 2)
        
    # Save portfolio
    portfolio_path.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Save transaction history
    history_path = sim_dir / "history.csv"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_record = f"{timestamp},{code},{name},SELL,{price:.2f},{args.qty},{trade_amount:.2f},{commission:.2f},{stamp_tax:.2f},{transfer_fee:.2f},{net_inflow:.2f}\n"
    
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(history_record)
        
    print("==================================================")
    print(" SELL ORDER EXECUTED (卖出委托已成交)")
    print("==================================================")
    print(f" Stock         : {code} ({name})")
    print(f" Quantity      : {args.qty} shares")
    print(f" Price         : {price:.2f} Yuan")
    print(f" Net Amount    : {trade_amount:,.2f} Yuan")
    print(f" Commission    : {commission:.2f} Yuan")
    print(f" Transfer Fee  : {transfer_fee:.2f} Yuan")
    print(f" Stamp Tax     : {stamp_tax:.2f} Yuan")
    print(f" Net Cash In   : {net_inflow:,.2f} Yuan")
    print(f" Remaining Cash: {portfolio['cash']:,.2f} Yuan")
    print("==================================================")

if __name__ == "__main__":
    place_sell_order()
