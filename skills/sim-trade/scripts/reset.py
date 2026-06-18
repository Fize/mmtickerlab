import sys
from pathlib import Path
import json
import argparse
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description="Reset or initialize simulation trading account")
    parser.add_argument("--cash", type=float, default=None, help="Initial capital in Yuan")
    parser.add_argument("--name", type=str, default=None, help="Account name")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    return parser.parse_args()

def confirm_action(prompt_msg):
    while True:
        choice = input(f"{prompt_msg} [y/n]: ").strip().lower()
        if choice in ["y", "yes"]:
            return True
        elif choice in ["n", "no"]:
            return False
        print("Please enter 'y' or 'n'.")

def reset_account():
    args = parse_args()
    
    # Check if stdin is interactive (tty) to decide if we should prompt
    is_interactive = sys.stdin.isatty() and not args.yes
    
    # Determine account name
    if args.name is not None:
        account_name = args.name
    elif is_interactive:
        val = input("Enter Account Name (default: '我的模拟账户'): ").strip()
        account_name = val if val else "我的模拟账户"
    else:
        account_name = "我的模拟账户"
        
    # Determine initial cash
    if args.cash is not None:
        initial_cash = args.cash
    elif is_interactive:
        while True:
            val = input("Enter Initial Capital (default: 500000): ").strip()
            if not val:
                initial_cash = 500000.0
                break
            try:
                initial_cash = float(val)
                if initial_cash <= 0:
                    print("Capital must be greater than 0.")
                    continue
                break
            except ValueError:
                print("Invalid number. Please enter a float value.")
    else:
        initial_cash = 500000.0
        
    # Confirm reset
    if is_interactive:
        msg = f"Resetting simulation account '{account_name}' with {initial_cash:,.2f} Yuan. All existing positions and trading history will be DELETED. Continue?"
        if not confirm_action(msg):
            print("Reset cancelled.")
            sys.exit(0)
            
    # Create directory structure
    sim_dir = Path(__file__).resolve().parents[1] / "data" / "simulation"
    sim_dir.mkdir(parents=True, exist_ok=True)
    
    portfolio_path = sim_dir / "portfolio.json"
    history_path = sim_dir / "history.csv"
    
    # Initialize portfolio dict
    portfolio = {
      "account_name": account_name,
      "cash": initial_cash,
      "initial_capital": initial_cash,
      "frozen_cash": 0.0,
      "positions": {},
      "created_at": datetime.now().strftime("%Y-%m-%d"),
      "updated_at": datetime.now().isoformat()
    }
    
    try:
        # Write portfolio
        portfolio_path.write_text(json.dumps(portfolio, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Initialize history CSV with headers
        headers = "timestamp,code,name,action,price,qty,amount,commission,stamp_tax,transfer_fee,total_cost\n"
        history_path.write_text(headers, encoding="utf-8")
        
        print("==================================================")
        print(" SIMULATION ACCOUNT RESET SUCCESSFUL")
        print(f" Account Name: {account_name}")
        print(f" Initial Cash: {initial_cash:,.2f} Yuan")
        print(f" Data Directory: {sim_dir}")
        print("==================================================")
    except Exception as e:
        print(f"Error resetting simulation account: {type(e).__name__}: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    reset_account()
