#!/usr/bin/env python3
"""Render an auditable SVG chart from market skill JSON outputs."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


WIDTH = 1200
HEIGHT = 900
LEFT = 72
RIGHT = 28
PLOT_WIDTH = WIDTH - LEFT - RIGHT


def load_document(path: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("status") != "ready":
        raise ValueError(f"Input is not ready: {path}")
    return document


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def moving_average(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            result.append(None)
        else:
            window = values[index + 1 - period:index + 1]
            result.append(sum(window) / period)
    return result


def exponential_average(values: list[float], period: int) -> list[float]:
    alpha = 2.0 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def calculated_indicators(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closes = [numeric(row.get("close")) for row in rows]
    if any(value is None for value in closes):
        raise ValueError("K-line input has invalid close values")
    values = [float(value) for value in closes if value is not None]
    ema12 = exponential_average(values, 12)
    ema26 = exponential_average(values, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26)]
    dea = exponential_average(dif, 9)
    macd = [2 * (d - e) for d, e in zip(dif, dea)]

    gains = [0.0]
    losses = [0.0]
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = exponential_average(gains, 11)
    avg_loss = exponential_average(losses, 11)
    rsi6 = [100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
            for gain, loss in zip(avg_gain, avg_loss)]

    sma5 = moving_average(values, 5)
    sma10 = moving_average(values, 10)
    sma20 = moving_average(values, 20)
    return [{
        "Date": str(row.get("timestamp", ""))[:10],
        "SMA_5": sma5[index],
        "SMA_10": sma10[index],
        "SMA_20": sma20[index],
        "DIF": dif[index],
        "DEA": dea[index],
        "MACD": macd[index],
        "RSI_6": rsi6[index],
    } for index, row in enumerate(rows)]


def scale(value: float, low: float, high: float, top: float, bottom: float) -> float:
    if high == low:
        return (top + bottom) / 2
    return bottom - (value - low) * (bottom - top) / (high - low)


def polyline(points: list[tuple[float, float]], color: str, width: float = 1.5) -> str:
    if len(points) < 2:
        return ""
    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}"/>'


def line_series(
    rows: list[dict[str, Any]],
    field: str,
    xs: dict[str, float],
    low: float,
    high: float,
    top: float,
    bottom: float,
    color: str,
) -> str:
    points: list[tuple[float, float]] = []
    for row in rows:
        key = str(row.get("Date", ""))[:10]
        value = numeric(row.get(field))
        if key in xs and value is not None:
            points.append((xs[key], scale(value, low, high, top, bottom)))
    return polyline(points, color)


def render(kline: dict[str, Any], technical: dict[str, Any] | None, title: str) -> str:
    rows = kline.get("data", {}).get("rows", [])
    if not rows:
        raise ValueError("K-line input has no rows")
    indicators = technical.get("data", {}).get("rows", []) if technical else calculated_indicators(rows)

    price_top, price_bottom = 70.0, 500.0
    volume_top, volume_bottom = 535.0, 665.0
    macd_top, macd_bottom = 700.0, 790.0
    rsi_top, rsi_bottom = 820.0, 875.0
    step = PLOT_WIDTH / max(len(rows), 1)
    candle_width = max(2.0, min(8.0, step * 0.62))

    highs = [numeric(row.get("high")) for row in rows]
    lows = [numeric(row.get("low")) for row in rows]
    valid_highs = [value for value in highs if value is not None]
    valid_lows = [value for value in lows if value is not None]
    if not valid_highs or not valid_lows:
        raise ValueError("K-line input has no valid price range")
    price_low, price_high = min(valid_lows), max(valid_highs)
    padding = max((price_high - price_low) * 0.05, 0.01)
    price_low -= padding
    price_high += padding

    volumes = [numeric(row.get("volume")) or 0.0 for row in rows]
    volume_high = max(volumes) or 1.0
    xs: dict[str, float] = {}
    elements: list[str] = []

    elements.append(f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#0f172a"/>')
    elements.append(f'<text x="{LEFT}" y="34" fill="#f8fafc" font-size="22" font-family="sans-serif">{html.escape(title)}</text>')

    for index, row in enumerate(rows):
        x = LEFT + (index + 0.5) * step
        timestamp = str(row.get("timestamp", ""))
        xs[timestamp[:10]] = x
        open_value = numeric(row.get("open"))
        high_value = numeric(row.get("high"))
        low_value = numeric(row.get("low"))
        close_value = numeric(row.get("close"))
        if None in (open_value, high_value, low_value, close_value):
            continue
        assert open_value is not None and high_value is not None
        assert low_value is not None and close_value is not None
        color = "#ef4444" if close_value >= open_value else "#22c55e"
        y_high = scale(high_value, price_low, price_high, price_top, price_bottom)
        y_low = scale(low_value, price_low, price_high, price_top, price_bottom)
        y_open = scale(open_value, price_low, price_high, price_top, price_bottom)
        y_close = scale(close_value, price_low, price_high, price_top, price_bottom)
        body_top = min(y_open, y_close)
        body_height = max(abs(y_close - y_open), 1.0)
        elements.append(f'<line x1="{x:.1f}" y1="{y_high:.1f}" x2="{x:.1f}" y2="{y_low:.1f}" stroke="{color}"/>')
        elements.append(f'<rect x="{x - candle_width / 2:.1f}" y="{body_top:.1f}" width="{candle_width:.1f}" height="{body_height:.1f}" fill="{color}"/>')

        volume = numeric(row.get("volume")) or 0.0
        volume_y = scale(volume, 0.0, volume_high, volume_top, volume_bottom)
        elements.append(f'<rect x="{x - candle_width / 2:.1f}" y="{volume_y:.1f}" width="{candle_width:.1f}" height="{volume_bottom - volume_y:.1f}" fill="{color}" opacity="0.7"/>')

    elements.append(line_series(indicators, "SMA_5", xs, price_low, price_high, price_top, price_bottom, "#facc15"))
    elements.append(line_series(indicators, "SMA_10", xs, price_low, price_high, price_top, price_bottom, "#38bdf8"))
    elements.append(line_series(indicators, "SMA_20", xs, price_low, price_high, price_top, price_bottom, "#c084fc"))

    macd_values = [numeric(row.get(field)) for row in indicators for field in ("DIF", "DEA", "MACD")]
    valid_macd = [value for value in macd_values if value is not None]
    macd_bound = max([abs(value) for value in valid_macd], default=1.0) or 1.0
    zero_y = scale(0.0, -macd_bound, macd_bound, macd_top, macd_bottom)
    elements.append(f'<line x1="{LEFT}" y1="{zero_y:.1f}" x2="{WIDTH - RIGHT}" y2="{zero_y:.1f}" stroke="#475569"/>')
    for row in indicators:
        key = str(row.get("Date", ""))[:10]
        value = numeric(row.get("MACD"))
        if key not in xs or value is None:
            continue
        x = xs[key]
        y = scale(value, -macd_bound, macd_bound, macd_top, macd_bottom)
        color = "#ef4444" if value >= 0 else "#22c55e"
        elements.append(f'<rect x="{x - candle_width / 3:.1f}" y="{min(y, zero_y):.1f}" width="{candle_width * 2 / 3:.1f}" height="{max(abs(y - zero_y), 1):.1f}" fill="{color}"/>')
    elements.append(line_series(indicators, "DIF", xs, -macd_bound, macd_bound, macd_top, macd_bottom, "#facc15"))
    elements.append(line_series(indicators, "DEA", xs, -macd_bound, macd_bound, macd_top, macd_bottom, "#38bdf8"))

    for level in (30.0, 70.0):
        y = scale(level, 0.0, 100.0, rsi_top, rsi_bottom)
        elements.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{WIDTH - RIGHT}" y2="{y:.1f}" stroke="#475569" stroke-dasharray="4 4"/>')
    elements.append(line_series(indicators, "RSI_6", xs, 0.0, 100.0, rsi_top, rsi_bottom, "#f97316"))

    for y, label in ((price_top, "Price + SMA5/10/20"), (volume_top, "Volume"), (macd_top, "MACD"), (rsi_top, "RSI6")):
        elements.append(f'<text x="8" y="{y + 14:.1f}" fill="#94a3b8" font-size="12" font-family="sans-serif">{label}</text>')

    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        index = min(round((len(rows) - 1) * fraction), len(rows) - 1)
        x = LEFT + (index + 0.5) * step
        label = html.escape(str(rows[index].get("timestamp", ""))[:10])
        elements.append(f'<text x="{x:.1f}" y="895" fill="#94a3b8" font-size="11" text-anchor="middle" font-family="sans-serif">{label}</text>')

    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">' + "".join(elements) + "</svg>\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kline", required=True)
    parser.add_argument("--technical", help="Optional market technical JSON; otherwise calculate core indicators from K-line rows")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="First-board candidate")
    args = parser.parse_args()

    kline = load_document(args.kline)
    technical = load_document(args.technical) if args.technical else None
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(kline, technical, args.title), encoding="utf-8")
    print(json.dumps({"status": "ready", "output": str(output), "format": "svg"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
