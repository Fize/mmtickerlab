from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "workflow.py"
SPEC = importlib.util.spec_from_file_location("plan_review_workflow", MODULE_PATH)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(workflow)


class WorkflowValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.data = base / "data"
        self.reports = base / "report"
        self.reports.mkdir()
        self.patchers = [
            mock.patch.object(workflow, "DATA_DIR", self.data),
            mock.patch.object(workflow, "REPORT_DIR", self.reports),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def _write_bundle(self, phase: str = "pre") -> dict:
        bundle = {
            "status": "ready",
            "checks": [],
            "kind": "report_bundle",
            "bundle_id": "20260813-pre-test",
            "date": "20260813",
            "phase": phase,
            "created_at": "2026-08-13T08:00:00+08:00",
            "report_path": str(self.reports / f"20260813_{workflow.PHASE_LABEL[phase]}.md"),
            "evidence": [{"id": "E01"}],
        }
        path = self.data / "20260813" / f"{phase}_bundle.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        return bundle

    def _valid_report(self, phase: str = "pre") -> str:
        headings = "\n\n".join(workflow.REQUIRED_HEADINGS[phase])
        return (
            f"# 报告\n\n> bundle_id: `20260813-pre-test`\n\n{headings}\n\n"
            "上涨 10 家 [E01]\n\n来源接口数据 [E01]\n"
        )

    def test_valid_report_passes(self) -> None:
        bundle = self._write_bundle()
        report = Path(bundle["report_path"])
        report.write_text(self._valid_report(), encoding="utf-8")
        result = workflow.validate("20260813", "pre", str(report))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["citations"], ["E01"])

    def test_uncited_number_blocks_report(self) -> None:
        bundle = self._write_bundle()
        report = Path(bundle["report_path"])
        report.write_text(self._valid_report().replace("上涨 10 家 [E01]", "上涨 10 家"), encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "量化陈述没有证据编号"):
            workflow.validate("20260813", "pre", str(report))

    def test_unknown_evidence_blocks_report(self) -> None:
        bundle = self._write_bundle()
        report = Path(bundle["report_path"])
        report.write_text(self._valid_report().replace("[E01]", "[E99]"), encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "不存在的证据"):
            workflow.validate("20260813", "pre", str(report))

    def test_missing_bundle_blocks_report(self) -> None:
        with self.assertRaisesRegex(workflow.WorkflowError, "无法读取数据文件"):
            workflow.validate("20260813", "pre", None)

    def test_snapshot_date_mismatch_is_rejected(self) -> None:
        path = self.data / "20260812" / "market_snapshot_close.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "status": "ready", "checks": [], "target_date": "20260811",
        }), encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "快照日期不匹配"):
            workflow._snapshot("20260812", "market_snapshot_close")

    def test_incomplete_capture_manifest_is_rejected(self) -> None:
        path = self.data / "20260812" / "capture_close.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "status": "ready", "checks": [], "kind": "capture_manifest",
            "date": "20260812", "phase": "close", "datasets": ["index_history"],
        }), encoding="utf-8")
        with self.assertRaisesRegex(workflow.WorkflowError, "数据集不完整"):
            workflow._capture_manifest("20260812", "close")

    def test_failed_capture_does_not_commit_partial_datasets(self) -> None:
        names = {
            "snapshot": "market_snapshot_noon",
            "limits": "limit_activity_noon",
            "indices": "index_history_noon",
        }

        def fake_market_call(dataset: str, day: str, **options):
            if dataset == "flows":
                raise workflow.WorkflowError("资金流不可用")
            if dataset == "big-deals":
                raise workflow.WorkflowError("大单数据不可用")
            name = names[dataset]
            return {"status": "ready", "dataset": name, "target_date": day, "checks": []}

        with mock.patch.object(workflow, "market_call", side_effect=fake_market_call):
            with self.assertRaisesRegex(workflow.WorkflowError, "资金流不可用"):
                workflow.capture("20260812", "noon")
        manifest = json.loads((self.data / "20260812" / "capture_noon.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "blocked")
        self.assertFalse((self.data / "20260812" / "market_snapshot_noon.json").exists())
        self.assertFalse((self.data / "20260812" / "index_history.json").exists())


class TemplateTests(unittest.TestCase):
    def test_three_templates_match_workflow(self) -> None:
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        self.assertEqual(
            {path.name for path in template_dir.glob("*.md")},
            {"pre_market.md", "intraday_review.md", "post_market.md"},
        )

    def test_post_template_has_six_disjoint_lifecycle_stages(self) -> None:
        text = (Path(__file__).resolve().parents[1] / "templates" / "post_market.md").read_text(encoding="utf-8")
        for stage in ("观察", "启动", "扩散", "高潮", "分歧", "退潮"):
            self.assertIn(f"| {stage} |", text)


if __name__ == "__main__":
    unittest.main()
