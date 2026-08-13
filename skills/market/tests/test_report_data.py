from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("strict_market_data", SCRIPT_DIR / "market_data.py")
report_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(report_data)


class SessionGateTests(unittest.TestCase):
    def test_close_requires_target_day_and_after_close(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        allowed, _ = report_data._session_allowed(
            date(2026, 8, 12), "close", datetime(2026, 8, 12, 15, 5, tzinfo=tz)
        )
        self.assertTrue(allowed)
        allowed, _ = report_data._session_allowed(
            date(2026, 8, 11), "close", datetime(2026, 8, 12, 23, 0, tzinfo=tz)
        )
        self.assertFalse(allowed)

    def test_noon_rejects_afternoon(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        allowed, _ = report_data._session_allowed(
            date(2026, 8, 12), "noon", datetime(2026, 8, 12, 13, 0, tzinfo=tz)
        )
        self.assertFalse(allowed)


class OverseasFinalizationTests(unittest.TestCase):
    def test_unfinished_us_row_is_discarded(self) -> None:
        frame = pd.DataFrame([
            {"日期": "2026-08-10", "最新价": 100.0},
            {"日期": "2026-08-11", "最新价": 102.0},
            {"日期": "2026-08-12", "最新价": 105.0},
        ])
        now = datetime(2026, 8, 12, 11, 0, tzinfo=ZoneInfo("America/New_York"))
        result = report_data._final_global_row(frame, now)
        self.assertEqual(result["row"]["日期"], "2026-08-11T00:00:00")
        self.assertTrue(result["discarded_unfinished_latest"])
        self.assertAlmostEqual(result["change_pct"], 2.0)


if __name__ == "__main__":
    unittest.main()
