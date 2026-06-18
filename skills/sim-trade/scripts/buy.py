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

def get_exchange_market(code: str) -> str:
    if code.startswith(('60', '68', '51')):
        return "sh"
    elif code.startswith(('00', '30')):
        return "sz"
    elif code.startswith(('8', '4')):
        return "bj"
    else:
        raise ValueError(f"Unknown exchange for stock code: {code}")

def get_stock_name(code: str) -> str:
    cache_path = Path(__file__).resolve().parents[1] / "data" / "stock_names.json"
    names = {}
    if cache_path.exists():
        try:
            names = json.loads(cache_path.read_text(encoding="utf-8"))
            if code in names:
                return names[code]
        except Exception:
            pass
            
    # Try direct Sina API first
    try:
        info = akshare_patch.get_single_stock_realtime(code)
        if info and info.get("name"):
            names[code] = info["name"]
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(names, indent=2, ensure_ascii=False), encoding="utf-8")
            return info["name"]
    except Exception:
        pass

    try:
        print("Fetching stock name from Sina spot list...")
        df = ak.stock_zh_a_spot()
        if df is not None and not df.empty:
            df["代码"] = df["代码"].str[-6:]
            for _, row in df.iterrows():
                names[str(row["代码"])] = str(row["名称"])
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(names, indent=2, ensure_ascii=False), encoding="utf-8")
            if code in names:
                return names[code]
    except Exception as e:
        print(f"Warning: Could not fetch stock name: {e}")
        
    return "未知股票"

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
    parser = argparse.ArgumentParser(description="Place a simulation buy order")
    parser.add_argument("code", type=str, help="Stock code (e.g. 600519)")
    parser.add_argument("qty", type=int, help="Quantity to buy (must be multiple of 100)")
    parser.add_argument("--price", type=float, default=None, help="Execution limit price (defaults to real-time close)")
    parser.add_argument("--force", action="store_true", help="Bypass trading hours validation")
    return parser.parse_args()

def place_buy_order():
    args = parse_args()
    
    try:
        code = clean_stock_code(args.code)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    # 1. Validate quantity
    if args.qty <= 0 or args.qty % 100 != 0:
        print(f"Error: A-share buy order quantity must be a positive multiple of 100 shares. Provided: {args.qty}")
        sys.exit(1)
        
    # 2. Validate trading hours
    if not args.force and not check_trading_hours():
        print("Error: Orders can only be placed during A-share trading hours (9:30-11:30, 13:00-15:00 on weekdays). Use --force to bypass this check.")
        sys.exit(1)
        
    # 3. Load Portfolio
    sim_dir = Path(__file__).resolve().parents[1] / "data" / "simulation"
    portfolio_path = sim_dir / "portfolio.json"
    if not portfolio_path.exists():
        print("Error: Portfolio file not found. Run reset.py first.")
        sys.exit(1)
        
    portfolio = load_portfolio_and_sync(portfolio_path)
    
    # 4. Fetch price data & metadata
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
        
    name = get_stock_name(code)
    
    # Determine limit price
    price = args.price if args.price is not None else current_price
    
    # 5. Validate price limits
    # ST stock limit is 5%; ChiNext (30)/Star (68) is 20%; Beijing (4/8) is 30%; Normal is 10%
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
        
    # 6. Calculate fees & cash requirements
    trade_amount = price * args.qty
    commission = max(5.0, trade_amount * 0.00025)
    transfer_fee = trade_amount * 0.00002
    stamp_tax = 0.0
    total_cost = trade_amount + commission + transfer_fee
    
    if total_cost > portfolio["cash"]:
        print(f"Error: Insufficient cash. Required: {total_cost:,.2f} Yuan, Available: {portfolio['cash']:,.2f} Yuan.")
        sys.exit(1)
        
    # 7. Execute order
    portfolio["cash"] -= total_cost
    portfolio["updated_at"] = datetime.now().isoformat()
    
    positions = portfolio["positions"]
    if code in positions:
        pos = positions[code]
        old_shares = pos["shares"]
        new_shares = old_shares + args.qty
        new_total_cost = pos["total_cost"] + trade_amount
        new_avg_cost = round(new_total_cost / new_shares, 2)
        
        pos["shares"] = new_shares
        # Note: available_shares does not increase today (T+1)
        pos["cost_per_share"] = new_avg_cost
        pos["total_cost"] = new_total_cost
        pos["buy_date"] = datetime.now().strftime("%Y-%m-%d")
    else:
        positions[code] = {
            "name": name,
            "shares": args.qty,
            "available_shares": 0,  # T+1 rule
            "buy_date": datetime.now().strftime("%Y-%m-%d"),
            "cost_per_share": price,
            "total_cost": trade_amount
        }
        
    # Save portfolio
    portfolio_path.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # Save transaction history
    history_path = sim_dir / "history.csv"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_record = f"{timestamp},{code},{name},BUY,{price:.2f},{args.qty},{trade_amount:.2f},{commission:.2f},{stamp_tax:.2f},{transfer_fee:.2f},{total_cost:.2f}\n"
    
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(history_record)
        
    print("==================================================")
    print(" BUY ORDER EXECUTED (买入委托已成交)")
    print("==================================================")
    print(f" Stock         : {code} ({name})")
    print(f" Quantity      : {args.qty} shares")
    print(f" Price         : {price:.2f} Yuan")
    print(f" Net Amount    : {trade_amount:,.2f} Yuan")
    print(f" Commission    : {commission:.2f} Yuan")
    print(f" Transfer Fee  : {transfer_fee:.2f} Yuan")
    print(f" Total Cash Out: {total_cost:,.2f} Yuan")
    print(f" Remaining Cash: {portfolio['cash']:,.2f} Yuan")
    print("==================================================")

if __name__ == "__main__":
    place_buy_order()
