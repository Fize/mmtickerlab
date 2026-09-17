import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS = (
    "market",
    "market-intel",
    "plan-review",
    "risk-guard",
    "industry-research",
    "asset-analysis",
    "first-board-overnight",
    "ticker-pipeline",
    "trading-sop",
)


class SkillContractTests(unittest.TestCase):
    def test_each_skill_declares_standalone_data_contract(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                text = (ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^name:\s*\S+")
                self.assertRegex(text, r"(?m)^description:\s*\S+")
                self.assertIn("独立", text)
                self.assertIn("补充", text)
                self.assertRegex(text, r"核验|校验|验证")

    def test_trading_sop_preserves_fail_closed_rule(self):
        text = (ROOT / "trading-sop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"仍不可用.*停止|停止.*仍不可用")

    def test_daily_review_references_optional_reports(self):
        text = (ROOT / "trading-sop" / "references" / "sop-a-daily.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("午间复盘可以独立运行", text)
        self.assertIn("盘后复盘可以独立运行", text)
        self.assertNotIn("必须存在同日盘前计划报告", text)

    def test_first_board_uses_structured_snapshot_gate(self):
        text = (ROOT / "trading-sop" / "references" / "sop-c-firstboard.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("结构化快照", text)
        self.assertIn("报告是可选的", text)
        self.assertIn("BLOCKED", text)


if __name__ == "__main__":
    unittest.main()
