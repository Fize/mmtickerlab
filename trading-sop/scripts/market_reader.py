#!/usr/bin/env python3
"""Market data reader and technical indicator calculation engine."""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path
from typing import Any


def get_default_db_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "market" / "data" / "market_raw.db"


def get_kline_bars(
    security_code: str,
    period: str = "daily",
    adjust: str = "qfq",
    count: int = 120,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Query raw candlestick bars from market_raw.db SQLite database."""
    path = Path(db_path) if db_path else get_default_db_path()
    if not path.exists():
        return []

    code = str(security_code).strip()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # First try exact match with adjust
        cursor = conn.execute(
            """
            SELECT timestamp, open, high, low, close, volume, turnover_yuan,
                   amplitude_pct, change_pct, turnover_rate_pct
            FROM bars
            WHERE security_code = ? AND period = ? AND adjust = ?
            ORDER BY timestamp ASC
            """,
            (code, period, adjust),
        )
        rows = [dict(row) for row in cursor.fetchall()]

        # If not found, try without adjust constraint
        if not rows:
            cursor = conn.execute(
                """
                SELECT timestamp, open, high, low, close, volume, turnover_yuan,
                       amplitude_pct, change_pct, turnover_rate_pct
                FROM bars
                WHERE security_code = ? AND period = ?
                ORDER BY timestamp ASC
                """,
                (code, period),
            )
            rows = [dict(row) for row in cursor.fetchall()]

        if count and len(rows) > count:
            rows = rows[-count:]

        return rows
    finally:
        conn.close()


def moving_average(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            result.append(None)
        else:
            window = values[index + 1 - period : index + 1]
            result.append(round(sum(window) / period, 2))
    return result


def exponential_average(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def calculate_indicators(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute SMA5/10/20/60, Volume MA5, MACD, and RSI6 for OHLCV bars."""
    if not bars:
        return []

    closes = [float(b.get("close") or 0.0) for b in bars]
    volumes = [float(b.get("volume") or 0.0) for b in bars]

    # Moving Averages
    sma5 = moving_average(closes, 5)
    sma10 = moving_average(closes, 10)
    sma20 = moving_average(closes, 20)
    sma60 = moving_average(closes, 60)
    vol_ma5 = moving_average(volumes, 5)

    # MACD (12, 26, 9)
    ema12 = exponential_average(closes, 12)
    ema26 = exponential_average(closes, 26)
    dif = [round(fast - slow, 3) for fast, slow in zip(ema12, ema26)]
    dea = [round(val, 3) for val in exponential_average(dif, 9)]
    macd = [round(2 * (d - e), 3) for d, e in zip(dif, dea)]

    # RSI 6
    gains = [0.0]
    losses = [0.0]
    for prev, curr in zip(closes, closes[1:]):
        chg = curr - prev
        gains.append(max(chg, 0.0))
        losses.append(max(-chg, 0.0))
    avg_gain = exponential_average(gains, 6)
    avg_loss = exponential_average(losses, 6)
    rsi6 = []
    for g, l in zip(avg_gain, avg_loss):
        if l == 0:
            rsi6.append(100.0)
        else:
            rs = g / l
            rsi6.append(round(100.0 - (100.0 / (1.0 + rs)), 1))

    indicators = []
    for idx, b in enumerate(bars):
        date_str = str(b.get("timestamp", ""))[:10]
        indicators.append(
            {
                "date": date_str,
                "timestamp": b.get("timestamp", ""),
                "open": b.get("open"),
                "high": b.get("high"),
                "low": b.get("low"),
                "close": b.get("close"),
                "volume": b.get("volume"),
                "turnover": b.get("turnover_yuan"),
                "change_pct": b.get("change_pct"),
                "turnover_rate": b.get("turnover_rate_pct"),
                "sma5": sma5[idx],
                "sma10": sma10[idx],
                "sma20": sma20[idx],
                "sma60": sma60[idx],
                "vol_ma5": vol_ma5[idx],
                "dif": dif[idx],
                "dea": dea[idx],
                "macd": macd[idx],
                "rsi6": rsi6[idx],
            }
        )

    return indicators


def render_svg_chart(bars: list[dict[str, Any]], title: str = "A-Share Candlestick Chart") -> str:
    """Render an SVG chart containing Candlesticks, SMA5/10/20, Volume, and MACD."""
    if not bars:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="#0f172a"/><text x="400" y="200" fill="#94a3b8" text-anchor="middle" font-size="16">No K-Line Data Available</text></svg>'

    data = calculate_indicators(bars)
    width = 1000
    height = 680
    left = 60
    right = 30
    plot_width = width - left - right

    price_top, price_bottom = 50.0, 360.0
    vol_top, vol_bottom = 390.0, 480.0
    macd_top, macd_bottom = 510.0, 630.0

    highs = [float(d["high"] or 0) for d in data if d["high"] is not None]
    lows = [float(d["low"] or 0) for d in data if d["low"] is not None]
    price_high = max(highs) if highs else 1.0
    price_low = min(lows) if lows else 0.0
    padding = max((price_high - price_low) * 0.05, 0.01)
    price_high += padding
    price_low = max(0.01, price_low - padding)

    volumes = [float(d["volume"] or 0) for d in data]
    vol_max = max(volumes) if volumes else 1.0

    dif_values = [abs(float(d["dif"] or 0)) for d in data]
    dea_values = [abs(float(d["dea"] or 0)) for d in data]
    macd_values = [abs(float(d["macd"] or 0)) for d in data]
    macd_max = max(dif_values + dea_values + macd_values + [0.1])

    step = plot_width / max(len(data), 1)
    candle_w = max(1.5, min(7.0, step * 0.65))

    def scale_y(val: float, low: float, high: float, top: float, bottom: float) -> float:
        if high == low:
            return (top + bottom) / 2
        return bottom - (val - low) * (bottom - top) / (high - low)

    elements: list[str] = [
        f'<rect width="{width}" height="{height}" fill="#0f172a"/>',
        f'<text x="{left}" y="32" fill="#f8fafc" font-size="18" font-weight="bold" font-family="system-ui, -apple-system, sans-serif">{html.escape(title)}</text>',
        # Horizontal grids
        f'<line x1="{left}" y1="{price_top}" x2="{width - right}" y2="{price_top}" stroke="#334155" stroke-dasharray="2 2"/>',
        f'<line x1="{left}" y1="{price_bottom}" x2="{width - right}" y2="{price_bottom}" stroke="#334155"/>',
        f'<line x1="{left}" y1="{vol_bottom}" x2="{width - right}" y2="{vol_bottom}" stroke="#334155"/>',
        f'<line x1="{left}" y1="{macd_bottom}" x2="{width - right}" y2="{macd_bottom}" stroke="#334155"/>',
        # Labels
        f'<text x="{left - 8}" y="{price_top + 12}" fill="#94a3b8" font-size="11" text-anchor="end">{price_high:.2f}</text>',
        f'<text x="{left - 8}" y="{price_bottom}" fill="#94a3b8" font-size="11" text-anchor="end">{price_low:.2f}</text>',
        f'<text x="12" y="{vol_top + 14}" fill="#64748b" font-size="11">VOL</text>',
        f'<text x="12" y="{macd_top + 14}" fill="#64748b" font-size="11">MACD</text>',
    ]

    sma5_pts: list[str] = []
    sma10_pts: list[str] = []
    sma20_pts: list[str] = []

    for i, d in enumerate(data):
        x = left + (i + 0.5) * step
        o, h, l, c = float(d["open"]), float(d["high"]), float(d["low"]), float(d["close"])
        is_up = c >= o
        color = "#ef4444" if is_up else "#10b981"

        yh = scale_y(h, price_low, price_high, price_top, price_bottom)
        yl = scale_y(l, price_low, price_high, price_top, price_bottom)
        yo = scale_y(o, price_low, price_high, price_top, price_bottom)
        yc = scale_y(c, price_low, price_high, price_top, price_bottom)
        body_top = min(yo, yc)
        body_h = max(abs(yc - yo), 1.0)

        # Candle wick & body
        elements.append(f'<line x1="{x:.1f}" y1="{yh:.1f}" x2="{x:.1f}" y2="{yl:.1f}" stroke="{color}" stroke-width="1"/>')
        elements.append(f'<rect x="{x - candle_w/2:.1f}" y="{body_top:.1f}" width="{candle_w:.1f}" height="{body_h:.1f}" fill="{color}"/>')

        # Volume bar
        v = float(d["volume"])
        vy = scale_y(v, 0, vol_max, vol_top, vol_bottom)
        elements.append(f'<rect x="{x - candle_w/2:.1f}" y="{vy:.1f}" width="{candle_w:.1f}" height="{vol_bottom - vy:.1f}" fill="{color}" opacity="0.75"/>')

        # Moving Averages
        if d["sma5"]:
            sma5_pts.append(f"{x:.1f},{scale_y(d['sma5'], price_low, price_high, price_top, price_bottom):.1f}")
        if d["sma10"]:
            sma10_pts.append(f"{x:.1f},{scale_y(d['sma10'], price_low, price_high, price_top, price_bottom):.1f}")
        if d["sma20"]:
            sma20_pts.append(f"{x:.1f},{scale_y(d['sma20'], price_low, price_high, price_top, price_bottom):.1f}")

        # MACD
        m_bar = float(d["macd"])
        zero_y = scale_y(0.0, -macd_max, macd_max, macd_top, macd_bottom)
        m_color = "#ef4444" if m_bar >= 0 else "#10b981"
        my = scale_y(m_bar, -macd_max, macd_max, macd_top, macd_bottom)
        elements.append(f'<rect x="{x - candle_w/3:.1f}" y="{min(my, zero_y):.1f}" width="{candle_w*2/3:.1f}" height="{max(abs(my - zero_y), 1.0):.1f}" fill="{m_color}"/>')

    if sma5_pts:
        elements.append(f'<polyline points="{" ".join(sma5_pts)}" fill="none" stroke="#fbbf24" stroke-width="1.2"/>')
    if sma10_pts:
        elements.append(f'<polyline points="{" ".join(sma10_pts)}" fill="none" stroke="#38bdf8" stroke-width="1.2"/>')
    if sma20_pts:
        elements.append(f'<polyline points="{" ".join(sma20_pts)}" fill="none" stroke="#c084fc" stroke-width="1.2"/>')

    # Legend
    legend = (
        f'<text x="{width - right}" y="30" text-anchor="end" font-size="11" font-family="sans-serif">'
        f'<tspan fill="#fbbf24">MA5  </tspan>'
        f'<tspan fill="#38bdf8">MA10  </tspan>'
        f'<tspan fill="#c084fc">MA20  </tspan>'
        f'</text>'
    )
    elements.append(legend)

    # Date labels at bottom
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        idx = min(round((len(data) - 1) * frac), len(data) - 1)
        x = left + (idx + 0.5) * step
        d_str = html.escape(data[idx]["date"])
        elements.append(f'<text x="{x:.1f}" y="655" fill="#64748b" font-size="10" text-anchor="middle" font-family="sans-serif">{d_str}</text>')

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">' + "".join(elements) + "</svg>\n"


if __name__ == "__main__":
    import sys
    test_code = sys.argv[1] if len(sys.argv) > 1 else "600176"
    bars = get_kline_bars(test_code, count=60)
    print(f"Loaded {len(bars)} bars for {test_code}")
    if bars:
        ind = calculate_indicators(bars)
        print("Last bar:", ind[-1])
