#!/usr/bin/env python3
"""Strict three-phase report workflow.

`capture` collects an atomic phase snapshot. `prepare` assembles a report
bundle only when every required input is ready. `validate` rejects reports that
were written without a ready bundle or contain uncited quantitative claims.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
MARKET_PYTHON = ROOT / "skills" / "market" / ".venv" / "bin" / "python"
MARKET_SCRIPT = ROOT / "skills" / "market" / "scripts" / "report_data.py"
DATA_DIR = SKILL_DIR / "data"
REPORT_DIR = ROOT / "report"

PHASE_LABEL = {"pre": "盘前计划", "noon": "盘中复盘", "post": "盘后复盘"}
TEMPLATE_NAME = {"pre": "pre_market.md", "noon": "intraday_review.md", "post": "post_market.md"}
CAPTURE_DATASETS = {
    "noon": {"market_snapshot_noon", "fund_flows_noon", "limit_activity", "index_history"},
    "close": {"market_snapshot_close", "fund_flows_close", "limit_activity", "index_history", "dragon_tiger"},
}
REQUIRED_HEADINGS = {
    "pre": ["## 数据状态", "## 隔夜与市场背景", "## 前一交易日结构", "## 今日观察框架", "## 风险与失效条件", "## 数据来源"],
    "noon": ["## 数据状态", "## 上午市场事实", "## 与盘前假设的对照", "## 结构变化", "## 下午观察框架", "## 数据来源"],
    "post": ["## 数据状态", "## 收盘事实", "## 盘前与盘中判断复核", "## 题材生命周期", "## 龙虎榜事实", "## 次日研究清单", "## 数据来源"],
}
FORBIDDEN = ["sim-trade", "sim_trade", "模拟交易", "仿真交易", "纸上交易"]


class WorkflowError(RuntimeError):
    pass


def parse_day(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise WorkflowError(f"日期必须为 YYYYMMDD：{value}") from exc


def phase_dir(day: str) -> Path:
    return DATA_DIR / day


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"无法读取数据文件 {path}：{exc}") from exc
    if data.get("status") != "ready":
        raise WorkflowError(f"数据未就绪：{path}")
    if any(not item.get("passed") for item in data.get("checks", [])):
        raise WorkflowError(f"数据校验未全部通过：{path}")
    return data


def market_call(dataset: str, day: str, **options: Any) -> dict[str, Any]:
    if not MARKET_PYTHON.exists():
        raise WorkflowError(
            "market 虚拟环境不存在；先运行 uv venv skills/market/.venv，"
            "再安装 skills/market/requirements.txt"
        )
    command = [str(MARKET_PYTHON), str(MARKET_SCRIPT), dataset, "--date", day]
    for key, value in options.items():
        command.extend([f"--{key.replace('_', '-')}", str(value)])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
        raise WorkflowError(f"{dataset} 获取失败：{detail}")
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"{dataset} 输出不是有效 JSON：{result.stdout[-300:]}") from exc
    if document.get("status") != "ready":
        raise WorkflowError(f"{dataset} 返回未就绪状态")
    return document


def capture(day: str, phase: str) -> dict[str, Any]:
    datasets: dict[str, dict[str, Any]] = {}
    specs = [
        ("snapshot", {"session": phase}),
        ("flows", {"session": phase}),
        ("limits", {}),
        ("indices", {"count": 60}),
    ]
    if phase == "close":
        specs.append(("lhb", {}))
    collecting = {
        "schema_version": 1,
        "kind": "capture_manifest",
        "date": day,
        "phase": phase,
        "status": "collecting",
        "datasets": [],
        "errors": [],
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    manifest_path = phase_dir(day) / f"capture_{phase}.json"
    # The manifest is the commit marker. Overwrite any older ready marker before
    # network collection so interrupted or partial refreshes cannot be consumed.
    atomic_json(manifest_path, collecting)
    errors = []
    for name, options in specs:
        try:
            document = market_call(name, day, **options)
            key = document["dataset"]
            datasets[key] = document
        except WorkflowError as exc:
            errors.append(str(exc))
    manifest = {
        "schema_version": 1,
        "kind": "capture_manifest",
        "date": day,
        "phase": phase,
        "status": "blocked" if errors else "ready",
        "datasets": sorted(datasets),
        "errors": errors,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if errors:
        atomic_json(manifest_path, manifest)
        raise WorkflowError("；".join(errors))
    actual = set(datasets)
    if actual != CAPTURE_DATASETS[phase]:
        manifest["status"] = "blocked"
        manifest["errors"] = [
            f"数据集集合不匹配：要求 {sorted(CAPTURE_DATASETS[phase])}，取得 {sorted(actual)}"
        ]
        atomic_json(manifest_path, manifest)
        raise WorkflowError(manifest["errors"][0])
    for key, document in datasets.items():
        atomic_json(phase_dir(day) / f"{key}.json", document)
    atomic_json(manifest_path, manifest)
    return manifest


def _calendar_for(day: str) -> dict[str, Any]:
    return market_call("calendar", day, count=10)


def _evidence(datasets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for number, (key, document) in enumerate(sorted(datasets.items()), start=1):
        items.append({
            "id": f"E{number:02d}",
            "dataset_key": key,
            "dataset": document["dataset"],
            "target_date": document["target_date"],
            "source": document["source"],
            "retrieved_at": document["retrieved_at"],
            "checks": document["checks"],
        })
    return items


def _read_report(day: str, phase: str) -> Path:
    path = REPORT_DIR / f"{day}_{PHASE_LABEL[phase]}.md"
    if not path.exists():
        raise WorkflowError(f"前置报告不存在：{path}")
    return path


def _snapshot(day: str, name: str) -> dict[str, Any]:
    document = load_json(phase_dir(day) / f"{name}.json")
    if document.get("target_date") != day:
        raise WorkflowError(
            f"快照日期不匹配：{name} 标记 {document.get('target_date')}，要求 {day}"
        )
    return document


def _capture_manifest(day: str, phase: str) -> dict[str, Any]:
    manifest = load_json(phase_dir(day) / f"capture_{phase}.json")
    if manifest.get("kind") != "capture_manifest" or manifest.get("date") != day or manifest.get("phase") != phase:
        raise WorkflowError(f"{day} {phase} capture manifest 身份不匹配")
    actual = set(manifest.get("datasets", []))
    required = CAPTURE_DATASETS[phase]
    if actual != required:
        raise WorkflowError(f"capture manifest 数据集不完整：要求 {sorted(required)}，取得 {sorted(actual)}")
    return manifest


def _validated_report(day: str, phase: str) -> Path:
    path = _read_report(day, phase)
    validate(day, phase, str(path))
    return path


def prepare(day: str, phase: str) -> dict[str, Any]:
    calendar = _calendar_for(day)
    if not calendar["data"]["is_trading_day"]:
        raise WorkflowError(f"{day} 不是交易日，不生成报告")
    previous = calendar["data"]["previous_trading_day"]
    datasets: dict[str, dict[str, Any]] = {"calendar": calendar}
    prerequisites: list[str] = []

    if phase == "pre":
        _capture_manifest(previous, "close")
        datasets["previous_close"] = _snapshot(previous, "market_snapshot_close")
        datasets["previous_flows"] = _snapshot(previous, "fund_flows_close")
        datasets["previous_indices"] = _snapshot(previous, "index_history")
        datasets["overnight"] = market_call("overnight", day)
        datasets["watchlist"] = market_call("watchlist", previous, count=120)
        recent = calendar["data"]["last_trading_days"][-6:-1]
        if len(recent) != 5:
            raise WorkflowError("无法确定前 5 个交易日")
        for recent_day in recent:
            datasets[f"limits_{recent_day}"] = market_call("limits", recent_day)
    elif phase == "noon":
        prerequisites.append(str(_validated_report(day, "pre")))
        _capture_manifest(day, "noon")
        datasets["noon_snapshot"] = _snapshot(day, "market_snapshot_noon")
        datasets["noon_flows"] = _snapshot(day, "fund_flows_noon")
        datasets["noon_limits"] = _snapshot(day, "limit_activity")
        datasets["noon_indices"] = _snapshot(day, "index_history")
        pre_bundle = load_json(phase_dir(day) / "pre_bundle.json")
        datasets["pre_bundle_manifest"] = {
            "dataset": "pre_bundle_manifest", "target_date": day,
            "source": str(phase_dir(day) / "pre_bundle.json"),
            "retrieved_at": pre_bundle["created_at"], "status": "ready", "checks": [],
            "data": {"bundle_id": pre_bundle["bundle_id"]},
        }
    else:
        prerequisites.extend([str(_validated_report(day, "pre")), str(_validated_report(day, "noon"))])
        _capture_manifest(day, "close")
        datasets["close_snapshot"] = _snapshot(day, "market_snapshot_close")
        datasets["close_flows"] = _snapshot(day, "fund_flows_close")
        datasets["close_limits"] = _snapshot(day, "limit_activity")
        datasets["close_indices"] = _snapshot(day, "index_history")
        datasets["dragon_tiger"] = _snapshot(day, "dragon_tiger")

    bundle_id = f"{day}-{phase}-{datetime.now().astimezone():%Y%m%dT%H%M%S%z}"
    bundle = {
        "schema_version": 1,
        "kind": "report_bundle",
        "bundle_id": bundle_id,
        "date": day,
        "phase": phase,
        "status": "ready",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "prerequisites": prerequisites,
        "evidence": _evidence(datasets),
        "datasets": datasets,
        "template": str(SKILL_DIR / "templates" / TEMPLATE_NAME[phase]),
        "report_path": str(REPORT_DIR / f"{day}_{PHASE_LABEL[phase]}.md"),
    }
    path = phase_dir(day) / f"{phase}_bundle.json"
    atomic_json(path, bundle)
    return {"status": "ready", "bundle": str(path), "template": bundle["template"],
            "report_path": bundle["report_path"], "bundle_id": bundle_id}


def validate(day: str, phase: str, report_arg: str | None) -> dict[str, Any]:
    bundle_path = phase_dir(day) / f"{phase}_bundle.json"
    bundle = load_json(bundle_path)
    if bundle.get("phase") != phase or bundle.get("date") != day:
        raise WorkflowError("数据包日期或阶段不匹配")
    report = Path(report_arg) if report_arg else Path(bundle["report_path"])
    if not report.is_absolute():
        report = ROOT / report
    if not report.exists():
        raise WorkflowError(f"报告不存在：{report}")
    text = report.read_text(encoding="utf-8")
    errors = []
    if bundle["bundle_id"] not in text:
        errors.append("报告未声明对应 bundle_id")
    for heading in REQUIRED_HEADINGS[phase]:
        if heading not in text:
            errors.append(f"缺少章节：{heading}")
    for token in FORBIDDEN:
        if token.lower() in text.lower():
            errors.append(f"包含禁止内容：{token}")
    valid_ids = {item["id"] for item in bundle["evidence"]}
    cited_ids = set(re.findall(r"\[(E\d{2})\]", text))
    unknown = cited_ids - valid_ids
    if unknown:
        errors.append(f"引用了不存在的证据：{sorted(unknown)}")
    quantitative = re.compile(r"\d+(?:\.\d+)?\s*(?:%|亿元|万元|元|点|家|只|条|倍)")
    for line_no, line in enumerate(text.splitlines(), start=1):
        if quantitative.search(line) and not re.search(r"\[E\d{2}\]", line):
            errors.append(f"第 {line_no} 行的量化陈述没有证据编号")
    if not cited_ids:
        errors.append("报告没有任何证据引用")
    if errors:
        raise WorkflowError("；".join(errors))
    return {"status": "ready", "report": str(report), "bundle": str(bundle_path),
            "citations": sorted(cited_ids)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="盘前/盘中/盘后严格报告工作流")
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture", help="采集午间或收盘不可回溯快照")
    capture_parser.add_argument("--date", required=True)
    capture_parser.add_argument("--phase", choices=["noon", "close"], required=True)
    prepare_parser = sub.add_parser("prepare", help="严格组装报告数据包")
    prepare_parser.add_argument("--date", required=True)
    prepare_parser.add_argument("--phase", choices=["pre", "noon", "post"], required=True)
    validate_parser = sub.add_parser("validate", help="验证报告结构和证据引用")
    validate_parser.add_argument("--date", required=True)
    validate_parser.add_argument("--phase", choices=["pre", "noon", "post"], required=True)
    validate_parser.add_argument("--report")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        day = parse_day(args.date)
        if args.command == "capture":
            result = capture(day, args.phase)
        elif args.command == "prepare":
            result = prepare(day, args.phase)
        else:
            result = validate(day, args.phase, args.report)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
