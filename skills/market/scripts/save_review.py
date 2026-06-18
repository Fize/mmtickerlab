import sys
from pathlib import Path
import argparse
from datetime import datetime

project_root = str(Path(__file__).resolve().parents[3])

def parse_args():
    parser = argparse.ArgumentParser(description="Save noon or evening market review")
    parser.add_argument("--type", type=str, required=True, choices=["noon", "evening"], 
                        help="Review type: 'noon' or 'evening'")
    return parser.parse_args()

def save_review():
    args = parse_args()
    today_str = datetime.now().strftime("%Y%m%d")
    
    # Resolve directory path
    review_dir = Path(project_root) / "data" / "review" / args.type
    review_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = review_dir / f"{today_str}.md"
    
    print(f"Reading {args.type} review content from standard input (Ctrl+D to finish)...")
    content = sys.stdin.read().strip()
    
    if not content:
        print("Error: Review content is empty. Nothing was saved.")
        sys.exit(1)
        
    # Prepend date and time header if not present
    header = f"# A-Share {args.type.capitalize()} Review - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    full_content = header + content + "\n"
    
    try:
        file_path.write_text(full_content, encoding="utf-8")
        print(f"Successfully saved {args.type} review to: {file_path}")
    except Exception as e:
        print(f"Error saving review file: {type(e).__name__}: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    save_review()
