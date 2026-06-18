"""
A-share Daily Trading Journal Manager

Part of the plan-review skill. Manages one markdown file per day at
`data/journal/YYYYMMDD.md` with three sections:
  - ## 盘前计划 (Pre-market Plan)
  - ## 午间复盘 (Noon Review)
  - ## 晚间复盘 (Evening Review)

Usage:
  journal.py create                        Create today's journal (reads plan from stdin)
  journal.py create --plan "plan text"     Create today's journal with inline plan
  journal.py append --section noon         Append noon review (reads from stdin)
  journal.py append --section evening      Append evening review (reads from stdin)
  journal.py append --section noon --content "text"   Inline content
  journal.py view                          View today's journal
  journal.py view --date 20260617          View a specific day
  journal.py list --n 5                    List recent 5 journal entries
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Resolve project root: this script is at skills/plan-review/scripts/journal.py
# parents[3] = project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
JOURNAL_DIR = PROJECT_ROOT / "data" / "journal"

SECTION_HEADERS = {
    "plan": "## 盘前计划",
    "noon": "## 午间复盘",
    "evening": "## 晚间复盘",
}


def get_today_str() -> str:
    return datetime.now().strftime("%Y%m%d")


def get_today_display() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def journal_path(date_str: str) -> Path:
    return JOURNAL_DIR / f"{date_str}.md"


def ensure_journal_dir():
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def read_content_from_stdin(prompt: str = "") -> str:
    """Read multi-line content from stdin until EOF (Ctrl+D)."""
    if prompt:
        print(prompt, file=sys.stderr)
    return sys.stdin.read().strip()


def find_section_line(lines, section_header):
    """Find the line index of a section header. Returns None if not found."""
    for idx, line in enumerate(lines):
        if line.strip() == section_header:
            return idx
    return None


def file_exists_or_create(date_str: str) -> Path:
    """Ensure journal file exists for today; create with header if not."""
    ensure_journal_dir()
    path = journal_path(date_str)
    if not path.exists():
        display = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d") if len(date_str) == 8 else date_str
        header = f"# 交易日志 {display}\n\n"
        path.write_text(header, encoding="utf-8")
    return path


# ─── Command implementations ────────────────────────────────────────────────


def cmd_create(args: argparse.Namespace) -> None:
    """Create today's journal with the pre-market plan section."""
    date_str = get_today_str()
    path = file_exists_or_create(date_str)

    content = args.plan if args.plan else read_content_from_stdin(
        "输入盘前计划内容（多行，Ctrl+D 结束）..."
    )
    content = content.replace("\\n", "\n")
    if not content:
        print("Error: Plan content is empty. Nothing saved.", file=sys.stderr)
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").splitlines()

    # Check if plan section already exists
    existing = find_section_line(lines, SECTION_HEADERS["plan"])
    if existing is not None:
        print(f"Warning: Plan section already exists in {date_str}.md. Overwriting.", file=sys.stderr)
        # Remove existing plan section (from header to next header or end)
        end_idx = _find_next_section(lines, existing + 1)
        lines = lines[:existing] + lines[end_idx:]

    # Find insertion point: after the title or after the last section before plan
    insert_idx = _find_insertion_point(lines, SECTION_HEADERS["plan"])
    section_block = [SECTION_HEADERS["plan"], "", content.rstrip("\n"), ""]
    lines[insert_idx:insert_idx] = section_block

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 盘前计划已保存到: {path}")


def cmd_append(args: argparse.Namespace) -> None:
    """Append a review section (noon or evening) to today's journal."""
    date_str = get_today_str()
    path = file_exists_or_create(date_str)

    section_key = args.section  # "noon" or "evening"
    header = SECTION_HEADERS[section_key]

    content = args.content if args.content else read_content_from_stdin(
        f"输入{section_key}复盘内容（多行，Ctrl+D 结束）..."
    )
    content = content.replace("\\n", "\n")
    if not content:
        print(f"Error: {section_key} review content is empty. Nothing saved.", file=sys.stderr)
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").splitlines()

    # Check if section already exists
    existing = find_section_line(lines, header)
    if existing is not None:
        print(f"Warning: {header} already exists. Overwriting.", file=sys.stderr)
        end_idx = _find_next_section(lines, existing + 1)
        lines = lines[:existing] + lines[end_idx:]

    # Find insertion point
    insert_idx = _find_insertion_point(lines, header)
    section_block = [header, "", content.rstrip("\n"), ""]
    lines[insert_idx:insert_idx] = section_block

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ {header} 已保存到: {path}")


def cmd_view(args: argparse.Namespace) -> None:
    """Display journal for a specific date (default: today)."""
    date_str = args.date if args.date else get_today_str()
    path = journal_path(date_str)

    if not path.exists():
        print(f"No journal found for {date_str}.", file=sys.stderr)
        sys.exit(1)

    print(path.read_text(encoding="utf-8").rstrip())


def cmd_list(args: argparse.Namespace) -> None:
    """List recent journal entries."""
    ensure_journal_dir()
    if not JOURNAL_DIR.exists():
        print("No journal entries found.")
        return

    files = sorted(JOURNAL_DIR.glob("*.md"), reverse=True)
    count = args.n

    if not files:
        print("No journal entries found.")
        return

    print(f"Recent {min(count, len(files))} journal entries:")
    print()
    for f in files[:count]:
        # Read first line (title) for a summary
        first_line = f.read_text(encoding="utf-8").splitlines()[0] if f.stat().st_size > 0 else "(empty)"
        # Count sections
        content = f.read_text(encoding="utf-8")
        sections = sum(1 for h in SECTION_HEADERS.values() if h in content)
        print(f"  {f.stem}  |  {first_line}  |  {sections}/3 sections")


# ─── Internal helpers ───────────────────────────────────────────────────────


def _find_next_section(lines, start):
    """Find the next section header after `start`. Returns len(lines) if none."""
    headers = set(SECTION_HEADERS.values())
    for i in range(start, len(lines)):
        if lines[i].strip() in headers:
            return i
    return len(lines)


def _find_insertion_point(lines, target_header):
    """
    Find where to insert `target_header` in the file.
    Insert in logical order: plan → noon → evening.
    If later sections already exist, insert before them.
    If the target already exists (shouldn't happen here), return its position.
    """
    # Ordered list of headers
    ordered = [SECTION_HEADERS["plan"], SECTION_HEADERS["noon"], SECTION_HEADERS["evening"]]
    target_idx = ordered.index(target_header)

    # Find positions of existing sections
    positions = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ordered:
            positions[stripped] = i

    # If there's a section after the target, insert before it
    for header in ordered[target_idx + 1:]:
        if header in positions:
            return positions[header]

    # If the target is the plan and noon exists, insert before noon
    if target_header == SECTION_HEADERS["plan"] and SECTION_HEADERS["noon"] in positions:
        return positions[SECTION_HEADERS["noon"]]

    # If the target is noon and evening exists, insert before evening
    if target_header == SECTION_HEADERS["noon"] and SECTION_HEADERS["evening"] in positions:
        return positions[SECTION_HEADERS["evening"]]

    # Otherwise, append at the end (after ensuring blank line)
    # If file ends with blank lines, insert before them
    end = len(lines)
    while end > 0 and lines[end - 1].strip() == "":
        end -= 1
    return end


# ─── CLI Entry Point ────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A-share trading journal manager (plan-review skill)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create today's journal with pre-market plan")
    p_create.add_argument("--plan", type=str, default=None,
                          help="Pre-market plan text (inline). If omitted, reads from stdin.")

    # append
    p_append = subparsers.add_parser("append", help="Append a section to today's journal")
    p_append.add_argument("--section", type=str, required=True, choices=["noon", "evening"],
                          help="Section to append")
    p_append.add_argument("--content", type=str, default=None,
                          help="Section content (inline). If omitted, reads from stdin.")

    # view
    p_view = subparsers.add_parser("view", help="View journal for a specific date")
    p_view.add_argument("--date", type=str, default=None,
                        help="Date in YYYYMMDD format (default: today)")

    # list
    p_list = subparsers.add_parser("list", help="List recent journal entries")
    p_list.add_argument("--n", type=int, default=10,
                        help="Number of entries to show (default: 10)")

    return parser.parse_args()


def main():
    args = parse_args()

    handlers = {
        "create": cmd_create,
        "append": cmd_append,
        "view": cmd_view,
        "list": cmd_list,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
