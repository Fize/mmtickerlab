"""Deterministic market-derived metrics shared by plan-review reports.

The module keeps the score calculation separate from prose generation so every
report phase can reproduce the same value from the same validated snapshot.
"""

from __future__ import annotations

from typing import Any, Mapping
import math


FEAR_GREED_WEIGHTS = {
    "volume": 0.15,
    "breadth": 0.15,
    "rsi": 0.25,
    "momentum": 0.25,
    "volatility": 0.20,
}
FEAR_GREED_FORMULAS = {
    "volume": "50 + (当前成交额/前一交易日成交额 - 1) × 100",
    "breadth": "上涨家数 / (上涨家数 + 下跌家数) × 100",
    "rsi": "上证指数 14 个变动样本的 RSI",
    "momentum": "50 + 20 日上证指数收益率 × 500",
    "volatility": "100 - 20 日上证指数收益率标准差 × 2000",
}


def fear_greed_index(scores: Mapping[str, float]) -> dict[str, Any]:
    """Return the versioned weighted score and its auditable components."""
    missing = sorted(set(FEAR_GREED_WEIGHTS) - set(scores))
    if missing:
        raise ValueError(f"恐慌贪婪指数缺少分项：{missing}")
    invalid = {
        key: value for key, value in scores.items()
        if key in FEAR_GREED_WEIGHTS and not 0 <= float(value) <= 100
    }
    if invalid:
        raise ValueError(f"恐慌贪婪指数分项必须在 0 到 100：{invalid}")
    components = {
        key: {
            "score": round(float(scores[key]), 1),
            "weight": weight,
            "contribution": round(float(scores[key]) * weight, 2),
        }
        for key, weight in FEAR_GREED_WEIGHTS.items()
    }
    score = round(sum(item["contribution"] for item in components.values()), 1)
    if score < 20:
        level = "极度恐慌"
    elif score < 40:
        level = "恐慌"
    elif score < 60:
        level = "中性"
    elif score < 80:
        level = "贪婪"
    else:
        level = "极度贪婪"
    return {
        "version": "fg-v1", "score": score, "level": level,
        "weights": dict(FEAR_GREED_WEIGHTS), "formulas": dict(FEAR_GREED_FORMULAS),
        "components": components,
    }


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, value))


def fear_greed_from_market_data(
    snapshot: Mapping[str, Any],
    previous_snapshot: Mapping[str, Any],
    indices: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive all five components from validated market snapshots and index history."""
    metrics = snapshot.get("data", {}).get("metrics", {})
    previous_metrics = previous_snapshot.get("data", {}).get("metrics", {})
    turnover = float(metrics["total_turnover_yuan"])
    previous_turnover = float(previous_metrics["total_turnover_yuan"])
    denominator = int(metrics["up_count"]) + int(metrics["down_count"])
    if turnover <= 0 or previous_turnover <= 0 or denominator <= 0:
        raise ValueError("恐慌贪婪指数基础市场指标无效")
    rows = indices.get("data", {}).get("indices", {}).get("000001", {}).get("rows", [])
    closes = [float(row["close"]) for row in rows if row.get("close") is not None]
    if len(closes) < 20:
        raise ValueError("恐慌贪婪指数至少需要 20 个指数收盘样本")
    changes = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    gains = [max(change, 0) for change in changes[-14:]]
    losses = [max(-change, 0) for change in changes[-14:]]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    rsi = 100.0 if avg_loss == 0 and avg_gain else 50.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    volatility = math.sqrt(sum((change - sum(changes[-20:]) / min(20, len(changes[-20:]))) ** 2 for change in changes[-20:]) / min(20, len(changes[-20:])))
    scores = {
        "volume": _bounded(50 + (turnover / previous_turnover - 1) * 100),
        "breadth": _bounded(int(metrics["up_count"]) / denominator * 100),
        "rsi": _bounded(rsi),
        "momentum": _bounded(50 + (closes[-1] / closes[-20] - 1) * 500),
        "volatility": _bounded(100 - volatility * 2000),
    }
    return fear_greed_index(scores)


REQUIRED_COMMODITY_FIELDS = {
    "category", "instrument", "price", "change_pct", "change_5d", "unit", "as_of", "status",
}


def validate_commodity_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate the fixed commodity row contract before report rendering."""
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        missing = sorted(REQUIRED_COMMODITY_FIELDS - set(row))
        if missing:
            raise ValueError(f"商品行情第 {index + 1} 行缺少字段：{missing}")
        if row["status"] not in {"final", "intraday", "delayed", "closed", "unavailable"}:
            raise ValueError(f"商品行情第 {index + 1} 行状态无效：{row['status']}")
        if row["price"] is None and row["status"] != "unavailable":
            raise ValueError(f"商品行情第 {index + 1} 行价格缺失但状态不是 unavailable")
        normalized.append(dict(row))
    return normalized
