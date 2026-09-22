from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import urllib.request
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import providers.yfinance_provider as yf_provider


class YfinanceSymbolTests(unittest.TestCase):
    def test_to_yf_symbol_hk(self) -> None:
        self.assertEqual(yf_provider.to_yf_symbol("00700", "hk"), "0700.HK")
        self.assertEqual(yf_provider.to_yf_symbol("0700", "hk"), "0700.HK")
        self.assertEqual(yf_provider.to_yf_symbol("00700.HK"), "0700.HK")
        self.assertEqual(yf_provider.to_yf_symbol("9988", "hk"), "9988.HK")

    def test_to_yf_symbol_us(self) -> None:
        self.assertEqual(yf_provider.to_yf_symbol("AAPL", "us"), "AAPL")
        self.assertEqual(yf_provider.to_yf_symbol("AAPL.US"), "AAPL")
        self.assertEqual(yf_provider.to_yf_symbol("US.AAPL"), "AAPL")
        self.assertEqual(yf_provider.to_yf_symbol("BRK.B", "us"), "BRK-B")


class YfinanceQuoteTests(unittest.TestCase):
    def test_sina_hk_quote_parsing(self) -> None:
        mock_response_text = (
            'var hq_str_rt_hk00700="TENCENT,腾讯控股,480.000,475.000,485.000,472.000,482.000,'
            '7.000,1.474,481.800,482.000,2890000000.000,6000000,0.000,0.000,500.000,300.000,'
            '2026/09/21,11:30:00,00000";'
        )
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = mock_response_text.encode("gbk")
        mock_resp.__enter__.return_value = mock_resp

        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            quote = yf_provider._fetch_sina_hk_quote("00700")

        self.assertEqual(quote["name"], "腾讯控股")
        self.assertEqual(quote["last"], 482.0)
        self.assertEqual(quote["pre_close"], 475.0)
        self.assertEqual(quote["change"], 7.0)
        self.assertEqual(quote["change_pct"], 1.474)
        self.assertEqual(quote["quote_timestamp"], "2026-09-21 11:30:00")
        self.assertEqual(quote["source"], "Sina.rt_hk")

    def test_sina_us_quote_parsing(self) -> None:
        mock_response_text = (
            'var hq_str_gb_aapl="苹果,230.5000,1.25,2026-09-18 16:00:00,2.8500,228.0000,'
            '231.0000,227.5000,240.0000,165.0000,55000000,25000000";'
        )
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = mock_response_text.encode("gbk")
        mock_resp.__enter__.return_value = mock_resp

        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            quote = yf_provider._fetch_sina_us_quote("AAPL")

        self.assertEqual(quote["name"], "苹果")
        self.assertEqual(quote["last"], 230.5)
        self.assertEqual(quote["change"], 2.85)
        self.assertEqual(quote["change_pct"], 1.25)
        self.assertEqual(quote["pre_close"], 227.65)
        self.assertEqual(quote["quote_timestamp"], "2026-09-18 16:00:00")
        self.assertEqual(quote["source"], "Sina.gb_us")

    def test_quote_fallback_when_yfinance_fails(self) -> None:
        with mock.patch.object(yf_provider, "yf", None):
            with mock.patch.object(yf_provider, "_fetch_sina_hk_quote") as mock_sina:
                mock_sina.return_value = {"name": "腾讯", "last": 480.0, "source": "Sina.rt_hk"}
                res = yf_provider.get_stock_quote("00700", "hk")
                self.assertEqual(res["last"], 480.0)
                self.assertEqual(res["source"], "Sina.rt_hk")


class YfinanceGlobalIndexTests(unittest.TestCase):
    def test_global_index_history_sina_fallback(self) -> None:
        sample_bars = [
            {"d": "2026-09-17", "o": "51800.0", "h": "51900.0", "l": "51600.0", "c": "51778.0", "v": "400000"},
            {"d": "2026-09-18", "o": "51826.0", "h": "51826.0", "l": "51497.0", "c": "51682.6", "v": "800000"},
        ]
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps(sample_bars).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with mock.patch.object(yf_provider, "yf", None):
            with mock.patch("urllib.request.urlopen", return_value=mock_resp):
                df = yf_provider.get_global_index_history("道琼斯")

        self.assertIn("日期", df.columns)
        self.assertIn("最新价", df.columns)
        self.assertIn("涨跌额", df.columns)
        self.assertIn("涨跌幅", df.columns)
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(df.iloc[-1]["最新价"], 51682.6)


if __name__ == "__main__":
    unittest.main()

