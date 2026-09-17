from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "derived_metrics.py"
SPEC = importlib.util.spec_from_file_location("plan_review_derived_metrics", MODULE_PATH)
metrics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(metrics)


class FearGreedTests(unittest.TestCase):
    def test_fear_greed_score_is_weighted_and_exposes_components(self) -> None:
        result = metrics.fear_greed_index({
            "volume": 41.5,
            "breadth": 50.0,
            "rsi": 50.0,
            "momentum": 44.4,
            "volatility": 75.5,
        })
        self.assertEqual(result["version"], "fg-v1")
        self.assertAlmostEqual(result["score"], 52.4, places=1)
        self.assertEqual(set(result["components"]), {"volume", "breadth", "rsi", "momentum", "volatility"})

    def test_fear_greed_from_market_data_uses_validated_snapshots(self) -> None:
        snapshot = {"data": {"metrics": {"total_turnover_yuan": 120, "up_count": 60, "down_count": 40}}}
        previous = {"data": {"metrics": {"total_turnover_yuan": 100}}}
        indices = {"data": {"indices": {"000001": {"rows": [
            {"close": 100 + value} for value in (0, 1, 2, 1, 3, 4, 5, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)
        ]}}}}
        result = metrics.fear_greed_from_market_data(snapshot, previous, indices)
        self.assertEqual(result["version"], "fg-v1")
        self.assertIn("components", result)

    def test_commodity_rows_require_timestamped_status(self) -> None:
        rows = [{
            "category": "贵金属", "instrument": "黄金主连", "price": 800,
            "change_pct": 1.2, "change_5d": 2.3, "unit": "元/克",
            "as_of": "2026-09-17T15:00:00+08:00", "status": "final",
        }]
        self.assertEqual(metrics.validate_commodity_rows(rows), rows)


if __name__ == "__main__":
    unittest.main()
