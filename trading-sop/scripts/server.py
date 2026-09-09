#!/usr/bin/env python3
"""Lightweight HTTP server for MMTickerLab reports and interactive K-line dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from market_reader import calculate_indicators, get_kline_bars, render_svg_chart
from report_indexer import get_report_detail, scan_reports

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = REPO_ROOT / "report"
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class DashboardHandler(BaseHTTPRequestHandler):
    report_dir: Path = DEFAULT_REPORT_DIR

    def log_message(self, format: str, *args: object) -> None:
        # Standard silent or compact logging
        pass

    def send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message, "status": "error"}, status=status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. API: List reports
        if path == "/api/reports":
            category = query.get("category", [None])[0]
            reports = scan_reports(self.report_dir)
            if category and category != "all":
                reports = [r for r in reports if r.get("category") == category]
            self.send_json(reports)
            return

        # 2. API: Get report detail
        if path == "/api/report":
            rel_path = query.get("path", [None])[0]
            if not rel_path:
                self.send_error_json("Missing 'path' parameter", 400)
                return
            detail = get_report_detail(self.report_dir, rel_path)
            if not detail:
                self.send_error_json(f"Report not found: {rel_path}", 404)
                return
            self.send_json(detail)
            return

        # 3. API: Query K-line and indicators
        if path == "/api/kline":
            code = query.get("code", [None])[0]
            if not code:
                self.send_error_json("Missing 'code' parameter", 400)
                return
            try:
                count = int(query.get("count", ["120"])[0])
            except ValueError:
                count = 120
            period = query.get("period", ["daily"])[0]

            bars = get_kline_bars(code, period=period, count=count)
            data = calculate_indicators(bars)
            self.send_json(data)
            return

        # 4. API: Render SVG Chart
        if path == "/api/chart/svg":
            code = query.get("code", [None])[0]
            if not code:
                self.send_error_json("Missing 'code' parameter", 400)
                return
            try:
                count = int(query.get("count", ["120"])[0])
            except ValueError:
                count = 120
            bars = get_kline_bars(code, count=count)
            title = f"{code} A-Share K-Line & Technical Indicators"
            svg_content = render_svg_chart(bars, title=title).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(svg_content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(svg_content)
            return

        # 5. Static files & Web Dashboard
        if path == "/" or path == "/index.html":
            index_file = WEB_DIR / "index.html"
            if not index_file.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Web UI not found")
                return
            content = index_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # Serve static assets if requested
        file_target = (WEB_DIR / path.lstrip("/")).resolve()
        if file_target.is_file() and file_target.is_relative_to(WEB_DIR):
            content_type, _ = mimetypes.guess_type(str(file_target))
            content = file_target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "File Not Found")


def run_server(port: int = 8088, host: str = "127.0.0.1", report_dir: Path | str | None = None) -> None:
    r_dir = Path(report_dir).resolve() if report_dir else DEFAULT_REPORT_DIR
    r_dir.mkdir(parents=True, exist_ok=True)
    DashboardHandler.report_dir = r_dir

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    print(f"🚀 MMTickerLab Dashboard Server running at: http://{host}:{port}")
    print(f"📁 Watching reports directory: {r_dir}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MMTickerLab Dashboard HTTP Server")
    parser.add_argument("--port", type=int, default=8088, help="Port to listen on (default: 8088)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--report-dir", help="Directory containing reports (default: report/)")
    args = parser.parse_args()

    run_server(port=args.port, host=args.host, report_dir=args.report_dir)
