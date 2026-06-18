import sys
from pathlib import Path
import json
from datetime import datetime, timedelta
import pandas as pd

import akshare_patch
import akshare as ak

def load_portfolio_and_sync(portfolio_path):
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    
    # Parse last updated time
    updated_at = datetime.fromisoformat(portfolio["updated_at"])
    today = datetime.now()
    
    # Check if we crossed a calendar day boundary
    if today.date() > updated_at.date():
        # T+1 Rollover: all held shares become sellable (available)
        for code, pos in portfolio["positions"].items():
            pos["available_shares"] = pos["shares"]
        portfolio["updated_at"] = today.isoformat()
        portfolio_path.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
        
    return portfolio

def show_portfolio():
    sim_dir = Path(__file__).resolve().parents[1] / "data" / "simulation"
    portfolio_path = sim_dir / "portfolio.json"
    
    if not portfolio_path.exists():
        print("Error: Simulation portfolio does not exist. Please run reset.py first.")
        sys.exit(1)
        
    # Load and sync T+1 available shares
    portfolio = load_portfolio_and_sync(portfolio_path)
    
    account_name = portfolio["account_name"]
    cash = portfolio["cash"]
    frozen_cash = portfolio.get("frozen_cash", 0.0)
    positions = portfolio["positions"]
    
    # Read initial capital or calculate fallback from positions cost basis + cash
    initial_capital = portfolio.get("initial_capital", cash + sum(pos["total_cost"] for pos in positions.values()))
    
    print("==================================================")
    print(f" SIMULATION PORTFOLIO: {account_name}")
    print(f" Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    print(f" Cash Available : {cash:,.2f} Yuan")
    if frozen_cash > 0:
        print(f" Cash Frozen    : {frozen_cash:,.2f} Yuan")
    
    if not positions:
        total_assets = cash
        total_return = total_assets - initial_capital
        total_return_pct = (total_return / initial_capital * 100) if initial_capital > 0 else 0.0
        print("\n No active holdings (空仓状态)")
        print(f" Total Assets   : {total_assets:,.2f} Yuan")
        print(f" Total Return   : {total_return:+,.2f} Yuan ({total_return_pct:+.2f}%)")
        print("==================================================")
        return
        
    # Fetch real-time prices for positions in a single batch
    print("\nFetching real-time prices for holdings...")
    rows = []
    total_market_value = 0.0
    total_cost_basis = 0.0
    
    # Batch query prices from Sina direct API
    realtime_prices = {}
    try:
        realtime_prices = akshare_patch.get_multi_stocks_realtime(list(positions.keys()))
    except Exception as e:
        print(f"  Warning: Sina direct API batch query failed: {e}. Falling back to individual stock queries.")
        
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)  # look back 7 days to cover weekends/holidays
    
    for code, pos in positions.items():
        name = pos["name"]
        shares = pos["shares"]
        available = pos["available_shares"]
        avg_cost = pos["cost_per_share"]
        total_cost = pos["total_cost"]
        
        current_price = avg_cost # fallback
        if code in realtime_prices and realtime_prices[code]["price"] > 0:
            current_price = realtime_prices[code]["price"]
        else:
            try:
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                    adjust="qfq"
                )
                if df is not None and not df.empty:
                    current_price = float(df.iloc[-1]["收盘"])
            except Exception as e:
                print(f"  Warning: Could not fetch real-time price for {code} ({name}): {str(e)}. Using cost as current price.")
            
        market_value = shares * current_price
        pnl = market_value - total_cost
        pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0
        
        total_market_value += market_value
        total_cost_basis += total_cost
        
        rows.append({
            "Code": code,
            "Name": name,
            "Shares": shares,
            "Available": available,
            "AvgCost": f"{avg_cost:.2f}",
            "Current": f"{current_price:.2f}",
            "MarketValue": f"{market_value:.2f}",
            "P&L": f"{pnl:+.2f}",
            "P&L%": f"{pnl_pct:+.2f}%"
        })
        
    # Print positions table
    df_display = pd.DataFrame(rows)
    print("\nPositions (持仓明细):")
    print(df_display.to_string(index=False))
    
    # Calculate totals
    total_assets = cash + total_market_value
    total_return = total_assets - initial_capital
    total_return_pct = (total_return / initial_capital * 100) if initial_capital > 0 else 0.0
    
    print("\nSummary (账户汇总):")
    print(f" Total Cost Basis: {total_cost_basis:,.2f} Yuan")
    print(f" Market Value    : {total_market_value:,.2f} Yuan")
    print(f" Total Assets    : {total_assets:,.2f} Yuan")
    print(f" Total Return    : {total_return:+,.2f} Yuan ({total_return_pct:+.2f}%)")
    print("==================================================")

if __name__ == "__main__":
    show_portfolio()
