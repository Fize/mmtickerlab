import sys
from pathlib import Path
import pandas as pd
import argparse

# Add project root to sys.path
import akshare_patch

def parse_args():
    parser = argparse.ArgumentParser(description="View transaction history")
    parser.add_argument("--code", type=str, default=None, help="Filter history by 6-digit stock code")
    parser.add_argument("--n", type=int, default=20, help="Number of records to display (default: 20)")
    return parser.parse_args()

def clean_stock_code(code: str) -> str:
    if not code:
        return ""
    clean = code.strip().upper()
    if "." in clean:
        clean = clean.split(".")[0]
    for prefix in ["SH", "SZ", "BJ"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
        if clean.endswith(prefix):
            clean = clean[:-len(prefix)]
    clean = clean.strip()
    return clean

def show_history():
    args = parse_args()
    
    sim_dir = Path(__file__).resolve().parents[1] / "data" / "simulation"
    history_path = sim_dir / "history.csv"
    
    if not history_path.exists():
        print("Error: History file does not exist. Run reset.py first.")
        sys.exit(1)
        
    print("==================================================")
    print(" SIMULATION TRANSACTION HISTORY")
    print("==================================================")
    
    try:
        # Load CSV, specifying code as str to preserve leading zeros
        df = pd.read_csv(history_path, dtype={"code": str})
        
        if df.empty:
            print("No transactions recorded yet.")
            print("==================================================")
            return
            
        # Clean and filter by code if provided
        if args.code:
            target_code = clean_stock_code(args.code)
            df = df[df["code"] == target_code]
            if df.empty:
                print(f"No transactions found for stock code: {target_code}")
                print("==================================================")
                return
                
        # Show latest transactions first (reverse chronological order)
        df_display = df.iloc[::-1].head(args.n).copy()
        
        # Format columns for print
        print(df_display.to_string(index=False))
        print("==================================================")
        
    except Exception as e:
        print(f"Error loading transaction history: {type(e).__name__}: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    show_history()
