#!/usr/bin/env python3
"""Scanner and indexer for standardized reports in MMTickerLab."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

CATEGORY_LABELS = {
    "daily": "日内复盘",
    "ticker": "个股投研",
    "strategy": "策略决策",
    "industry": "行业研报",
    "sop": "SOP摘要",
    "general": "通用报告",
}


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter using standard library without external PyYAML."""
    frontmatter: dict[str, Any] = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_fm = parts[1]
            body = parts[2].lstrip("\r\n")
            for line in raw_fm.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    was_quoted = (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'"))
                    if was_quoted:
                        val = val[1:-1]
                        frontmatter[key] = val
                    elif val.lower() == "true":
                        frontmatter[key] = True
                    elif val.lower() == "false":
                        frontmatter[key] = False
                    elif key == "code":
                        frontmatter[key] = val
                    else:
                        try:
                            if "." in val:
                                frontmatter[key] = float(val)
                            else:
                                frontmatter[key] = int(val)
                        except ValueError:
                            frontmatter[key] = val
    return frontmatter, body


def infer_metadata_from_text(filename: str, body: str, parent_dir: str) -> dict[str, Any]:
    """Fallback extraction when frontmatter is absent."""
    meta: dict[str, Any] = {}

    # 1. Title
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if title_match:
        meta["title"] = title_match.group(1).strip()
    else:
        meta["title"] = Path(filename).stem

    # 2. Date
    date_match = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", filename)
    if date_match:
        meta["date"] = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    else:
        date_body = re.search(r"基准日期[：:]\s*(\d{4}-\d{2}-\d{2})", body) or re.search(r"日期[：:]\s*(\d{4}-\d{2}-\d{2})", body)
        if date_body:
            meta["date"] = date_body.group(1)
        else:
            meta["date"] = datetime.now().strftime("%Y-%m-%d")

    # 3. Category
    if parent_dir in CATEGORY_LABELS:
        meta["category"] = parent_dir
    else:
        if "盘前" in filename or "盘中" in filename or "盘后" in filename:
            meta["category"] = "daily"
        elif "投研" in filename or "决策总报" in filename:
            meta["category"] = "ticker"
        elif "首板" in filename or "隔夜" in filename:
            meta["category"] = "strategy"
        elif "行业" in filename:
            meta["category"] = "industry"
        elif "SOP" in filename:
            meta["category"] = "sop"
        else:
            meta["category"] = "general"

    # 4. Stock Code & Name
    code_match = re.search(r"(?:^|_)(\d{6})(?:_|\.|\b)", filename) or re.search(r"\((\d{6})\)", body)
    if code_match:
        meta["code"] = code_match.group(1)

    # 5. VETO & Rating
    if "VETO: PASSED" in body or "风控合规已放行" in body:
        meta["veto_status"] = "PASSED"
    elif "VETO: BLOCKED" in body or "一票否决" in body or "风控阻断" in body:
        meta["veto_status"] = "BLOCKED"
    elif "数据盲区" in body or "SAFE HALTED" in body:
        meta["veto_status"] = "WAITING_DATA"

    rating_match = re.search(r"(🟢\s*强烈推荐买入|🟡\s*逢低试仓配置|⚪\s*观望持有|🔴\s*减仓卖出)", body)
    if rating_match:
        meta["rating"] = rating_match.group(1).strip()

    return meta


def scan_reports(report_dir: Path | str) -> list[dict[str, Any]]:
    """Recursively scan report directory and return structured metadata list."""
    base_path = Path(report_dir).resolve()
    if not base_path.exists():
        return []

    reports: list[dict[str, Any]] = []

    for file_path in sorted(base_path.rglob("*.md")):
        if file_path.name.startswith("."):
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        rel_path = file_path.relative_to(base_path)
        frontmatter, body = parse_frontmatter(content)
        parent_dir = rel_path.parent.name if rel_path.parent != Path(".") else ""

        # Merge frontmatter with inferred metadata
        inferred = infer_metadata_from_text(file_path.name, body, parent_dir)
        merged = {**inferred, **frontmatter}

        # Normalize date format
        raw_date = str(merged.get("date", ""))
        if re.match(r"^\d{8}$", raw_date):
            normalized_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        else:
            normalized_date = raw_date

        cat = str(merged.get("category", "general")).lower()
        stat = file_path.stat()
        file_hash = hashlib.md5(str(rel_path).encode("utf-8")).hexdigest()[:10]

        summary = merged.get("summary")
        if not summary:
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith("#") and not p.strip().startswith(">")]
            summary = paragraphs[0][:150] + ("..." if len(paragraphs[0]) > 150 else "") if paragraphs else ""

        item = {
            "id": file_hash,
            "relative_path": str(rel_path),
            "filename": file_path.name,
            "title": merged.get("title", file_path.stem),
            "date": normalized_date,
            "category": cat,
            "category_label": CATEGORY_LABELS.get(cat, "通用"),
            "code": str(merged.get("code", "")),
            "ticker_name": str(merged.get("ticker_name", "")),
            "rating": str(merged.get("rating", "")),
            "veto_status": str(merged.get("veto_status", "")),
            "summary": summary,
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        reports.append(item)

    reports.sort(key=lambda r: (r["date"], r["mtime"]), reverse=True)
    return reports


def get_report_detail(report_dir: Path | str, relative_path: str) -> dict[str, Any] | None:
    """Read a specific report file and return metadata plus markdown content."""
    base_path = Path(report_dir).resolve()
    target_path = (base_path / relative_path).resolve()

    try:
        target_path.relative_to(base_path)
    except ValueError:
        return None

    if not target_path.exists() or not target_path.is_file():
        return None

    content = target_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)
    parent_dir = target_path.parent.name if target_path.parent != base_path else ""
    inferred = infer_metadata_from_text(target_path.name, body, parent_dir)
    merged = {**inferred, **frontmatter}

    return {
        "relative_path": str(target_path.relative_to(base_path)),
        "filename": target_path.name,
        "metadata": merged,
        "raw_content": content,
        "body_markdown": body,
    }


if __name__ == "__main__":
    import sys
    rdir = sys.argv[1] if len(sys.argv) > 1 else "report"
    res = scan_reports(rdir)
    print(json.dumps(res, ensure_ascii=False, indent=2))
