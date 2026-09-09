from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure scripts dir is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import market_reader
import report_indexer
import server


class ReportIndexerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.report_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_frontmatter(self) -> None:
        content = "---\ntitle: \"测试标题\"\ndate: \"2026-09-09\"\ncode: \"600519\"\nactive: true\n---\n\n# 正文内容"
        fm, body = report_indexer.parse_frontmatter(content)
        self.assertEqual(fm.get("title"), "测试标题")
        self.assertEqual(fm.get("date"), "2026-09-09")
        self.assertEqual(fm.get("code"), "600519")
        self.assertTrue(fm.get("active"))
        self.assertIn("# 正文内容", body)

    def test_infer_metadata_without_frontmatter(self) -> None:
        body = "# 2026-09-09 盘前计划\n\n> bundle_id: test\n\n基准日期：2026-09-09\n\nVETO: PASSED\n"
        meta = report_indexer.infer_metadata_from_text("20260909_盘前计划.md", body, "daily")
        self.assertEqual(meta.get("title"), "2026-09-09 盘前计划")
        self.assertEqual(meta.get("date"), "2026-09-09")
        self.assertEqual(meta.get("category"), "daily")
        self.assertEqual(meta.get("veto_status"), "PASSED")

    def test_scan_and_detail(self) -> None:
        sub = self.report_dir / "ticker"
        sub.mkdir(parents=True)
        sample = sub / "20260909_600176_中国巨石_投研决策总报.md"
        sample.write_text(
            "---\ntitle: 中国巨石投研总报\ndate: 20260909\ncode: '600176'\nrating: '🟢 强烈推荐买入'\nveto_status: PASSED\n---\n\n# 核心逻辑\n\n玻纤龙头",
            encoding="utf-8",
        )

        reports = report_indexer.scan_reports(self.report_dir)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["code"], "600176")
        self.assertEqual(reports[0]["date"], "2026-09-09")
        self.assertEqual(reports[0]["category"], "ticker")

        detail = report_indexer.get_report_detail(self.report_dir, reports[0]["relative_path"])
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["metadata"]["code"], "600176")
        self.assertIn("玻纤龙头", detail["body_markdown"])


class MarketReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db")
        conn = sqlite3.connect(self.temp_db.name)
        conn.execute(
            """
            CREATE TABLE bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                security_code TEXT NOT NULL,
                period TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                turnover_yuan REAL,
                amplitude_pct REAL,
                change_pct REAL,
                turnover_rate_pct REAL,
                adjust TEXT NOT NULL,
                source TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );
            """
        )
        # Insert 10 sample bars
        for i in range(10):
            conn.execute(
                """
                INSERT INTO bars (security_code, period, timestamp, open, high, low, close, volume, turnover_yuan, adjust, source, observed_at, content_hash)
                VALUES ('600000', 'daily', ?, ?, ?, ?, ?, 10000, 100000, 'qfq', 'test', 'now', ?)
                """,
                (f"2026-08-{10+i:02d}T00:00:00+08:00", 10.0 + i * 0.1, 10.5 + i * 0.1, 9.8 + i * 0.1, 10.2 + i * 0.1, f"hash{i}"),
            )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.temp_db.close()

    def test_get_bars_and_indicators(self) -> None:
        bars = market_reader.get_kline_bars("600000", period="daily", db_path=self.temp_db.name)
        self.assertEqual(len(bars), 10)
        ind = market_reader.calculate_indicators(bars)
        self.assertEqual(len(ind), 10)
        # Bar 5 should have SMA5
        self.assertIsNotNone(ind[4]["sma5"])
        # Indicators keys exist
        self.assertIn("macd", ind[-1])
        self.assertIn("rsi6", ind[-1])

    def test_render_svg_chart(self) -> None:
        bars = market_reader.get_kline_bars("600000", period="daily", db_path=self.temp_db.name)
        svg = market_reader.render_svg_chart(bars, title="Test Chart")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("Test Chart", svg)
        self.assertIn("</svg>", svg)


class ServerEndpointsTests(unittest.TestCase):
    def test_server_handler_routes(self) -> None:
        # Verify server handler methods without starting background daemon
        handler = server.DashboardHandler
        self.assertTrue(hasattr(handler, "do_GET"))
        self.assertTrue(hasattr(handler, "send_json"))


if __name__ == "__main__":
    unittest.main()

import threading
import urllib.request


class LiveServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.port = 18099
        cls.host = "127.0.0.1"
        cls.report_dir = REPO_ROOT = Path(__file__).resolve().parents[2] / "report"
        server.DashboardHandler.report_dir = cls.report_dir
        cls.httpd = server.ThreadingHTTPServer((cls.host, cls.port), server.DashboardHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_get_index(self) -> None:
        url = f"http://{self.host}:{self.port}/"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            body = resp.read().decode("utf-8")
            self.assertIn("MMTickerLab", body)
            self.assertIn("投研看板", body)

    def test_api_reports(self) -> None:
        url = f"http://{self.host}:{self.port}/api/reports"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 1)

    def test_api_kline_and_svg(self) -> None:
        url = f"http://{self.host}:{self.port}/api/kline?code=600176&count=10"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIsInstance(data, list)

        url_svg = f"http://{self.host}:{self.port}/api/chart/svg?code=600176&count=20"
        with urllib.request.urlopen(url_svg) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("image/svg+xml", resp.headers.get("Content-Type", ""))
            svg = resp.read().decode("utf-8")
            self.assertTrue(svg.startswith("<svg"))
