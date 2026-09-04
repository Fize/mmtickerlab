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


class MultiMarketSymbolTests(unittest.TestCase):
    def test_detect_market(self) -> None:
        self.assertEqual(report_data.detect_market("600519"), "cn")
        self.assertEqual(report_data.detect_market("SH600519"), "cn")
        self.assertEqual(report_data.detect_market("000001.SZ"), "cn")
        self.assertEqual(report_data.detect_market("832000"), "cn")
        self.assertEqual(report_data.detect_market("00700"), "hk")
        self.assertEqual(report_data.detect_market("00700.HK"), "hk")
        self.assertEqual(report_data.detect_market("HK00700"), "hk")
        self.assertEqual(report_data.detect_market("09988"), "hk")
        self.assertEqual(report_data.detect_market("AAPL"), "us")
        self.assertEqual(report_data.detect_market("TSLA.US"), "us")
        self.assertEqual(report_data.detect_market("US.NVDA"), "us")
        self.assertEqual(report_data.detect_market("BRK.B"), "us")

    def test_stock_code_normalization(self) -> None:
        self.assertEqual(report_data.stock_code("sh600519"), "600519")
        self.assertEqual(report_data.stock_code("000001.SZ"), "000001")
        self.assertEqual(report_data.stock_code("00700.hk"), "00700")
        self.assertEqual(report_data.stock_code("hk00700"), "00700")
        self.assertEqual(report_data.stock_code("09988"), "09988")
        self.assertEqual(report_data.stock_code("aapl"), "AAPL")
        self.assertEqual(report_data.stock_code("tsla.us"), "TSLA")
        self.assertEqual(report_data.stock_code("BRK.B"), "BRK.B")
        with self.assertRaises(report_data.DataError):
            report_data.stock_code("123")
        with self.assertRaises(report_data.DataError):
            report_data.stock_code("TOO_LONG_SYMBOL")

    def test_exchange_for(self) -> None:
        self.assertEqual(report_data.exchange_for("600519"), "sh")
        self.assertEqual(report_data.exchange_for("000001"), "sz")
        self.assertEqual(report_data.exchange_for("832000"), "bj")
        self.assertEqual(report_data.exchange_for("00700"), "hk")
        self.assertEqual(report_data.exchange_for("AAPL"), "us")


class IwencaiQueryGenerationTests(unittest.TestCase):
    def test_hk_and_us_query_generation(self) -> None:
        from providers.iwencai import _query
        # HK Quote
        q_hk, _ = _query("stock_quote", (), {"symbol": "00700", "market": "hk"})
        self.assertIn("港股 股票代码=00700 实时行情", q_hk)

        # US Quote
        q_us, _ = _query("stock_quote", (), {"symbol": "AAPL", "market": "us"})
        self.assertIn("美股 股票代码=AAPL 实时行情", q_us)

        # A-share Quote
        q_cn, _ = _query("stock_quote", (), {"symbol": "600519", "market": "cn"})
        self.assertIn("A股 股票代码=600519 实时行情", q_cn)

        # HK K-line
        q_hk_k, _ = _query("stock_zh_a_hist", (), {"symbol": "00700", "start_date": "20260101", "end_date": "20260110", "market": "hk"})
        self.assertIn("港股 股票代码=00700 日期在", q_hk_k)

        # US K-line
        q_us_k, _ = _query("stock_zh_a_hist", (), {"symbol": "AAPL", "start_date": "20260101", "end_date": "20260110", "market": "us"})
        self.assertIn("美股 股票代码=AAPL 日期在", q_us_k)


class OverseasFallbackProhibitionTests(unittest.TestCase):
    def test_overseas_quote_raises_without_key_and_never_falls_back(self) -> None:
        import os
        old_key = os.environ.pop("IWENCAI_API_KEY", None)
        try:
            with self.assertRaises(report_data.DataError) as ctx:
                report_data.run_with_provider("quote", lambda: None, target_code="00700")
            self.assertIn("不支持通过 AKShare 兜底", str(ctx.exception))

            with self.assertRaises(report_data.DataError) as ctx:
                report_data.run_with_provider("quote", lambda: None, target_code="AAPL")
            self.assertIn("不支持通过 AKShare 兜底", str(ctx.exception))
        finally:
            if old_key is not None:
                os.environ["IWENCAI_API_KEY"] = old_key

    def test_overseas_ashare_only_datasets_blocked(self) -> None:
        today = date(2026, 8, 12)
        with self.assertRaises(report_data.DataError) as ctx:
            report_data.chip_dataset(today, "00700", 10)
        self.assertIn("筹码分布数据集仅支持 A 股标的", str(ctx.exception))

        with self.assertRaises(report_data.DataError) as ctx:
            report_data.financial_dataset(today, "AAPL", "income", 4)
        self.assertIn("财务报表数据集目前仅支持 A 股标的", str(ctx.exception))

        with self.assertRaises(report_data.DataError) as ctx:
            report_data.news_dataset(today, "AAPL", 10)
        self.assertIn("个股新闻数据集目前仅支持 A 股标的", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
